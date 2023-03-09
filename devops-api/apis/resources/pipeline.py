import base64
import json
from sqlalchemy.sql.operators import exists

import werkzeug
import yaml
from flask_jwt_extended import jwt_required
from flask_restful import Resource, reqparse
from flask import send_file

import resources.apiError as apiError
import util as util
import time
import websocket
from flask_socketio import emit, disconnect, Namespace
from model import db   #  remove ProjectPluginRelation ,PipelineLogsCache, Project
from nexus import nx_get_project_plugin_relation
from resources import role
from .gitlab import GitLab, commit_id_to_url
from typing import Union, Any

# from .rancher import rancher
from os import listdir, makedirs
from shutil import rmtree

gitlab = GitLab()


def pipeline_exec_action(git_repository_id: int, args: dict[str, Union[int, str]]) -> None:
    """
    :param args: must provide: action[rerun, stop] & pipelines_exec_run(job_id)
    """
    action, job_id = args["action"], args["pipelines_exec_run"]
    if action == "rerun":
        gitlab.gl_rerun_pipeline_job(git_repository_id, job_id)
    elif action == "stop":
        gitlab.gl_stop_pipeline_job(git_repository_id, job_id)


def pipeline_exec_list(git_repository_id: int, limit: int = 10, start: int = 0) -> dict[str, Any]:
    """ The list sort in descending order
    :param limit: how many data per page
    :param start: start from 
    """
    pipelines_info, pagination = gitlab.gl_list_pipelines(git_repository_id, limit, start, with_pagination=True)
    ret = []
    for pipeline_info in pipelines_info:
        sha = pipeline_info["sha"]
        gitlab.get_pipeline_jobs_status(git_repository_id, pipeline_info["id"])
        pipeline_info["commit_id"] = sha[:7]
        pipeline_info["commit_url"] = f'{pipeline_info["web_url"].split("/-/")[0]}/-/commit/{sha}'
        pipeline_info["execution_state"] = pipeline_info["status"].capitalize()
        pipeline_info.update(gitlab.get_pipeline_jobs_status(git_repository_id, pipeline_info["id"], with_commit_msg=True))
        ret.append(pipeline_info)
    return {
        "pagination": pagination,
        "pipe_execs": ret
    }


def get_pipeline_job_status(repo_id: int, pipeline_id: int) -> list[dict[str, Any]]:
    jobs = gitlab.gl_pipeline_jobs(repo_id, pipeline_id)
    ret = [{
        "stage_id": job["id"],
        "name": job["name"],
        "state": job["status"].capitalize(),
        
    } for job in jobs]
    return sorted(ret, key=lambda r: r['stage_id'])


def get_pipe_log_websocket(data):
    repo_id, job_id = data["repository_id"], data["stage_id"]
    ws_start_time = time.time()
    success_end_word = "Job succeeded"
    failure_end_word = "ERROR: Job failed"
    i, last_index, first_time = 0, 0, True
    while True:
        ret = gitlab.gl_get_pipeline_console(repo_id, job_id)
        ws_end_time = time.time() - ws_start_time

        if success_end_word in ret or failure_end_word in ret:
            if first_time:
                first_time = False
            else:
                ret = ""
        
        if ret == "" or ws_end_time >= 600 or i >= 100:
            emit(
                "pipeline_log",
                {
                    "data": "",
                    "repository_id": repo_id,
                    "repo_id": job_id
                }
            )
            break
        
        # Calculate last_index, next time emit from last_index.
        ret_list = ret.split("/n")
        ret = "/n".join(ret_list[last_index:])
        last_index = len(ret_list)
        emit(
            "pipeline_log",
            {
                "data": ret,
                "repository_id": repo_id,
                "repo_id": job_id
            }
        )   
        i += 1
    
    # self.token = self.__generate_token()
    # headersandtoken = "Authorization: Bearer {0}".format(self.token)
    # self.rc_get_project_id()
    # url = ("wss://{0}/{1}/project/{2}/pipelineExecutions/" "{3}-{4}/log?stage={5}&step={6}").format(
    #     config.get("RANCHER_IP_PORT"),
    #     config.get("RANCHER_API_VERSION"),
    #     self.project_id,
    #     data["ci_pipeline_id"],
    #     data["pipelines_exec_run"],
    #     data["stage_index"],
    #     data["step_index"],
    # )
    # result = None
    # try:
    #     ws_start_time = time.time()
    #     gitlab.gl_get_pipeline_console(repo_id, pipeline_id)
    #     # ws = websocket.create_connection(url, header=[headersandtoken], sslopt={"cert_reqs": ssl.CERT_NONE})
    #     i = 0
    #     while True:
            
    #         emit(
    #             "pipeline_log",
    #             {
    #                 "data": result,
    #                 "ci_pipeline_id": data["ci_pipeline_id"],
    #                 "pipelines_exec_run": data["pipelines_exec_run"],
    #                 "stage_index": data["stage_index"],
    #                 "step_index": data["step_index"],
    #             },
    #         )
    #         # print(f"result: {result}")
    #         ws_end_time = time.time() - ws_start_time
    #         if result == "" or ws_end_time >= 600 or i >= 100:
    #             emit(
    #                 "pipeline_log",
    #                 {
    #                     "data": "",
    #                     "ci_pipeline_id": data["ci_pipeline_id"],
    #                     "pipelines_exec_run": data["pipelines_exec_run"],
    #                     "stage_index": data["stage_index"],
    #                     "step_index": data["step_index"],
    #                 },
    #             )
    #             ws.close()
    #             print(f"result: {result}, ws_end_time: {ws_end_time}, i: {i}")
    #             break
    #         else:
    #             i += 1
    # except:
    #     if ws is not None:
    #         ws.close()
    #     disconnect()

