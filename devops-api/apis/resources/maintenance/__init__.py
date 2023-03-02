"""
from model import db, ProjectPluginRelation, Project
from resources import role
import util
import resources.apiError as apiError
from resources.apiError import DevOpsError
from flask_restful import Resource, reqparse
from flask_jwt_extended import jwt_required
from resources.gitlab import gitlab
import util


def get_system_parameter():
    return util.read_json_file("apis/resources/maintenance/system_parameter.json")


def check_name_duplicate(name, type):
    system_parameter = get_system_parameter()
    if name in system_parameter[type]:
        raise apiError.DevOpsError(404, "Name must not be duplicate", apiError.argument_error("name"))


def add_system_tag(system_list, type):
    system_parameter = get_system_parameter()
    for system in system_list:
        system["system"] = system["name"] in system_parameter[type]


def update_db_rancher_projectid_and_pipelineid(force=None):
    # get all project
    rows = (
        db.session.query(ProjectPluginRelation, Project)
        .join(Project, ProjectPluginRelation.project_id == Project.id)
        .all()
    )
    rancher.rc_get_project_id()
    now_pipe_data = rancher.rc_get_project_pipeline()
    if force == "true":
        for now_pipe in now_pipe_data:
            rancher.rc_disable_project_pipeline(now_pipe["projectId"], now_pipe["id"])
        for row in rows:
            pj_info = gitlab.gl_get_project(row.ProjectPluginRelation.git_repository_id)
            rancher_pipeline_id = rancher.rc_enable_project_pipeline(pj_info["http_url_to_repo"])
            ppro = ProjectPluginRelation.query.filter_by(project_id=row.ProjectPluginRelation.project_id).first()
            ppro.ci_project_id = rancher.project_id
            ppro.ci_pipeline_id = rancher_pipeline_id
            db.session.commit()
    else:
        for now_pipe in now_pipe_data:
            for row in rows:
                if now_pipe["repositoryUrl"].split("//")[1] == row.Project.http_url.split("//")[1] and (
                    now_pipe["projectId"] != row.ProjectPluginRelation.ci_project_id
                    or now_pipe["id"] != row.ProjectPluginRelation.ci_pipeline_id
                ):
                    ppro = ProjectPluginRelation.query.filter_by(
                        project_id=row.ProjectPluginRelation.project_id
                    ).first()
                    ppro.ci_project_id = now_pipe["projectId"]
                    ppro.ci_pipeline_id = now_pipe["id"]
                    db.session.commit()


def update_pj_httpurl():
    rows = db.session.query(Project, ProjectPluginRelation).filter(ProjectPluginRelation.project_id == Project.id).all()
    gl_pjs = gitlab.gl_get_all_project()
    for row in rows:
        for gl_pj in gl_pjs:
            if row.ProjectPluginRelation.git_repository_id == gl_pj.id:
                if row.Project.http_url != gl_pj.http_url_to_repo:
                    row.Project.http_url = gl_pj.http_url_to_repo
                    db.session.commit()
                if row.Project.ssh_url != gl_pj.ssh_url_to_repo:
                    row.Project.ssh_url = gl_pj.ssh_url_to_repo
                    db.session.commit()
                break


class UpdateDbRcProjectPipelineId(Resource):
    @jwt_required()
    def get(self):
        role.require_admin()
        parser = reqparse.RequestParser()
        parser.add_argument("force", type=str, location="args")
        args = parser.parse_args()
        update_db_rancher_projectid_and_pipelineid(args["force"])
        return util.success()


class SecretesIntoRcAll(Resource):
    @jwt_required()
    def get(self):
        secret_list = rancher.rc_get_secrets_all_list()
        registry_list = rancher.rc_get_registry_into_rc_all()
        i = 0
        while i < len(secret_list):
            for registry in registry_list:
                if secret_list[i]["name"] == registry["name"]:
                    del secret_list[i]
                    break
            i += 1

        add_system_tag(secret_list, "secret")
        return util.success(secret_list)

    @jwt_required()
    def post(self):
        parser = reqparse.RequestParser()
        parser.add_argument("name", type=str, required=True)
        parser.add_argument("type", type=str, required=True)
        parser.add_argument("data", type=dict, required=True)
        args = parser.parse_args()

        # check_name_duplicate(args["name"], "secret")

        rancher.rc_add_secrets_into_rc_all(args)
        return util.success()

    @jwt_required()
    def put(self, secret_name):
        parser = reqparse.RequestParser()
        parser.add_argument("type", type=str, required=True)
        parser.add_argument("data", type=dict, required=True)
        args = parser.parse_args()
        rancher.rc_put_secrets_into_rc_all(secret_name, args)
        return util.success()

    @jwt_required()
    def delete(self, secret_name):
        return util.success(rancher.rc_delete_secrets_into_rc_all(secret_name))


class RegistryIntoRcAll(Resource):
    @jwt_required()
    def get(self):
        registry_list = rancher.rc_get_registry_into_rc_all()
        add_system_tag(registry_list, "registry")
        return util.success(registry_list)

    @jwt_required()
    def post(self):
        parser = reqparse.RequestParser()
        parser.add_argument("name")
        parser.add_argument("url")
        parser.add_argument("username")
        parser.add_argument("password")
        args = parser.parse_args()

        # check_name_duplicate(args["name"], "registry")
        rancher.rc_add_registry_into_rc_all(args)
        return util.success()

    @jwt_required()
    def delete(self, registry_name):
        return util.success(rancher.rc_delete_registry_into_rc_all(registry_name))


class UpdatePjHttpUrl(Resource):
    @jwt_required()
    def put(self):
        role.require_admin()
        update_pj_httpurl()
        return util.success()
"""
