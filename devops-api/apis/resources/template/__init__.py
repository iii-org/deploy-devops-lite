import json
import shutil
import subprocess
import sys
import threading
from datetime import datetime
from pathlib import Path
from typing import Any
import dateutil.parser
import yaml
from flask_jwt_extended import get_jwt_identity, jwt_required
from flask_restful import Resource, reqparse
from gitlab import Gitlab
from gitlab.exceptions import GitlabGetError
import ast
import config
import nexus
import resources.apiError as apiError
import resources.pipeline as pipeline
import resources.role as role
import util
from model import PluginSoftware, Project, db
from resources import logger
from resources.apiError import DevOpsError
from resources.gitlab import gitlab as rs_gitlab, get_all_group_projects
from resources.redis import (
    update_template_cache,
    get_template_caches_all,
    count_template_number,
    update_template_cache_all,
)


template_replace_dict = {
    # "registry": config.get("HARBOR_EXTERNAL_BASE_URL").replace("https://", ""),
    # "PLUGIN_MIRROR": config.get("HARBOR_EXTERNAL_BASE_URL"),
    # "harbor.host": config.get("HARBOR_EXTERNAL_BASE_URL").replace("https://", ""),
    "git.host": config.get("GITLAB_BASE_URL").replace("http://", ""),
    "kube.ingress.base_domain": config.get("INGRESS_EXTERNAL_BASE"),
}

gitlab_private_token = config.get("GITLAB_PRIVATE_TOKEN")
gl = Gitlab(config.get("GITLAB_BASE_URL"), private_token=gitlab_private_token, ssl_verify=False)
support_software_json = util.read_json_file("apis/resources/template/supported_software.json")
TEMPLATE_FOLDER_NAME = "pj_push_template"

TEMPLATE_GROUP_DICT = {
    "iiidevops-templates": "Public Templates",
    "local-templates": "Local Templates",
}

TEMPLATE_SUPPORT_VERSION = None
with open("apis/resources/template/template_support_version.json") as file:
    TEMPLATE_SUPPORT_VERSION = json.load(file)


def __tm_get_tag_info(pj, tag_name):
    tag_info_dict = {
        "tag_name": None,
        "commit_time": sys.float_info.max,
        "commit_id": None,
    }
    tags = pj.tags.list()
    if len(tags) != 0:
        if tag_name is None:
            # Get the last tag
            for tag in tags:
                seconds = (
                    datetime.utcnow() - dateutil.parser.parse(tag.commit["committed_date"]).replace(tzinfo=None)
                ).total_seconds()
                if seconds < tag_info_dict["commit_time"]:
                    tag_info_dict["tag_name"] = tag.name
                    tag_info_dict["commit_time"] = seconds
                    tag_info_dict["commit_id"] = tag.commit["id"]
        else:
            for tag in tags:
                if tag_name == tag.name:
                    tag_info_dict["tag_name"] = tag.name
                    tag_info_dict["commit_id"] = tag.commit["id"]
    else:
        tag_info_dict = {
            "tag_name": pj.default_branch,
            "commit_time": sys.float_info.max,
            "commit_id": pj.default_branch,
        }
    return tag_info_dict


def __tm_get_pipe_yamlfile_name(pj, tag_name=None, branch_name=None, commit_id=None):
    pipe_yaml_file_name = None
    if tag_name is None and branch_name is None and commit_id is None:
        ref = pj.default_branch
    elif tag_name is not None:
        tag_info_dict = __tm_get_tag_info(pj, tag_name)
        ref = tag_info_dict["commit_id"]
    elif branch_name is not None:
        ref = branch_name
    elif commit_id is not None:
        ref = commit_id
    for item in pj.repository_tree(ref=ref):
        if item["path"] == ".rancher-pipeline.yml":
            pipe_yaml_file_name = ".rancher-pipeline.yml"
        elif item["path"] == ".rancher-pipeline.yaml":
            pipe_yaml_file_name = ".rancher-pipeline.yaml"
    return pipe_yaml_file_name


def tm_get_git_pipeline_json(pj, tag_name=None, commit_id=None):
    if tag_name is None and commit_id is None:
        pipe_yaml_file_name = __tm_get_pipe_yamlfile_name(pj)
        ref = pj.default_branch
    elif commit_id:
        pipe_yaml_file_name = __tm_get_pipe_yamlfile_name(pj, commit_id=commit_id)
        ref = commit_id
    else:
        pipe_yaml_file_name = __tm_get_pipe_yamlfile_name(pj, tag_name=tag_name)
        tag_info_dict = __tm_get_tag_info(pj, tag_name)
        ref = tag_info_dict["commit_id"]

    f_raw = pj.files.raw(file_path=pipe_yaml_file_name, ref=ref)
    pipe_json = yaml.safe_load(f_raw.decode())
    return pipe_json


