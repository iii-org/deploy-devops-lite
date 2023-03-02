# Error code document at:
# https://github.com/iii-org/devops-system/wiki/ErrorCodes

from werkzeug.exceptions import HTTPException


def build(err_code, message, details=None):
    if details is None:
        return {"code": err_code, "message": message}
    else:
        return {"code": err_code, "message": message, "details": details}


def error_3rd_party_api(service_name, response):
    msg = None
    service_name_error_msg_mapping = {"Rancher": "message"}
    if type(response) is str:
        resp_value = response
    else:
        try:
            resp_value = response.json()
            error_key = service_name_error_msg_mapping.get(service_name, "")
            msg = resp_value.get(error_key, "")
        except Exception:
            msg = resp_value = response.text

    message = msg or f"{service_name} responds error."
    return build(8001, message, {"service_name": service_name, "response": resp_value})


# 1: Project errors
def identifier_has_been_taken(identifier):
    return build(1001, "Project identifier has been taken.", {"identifier": identifier})


def invalid_project_name(name):
    return build(
        1002,
        "Project name may only contain lower cases, numbers, dash, "
        "the heading and trailing character should be alphanumeric,"
        "and should be 2 to 225 characters long.",
        {"name": name},
    )


def project_not_found(project_id=None):
    return build(1003, "Project not found.", {"project_id": project_id})


def repository_id_not_found(repository_id=None):
    return build(1004, "Gitlab project not found.", {"repository_id": repository_id})


def redmine_project_not_found(project_id=None):
    return build(1005, "Redmine does not have this project.", {"project_id": project_id})


def redmine_unable_to_delete_version(version_id=None):
    return build(1006, "Unable to delete the version.", {"version_id": version_id})


def redmine_unable_to_forced_closed_issues(issues=None):
    return build(1007, "Unable to build the release.", {"issues": issues})


def release_unable_to_build(info=None):
    return build(1008, "Unable to build the release.", info)


def invalid_plugin_name(plugin_name):
    return build(1009, "Plugin Software not found.", {"plugin_name": plugin_name})


def invalid_project_content(key, value):
    return build(
        1010,
        "Project {0} contain characters like & or <.".format(key),
        {"{0}".format(key): value},
    )


def invalid_project_owner(owner_id=None):
    return build(1011, "Project owner role must be PM.", {"owner_id": owner_id})


def invalid_fixed_version_id(fixed_version, fixed_version_status):
    return build(
        1012,
        "Fixed version status is {0}.".format(fixed_version_status),
        {"fixed_version": fixed_version, "fixed_version_status": fixed_version_status},
    )


def unable_to_delete_issue_has_children(children_info):
    return build(
        1013,
        "Warning ! The issue with children issues cannot be deleted, \
                     please re-confirm it if you insist and all of children issue will be deleted at the same time.",
        children_info,
    )


def project_issue_file_not_exits(project_id):
    return build(
        1014,
        "File is not exist. Please ensure you have downloaded it before.",
        {"project_id": project_id},
    )


def project_name_not_found(project_name=None):
    return build(1015, "project_name not found.", {"project_name": project_name})


def project_version_exist(version_name):
    return build(
        1016,
        f"The project_version name {version_name} already exists, please try another one.",
        {"version_name": version_name},
    )


def project_is_disabled(project_id):
    return build(1017, "Project is disabled.", {"project_id": project_id})


def project_tracker_must_has_father_issue(project_id, tracker_name):
    return build(
        1018,
        f"Modify or Create issue with tacker_id:{tracker_name} must has father issue.",
        {"project_id": project_id, "tracker_name": tracker_name},
    )


# 2: User errors
def user_not_found(user_id):
    return build(2001, "User not found.", {"user_id": user_id})


def invalid_user_name(name):
    return build(
        2002,
        "User name may only contain a-z, A-Z, 0-9, dot, dash, underline, "
        "the heading and trailing character should be alphanumeric,"
        "and should be 2 to 60 characters long.",
        {"name": name},
    )


def invalid_user_password():
    return build(
        2003,
        "User password may only contain a-z, A-Z, 0-9, "
        "!@#$%^&*()_+|{}[]`~-='\";:/?.>,<, "
        "and should contain at least an upper case alphabet, "
        "a lower case alphabet, and a digit, "
        "and is 8 to 20 characters long.",
    )


def wrong_password():
    return build(2004, "Wrong password or username.")


def already_used():
    return build(2005, "This username or email is already used.")


def already_in_project(user_id, project_id):
    return build(
        2006,
        "This user is already in the project.",
        {"user_id": user_id, "project_id": project_id},
    )