# def __rancher_pagination(rancher_output):
#     def __url_get_marker(url):
#         key_name = "marker"
#         for param in url.split("?", 1)[1].split("&"):
#             if key_name in param:
#                 return __marker_get_id(param.split("=")[1])

#     def __marker_get_id(marker):
#         return int(marker.split("-")[3])

#     pagination = {
#         "total": rancher_output["pagination"]["total"],
#         "limit": rancher_output["pagination"]["limit"],
#         "start": 0,
#         "first": 0,
#         "next": 0,
#         "last": 0,
#     }
#     if "marker" in rancher_output["pagination"]:
#         pagination["start"] = __marker_get_id(rancher_output["pagination"]["marker"])
#     if "first" in rancher_output["pagination"]:
#         pagination["first"] = __url_get_marker(rancher_output["pagination"]["first"])
#     if "next" in rancher_output["pagination"]:
#         pagination["next"] = __url_get_marker(rancher_output["pagination"]["next"])
#     if "last" in rancher_output["pagination"]:
#         pagination["last"] = __url_get_marker(rancher_output["pagination"]["last"])
#     return pagination


# def pipeline_action(repository_id, args):
#     relation = nx_get_project_plugin_relation(repo_id=repository_id)
#     rancher.rc_run_pipeline(relation.ci_project_id, relation.ci_pipeline_id, args["branch"])

