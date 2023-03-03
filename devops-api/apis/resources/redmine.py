import time
from io import BytesIO

import requests
# import yaml
from flask import send_file
from flask_jwt_extended import jwt_required, get_jwt_identity
from flask_restful import reqparse, Resource

import config
import nexus
import resources.apiError as apiError
import util as util
from accessories import redmine_lib
from resources.apiError import DevOpsError
from resources.logger import logger
from . import role
import json
from urllib.parse import quote_plus
from model import db, SystemParameter, UserPluginRelation


"""
1. rm_get_or_create_configmap
    - Find another way to store secret
2. deployer_node_ip
3. rm_put_mail_setting
"""


DEFAULT_MAIL_CONFIG = {
    "smtp_settings": {
        "enable_starttls_auto": "smtp_enable_starttls_auto",
        "address": "smtp_address",
        "port": "smtp_port",
        "authentication": "smtp_authentication",
        "domain": "smtp_domain",
        "user_name": "smtp_username",
        "password": "smtp_password",
    },
    "emission_email_address": "smtp_username",
}


def get_redmine_obj(operator_id=None, plan_user_id=None):
    if plan_user_id is not None:
        return Redmine(operator_id=plan_user_id)
    else:
        operator = UserPluginRelation.query.filter_by(user_id=operator_id).first()
        operator_id = operator.plan_user_id if operator is not None else None
        return Redmine(operator_id=operator_id)


