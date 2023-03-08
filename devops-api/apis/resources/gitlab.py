import base64
import json
import os
import re
from datetime import datetime, timedelta
from pathlib import Path

from typing import Any, Union
from github import Github
from github.GithubException import BadCredentialsException

import requests
from flask_jwt_extended import get_jwt_identity, jwt_required
from flask_restful import Resource, reqparse
from gitlab import Gitlab, exceptions
from gitlab.v4 import objects
from sqlalchemy.exc import NoResultFound
from accessories.redmine_lib import redmine
from sqlalchemy.exc import IntegrityError
from sqlalchemy import desc

from enums.gitlab_enums import FileActions
from sqlalchemy.orm import joinedload
import config
import model
import nexus
import util as util
from model import (
    GitCommitNumberEachDays,
    db,
    SystemParameter,
    Project,
    ProjectPluginRelation,
    GitlabSourceCodeLens,
)
from resources import apiError, role
from resources.apiError import DevOpsError
from resources.logger import logger
from resources.project_relation import (
    get_all_fathers_project,
    get_all_sons_project,
    get_root_project_id,
)
from flask_apispec import marshal_with, doc, use_kwargs
from urls import route_model
from flask_apispec.views import MethodResource
from resources.notification_message import (
    close_notification_message,
    create_notification_message,
    get_unread_notification_message_list,
)


GITLAB_NOTFOUND = exceptions
GITLAB_DATETIME_FORMAT = "%Y-%m-%dT%H:%M:%S"
iiidevops_system_group = ["iiidevops-templates", "local-templates", "iiidevops-catalog"]

"""
1. Gitlab domain name might need to write /etc/hosts
    - 97: GitLab find another way to get cluster ip
2. Gitlab adjust ip / domain mode(change k8s ingress)
"""


def get_nexus_project_id(repo_id):
    row = model.ProjectPluginRelation.query.filter_by(git_repository_id=repo_id).first()
    if row:
        return row.project_id
    else:
        return -1


def get_nexus_repo_id(project_id):
    row = model.ProjectPluginRelation.query.filter_by(project_id=project_id).first()
    if row:
        return row.git_repository_id
    else:
        return -1


def get_repo_url(project_id):
    row = model.Project.query.filter_by(id=project_id).one()
    return row.http_url


def commit_id_to_url(project_id, commit_id):
    return f"{get_repo_url(project_id)[0:-4]}/-/commit/{commit_id}"


# May throws NoResultFound
def get_repository_id(project_id):
    return nexus.nx_get_project_plugin_relation(project_id).git_repository_id