def tm_read_pipe_set_json(pj, tag_name=None):
    pip_set_json = {}
    try:
        if pj.empty_repo:
            return {"description": "", "name": pj.name}
        if tag_name is None:
            iiidevops_folder = pj.repository_tree(path="iiidevops", all=True)
        else:
            tag_info_dict = __tm_get_tag_info(pj, tag_name)
            iiidevops_folder = pj.repository_tree(path="iiidevops", ref=tag_info_dict["commit_id"], all=True)
        for file in iiidevops_folder:
            if file["name"] == "pipeline_settings.json":
                f_raw = pj.files.raw(file_path="iiidevops/pipeline_settings.json", ref=pj.default_branch)
                pip_set_json = json.loads(f_raw.decode())
        return pip_set_json
    except apiError.TemplateError:
        return {"description": "", "name": pj.name}


def set_git_username_config(path):
    git_user_email_proc = subprocess.Popen(["git", "config", "user.email"], stdout=subprocess.PIPE, shell=False)
    git_user_name_proc = subprocess.Popen(["git", "config", "user.name"], stdout=subprocess.PIPE, shell=False)
    git_user_email = git_user_email_proc.stdout.read().decode("utf-8")
    git_user_name = git_user_name_proc.stdout.read().decode("utf-8")
    if git_user_email == "":
        subprocess.call(
            ["git", "config", "--global", "user.email", '"system@iiidevops.org"'],
            cwd=path,
        )
    if git_user_name == "":
        subprocess.call(["git", "config", "--global", "user.name", '"system"'], cwd=path)


def __check_git_project_is_empty(pj):
    if pj.default_branch is None or pj.repository_tree() is None:
        return True


def fetch_latest_plugin_status():
    """
    從資料庫拉取 plugin 的啟用狀態並更新 support_software_json 的值
    :return:
    """
    db_plugins = PluginSoftware.query.all()
    for software in support_software_json:
        for db_plugin in db_plugins:
            if software.get("plugin_key") == db_plugin.name:
                software["plugin_disabled"] = db_plugin.disabled


def __compare_tag_version(tag_version, start_version, end_version=None):
    def version_parser(version_string):
        return version_string.replace("v", "").split(".")

    def ver_hight_greater_ver_low(ver_low, ver_hight):
        i = 0
        while i < 3:
            if int(ver_hight[i]) > int(ver_low[i]):
                return True
            elif int(ver_hight[i]) < int(ver_low[i]):
                return False
            elif i == 2:
                return True
            else:
                i += 1

    # has end
    tag_version_list = version_parser(tag_version)
    tag_version_list = tag_version_list + [0] * (3 - len(tag_version_list))
    start_version_list = version_parser(start_version)
    start_version_list = start_version_list + [0] * (3 - len(start_version_list))
    if end_version == "":
        return ver_hight_greater_ver_low(start_version_list, tag_version_list)
    else:
        # has end version
        end_version_list = version_parser(end_version)
        end_version_list = end_version_list + [0] * (3 - len(end_version_list))
        over_start_ver = ver_hight_greater_ver_low(start_version_list, tag_version_list)
        low_end_ver = ver_hight_greater_ver_low(tag_version_list, end_version_list)
        if over_start_ver and low_end_ver:
            return True
        else:
            return False


def get_tag_info_list_from_pj(pj, group_name):
    # get all tags
    tag_list = []
    for tag in pj.tags.list(all=True):
        if group_name == "iiidevops-templates" and TEMPLATE_SUPPORT_VERSION is not None:
            for temp_name, temp_value in TEMPLATE_SUPPORT_VERSION.items():
                if temp_name == pj.name:
                    status = __compare_tag_version(
                        tag.name,
                        temp_value.get("start_version"),
                        temp_value.get("end_version"),
                    )
                    if status:
                        tag_list.append(
                            {
                                "name": tag.name,
                                "commit_id": tag.commit["id"],
                                "commit_time": tag.commit["committed_date"],
                            }
                        )
                    break
        else:
            tag_list.append(
                {
                    "name": tag.name,
                    "commit_id": tag.commit["id"],
                    "commit_time": tag.commit["committed_date"],
                }
            )
    return tag_list


def handle_template_cache(pj, group_name, pip_set_json, tag_list):
    return {
        str(pj.id): json.dumps(
            {
                "name": pj.name,
                "path": pj.path,
                "display": pip_set_json["name"],
                "description": pip_set_json["description"],
                "version": tag_list,
                "update_at": datetime.utcnow().isoformat(),
                "group_name": TEMPLATE_GROUP_DICT.get(group_name),
            },
            default=str,
        )
    }


def update_redis_template_cache(pj, group_name, pip_set_json, tag_list):
    update_template_cache(
        pj.id,
        {
            "name": pj.name,
            "path": pj.path,
            "display": pip_set_json["name"],
            "description": pip_set_json["description"],
            "version": tag_list,
            "update_at": datetime.utcnow(),
            "group_name": TEMPLATE_GROUP_DICT.get(group_name),
        },
    )