class Redmine:
    def __init__(self, operator_id=None):
        self.key_generated = 0.0
        self.last_operator_id = None
        self.redmine_key = None
        self.versions = None
        self.issues = None
        self.closed_status = []
        self.redmine_config_name = "redmine-config"
        self.operator_id = operator_id

    def __api_request(self, method, path, headers=None, params=None, data=None, resp_format=".json"):
        logger.info(f"operator_id:{self.operator_id}")
        self.__key_check()
        if headers is None:
            headers = {}
        if params is None:
            params = {}
        if "Content-Type" not in headers:
            headers["Content-Type"] = "application/json"

        url = f"{config.get('REDMINE_INTERNAL_BASE_URL')}{path}{resp_format}"
        params["key"] = self.redmine_key
        output = util.api_request(method, url, headers, params, data)

        if resp_format != "":
            logger.debug(
                "redmine api {0} {1}, params={2}, body={5}, response={3} {4}".format(
                    method, url, params.__str__(), output.status_code, output.text, data
                )
            )
        if int(output.status_code / 100) != 2:
            logger.debug(
                "redmine api {0} {1}, params={2}, body={5}, response={3} {4}".format(
                    method, url, params.__str__(), output.status_code, output.text, data
                )
            )
            raise apiError.DevOpsError(
                output.status_code,
                "Got non-2xx response from Redmine.",
                apiError.redmine_error(output),
            )
        return output

    def __api_get(self, path, params=None, headers=None, resp_format=".json"):
        return self.__api_request("GET", path, params=params, headers=headers, resp_format=resp_format)

    def __api_post(self, path, params=None, headers=None, data=None, resp_format=".json"):
        return self.__api_request(
            "POST",
            path,
            headers=headers,
            data=data,
            params=params,
            resp_format=resp_format,
        )

    def __api_put(self, path, params=None, headers=None, data=None, resp_format=".json"):
        return self.__api_request(
            "PUT",
            path,
            headers=headers,
            data=data,
            params=params,
            resp_format=resp_format,
        )

    def __api_delete(self, path, params=None, headers=None, resp_format=".json"):
        return self.__api_request("DELETE", path, params=params, headers=headers, resp_format=resp_format)

    def __key_check(self):
        # Check if key expires first, seems to expire in 2 hours in default?
        if self.redmine_key is None or time.time() - self.key_generated >= 7200:
            self.__refresh_key()

    def __refresh_key(self):
        protocol = "https" if config.get("REDMINE_INTERNAL_BASE_URL")[:5] == "https" else "http"
        host = config.get("REDMINE_INTERNAL_BASE_URL")[len(protocol + "://") :]
        redmine_pwd = quote_plus(config.get('REDMINE_ADMIN_PASSWORD'))
        if self.operator_id is None:
            # get redmine_key
            url = f"{protocol}://{config.get('REDMINE_ADMIN_ACCOUNT')}:{redmine_pwd}@{host}/users/current.json"
            self.key_generated = time.time()
        else:
            url = (
                f"{protocol}://{config.get('REDMINE_ADMIN_ACCOUNT')}"
                f":{quote_plus(config.get('REDMINE_ADMIN_PASSWORD'))}"
                f"@{host}/users/{self.operator_id}.json"
            )
        output = requests.get(url, headers={"Content-Type": "application/json"}, verify=False)
        self.redmine_key = output.json()["user"]["api_key"]

    # --------------- Normal methods ---------------

    def paging(self, key, page=100, params=None, with_total_count=False):
        if params is None:
            params = {}
        offset = 0
        ret = []
        path = "/{0}".format(key)
        params["limit"] = page
        while True:
            issue_json = self.__api_get(path=path, params=params).json()
            total_count = issue_json["total_count"]
            res = issue_json.get(key)
            ret.extend(res)
            if len(res) == 100:
                offset += 100
                params["offset"] = offset
            else:
                break
        if not with_total_count:
            return ret
        return ret, total_count

    def rm_list_projects(self):
        return self.paging("projects")

    def rm_get_project(self, plan_project_id):
        return self.__api_get("/projects/{0}".format(plan_project_id)).json()

    def rm_create_project(self, args):
        param = {
            "project": {
                "name": args.get("display"),
                "identifier": args.get("name"),
                "description": args.get("description", ""),
                "is_public": False,
            }
        }
        if args.get("parent_plan_project_id", None) is not None:
            param["project"]["parent_id"] = args.get("parent_plan_project_id")

        return self.__api_post("/projects", data=param).json()

    def rm_update_project(self, plan_project_id, args):
        xml_body = """<?xml version="1.0" encoding="UTF-8"?>        
                        <project>
                        <name>{0}</name>
                        <description>{1}</description>
                        </project>""".format(
            args["display"],
            args["description"],
        )
        if args.get("parent_plan_project_id", None) is not None:
            xml_body = """<?xml version="1.0" encoding="UTF-8"?>        
                            <project>
                            <name>{0}</name>
                            <description>{1}</description>
                            <parent_id>{2}</parent_id>
                            </project>""".format(
                args["display"], args["description"], args["parent_plan_project_id"]
            )

        headers = {"Content-Type": "application/xml"}
        return self.__api_put(
            "/projects/{0}".format(plan_project_id),
            headers=headers,
            data=xml_body.encode("utf-8"),
        )

    def rm_delete_project(self, plan_project_id):
        return self.__api_delete("/projects/{0}".format(plan_project_id))

    # Can not use until redmine version to 5.0.0
    def rm_archive_project(self, plan_project_id, disabled):
        status = "archive" if disabled else "unarchive"
        path = f"/projects/{plan_project_id}/{status}.xml"
        headers = {"Content-Type": "application/xml"}
        return self.__api_put(path, headers=headers).json()

    def rm_list_issues(self, paging=100, params=None):
        if params is None:
            params = {"status_id": "*"}
        if params.get("limit") is not None:
            issue_info = self.__api_get("/issues", params=params).json()
            return issue_info["issues"], issue_info["total_count"]
        issues, total_count = self.paging("issues", paging, params, with_total_count=True)
        return issues, total_count

    def rm_get_issues_by_user(self, user_id):
        params = {"assigned_to_id": user_id, "status_id": "*"}
        return self.paging("issues", 100, params)

    def rm_get_issues_by_project(self, plan_project_id, args=None):
        if args is not None and "fixed_version_id" in args and args["fixed_version_id"] is not None:
            params = {
                "project_id": plan_project_id,
                "status_id": "*",
                "fixed_version_id": args["fixed_version_id"],
            }
        elif args is not None and "tracker_id" in args and args["tracker_id"] is not None:
            params = {
                "project_id": plan_project_id,
                "status_id": "*",
                "tracker_id": args["tracker_id"],
                "include": "relations",
            }
        else:
            params = {"project_id": plan_project_id, "status_id": "*"}
        return self.paging("issues", 100, params)

    def rm_get_issues_by_project_and_user(self, user_id, plan_project_id):
        params = {
            "assigned_to_id": user_id,
            "project_id": plan_project_id,
            "status_id": "*",
        }
        return self.paging("issues", 100, params)

    def rm_get_issue(self, issue_id, journals=True):
        if journals is False:
            params = {}
        else:
            params = {"include": "children,attachments,relations,changesets,journals,watchers"}
        output = self.__api_get("/issues/{0}".format(issue_id), params=params)
        return output.json()["issue"]

    def rm_get_statistics(self, params):
        if "status_id" not in params:
            params["status_id"] = "*"
        return self.__api_get("/issues", params=params).json()

    def rm_create_issue(self, args):
        return self.__api_post("/issues", data={"issue": args}).json()

    def rm_update_issue(self, issue_id, args):
        return self.__api_put("/issues/{0}".format(issue_id), data={"issue": args})

    def rm_delete_issue(self, issue_id):
        params = {"include": "journals,attachment"}
        return self.__api_delete("/issues/{0}".format(issue_id), params=params)

    def rm_get_issue_status(self):
        return self.__api_get("/issue_statuses").json()

    def rm_get_priority(self):
        return self.__api_get("/enumerations/issue_priorities").json()

    def rm_get_trackers(self):
        return self.__api_get("/trackers").json()

    def rm_create_user(self, args, user_source_password, is_admin=False):
        params = {
            "user": {
                "login": args["login"],
                "firstname": "#",
                "lastname": args["name"],
                "mail": args["email"],
                "password": user_source_password,
            }
        }
        if is_admin:
            params["user"]["admin"] = True
        return self.__api_post("/users", data=params).json()

    def rm_update_user_active(self, plan_user_id, status_id):
        param = {"user": {"status": status_id}}
        return self.__api_put(f"/users/{plan_user_id}", data=param)

    def rm_update_password(self, plan_user_id, new_pwd):
        param = {"user": {"password": new_pwd}}
        return self.__api_put("/users/{0}".format(plan_user_id), data=param)

    def rm_get_user_list(self, args):
        return self.__api_get("/users", params=args).json()

    def rm_delete_user(self, redmine_user_id):
        return self.__api_delete("/users/{0}".format(redmine_user_id))

    def rm_get_wiki_list(self, project_id):
        return self.__api_get("/projects/{0}/wiki/index".format(project_id)).json()

    def rm_get_wiki(self, project_id, wiki_name):
        return self.__api_get("/projects/{0}/wiki/{1}".format(project_id, wiki_name)).json()

    def rm_put_wiki(self, project_id, wiki_name, args):
        param = {"wiki_page": {"text": args["wiki_text"]}}
        return self.__api_put("/projects/{0}/wiki/{1}".format(project_id, wiki_name), data=param)

    def rm_delete_wiki(self, project_id, wiki_name):
        return self.__api_delete("/projects/{0}/wiki/{1}".format(project_id, wiki_name))

    # Get Redmine Version List
    def rm_get_version_list(self, project_id):
        return self.__api_get("/projects/{0}/versions".format(project_id)).json()

    # Create Redmine Version
    def rm_post_version(self, project_id, args):
        return self.__api_post("/projects/{0}/versions".format(project_id), data=args).json()

    def rm_get_version(self, version_id):
        return self.__api_get("/versions/{0}".format(version_id)).json()

    def rm_put_version(self, version_id, args):
        return self.__api_put("/versions/{0}".format(version_id), data=args)

    def rm_delete_version(self, version_id):
        return self.__api_delete("/versions/{0}".format(version_id))

    def rm_create_memberships(self, project_id, user_id, role_id):
        param = {"membership": {"user_id": user_id, "role_ids": [role_id]}}
        return self.__api_post("/projects/{0}/memberships".format(project_id), data=param)

    def rm_delete_memberships(self, membership_id):
        return self.__api_delete("/memberships/{0}".format(membership_id))

    def rm_get_memberships_list(self, project_id):
        return self.__api_get("/projects/{0}/memberships".format(project_id)).json()

    def rm_upload(self, args):
        files = args.pop("upload_files", None) if "upload_files" in args else None
        if files is None:
            return None
        ret = []
        for file in files:
            headers = {"Content-Type": "application/octet-stream"}
            res = self.__api_post("/uploads", data=file, headers=headers)
            if res.status_code != 201:
                raise DevOpsError(
                    res.status_code,
                    "Error while uploading to redmine",
                    error=apiError.redmine_error(res.text),
                )
            token = res.json().get("upload").get("token")
            filename = file.filename
            ret.append(
                {
                    "token": token,
                    "filename": filename,
                    "content_type": file.content_type,
                }
            )
        """
        if 'upload_description' in args:
            ret['description'] = args['upload_description']
            del args['upload_description']
        """
        return ret

    def rm_upload_to_project(self, plan_project_id, args):
        if args.get("file"):
            file = args["file"]
        #     check_upload_size(file)
        headers = {"Content-Type": "application/octet-stream"}
        res = self.__api_post("/uploads", data=file, headers=headers)
        token = res.json().get("upload").get("token")
        filename = args["filename"]
        if filename is None:
            filename = file.filename
        params = {"token": token, "filename": filename}
        if args.get("description") is not None:
            params["description"] = args["description"]
        if args.get("version_id") is not None:
            params["version_id"] = args["version_id"]
        data = {"file": params}
        res = self.__api_post("/projects/%d/files" % plan_project_id, data=data)
        if res.status_code == 204:
            return util.respond(201, None)
        else:
            raise DevOpsError(
                res.status_code,
                "Error while adding the file to redmine",
                error=apiError.redmine_error(res.text),
            )

    def rm_list_file(self, plan_project_id):
        return self.__api_get("/projects/%d/files" % plan_project_id).json()

    def rm_download_attachment(self, args):
        a_id = args["id"]
        filename = args["filename"]
        try:
            r = self.__api_get("/attachments/download/{0}/{1}".format(a_id, filename), resp_format="")
            file_obj = BytesIO(r.content)
            return send_file(file_obj, attachment_filename=filename)
        except Exception as e:
            raise DevOpsError(
                500,
                "Error when downloading an attachment.",
                error=apiError.uncaught_exception(e),
            )

    def rm_delete_attachment(self, attachment_id):
        output = self.__api_delete("/attachments/{0}".format(attachment_id))
        status_code = output.status_code
        if status_code == 204:
            return util.success()
        elif status_code == 404:
            return util.respond(200, "File is already deleted.")
        else:
            raise DevOpsError(
                status_code,
                "Error while deleting attachments.",
                error=apiError.redmine_error(output),
            )

    def rm_list_issues_by_versions_and_closed(self, plan_project_id, versions, closed_statuses):
        self.versions = {}
        for version in versions:
            self.versions[version] = {
                "id": str(version),
                "name": "",
                "closed": 0,
                "unclosed": 0,
                "issues": [],
            }
            params = {
                "project_id": plan_project_id,
                "fixed_version_id": version,
                "status_id": "*",
            }
            issues = self.paging("issues", 100, params)
            self.analysis_issue_type_by_versions(issues, closed_statuses)
        return list(self.versions.values())

    def analysis_issue_type_by_versions(self, issues, closed_statuses):
        for issue in issues:
            version_id = str(issue["fixed_version"]["id"])
            if version_id not in self.versions:
                break
            if self.versions[version_id]["name"] == "":
                self.versions[version_id]["name"] = issue["fixed_version"]["name"]
            if issue["closed_on"] != "" and int(issue["status"]["id"]) in closed_statuses:
                self.versions[version_id]["closed"] += 1
            else:
                self.versions[version_id]["unclosed"] += 1
            self.versions[version_id]["issues"].append(issue)

    def get_closed_status(self, statuses):
        for status in statuses:
            if status["is_closed"] is True:
                self.closed_status.append(status["id"])
        return self.closed_status

    def rm_get_or_create_configmap(self):
        pass
        # configs = kubernetesClient.list_namespace_configmap("default")
        # if any(self.redmine_config_name == config.get("name") for config in configs) is False:
        #     # Don't has redmine config, create one.
        #     with open(f"k8s-yaml/redmine-config.yaml") as file:
        #         redmine_config_json = yaml.safe_load(file)["data"]
        #         kubernetesClient.create_namespace_configmap("default", self.redmine_config_name, redmine_config_json)
        # return yaml.safe_load(
        #     kubernetesClient.read_namespace_configmap("default", self.redmine_config_name)["configuration.yml"]
        # )

    def rm_get_mail_setting(self):
        rm_con_json = self.rm_get_or_create_configmap()
        del rm_con_json["default"]["email_delivery"]["delivery_method"]
        return rm_con_json["default"]["email_delivery"]

    def pre_check_mail_alive(self, rm_put_mail_dict, emissoin_email_address):
        from resources.mail import Mail

        Mail.check_mail_server(
            rm_put_mail_dict.get("address"),
            rm_put_mail_dict.get("port"),
            rm_put_mail_dict.get("user_name"),
            rm_put_mail_dict.get("password"),
            emissoin_email_address,
        )
        self.read_mail_unclose_message()

    def read_mail_unclose_message(self, message="SMTP is back."):
        from resources.notification_message import (
            close_notification_message,
            get_unclose_notification_message,
            create_notification_message,
        )

        not_alive_messages = get_unclose_notification_message(1101)
        if not_alive_messages is not None and len(not_alive_messages) > 0:
            for not_alive_message in not_alive_messages:
                close_notification_message(not_alive_message["id"])
            create_notification_message(
                {
                    "alert_level": 1,
                    "title": "SMTP is back.",
                    "message": message,
                    "type_ids": [4],
                    "type_parameters": {"role_ids": [5]},
                },
                user_id=1,
            )

    # def rm_put_mail_setting(self, rm_put_mail_dict):
    #     optional_parameters = ["ssl", "user_name", "password"]
    #     rm_configmap_dict = self.rm_get_or_create_configmap()
    #     rm_put_mail_dict = {k: v for k, v in rm_put_mail_dict.items() if k not in optional_parameters or v != ""}
    #     rm_configmap_dict["default"]["email_delivery"]["delivery_method"] = ":smtp"
    #     rm_configmap_dict["default"]["email_delivery"]["smtp_settings"] = rm_put_mail_dict
    #     out = {}
        # out["configuration.yml"] = str(yaml.dump(rm_configmap_dict))
        # kubernetesClient.put_namespace_configmap("default", self.redmine_config_name, out)
        # kubernetesClient.redeploy_deployment("default", "redmine")

    @staticmethod
    def rm_build_external_link(path):
        return f"{config.get('REDMINE_EXTERNAL_BASE_URL')}{path}"

    def rm_update_user_name(self, plan_user_id, new_name):
        user = redmine_lib.redmine.user.get(plan_user_id)
        setattr(user, "lastname", new_name)
        user.save()

    def rm_update_email(self, plan_user_id, new_email):
        user = redmine_lib.redmine.user.get(plan_user_id)
        setattr(user, "mail", new_email)
        user.save()

    def rm_get_or_set_emission_email_address(self, rm_emission_email_address):
        deployer_node_ip = config.get("DEPLOYER_NODE_IP")
        # if deployer_node_ip is None:
        #     # get the k8s cluster the oldest node ip
        #     deployer_node_ip = kubernetesClient.get_the_oldest_node()[0]

        if rm_emission_email_address is not None:
            bs4 = util.base64encode(rm_emission_email_address)
            pl = f"~/deploy-devops/redmine/redmine-tools.pl mail_from {bs4}"
        else:
            pl = "~/deploy-devops/redmine/redmine-tools.pl mail_from"

        output_str, error_str = util.ssh_to_node_by_key(pl, deployer_node_ip)
        if not error_str:
            return json.loads(output_str)