def is_project_owner_in_project(user_id, project_id):
    return build(
        2007,
        "This user is project owner  in the project.",
        {"user_id": user_id, "project_id": project_id},
    )


def user_from_ad(user_id):
    return build(
        2008,
        "This user comes from ad server, normal user cannot modify.",
        {"user_id": user_id},
    )


def user_in_a_project(user_id):
    return build(2009, "User is in a project, cannot change his role.", {"user_id": user_id})


def ad_account_not_allow():
    return build(2010, "User Account in AD is invalid in DevOps System")


def get_clusters_failed(server_name=None):
    _FAILED_GET_CLUSTERS = "Get clusters error"
    if server_name is None:
        return build(2011, _FAILED_GET_CLUSTERS)
    return build(2011, _FAILED_GET_CLUSTERS, {"server_name": server_name})


def create_cluster_failed(server_name=None):
    _FAILED_CREATE_CLUSTERS = "Create clusters error"
    if server_name is None:
        return build(2012, _FAILED_CREATE_CLUSTERS)
    return build(2012, _FAILED_CREATE_CLUSTERS, {"server_name": server_name})


def update_cluster_failed(server_name=None):
    _FAILED_UPDATE_CLUSTERS = "Update clusters error"
    if server_name is None:
        return build(2013, _FAILED_UPDATE_CLUSTERS)
    return build(2013, _FAILED_UPDATE_CLUSTERS, {"server_name": server_name})


def delete_cluster_failed():
    return build(2014, "Delete clusters error")


def get_registry_failed(registry_id=None):
    _FAILED_GET_REGISTRIES = "Get registry error"
    if registry_id is None:
        return build(2015, _FAILED_GET_REGISTRIES)
    return build(2015, _FAILED_GET_REGISTRIES, {"registry_id": registry_id})


def create_registry_failed(registry_name=None):
    _FAILED_CREATE_REGISTRIES = "Create registry error"
    if registry_name is None:
        return build(2016, _FAILED_CREATE_REGISTRIES)
    return build(2016, _FAILED_CREATE_REGISTRIES, {"registry_name": registry_name})


def update_registry_failed(registry_name=None):
    _FAILED_UPDATE_REGISTRIES = "Update registry error"
    if registry_name is None:
        return build(2017, _FAILED_UPDATE_REGISTRIES)
    return build(2017, _FAILED_UPDATE_REGISTRIES, {"registry_name": registry_name})


def delete_registry_failed():
    return build(2018, "Delete registry error")


def create_deploy_application_failed(cluster_name=None, namespace=None, application_name=None):
    _FAILED_CREATE_DEPLOY_APPLICATION = "Create deploy application failed"
    if cluster_name is None or namespace is None or application_name is None:
        return build(2019, _FAILED_CREATE_DEPLOY_APPLICATION)
    else:
        return build(
            2019,
            _FAILED_CREATE_DEPLOY_APPLICATION,
            {
                "cluster_name": cluster_name,
                "application_name": application_name,
                "namespace": namespace,
            },
        )


def get_deploy_application_failed(**kwargs):
    _FAILED_GET_DEPLOY_APPLICATION = "Get deploy application failed"
    if len(kwargs) != 0:
        return build(2020, _FAILED_GET_DEPLOY_APPLICATION, kwargs)
    else:
        return build(2020, _FAILED_GET_DEPLOY_APPLICATION)


def update_deploy_application_failed(**kwargs):
    _FAILED_GET_DEPLOY_APPLICATION = "Get deploy application failed"
    if len(kwargs) != 0:
        return build(2021, _FAILED_GET_DEPLOY_APPLICATION, kwargs)
    else:
        return build(2021, _FAILED_GET_DEPLOY_APPLICATION)


def re_deploy_application_failed(application_name):
    return build(
        2022,
        "Deploy application had reached retry number limit",
        {"application_name": application_name},
    )


def delete_deploy_application_failed(application_id):
    return build(2023, "Delete deploy application failed", {"application_id", application_id})


# 3: Permission errors
class NotAllowedError(HTTPException):
    pass


class NotInProjectError(HTTPException):
    pass


class NotUserHimselfError(HTTPException):
    pass


class NotProjectOwnerError(HTTPException):
    pass


def license_key_error(plugin):
    return build(
        3007,
        "Sbom deployment failed, please contact DevOps for assistance.",
        {"service": plugin},
    )


def not_deployment_error(plugin):
    return build(3008, "Service has not been deployed.", {"service": plugin})