def fetch_and_update_template_cache():
    logger.logger.info("Start updating template cache.")
    output = [
        {"source": "Public Templates", "options": []},
        {"source": "Local Templates", "options": []},
    ]
    template_list = {}
    for group in gl.groups.list(all=True):
        if group.name in TEMPLATE_GROUP_DICT:
            for group_project in get_all_group_projects(group):
                pj = gl.projects.get(group_project.id)
                if pj.empty_repo:
                    continue
                tag_list = get_tag_info_list_from_pj(pj, group.name)
                pip_set_json = tm_read_pipe_set_json(pj)
                template_data = {
                    "id": pj.id,
                    "name": pj.name,
                    "path": pj.path,
                    "display": pip_set_json["name"],
                    "description": pip_set_json["description"],
                    "version": tag_list,
                }
                if group.name == "iiidevops-templates" and TEMPLATE_SUPPORT_VERSION is None:
                    output[0]["options"].append(template_data)
                elif (
                    group.name == "iiidevops-templates"
                    and TEMPLATE_SUPPORT_VERSION is not None
                    and pj.name in TEMPLATE_SUPPORT_VERSION
                ):
                    output[0]["options"].append(template_data)
                elif group.name == "local-templates":
                    output[1]["options"].append(template_data)
                template_list |= handle_template_cache(pj, group.name, pip_set_json, tag_list)
                # update_redis_template_cache(pj, group.name, pip_set_json, tag_list)
    update_template_cache_all(template_list)
    logger.logger.info(f"Updated data: {template_list}")
    return output


def __update_stage_when_plugin_disable(stage):
    if stage.get("iiidevops") is not None:
        for software in support_software_json:
            if software.get("template_key") == stage.get("iiidevops") and software.get("plugin_disabled") is True:
                if "when" not in stage:
                    stage["when"] = {"branch": {"include": []}}
                stage_when = stage.get("when", {}).get("branch", {}).get("include", {})
                stage_when.clear()
                stage_when.append("skip")
    return stage


def lock_project(pj_name, info):
    pj_row = Project.query.filter_by(name=pj_name).first()
    pj_row.is_lock = True
    pj_row.lock_reason = f"The {info} softwares of the {pj_name} project has been deleted."
    db.session.commit()


def tm_get_template_list(force_update=0):
    if force_update == 1:
        return fetch_and_update_template_cache()
    elif count_template_number() == 0:
        return fetch_and_update_template_cache()
    else:
        total_data = get_template_caches_all()
        output = [
            {"source": "Public Templates", "options": []},
            {"source": "Local Templates", "options": []},
        ]
        for data in total_data:
            k = list(data.keys())[0]
            v = list(data.values())[0]
            try:
                gl.projects.get(k, lazy=True)
            except:
                continue
            if v.get("group_name") == "Public Templates":
                i = 0
            else:
                i = 1
            output[i]["options"].append(
                {
                    "id": k,
                    "name": v.get("name"),
                    "path": v.get("path"),
                    "display": v.get("display"),
                    "description": v.get("description"),
                    "version": v.get("version"),
                }
            )

        output[0]["options"].sort(key=lambda x: x["display"])
        output[1]["options"].sort(key=lambda x: x["display"])
        return output


def tm_get_template(repository_id, tag_name):
    pj = gl.projects.get(repository_id)
    tag_info_dict = __tm_get_tag_info(pj, tag_name)
    pip_set_json = tm_read_pipe_set_json(pj, tag_name)
    output = {"id": int(repository_id), "tag_name": tag_info_dict["tag_name"]}
    if "name" in pip_set_json:
        output["name"] = pip_set_json["name"]
    if "description" in pip_set_json:
        output["description"] = pip_set_json["description"]
    if "arguments" in pip_set_json:
        output["arguments"] = pip_set_json["arguments"]
    return output


def get_projects_detail(template_repository_id):
    return gl.projects.get(template_repository_id)


def tm_get_secret_url(pj):
    http_url = pj.http_url_to_repo
    protocol = "https" if http_url[:5] == "https" else "http"
    if protocol == "https":
        secret_http_url = http_url[:8] + f"root:{gitlab_private_token}@" + http_url[8:]
    else:
        secret_http_url = http_url[:7] + f"root:{gitlab_private_token}@" + http_url[7:]
    return secret_http_url