redmine = Redmine()


def row_to_dict(row):
    if row is None:
        return {
            "name": "mail_config",
            "emission_email_address": "",
            "smtp_settings": {},
            "active": False,
        }
    return {key: getattr(row, key) for key in type(row).__table__.columns.keys()}


def get_mail_config():
    mail_config = SystemParameter.query.filter_by(name="mail_config").first()
    ret = row_to_dict(mail_config)
    ret.update(ret.pop("value", {}))
    return ret

'''
def update_mail_config(args):
    args = {k: v for k, v in args.items() if v is not None}
    args.update(args.pop("redmine_mail", {}))
    args["emission_email_address"] = args.pop("emissoin_email_address", args.get("emission_email_address"))
    active, temp_save = args.pop("active", None), args.pop("temp_save", None)

    mail_config = SystemParameter.query.filter_by(name="mail_config").first()
    value, old_active = mail_config.value, mail_config.active

    if active is not None:
        if not active:
            args = DEFAULT_MAIL_CONFIG
            redmine.read_mail_unclose_message("Close SMTP alive alert, because SMTP function has been inactivated.")
        else:
            redmine.pre_check_mail_alive(args.get("smtp_settings") or {}, args.get("emission_email_address"))
            mail_config.value = value | args
        mail_config.active = active
        db.session.commit()

        try:
            if args.get("emission_email_address") is not None:
                redmine.rm_get_or_set_emission_email_address(args["emission_email_address"])
            if args.get("smtp_settings") is not None:
                redmine.rm_put_mail_setting(args["smtp_settings"])
        except:
            # Roll back if fail to update redmine config.
            mail_config.active = old_active
            mail_config.value = value
            db.session.commit()
    elif not old_active and temp_save is not None:
        mail_config.value = value | args
        db.session.commit()

'''
# --------------------- Resources ---------------------