# Exception type errors, for errors those need to be aborted instantly rather than returning
# an error response.
custom_errors = {
    "NotAllowedError": {
        "error": build(3001, "Your role does not have the permission for this operation."),
        "status": 401,
    },
    "NotInProjectError": {
        "error": build(3002, "You need to be in the project for this operation."),
        "status": 401,
    },
    "NotUserHimselfError": {
        "error": build(3003, "You are not permitted to access another user's data."),
        "status": 401,
    },
    "NotProjectOwnerError": {
        "error": build(3004, "Only PM can set it, please contact PM for assistance."),
        "status": 401,
    },
}


# 4: Redmine Issue/Wiki/... errors
def issue_not_found(issue_id):
    return build(4001, "Issue not found.", {"issue_id": issue_id})


def issue_not_all_closed(version_ids):
    return build(4002, "Issue in Versions not closed.", {"versions": version_ids})


def redmine_unable_to_relate(issue_id, issue_to_id):
    return build(
        4003,
        "Issues {issue_id}, {issue_to_id} can not create relations.",
        {"issue_ids": [issue_id, issue_to_id]},
    )


# 5: Template errors
def template_not_found(template_id):
    return build(5001, "Template not found.", {"template_id": template_id})


def template_file_not_found(template_id, template_name):
    return build(
        5002,
        "Can not get template file or folder.",
        {"template_id": template_id, "template_name": template_name},
    )


def template_user_not_in_template_gitlab_repo(template_repository_id, user_id):
    return build(
        5003,
        f"User not in this template gitlab repository",
        {"template_repository_id": template_repository_id, "user_id": user_id},
    )


# 6: Notification message error
def not_enough_authorization(message_id, user_id):
    return build(
        6001,
        "Not enough authorization to get message.",
        {"message_id": message_id, "user_id": user_id},
    )


# 7: General errors
def no_detail():
    return build(7001, "This error has no detailed information.")


def argument_error(arg_name):
    return build(7002, "Argument {0} is incorrect.".format(arg_name), {"arg": arg_name})


def resource_not_found():
    return build(7003, "The indicated resource is not found.")


def path_not_found():
    return build(
        7004,
        "The requested URL is not found on this server. Please check if the path is correct.",
    )


def maximum_error(object, num):
    return build(7005, f"Maximum number of {object} is {num}.", {"object": object, "num": num})


def redmine_argument_error(arg_name):
    return build(
        7006,
        f"Argument {arg_name} can not be alerted when children issue exist.",
        {"arg": arg_name},
    )


def error_with_alert_code(resource_type, alert_code, message, detail):
    return {
        "code": alert_code,
        "resource_type": resource_type,
        "message": message,
        "detail": detail,
    }


def github_token_error(arg_name):
    return build(7007, f"{arg_name} should begin with 'ghp_'.", {"arg": arg_name})


def file_not_found(file_name, path):
    return build(
        7008,
        f"The file is not found in provided path.",
        {"file_name": file_name, "path": path},
    )


def gmail_need_apply_apppassword(account):
    return build(
        7009,
        "According to google policy, account needs to apply apppassord to operate SMTP server.",
        {"account": account},
    )


def login_email_error():
    return build(
        7010,
        "SMTP System responses error, please make sure your system, port, account and password are correct.",
    )


# Third party service errors

# 8: Redmine
def redmine_error(response):
    try:
        error_message_list = response.json().get("errors")
        # Parent id error
        if isinstance(error_message_list, list) and error_message_list[0] == "Parent task is invalid":
            return parent_issue_error()
    except Exception:
        pass
    return error_3rd_party_api("Redmine", response)


"""
# 8: Harbor
def harbor_tag_already_exist(tag, repo_name):
    return build(
        8201,
        f"Harbor repository: {repo_name} already have tag: {tag}.",
        {"tag": tag, "repo_name": repo_name},
    )


def no_image_error(repo_name):
    return build(
        8202,
        f"Can not add tag on harbor repository: {repo_name} because it does not has image.",
        {"repo_name": repo_name},
    )


def parent_issue_error():
    return build(
        8101,
        f"Parent issue setting error! Please confirm that the setting issue is not a sub-issue or related issue of this issue.",
    )


def excalidraw_operation_error(msg):
    return build(8102, f"Error occurs during operating excalidraw db, message: {msg}")
"""

# GitLab
def gitlab_error(response):
    return error_3rd_party_api("Gitlab", response)


# 89: General Plugin
def plugin_is_disabled(plugin_name):
    return build(8901, "Plugin Software is disabled.", {"plugin_name": plugin_name})


def plugin_server_not_alive(plugin_name):
    return build(8902, "Plugin Server is not alive.", {"plugin_name": plugin_name})


# 9: Internal errors
def uncaught_exception(exception):
    return build(
        9001,
        "An uncaught exception has occurred.",
        {"type": str(type(exception)), "exception": str(exception)},
    )