def tm_use_template_push_into_pj(template_repository_id, user_repository_id, tag_name, arguments, uuids, force=False):
    fetch_latest_plugin_status()
    template_pj = gl.projects.get(template_repository_id)
    secret_temp_http_url = tm_get_secret_url(template_pj)
    tag_info_dict = __tm_get_tag_info(template_pj, tag_name)
    pipe_yaml_file_name = __tm_get_pipe_yamlfile_name(template_pj, tag_name=tag_name)
    pip_set_json = tm_read_pipe_set_json(template_pj, tag_name)

    pj = gl.projects.get(user_repository_id)
    secret_pj_http_url = tm_get_secret_url(pj)
    Path(TEMPLATE_FOLDER_NAME).mkdir(exist_ok=True)
    subprocess.call(
        [
            "git",
            "clone",
            "--branch",
            tag_info_dict["tag_name"],
            secret_temp_http_url,
            f"{TEMPLATE_FOLDER_NAME}/{pj.path}",
        ]
    )
    pipe_json = None
    with open(f"{TEMPLATE_FOLDER_NAME}/{pj.path}/{pipe_yaml_file_name}") as file:
        pipe_json = yaml.safe_load(file)
        for stage in pipe_json["stages"]:
            if "steps" in stage:
                for step in stage["steps"]:
                    for fun_key, fun_value in step.items():
                        # Replace System parameters, like harbor.host, registry.
                        if fun_key == "applyAppConfig":
                            for ans_key in fun_value["answers"].keys():
                                if ans_key in template_replace_dict:
                                    fun_value["answers"][ans_key] = template_replace_dict[ans_key]
                                # Replace by pipeline_settings.json default value
                                if "arguments" in pip_set_json:
                                    for argument in pip_set_json["arguments"]:
                                        if "default_value" in argument and argument["key"] == ans_key:
                                            fun_value["answers"][ans_key] = argument["default_value"]
                                # Replace by user input parameter.
                                if arguments is not None and ans_key in arguments:
                                    if type(arguments) is str:
                                        arguments = ast.literal_eval(arguments)
                                    for arg_key, arg_value in arguments.items():
                                        if arg_key is not None and ans_key == arg_key:
                                            fun_value["answers"][ans_key] = arg_value

                            # Add volume uuid in DB and Web answer.
                            if fun_value.get("answers", {}).get("volumeMounts.uuid") is not None:
                                fun_value["answers"]["volumeMounts.uuid"] = uuids

                        elif fun_key == "envFrom":
                            pass
                        else:
                            for parm_key in fun_value.keys():
                                if parm_key in template_replace_dict:
                                    fun_value[parm_key] = template_replace_dict[parm_key]
            stage = __update_stage_when_plugin_disable(stage)
    with open(f"{TEMPLATE_FOLDER_NAME}/{pj.path}/{pipe_yaml_file_name}", "w") as file:
        yaml.dump(pipe_json, file, sort_keys=False)
    set_git_username_config(f"{TEMPLATE_FOLDER_NAME}/{pj.path}")
    tm_git_commit_push(pj.path, secret_pj_http_url, TEMPLATE_FOLDER_NAME, "範本 commit", force=force)


def tm_git_commit_push(pj_path, secret_pj_http_url, folder_name, commit_message, force=False):
    subprocess.call(["git", "branch"], cwd=f"{folder_name}/{pj_path}")
    # Too lazy to handle file deleting issue on Windows, just keep the garbage there
    try:
        shutil.rmtree(f"{folder_name}/{pj_path}/.git")
    except PermissionError:
        pass
    subprocess.call(["git", "init"], cwd=f"{folder_name}/{pj_path}")
    subprocess.call(
        ["git", "remote", "add", "origin", secret_pj_http_url],
        cwd=f"{folder_name}/{pj_path}",
    )
    subprocess.call(["git", "add", "."], cwd=f"{folder_name}/{pj_path}")
    subprocess.call(["git", "commit", "-m", f'"{commit_message}"'], cwd=f"{folder_name}/{pj_path}")
    if force:
        subprocess.call(
            ["git", "push", "-u", "-f", "origin", "master"],
            cwd=f"{folder_name}/{pj_path}",
        )
    else:
        subprocess.call(["git", "push", "-u", "origin", "master"], cwd=f"{folder_name}/{pj_path}")
    # Too lazy to handle file deleting issue on Windows, just keep the garbage there
    try:
        shutil.rmtree(f"{folder_name}/{pj_path}", ignore_errors=True)
    except PermissionError:
        pass


def tm_git_mirror_push(pj_path, secret_pj_http_url, folder_name):
    subprocess.call(
        ["git", "remote", "set-url", "origin", secret_pj_http_url],
        cwd=f"{folder_name}/{pj_path}",
    )
    subprocess.call(["git", "push", "--mirror"], cwd=f"{folder_name}/{pj_path}")
    try:
        shutil.rmtree(f"{folder_name}/{pj_path}", ignore_errors=True)
    except PermissionError:
        pass