class GitLab(object):
    private_token = None

    def __init__(self):
        # Wirte gitlab domain to /etc/host
        if config.get("GITLAB_DOMAIN_NAME") is not None:
            cluster_ip = ""
            # namespaces = ApiK8sClient().list_namespaced_service("default")
            # for nsp in namespaces.items:
            #     if nsp.metadata.name == "gitlab-service":
            #         cluster_ip = nsp.spec.cluster_ip
            cmd = f'echo "$(sed /$GITLAB_DOMAIN_NAME/d /etc/hosts)" > /etc/hosts; echo "{cluster_ip} $GITLAB_DOMAIN_NAME" >> /etc/hosts'
            os.system(cmd)

        if config.get("GITLAB_API_VERSION") == "v3":
            # get gitlab admin token
            url = f'{config.get("GITLAB_BASE_URL")}/api/v3/session'
            param = {
                "login": config.get("GITLAB_ADMIN_ACCOUNT"),
                "password": config.get("GITLAB_ADMIN_PASSWORD"),
            }
            output = requests.post(
                url,
                data=json.dumps(param),
                headers={"Content-Type": "application/json"},
                verify=False,
            )
            self.private_token = output.json()["private_token"]
        else:
            self.private_token = config.get("GITLAB_PRIVATE_TOKEN")
        logger.info(config.get("GITLAB_BASE_URL"))
        self.gl = Gitlab(
            config.get("GITLAB_BASE_URL"),
            private_token=self.private_token,
            ssl_verify=False,
        )

    @staticmethod
    def gl_get_nexus_project_id(repository_id):
        project_id = get_nexus_project_id(repository_id)
        if project_id > 0:
            return util.success(project_id)
        else:
            raise DevOpsError(
                404,
                "Error when getting project id.",
                error=apiError.repository_id_not_found(repository_id),
            )

    @staticmethod
    def gl_get_project_id_from_url(repository_url):
        row = model.Project.query.filter_by(http_url=repository_url).one()
        project_id = row.id
        repository_id = nexus.nx_get_repository_id(project_id)
        return {"project_id": project_id, "repository_id": repository_id}

    def __api_request(self, method, path, headers=None, params=None, data=None):
        if headers is None:
            headers = {}
        if params is None:
            params = {}
        if "Content-Type" not in headers:
            headers["Content-Type"] = "application/json"

        url = (
            f'{config.get("GITLAB_BASE_URL")}/api/'
            f'{config.get("GITLAB_API_VERSION")}{path}'
            f"?private_token={self.private_token}"
        )

        output = util.api_request(method, url, headers, params, data)

        logger.debug(
            f"gitlab api {method} {url}, params={params.__str__()}, body={data}, response={output.status_code} {output.text}"
        )
        if int(output.status_code / 100) != 2:
            raise apiError.DevOpsError(
                output.status_code,
                "Got non-2xx response from Gitlab.",
                apiError.gitlab_error(output),
            )
        return output

    def __api_get(self, path, params=None, headers=None):
        return self.__api_request("GET", path, params=params, headers=headers)

    def __api_post(self, path, params=None, headers=None, data=None):
        return self.__api_request("POST", path, headers=headers, data=data, params=params)

    def __api_put(self, path, params=None, headers=None, data=None):
        return self.__api_request("PUT", path, headers=headers, data=data, params=params)

    def __api_delete(self, path, params=None, headers=None):
        return self.__api_request("DELETE", path, params=params, headers=headers)

    def __gl_timezone_to_utc(self, gl_datetime_str):
        return datetime.strptime(gl_datetime_str, "%Y-%m-%dT%H:%M:%S.%f%z").isoformat()

    def gl_get_all_project(self):
        return self.gl.projects.list(all=True)

    def gl_create_project(self, args):
        return self.__api_post(
            "/projects",
            params={"name": args["name"], "description": args["description"]},
        ).json()

    def gl_get_project(self, repo_id):
        return self.__api_get(f"/projects/{repo_id}", {"statistics": "true"}).json()

    def gl_update_project(self, repo_id, description):
        params = {"description": description}
        return self.__api_put(f"/projects/{repo_id}", params=params)

    def gl_delete_project(self, repo_id):
        return self.__api_delete(f"/projects/{repo_id}")

    def gl_create_user(self, args, user_source_password, is_admin=False):
        data = {
            "name": args["name"],
            "email": args["email"],
            "username": args["login"],
            "password": user_source_password,
            "skip_confirmation": True,
        }
        if is_admin:
            data["admin"] = True
        return self.__api_post("/users", data=data).json()

    def gl_update_password(self, repository_user_id, new_pwd):
        return self.__api_put(
            f"/users/{repository_user_id}",
            params={"password": new_pwd, "skip_reconfirmation": True},
        )

    def gl_update_email(self, repository_user_id, new_email):
        return self.__api_put(
            f"/users/{repository_user_id}",
            params={"email": new_email, "skip_reconfirmation": True},
        )

    def gl_update_user_name(self, repository_user_id, new_name):
        return self.__api_put(
            f"/users/{repository_user_id}",
            params={"name": new_name, "skip_reconfirmation": True},
        )

    def gl_update_user_state(self, repository_user_id, block_status):
        if block_status:
            return self.__api_post(f"/users/{repository_user_id}/block")
        else:
            return self.__api_post(f"/users/{repository_user_id}/unblock")

    def gl_get_user_list(self, args):
        return self.__api_get("/users", params=args)

    def gl_project_list_member(self, project_id, args):
        return self.__api_get(f"/projects/{project_id}/members", params=args)

    def gl_project_add_member(self, project_id, user_id):
        params = {
            "user_id": user_id,
            "access_level": 40,
        }
        return self.__api_post(f"/projects/{project_id}/members", params=params)

    def gl_project_delete_member(self, project_id, user_id):
        return self.__api_delete(f"/projects/{project_id}/members/{user_id}")

    def gl_delete_user(self, gitlab_user_id):
        return self.__api_delete(f"/users/{gitlab_user_id}")

    def gl_get_user_email(self, gitlab_user_id):
        return self.__api_get(f"/users/{gitlab_user_id}/emails")

    def gl_delete_user_email(self, gitlab_user_id, gitlab_email_id):
        return self.__api_delete(f"/users/{gitlab_user_id}/emails/{gitlab_email_id}")

    def gl_count_branches(self, repo_id):
        output = self.__api_get(f"/projects/{repo_id}/repository/branches")
        return len(output.json())

    def gl_create_rancher_pipeline_yaml(self, repo_id, args, method):
        path = f'/projects/{repo_id}/repository/files/{args["file_path"]}'
        params = {}
        for key in [
            "branch",
            "start_branch",
            "encoding",
            "author_email",
            "author_name",
            "content",
            "commit_message",
        ]:
            params[key] = args[key]
        return self.__api_request(method, path, params=params)

    def gl_get_project_file_for_pipeline(self, project_id, args):
        return self.__api_get(
            f'/projects/{project_id}/repository/files/{args["file_path"]}',
            params={"ref": args["branch"]},
        )

    def gl_get_branches(self, repo_id):
        gl_total_branch_list = []
        total_pages = 1
        i = 1
        while i <= total_pages:
            params = {"per_page": 25, "page": i}
            output = self.__api_get(f"/projects/{repo_id}/repository/branches", params=params)
            if output.status_code != 200:
                raise DevOpsError(
                    output.status_code,
                    "Error while getting git branches",
                    error=apiError.gitlab_error(output),
                )
            gl_total_branch_list.extend(output.json())
            total_pages = int(output.headers.get("x-total-pages", total_pages))
            i += 1

        branch_list = []
        for branch_info in gl_total_branch_list:
            branch = {
                "name": branch_info["name"],
                "last_commit_message": branch_info["commit"]["message"],
                "last_commit_time": branch_info["commit"]["committed_date"],
                "short_id": branch_info["commit"]["short_id"][0:7],
                "id": branch_info["commit"]["id"],
                "commit_url": commit_id_to_url(get_nexus_project_id(repo_id), branch_info["commit"]["short_id"]),
            }
            branch_list.append(branch)
        return branch_list

    def gl_create_branch(self, repo_id, args):
        output = self.__api_post(
            f"/projects/{repo_id}/repository/branches",
            params={"branch": args["branch"], "ref": args["ref"]},
        )
        return output.json()

    def gl_get_branch(self, repo_id, branch):
        output = self.__api_get(f"/projects/{repo_id}/repository/branches/{branch}")
        return output.json()

    def gl_delete_branch(self, project_id, branch):
        output = self.__api_delete(f"/projects/{project_id}/repository/branches/{branch}")
        return output

    def gl_list_protect_branches(self, project_id):
        output = self.__api_get(f"/projects/{project_id}/protected_branches")
        return output.json()

    def gl_unprotect_branch(self, project_id, branch):
        output = self.__api_delete(f"/projects/{project_id}/protected_branches/{branch}")
        return output

    def gl_get_repository_tree(self, repo_id, branch):
        output = self.__api_get(f"/projects/{repo_id}/repository/tree", params={"ref": branch})
        return {"file_list": output.json()}

    def gl_get_storage_usage(self, repo_id):
        project_detail = self.gl_get_project(repo_id)
        usage_info = {"title": "GitLab", "used": {}, "quota": {}}
        usage_info["used"]["value"] = project_detail["statistics"]["storage_size"]
        usage_info["used"]["unit"] = ""
        usage_info["quota"]["value"] = "1073741824"
        usage_info["quota"]["unit"] = ""
        return usage_info

    def __edit_file_exec(self, method, repo_id, args):
        path = f'/projects/{repo_id}/repository/files/{args["file_path"]}'
        params = {}
        keys = [
            "branch",
            "start_branch",
            "encoding",
            "author_email",
            "author_name",
            "content",
            "commit_message",
        ]
        for k in keys:
            params[k] = args[k]

        if method.upper() == "POST":
            output = self.__api_post(path, params=params)
        elif method.upper() == "PUT":
            output = self.__api_put(path, params=params)
        else:
            raise DevOpsError(
                500,
                "Only accept POST and PUT.",
                error=apiError.invalid_code_path("Only PUT and POST is allowed, but" f"{method} provided."),
            )

        if output.status_code == 201:
            return util.success(
                {
                    "file_path": output.json()["file_path"],
                    "branch_name": output.json()["branch"],
                }
            )
        else:
            raise DevOpsError(
                output.status_code,
                "Error when adding gitlab file.",
                error=apiError.gitlab_error(output),
            )

    def gl_add_file(self, repo_id, args):
        return self.__edit_file_exec("POST", repo_id, args)

    def gl_update_file(self, repo_id, args):
        return self.__edit_file_exec("PUT", repo_id, args)

    def gl_get_file(self, repo_id, branch, file_path):
        output = self.__api_get(f"/projects/{repo_id}/repository/files/{file_path}", params={"ref": branch})
        return util.success(
            {
                "file_name": output.json()["file_name"],
                "file_path": output.json()["file_path"],
                "size": output.json()["size"],
                "encoding": output.json()["encoding"],
                "content": output.json()["content"],
                "content_sha256": output.json()["content_sha256"],
                "ref": output.json()["ref"],
                "last_commit_id": output.json()["last_commit_id"],
            }
        )

    def gl_delete_file(self, repo_id, file_path, args, branch=None):
        if branch is None:
            pj = self.gl.projects.get(repo_id)
            branch = pj.default_branch
        return self.__api_delete(
            f"/projects/{repo_id}/repository/files/{file_path}",
            params={
                "branch": branch,
                "author_email": "system@iiidevops.org.tw",
                "author_name": "iiidevops",
                "commit_message": args["commit_message"],
            },
        )

    def get_tags(
        self,
        repo_id: Union[int, str],
        order_by: str = None,
        sort: str = None,
        search: str = None,
    ):
        """
        取得所有 tag 列表，或透過參數取得特定 tag 資訊
        src: https://docs.gitlab.com/ee/api/tags.html#list-project-repository-tags

        Args:
            repo_id: The ID or URL-encoded path of the project owned by the authenticated user.
            order_by: Return tags ordered by `name`, `updated`, or `version`. Default is `updated`.
            sort: Return tags sorted in `asc` or `desc` order. Default is `desc`.
            search: Return list of tags matching the search criteria. You can use `^term` and `term$` to find
                tags that begin and end with term respectively. No other regular expressions are supported.

        Returns:
            list of tags
        """
        params: dict[str, str] = {}
        if order_by:
            params["order_by"] = order_by
        if sort:
            params["sort"] = sort
        if search:
            params["search"] = search

        return self.__api_get(f"/projects/{repo_id}/repository/tags", params).json()

    def is_tag_exist(self, repo_id: Union[int, str], pattern: str) -> bool:
        """
        檢查 tag 是否存在，並完全符合 pattern

        Args:
            repo_id: project id
            pattern: tag name

        Returns:
            True if tag exist, otherwise False
        """
        _result: bool = False

        for _tag in self.get_tags(repo_id, search=pattern):
            if _tag.get("name", None) == pattern:
                _result = True
                break

        return _result

    def create_tag(self, repo_id: Union[int, str], tag_name: str, ref: str, message: str = None):
        """
        替 GitLab commit 建立新 tag
        src: https://docs.gitlab.com/ee/api/tags.html#create-a-new-tag

        Args:
            repo_id: The ID or URL-encoded path of the project owned by the authenticated user
            tag_name: The name of a tag
            ref: Create tag using commit SHA, another tag name, or branch name
            message: Creates annotated tag

        Returns:
            tag info
        """
        params: dict[str, str] = {}
        if tag_name:
            params["tag_name"] = tag_name
        if ref:
            params["ref"] = ref
        if message:
            params["message"] = message

        return self.__api_post(f"/projects/{repo_id}/repository/tags", params=params).json()

    def delete_tag(self, repo_id: Union[int, str], tag_name: str):
        """
        刪除 GitLab tag
        src: https://docs.gitlab.com/ee/api/tags.html#delete-a-tag

        Args:
            repo_id: The ID or URL-encoded path of the project owned by the authenticated user
            tag_name: The name of a tag

        Returns:
            tag info
        """
        return self.__api_delete(f"/projects/{repo_id}/repository/tags/{tag_name}")

    def gl_get_commits(self, project_id, branch, per_page=100, page=1, since=None):
        return self.__api_get(
            f"/projects/{project_id}/repository/commits",
            params={
                "ref_name": branch,
                "per_page": per_page,
                "since": since,
                "page": page,
            },
        ).json()

    def gl_get_commits_by_author(self, project_id, branch, filter=None):
        commits = self.gl_get_commits(project_id, branch)
        if filter is None:
            return commits
        output = []
        for commit in commits:
            if commit.get("author_name") != filter:
                output.append(commit)
        return output

    def convert_login_to_mail(self, login):
        user = model.User.query.filter_by(login=login).one()
        return user.email

    def gl_get_commits_by_members(self, project_id, branch):
        commits = self.gl_get_commits(project_id, branch)
        output = []
        for commit in commits:
            if (
                commit.get("author_name") != "Administrator"
                and commit.get("committer_name") != "Administrator"
                and not commit.get("author_name", "").startswith("專案管理機器人")
                and not commit.get("committer_name", "").startswith("專案管理機器人")
            ):
                output.append(commit)
        return output

    # 用project_id查詢project的網路圖

    def gl_get_network(self, repo_id):
        branch_commit_list = []

        # 整理各branches的commit_list
        branches = self.gl_get_branches(repo_id)
        for branch in branches:
            branch_commits = self.gl_get_commits(repo_id, branch["name"])
            for branch_commit in branch_commits:
                obj = {
                    "id": branch_commit["id"],
                    "title": branch_commit["title"],
                    "message": branch_commit["message"],
                    "author_name": branch_commit["author_name"],
                    "committed_date": branch_commit["committed_date"],
                    "parent_ids": branch_commit["parent_ids"],
                    "branch_name": branch["name"],
                    "tags": [],
                }
                branch_commit_list.append(obj)

        # 整理tags
        tags = gitlab.get_tags(repo_id)
        for tag in tags:
            for commit in branch_commit_list:
                if commit["id"] == tag["commit"]["id"]:
                    commit["tags"].append(tag["name"])

        data_by_time = sorted(
            branch_commit_list,
            reverse=False,
            key=lambda c_list: c_list["committed_date"],
        )

        return util.success(data_by_time)

    def gl_create_access_token(self, user_id):
        data = {"name": "IIIDevops Helm source code analysis", "scopes": ["read_api"]}
        return self.__api_post(f"/users/{user_id}/impersonation_tokens", data=data).json()["token"]

    # Get Gitlab list releases
    def gl_list_releases(self, repo_id):
        return self.__api_get(f"/projects/{repo_id}/releases").json()

    # Get Gitlab list releases
    def gl_get_release(self, repo_id, tag_name):
        return self.__api_get(f"/projects/{repo_id}/releases/{tag_name}").json()

    def gl_create_release(self, repo_id, data):
        path = f"/projects/{repo_id}/releases"
        return self.__api_post(path, params=data).json()

    def gl_update_release(self, repo_id, tag_name, data):
        path = f"/projects/{repo_id}/releases/{tag_name}"
        return self.__api_put(path, params=data).json()

    def gl_delete_release(self, repo_id, tag_name):
        path = f"/projects/{repo_id}/releases/{tag_name}"
        return self.__api_delete(path).json()

    # Archive project
    def gl_archive_project(self, repo_id, disabled):
        status = "archive" if disabled else "unarchive"
        path = f"/projects/{repo_id}/{status}"
        return self.__api_post(path).json()

    def single_commit(self, project_id, commit_id):
        return self.__api_get(f"/projects/{project_id}/repository/commits/{commit_id}").json()

    def __get_projects_commit(self, pjs, out_list, branch_name, days_ago):
        for pj in pjs:
            if (pj.empty_repo is False) and pj.path_with_namespace.split("/")[0] not in iiidevops_system_group:
                if branch_name is None:
                    pj_commits = pj.commits.list(since=days_ago)
                else:
                    pj_commits = pj.commits.list(ref_name=branch_name, since=days_ago)
                for commit in pj_commits:
                    out_list.append(
                        {
                            "pj_name": pj.name,
                            "author_name": commit.author_name,
                            "author_email": commit.author_email,
                            "commit_time": self.__gl_timezone_to_utc(commit.committed_date),
                            "commit_id": commit.short_id,
                            "commit_title": commit.title,
                            "commit_message": commit.message,
                        }
                    )
        return out_list

    def __get_projects_by_repo_or_by_user(self, git_repository_id, user_id):
        pjs = []
        if git_repository_id is not None:
            pjs.append(self.gl.projects.get(git_repository_id))
        elif user_id is not None:
            rows = (
                db.session.query(model.ProjectUserRole, model.ProjectPluginRelation)
                .join(
                    model.ProjectPluginRelation,
                    model.ProjectPluginRelation.project_id == model.ProjectUserRole.project_id,
                )
                .filter(
                    model.ProjectUserRole.user_id == user_id,
                    model.ProjectUserRole.project_id == model.ProjectPluginRelation.project_id,
                )
                .all()
            )
            for row in rows:
                pjs.append(self.gl.projects.get(row.ProjectPluginRelation.git_repository_id))
        else:
            pjs = self.gl.projects.list(order_by="last_activity_at")
        return pjs

    def gl_get_the_last_hours_commits(
        self,
        the_last_hours=None,
        show_commit_rows=None,
        git_repository_id=None,
        branch_name=None,
        user_id=None,
    ):
        if role.is_admin() is False:
            user_id = get_jwt_identity()["user_id"]
        out_list = []
        if show_commit_rows is not None:
            for x in range(12, 169, 12):
                out_list = []
                days_ago = (datetime.utcnow() - timedelta(days=x)).isoformat()
                pjs = self.__get_projects_by_repo_or_by_user(git_repository_id, user_id)
                out_list = self.__get_projects_commit(pjs, out_list, branch_name, days_ago)
                if len(out_list) > show_commit_rows - 1:
                    return out_list[:show_commit_rows]
            return out_list[:show_commit_rows]
        else:
            if the_last_hours is None:
                the_last_hours = 24
            days_ago = (datetime.utcnow() - timedelta(hours=the_last_hours)).isoformat()
            pjs = self.__get_projects_by_repo_or_by_user(git_repository_id, user_id)
            out_list = self.__get_projects_commit(pjs, out_list, branch_name, days_ago)
        return out_list

    def gl_count_each_pj_commits_by_days(self, days=30, timezone_hours_number=8):
        for pj in self.gl.projects.list(all=True):
            if pj.path_with_namespace.split("/")[0] not in iiidevops_system_group:
                commit_number = 0
                total_commit_number = 0
                the_last_time_total_commit_number = 0
                if pj.empty_repo is False:
                    try:
                        the_last_data = (
                            GitCommitNumberEachDays.query.filter(GitCommitNumberEachDays.repo_id == pj.id)
                            .order_by(GitCommitNumberEachDays.id.desc())
                            .first()
                        )
                        if the_last_data is not None and the_last_data.total_commit_number is not None:
                            the_last_time_total_commit_number = the_last_data.total_commit_number
                    except NoResultFound:
                        pass
                    total_commit_number = len(pj.commits.list(all=True))
                    commit_number = total_commit_number - the_last_time_total_commit_number
                    if commit_number < 0:
                        commit_number = 0
                now_time = datetime.utcnow() + timedelta(hours=timezone_hours_number)
                one_row_data = GitCommitNumberEachDays(
                    repo_id=pj.id,
                    repo_name=pj.name,
                    date=now_time.date(),
                    commit_number=commit_number,
                    total_commit_number=total_commit_number,
                    created_at=str(datetime.utcnow()),
                )
                db.session.add(one_row_data)
                db.session.commit()

    def ql_get_tree(self, repository_id, path, branch_name=None, all=False):
        try:
            pj = self.gl.projects.get(repository_id)
            if pj.empty_repo:
                return []
            if branch_name is None:
                return pj.repository_tree(ref=pj.default_branch, path=path, all=all)
            else:
                return pj.repository_tree(ref=branch_name, path=path, all=all)
        except apiError.TemplateError as e:
            raise apiError.TemplateError(
                404,
                "Error when getting project repository_tree.",
                error=apiError.gitlab_error(e),
            )

    def gl_get_raw_from_lib(self, repository_id, path, branch_name=None):
        pj = self.gl.projects.get(repository_id)
        if branch_name is None:
            f_byte = pj.files.raw(file_path=path, ref=pj.default_branch)
        else:
            f_byte = pj.files.raw(file_path=path, ref=branch_name)
        return f_byte

    def gl_get_file_from_lib(self, repository_id, path, branch_name=None):
        pj = self.gl.projects.get(repository_id)
        if branch_name is None:
            f_byte = pj.files.get(file_path=path, ref=pj.default_branch)
        else:
            f_byte = pj.files.get(file_path=path, ref=branch_name)
        return f_byte

    def gl_create_file(self, pj, file_path, file_name, local_file_path, branch=""):
        branch = branch if branch else pj.default_branch
        with open(f"{local_file_path}/{file_name}", "r") as f:
            content = base64.b64encode(bytes(f.read(), encoding="utf-8")).decode("utf-8")
            pj.files.create(
                {
                    "file_path": file_path,
                    "branch": branch,
                    "encoding": "base64",
                    "author_email": "system@iiidevops.org.tw",
                    "author_name": "iiidevops",
                    "content": content,
                    "commit_message": f"Add file {file_path}",
                }
            )

    def create_multiple_file_commit(
        self,
        project: objects.Project,
        files: list[dict[str, str]],
        branch: str = "",
        commit_message: str = "",
    ) -> None:
        """
        Upload multiple files to the repository in one commit.

        :param project: Project object
        :param files: file list, generated by single_file
        :param branch: branch name
        :param commit_message: Commit message
        :return: None
        """
        fallback_message: str = "Add or update files\n\n"
        for file in files:
            if not (file.get("action", False) and file.get("file_path", False) and file.get("content", False)):
                raise apiError.DevOpsError(
                    400,
                    "Error when create multiple file commit.",
                    error=f"{file} missing required parameter.",
                )
            path: Path = Path(file["file_path"])
            fallback_message += f"- {file['action'].capitalize()} {path.stem}{path.suffix}\n"

        data = {
            "branch": branch if branch else project.default_branch,
            "author_email": "system@iiidevops.org.tw",
            "author_name": "iiidevops",
            "commit_message": commit_message if commit_message else fallback_message,
            "actions": files,
        }

        project.commits.create(data)

    def gl_operate_multi_files(self, project, operate_list, commit_msg, branch=""):
        data = {
            "branch": branch if branch else project.default_branch,
            "author_email": "system@iiidevops.org.tw",
            "author_name": "iiidevops",
            "commit_message": commit_msg,
            "actions": operate_list,
        }
        commit = project.commits.create(data)
        return commit

    def list_pj_commits_and_wirte_in_file(self):
        # Check this process is active or not
        git_commit_history = SystemParameter.query.filter_by(name="git_commit_history").one()
        if not git_commit_history.active:
            return

        # Initialize varialbe
        base_path = "logs/git_commit_history"
        datetime_now = datetime.utcnow().strftime(GITLAB_DATETIME_FORMAT)
        date = datetime_now[:10]
        keep_days = git_commit_history.value["keep_days"]

        # Check git_commit_history folder exists, if not create it
        util.check_folder_exist(base_path, create=True)

        # Remove existed more than keep days' files
        for pj_folder in os.listdir(base_path):
            for commit_file in os.listdir(f"{base_path}/{pj_folder}"):
                if commit_file.split(".")[0] < str(util.get_certain_date_from_now(keep_days))[:10]:
                    os.remove(f"{base_path}/{pj_folder}/{commit_file}")
            if os.listdir(f"{base_path}/{pj_folder}") == []:
                os.rmdir(f"{base_path}/{pj_folder}")

        # List all pjs' commits, write into json file and names it by date.
        projects = self.gl_get_all_project()
        for pj in projects:
            util.check_folder_exist(f"{base_path}/{pj.id}", create=True)
            result = {"repo_name": pj.name, "create_at": datetime_now, "commits": {}}
            for commit in pj.commits.list():
                result["commits"][commit.id[:4]] = {
                    "author_name": commit.author_name,
                    "parent_ids": commit.parent_ids,
                    "title": commit.title,
                    "message": commit.message.replace("\n", ""),
                    "author_email": commit.author_email,
                    "commit_date": commit.committed_date,
                    "commit_id": commit.id,
                }
            util.write_json_file(f"{base_path}/{pj.id}/{date}.json", result)

    def __gl_start_convert_page(self, start: int, limit: int):
        page = (start // limit) + 1
        return page

    # pipeline
    def gl_list_pipelines(self, repo_id: int, limit: int, start: int, sort: str = "desc", with_pagination: bool = False) -> list[dict[str, Any]]:
        params={
            "page": self.__gl_start_convert_page(start, limit),
            "per_page": limit,
            "sort": sort
        }
        ret = self.__api_get(f"/projects/{repo_id}/pipelines", params=params)
        results = ret.json()
        if not with_pagination:
            return results

        headers = ret.headers
        pagination = {
            "total": headers.get("X-Total"),
            "current": headers.get("X-Page"),
            "prev": headers.get("X-Per-Page"),
            "next": headers.get("X-Next-Page"),
            "pages": headers.get("X-Total-Pages"),
            "per_page": limit,

        }
        return results, pagination

    def gl_get_pipeline_console(self, repo_id: int, job_id: int):
        return self.__api_get(f"/projects/{repo_id}/jobs/{job_id}/trace").content.decode("utf-8")

    def gl_rerun_pipeline_job(self, repo_id: int, job_id: int):
        return self.__api_post(f"/projects/{repo_id}/pipelines/{job_id}/retry").json()

    def gl_stop_pipeline_job(self, repo_id: int, job_id: int):
        return self.__api_post(f"/projects/{repo_id}/pipelines/{job_id}/cancel").json()

    def gl_pipeline_jobs(self, repo_id: int, pipeline_id: int) -> dict[str, Any]:
        return self.__api_get(f"/projects/{repo_id}/pipelines/{pipeline_id}/jobs").json()

    def get_pipeline_jobs_status(self, repo_id: int, pipeline_id: int, with_commit_msg: bool = False) -> dict[str, int]:
        jobs = self.gl_pipeline_jobs(repo_id, pipeline_id)
        total = len(jobs)
        success = len([job for job in jobs if job["status"] == "success"])
        ret = {
            "status": {
                "total": total,
                "success": success
            }     
        }
        if with_commit_msg:
            commit_message = jobs[0]["commit"]["title"]
            ret.update({
                "commit_message": commit_message
            })
        return ret

        
        

def single_file(
    file_path: str,
    local_file_path: str,
    action: FileActions = FileActions.CREATE,
    binary: bool = False,
) -> dict[str, str]:
    """
    建立一個要新增的檔案 dictionary，需搭配 create_multiple_file_commit 使用

    :param file_path: Repo 中的檔案路徑
    :param local_file_path: 要上傳的檔案路徑
    :param action: 檔案的行為，預設是新增檔案
    :param binary: 是否是二進位檔案，預設為 False
    :return: 一個要新增的 dictionary
    """

    if binary:
        return {
            "action": action.value,
            "file_path": file_path,
            "content": base64.b64encode(open(local_file_path, "rb").read()),
            "encoding": "base64",
        }
    return {
        "action": action.value,
        "file_path": file_path,
        "content": open(local_file_path, encoding="utf-8").read(),
    }


def get_all_group_projects(group):
    group_project_list = []
    item = group.projects.list(as_list=False)
    for i in range(1, item.total_pages + 1):
        group_project_list.extend(group.projects.list(page=i))
    return group_project_list


def get_all_repo_members(project_id=None):
    gl_users = []
    page = 1
    x_total_pages = 10
    while page <= x_total_pages:
        params = {"page": page}
        if project_id:
            output = gitlab.gl_project_list_member(get_nexus_repo_id(project_id), params)
        else:
            output = gitlab.gl_get_user_list(params)
        gl_users.extend(output.json())
        x_total_pages = int(output.headers["X-Total-Pages"])
        page += 1
    return gl_users


def account_is_gitlab_project_memeber(project_id, account):
    for member in get_all_repo_members(project_id):
        if account == member["username"] or account == "Administrator":
            return True
    return False


def get_commit_issues_relation(project_id, issue_id, limit):
    account = get_jwt_identity()["user_account"]
    relation_project_list = (
        [project_id] + get_all_fathers_project(project_id, []) + get_all_sons_project(project_id, [])
    )
    commit_issues_relations = (
        model.IssueCommitRelation.query.filter(model.IssueCommitRelation.project_id.in_(tuple(relation_project_list)))
        .filter(model.IssueCommitRelation.issue_ids.contains([int(issue_id)]))
        .order_by(desc(model.IssueCommitRelation.commit_time))
        .limit(limit)
        .all()
    )

    return [
        {
            "commit_id": commit_issues_relation.commit_id,
            "pj_name": model.Project.query.get(commit_issues_relation.project_id).name,
            "issue_id": issue_id,
            "author_name": commit_issues_relation.author_name,
            "commit_message": commit_issues_relation.commit_message,
            "commit_title": commit_issues_relation.commit_title,
            "commit_time": str(commit_issues_relation.commit_time.isoformat()),
            "branch": commit_issues_relation.branch,
            "web_url": commit_issues_relation.web_url
            if account_is_gitlab_project_memeber(commit_issues_relation.project_id, account)
            else None,
            "created_at": str(commit_issues_relation.created_at),
            "updated_at": str(commit_issues_relation.updated_at),
        }
        for commit_issues_relation in commit_issues_relations
    ]


def get_project_plugin_object(project_id):
    return model.ProjectPluginRelation.query.filter_by(project_id=project_id).first()


def get_project_commit_endpoint_object(project_id):
    project_commit_endpoint = model.ProjectCommitEndpoint.query.filter_by(project_id=project_id).first()
    if project_commit_endpoint is None:
        new = model.ProjectCommitEndpoint(project_id=project_id, commit_id=None, updated_at=None)
        model.db.session.add(new)
        model.db.session.commit()
        return model.ProjectCommitEndpoint.query.filter_by(project_id=project_id).first()
    return project_commit_endpoint


def sync_commit_issues_relation(project_id):
    git_pj_id = get_project_plugin_object(project_id).git_repository_id
    # Find root project to get all related issues
    root_project_id = get_root_project_id(project_id, force=True)
    root_plan_project_id = get_project_plugin_object(root_project_id).plan_project_id
    issue_list = [str(issue.id) for issue in redmine.project.get(root_plan_project_id).issues]

    pj = gitlab.gl.projects.get(git_pj_id)
    for br in pj.branches.list(all=True):
        project_commit_endpoint = get_project_commit_endpoint_object(project_id)
        end_point = (
            str(project_commit_endpoint.updated_at - timedelta(days=1))
            if project_commit_endpoint.updated_at is not None
            else None
        )
        commits = gitlab.gl_get_commits(git_pj_id, br.name, per_page=5000, since=end_point)
        for commit in commits:
            # Find all issue_id startswith '#'
            regex = re.compile(r"#(\d+)")
            commit_issue_id_list = regex.findall(commit["title"])
            commit_issue_id_list = [int(issue_id) for issue_id in commit_issue_id_list if issue_id in issue_list]

            if commit_issue_id_list != []:
                # Just in case it stores duplicated commit.
                try:
                    new = model.IssueCommitRelation(
                        commit_id=commit["id"],
                        project_id=project_id,
                        issue_ids=commit_issue_id_list,
                        author_name=commit["author_name"],
                        commit_message=commit["message"],
                        commit_title=commit["title"],
                        commit_time=datetime.strptime(commit["committed_date"], "%Y-%m-%dT%H:%M:%S.%f%z"),
                        web_url=commit["web_url"],
                        branch=br.name,
                        created_at=datetime.utcnow().strftime(GITLAB_DATETIME_FORMAT),
                        updated_at=datetime.utcnow().strftime(GITLAB_DATETIME_FORMAT),
                    )
                    model.db.session.add(new)
                    model.db.session.commit()
                except IntegrityError:
                    model.db.session.rollback()
                finally:
                    model.db.session.close()

        if end_point is None or br.commit["committed_date"] > "T".join(end_point.split(" ")):
            project_commit_endpoint.updated_at = br.commit["committed_date"]
            project_commit_endpoint.commit_id = br.commit["id"]
            model.db.session.commit()


def get_project_members(project_id):
    # list users in the project
    project_row = (
        model.Project.query.options(
            joinedload(model.Project.user_role)
            .joinedload(model.ProjectUserRole.user)
            .joinedload(model.User.project_role)
        )
        .filter_by(id=project_id)
        .one()
    )
    users = list(filter(lambda x: not x.user.disabled, project_row.user_role))
    account_list = ["sysadmin"] + [
        model.User.query.get(user.user_id).login
        for user in users
        if not model.User.query.get(user.user_id).login.startswith("project_bot")
    ]
    return account_list


def get_commit_issues_hook_by_branch(project_id, branch_name, limit):
    ret_list = []
    role_id = get_jwt_identity()["role_id"]
    account = get_jwt_identity()["user_account"]
    repo_id = get_project_plugin_object(project_id).git_repository_id
    if role_id == 5:
        show_url = True
    else:
        show_url = account in [
            member["username"]
            for member in get_all_repo_members(project_id)
            if not member["username"].startswith("project_bot")
        ]
    # Find root project to get all related issues
    root_project_id = get_root_project_id(project_id)
    root_plan_project_id = get_project_plugin_object(root_project_id).plan_project_id
    issue_list = [int(issue.id) for issue in redmine.project.get(root_plan_project_id).issues]

    commits = gitlab.gl_get_commits(repo_id, branch_name, per_page=limit)
    for commit in commits:
        ret = {"issue_hook": {}}
        issue_commit_relation = model.IssueCommitRelation.query.filter_by(commit_id=commit["id"]).first()
        commit_issue_id_list = issue_commit_relation.issue_ids if issue_commit_relation is not None else []
        for issue_id in commit_issue_id_list:
            if issue_id in issue_list:
                issue = redmine.issue.get(issue_id)
                project_id = (
                    model.ProjectPluginRelation.query.filter_by(plan_project_id=issue.project.id).first().project_id
                )
                ret["issue_hook"][issue_id] = account in get_project_members(project_id)

        ret["commit_id"] = commit["id"]
        ret["commit_short_id"] = commit["id"][:7]
        ret["author_name"] = commit["author_name"]
        ret["commit_title"] = commit["title"]
        ret["commit_time"] = datetime.strptime(commit["committed_date"], "%Y-%m-%dT%H:%M:%S.%f%z").isoformat()
        ret["gitlab_url"] = commit["web_url"] if show_url else None

        ret_list.append(ret)

    return ret_list


def verify_github_info(value: dict[str, str]) -> None:
    account: str = value["account"]
    token: str = value["token"]
    g: Github = Github(login_or_token=token)
    try:
        login: str = g.get_user().login
        not_alive_messages: list = get_unread_notification_message_list(title="GitHub token is unavailable")
        if not_alive_messages:
            for not_alive_message in not_alive_messages:
                close_notification_message(not_alive_message["id"])
            back_to_alive_title = "GitHub token is back to available."
            create_notification_message(
                {
                    "alert_level": 1,
                    "title": back_to_alive_title,
                    "message": back_to_alive_title,
                    "type_ids": [4],
                    "type_parameters": {"role_ids": [5]},
                }
            )
    except BadCredentialsException:
        raise apiError.DevOpsError(
            400,
            "Token is invalid.",
            apiError.error_with_alert_code("github", 20001, "Token is invalid.", value),
        )

    if login != account:
        raise apiError.DevOpsError(
            400,
            "Token is not belong to this account.",
            apiError.error_with_alert_code("github", 20002, "Token is not belong to this account.", value),
        )

    if len([repo for repo in g.search_repositories(query="iiidevops in:name")]) == 0:
        raise apiError.DevOpsError(
            400,
            "Token is not belong to this project(iiidevops).",
            apiError.error_with_alert_code(
                "github",
                20003,
                "Token is not belong to this project(iiidevops).",
                value,
            ),
        )


"""
def gitlab_domain_connection(action):
    if action not in ["open", "close"]:
        return
    body = gitlab_connection(action)
    ApiK8sClient().patch_namespaced_ingress(name="gitlab-ing", body=body, namespace="default")

    gitlab_domain_connection = model.SystemParameter.query.filter_by(name="gitlab_domain_connection").first()
    gitlab_domain_connection.value = {"gitlab_domain_connection": action == "open"}
    from sqlalchemy.orm.attributes import flag_modified

    flag_modified(gitlab_domain_connection, "value")
    db.session.commit()


def gitlab_status_connection():
    try:
        a = ApiK8sClient().read_namespaced_ingress(name="gitlab-ing", namespace="default")
        paths = a.spec.rules[0].http.paths
        return {"status": len(paths) == 1}
    except Exception:
        return {"status": False}
"""


def get_source_code_info(repo_name, branch):
    project_query = Project.query.filter(Project.name == repo_name).first()
    query = ProjectPluginRelation.query.filter(ProjectPluginRelation.project_id == project_query.id).first()
    code_len_query = (
        GitlabSourceCodeLens.query.filter(GitlabSourceCodeLens.project_id == project_query.id)
        .filter(GitlabSourceCodeLens.branch == branch)
        .first()
    )
    if code_len_query:
        return util.success(
            {
                "branch": branch,
                "commit_id": code_len_query.commit_id,
                "project_id": project_query.id,
                "project_name": project_query.name,
                "repo_id": query.git_repository_id,
                "source_code_num": code_len_query.source_code_num,
            }
        )
    else:
        return None


def unprotect_project(gl_pj_id, branch):
    for protect_branch in gitlab.gl_list_protect_branches(gl_pj_id):
        if protect_branch.get("name") == "master":
            gitlab.gl_unprotect_branch(gl_pj_id, branch)
            break

    # --------------------- Resources ---------------------


gitlab = GitLab()


class GitRelease:
    @jwt_required()
    def check_gitlab_release(self, repository_id, tag_name, branch_name, commit):
        output = {"check": True, "info": "", "errors": ""}
        branch = gitlab.gl_get_commits(str(repository_id), branch_name)
        #  check branch exist
        if len(branch) == 0:
            output = {"check": False, "info": "Gitlab no exists commit", "errors": ""}
            return output
        tags = gitlab.get_tags(str(repository_id), search=tag_name)
        for tag in tags:
            if tag["name"] == tag_name:
                output["check"] = False
                output["info"] = f"{tag_name} is exists in gitlab"
                output["errors"] = tag
        return output


gl_release = GitRelease()


class GitProjectBranches(Resource):
    @jwt_required()
    def get(self, repository_id):
        return util.success({"branch_list": gitlab.gl_get_branches(repository_id)})

    @jwt_required()
    def post(self, repository_id):
        parser = reqparse.RequestParser()
        parser.add_argument("branch", type=str, required=True)
        parser.add_argument("ref", type=str, required=True)
        args = parser.parse_args()
        return util.success(gitlab.gl_create_branch(repository_id, args))


class GitProjectBranchesV2(MethodResource):
    @doc(tags=["Gitlab"], description="get all branches in project")
    @jwt_required()
    @marshal_with(route_model.GitlabGetProjectBranchesRes)
    def get(self, repository_id):
        return util.success({"branch_list": gitlab.gl_get_branches(repository_id)})

    @doc(tags=["Gitlab"], description="add branch for the project")
    @jwt_required()
    @use_kwargs(route_model.GitlabPostProjectBranchesSch, location="json")
    @marshal_with(route_model.GitlabPostProjectBranchesRes)
    def post(self, repository_id, **kwargs):
        return util.success(gitlab.gl_create_branch(repository_id, kwargs))


class GitProjectBranch(Resource):
    @jwt_required()
    def get(self, repository_id, branch_name):
        project_id = get_nexus_project_id(repository_id)
        role.require_in_project(project_id)
        return util.success(gitlab.gl_get_branch(repository_id, branch_name))

    @jwt_required()
    def delete(self, repository_id, branch_name):
        project_id = get_nexus_project_id(repository_id)
        role.require_in_project(project_id)
        gitlab.gl_delete_branch(repository_id, branch_name)
        return util.success()


class GitProjectBranchV2(MethodResource):
    @doc(tags=["Gitlab"], description="get project branch info")
    @jwt_required()
    @marshal_with(route_model.GitlabGetProjectBranchRes)
    def get(self, repository_id, branch_name):
        project_id = get_nexus_project_id(repository_id)
        role.require_in_project(project_id)
        return util.success(gitlab.gl_get_branch(repository_id, branch_name))

    @doc(tags=["Gitlab"], description="delete project branch")
    @jwt_required()
    @marshal_with(util.CommonResponse)
    def delete(self, repository_id, branch_name):
        project_id = get_nexus_project_id(repository_id)
        role.require_in_project(project_id)
        gitlab.gl_delete_branch(repository_id, branch_name)
        return util.success()


class GitProjectRepositories(Resource):
    @jwt_required()
    def get(self, repository_id, branch_name):
        project_id = get_nexus_project_id(repository_id)
        role.require_in_project(project_id)
        return util.success(gitlab.gl_get_repository_tree(repository_id, branch_name))


class GitProjectRepositoriesV2(MethodResource):
    @doc(tags=["Gitlab"], description="get branch file type")
    @jwt_required()
    @marshal_with(route_model.GitGetProjectRepositoriesRes)
    def get(self, repository_id, branch_name):
        project_id = get_nexus_project_id(repository_id)
        role.require_in_project(project_id)
        return util.success(gitlab.gl_get_repository_tree(repository_id, branch_name))


class GitProjectFile(Resource):
    @jwt_required()
    def post(self, repository_id):
        project_id = get_nexus_project_id(repository_id)
        role.require_in_project(project_id)
        parser = reqparse.RequestParser()
        parser.add_argument("branch", type=str, required=True)
        parser.add_argument("file_path", type=str, required=True)
        parser.add_argument("start_branch", type=str)
        parser.add_argument("author_email", type=str)
        parser.add_argument("author_name", type=str)
        parser.add_argument("encoding", type=str)
        parser.add_argument("content", type=str, required=True)
        parser.add_argument("commit_message", type=str, required=True)
        args = parser.parse_args()
        return gitlab.gl_add_file(repository_id, args)

    @jwt_required()
    def put(self, repository_id):
        project_id = get_nexus_project_id(repository_id)
        role.require_in_project(project_id)
        parser = reqparse.RequestParser()
        parser.add_argument("branch", type=str, required=True)
        parser.add_argument("file_path", type=str, required=True)
        parser.add_argument("start_branch", type=str)
        parser.add_argument("author_email", type=str)
        parser.add_argument("author_name", type=str)
        parser.add_argument("encoding", type=str)
        parser.add_argument("content", type=str, required=True)
        parser.add_argument("commit_message", type=str, required=True)
        args = parser.parse_args()
        return gitlab.gl_update_file(repository_id, args)

    @jwt_required()
    def get(self, repository_id, branch_name, file_path):
        project_id = get_nexus_project_id(repository_id)
        role.require_in_project(project_id)
        return gitlab.gl_get_file(repository_id, branch_name, file_path)

    @jwt_required()
    def delete(self, repository_id, branch_name, file_path):
        project_id = get_nexus_project_id(repository_id)
        role.require_in_project(project_id)
        parser = reqparse.RequestParser()
        parser.add_argument("commit_message", type=str, required=True, location="args")
        args = parser.parse_args()
        gitlab.gl_delete_file(repository_id, file_path, args, branch_name)
        return util.success()


class GitProjectTag(Resource):
    @jwt_required()
    def get(self, repository_id):
        project_id = get_nexus_project_id(repository_id)
        role.require_in_project(project_id)
        res = gitlab.get_tags(repository_id)
        return util.success({"tag_list": res})

    @jwt_required()
    def post(self, repository_id):
        project_id = get_nexus_project_id(repository_id)
        role.require_in_project(project_id)
        parser = reqparse.RequestParser()
        parser.add_argument("tag_name", type=str, required=True)
        parser.add_argument("ref", type=str, required=True)
        parser.add_argument("message", type=str)
        parser.add_argument("release_description", type=str)

        args = parser.parse_args()
        return util.success(
            gitlab.create_tag(
                repository_id,
                args.get("tag_name", None),
                args.get("ref", None),
                args.get("message", None),
            )
        )

    @jwt_required()
    def delete(self, repository_id, tag_name):
        project_id = get_nexus_project_id(repository_id)
        role.require_in_project(project_id)
        gitlab.delete_tag(repository_id, tag_name)
        return util.success()


class GitProjectTagV2(MethodResource):
    @doc(tags=["Gitlab"], description="get project tags")
    @jwt_required()
    @marshal_with(route_model.GitGetProjectTagRes)
    def get(self, repository_id):
        project_id = get_nexus_project_id(repository_id)
        role.require_in_project(project_id)
        res = gitlab.get_tags(repository_id)
        return util.success({"tag_list": res})

    @doc(tags=["Gitlab"], description="add project tags")
    @use_kwargs(route_model.GitPostProjectTagSch, location="form")
    @jwt_required()
    @marshal_with(route_model.GitPostProjectTagRes)
    def post(self, repository_id, **kwargs):
        project_id = get_nexus_project_id(repository_id)
        role.require_in_project(project_id)
        return util.success(gitlab.create_tag(repository_id, kwargs))

    @doc(tags=["Gitlab"], description="delete project tags")
    @jwt_required()
    @marshal_with(util.CommonResponse)
    def delete(self, repository_id, tag_name):
        project_id = get_nexus_project_id(repository_id)
        role.require_in_project(project_id)
        gitlab.delete_tag(repository_id, tag_name)
        return util.success()


class GitProjectBranchCommits(Resource):
    @jwt_required()
    def get(self, repository_id):
        project_id = get_nexus_project_id(repository_id)
        role.require_in_project(project_id)
        parser = reqparse.RequestParser()
        parser.add_argument("branch", type=str, required=True, location="args")
        parser.add_argument("filter", type=str, location="args")
        args = parser.parse_args()
        return util.success(gitlab.gl_get_commits_by_author(repository_id, args["branch"], args.get("filter")))


class GitProjectBranchCommitsV2(MethodResource):
    @doc(tags=["Gitlab"], description="get commits of one branch")
    @jwt_required()
    @use_kwargs(route_model.GitGetBranchCommitsSch, location="query")
    @marshal_with(route_model.GitGetBranchCommitsRes)
    def get(self, repository_id, **kwargs):
        project_id = get_nexus_project_id(repository_id)
        role.require_in_project(project_id)
        return util.success(gitlab.gl_get_commits_by_author(repository_id, kwargs["branch"], kwargs.get("filter")))


class GitProjectMembersCommits(Resource):
    @jwt_required()
    def get(self, repository_id):
        project_id = get_nexus_project_id(repository_id)
        role.require_in_project(project_id)
        parser = reqparse.RequestParser()
        parser.add_argument("branch", type=str, required=True, location="args")
        args = parser.parse_args()
        return util.success(gitlab.gl_get_commits_by_members(repository_id, args["branch"]))


class GitProjectMembersCommitsV2(MethodResource):
    @doc(tags=["Gitlab"], description="get commits of the pj_members ")
    @jwt_required()
    @use_kwargs(route_model.GitGetMembersCommitsSch, location="query")
    @marshal_with(route_model.GitGetMembersCommitsRes)
    def get(self, repository_id, **kwargs):
        project_id = get_nexus_project_id(repository_id)
        role.require_in_project(project_id)
        return util.success(gitlab.gl_get_commits_by_members(repository_id, kwargs["branch"]))


class GitProjectNetwork(Resource):
    @jwt_required()
    def get(self, repository_id):
        return gitlab.gl_get_network(repository_id)


class GitProjectNetworkV2(MethodResource):
    @doc(tags=["Gitlab"], description="get repositories overview")
    @jwt_required()
    @marshal_with(route_model.GitGetRepositoriesOverviewRes)
    def get(self, repository_id):
        return gitlab.gl_get_network(repository_id)


class GitProjectId(Resource):
    @jwt_required()
    def get(self, repository_id):
        return GitLab.gl_get_nexus_project_id(repository_id)


class GitProjectIdV2(MethodResource):
    @doc(tags=["Gitlab"], description="get project id")
    @jwt_required()
    @marshal_with(route_model.GitGetProjectIdRes)
    def get(self, repository_id):
        return GitLab.gl_get_nexus_project_id(repository_id)


class GitProjectIdFromURL(Resource):
    @jwt_required()
    def get(self):
        parser = reqparse.RequestParser()
        parser.add_argument("repository_url", type=str, required=True, location="args")
        args = parser.parse_args()
        try:
            return util.success(GitLab.gl_get_project_id_from_url(args["repository_url"]))
        except NoResultFound:
            return util.respond(
                404,
                "No such repository found in database.",
                error=apiError.repository_id_not_found(args["repository_url"]),
            )


class GitProjectIdFromURLV2(MethodResource):
    @doc(tags=["Gitlab"], description="get project id form URI")
    @use_kwargs(route_model.GitGetProjectIdFromURISch, location="query")
    @jwt_required()
    @marshal_with(route_model.GitGetProjectIdFromURIRes)
    def get(self, **kwargs):
        try:
            return util.success(GitLab.gl_get_project_id_from_url(kwargs["repository_url"]))
        except NoResultFound:
            return util.respond(
                404,
                "No such repository found in database.",
                error=apiError.repository_id_not_found(kwargs["repository_url"]),
            )


class GitProjectURLFromId(Resource):
    @jwt_required()
    def get(self):
        parser = reqparse.RequestParser()
        parser.add_argument("project_id", type=int, location="args")
        parser.add_argument("repository_id", type=int, location="args")
        args = parser.parse_args()
        project_id = args["project_id"]
        if project_id is None:
            repo_id = args["repository_id"]
            if repo_id is None:
                return util.respond(
                    400,
                    "You must provide project_id or repository_id.",
                    error=apiError.argument_error("project_id|repository_id"),
                )
            project_id = get_nexus_project_id(repo_id)
        return util.success({"http_url": get_repo_url(project_id)})


class GitProjectURLFromIdV2(MethodResource):
    @doc(tags=["Gitlab"], description="get project url form id")
    @use_kwargs(route_model.GitGetProjectURLFromIdSch, location="query")
    @jwt_required()
    @marshal_with(route_model.GitGetProjectURLFromIdRes)
    def get(self, **kwargs):
        project_id = kwargs["project_id"]
        if project_id is None:
            repo_id = kwargs["repository_id"]
            if repo_id is None:
                return util.respond(
                    400,
                    "You must provide project_id or repository_id.",
                    error=apiError.argument_error("project_id|repository_id"),
                )
            project_id = get_nexus_project_id(repo_id)
        return util.success({"http_url": get_repo_url(project_id)})


class GitTheLastHoursCommits(Resource):
    @jwt_required()
    def get(self):
        parser = reqparse.RequestParser()
        parser.add_argument("the_last_hours", type=int, location="args")
        parser.add_argument("show_commit_rows", type=int, location="args")
        parser.add_argument("git_repository_id", type=int, location="args")
        parser.add_argument("branch_name", type=str, location="args")
        parser.add_argument("user_id", type=int, location="args")
        args = parser.parse_args()
        return util.success(
            gitlab.gl_get_the_last_hours_commits(
                args["the_last_hours"],
                args["show_commit_rows"],
                args["git_repository_id"],
                args["branch_name"],
                args["user_id"],
            )
        )


class GitCountEachPjCommitsByDays(Resource):
    def get(self):
        gitlab.gl_count_each_pj_commits_by_days()
        gitlab.list_pj_commits_and_wirte_in_file()
        return util.success()


class SyncGitCommitIssueRelation(Resource):
    @jwt_required()
    def get(self, project_id, issue_id):
        parser = reqparse.RequestParser()
        parser.add_argument("limit", type=int, default=10, location="args")
        args = parser.parse_args()
        return util.success(get_commit_issues_relation(project_id, issue_id, args["limit"]))

    @jwt_required()
    def post(self, project_id):
        sync_commit_issues_relation(project_id)
        return util.success()


class SyncGitCommitIssueRelationByPjName(Resource):
    def post(self):
        parser = reqparse.RequestParser()
        parser.add_argument("project_name", type=str, required=True, location="form")
        args = parser.parse_args()
        try:
            project = Project.query.filter_by(name=args["project_name"]).first()
        except NoResultFound:
            return util.respond(
                404,
                "No such repository found in database.",
                error=apiError.project_name_not_found(args["project_name"]),
            )

        sync_commit_issues_relation(project.id)
        return util.success()


class GetCommitIssueHookByBranch(Resource):
    @jwt_required()
    def get(self, project_id):
        parser = reqparse.RequestParser()
        parser.add_argument("limit", type=int, default=10, location="args")
        parser.add_argument("branch_name", type=str, required=True, location="args")
        args = parser.parse_args()
        return util.success(get_commit_issues_hook_by_branch(project_id, args["branch_name"], args["limit"]))


# class GitlabDomainConnection(Resource):
#     @jwt_required()
#     def get(self):
#         if config.get("GITLAB_DOMAIN_NAME") is None or config.get("GITLAB_DOMAIN_NAME") == "":
#             return {"is_ip": True}
#         try:
#             ipaddress.ip_address(config.get("GITLAB_DOMAIN_NAME"))
#             is_ip = True
#         except ValueError:
#             is_ip = False
#         return {"is_ip": is_ip}

#     @jwt_required()
#     def post(self):
#         parser = reqparse.RequestParser()
#         parser.add_argument("action", type=str)
#         args = parser.parse_args()
#         return util.success(gitlab_domain_connection(args["action"]))


# class GitlabDomainStatus(Resource):
#     @jwt_required()
#     def get(self):
#         return util.success(gitlab_status_connection())


# class GitlabDomainStatusV2(MethodResource):
#     @doc(tags=["Gitlab"], description="get domain status")
#     @jwt_required()
#     @marshal_with(route_model.GitGetDomainStatusRes)
#     def get(self):
#         return util.success(gitlab_status_connection())


class GitlabSingleCommit(Resource):
    @jwt_required()
    def get(self, repo_id, commit_id):
        return util.success(gitlab.single_commit(repo_id, commit_id))


class GitlabSingleCommitV2(MethodResource):
    @doc(tags=["Gitlab"], description="get single commit")
    @jwt_required()
    @marshal_with(route_model.GitGetSingleCommitRes)
    def get(self, repo_id, commit_id):
        return util.success(gitlab.single_commit(repo_id, commit_id))


@doc(tags=["Gitlab"], description="update source code len")
@use_kwargs(route_model.GitlabSourceCodeSchema, location="json")
@marshal_with(route_model.GitlabSourceCodeResponse)
class GitlabSourceCodeV2(MethodResource):
    def post(self, **kwargs):
        project_query = Project.query.filter(Project.name == kwargs["repo_name"]).first()
        update_dict = {
            "branch": kwargs["branch_name"],
            "commit_id": kwargs["commit_id"],
            "project_id": project_query.id,
            "source_code_num": kwargs["source_code_num"],
            "updated_at": datetime.utcnow().strftime(GITLAB_DATETIME_FORMAT),
        }
        result = get_source_code_info(kwargs["repo_name"], kwargs["branch_name"])
        if result:
            try:
                new = GitlabSourceCodeLens(**update_dict)
                db.session.merge(new)
                db.session.commit()
                return util.success()
            except Exception as e:
                model.db.session.rollback()
                return util.respond(401, "update failed.", error=e)
        else:
            try:
                new = GitlabSourceCodeLens(**update_dict)
                model.db.session.add(new)
                model.db.session.commit()
                return util.success()
            except Exception as e:
                model.db.session.rollback()
                return util.respond(401, "insert failed.", error=e)


# class GitlabPipelineJobConsole(Resource):
#     @jwt_required()
#     def get(self, repository_id, job_id):
#         return util.success(gitlab.get_pipeline_console(repository_id, job_id))


# class GitlabPipelineJobRetry(Resource):
#     @jwt_required()
#     def post(self, repository_id, job_id):
#         return util.success(gitlab.retry_pipeline_job(repository_id, job_id))


# class GitlabPipelineJobStop(Resource):
#     @jwt_required()
#     def post(self, repository_id, job_id):
#         return util.success(gitlab.gl_stop_pipeline_job(repository_id, job_id))
    