class RedmineFile(Resource):
    @jwt_required()
    def get(self):
        parser = reqparse.RequestParser()
        parser.add_argument("id", type=int, location="args")
        parser.add_argument("filename", type=str, location="args")
        parser.add_argument("project_id", type=int, required=True, location="args")
        args = parser.parse_args()
        role.require_in_project(args["project_id"], "Error while download redmine file.")
        return redmine.rm_download_attachment(args)

    @jwt_required()
    def delete(self, file_id):
        personal_redmine_obj = get_redmine_obj(operator_id=get_jwt_identity()["user_id"])
        return personal_redmine_obj.rm_delete_attachment(file_id)


class RedmineMail(Resource):
    @jwt_required()
    def get(self):
        role.require_admin()
        return util.success(get_mail_config())

    @jwt_required()
    def put(self):
        role.require_admin()
        parser = reqparse.RequestParser()
        parser.add_argument("redmine_mail", type=dict)
        parser.add_argument("emission_email_address", type=str)
        parser.add_argument("active", type=bool)
        parser.add_argument("temp_save", type=bool)
        args = parser.parse_args()
        return util.success ('successful')
        # return util.success(update_mail_config(args))


class RedmineMailActive(Resource):
    @jwt_required()
    def get(self):
        return util.success(get_mail_config().get("active", False))


class RedmineRelease:
    @jwt_required()
    def check_redemine_release(self, targets, versions, main_version=None):
        output = {
            "check": True,
            "info": "",
            "errors": {},
            "versions_status": {"pass": [], "failed": []},
            "failed_name": [],
            "issues": [],
            "unclosed_issues": [],
            "versions": [],
        }
        for target in targets:
            version_id = str(target["id"])
            output["issues"] += target["issues"]
            output["versions"].append(int(target["id"]))
            if version_id == main_version:
                output["errors"] = {
                    "id": version_id,
                    "name": versions[version_id]["name"],
                }
            if target["unclosed"] != 0:
                output["check"] = False
                output["versions_status"]["failed"].append({"id": version_id, "name": versions[version_id]["name"]})
                output["failed_name"].append(versions[version_id]["name"])
                output["unclosed_issues"] += target["issues"]
            else:
                output["versions_status"]["pass"].append({"id": version_id, "name": versions[version_id]["name"]})
        if len(output["failed_name"]) > 0:
            output["info"] = "Issue is not closed in version {0} in redmine".format(
                " ".join(map(str, output["failed_name"]))
            )
        return output


rm_release = RedmineRelease()