def tm_get_pipeline_branches(repository_id, all_data=False):
    out = {}
    duplicate_tools = {}
    pj = gl.projects.get(repository_id)
    project_branches = pj.branches.list(all=True)
    all_branch = [_.name for _ in project_branches]
    stages_info = tm_get_pipeline_default_branch(repository_id, is_default_branch=False)
    disable_list = []
    if PluginSoftware.query.filter_by(disabled=True).first():
        rows = PluginSoftware.query.filter_by(disabled=True).all()
        disable_list = [row.name for row in rows]

    if not stages_info:
        return out

    for branch in project_branches:
        testing_tools: list[dict[str, Any]] = []
        for yaml_stage in stages_info["stages"]:
            if branch.name not in out:
                out[branch.name] = {
                    "commit_message": branch.commit["message"],
                    "commit_time": branch.commit["created_at"],
                }
            soft_key_and_status = {
                "key": yaml_stage["key"],
                "name": yaml_stage["name"],
                "enable": "branches" in yaml_stage and branch.name in yaml_stage["branches"],
            }
            if soft_key_and_status not in testing_tools:
                if all_data:
                    tem_soft_key_and_status = soft_key_and_status.copy()
                    tem_soft_key_and_status["enable"] = not tem_soft_key_and_status["enable"]
                    if tem_soft_key_and_status in testing_tools:
                        duplicate_tools.setdefault(f'{yaml_stage["key"]},{yaml_stage["name"]}', []).append(branch.name)
                testing_tools.append(soft_key_and_status)
        out[branch.name]["testing_tools"] = testing_tools
        if disable_list != []:
            for index, value in enumerate(testing_tools):
                if value["key"] in disable_list:
                    del testing_tools[index]

    # Put duplicate tools to the end of the list(FrontEnd needs right order and same length)
    for key, branch_list in duplicate_tools.items():
        if sorted(all_branch) == sorted(branch_list):
            continue

        positive_temp_tool = generate_temp_pipline_tool(key, True)
        negative_temp_tool = generate_temp_pipline_tool(key, False)

        for branch in all_branch:
            for temp_tool in [positive_temp_tool, negative_temp_tool]:
                if branch in branch_list:
                    out[branch]["testing_tools"].remove(temp_tool)
                    out[branch]["testing_tools"].append(temp_tool)
                elif temp_tool in out[branch]["testing_tools"]:
                    out[branch]["testing_tools"].remove(temp_tool)
                    out[branch]["testing_tools"].append(temp_tool)
                    out[branch]["testing_tools"].append(temp_tool)
    return out


def generate_temp_pipline_tool(tool_name, enable):
    return {
        "key": tool_name.split(",")[0],
        "name": tool_name.split(",")[1],
        "enable": enable,
    }


def get_tool_name(stage):
    """
    It will delete when all rancher_pipline.yml has iiidevops.
    Only updating pipline_branch will use.
    """
    if stage.get("iiidevops") is not None:
        tool_name = stage["iiidevops"]
    else:
        if stage["name"].startswith("Test--SonarQube for Java"):
            tool_name = "sonarqube"
        else:
            tool_name = stage.get("steps")[0].get("applyAppConfig", {}).get("catalogTemplate")
            if tool_name is not None:
                tool_name = tool_name.split(":")[1].replace("iii-dev-charts3-", "")
                if tool_name == "web":
                    tool_name = "deployed-environments"
                else:
                    for prefix in ["test-", "scan-"]:
                        if tool_name.startswith(prefix):
                            tool_name = tool_name.replace(prefix, "")
                            break
            else:
                tool_name = "deployed-environments"
    return tool_name


def handle_stage_format_helper(stage, column):
    if isinstance(stage.get(column), dict):
        return True
    elif isinstance(stage.get(column), list):
        return stage[column]
    else:
        return []


def handle_stage_format(stage):
    stage_copy = stage.copy()
    for column in ["when", "branch", "include"]:
        ret = handle_stage_format_helper(stage_copy, column)
        if ret is True:
            stage_copy = stage_copy.get(column)
        else:
            return ret
    return []


def update_branches(stage, pipline_soft, branch, enable_key_name, exist_branches):
    had_update_branche = False
    if get_tool_name(stage) is not None and pipline_soft["key"] == get_tool_name(stage):
        if "when" not in stage:
            stage["when"] = {"branch": {"include": []}}
        stage_when = handle_stage_format(stage)
        if pipline_soft[enable_key_name] and branch not in stage_when:
            stage_when.append(branch)
            had_update_branche = True
        elif pipline_soft[enable_key_name] is False and branch in stage_when:
            stage_when.remove(branch)
            had_update_branche = True

        stage_when = [branch for branch in stage_when if branch in exist_branches]
        if len(stage_when) == 0:
            stage_when.append("skip")
            had_update_branche = True
        elif len(stage_when) > 1 and "skip" in stage_when:
            stage_when.remove("skip")
            had_update_branche = True
        stage["when"] = {"branch": {"include": stage_when}}
    return had_update_branche


