'''
import base64
import io
import json
import os
from datetime import datetime, date
from pathlib import Path

import werkzeug
import yaml
from flask_jwt_extended import jwt_required, get_jwt_identity
from flask_restful import Resource, reqparse, inputs
from kubernetes import client as k8s_client
from sqlalchemy.exc import NoResultFound
from werkzeug.utils import secure_filename
from urllib3.exceptions import MaxRetryError

import config
import model
import util as util
from model import db
from resources import apiError, role
from resources import kubernetesClient
from resources import release
from resources.system_parameter import check_upload_type
from resources.apiError import DevOpsError
from enums.action_type import ActionType
from resources.activity import record_activity
from resources.logger import logger

_DEFAULT_RESTART_NUMBER = 30
_DEFAULT_PROJECT_ID = "-1"

_ERROR_GET_REGISTRIES = "Get registries failed"

_ERROR_GET_CLUSTERS = "Get clusters failed"
_ERROR_CREATE_CLUSTERS = "Create clusters failed"
_ERROR_UPDATE_CLUSTERS = "Update clusters failed"
_ERROR_DELETE_CLUSTERS = "Delete clusters failed"


_ERROR_GET_DEPLOY_APPLICATION = "Get deploy application failed"
_ERROR_CREATE_DEPLOY_APPLICATION = "Create deploy application failed"
_ERROR_UPDATE_DEPLOY_APPLICATION = "Update deploy application failed"
_ERROR_DELETE_DEPLOY_APPLICATION = "Delete deploy application failed"
_ERROR_APPLICATION_EXISTS = "Deploy application had been deployed"
_ERROR_RESTART_DEPLOY_APPLICATION = "Deploy application had reached retry number limit"
_ERROR_RELEASE_APPLICATION = "Deploy application not found at gitlab"

# 20230215 為新增 application_header table 而新增下列一段程式
_ERROR_GET_APPLICATION_HEADER = "Get application header failed"
_ERROR_CREATE_APPLICATION_HEADER = "Create application header failed"
_ERROR_UPDATE_APPLICATION_HEADER = "Update application header failed"
_ERROR_DELETE_APPLICATION_HEADER = "Delete application header failed"
_ERROR_APPLICATION_HEADER_EXISTS = "Deploy application header had been deployed"
# 20230215 為新增 application_header table 而新增下列一段程式

# 20230119 新增下列程式，因新增取得DEPLOYMENT的API而新增下列錯誤訊息的程式
_ERROR_GET_DEPLOYMENT = "Get deployment failed"
# 202301198 新增上列程式，因新增取得DEPLOYMENT的API而新增上列錯誤訊息的程式

# 20230119 為取得 storage class 資訊而新增下列一段程式
_ERROR_GET_STORAGE_CLASS = "Get storage class failed"
_ERROR_CREATE_STORAGE_CLASS = "Create storage class failed"
# 20230119 為取得 storage class 資訊而新增上列一段程式
# 20230201 為變更 storage class disabled 布林值而新增下列一段程式
_ERROR_DISABLED_STORAGE_CLASS = "Change storage class disabled failed"
# 20230201 為變更 storage class disabled 布林值而新增上列一段程式
# 20230202 為取得 persistent volume claim 資訊而新增下列一段程式
_ERROR_GET_PERSISTENT_VOLUME_CLAIM = "Get persistent volume claim failed"
# 20230202 為取得 persistent volume claim 資訊而新增上列一段程式

_NEED_UPDATE_APPLICATION_STATUS = [1, 2, 3, 4, 9, 11]
_DEFAULT_K8S_CONFIG_FILE = "k8s_config"
_DEFAULT__APPLICATION_STATUS = "Something Error"
_APPLICATION_STATUS = {
    1: "Initializing",
    2: "Start Image replication",
    3: "Finish Image replication",
    4: "Start Kubernetes deployment",
    5: "Finish Kubernetes deployment",
    9: "Start Kubernetes deletion",
    10: "Finish Kubernetes deletion",
    11: "Initializing",
    32: "Deploy stopped",
    3001: "Error, No Image need to be replicated",
    5001: "Error, K8s Error",
}


def is_json(string):
    try:
        json.loads(string)
    except ValueError:
        return False
    return True


def get_environments_value(items, value_type):
    out_dict = {}
    for item in items:
        #  config map
        if item.get("type") == value_type and value_type == "configmap":
            out_dict[str(item.get("key")).strip()] = str(item.get("value")).strip()
        #  secret
        elif item.get("type") == value_type and value_type == "secret":
            out_dict[str(item.get("key")).strip()] = str(util.base64encode(item.get("value"))).strip()
    return out_dict


def row_to_dict(row):
    ret = {}
    if row is None:
        return row
    for key in type(row).__table__.columns.keys():
        value = getattr(row, key)
        if type(value) is datetime or type(value) is date:
            ret[key] = str(value)
        elif isinstance(value, str) and is_json(value):
            ret[key] = json.loads(value)
        else:
            ret[key] = value
    return ret


def get_cluster_directory_path(server_name):
    root_path = config.get("DEPLOY_CERTIFICATE_ROOT_PATH")
    return root_path + "/cluster/" + util.base64encode(server_name)


def get_cluster_config_path(server_name):
    return get_cluster_directory_path(server_name) + "/" + _DEFAULT_K8S_CONFIG_FILE


def check_directory_exists(server_name):
    cluster_path = get_cluster_directory_path(server_name)
    try:
        Path(cluster_path).mkdir(parents=True, exist_ok=True)
        return cluster_path
    except NoResultFound:
        return util.respond(404, "Create Server Directory Error")


def check_cluster(server_name, cluster_id=None):
    if cluster_id is None:
        return model.Cluster.query.filter(model.Cluster.name == server_name).first()
    else:
        return model.Cluster.query.filter(model.Cluster.name == server_name, model.Cluster.id != cluster_id).first()


def get_cluster_application_information(cluster):
    if cluster is None:
        return []
    output = row_to_dict(cluster)
    ret_output = []
    for application in cluster.application:
        if application is None or application.harbor_info is None:
            continue
        app = {}
        harbor_info = json.loads(application.harbor_info)
        app["id"] = application.id
        app["tag"] = harbor_info.get("tag_name")
        app["project_name"] = harbor_info.get("project")
        app["namespace"] = harbor_info.get("dest_repo_name")
        k8s_yaml = json.loads(application.k8s_yaml)
        cluster_status_id = k8s_yaml.get("status_id", 1)
        app["status"] = _APPLICATION_STATUS.get(cluster_status_id, _DEFAULT__APPLICATION_STATUS)
        ret_output.append(app)
    output["application"] = ret_output
    return output


def get_clusters(cluster_id=None):
    output = []
    if cluster_id is not None:
        return get_cluster_application_information(model.Cluster.query.filter_by(id=cluster_id).first())
    # 20230203 為了 [當使用者為系統管理員時自動判斷 id 為 0 的 cluster ，若不存在則自動新增。] 而新增下列程式段
    elif role.is_admin():
        if model.Cluster.query.filter_by(id=0).first() is None:
            server_name: str = "local-cluster"
            if model.Cluster.query.filter_by(name=server_name).first() is not None:
                for i in range(100):
                    server_name = "local-cluster-" + ("00" + str(i))[-2:]
                    if model.Cluster.query.filter_by(name=server_name).first() is None:
                        break
            user_id: int = get_jwt_identity()["user_id"]
            args = reqparse.Namespace()
            args["id"] = 0
            args["name"] = server_name
            args["k8s_config_file"] = werkzeug.datastructures.FileStorage(
                stream=io.BytesIO(open("/root/.kube/config", "rb").read()), filename="config"
            )
            args["disabled"] = False
            create_local_cluster(args, server_name, user_id)
    # 20230203 為了 [當使用者為系統管理員時自動判斷 id 為 0 的 cluster ，若不存在則自動新增。] 而新增上列程式段
    for cluster in model.Cluster.query.all():
        output.append(get_cluster_application_information(cluster))
    return output


def save_clusters(args, server_name):
    cluster_path = check_directory_exists(server_name)
    file_name = secure_filename(_DEFAULT_K8S_CONFIG_FILE)
    file_path = os.path.join(cluster_path, file_name)
    if args.get("k8s_config_file") is not None:
        file = args.get("k8s_config_file", None)
        file.save(os.path.join(cluster_path, file_name))
        file.seek(0)
        content = file.read()
        content = str(content, "utf-8")
    elif args.get("k8s_config_string") is not None:
        content = util.base64decode(args.get("k8s_config_string"))
        Path(file_path).write_text(content)
    else:
        raise apiError.DevOpsError(404, "Cluster config file cannot found")
    try:
        deploy_k8s_client = DeployK8sClient(server_name)
        deploy_k8s_client.get_api_resources()
    except NoResultFound:
        return util.respond(
            404,
            _ERROR_CREATE_CLUSTERS,
            error=apiError.create_cluster_failed(server_name),
        )
    k8s_json = yaml.safe_load(content)
    return k8s_json


def create_cluster(args, server_name, user_id):
    k8s_json = save_clusters(args, server_name)
    now = str(datetime.utcnow())
    new = model.Cluster(
        name=server_name,
        disabled=args.get("disabled", False),
        creator_id=user_id,
        create_at=now,
        update_at=now,
        cluster_name=k8s_json["clusters"][0]["name"],
        cluster_host=k8s_json["clusters"][0]["cluster"]["server"],
        cluster_user=k8s_json["users"][0]["name"],
    )
    db.session.add(new)
    db.session.commit()
    return new.id


# 20230203 為了 [當使用者為系統管理員時自動判斷 id 為 0 的 cluster ，若不存在則自動新增。] 而新增下列程式段
def create_local_cluster(args, server_name, user_id):
    k8s_json = save_clusters(args, server_name)
    now = str(datetime.utcnow())
    new = model.Cluster(
        id=0,
        name=server_name,
        disabled=args.get("disabled", False),
        creator_id=user_id,
        create_at=now,
        update_at=now,
        cluster_name=k8s_json["clusters"][0]["name"],
        cluster_host=k8s_json["clusters"][0]["cluster"]["server"],
        cluster_user=k8s_json["users"][0]["name"],
    )
    db.session.add(new)
    db.session.commit()
    return new.id


# 20230203 為了 [當使用者為系統管理員時自動判斷 id 為 0 的 cluster ，若不存在則自動新增。] 而新增上列程式段


def update_cluster(cluster_id, args):
    cluster = model.Cluster.query.filter_by(id=cluster_id).one()
    for key in args.keys():
        if not hasattr(cluster, key):
            continue
        elif args[key] is not None:
            setattr(cluster, key, args[key])
    server_name = args.get("name").strip()
    if args.get("k8s_config_file") is not None or args.get("k8s_config_string") is not None:
        k8s_json = save_clusters(args, server_name)
        cluster.cluster_name = (k8s_json["clusters"][0]["name"],)
        cluster.cluster_host = (k8s_json["clusters"][0]["cluster"]["server"],)
        cluster.cluster_user = k8s_json["users"][0]["name"]
    cluster.name = server_name
    cluster.update_at = str(datetime.utcnow())
    db.session.commit()
    return cluster.id


def delete_cluster(cluster_id):
    cluster = model.Cluster.query.filter_by(id=cluster_id).one()
    k8s_config_path = get_cluster_directory_path(cluster.name)
    k8s_file = Path(get_cluster_config_path(cluster.name))
    k8s_file.unlink()
    k8s_directory = Path(k8s_config_path)
    k8s_directory.rmdir()
    db.session.delete(cluster)
    db.session.commit()


class Clusters(Resource):
    @jwt_required()
    def get(self):
        try:
            output = get_clusters()
            return util.success({"cluster": output})
        except NoResultFound:
            return util.respond(404, _ERROR_GET_CLUSTERS, error=apiError.get_clusters_failed())

    @jwt_required()
    def post(self):
        try:
            user_id = get_jwt_identity()["user_id"]
            role.require_admin()
            parser = reqparse.RequestParser()
            parser.add_argument("name", type=str, location="form")
            parser.add_argument(
                "k8s_config_file",
                type=werkzeug.datastructures.FileStorage,
                location="files",
            )
            parser.add_argument("k8s_config_string", type=str, location="form")
            parser.add_argument("disabled", type=inputs.boolean, location="form")
            args = parser.parse_args()
            # check file upload
            if args.get("k8s_config_file"):
                file = args.get("k8s_config_file")
                check_upload_type(file)
                # check_upload_size(file)

            server_name = args.get("name").strip()
            if check_cluster(server_name) is not None:
                raise apiError.DevOpsError(
                    404,
                    _ERROR_CREATE_CLUSTERS,
                    error=apiError.create_cluster_failed(server_name),
                )
            output = {"cluster_id": create_cluster(args, server_name, user_id)}
            return util.success(output)
        except NoResultFound:
            return util.respond(404, _ERROR_CREATE_CLUSTERS, error=apiError.create_cluster_failed)


class Cluster(Resource):
    @jwt_required()
    def get(self, cluster_id):
        try:
            output = get_clusters(cluster_id)
            if output is None:
                return util.success()
            return util.success(output)
        except NoResultFound:
            return util.respond(404, _ERROR_GET_CLUSTERS, error=apiError.get_clusters_failed())

    @jwt_required()
    def put(self, cluster_id):
        try:
            role.require_admin()
            parser = reqparse.RequestParser()
            parser.add_argument("name", type=str, location="form")
            parser.add_argument(
                "k8s_config_file",
                type=werkzeug.datastructures.FileStorage,
                location="files",
            )
            parser.add_argument("disabled", type=inputs.boolean, location="form")
            parser.add_argument("k8s_config_string", type=str, location="form")
            args = parser.parse_args()
            server_name = args.get("name").strip()
            if check_cluster(server_name, cluster_id) is not None:
                return util.respond(
                    404,
                    _ERROR_UPDATE_CLUSTERS,
                    error=apiError.update_cluster_failed(server_name),
                )
            output = {"cluster_id": update_cluster(cluster_id, args)}
            return util.success(output)
        except NoResultFound:
            return util.respond(404, _ERROR_UPDATE_CLUSTERS, error=apiError.update_cluster_failed())

    @jwt_required()
    def delete(self, cluster_id):
        try:
            role.require_admin()
            delete_cluster(cluster_id)
            return util.success()
        except NoResultFound:
            return util.respond(404, _ERROR_DELETE_CLUSTERS, error=apiError.delete_cluster_failed())


def get_registries_application_information(registry):
    if registry is None:
        return []
    output = row_to_dict(registry)
    if output.get("type") == "harbor":
        output.update({"access_secret": util.base64decode(output.get("access_secret"))})
    ret_output = []
    for application in registry.application:
        if application is None or application.harbor_info is None:
            continue
        app = {}
        harbor_info = json.loads(application.harbor_info)
        app["id"] = application.id
        app["tag"] = harbor_info.get("tag_name")
        app["project_name"] = harbor_info.get("project")
        app["namespace"] = harbor_info.get("dest_repo_name")
        registry_status_id = harbor_info.get("status_id", 1)
        app["status"] = _APPLICATION_STATUS.get(registry_status_id, _DEFAULT__APPLICATION_STATUS)
        ret_output.append(app)
    output["application"] = ret_output
    return output


# 20230213 為了 [當使用者為系統管理員時自動判斷 id 為 0 的 registry ，若不存在則自動新增。] 而新增下列程式段
def create_local_registry(args):
    user_id = get_jwt_identity()["user_id"]
    # args["credential"] = {
    #     "access_key": args["access_key"],
    #     "access_secret": args["access_secret"],
    #     "type": "basic",
    # }
    if args["type"] == "harbor":
        args["access_secret"] = util.base64encode(args["access_secret"])
    registries_id = args["id"]
    new_registries = model.Registries(
        registries_id=registries_id,
        name=args["name"],
        user_id=user_id,
        description=args["description"],
        access_key=args["access_key"],
        access_secret=args["access_secret"],
        url=args["login_server"],
        type=args["type"],
        disabled=False,
    )
    model.db.session.add(new_registries)
    model.db.session.commit()
    return registries_id


# 20230213 為了 [當使用者為系統管理員時自動判斷 id 為 0 的 registry ，若不存在則自動新增。] 而新增上列程式段


def get_registries(registry_id=None):
    output = []
    if registry_id is not None:
        return get_registries_application_information(
            model.Registries.query.filter_by(registries_id=registry_id).first()
        )
    # 20230213 為了 [當使用者為系統管理員時自動判斷 id 為 0 的 registry ，若不存在則自動新增。] 而新增下列程式段
    elif role.is_admin():
        if model.Registries.query.filter_by(registries_id=0).first() is None:
            server_name: str = "local-registry"
            if model.Registries.query.filter_by(name=server_name).first() is not None:
                for i in range(100):
                    server_name = "local-registry-" + ("00" + str(i))[-2:]
                    if model.Registries.query.filter_by(name=server_name).first() is None:
                        break
            args = reqparse.Namespace()
            args["id"] = 0
            args["name"] = server_name
            args["type"] = "harbor"
            args["access_key"] = config.get("HARBOR_ACCOUNT")
            args["access_secret"] = config.get("HARBOR_PASSWORD")
            args["location"] = ""
            args["login_server"] = config.get("HARBOR_EXTERNAL_BASE_URL")
            args["description"] = ""
            args["insecure"] = True
            create_local_registry(args)
    # 20230213 為了 [當使用者為系統管理員時自動判斷 id 為 0 的 registry ，若不存在則自動新增。] 而新增上列程式段
    for registry in model.Registries.query.filter().all():
        output.append(get_registries_application_information(registry))

    return output


class Registries(Resource):
    @jwt_required()
    def get(self):
        try:
            output = get_registries()
            return util.success({"registries": output})
        except NoResultFound:
            return util.respond(404, _ERROR_GET_REGISTRIES, error=apiError.get_registry_failed())


class Registry(Resource):
    @jwt_required()
    def get(self, registry_id):
        try:
            output = get_registries(registry_id)
            return util.success({"registries": output})
        except NoResultFound:
            return util.respond(
                404,
                _ERROR_GET_REGISTRIES,
                error=apiError.get_registry_failed(registry_id),
            )


def create_default_harbor_data(project, db_release, registry_id, namespace, app_name):
    db_release_id = str(db_release.id)
    harbor_data = {
        "project": project.display,
        "project_id": project.name,
        "policy_name": f"{project.name}-release-{db_release_id}-at-{namespace}-{app_name}",
        "repo_name": project.name,
        "image_name": db_release.branch,
        "tag_name": db_release.tag_name,
        "description": "Automate create replication policy " + project.name + " release ID " + db_release_id,
        "registry_id": registry_id,
        "dest_repo_name": namespace,
        "status": "initial",
    }
    return harbor_data


# Remove Object Key with Target
def remove_object_key_by_value(items, target=None):
    output = {}
    if items is None:
        return output
    for key in items.keys():
        m_key = str(key).strip()
        m_value = items[key]
        if isinstance(items[key], int) is not True:
            m_value = str(items[key]).strip()
        if target is None or items[key] != target:
            output[m_key] = m_value
    return output


def create_default_k8s_data(db_project, db_release, args):
    if db_release is None:
        image_name = None
        tag_name = None
    else:
        image_name = db_release.branch
        tag_name = db_release.tag_name
    k8s_data = {
        "app_name": args.get("name"),
        "project": db_project.display,
        "project_id": db_project.name,
        "repo_name": db_project.name,
        "image_name": image_name,
        "tag_name": tag_name,
        "namespace": args.get("namespace"),
        "image": args.get("image", {"policy": "Always"}),
        "status_id": 1,
        "deploy_finish": False,
    }
    resources = remove_object_key_by_value(args.get("resources", {}), "")
    if resources != {}:
        k8s_data["resources"] = resources

    network = remove_object_key_by_value(args.get("network", {}), "")
    if "ports" in args.get("network", {}):
        ports: list = []
        for port in args.get("network", {}).get("ports"):
            ports.append(remove_object_key_by_value(port))
        network["ports"] = ports
    if network != {}:
        k8s_data["network"] = network

    environments = args.get("environments", None)
    if environments is not None:
        items = []
        for env in environments:
            item = remove_object_key_by_value(env)
            if item is not None:
                items.append(item)
        if len(items) > 0:
            k8s_data["environments"] = items
    volumes = args.get("volumes", None)
    if volumes is not None:
        items = []
        for vol in volumes:
            item = remove_object_key_by_value(vol)
            if item is not None:
                items.append(item)
        if len(items) > 0:
            k8s_data["volumes"] = items
    return k8s_data


def harbor_policy_exist(target, policies):
    check_result = False
    policy_id = 0
    for policy in policies:
        if str(target) == str(policy.get("name")):
            check_result = True
            policy_id = policy.get("id")
            break
    return check_result, policy_id


def initial_harbor_replication_image_policy(app):
    harbor_info = json.loads(app.harbor_info)
    if "project" in harbor_info:
        harbor_info.pop("project")
    if "status" in harbor_info:
        harbor_info.pop("status")

    query_data = {"name": harbor_info.get("policy_name")}
    check, policy_id = harbor_policy_exist(
        harbor_info.get("policy_name"),
        harbor.hb_get_replication_policies(args=query_data),
    )
    if not check:
        policy_id = harbor.hb_create_replication_policy(harbor_info)
    else:
        harbor.hb_put_replication_policy(harbor_info, policy_id)
    return policy_id


def execute_replication_policy(policy_id):
    return harbor.hb_execute_replication_policy(policy_id)


def get_replication_executions(policy_id):
    return harbor.hb_get_replication_executions(policy_id)


def get_replication_execution_task(policy_id):
    return harbor.hb_get_replication_execution_task(policy_id)


def check_replication_policy(policy_id):
    polices = harbor.hb_get_replication_policy()
    check = False
    for policy in polices:
        if policy.get("id") == policy_id:
            check = True
            break
    return check


def get_replication_policy(policy_id):
    return harbor.hb_get_replication_policy(policy_id)


def delete_replication_policy(policy_id):
    return harbor.hb_delete_replication_policy(policy_id)


def check_image_replication_status(task):
    output = False
    if task.get("status") == "Succeed":
        output = True
    return output


def execute_image_replication(app, restart=False):
    task_info = None
    harbor_info = json.loads(app.harbor_info)
    if not restart or harbor_info.get("policy") is None or harbor_info.get("image_uri"):
        output = create_replication_policy(app)
        policy_id = output.get("policy_id")
    else:
        policy_id = harbor_info.get("policy").get("id")
        output = {
            "policy": harbor_info.get("policy"),
            "policy_id": harbor_info.get("policy_id"),
        }

    execution_info = check_execute_replication_policy(policy_id, harbor_info, restart)
    output.update(execution_info)
    if execution_info.get("status_id") == 2:
        task_info = check_replication_execution_task(execution_info.get("execution_id"))
    if task_info is not None:
        output.update(task_info)
    return output


def create_replication_policy(app):
    policy_id = initial_harbor_replication_image_policy(app)
    policy = get_replication_policy(policy_id)
    return {"policy": policy, "policy_id": policy_id}


def check_execute_replication_policy(policy_id, harbor_info, restart=False):
    executions = get_replication_executions(policy_id)
    if not executions or restart:
        image_uri = execute_replication_policy(policy_id)
    else:
        image_uri = harbor_info.get("image_uri")
    output = {
        "image_uri": image_uri,
    }
    if executions:
        execution = executions[0]
        output.update(
            {
                "executions": executions,
                "execution_id": executions[0]["id"],
                "status_id": 2,
            }
        )
        if execution.get("total") == 0 and execution.get("status") == "Succeed":
            output["status"] = "Error"
            output["error"] = "no resource need to be replicated"
            output["status_id"] = 3001

    return output


def check_replication_execution_task(execution_id):
    output = None
    tasks = get_replication_execution_task(execution_id)
    if len(tasks) > 0:
        output = {
            "task_id": tasks[0]["id"],
            "task": tasks,
            "status": tasks[0]["status"],
            "status_id": 2,
        }
        if tasks[0]["status"] == "Succeed":
            output["status_id"] = 3
    return output


def create_registry_data(server_name, user_name, password):
    pay_load = {"auths": {server_name: {"Username": user_name, "Password": password}}}
    return {".dockerconfigjson": base64.b64encode(json.dumps(pay_load).encode()).decode()}


def create_registry_secret_object(secret_name, data):
    return k8s_client.V1Secret(
        api_version="v1",
        data=data,
        kind="Secret",
        metadata=k8s_client.V1ObjectMeta(name=secret_name),
        type="kubernetes.io/dockerconfigjson",
    )


def create_secret_object(secret_name, secret_dict):
    body = k8s_client.V1Secret(
        api_version="v1",
        kind="Secret",
        metadata=k8s_client.V1ObjectMeta(
            name=secret_name,
        ),
        data=secret_dict,
    )
    return body


def create_configmap_object(configmap_name, configmap_dict):
    body = k8s_client.V1ConfigMap(
        metadata=k8s_client.V1ObjectMeta(
            name=configmap_name,
        ),
        data=configmap_dict,
    )
    return body


def create_pvc_object(pvc_dict):
    body: list = []
    pvc_list: list = []
    if isinstance(pvc_dict, list):
        pvc_list = pvc_dict
    else:
        pvc_list.append(pvc_dict)

    for pvc in pvc_list:
        body.append(
            k8s_client.V1PersistentVolumeClaim(
                api_version="v1",
                kind="PersistentVolumeClaim",
                metadata=k8s_client.V1ObjectMeta(name=pvc.get("pvc_name")),
                spec=k8s_client.V1PersistentVolumeClaimSpec(
                    # storage_class_name="deploy-local-sc",
                    storage_class_name=pvc.get("sc_name"),
                    access_modes=["ReadWriteMany"],
                    resources=k8s_client.V1ResourceRequirements(requests={"storage": "5Gi"}),
                ),
            )
        )
    return body


def create_service_port(network):
    """
    20230218 因為舊的 network 只有一組 protocol、port 及 expose_port。
    為了改成多組的 protocol、port 及 expose_port 增加了 ports 這個 key 來存放。
    但因為原本的資料庫中存放的是舊的 network 只有一組 protocol、port 及 expose_port，
    所以程式修改如下，讓其新舊格式皆可處理。
    """
    service_ports: list = []
    if "ports" in network:
        ports = network.get("ports", [])
    else:
        ports = [network]
    for port in ports:
        if port.get("expose_port") is not None:
            service_port = k8s_client.V1ServicePort(
                protocol=port.get("protocol"),
                port=port.get("port"),
                node_port=port.get("expose_port"),
                target_port=port.get("port"),
            )
        else:
            service_port = k8s_client.V1ServicePort(
                protocol=port.get("protocol"),
                port=port.get("port"),
                target_port=port.get("port"),
            )
        service_ports.append(service_port)
    return service_ports


def create_service_object(app_name, service_name, network):
    return k8s_client.V1Service(
        api_version="v1",
        kind="Service",
        metadata=k8s_client.V1ObjectMeta(name=service_name),
        spec=k8s_client.V1ServiceSpec(
            type=network.get("type"),
            selector={"app": app_name},
            ports=create_service_port(network),
        ),
    )


def init_resource_requirements(resources):
    if resources is None:
        return k8s_client.V1ResourceRequirements()
    else:
        return k8s_client.V1ResourceRequirements(
            limits={"cpu": resources.get("cpu"), "memory": resources.get("memory")}
        )


def create_deployment_object(
    app_name,
    deployment_name,
    image_uri,
    ports: list,
    registry_secret_name,
    resource=None,
    image=None,
    env=None,
    volume_devices=[],
):
    # Configured Pod template container
    default_image_policy = "Always"
    if "type" not in image or image.get("type") == "harbor":
        if image is not None and image.get("policy", None) is not None:
            default_image_policy = image.get("policy", None)
    vm_list: list = []
    v_list: list = []
    for vd in volume_devices:
        vm_list.append(k8s_client.V1VolumeMount(mount_path=vd.get("device_path"), name=vd.get("pvc_name")))
        v_list.append(
            k8s_client.V1Volume(
                name=vd.get("pvc_name"),
                persistent_volume_claim=k8s_client.V1PersistentVolumeClaimVolumeSource(claim_name=vd.get("pvc_name")),
            )
        )
    container_ports: list = []
    for port in ports:
        container_ports.append(k8s_client.V1ContainerPort(container_port=port))
    container = k8s_client.V1Container(
        name=app_name,
        image=image_uri,
        ports=container_ports,
        resources=init_resource_requirements(resource),
        image_pull_policy=default_image_policy,
        volume_mounts=vm_list,
    )
    if env is not None:
        env_list = [k8s_client.V1EnvVar(name=key, value=value) for key, value in env.items()]
        container.env = env_list

    # Create and configure a spec section
    template = k8s_client.V1PodTemplateSpec(
        metadata=k8s_client.V1ObjectMeta(labels={"app": app_name}),
        spec=k8s_client.V1PodSpec(
            containers=[container],
            image_pull_secrets=[k8s_client.V1LocalObjectReference(name=registry_secret_name)],
            volumes=v_list,
        ),
    )
    num_replicas = 1
    if resource is not None and resource.get("replicas", None) is not None:
        num_replicas = resource.get("replicas", None)
    # Create the specification of deployment
    spec = k8s_client.V1DeploymentSpec(
        replicas=num_replicas,
        template=template,
        selector={"matchLabels": {"app": app_name}},
    )
    # Instantiate the deployment object
    deployment = k8s_client.V1Deployment(
        api_version="apps/v1",
        kind="Deployment",
        metadata=k8s_client.V1ObjectMeta(name=deployment_name),
        spec=spec,
    )
    return deployment


def create_ingress_object(ingress_name, domain, service_name, port, path):
    spec = k8s_client.NetworkingV1beta1IngressSpec(
        rules=[
            k8s_client.NetworkingV1beta1IngressRule(
                host=domain,
                http=k8s_client.NetworkingV1beta1HTTPIngressRuleValue(
                    paths=[
                        k8s_client.NetworkingV1beta1HTTPIngressPath(
                            path=path,
                            backend=k8s_client.NetworkingV1beta1IngressBackend(
                                service_name=service_name, service_port=port
                            ),
                        )
                    ]
                ),
            )
        ]
    )
    metadata = k8s_client.V1ObjectMeta(
        name=ingress_name,
        annotations={
            "nginx.ingress.kubernetes.io/rewrite-target": "/",
        },
    )
    body = k8s_client.NetworkingV1beta1Ingress(
        # NetworkingV1beta1Api
        api_version="networking.k8s.io/v1beta1",
        kind="Ingress",
        metadata=metadata,
        spec=spec,
    )
    return body


def create_namespace_object(namespace):
    return k8s_client.V1Namespace(metadata=k8s_client.V1ObjectMeta(name=namespace))


def k8s_resource_exist(target, response):
    check_result = False
    for i in response.items:
        if str(target) == str(i.metadata.name):
            check_result = True
    return check_result


class DeployK8sClient:
    def __init__(self, server_name):
        self.client = kubernetesClient.ApiK8sClient(configuration_file=get_cluster_config_path(server_name))

    def get_api_resources(self):
        return self.client.get_api_resources()

    # namespace
    def read_namespace(self, namespace):
        if self.check_namespace(namespace):
            return self.client.read_namespace(namespace)
        else:
            return {}

    def create_namespace(self, namespace, body):
        if not self.check_namespace(namespace):
            return self.client.create_namespace(body)

    def delete_namespace(self, namespace):
        if self.check_namespace(namespace):
            return self.client.delete_namespace(namespace)

    def check_namespace(self, namespace):
        return k8s_resource_exist(namespace, self.client.list_namespace())

    def execute_namespace_secret(self, name, namespace, body):
        if not self.check_namespace_secret(name, namespace):
            return self.client.create_namespaced_secret(namespace, body)
        else:
            return self.client.patch_namespaced_secret(name, namespace, body)

    def delete_namespace_secret(self, name, namespace):
        if self.check_namespace_secret(name, namespace):
            return self.client.delete_namespaced_secret(name, namespace)

    def check_namespace_secret(self, name, namespace):
        return k8s_resource_exist(name, self.client.list_namespaced_secret(namespace))

    def read_namespace_service(self, name, namespace):
        if self.check_namespace_service(name, namespace):
            return self.client.read_namespaced_service(name, namespace)
        return None

    def execute_namespace_service(self, name, namespace, body):
        if not self.check_namespace_service(name, namespace):
            return self.client.create_namespaced_service(namespace, body)
        else:
            return self.client.patch_namespaced_service(name, namespace, body)

    def delete_namespace_service(self, name, namespace):
        if self.check_namespace_service(name, namespace):
            return self.client.delete_namespaced_service(name, namespace)

    def check_namespace_service(self, name, namespace):
        return k8s_resource_exist(name, self.client.list_namespaced_service(namespace))

    def read_namespace_ingress(self, name, namespace):
        if self.check_namespace_ingress(name, namespace):
            return self.client.read_namespaced_ingress(name, namespace)
        return None

    def execute_namespace_ingress(self, name, namespace, body):
        if not self.check_namespace_ingress(name, namespace):
            return self.client.create_namespaced_ingress(namespace, body)
        else:
            return self.client.patch_namespaced_ingress(name, namespace, body)

    def delete_namespace_ingress(self, name, namespace):
        if self.check_namespace_ingress(name, namespace):
            return self.client.delete_namespaced_ingress(name, namespace)

    def check_namespace_ingress(self, name, namespace):
        return k8s_resource_exist(name, self.client.list_namespaced_ingress(namespace))

    def read_namespace_deployment(self, name, namespace):
        if self.check_namespace_deployment(name, namespace):
            return self.client.read_namespaced_deployment(name, namespace)
        return None

    def execute_namespace_deployment(self, name, namespace, body):
        if not self.check_namespace_deployment(name, namespace):
            return self.client.create_namespaced_deployment(namespace, body)
        else:
            return self.client.patch_namespaced_deployment(name, namespace, body)

    def delete_namespace_deployment(self, name, namespace):
        if self.check_namespace_deployment(name, namespace):
            return self.client.delete_namespaced_deployment(name, namespace)

    def check_namespace_deployment(self, name, namespace):
        return k8s_resource_exist(name, self.client.list_namespaced_deployment(namespace))

    def execute_namespace_configmap(self, name, namespace, body):
        if not self.check_namespace_configmap(name, namespace):
            return self.client.create_namespaced_config_map(namespace, body)
        else:
            return self.client.patch_namespaced_config_map(name, namespace, body)

    def delete_namespace_configmap(self, name, namespace):
        if self.check_namespace_configmap(name, namespace):
            return self.client.delete_namespaced_configmap(name, namespace)

    def check_namespace_configmap(self, name, namespace):
        return k8s_resource_exist(name, self.client.list_namespaced_config_map(namespace))

    def execute_namespace_pvc(self, namespace, body_list):
        pvc_list: list = []
        for body in body_list:
            if not self.check_namespace_pvc(body.metadata.name, namespace):
                pvc_list.append(self.client.create_namespace_pvc(namespace, body))
            else:
                pvc_list.append(self.client.read_namespace_pvc(body.metadata.name, namespace))
        return pvc_list

    # 20230102 為取得 persistent volume claim 資訊而新增下列一段程式
    def list_persistent_volume_claim(self, namespace: str):
        return self.client.list_namespace_pvc(namespace)

    def read_persistent_volume(self, name: str):
        return self.client.read_persistent_volume(name)

    # 20230202 為取得 persistent volume claim 資訊而新增上列一段程式

    def delete_namespace_pvc(self, name, namespace):
        if self.check_namespace_pvc(name, namespace):
            return self.client.delete_namespace_pvc(name, namespace)

    def check_namespace_pvc(self, name, namespace):
        return k8s_resource_exist(name, self.client.list_namespace_pvc(namespace))

    # 20230118 為取得 storage class 資訊而新增下列一段程式
    def list_storage_class(self):
        return self.client.list_storage_class()

    def check_storage_class(self, name):
        return k8s_resource_exist(name, self.client.list_storage_class())

    # 20230118 為取得 storage class 資訊而新增上列一段程式


class DeployNamespace:
    def __init__(self, namespace):
        self.namespace = namespace

    def namespace_body(self):
        return create_namespace_object(self.namespace)


class DeployConfigMap:
    def __init__(self, app, project):
        self.app = app
        self.project = project
        self.configmap_name = None
        self.configmap_dict = None
        self.set_configmap_data()

    def get_configmap_info(self):
        return {"configmap_name": self.configmap_name}

    def set_configmap_data(self):
        environments = json.loads(self.app.k8s_yaml).get("environments", None)
        self.configmap_dict = get_environments_value(environments, "configmap")
        self.configmap_name = self.project.name + "-configmap"

    def configmap_body(self):
        return create_configmap_object(self.configmap_name, self.configmap_dict)


class DeployPVC:
    def __init__(self, app, project):
        self.app = app
        self.project = project
        self.sc_name = None
        self.pvc_name = None
        self.device_path = None
        self.pvc_dict = None
        self.set_pvc_data()

    def get_pvc_info(self):
        list_len: int = min(len(self.sc_name), len(self.pvc_name), len(self.device_path))
        info: list = []
        for i in range(list_len):
            info.append({"sc_name": self.sc_name[i], "pvc_name": self.pvc_name[i], "device_path": self.device_path[i]})
        return info

    def set_pvc_data(self):
        self.pvc_dict = json.loads(self.app.k8s_yaml).get("volumes", None)
        pvc_list = []
        if isinstance(self.pvc_dict, list):
            pvc_list = self.pvc_dict
        else:
            pvc_list.append(self.pvc_dict)
        self.sc_name = []
        self.pvc_name = []
        self.device_path = []
        for i in range(len(pvc_list)):
            self.sc_name.append(pvc_list[i].get("sc_name"))
            if pvc_list[i].get("pvc_name", None) is None:
                self.pvc_name.append(self.project.name + "-pvc-" + str(i))
            else:
                self.pvc_name.append(pvc_list[i].get("pvc_name"))
            self.device_path.append(pvc_list[i].get("device_path"))

    def pvc_body(self):
        return create_pvc_object(self.pvc_dict)


class DeploySecret:
    def __init__(self, app, project):
        self.app = app
        self.project = project
        self.secret_name = None
        self.secret_dict = None
        self.set_secret_data()

    def get_secret_info(self):
        return {"secret_name": self.secret_name}

    def set_secret_data(self):
        environments = json.loads(self.app.k8s_yaml).get("environments", None)
        self.secret_dict = get_environments_value(environments, "secret")
        self.secret_name = self.project.name + "-secret"

    def secret_body(self):
        return create_secret_object(self.secret_name, self.secret_dict)


class DeployRegistrySecret:
    def __init__(self, app, registry):
        self.registry = registry
        self.app = app
        self.registry_server_url = None
        self.registry_secret_name = None
        self.set_registry_secret_info()

    def set_registry_secret_info(self):
        harbor_info = json.loads(self.app.harbor_info)
        self.registry_server_url = harbor_info.get("image_uri").split("/")[0]
        self.registry_secret_name = self.registry_server_url.translate(str.maketrans({".": "-", ":": "-"})) + "-harbor"

    def get_registry_secret_info(self):
        return {
            "registry_secret_url": self.registry_server_url,
            "registry_secret_name": self.registry_secret_name,
        }

    def registry_secret_body(self):
        return create_registry_secret_object(
            self.registry_secret_name,
            create_registry_data(
                self.registry_server_url,
                self.registry.access_key,
                util.base64decode(self.registry.access_secret),
            ),
        )


class DeployService:
    def __init__(self, app, project):
        k8s_info = json.loads(app.k8s_yaml)
        release_id = str(app.release_id)
        if "type" in k8s_info.get("image") and k8s_info.get("image").get("type") != "harbor":
            release_id = k8s_info.get("image").get("type")
        self.app = app
        self.project = project
        self.k8s_info = k8s_info
        self.name = f"{project.name}-release-{release_id}-{app.name}"
        self.service_name = f"{self.project.name}-service-{release_id}-{app.name}"

    def get_service_info(self):
        network = self.k8s_info.get("network")
        container_port: list = []
        expose_port: list = []
        if "ports" in network:
            for port in network.get("ports"):
                container_port.append(port.get("port"))
                expose_port.append(port.get("expose_port"))
        else:
            container_port.append(network.get("port"))
            expose_port.append(network.get("expose_port"))
        output = {
            "service_name": self.service_name,
            "port": container_port,
            "container_port": container_port,
            "expose_port": expose_port,
        }
        return output

    def service_body(self):
        return create_service_object(self.name, self.service_name, self.k8s_info.get("network"))


class DeployIngress:
    def __init__(self, app, project):
        release_id = str(app.release_id)
        self.app = app
        self.k8s_info = json.loads(app.k8s_yaml)
        self.service_name = f"{project.name}-service-{release_id}-{app.name}"
        self.ingress_name = f"{project.name}-ingress-{release_id}-{app.name}"

    def get_ingress_info(self):
        return {
            "ingress_name": self.ingress_name,
            "domain": self.k8s_info.get("network").get("domain"),
            "port": self.k8s_info.get("network").get("port"),
            "path": self.k8s_info.get("network").get("path"),
        }

    def ingress_body(self):
        return create_ingress_object(
            self.ingress_name,
            self.k8s_info.get("network").get("domain"),
            self.service_name,
            self.k8s_info.get("network").get("port"),
            self.k8s_info.get("network").get("path"),
        )


class DeployDeployment:
    def __init__(self, app, project, service_info, registry_secret_info: dict = {}):
        harbor_info = json.loads(app.harbor_info)
        k8s_info = json.loads(app.k8s_yaml)
        image = k8s_info.get("image")
        release_id: str = str(app.release_id)
        if "type" not in image or image.get("type") == "harbor":
            image_uri = harbor_info.get("image_uri")
        else:
            image_uri = image.get("uri")
            release_id = image.get("type")
        self.app = app
        self.namespace = self.app.namespace
        self.name = f"{project.name}-release-{release_id}-{app.name}"
        self.harbor_info = harbor_info
        self.k8s_info = k8s_info
        self.deployment_name = f"{project.name}-dep-{app.name}"
        self.service_info = service_info
        self.registry_secret_info = registry_secret_info
        self.image_uri = image_uri

    def get_deployment_info(self):
        return {"deployment_name": self.deployment_name}

    def get_env(self):
        env = None
        environments = json.loads(self.app.k8s_yaml).get("environments", None)
        if environments is not None:
            env = {environment["key"]: environment["value"] for environment in environments}
        return env

    def deployment_body(self):
        return create_deployment_object(
            self.name,
            self.deployment_name,
            self.image_uri,
            self.service_info.get("container_port"),
            self.registry_secret_info.get("registry_secret_name"),
            self.k8s_info.get("resources"),
            self.k8s_info.get("image"),
            self.get_env(),
            json.loads(self.app.k8s_yaml).get("volumes", []),
        )


class K8sDeployment:
    def __init__(self, app):
        self.app = app
        self.cluster = model.Cluster.query.filter_by(id=app.cluster_id).first()
        self.project = model.Project.query.filter_by(id=app.project_id).first()
        self.registry = model.Registries.query.filter_by(registries_id=app.registry_id).first()
        self.k8s_client = DeployK8sClient(self.cluster.name)
        self.k8s_info = json.loads(app.k8s_yaml)
        image = self.k8s_info.get("image")
        if "type" not in image:
            self.image_type = "harbor"
        else:
            self.image_type = image.get("type")
        self.volumes = self.k8s_info.get("volumes")
        self.namespace = None
        self.registry_secret = None
        self.service = None
        self.ingress = None
        self.pvc = None
        self.deployment = None
        self.configmap = None
        self.secret = None
        self.deployment_info = {}

    def check_namespace(self):
        self.namespace = DeployNamespace(self.app.namespace)
        self.k8s_client.create_namespace(self.app.namespace, self.namespace.namespace_body())

    def check_registry_secret(self):
        if self.registry_secret is None:
            self.registry_secret = DeployRegistrySecret(self.app, self.registry)

    def execute_registry_secret(self):
        self.check_registry_secret()
        self.k8s_client.execute_namespace_secret(
            self.registry_secret.registry_secret_name,
            self.app.namespace,
            self.registry_secret.registry_secret_body(),
        )
        self.deployment_info["registry_secret"] = self.registry_secret.get_registry_secret_info()

    def check_service(self):
        if self.service is None:
            self.service = DeployService(self.app, self.project)

    def execute_service(self):
        self.check_service()
        self.k8s_client.execute_namespace_service(
            self.service.service_name, self.app.namespace, self.service.service_body()
        )
        self.deployment_info["service"] = self.service.get_service_info()

    def check_pvc(self):
        if self.pvc is None:
            self.pvc = DeployPVC(self.app, self.project)

    def execute_pvc(self):
        self.check_pvc()
        self.k8s_client.execute_namespace_pvc(self.app.namespace, self.pvc.pvc_body())
        self.deployment_info["volumes"] = self.pvc.get_pvc_info()

    def check_ingress(self):
        if self.ingress is None:
            self.ingress = DeployIngress(self.app, self.project)

    def execute_ingress(self):
        self.check_ingress()
        self.k8s_client.execute_namespace_ingress(
            self.ingress.ingress_name, self.app.namespace, self.ingress.ingress_body()
        )
        self.deployment_info["ingress"] = self.ingress.get_ingress_info()

    def check_deployment(self):
        if self.deployment is None:
            self.check_service()
            if self.image_type == "harbor":
                self.check_registry_secret()
                self.deployment = DeployDeployment(
                    self.app,
                    self.project,
                    self.service.get_service_info(),
                    self.registry_secret.get_registry_secret_info(),
                )
            else:
                self.deployment = DeployDeployment(
                    self.app,
                    self.project,
                    self.service.get_service_info(),
                )

    def execute_deployment(self):
        self.check_deployment()
        self.k8s_client.execute_namespace_deployment(
            self.deployment.deployment_name,
            self.app.namespace,
            self.deployment.deployment_body(),
        )
        self.deployment_info["deployment"] = self.deployment.get_deployment_info()

    def check_configmap(self):
        if self.configmap is None:
            self.configmap = DeployConfigMap(self.app, self.project)

    def execute_configmap(self):
        self.check_configmap()
        if self.configmap.configmap_dict != {}:
            self.k8s_client.execute_namespace_configmap(
                self.configmap.configmap_name,
                self.app.namespace,
                self.configmap.configmap_body(),
            )
            self.deployment_info["configmap"] = self.configmap.get_configmap_info()

    def check_secret(self):
        if self.secret is None:
            self.secret = DeploySecret(self.app, self.project)

    def execute_secret(self):
        self.check_secret()
        if self.secret.secret_dict != {}:
            self.k8s_client.execute_namespace_secret(
                self.secret.secret_name, self.app.namespace, self.secret.secret_body()
            )
            self.deployment_info["secret"] = self.secret.get_secret_info()

    def get_deployment_information(self):
        return self.deployment_info


def execute_k8s_deployment(app):
    k8s_deployment = K8sDeployment(app)
    k8s_deployment.check_namespace()
    if k8s_deployment.image_type == "harbor":
        k8s_deployment.execute_registry_secret()
    k8s_deployment.execute_service()
    k8s_info = json.loads(app.k8s_yaml)
    if k8s_info.get("volumes", None) is not None:
        k8s_deployment.execute_pvc()
    if k8s_info.get("network").get("domain", None) is not None:
        k8s_deployment.execute_ingress()
    if k8s_info.get("environments", None) is not None:
        k8s_deployment.execute_configmap()
        k8s_deployment.execute_secret()
    k8s_deployment.execute_deployment()
    return k8s_deployment.get_deployment_information()


# check Deployment status
def check_k8s_deployment(app, deployed=True):
    deployed_status = []
    deploy_object = json.loads(app.k8s_yaml)
    cluster = model.Cluster.query.filter_by(id=app.cluster_id).first()
    deploy_k8s_client = DeployK8sClient(cluster.name)

    if deploy_object.get("deployment") is not None:
        deployed_status.append(
            deploy_k8s_client.check_namespace_deployment(
                deploy_object.get("deployment").get("deployment_name"), app.namespace
            )
        )

    if deploy_object.get("ingress") is not None:
        deployed_status.append(
            deploy_k8s_client.check_namespace_ingress(deploy_object.get("ingress").get("ingress_name"), app.namespace)
        )

    if deploy_object.get("service") is not None:
        deployed_status.append(
            deploy_k8s_client.check_namespace_service(deploy_object.get("service").get("service_name"), app.namespace)
        )
    if deploy_object.get("registry_secret") is not None:
        deployed_status.append(
            deploy_k8s_client.check_namespace_secret(
                deploy_object.get("registry_secret").get("registry_secret_name"),
                app.namespace,
            )
        )

    return deployed_status.count(deployed) == len(deployed_status)


def reset_restart_number(app):
    app.restart_number = 1
    app.restarted_at = str(datetime.utcnow())
    return app


def check_application_restart(app):
    if app.restart_number is None:
        app = reset_restart_number(app)
    else:
        app.restart_number = app.restart_number + 1
    app.restarted_at = str(datetime.utcnow())
    db.session.commit()


def check_application_status(app):
    output = {}
    if app is None:
        return output
    application_id = app.id
    # check_application_restart(app)
    app = model.Application.query.filter_by(id=application_id).first()
    # Check Harbor Replication execution
    if app.status_id == 1:
        if app.harbor_info == "{}":
            app.status_id = 2
        else:
            output = execute_image_replication(app)
            harbor_info = json.loads(app.harbor_info)
            harbor_info.update(output)
            app.harbor_info = json.dumps(harbor_info)
            app.status_id = harbor_info.get("status_id", app.status_id)
        app = reset_restart_number(app)
        db.session.commit()
    # Restart Execution Replication
    elif app.status_id == 11 or app.status_id == 2:
        if app.harbor_info == "{}":
            app.status_id = 3
        else:
            harbor_info = json.loads(app.harbor_info)
            output = execute_image_replication(app, True)
            harbor_info.update(output)
            app.status_id = harbor_info.get("status_id", app.status_id)
            app.harbor_info = json.dumps(harbor_info)
        if app.status_id == 3:
            app = reset_restart_number(app)
        db.session.commit()
    elif app.status_id == 3:
        k8s_yaml = json.loads(app.k8s_yaml)
        output = execute_k8s_deployment(app)
        k8s_yaml.update(output)
        app.status_id = 4
        app.k8s_yaml = json.dumps(k8s_yaml)
        app = reset_restart_number(app)
        db.session.commit()
    elif app.status_id == 4:
        k8s_yaml = json.loads(app.k8s_yaml)
        k8s_yaml["deploy_finish"] = check_k8s_deployment(app)
        if k8s_yaml["deploy_finish"]:
            k8s_yaml["status_id"] = 5
            app.status_id = 5
            app = reset_restart_number(app)
            app.k8s_yaml = json.dumps(k8s_yaml)
            db.session.commit()
    elif app.status_id == 9:
        finished = check_k8s_deployment(app, False)
        if not finished:
            app.status_id = 10
            app = reset_restart_number(app)
            db.session.commit()

    return {
        "id": app.id,
        "status": _APPLICATION_STATUS.get(app.status_id, _DEFAULT__APPLICATION_STATUS),
        "output": output,
        "database": row_to_dict(app),
    }


def check_application_exists(name, namespace, cluster_id):
    return model.Application.query.filter(
        model.Application.namespace == namespace,
        model.Application.name == name,
        model.Application.cluster_id == cluster_id,
    ).first()


def get_clusters_name(cluster_id, info=None):
    if info is None:
        info = {}
    cluster = model.Cluster.query.filter_by(id=cluster_id).first()
    info[str(cluster_id)] = cluster.name
    return info


def get_deployment_info(cluster_name, k8s_yaml):
    deployment_info = None
    service_info = None
    ingress_info = None
    namespace = k8s_yaml.get("namespace")
    deploy_k8s_client = DeployK8sClient(cluster_name)
    if k8s_yaml.get("deployment").get("deployment_name"):
        deployment = deploy_k8s_client.read_namespace_deployment(
            k8s_yaml.get("deployment").get("deployment_name"), namespace
        )
        deployment_info = kubernetesClient.get_deployments_info(deployment)

    if k8s_yaml.get("service").get("service_name"):
        service = deploy_k8s_client.read_namespace_service(k8s_yaml.get("service").get("service_name"), namespace)
        service_info = {}
        if service is not None:
            service_info = json.loads(service.metadata.annotations["field.cattle.io/publicEndpoints"])

    if k8s_yaml.get("ingress") and k8s_yaml.get("ingress").get("ingress_name"):
        ingress = deploy_k8s_client.read_namespace_ingress(k8s_yaml.get("ingress").get("ingress_name"), namespace)
        ingress_info = {}
        if ingress is not None:
            ingress_info = json.loads(ingress.metadata.annotations["field.cattle.io/publicEndpoints"])
    url = ""
    if ingress_info:
        ingress = ingress_info[0]
        url = (
            ingress.get("protocol")
            + "://"
            + ingress.get("hostname")
            + ":"
            + str(ingress.get("port"))
            + ingress.get("path")
        )
    elif service_info:
        service = service_info[0]
        url = "http://" + service.get("addresses")[0] + ":" + str(service.get("port"))

    return deployment_info, url


def get_application_information(application, need_update=True, cluster_info=None):
    if application is None:
        return []
    error_message = None
    if application.status_id in _NEED_UPDATE_APPLICATION_STATUS and need_update:
        try:
            check_application_status(application)
        except Exception as ex:
            error_message = str(ex)
        app = model.Application.query.filter_by(id=application.id).first()
    else:
        app = application

    output = row_to_dict(application)

    output["status"] = _APPLICATION_STATUS.get(app.status_id, _DEFAULT__APPLICATION_STATUS)
    output.pop("k8s_yaml")
    output.pop("harbor_info")
    if app.harbor_info is None or app.k8s_yaml is None:
        return output
    harbor_info = json.loads(app.harbor_info)
    k8s_yaml = json.loads(app.k8s_yaml)
    cluster_id = str(app.cluster_id)
    # single cluster get single cluster name
    if cluster_info is None:
        cluster_info = get_clusters_name(cluster_id)

    url = None
    deployment_info = {
        "name": None,
        "available_pod_number": None,
        "total_pod_number": None,
        "created_time": None,
        "containers": None,
    }
    if k8s_yaml.get("deploy_finish") and app.status_id == 5:
        try:
            deployment_info, url = get_deployment_info(cluster_info[cluster_id], k8s_yaml)
        except MaxRetryError as ex:
            logger.info(f"No Route To Host {cluster_id}!")
            logger.error(ex)
            error_message = str(ex)
        except Exception as ex:
            error_message = str(ex)
    output["deployment"] = deployment_info
    output["public_endpoint"] = url
    output["cluster"] = {}
    output["cluster"]["id"] = app.cluster_id
    output["cluster"]["name"] = cluster_info[cluster_id]
    output["registry"] = {}
    output["registry"]["id"] = app.registry_id
    output["image"] = k8s_yaml.get("image")
    output["project_name"] = harbor_info.get("project")
    output["tag_name"] = harbor_info.get("tag_name")
    output["k8s_status"] = k8s_yaml.get("deploy_finish")
    output["resources"] = k8s_yaml.get("resources")
    output["network"] = k8s_yaml.get("network")
    output["environments"] = k8s_yaml.get("environments")
    output["volumes"] = k8s_yaml.get("volumes")
    if output["volumes"] is not None:
        for i in range(len(output["volumes"])):
            if "sc_name" not in output["volumes"][i]:
                output["volumes"][i]["sc_name"] = "deploy-local-sc"
    if error_message is not None:
        output["error_message"] = error_message
    return output


def generate_multithreads(app):
    cluster_info = {}
    clusters = model.Cluster.query.with_entities(model.Cluster.id, model.Cluster.name).all()
    for cluster in clusters:
        cluster_info[str(cluster.id)] = cluster.name
    services = []
    service_args = {}
    targets = {}
    for application in app:
        application_id = str(application.id)
        services.append(application_id)
        targets[application_id] = get_application_information
        service_args[application_id] = (
            application,
            False,
            cluster_info,
        )
    return services, targets, service_args


def get_applications(args=None):
    output = []
    app = None
    if args is None:
        app = model.Application.query.filter().order_by(model.Application.id.desc()).all()
    elif "application_id" in args:
        app = (
            model.Application.query.filter_by(id=args.get("application_id"))
            .order_by(model.Application.id.desc())
            .first()
        )
    elif "project_id" in args:
        app = (
            model.Application.query.filter_by(project_id=args.get("project_id"))
            .order_by(model.Application.id.desc())
            .all()
        )
    if app is None:
        return output
    elif isinstance(app, list):
        services, targets, service_args = generate_multithreads(app)
        helper = util.ServiceBatchOpHelper(services, targets, service_args)
        helper.run()
        for service in services:
            if helper.errors[service] is None:
                output.append(helper.outputs[service])
        # cluster_info = {}
        # clusters = model.Cluster.query.with_entities(model.Cluster.id, model.Cluster.name).all()
        # for cluster in clusters:
        #     cluster_info[str(cluster.id)] = cluster.name
        # for application in app:
        #     output.append(get_application_information(application, False, cluster_info))
    else:
        output = get_application_information(app)
    return output


def create_application(args):
    cluster = model.Cluster.query.filter_by(id=args.get("cluster_id")).first()
    if check_application_exists(args.get("name"), args.get("namespace"), args.get("cluster_id")) is not None:
        raise apiError.DevOpsError(
            404,
            _ERROR_APPLICATION_EXISTS,
            error=apiError.create_deploy_application_failed(cluster.name, args.get("namespace"), args.get("name")),
        )
    db_project = (
        db.session.query(model.Project)
        .filter(
            model.Project.id == args.get("project_id"),
        )
        .one()
    )
    image = args.get("image")
    db_release = None
    harbor_info: dict = {}
    if "type" not in image or image.get("type") == "harbor":
        db_release = (
            db.session.query(model.Release)
            .filter(
                model.Release.id == args.get("release_id"),
            )
            .one()
        )
        harbor_info = create_default_harbor_data(
            db_project,
            db_release,
            args.get("registry_id"),
            args.get("namespace"),
            args.get("name"),
        )
    k8s_yaml = create_default_k8s_data(db_project, db_release, args)
    # check namespace
    deploy_k8s_client = DeployK8sClient(cluster.name)
    deploy_namespace = DeployNamespace(args.get("namespace"))
    deploy_k8s_client.create_namespace(args.get("namespace"), deploy_namespace.namespace_body())
    now = str(datetime.utcnow())
    new = model.Application(
        name=args.get("name"),
        disabled=False,
        project_id=args.get("project_id"),
        registry_id=args.get("registry_id"),
        cluster_id=args.get("cluster_id"),
        release_id=args.get("release_id"),
        namespace=args.get("namespace"),
        created_at=now,
        updated_at=now,
        status_id=1,
        harbor_info=json.dumps(harbor_info),
        k8s_yaml=json.dumps(k8s_yaml),
        status="Initial Creating",
    )
    db.session.add(new)
    db.session.commit()
    return new.id


def check_update_application_status(app, args):
    status_id = 1
    # Project Change
    if app.cluster_id != args.get("cluster_id"):
        delete_application(app.id)
        status_id = 1

    return status_id


def update_application(application_id, args):
    app = model.Application.query.filter_by(id=application_id).first()
    db_project = (
        db.session.query(model.Project)
        .filter(
            model.Project.id == args.get("project_id"),
        )
        .one()
    )
    image = args.get("image")
    db_release = None
    harbor_info: dict = {}
    if "type" not in image or image.get("type") == "harbor":
        db_release = (
            db.session.query(model.Release)
            .filter(
                model.Release.id == args.get("release_id"),
            )
            .one()
        )
        #  Change Harbor Info
        harbor_info = json.loads(app.harbor_info)
        delete_image_replication_policy(harbor_info.get("policy_id"))

        harbor_info = create_default_harbor_data(
            db_project,
            db_release,
            args.get("registry_id"),
            args.get("namespace"),
            args.get("name"),
        )
    #  Change k8s Info
    # db_k8s_yaml = json.loads(app.k8s_yaml)
    db_k8s_yaml = create_default_k8s_data(db_project, db_release, args)
    # check namespace
    app.status_id = disable_application(args.get("disabled"), app)
    app.harbor_info = json.dumps(harbor_info)
    app.k8s_yaml = json.dumps(db_k8s_yaml)
    app.updated_at = datetime.utcnow()
    db.session.commit()
    return app.id


def patch_application(application_id, args):
    app = model.Application.query.filter_by(id=application_id).first()
    release_id = args.get("release_id", app.release_id)
    db_release, db_project = (
        db.session.query(model.Release, model.Project)
        .join(model.Project)
        .filter(model.Release.id == release_id, model.Project.id == model.Release.project_id)
        .one()
    )
    for key in args.keys():
        if not hasattr(app, key):
            continue
        elif args[key] is not None:
            setattr(app, key, args[key])

    #  Delete Application
    if "disabled" in args:
        app.status_id = disable_application(args.get("disabled"), app)
    else:
        app.status_id = 11

    #  Change K8s Deploy
    if (
        "namespace" in args
        or "image" in args
        or "resources" in args
        or "network" in args
        or "environments" in args
        or "release_id" in args
    ):
        db_k8s_yaml = json.loads(app.k8s_yaml)
        db_k8s_yaml.update(create_default_k8s_data(db_project, db_release, args))
        app.k8s_yaml = json.dumps(db_k8s_yaml)
    #  Change harbor_info Deploy
    if "namespace" in args or "registry_id" in args or "release_id" in args or "name" in args:
        db_harbor_info = json.loads(app.harbor_info)
        delete_image_replication_policy(db_harbor_info.get("policy_id"))
        db_release, db_project = (
            db.session.query(model.Release, model.Project)
            .join(model.Project)
            .filter(
                model.Release.id == release_id,
                model.Project.id == model.Release.project_id,
            )
            .one()
        )
        db_harbor_info.update(
            create_default_harbor_data(
                db_project,
                db_release,
                args.get("registry_id", app.registry_id),
                args.get("namespace", app.namespace),
                args.get("name", app.name),
            )
        )
    app.status = _APPLICATION_STATUS.get(app.status_id, _DEFAULT__APPLICATION_STATUS)
    app.restart_number = 1
    app.updated_at = datetime.utcnow()
    db.session.commit()
    return application_id


def redeploy_application(application_id):
    app = model.Application.query.filter_by(id=application_id).first()
    app.status_id = 11
    app.restart_number = 1
    app.restarted_at = str(datetime.utcnow())
    app.status = _APPLICATION_STATUS.get(1, _DEFAULT__APPLICATION_STATUS)
    db.session.commit()
    return app.id


def delete_application(application_id, delete_db=False):
    app = model.Application.query.filter_by(id=application_id).first()
    if app is None:
        return {}
    harbor_info = json.loads(app.harbor_info)
    delete_image_replication_policy(harbor_info.get("policy_id"))
    delete_k8s_application(app)
    if delete_db is False:
        app.status_id = 9
        app.status = _APPLICATION_STATUS.get(9, _DEFAULT__APPLICATION_STATUS)
        db.session.commit()
    elif delete_db is True:
        db.session.delete(app)
        db.session.commit()
    return app.id


def disable_application(disabled, app):
    #  Delete Application retain namespace
    delete_k8s_application(app)
    if disabled:
        # Stop Application
        status_id = 32
    else:
        # Redeploy K8s
        cluster = model.Cluster.query.filter_by(id=app.cluster_id).first()
        deploy_k8s_client = DeployK8sClient(cluster.name)
        deploy_namespace = DeployNamespace(app.namespace)
        deploy_k8s_client.create_namespace(app.namespace, deploy_namespace.namespace_body())
        status_id = 1
    return status_id


def delete_image_replication_policy(policy_id):
    if policy_id is not None and check_replication_policy(policy_id):
        delete_replication_policy(policy_id)


def delete_k8s_application(app):
    if app.cluster_id is not None and app.namespace is not None:
        cluster = model.Cluster.query.filter_by(id=app.cluster_id).first()
        deploy_k8s_client = DeployK8sClient(cluster.name)
        deploy_object = json.loads(app.k8s_yaml)
        if deploy_object.get("deployment") is not None:
            deploy_k8s_client.delete_namespace_deployment(
                deploy_object.get("deployment").get("deployment_name"), app.namespace
            )

        if deploy_object.get("ingress") is not None:
            deploy_k8s_client.delete_namespace_ingress(deploy_object.get("ingress").get("ingress_name"), app.namespace)

        if deploy_object.get("service") is not None:
            deploy_k8s_client.delete_namespace_service(deploy_object.get("service").get("service_name"), app.namespace)

        if deploy_object.get("registry_secret") is not None:
            deploy_k8s_client.delete_namespace_secret(
                deploy_object.get("registry_secret").get("registry_secret_name"),
                app.namespace,
            )

        if deploy_object.get("secret") is not None:
            deploy_k8s_client.delete_namespace_secret(deploy_object.get("secret").get("secret_name"), app.namespace)

        if deploy_object.get("configmap") is not None:
            deploy_k8s_client.delete_namespace_configmap(
                deploy_object.get("configmap").get("configmap_name"), app.namespace
            )


class Applications(Resource):
    @jwt_required()
    def get(self):
        try:
            parser = reqparse.RequestParser()
            parser.add_argument("project_id", type=str, location="args")
            args = parser.parse_args()
            role_id = get_jwt_identity()["role_id"]
            project_id = args.get("project_id", None)
            if role_id == 5 and project_id is None:
                role.require_admin()
                output = get_applications()
            else:
                output = get_applications(args)
            return util.success({"applications": output})
        except NoResultFound:
            return util.respond(
                404,
                _ERROR_GET_DEPLOY_APPLICATION,
                error=apiError.get_deploy_application_failed(project_id=args.get("project_id")),
            )

    @jwt_required()
    def post(self):
        try:
            parser = reqparse.RequestParser()
            parser.add_argument("name", type=str)
            parser.add_argument("project_id", type=int)
            parser.add_argument("registry_id", type=int)
            parser.add_argument("cluster_id", type=int)
            parser.add_argument("release_id", type=int)
            parser.add_argument("namespace", type=str)
            parser.add_argument("resources", type=dict)
            parser.add_argument("network", type=dict)
            parser.add_argument("image", type=dict)
            parser.add_argument("environments", type=dict, action="append")
            parser.add_argument("volumes", type=dict, action="append")
            parser.add_argument("disabled", type=inputs.boolean)
            args = parser.parse_args()
            output = create_application(args)
            return util.success({"applications": {"id": output}})
        except NoResultFound:
            return util.respond(404, _ERROR_CREATE_DEPLOY_APPLICATION)


class Application(Resource):
    @jwt_required()
    def get(self, application_id):
        try:
            args = {"application_id": application_id}
            output = get_applications(args)
            return util.success({"application": output})
        except NoResultFound:
            return util.respond(
                404,
                _ERROR_GET_DEPLOY_APPLICATION,
                error=apiError.get_deploy_application_failed(project_id=args.get("project_id")),
            )

    @jwt_required()
    def patch(self, application_id):
        try:
            parser = reqparse.RequestParser()
            parser.add_argument("disabled", type=inputs.boolean)
            args = parser.parse_args()
            output = patch_application(application_id, args)
            return util.success({"applications": output})
        except NoResultFound:
            return util.respond(
                404,
                _ERROR_UPDATE_DEPLOY_APPLICATION,
                error=apiError.update_deploy_application_failed(application_id=application_id),
            )

    @jwt_required()
    def delete(self, application_id):
        try:
            output = delete_application(application_id, True)
            return util.success(output)
        except NoResultFound:
            return util.respond(
                404,
                _ERROR_DELETE_DEPLOY_APPLICATION,
                error=apiError.delete_deploy_application_failed(application_id),
            )

    @jwt_required()
    def put(self, application_id):
        try:
            parser = reqparse.RequestParser()
            parser.add_argument("name", type=str)
            parser.add_argument("project_id", type=int)
            parser.add_argument("registry_id", type=int)
            parser.add_argument("cluster_id", type=int)
            parser.add_argument("release_id", type=int)
            parser.add_argument("namespace", type=str)
            parser.add_argument("resources", type=dict)
            parser.add_argument("network", type=dict)
            parser.add_argument("image", type=dict)
            parser.add_argument("environments", type=dict, action="append")
            parser.add_argument("volumes", type=dict, action="append")
            parser.add_argument("disabled", type=inputs.boolean)
            args = parser.parse_args()
            output = update_application(application_id, args)
            return util.success({"applications": {"id": output}})
        except NoResultFound:
            return util.respond(
                404,
                _ERROR_UPDATE_DEPLOY_APPLICATION,
                error=apiError.update_deploy_application_failed(application_id=application_id),
            )


class RedeployApplication(Resource):
    @jwt_required()
    def patch(self, application_id):
        try:
            output = redeploy_application(application_id)
            return util.success({"applications": output})
        except NoResultFound:
            return util.respond(
                404,
                _ERROR_UPDATE_DEPLOY_APPLICATION,
                error=apiError.update_deploy_application_failed(application_id=application_id),
            )


class UpdateApplication(Resource):
    @jwt_required()
    def patch(self, application_id):
        try:
            app = model.Application.query.filter_by(id=application_id).first()
            if app.restart_number > _DEFAULT_RESTART_NUMBER:
                return util.respond(
                    404,
                    _ERROR_RESTART_DEPLOY_APPLICATION,
                    error=apiError.re_deploy_application_failed(str(app.name)),
                )
            output = check_application_status(app)
            return util.success({"applications": output})
        except NoResultFound:
            return util.respond(
                404,
                _ERROR_UPDATE_DEPLOY_APPLICATION,
                error=apiError.update_deploy_application_failed(application_id=application_id),
            )


class ReleaseApplication(Resource):
    @jwt_required()
    def get(self, release_id):
        try:
            release_file = release.ReleaseFile(release_id)
            env = release_file.get_release_env_from_file()
            return util.success({"env": env})
        except NoResultFound:
            return util.respond(404, _ERROR_RELEASE_APPLICATION)


class Cronjob(Resource):
    @staticmethod
    def patch():
        try:
            execute_list = []
            apps = (
                db.session.query(model.Application)
                .filter(model.Application.status_id.in_(_NEED_UPDATE_APPLICATION_STATUS))
                .all()
            )
            for app in apps:
                if app.restart_number is None:
                    restart_number = 0
                else:
                    restart_number = app.restart_number
                if restart_number < _DEFAULT_RESTART_NUMBER:
                    temp = check_application_status(app)
                    execute_list.append(temp["id"])
            return util.success({"applications": execute_list})
        except NoResultFound:
            return util.respond(
                404,
                _ERROR_UPDATE_DEPLOY_APPLICATION,
                error=apiError.update_deploy_application_failed(),
            )


# 20230118 新增下列程式，以解決因遠端機器不存在造成TIMEOUT使得無法取得APPLICATION的資料列表
def get_deployments(args=None) -> dict:
    output: dict = {}
    app: model.Application = None
    if "application_id" in args:
        app = (
            model.Application.query.filter_by(id=args.get("application_id"))
            .order_by(model.Application.id.desc())
            .first()
        )
    if app is None:
        return output
    k8s_yaml: dict = json.loads(app.k8s_yaml)
    cluster_id: str = str(app.cluster_id)
    cluster_info: dict = get_clusters_name(cluster_id)
    url = None
    deployment_info = {
        "name": None,
        "available_pod_number": None,
        "total_pod_number": None,
        "created_time": None,
        "containers": None,
    }
    if k8s_yaml.get("deploy_finish") and app.status_id == 5:
        try:
            deployment_info, url = get_deployment_info(cluster_info[cluster_id], k8s_yaml)
        except MaxRetryError as ex:
            logger.info(f"No Route To Host {cluster_id}!")
            logger.error(ex)
    output["deployment"] = deployment_info
    output["public_endpoint"] = url
    return output


class Deployment(Resource):
    @jwt_required()
    def get(self, application_id):
        args = {"application_id": application_id}
        try:
            output = get_deployments(args)
            return util.success(output)
        except NoResultFound:
            return util.respond(
                404,
                _ERROR_GET_DEPLOYMENT,
                error=apiError.get_deployment_failed(application_id=args.get("application")),
            )


# 20230118 新增上列程式，以解決因遠端機器不存在造成TIMEOUT使得無法取得APPLICATION的資料列表


# 20230118 為取得 storage class 資訊而新增下列一段程式
def get_storage_class_info(cluster_name):
    deploy_k8s_client = DeployK8sClient(cluster_name)
    storages_info = []
    for storage in deploy_k8s_client.list_storage_class().items:
        if storage.metadata.name == "anchore-sc" or storage.metadata.name == "iiidevops-nfs-storage":
            continue
        storages_info.append(kubernetesClient.get_storage_class_info(storage))
    return storages_info


def get_storage_classes_from_db(cluster_id: int) -> list[model.StorageClass]:
    return model.StorageClass.query.filter_by(cluster_id=cluster_id).order_by(model.StorageClass.id.desc()).all()


def get_storage_class_json(storage: model.StorageClass) -> dict:
    pods: int = 0
    app_list: list = (
        model.Application.query.filter_by(storage_class_id=storage.id).order_by(model.Application.order).all()
    )
    for app in app_list:
        k8s_yaml = json.loads(app.k8s_yaml)
        cluster_id = str(app.cluster_id)
        # single cluster get single cluster name
        cluster_info = get_clusters_name(cluster_id)
        url = None
        deployment_info = {
            "name": None,
            "available_pod_number": None,
            "total_pod_number": None,
            "created_time": None,
            "containers": None,
        }
        if k8s_yaml.get("deploy_finish") and app.status_id == 5:
            try:
                deployment_info, url = get_deployment_info(cluster_info[cluster_id], k8s_yaml)
            except MaxRetryError as ex:
                logger.info(f"No Route To Host {cluster_id}!")
                logger.error(ex)
        if deployment_info["total_pod_number"] is not None:
            pods += deployment_info["total_pod_number"]
    status = "Enabled"
    if storage.disabled is None:
        status = "Not Exist"
    elif storage.disabled:
        status = "Disabled"
    return {
        "id": storage.id,
        "name": storage.name,
        "Pods used": pods,
        "status": status,
        "disabled": storage.disabled,
    }


@record_activity(ActionType.CREATE_SC)
def create_storage_class(cluster_id: int, storage_name: str) -> model.StorageClass:
    sc = model.StorageClass(cluster_id=cluster_id, name=storage_name, disabled=False)
    db.session.add(sc)
    db.session.commit()
    return sc


def sync_storage_classes(args=None) -> list:
    output: list = []
    db_sc_list: list = []
    storage_list: list = []
    cluster_id: int = args.get("cluster_id", None)
    if cluster_id is not None:
        db_sc_list = get_storage_classes_from_db(cluster_id)
    cluster_info: dict = get_clusters_name(cluster_id)
    try:
        storage_list = get_storage_class_info(cluster_info[str(cluster_id)])
    except MaxRetryError as ex:
        logger.info(f"No Route To Host {cluster_id}!")
        logger.error(ex)
    storage_name_list: list = []
    for storage in storage_list:
        storage_name_list.append(storage["name"])
    db_sc_name_list: list = []
    is_commit: bool = False
    for db_sc in db_sc_list:
        db_sc_name_list.append(db_sc.name)
        index = storage_name_list.index(db_sc.name)
        if index < 0:
            db_sc.disabled = None
            is_commit = True
        else:
            del storage_name_list[index]
        output.append(get_storage_class_json(db_sc))
    for storage_name in storage_name_list:
        sc = create_storage_class(cluster_id=cluster_id, storage_name=storage_name)
        output.append(get_storage_class_json(sc))
    if is_commit:
        db.session.commit()
    return output


def get_storage_classes_info(args=None) -> list:
    output: list = []
    db_sc_list: list = []
    cluster_id: int = args.get("cluster_id", None)
    if cluster_id is not None:
        db_sc_list = get_storage_classes_from_db(cluster_id)
    for db_sc in db_sc_list:
        output.append(get_storage_class_json(db_sc))
    return output


class StorageClass(Resource):
    @jwt_required()
    def get(self, cluster_id):
        args = {"cluster_id": cluster_id}
        try:
            output = get_storage_classes_info(args)
            return util.success(output)
        except NoResultFound:
            return util.respond(
                404,
                _ERROR_GET_STORAGE_CLASS,
                error=apiError.get_storage_class_failed(cluster_id=args.get("cluster_id")),
            )

    @jwt_required()
    def post(self, cluster_id):
        args = {"cluster_id": cluster_id}
        try:
            output = sync_storage_classes(args)
            return util.success(output)
        except NoResultFound:
            return util.respond(
                404,
                _ERROR_CREATE_STORAGE_CLASS,
                error=apiError.create_storage_class_failed(cluster_id=args.get("cluster_id")),
            )


# 20230118 為取得 storage class 資訊而新增上列一段程式


# 20230201 為變更 storage class disabled 而新增下列一段程式
def patch_storage_class(storage_class_id, args):
    sc = model.StorageClass.query.filter_by(id=storage_class_id).first()
    for key in args.keys():
        if not hasattr(sc, key):
            continue
        elif args[key] is not None:
            setattr(sc, key, args[key])
    db.session.commit()
    return storage_class_id


class UpdateStorageClass(Resource):
    @jwt_required()
    def patch(self, storage_class_id):
        try:
            parser = reqparse.RequestParser()
            parser.add_argument("disabled", type=inputs.boolean)
            args = parser.parse_args()
            output = patch_storage_class(storage_class_id, args)
            return util.success({"storage_class": output})
        except NoResultFound:
            return util.respond(
                404,
                _ERROR_DISABLED_STORAGE_CLASS,
                error=apiError.change_storage_class_disabled_failed(storage_class_id=storage_class_id),
            )


# 20230201 為變更 storage class disabled 而新增上列一段程式


# 20230202 為取得 storage class 所擁有的 PVC 而新增下列一段程式
def get_cluster_name_by_storage_class_id(storage_class_id: int) -> str:
    sc = model.StorageClass.query.filter_by(id=storage_class_id).first()
    cluster_name = ""
    if sc is not None:
        cluster = model.Cluster.query.filter_by(id=sc.cluster_id).first()
        if cluster is not None:
            cluster_name = cluster.name
    return cluster_name


def get_persistent_volume_claim_info(cluster_name: str, namespace: str, pvc_list: list):
    deploy_k8s_client = DeployK8sClient(cluster_name)
    for pvc in deploy_k8s_client.list_persistent_volume_claim(namespace).items:
        pvc_json = kubernetesClient.get_persistent_volume_claim_info(pvc)
        # pvc_json["volume_path"] = kubernetesClient.get_persistent_volume_info(
        #     deploy_k8s_client.read_persistent_volume(pvc_json["volume"])
        # )
        pvc_list.append(pvc_json)
    # return pvc_info


def get_persistent_volume_claim_json(storage_class_id: int, cluster_name: str) -> list:
    pvc_list: list = []
    if cluster_name != "":
        app_list: list = (
            model.Application.query.filter_by(storage_class_id=storage_class_id).order_by(model.Application.order).all()
        )
        namespace_list: list = []
        for app in app_list:
            if app.namespace in namespace_list:
                continue
            namespace_list.append(app.namespace)
        for namespace in namespace_list:
            get_persistent_volume_claim_info(cluster_name, namespace, pvc_list)
            # pvc_list.append()
    return pvc_list


class PersistentVolumeClaim(Resource):
    @jwt_required()
    def get(self, storage_class_id):
        try:
            cluster_name = get_cluster_name_by_storage_class_id(storage_class_id)
            output = get_persistent_volume_claim_json(storage_class_id, cluster_name)
            return util.success({"pvc_list": output})
        except NoResultFound:
            return util.respond(
                404,
                _ERROR_GET_PERSISTENT_VOLUME_CLAIM,
                error=apiError.get_persistent_volume_claim_failed(storage_class_id=storage_class_id),
            )


# 20230202 為取得 storage class 所擁有的 PVC 而新增上列一段程式


# 20230215 為新增 application_header table 而新增下列一段程式
def update_app_header(app_header_id, args):
    app_header = model.ApplicationHeader.query.filter_by(id=app_header_id).first()
    app_ids = json.loads(app_header.applications_id)
    cur_app_ids = []
    for key in args.keys():
        if not hasattr(app_header, key):
            continue
        elif args[key] is not None:
            setattr(app_header, key, args[key])
    for app_args in args.get("applications"):
        app_args["name"] = args.get("name")
        app_args["cluster_id"] = args.get("cluster_id")
        app_args["registry"] = args.get("registry_id")
        app_args["namespace"] = args.get("namespace")
        if "id" in app_args:
            app_id = update_application(app_args["id"], app_args)
        else:
            app_id = create_application(app_args)
        if app_id not in cur_app_ids:
            cur_app_ids.append(app_id)
    #  Delete Application
    for app_id in app_ids:
        if app_id not in cur_app_ids:
            delete_app_header(app_id, True)
    app_header.applications_id = "[" + ",".join(str(i) for i in cur_app_ids) + "]"
    db.session.commit()
    return app_header.id


def delete_app_header(app_header_id, delete_db=False, application_id=None):
    app_header = model.ApplicationHeader.query.filter_by(id=app_header_id).first()
    if app_header is None:
        return {}
    elif delete_db is True:
        app_ids: list = json.loads(app_header.applications_id)
        if application_id is None:
            for app_id in app_ids:
                delete_application(app_id, delete_db)
            db.session.delete(app_header)
            db.session.commit()
            return {"app_hrader_id": app_header.id, "applications_id": app_ids}
        else:
            if application_id in app_ids:
                id_index = app_ids.index(application_id)
                delete_application(application_id, delete_db)
                del app_ids[id_index]
                app_header.applications_id = json.dumps(app_ids)
                # db.session.delete(app_header)
                db.session.commit()
                return {"app_hrader_id": app_header.id, "application_id": application_id}
            else:
                return {}


def patch_app_header(app_header_id, args) -> int:
    app_header = model.ApplicationHeader.query.filter_by(id=app_header_id).first()
    if "disabled" in args:
        app_header.disabled = args.get("disabled")
        app_header.updated_at = datetime.utcnow()
        db.session.commit()
    app_id_list = json.loads(app_header.applications_id)
    for app_id in app_id_list:
        patch_application(app_id, args)
    return app_header_id


def get_app_header_information(app_header, detail: bool = False):
    if app_header is None:
        return []

    output = row_to_dict(app_header)
    output["total_pods"] = 0
    output["available_pods"] = 0
    output["cluster"] = {}
    output["cluster"]["id"] = app_header.cluster_id
    output["cluster"]["name"] = get_clusters_name(app_header.cluster_id)[str(app_header.cluster_id)]
    output["registry"] = {}
    output["registry"]["id"] = app_header.registry_id
    if detail:
        applications = []
        for app_id in output["applications_id"]:
            app_json = get_application_information(model.Application.query.filter_by(id=app_id).first())
            applications.append(app_json)
            if "deployment" in app_json:
                deployment = app_json["deployment"]
                if "total_pod_number" in deployment:
                    if deployment.get("total_pod_number", 0) is not None:
                        output["total_pods"] += deployment.get("total_pod_number", 0)
                if "available_pod_number" in deployment:
                    if deployment.get("available_pod_number", 0) is not None:
                        output["available_pods"] += deployment.get("available_pod_number", 0)
        output["applications"] = applications
    return output


def get_application_headers(args=None):
    output = []
    app_header = None
    if args is None:
        app_header = model.ApplicationHeader.query.filter().order_by(model.ApplicationHeader.id.desc()).all()
    elif "app_header_id" in args:
        app_header = (
            model.ApplicationHeader.query.filter_by(id=args.get("app_header_id"))
            .order_by(model.ApplicationHeader.id.desc())
            .first()
        )
    if app_header is None:
        return output
    elif isinstance(app_header, list):
        for app in app_header:
            output.append(get_app_header_information(app))
    else:
        output = get_app_header_information(app_header, True)
    return output


def check_application_header_exists(name, namespace, cluster_id, registry_id) -> model.ApplicationHeader:
    return model.ApplicationHeader.query.filter_by(
        name=name, namespace=namespace, cluster_id=cluster_id, registry_id=registry_id
    ).first()


def create_application_header(args) -> int:
    if not args.get("remote"):
        args["cluster_id"] = 0
        args["registry_id"] = 0
    cluster = model.Cluster.query.filter_by(id=args.get("cluster_id")).first()
    registry = model.Cluster.query.filter_by(id=args.get("registry_id")).first()
    application_list = args.get("applications")
    if len(application_list) <= 0:
        raise apiError.DevOpsError(
            404,
            _ERROR_APPLICATION_HEADER_EXISTS,
            error=apiError.create_application_header_failed(
                cluster.name, registry.name, args.get("namespace"), args.get("name")
            ),
        )
    if not args.get("remote"):
        args["namespace"] = None
        project_name = model.Project.query.filter_by(id=application_list[0]["project_id"]).first().name
        for i in range(100):
            temp_namespace = project_name + "-dpy" + ("00" + str(i))[-2:]
            if check_application_header_exists(args.get("name"), temp_namespace, 0, 0) is None:
                args["namespace"] = temp_namespace
                break
        if args.get("namespace") is None:
            raise apiError.DevOpsError(
                404,
                _ERROR_APPLICATION_HEADER_EXISTS,
                error=apiError.create_application_header_failed(
                    cluster.name, registry.name, args.get("namespace"), args.get("name")
                ),
            )
    else:
        if (
            check_application_header_exists(
                args.get("name"), args.get("namespace"), args.get("cluster_id"), args.get("registry_id")
            )
            is not None
        ):
            raise apiError.DevOpsError(
                404,
                _ERROR_APPLICATION_HEADER_EXISTS,
                error=apiError.create_application_header_failed(cluster.name, args.get("namespace"), args.get("name")),
            )
    applications_id = []
    for proj in application_list:
        app_args = reqparse.Namespace(**proj)
        app_args["name"] = args.get("name")
        app_args["cluster_id"] = args.get("cluster_id")
        app_args["registry_id"] = args.get("registry_id")
        app_args["namespace"] = args.get("namespace")
        applications_id.append(create_application(app_args))
    now = str(datetime.utcnow())
    app_header = model.ApplicationHeader(
        name=args.get("name"),
        remote=args.get("remote"),
        registry_id=args.get("registry_id"),
        cluster_id=args.get("cluster_id"),
        namespace=args.get("namespace"),
        applications_id="[" + ",".join(str(i) for i in applications_id) + "]",
        disabled=False,
        created_at=now,
        updated_at=now,
    )
    db.session.add(app_header)
    db.session.commit()
    return app_header.id


class ApplicationHeaders(Resource):
    @jwt_required()
    def get(self):
        try:
            return util.success({"app_headers": get_application_headers()})
        except NoResultFound:
            return util.respond(
                404,
                _ERROR_GET_APPLICATION_HEADER,
                error=apiError.get_application_header_failed(app_header_id=None),
            )

    @jwt_required()
    def post(self):
        try:
            parser = reqparse.RequestParser()
            parser.add_argument("name", type=str)
            parser.add_argument("remote", type=inputs.boolean)
            parser.add_argument("registry_id", type=int)
            parser.add_argument("cluster_id", type=int)
            parser.add_argument("namespace", type=str)
            parser.add_argument("applications", type=dict, action="append")
            parser.add_argument("disabled", type=inputs.boolean)
            args = parser.parse_args()
            # output = create_application_header(args)
            return util.success({"application_headers": {"id": create_application_header(args)}})
        except NoResultFound:
            return util.respond(404, _ERROR_CREATE_APPLICATION_HEADER)


class ApplicationHeader(Resource):
    @jwt_required()
    def get(self, app_header_id):
        try:
            args = {"app_header_id": app_header_id}
            output = get_application_headers(args)
            return util.success({"app_header": output})
        except NoResultFound:
            return util.respond(
                404,
                _ERROR_GET_APPLICATION_HEADER,
                error=apiError.get_application_header_failed(app_header_id=args.get("app_header_id")),
            )

    @jwt_required()
    def patch(self, app_header_id):
        try:
            parser = reqparse.RequestParser()
            parser.add_argument("disabled", type=inputs.boolean)
            args = parser.parse_args()
            return util.success({"app_headers": patch_app_header(app_header_id, args)})
        except NoResultFound:
            return util.respond(
                404,
                _ERROR_UPDATE_APPLICATION_HEADER,
                error=apiError.update_deploy_application_failed(app_header_id=app_header_id),
            )

    @jwt_required()
    def delete(self, app_header_id):
        try:
            return util.success(delete_app_header(app_header_id, True))
        except NoResultFound:
            return util.respond(
                404,
                _ERROR_DELETE_APPLICATION_HEADER,
                error=apiError.delete_application_header_failed(app_header_id),
            )

    @jwt_required()
    def put(self, app_header_id):
        try:
            parser = reqparse.RequestParser()
            parser.add_argument("name", type=str)
            parser.add_argument("remote", type=inputs.boolean)
            parser.add_argument("registry_id", type=int)
            parser.add_argument("cluster_id", type=int)
            parser.add_argument("namespace", type=str)
            parser.add_argument("applications", type=dict, action="append")
            parser.add_argument("disabled", type=inputs.boolean)
            args = parser.parse_args()
            output = update_app_header(app_header_id, args)
            return util.success({"app_header": {"id": output}})
        except NoResultFound:
            return util.respond(
                404,
                _ERROR_UPDATE_APPLICATION_HEADER,
                error=apiError.update_application_header_failed(app_header_id=app_header_id),
            )


class DeleteApplicationHeader(Resource):
    @jwt_required()
    def delete(self, app_header_id, application_id):
        try:
            return util.success(delete_app_header(app_header_id, True, application_id))
        except NoResultFound:
            return util.respond(
                404,
                _ERROR_DELETE_APPLICATION_HEADER,
                error=apiError.delete_application_header_failed(
                    app_header_id=app_header_id, application_id=application_id
                ),
            )


# 20230215 為新增 application_header table 而新增上列一段程式
'''