"""
def pipeline_exec_list(repository_id, args):
    out = {}
    output_array = []
    relation = nx_get_project_plugin_relation(repo_id=repository_id)
    pipeline_outputs = rancher.rc_get_pipeline_executions(
        relation.ci_project_id,
        relation.ci_pipeline_id,
        limit=args["limit"],
        page_start=args["start"],
    )
    pagination = __rancher_pagination(pipeline_outputs)
    out["pagination"] = pagination
    project_id = relation.project_id
    for pipeline_output in pipeline_outputs["data"]:
        output_dict = {
            "id": pipeline_output["run"],
            "last_test_time": pipeline_output["created"],
        }
        if "message" in pipeline_output:
            output_dict["commit_message"] = pipeline_output["message"]
        else:
            output_dict["commit_message"] = None
        output_dict["commit_branch"] = pipeline_output["branch"]
        output_dict["commit_id"] = pipeline_output["commit"][0:7]
        output_dict["commit_url"] = commit_id_to_url(relation.project_id, pipeline_output["commit"])
        output_dict["execution_state"] = pipeline_output["executionState"]
        output_dict["transitioning_message"] = pipeline_output["transitioningMessage"]
        stage_status = []
        for stage in pipeline_output["stages"]:
            if "state" in stage:
                stage_status.append(stage["state"])
        success_time = stage_status[1:].count("Success")
        output_dict["status"] = {
            "total": len(pipeline_output["stages"]) - 1,
            "success": success_time,
        }
        output_array.append(output_dict)
    out["pipe_execs"] = output_array
    if out["pipe_execs"] != []:
        rancher.rc_put_yaml_run(project_id, out["pipe_execs"][0]["id"])
    return out





def pipeline_exec_logs(args):
    relation = nx_get_project_plugin_relation(repo_id=args["repository_id"])

    # search PipelineLogsCache table log
    log_cache = PipelineLogsCache.query.filter(
        PipelineLogsCache.project_id == relation.project_id,
        PipelineLogsCache.ci_pipeline_id == relation.ci_pipeline_id,
        PipelineLogsCache.run == args["pipelines_exec_run"],
    ).first()
    if log_cache is None:
        output_array, execution_state = rancher.rc_get_pipeline_executions_logs(
            relation.ci_project_id, relation.ci_pipeline_id, args["pipelines_exec_run"]
        )

        # if execution status is Failed, Success, Aborted, log will insert into ipelineLogsCache table
        if execution_state in ["Failed", "Success", "Aborted"]:
            log = PipelineLogsCache(
                project_id=relation.project_id,
                ci_pipeline_id=relation.ci_pipeline_id,
                run=args["pipelines_exec_run"],
                logs=output_array,
            )
            db.session.add(log)
            db.session.commit()
        return util.success(output_array)
    else:
        return util.success(log_cache.logs)


def pipeline_exec_action(git_repository_id, args):
    relation = nx_get_project_plugin_relation(repo_id=git_repository_id)

    rancher.rc_get_pipeline_executions_action(
        relation.ci_project_id,
        relation.ci_pipeline_id,
        args["pipelines_exec_run"],
        args["action"],
    )
    return util.success()


def stop_and_delete_pipeline(repository_id, run, branch=None):
    relation = nx_get_project_plugin_relation(repo_id=repository_id)
    i = 0
    get_run_number = 0
    get_branch = ""
    while True:
        if branch:
            pipeline_outputs = rancher.rc_get_pipeline_executions(
                relation.ci_project_id, relation.ci_pipeline_id, limit=1, branch=branch
            )
        else:
            pipeline_outputs = rancher.rc_get_pipeline_executions(
                relation.ci_project_id, relation.ci_pipeline_id, limit=1
            )

        if (len(pipeline_outputs["data"]) > 0 and pipeline_outputs["data"][0]["run"] >= run) or i > 50:
            get_run_number = pipeline_outputs["data"][0]["run"]
            get_branch = pipeline_outputs["data"][0]["branch"]
            break
        else:
            i += 1
    if get_run_number >= run:
        print(f"get_run_number: {get_run_number}, branch: {get_branch}")
        rancher.rc_delete_pipeline_executions_run(relation.ci_project_id, relation.ci_pipeline_id, get_run_number)


def get_pipeline_next_run(repository_id):
    relation = nx_get_project_plugin_relation(repo_id=repository_id)
    info_json = rancher.rc_get_pipeline_info(relation.ci_project_id, relation.ci_pipeline_id)
    return info_json["nextRun"]
"""


def generate_ci_yaml(args, repository_id, branch_name):
    parameter = {}
    dict_object = json.loads(args["detail"].replace("'", '"'))
    doc = yaml.dump(dict_object)
    base_file = base64.b64encode(bytes(doc, encoding="utf-8")).decode("utf-8")
    parameter["branch"] = branch_name
    parameter["start_branch"] = branch_name
    parameter["encoding"] = "base64"
    parameter["content"] = base_file
    parameter["author_email"] = "system@iiidevops.org.tw"
    parameter["author_name"] = "iiidevops"
    (
        yaml_file_can_not_find,
        yml_file_can_not_find,
        get_yaml_data,
    ) = _get_rancher_pipeline_yaml(repository_id, parameter)
    if yaml_file_can_not_find and yml_file_can_not_find:
        method = "post"
        parameter["commit_message"] = "add .rancher-pipeline"
    elif yaml_file_can_not_find or yml_file_can_not_find:
        method = "put"
        parameter["commit_message"] = "modify .rancher-pipeline"
    else:
        raise apiError.DevOpsError(400, "Has both .yaml and .yml files")
    gitlab.gl_create_rancher_pipeline_yaml(repository_id, parameter, method)
    return util.success()