def tm_update_pipline_branches(user_account, repository_id, data, default=True, run=False):
    if run is None:
        run = False
    pj = gl.projects.get(repository_id)
    if __check_git_project_is_empty(pj):
        return
    exist_branch_list = [br.name for br in pj.branches.list(all=True)]

    # Update default branch's pipeline
    default_branch = pj.default_branch
    had_update_branche = False
    all_branches = [br.name for br in pj.branches.list(all=True)]
    need_running_branches = [i for i in list(data.keys()) if i in all_branches]
    pipe_yaml_file_name = __tm_get_pipe_yamlfile_name(pj)
    if pipe_yaml_file_name is None:
        return
    f = rs_gitlab.gl_get_file_from_lib(repository_id, pipe_yaml_file_name, branch_name=default_branch)
    default_pipe_json = yaml.safe_load(f.decode())
    for stage in default_pipe_json["stages"]:
        if default:
            for put_pipe_soft in data["stages"]:
                had_update_branche |= update_branches(
                    stage,
                    put_pipe_soft,
                    pj.default_branch,
                    "has_default_branch",
                    exist_branch_list,
                )
        else:
            for input_branch, multi_software in data.items():
                for input_soft_enable in multi_software:
                    had_update_branche |= update_branches(
                        stage,
                        input_soft_enable,
                        input_branch,
                        "enable",
                        exist_branch_list,
                    )
    if had_update_branche:
        # if not run or default or (run and default_branch not in need_running_branches):
        #     next_run = pipeline.get_pipeline_next_run(repository_id)
        #     print(f"next_run: {next_run}")
        #     create_pipeline_execution(repository_id, default_branch, next_run)

        f.content = yaml.dump(default_pipe_json, sort_keys=False)
        f.save(
            branch=default_branch,
            author_email="system@iiidevops.org.tw",
            author_name="iiidevops",
            commit_message=f"{user_account} 編輯 {default_branch} 分支 .rancher-pipeline.yaml",
        )
        # if not run or default or (run and default_branch not in need_running_branches):
        # pipeline.stop_and_delete_pipeline(repository_id, next_run, branch=default_branch)

    # Sync default branch pipeline.yml to other branches, seperate to two parts to avoid not delete all branches
    for br_name in need_running_branches:
        sync_branch(
            user_account,
            repository_id,
            pipe_yaml_file_name,
            br_name,
            default_pipe_json,
            not_run=not run,
        )

    # Rest of branches
    rest_branch_names = sorted([br for br in all_branches if br not in need_running_branches + [default_branch]])
    thread = threading.Thread(
        target=sync_branches,
        args=(
            user_account,
            repository_id,
            pipe_yaml_file_name,
            rest_branch_names,
            default_pipe_json,
        ),
    )
    thread.start()


def sync_branches(user_account, repository_id, pipe_yaml_file_name, br_name_list, default_pipe_json):
    for br_name in br_name_list:
        sync_branch(user_account, repository_id, pipe_yaml_file_name, br_name, default_pipe_json)


def sync_branch(
    user_account,
    repository_id,
    pipe_yaml_file_name,
    br_name,
    updated_pipe_json,
    not_run=True,
):
    f = rs_gitlab.gl_get_file_from_lib(repository_id, pipe_yaml_file_name, branch_name=br_name)
    pipe_json = yaml.safe_load(f.decode())
    had_update_branche = pipe_json != updated_pipe_json
    pipe_json = updated_pipe_json
    if had_update_branche:
        if not_run:
            next_run = pipeline.get_pipeline_next_run(repository_id)
            print(f"next_run: {next_run}")
            # create_pipeline_execution(repository_id, br_name, next_run)

        f.content = yaml.dump(pipe_json, sort_keys=False)
        f.save(
            branch=br_name,
            author_email="system@iiidevops.org.tw",
            author_name="iiidevops",
            commit_message=f"{user_account} 編輯 {br_name} 分支 .rancher-pipeline.yaml",
        )
        if not_run:
            pipeline.stop_and_delete_pipeline(repository_id, next_run, branch=br_name)
            print(f"stop_and_delete: {next_run}")


def initial_rancher_pipline_info(repository_id):
    try:
        pj = gl.projects.get(repository_id)
    except GitlabGetError as e:
        if "Project Not Found" in e.error_message:
            lock_project(
                nexus.nx_get_project(id=nexus.nx_get_project_plugin_relation(repo_id=repository_id).project_id).name,
                "Gitlab",
            )
        raise DevOpsError(
            404,
            "Gitlab project not found.",
            error=apiError.repository_id_not_found(repository_id),
        )
    if __check_git_project_is_empty(pj):
        return {}
    default_branch = pj.default_branch
    pipe_yaml_name = __tm_get_pipe_yamlfile_name(pj, branch_name=default_branch)
    if pipe_yaml_name is None:
        return {}
    f = rs_gitlab.gl_get_file_from_lib(repository_id, pipe_yaml_name, branch_name=default_branch)
    return {"default_branch": default_branch, "pipe_dict": yaml.safe_load(f.decode())}