def invalid_code_path(detail_message):
    return build(9002, "An invalid code path happens.", {"message": detail_message})


def db_error(detail_message):
    return build(9003, "An unexpected database error has occurred.", {"message": detail_message})


def unknown_error():
    return build(9999, "An unknown internal error has occurred.")


# Exceptions wrapping method_type error information
class DevOpsError(Exception):
    def __init__(self, status_code, message, error=None):
        self.status_code = status_code
        self.message = message
        self.error_value = error

    def unpack_response(self):
        return self.error_value["details"]["response"]


class TemplateError(Exception):
    def __init__(self, status_code, message, error=None):
        self.status_code = status_code
        self.message = message
        self.error_value = error


# 20230118 新增下列程式，因新增取得DEPLOYMENT的API而新增下列錯誤訊息的程式
def get_deployment_failed(**kwargs):
    _FAILED_GET_DEPLOYMENT = "Get deployment failed"
    if len(kwargs) != 0:
        return build(2030, _FAILED_GET_DEPLOYMENT, kwargs)
    else:
        return build(2030, _FAILED_GET_DEPLOYMENT)


# 20230118 新增上列程式，因新增取得DEPLOYMENT的API而新增下列錯誤訊息的程式


# 20230119 為取得 storage class 資訊而新增上下列一段程式
def get_storage_class_failed(**kwargs):
    _FAILED_GET_STORAGE_CLASS = "Get storage class failed"
    if len(kwargs) != 0:
        return build(2040, _FAILED_GET_STORAGE_CLASS, kwargs)
    else:
        return build(2040, _FAILED_GET_STORAGE_CLASS)


def create_storage_class_failed(**kwargs):
    _FAILED_CREATE_STORAGE_CLASS = "Create storage class failed"
    if len(kwargs) != 0:
        return build(2040, _FAILED_CREATE_STORAGE_CLASS, kwargs)
    else:
        return build(2040, _FAILED_CREATE_STORAGE_CLASS)


# 20230119 為取得 storage class 資訊而新增上列一段程式


# 20230201 為變更 storage class disabled 布林值而新增上列一段程式
def change_storage_class_disabled_failed(**kwargs):
    _FAILED_DISABLED_STORAGE_CLASS = "Change storage class disabled failed"
    if len(kwargs) != 0:
        return build(2040, _FAILED_DISABLED_STORAGE_CLASS, kwargs)
    else:
        return build(2040, _FAILED_DISABLED_STORAGE_CLASS)


# 20230201 為變更 storage class disabled 布林值而新增上列一段程式


# 20230202 為取得 persistent volume claim 資訊而新增上列一段程式
def get_persistent_volume_claim_failed(**kwargs):
    _FAILED_GET_PERSISTENT_VOLUME_CLAIM = "Get persistent volume claim failed"
    if len(kwargs) != 0:
        return build(2040, _FAILED_GET_PERSISTENT_VOLUME_CLAIM, kwargs)
    else:
        return build(2040, _FAILED_GET_PERSISTENT_VOLUME_CLAIM)


# 20230202 為取得 persistent volume claim 資訊而新增上列一段程式


# 20230215 為新增 application_header table 而新增下列一段程式
def create_application_header_failed(cluster_name=None, registry_name=None, namespace=None, application_name=None):
    _FAILED_CREATE_APPLICATION_HEADER = "Create deploy application header failed"
    if cluster_name is None or namespace is None or application_name is None:
        return build(2041, _FAILED_CREATE_APPLICATION_HEADER)
    else:
        return build(
            2041,
            _FAILED_CREATE_APPLICATION_HEADER,
            {
                "cluster_name": cluster_name,
                "registry_name": registry_name,
                "application_name": application_name,
                "namespace": namespace,
            },
        )


def get_application_header_failed(**kwargs):
    _FAILED_GET_APPLICATION_HEADER = "Get application header failed"
    if len(kwargs) != 0:
        return build(2042, _FAILED_GET_APPLICATION_HEADER, kwargs)
    else:
        return build(2042, _FAILED_GET_APPLICATION_HEADER)


def update_application_header_failed(**kwargs):
    _FAILED_UPDATE_APPLICATION_HEADER = "Update application header failed"
    if len(kwargs) != 0:
        return build(2043, _FAILED_UPDATE_APPLICATION_HEADER, kwargs)
    else:
        return build(2043, _FAILED_UPDATE_APPLICATION_HEADER)


def delete_application_header_failed(app_header_id):
    return build(2044, "Delete application header failed", {"app_header_id", app_header_id})


# 20230215 為新增 application_header table 而新增上列一段程式