def get_ci_yaml(repository_id, branch_name):
    parameter = {"branch": branch_name}
    (
        yaml_file_can_not_find,
        yml_file_can_not_find,
        get_yaml_data,
    ) = _get_rancher_pipeline_yaml(repository_id, parameter)
    if yaml_file_can_not_find and yml_file_can_not_find:
        return util.respond(204)
    rancher_ci_yaml = base64.b64decode(get_yaml_data["content"]).decode("utf-8")
    rancher_ci_json = yaml.safe_load(rancher_ci_yaml)
    return {"message": "success", "data": rancher_ci_json}, 200


def get_phase_yaml(repository_id, branch_name):
    parameter = {"branch": branch_name}
    (
        yaml_file_can_not_find,
        yml_file_can_not_find,
        get_yaml_data,
    ) = _get_rancher_pipeline_yaml(repository_id, parameter)
    if yaml_file_can_not_find and yml_file_can_not_find:
        return util.respond(204)

    rancher_ci_yaml = base64.b64decode(get_yaml_data["content"]).decode("utf-8")
    rancher_ci_json = yaml.safe_load(rancher_ci_yaml)
    phase_name_array = []
    phase_name = None
    for index, rancher_stage in enumerate(rancher_ci_json["stages"]):
        if "--" in rancher_stage["name"]:
            cut_list = rancher_stage["name"].split("--")
            phase_name = cut_list[0]
            soft_name = cut_list[1]
        else:
            soft_name = rancher_stage["name"]
        phase_name_array.append({"id": index + 1, "phase": phase_name, "software": soft_name})
    return {"message": "success", "data": phase_name_array}, 200


def _get_rancher_pipeline_yaml(repository_id, parameter):
    yaml_file_can_not_find = None
    yml_file_can_not_find = None
    get_yaml_data = None
    get_file_param = dict(parameter)
    try:
        get_file_param["file_path"] = ".rancher-pipeline.yaml"
        get_yaml_data = gitlab.gl_get_project_file_for_pipeline(repository_id, get_file_param).json()
        parameter["file_path"] = ".rancher-pipeline.yaml"
    except apiError.DevOpsError as e:
        if e.status_code == 404:
            yaml_file_can_not_find = True
    try:
        get_file_param["file_path"] = ".rancher-pipeline.yml"
        get_yaml_data = gitlab.gl_get_project_file_for_pipeline(repository_id, get_file_param).json()
        parameter["file_path"] = ".rancher-pipeline.yml"
    except apiError.DevOpsError as e:
        if e.status_code == 404:
            yml_file_can_not_find = True
    return yaml_file_can_not_find, yml_file_can_not_find, get_yaml_data


def check_pipeline_folder_exist(file_name, path):
    if file_name not in listdir(path):
        raise apiError.DevOpsError(
            404,
            "The file is not found in provided path.",
            apiError.file_not_found(file_name, path),
        )


def list_pipeline_file(project_name):
    project_folder_path = f"devops-data/project-data/{project_name}/pipeline"
    return {folder: listdir(f"{project_folder_path}/{folder}") for folder in listdir(project_folder_path)}


def upload_pipeline_file(project_name, folder_name, file):
    file_path = f"devops-data/project-data/{project_name}/pipeline/{folder_name}"
    makedirs(file_path, exist_ok=True)
    file.save(f"{file_path}/{file.filename}")


def download_pipeline_file(project_name, folder_name, file_name):
    file_path = f"devops-data/project-data/{project_name}/pipeline/{folder_name}"
    check_pipeline_folder_exist(file_name, file_path)
    return send_file(f"../{file_path}/{file_name}")


def delete_pipeline_file(project_name, folder_name, file_name):
    file_path = f"devops-data/project-data/{project_name}/pipeline/{folder_name}"
    check_pipeline_folder_exist(file_name, file_path)
    rmtree(file_path)


"""
def delete_rest_pipelines(project_name, branch_name):
    project_row = (
        db.session.query(ProjectPluginRelation)
        .join(Project)
        .filter(Project.id == ProjectPluginRelation.project_id)
        .filter(Project.name == project_name)
        .first()
    )

    if project_row is None:
        return
    repository_id = project_row.git_repository_id
    # output_array = pipeline_exec_list(repository_id, {"limit": 15, "start": 0})
    pipe_ids = [
        pipe["id"]
        for pipe in output_array["pipe_execs"]
        if pipe["execution_state"] in ["Waiting", "Building", "Queueing"] and pipe["commit_branch"] == branch_name
    ]
    for pipe_id in pipe_ids[1:]:
        pipeline_exec_action(repository_id, {"pipelines_exec_run": pipe_id, "action": "stop"})
"""
# --------------------- Resources ---------------------