def update_nonexist_key_rancher_file(repository_id: int):
    """
    更新 iiidevops 鍵值不存在的 .rancher-pipeline.yml 檔案

    :param repository_id:
    :return:
    """
    initial_info = initial_rancher_pipline_info(repository_id)

    if not initial_info:
        return initial_info

    pipe_dict = initial_info["pipe_dict"]

    # It will be removed if all project rancher.pipline.yml is in new type.
    for stage in pipe_dict["stages"]:
        if stage.get("iiidevops") is None:
            update_pj_rancher_pipline(repository_id)
            break


def tm_get_pipeline_default_branch(repository_id, is_default_branch=True):
    update_nonexist_key_rancher_file(repository_id)
    initial_info = initial_rancher_pipline_info(repository_id)
    disable_list = []
    if PluginSoftware.query.filter_by(disabled=True).first():
        rows = PluginSoftware.query.filter_by(disabled=True).all()
        disable_list = [row.name for row in rows]

    if not initial_info:
        return initial_info

    default_branch = initial_info["default_branch"]
    stages_info = {"default_branch": default_branch, "stages": []}
    return_stages = []
    file_stages = initial_info["pipe_dict"]["stages"]

    fetch_latest_plugin_status()  # update plugin enable status
    software_dict = {_["template_key"]: _ for _ in support_software_json}

    for stage in file_stages:
        single_stage = {"has_default_branch": False}
        tool = stage["iiidevops"]

        software = software_dict.get(tool, None)
        if software and (not software.get("plugin_disabled") or tool == "deployed-environments"):
            single_stage["name"] = software["display"]
            single_stage["key"] = software["template_key"]

        else:
            if tool != "initial-pipeline":
                # Exclude case: initial-pipeline
                single_stage["name"] = tool
                single_stage["key"] = tool

        if "when" in stage:
            include_branches = stage["when"]["branch"].get("include", [])
            if is_default_branch:
                single_stage["has_default_branch"] = default_branch in include_branches
            else:
                single_stage["branches"] = include_branches

        if (
            single_stage not in return_stages
            and single_stage.get("name", False)
            and single_stage.get("name") not in disable_list
        ):
            # 沒有 name 的 stage 表示是 initial-pipeline 的 stage
            return_stages.append(single_stage)

    stages_info["stages"] = return_stages
    return stages_info


def update_pj_rancher_pipline(repository_id):
    pj = gl.projects.get(repository_id)
    if pj.empty_repo:
        return
    for br in pj.branches.list(all=True):
        try:
            pipe_yaml_name = __tm_get_pipe_yamlfile_name(pj, branch_name=br.name)
            f = rs_gitlab.gl_get_file_from_lib(repository_id, pipe_yaml_name, branch_name=br.name)
            pipe_dict = yaml.safe_load(f.decode())
            temp_list = []
            for info in pipe_dict["stages"]:
                info_name = info["name"]
                logger.logger.info(f"name : {info_name}")
                if info.get("iiidevops") is None:
                    temp_dict = {"name": info.pop("name")}
                    if info_name.startswith("Test--SonarQube"):
                        temp_dict["iiidevops"] = "sonarqube"
                        temp_dict.update(info)
                        info = temp_dict
                    else:
                        catalog_template_value = info["steps"][0].get("applyAppConfig", {}).get("catalogTemplate")
                        if catalog_template_value is not None:
                            catalog_template_value = catalog_template_value.split(":")[1].replace(
                                "iii-dev-charts3-", ""
                            )
                            if catalog_template_value == "web":
                                catalog_template_value = "deployed-environments"
                            else:
                                for prefix in ["test-", "scan-"]:
                                    if catalog_template_value.startswith(prefix):
                                        catalog_template_value = catalog_template_value.replace(prefix, "")
                                        break
                        else:
                            catalog_template_value = "deployed-environments"
                        temp_dict["iiidevops"] = catalog_template_value
                        temp_dict.update(info)
                        info = temp_dict

                temp_list.append(info)
            pipe_dict["stages"] = temp_list
        except Exception as e:
            logger.logger.info(str(e))
            continue

        next_run = pipeline.get_pipeline_next_run(repository_id)
        f.content = yaml.dump(pipe_dict, sort_keys=False)
        f.save(
            branch=br.name,
            author_email="system@iiidevops.org.tw",
            author_name="iiidevops",
            commit_message=f'Add "iiidevops" in branch {br.name} .rancher-pipeline.yml.',
        )
        pipeline.stop_and_delete_pipeline(repository_id, next_run)


def update_project_rancher_pipline():
    projects = Project.query.all()
    project_id_list = [pj.id for pj in projects]
    project_id_list.remove(-1)
    for pj_id in project_id_list:
        logger.logger.info(f"project_id : {pj_id}")
        repository_id = nexus.nx_get_repository_id(pj_id)
        update_pj_rancher_pipline(repository_id)
        logger.logger.info(f"{pj_id} update completely")