class PipelineExec(Resource):
    @jwt_required()
    def get(self, repository_id):
        parser = reqparse.RequestParser()
        parser.add_argument("limit", default=10, type=int, location="args")
        parser.add_argument("start", default=0, type=int, location="args")
        args = parser.parse_args()
        return util.success(pipeline_exec_list(repository_id, args["limit"], args["start"]))
        # return util.success(gitlab.gl_get_pipeline_console(repository_id, args["limit"]))


class PipelineExecAction(Resource):
    @jwt_required()
    def post(self, repository_id):
        parser = reqparse.RequestParser()
        parser.add_argument("pipelines_exec_run", type=int, required=True)
        parser.add_argument("action", type=str, required=True)
        args = parser.parse_args()
        return pipeline_exec_action(repository_id, args)
        # return util.success()


class PipelineConfig(Resource):
    @jwt_required()
    def get(self, repository_id):
        parser = reqparse.RequestParser()
        parser.add_argument("pipelines_exec_run", type=int, required=True, location="args")
        args = parser.parse_args()
        return get_pipeline_job_status(repository_id, args["pipelines_exec_run"])
    

# ----------------------------------------------------------------------------------------------------------------------------

class PipelineExecLogs(Resource):
    @jwt_required()
    def get(self):
        parser = reqparse.RequestParser()
        parser.add_argument("repository_id", type=int, required=True, location="args")
        parser.add_argument("pipelines_exec_run", type=int, required=True, location="args")
        args = parser.parse_args()
        # return pipeline_exec_logs(args)
        return util.success()


class PipelineYaml(Resource):
    @jwt_required()
    def get(self, repository_id, branch_name):
        return get_ci_yaml(repository_id, branch_name)

    @jwt_required()
    def post(self, repository_id, branch_name):
        parser = reqparse.RequestParser()
        parser.add_argument("detail")
        args = parser.parse_args()
        return generate_ci_yaml(args, repository_id, branch_name)


class PipelinePhaseYaml(Resource):
    @jwt_required()
    def get(self, repository_id, branch_name):
        return get_phase_yaml(repository_id, branch_name)



class Pipeline(Resource):
    @jwt_required()
    def post(self, repository_id):
        role.require_in_project(repository_id=repository_id)
        parser = reqparse.RequestParser()
        parser.add_argument("branch", type=str, required=True, location="form")
        args = parser.parse_args()
        # pipeline_action(repository_id, args)
        return util.success()


class PipelineFile(Resource):
    @jwt_required()
    def get(self, project_name):
        return util.success(list_pipeline_file(project_name))

    # Upload
    @jwt_required()
    def post(self, project_name):
        parser = reqparse.RequestParser()
        parser.add_argument("commit_short_id", type=str, required=True, location="form")
        parser.add_argument("sequence", type=int, required=True, location="form")
        parser.add_argument("upload_file", type=werkzeug.datastructures.FileStorage, location="files")
        args = parser.parse_args()
        folder_name = f'{args["commit_short_id"]}-{args["sequence"]}'
        upload_pipeline_file(project_name, folder_name, args["upload_file"])
        return util.success()

    # Download
    @jwt_required()
    def patch(self, project_name):
        parser = reqparse.RequestParser()
        parser.add_argument("commit_short_id", type=str, required=True)
        parser.add_argument("sequence", type=int, required=True)
        parser.add_argument("file_name", type=str, required=True)
        args = parser.parse_args()
        folder_name = f'{args["commit_short_id"]}-{args["sequence"]}'
        return download_pipeline_file(project_name, folder_name, args["file_name"])

    @jwt_required()
    def delete(self, project_name):
        parser = reqparse.RequestParser()
        parser.add_argument("folder_name", type=str, required=True, location="args")
        parser.add_argument("file_name", type=str, required=True, location="args")
        args = parser.parse_args()
        return util.success(delete_pipeline_file(project_name, args["folder_name"], args["file_name"]))


class PipelineWebsocketLog(Namespace):
    def on_connect(self):
        print("connect")

    def on_disconnect(self):
        print("Client disconnected")

    def on_get_pipe_log(self, data):
        print("get_pipe_log")
        get_pipe_log_websocket(data)