def update_pj_plugin_status(plugin_name, disable):
    projects = Project.query.all()
    project_id_list = [pj.id for pj in projects]
    project_id_list.remove(-1)
    for pj_id in project_id_list:
        logger.logger.info(f"project_id : {pj_id}")
        repository_id = nexus.nx_get_repository_id(pj_id)
        pj = gl.projects.get(repository_id)
        if pj.empty_repo:
            continue
        branch_name_list = [br.name for br in pj.branches.list(all=True)]
        for br in pj.branches.list(all=True):
            pipe_yaml_name = __tm_get_pipe_yamlfile_name(pj, branch_name=br.name)
            f = rs_gitlab.gl_get_file_from_lib(repository_id, pipe_yaml_name, branch_name=br.name)
            pipe_dict = yaml.safe_load(f.decode())
            match = False
            for stage in pipe_dict["stages"]:
                if get_tool_name(stage) == plugin_name:
                    match = True
                    if "when" not in stage:
                        stage["when"] = {"branch": {"include": []}}
                    stage_when = stage.get("when", {}).get("branch", {}).get("include", {})
                    if disable:
                        stage_when.clear()
                        stage_when.append("skip")
                    else:
                        for branch in branch_name_list:
                            if branch not in stage_when:
                                stage_when.append(branch)

                    if len(stage_when) > 1 and "skip" in stage_when:
                        stage_when.remove("skip")
            # Do not commit if plugin_name has not match any stage.
            if match:
                # next_run = pipeline.get_pipeline_next_run(repository_id)
                f.content = yaml.dump(pipe_dict, sort_keys=False)
                process = "啟用" if not disable else "停用"
                f.save(
                    branch=br.name,
                    author_email="system@iiidevops.org.tw",
                    author_name="iiidevops",
                    commit_message=f"UI 編輯 .rancher-pipeline.yaml {process} {plugin_name}.",
                )
                # pipeline.stop_and_delete_pipeline(repository_id, next_run)


# --------------------- Resources ---------------------


class TemplateList(Resource):
    @jwt_required()
    def get(self):
        role.require_pm("Error while getting template list.")
        parser = reqparse.RequestParser()
        parser.add_argument("force_update", type=int, location="args")
        args = parser.parse_args()
        return util.success(tm_get_template_list(args["force_update"]))


class TemplateListForCronJob(Resource):
    def get(self):
        parser = reqparse.RequestParser()
        parser.add_argument("force_update", type=int, location="args")
        args = parser.parse_args()
        return util.success(tm_get_template_list(args["force_update"]))


class SingleTemplate(Resource):
    @jwt_required()
    def get(self, repository_id):
        role.require_pm("Error while getting template list.")
        parser = reqparse.RequestParser()
        parser.add_argument("tag_name", type=str, location="args")
        args = parser.parse_args()
        return util.success(tm_get_template(repository_id, args["tag_name"]))


class ProjectPipelineBranches(Resource):
    @jwt_required()
    def get(self, repository_id):
        parser = reqparse.RequestParser()
        parser.add_argument("all_data", type=bool, location="args")
        args = parser.parse_args()
        all_data = args.get("all_data") is not None

        return util.success(tm_get_pipeline_branches(repository_id, all_data=all_data))

    @jwt_required()
    def put(self, repository_id):
        parser = reqparse.RequestParser()
        parser.add_argument("detail", type=dict)
        parser.add_argument("run", type=bool)
        args = parser.parse_args()
        # Remove duplicate args
        for branch, pip_info in args["detail"].items():
            args["detail"][branch] = [dict(t) for t in {tuple(d.items()) for d in pip_info}]
        # thread = threading.Thread(
        #     target=tm_update_pipline_branches,
        #     args=(get_jwt_identity()["user_account"], repository_id, args["detail"],),
        #     kwargs={"default":False, "run": args["run"]}
        # )
        # thread.start()
        tm_update_pipline_branches(
            get_jwt_identity()["user_account"],
            repository_id,
            args["detail"],
            default=False,
            run=args["run"],
        )
        return util.success()


class ProjectPipelineDefaultBranch(Resource):
    @jwt_required()
    def get(self, repository_id):
        return util.success(tm_get_pipeline_default_branch(repository_id))

    @jwt_required()
    def put(self, repository_id):
        parser = reqparse.RequestParser()
        parser.add_argument("detail", type=dict)
        args = parser.parse_args()

        # Remove duplicate args
        args["detail"]["stages"] = [dict(t) for t in {tuple(d.items()) for d in args["detail"]["stages"]}]
        tm_update_pipline_branches(get_jwt_identity()["user_account"], repository_id, args["detail"])
        return util.success()
