import os
import shutil
import re
import zipfile
from datetime import date, datetime
from functools import cmp_to_key
from io import BytesIO
import json
import uuid
from typing import Optional

from accessories import redmine_lib
from flask import send_file
from flask_jwt_extended import jwt_required, get_jwt_identity
from flask_restful import Resource, reqparse
from sqlalchemy import desc, or_
from sqlalchemy.orm import Query, joinedload
from sqlalchemy.exc import NoResultFound

import model
import nexus
import plugins
import resources.apiError as apiError
import util as util
from data.nexus_project import (
    NexusProject,
    calculate_project_issues,
    fill_rd_extra_fields,
)
from model import ProjectPluginRelation, ProjectUserRole, StarredProject, db, Project
from nexus import nx_get_project_plugin_relation
from resources.apiError import DevOpsError
from resources.starred_project import spj_unset
from accessories import redmine_lib
from util import DevOpsThread
from redminelib.exceptions import ResourceNotFoundError, ForbiddenError
from . import user, role, template
from .activity import record_activity, ActionType

from plugins.sonarqube import sonarqube_main as sonarqube
from .gitlab import gitlab, unprotect_project
from .redmine import redmine
from resources import sync_project
from resources.project_relation import get_all_sons_project, get_plan_id
from flask_apispec import doc
from flask_apispec.views import MethodResource
from resources import role
from resources.redis import update_pj_issue_calcs, get_certain_pj_issue_calc
import config
import pandas as pd


"""
1. how to use template to create project
2. create project 
    - create bot
    - three secrets
"""


def get_pj_id_by_name(name):
    ret = {"id": -1, "plan_id": -1, "repo_id": -1}
    pj_info = (
        db.session.query(ProjectPluginRelation)
        .join(Project)
        .filter(model.ProjectPluginRelation.project_id == Project.id)
        .filter(model.Project.name == name)
        .first()
    )
    if pj_info is None:
        return ret
    ret["id"] = pj_info.project_id
    ret["plan_id"] = pj_info.plan_project_id
    ret["repo_id"] = pj_info.git_repository_id
    return ret


def get_project_issue_calculation(user_id, project_ids=[]):
    from resources.sync_project import check_project_exist

    ret = []
    user_name = model.User.query.get(user_id).login
    recheck_project = False
    for project_id in project_ids:
        redmine_project_id = model.ProjectPluginRelation.query.filter_by(project_id=project_id).one().plan_project_id
        try:
            project_object = redmine_lib.rm_impersonate(user_name).project.get(redmine_project_id)
        except:
            project_object = None

        if project_object is None:
            recheck_project = True
            calculate_project_issue = {
                "id": project_id,
                "closed_count": None,
                "overdue_count": None,
                "total_count": None,
                "project_status": None,
                "updated_time": None,
                "is_lock": True,
            }
        else:
            calculate_project_issue = get_certain_pj_issue_calc(project_id)
            # rm_project = {"updated_on": project_object.updated_on, "id": project_object.id}
            # calculate_project_issue = calculate_project_issues(rm_project, user_name)
            if role.is_role(role.RD):
                calculate_project_issue.update(fill_rd_extra_fields(user_id, redmine_project_id))
            calculate_project_issue["id"] = project_id
        ret.append(calculate_project_issue)
    if recheck_project:
        check_project_exist()
    return ret


def get_project_list(user_id, role="simple", args={}, disable=None, sync=False):
    limit = args.get("limit")
    offset = args.get("offset")
    extra_data = args.get("test_result", "false") == "true"
    pj_members_count = args.get("pj_members_count", "false") == "true"
    user_name = model.User.query.get(user_id).login

    rows, counts = get_project_rows_by_user(user_id, disable, args=args)
    ret = []
    for row in rows:
        nexus_project = NexusProject().set_project_row(row).set_starred_info(user_id)
        if role == "pm":
            redmine_project_id = row.plugin_relation.plan_project_id
            try:
                if sync:
                    project_object = redmine_lib.redmine.project.get(redmine_project_id)
                else:
                    project_object = redmine_lib.rm_impersonate(user_name).project.get(redmine_project_id)
                rm_project = {
                    "updated_on": project_object.updated_on,
                    "id": project_object.id,
                }
            except (ResourceNotFoundError, ForbiddenError):
                # When Redmin project was missing
                sync_project.lock_project(nexus_project.name, "Redmine")
                rm_project = {"updated_on": datetime.utcnow().isoformat(), "id": -1}
            nexus_project = nexus_project.fill_pm_extra_fields(rm_project, user_name, sync)
        if extra_data:
            pass
            # nexus_project = nexus_project.fill_extra_fields()

        if pj_members_count:
            nexus_project = nexus_project.set_project_members()

        ret.append(nexus_project.to_json())

    if limit is not None and offset is not None:
        page_dict = util.get_pagination(counts, limit, offset)
        return {"project_list": ret, "page": page_dict}

    return ret


def get_project_rows_by_user(user_id, disable, args={}):
    search: str = args.get("search")
    accsearch: str = args.get("accsearch")
    is_empty_project: bool = args.get("is_empty_project")
    limit: int = args.get("limit")
    offset: int = args.get("offset")
    pj_due_start: Optional[date] = (
        datetime.strptime(args.get("pj_due_date_start"), "%Y-%m-%d").date()
        if args.get("pj_due_date_start", False)
        else None
    )
    pj_due_end: Optional[date] = (
        datetime.strptime(args.get("pj_due_date_end"), "%Y-%m-%d").date()
        if args.get("pj_due_date_end", False)
        else None
    )

    query: Query = model.Project.query.options(joinedload(model.Project.user_role, innerjoin=True))
    # 如果不是admin（也就是一般RD/PM/QA），取得 user_id 有參加的 project 列表
    if user.get_role_id(user_id) != role.ADMIN.id:
        query: Query = query.filter(Project.user_role.any(user_id=user_id))

    stared_project_list: list[StarredProject] = db.session.query(StarredProject).filter_by(user_id=user_id).all()
    stared_project_objects: list[Project] = [Project.query.get(_.project_id) for _ in stared_project_list]

    if disable is not None:
        query: Query = query.filter_by(disabled=disable)
        stared_project_objects: list[Project] = [
            star_project for star_project in stared_project_objects if star_project.disabled == disable
        ]

    if search is not None:
        users: list[model.User] = model.User.query.filter(model.User.name.ilike(f"%{search}%")).all()
        owner_ids: list[int] = [user.id for user in users]
        query: Query = query.filter(
            or_(
                Project.owner_id.in_(owner_ids),
                Project.display.like(f"%{search}%"),
                Project.name.like(f"%{search}%"),
            )
        )
        stared_project_objects: list[Project] = [
            star_project
            for star_project in stared_project_objects
            if star_project.owner_id in owner_ids
            or search.upper() in star_project.display.upper()
            or search.upper() in star_project.name.upper()
        ]

    if accsearch is not None and search is None:
        query: Query = query.filter(Project.name == accsearch)

    if is_empty_project is True:
        query: Query = query.filter(Project.is_empty_project == is_empty_project)

    if pj_due_start is not None and pj_due_end is not None:
        query: Query = query.filter(Project.due_date.between(pj_due_start, pj_due_end))
        stared_project_objects: list[Project] = [
            star_project
            for star_project in stared_project_objects
            if pj_due_start <= star_project.due_date <= pj_due_end
        ]

    # Remove dump_project and stared_project
    stared_project_ids: list[int] = [_.id for _ in stared_project_objects]
    stared_project_count: int = len(stared_project_ids)
    # 取全部 project
    query: Query = query.filter(~Project.id.in_([-1])).order_by(desc(Project.id))
    # 全部的 project 數量
    total_count: int = query.count()

    all_projects: list[Project] = query.all()

    def sort_func(a: Project, b: Project):
        # Case 1, both in stared_project_ids
        if a.id in stared_project_ids and b.id in stared_project_ids:
            return b.id - a.id
        # Case 2, both not in stared_project_ids
        elif a.id not in stared_project_ids and b.id not in stared_project_ids:
            return b.id - a.id
        # Case 3, a in stared_project_ids, b not in stared_project_ids
        elif a.id in stared_project_ids and b.id not in stared_project_ids:
            return -1
        # Case 4, a not in stared_project_ids, b in stared_project_ids
        elif a.id not in stared_project_ids and b.id in stared_project_ids:
            return 1
        # Fallback case
        else:
            return 0

    all_projects.sort(key=cmp_to_key(sort_func))

    if offset is None or limit is None:
        return all_projects, total_count

    return all_projects[offset : offset + limit], total_count


# 新增redmine & gitlab的project並將db相關table新增資訊
@record_activity(ActionType.CREATE_PROJECT)
def create_project(user_id, args):
    is_inherit_members = args.pop("is_inheritance_member", False)
    if args["description"] is None:
        args["description"] = ""
    if args["display"] is None:
        args["display"] = args["name"]
    if not args["owner_id"]:
        owner_id = user_id
    else:
        owner_id = args["owner_id"]
    project_name = args["name"]
    # create namespace in kubernetes

    # 取得母專案資訊
    if args.get("parent_id", None) is not None:
        parent_plan_project_id = get_plan_project_id(args.get("parent_id"))
        args["parent_plan_project_id"] = parent_plan_project_id

    # 使用 multi-thread 建立各專案
    redmine_pj_id = redmine.rm_create_project(args)["project"]["id"]
    output = gitlab.gl_create_project(args)
    gitlab_pj_id = output["id"]
    gitlab_pj_name = output["name"]
    gitlab_pj_ssh_url = output["ssh_url_to_repo"]
    gitlab_pj_http_url = output["http_url_to_repo"]
    sonarqube.sq_create_project(args["name"], args.get("display"))
    # services = ["redmine", "gitlab", "sonarqube"]
    # targets = {
    #     "redmine": redmine.rm_create_project,
    #     "gitlab": gitlab.gl_create_project,
    #     "sonarqube": sonarqube.sq_create_project,
    # }
    # service_args = {
    #     "redmine": (args,),
    #     "gitlab": (args,),
    #     "sonarqube": (args["name"], args.get("display")),
    # }
    # helper = util.ServiceBatchOpHelper(services, targets, service_args)
    # helper.run()

    # 先取出已成功的專案建立 id，以便之後可能的回溯需求
    # redmine_pj_id = None
    # gitlab_pj_id = None
    # gitlab_pj_name = None
    # gitlab_pj_ssh_url = None
    # gitlab_pj_http_url = None
    project_name = args["name"]

    # for service in services:
    #     if helper.errors[service] is None:
    #         output = helper.outputs[service]
    #         if service == "redmine":
    #             redmine_pj_id = output["project"]["id"]
    #         elif service == "gitlab":
    #             gitlab_pj_id = output["id"]
    #             gitlab_pj_name = output["name"]
    #             gitlab_pj_ssh_url = output["ssh_url_to_repo"]
    #             gitlab_pj_http_url = output["http_url_to_repo"]

    # # 如果不是全部都成功，rollback
    # if any(helper.errors.values()):
    #     for service in services:
    #         if helper.errors[service] is None:
    #             if service == "redmine":
    #                 redmine.rm_delete_project(redmine_pj_id)
    #             elif service == "gitlab":
    #                 gitlab.gl_delete_project(gitlab_pj_id)
    #             elif service == "sonarqube":
    #                 sonarqube.sq_delete_project(project_name)

    #     # 丟出服務序列在最前的錯誤
    #     for service in services:
    #         e = helper.errors[service]
    #         if e is not None:
    #             if service == "redmine":
    #                 status_code = e.status_code
    #                 resp = e.unpack_response()
    #                 if status_code == 422 and "errors" in resp:
    #                     if len(resp["errors"]) > 0:
    #                         if resp["errors"][0] == "Identifier has already been taken":
    #                             raise DevOpsError(
    #                                 status_code,
    #                                 "Redmine already used this identifier.",
    #                                 error=apiError.identifier_has_been_taken(args["name"]),
    #                             )
    #                 raise e
    #             elif service == "gitlab":
    #                 status_code = e.status_code
    #                 gitlab_json = e.unpack_response()
    #                 if status_code == 400:
    #                     try:
    #                         if gitlab_json["message"]["name"][0] == "has already been taken":
    #                             raise DevOpsError(
    #                                 status_code,
    #                                 {"gitlab": gitlab_json},
    #                                 error=apiError.identifier_has_been_taken(args["name"]),
    #                             )
    #                     except (KeyError, IndexError):
    #                         pass
    #                 raise e
    #             else:
    #                 raise e
    try:
        project_id = None
        uuids = uuid.uuid1().hex
        # enable rancher pipeline

        # add kubernetes namespace into rancher default project

        # get base_example
        template_pj_path = None
        if args.get("template_id") is not None:
            template_pj = template.get_projects_detail(args["template_id"])
            template_pj_path = template_pj.path

        # Insert into nexus database
        new_pjt = model.Project(
            name=gitlab_pj_name,
            display=args["display"],
            description=args["description"],
            ssh_url=gitlab_pj_ssh_url,
            http_url=gitlab_pj_http_url,
            disabled=args["disabled"],
            start_date=args["start_date"],
            due_date=args["due_date"],
            create_at=str(datetime.utcnow()),
            owner_id=owner_id,
            creator_id=user_id,
            base_example=template_pj_path,
            example_tag=args["tag_name"],
            uuid=uuids,
            is_inheritance_member=is_inherit_members,
            is_empty_project=args.get("template_id") is None,
        )
        db.session.add(new_pjt)
        db.session.commit()
        project_id = new_pjt.id

        # 加關聯project_plugin_relation
        new_relation = model.ProjectPluginRelation(
            project_id=project_id,
            plan_project_id=redmine_pj_id,
            git_repository_id=gitlab_pj_id,
        )
        db.session.add(new_relation)
        db.session.commit()

        # 若有父專案, 加關聯進ProjectParentSonRelation
        if args.get("parent_plan_project_id") is not None:
            new_father_son_relation = model.ProjectParentSonRelation(
                parent_id=args.get("parent_id"),
                son_id=project_id,
                created_at=datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S"),
            )
            db.session.add(new_father_son_relation)
            db.session.commit()

        # 加關聯project_user_role
        project_add_member(project_id, owner_id)
        if owner_id != user_id:
            project_add_subadmin(project_id, user_id)
        create_bot(project_id)

        # 若要繼承父專案成員, 加剩餘成員加關聯project_user_role
        if is_inherit_members and args.get("parent_plan_project_id") is not None:
            for row in (
                db.session.query(model.User, ProjectUserRole)
                .join(model.User)
                .filter(model.ProjectUserRole.project_id == args.get("parent_id"))
                .all()
            ):
                if (
                    row.User.id not in [owner_id, user_id]
                    and not row.User.login.startswith("project_bot")
                    and row.ProjectUserRole.role_id != 7
                ):
                    project_add_member(project_id, row.User.id)

        # Commit and push file by template , if template env is not None
        if args.get("template_id") is not None:
            template.tm_use_template_push_into_pj(
                args["template_id"],
                gitlab_pj_id,
                args["tag_name"],
                args["arguments"],
                uuids,
            )
        # Create project NFS folder /(uuid)
        for folder in ["pipeline", uuids]:
            project_nfs_file_path = f"./devops-data/project-data/{gitlab_pj_name}/{folder}"
            os.makedirs(project_nfs_file_path, exist_ok=True)
            os.chmod(project_nfs_file_path, 0o777)

        return {
            "project_id": project_id,
            "plan_project_id": redmine_pj_id,
            "git_repository_id": gitlab_pj_id,
            "description": args["description"],
            "project_url": f'http://{config.get("DEPLOYMENT_NAME")}/#/plan/{project_name}/overview',
        }
    except Exception as e:
        redmine.rm_delete_project(redmine_pj_id)
        gitlab.gl_delete_project(gitlab_pj_id)
        sonarqube.sq_delete_project(project_name)

        if project_id is not None:
            delete_bot(project_id)
            db.engine.execute("DELETE FROM public.project_plugin_relation WHERE project_id = '{0}'".format(project_id))
            db.engine.execute("DELETE FROM public.project_user_role WHERE project_id = '{0}'".format(project_id))
            db.engine.execute("DELETE FROM public.projects WHERE id = '{0}'".format(project_id))
        raise e


def project_add_subadmin(project_id, user_id):
    role_id = user.get_role_id(user_id)

    # Check ProjectUserRole table has relationship or not
    row = model.ProjectUserRole.query.filter_by(user_id=user_id, project_id=project_id, role_id=role_id).first()
    # if ProjectUserRole table not has relationship
    if row is not None:
        raise DevOpsError(
            422,
            "Error while adding user to project.",
            error=apiError.already_in_project(user_id, project_id),
        )
    # insert one relationship
    new = model.ProjectUserRole(project_id=project_id, user_id=user_id, role_id=role_id)
    db.session.add(new)
    db.session.commit()


def create_bot(project_id):
    # Create project BOT
    login = f"project_bot_{project_id}"
    password = util.get_random_alphanumeric_string(6, 3)
    args = {
        "name": f"專案管理機器人{project_id}號",
        "email": f"project_bot_{project_id}@nowhere.net",
        "phone": "BOTRingRing",
        "login": login,
        "password": password,
        "role_id": role.BOT.id,
        "status": "enable",
    }
    u = user.create_user(args)
    user_id = u["user_id"]
    project_add_member(project_id, user_id)
    git_user_id = u["repository_user_id"]
    git_access_token = gitlab.gl_create_access_token(git_user_id)
    sonar_access_token = sonarqube.sq_create_access_token(login)

    # Add bot secrets to rancher
    # create_kubernetes_namespace_secret(project_id, "gitlab-bot", {"git-token": git_access_token})
    # create_kubernetes_namespace_secret(project_id, "sonar-bot", {"sonar-token": sonar_access_token})
    # create_kubernetes_namespace_secret(project_id, "nexus-bot", {"username": login, "password": password})


@record_activity(ActionType.UPDATE_PROJECT)
def pm_update_project(project_id, args):
    is_inherit_members = args.get("is_inheritance_member") or False

    plugin_relation = model.ProjectPluginRelation.query.filter_by(project_id=project_id).first()
    if args["description"] is not None:
        gitlab.gl_update_project(plugin_relation.git_repository_id, args["description"])
    if args.get("parent_id", None) is not None:
        if args["parent_id"] == "":
            args["parent_plan_project_id"] = ""
        else:
            args["parent_plan_project_id"] = get_plan_project_id(int(args.get("parent_id")))

    # Update project template
    project = model.Project.query.filter_by(id=project_id).first()
    project_name = project.name
    if project.is_empty_project and args.get("template_id") is not None:
        # Because it needs force push, so remove master from protected branch list
        unprotect_project(plugin_relation.git_repository_id, "master")

        template_pj = template.get_projects_detail(args["template_id"])
        args |= {
            "is_empty_project": False,
            "base_example": template_pj.path,
            "example_tag": args["tag_name"],
        }
        template.tm_use_template_push_into_pj(
            args["template_id"],
            plugin_relation.git_repository_id,
            args["tag_name"],
            args.get("arguments"),
            project.uuid,
            force=True,
        )

    redmine.rm_update_project(plugin_relation.plan_project_id, args)
    nexus.nx_update_project(project_id, args)

    # 如果有disable, 調整專案在gitlab archive狀態
    if args.get("disabled"):
        disabled = args["disabled"]
        gitlab.gl_archive_project(plugin_relation.git_repository_id, disabled)

    # 若有父專案, 加關聯進ProjectParentSonRelation, 須等redmine更新完再寫入
    if args.get("parent_plan_project_id") is not None:
        project_relation = model.ProjectParentSonRelation.query.filter_by(son_id=project_id)
        if project_relation.first() is None:
            if args.get("parent_plan_project_id") != "":
                new_father_son_relation = model.ProjectParentSonRelation(
                    parent_id=int(args.get("parent_id")),
                    son_id=project_id,
                    created_at=datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S"),
                )
                db.session.add(new_father_son_relation)
        else:
            if args.get("parent_plan_project_id") != "":
                project_relation = project_relation.first()
                project_relation.parent_id = int(args.get("parent_id"))
                project_relation.created_at = datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")
            else:
                project_relation.delete()
        db.session.commit()

    # 若要繼承父專案成員, 加剩餘成員加關聯project_user_role
    if is_inherit_members and args.get("parent_plan_project_id") is not None:
        exist_user_ids = [row.user_id for row in model.ProjectUserRole.query.filter_by(project_id=project_id).all()]

        for row in (
            db.session.query(model.User, ProjectUserRole)
            .join(model.User)
            .filter(model.ProjectUserRole.project_id == args.get("parent_id"))
            .all()
        ):
            if (
                row.User.id not in exist_user_ids
                and row.User.id != args.get("owner_id")
                and not row.User.login.startswith("project_bot")
                and row.ProjectUserRole.role_id != 7
            ):
                project_add_member(project_id, row.User.id)

    # 檢查是否要變更 DISPLAY，若有要一起變更 SONARQUBE 的 PROJECT NAME
    if args.get("display") is not None:
        sonar_url = config.get("SONARQUBE_EXTERNAL_BASE_URL")
        sonar_token = config.get("SONARQUBE_ADMIN_TOKEN")
        project_key = project_name
        project_name = args.get("display")
        sonar_host = 'sonar.host.url="' + sonar_url + '"'
        sonar_login = 'sonar.login="' + sonar_token + '"'
        sonar_projectkey = 'sonar.projectKey="' + project_key + '"'
        sonar_projectname = 'sonar.projectName="' + project_name + '"'
        # sonar_rename = (".\\sonar-scanner -D " + sonar_host + " -D " + sonar_login + " -D " + sonar_projectkey +
        #                 " -D " + sonar_projectname)
        # os.system("cd .\\sonar-scanner\\bin &&" + sonar_rename)
        # 以上為 WINDOWS 環境的執行指令，以下為 LINUX 的執行執令
        sonar_rename = (
            "./sonar-scanner -D"
            + sonar_host
            + " -D"
            + sonar_login
            + " -D"
            + sonar_projectkey
            + " -D"
            + sonar_projectname
        )
        os.system("cd " + sonarqube.SONAR_SCAN_PATH + " && " + sonar_rename)


@record_activity(ActionType.UPDATE_PROJECT)
def nexus_update_project(project_id, args):
    nexus.nx_update_project(project_id, args)


def try_to_delete(delete_method, argument):
    try:
        delete_method(argument)
    except DevOpsError as e:
        if e.status_code != 404:
            raise e


def delete_project(project_id):
    # Check project has son project and get all ids
    son_id_list = get_all_sons_project(project_id, [])
    delete_id_list = [project_id] + son_id_list

    for project_id in delete_id_list:
        delete_project_helper(project_id)
    return util.success()


# 用project_id刪除redmine & gitlab的project並將db的相關table欄位一併刪除


@record_activity(ActionType.DELETE_PROJECT)
def delete_project_helper(project_id):

    # 取得gitlab & redmine project_id
    relation = nx_get_project_plugin_relation(nexus_project_id=project_id)
    if relation is None:
        # 如果 project table 有髒資料，將其移除
        corr = model.Project.query.filter_by(id=project_id).first()
        if corr is not None:
            db.session.delete(corr)
            db.session.commit()
            return util.success()
        else:
            raise DevOpsError(
                404,
                "Error while deleting project.",
                error=apiError.project_not_found(project_id),
            )
    redmine_project_id = relation.plan_project_id
    gitlab_project_id = relation.git_repository_id
    project_name = nexus.nx_get_project(id=project_id).name

    delete_bot(project_id)

    try_to_delete(gitlab.gl_delete_project, gitlab_project_id)
    try_to_delete(redmine.rm_delete_project, redmine_project_id)
    try_to_delete(sonarqube.sq_delete_project, project_name)

    redmine_pj = model.RedmineProject.query.filter_by(project_id=project_id).first()
    if redmine_pj is not None:
        db.engine.execute("DELETE FROM public.redmine_project WHERE project_id = '{0}'".format(project_id))

    # 如果gitlab & redmine project都成功被刪除則繼續刪除db內相關tables欄位
    db.engine.execute("DELETE FROM public.project_plugin_relation WHERE project_id = '{0}'".format(project_id))
    db.engine.execute("DELETE FROM public.project_user_role WHERE project_id = '{0}'".format(project_id))
    db.engine.execute("DELETE FROM public.projects WHERE id = '{0}'".format(project_id))

    # Delete project NFS folder
    project_nfs_file_path = f"./devops-data/project-data/{project_name}"
    if os.path.isdir(project_nfs_file_path):
        shutil.rmtree(project_nfs_file_path)


def delete_bot(project_id):
    row = model.ProjectUserRole.query.filter_by(project_id=project_id, role_id=role.BOT.id).first()
    if row is None:
        return
    user.delete_user(row.user_id)
    # delete_kubernetes_namespace_secret(project_id, "gitlab-bot")
    # delete_kubernetes_namespace_secret(project_id, "sonar-bot")
    # delete_kubernetes_namespace_secret(project_id, "nexus-bot")


def get_project_info(project_id):
    return NexusProject().set_project_id(project_id, do_query=True).to_json()


@record_activity(ActionType.ADD_MEMBER)
def project_add_member(project_id, user_id):
    role_id = user.get_role_id(user_id)

    # Check ProjectUserRole table has relationship or not
    row = model.ProjectUserRole.query.filter_by(user_id=user_id, project_id=project_id, role_id=role_id).first()
    # if ProjectUserRole table not has relationship
    if row is not None:
        raise DevOpsError(
            422,
            "Error while adding user to project.",
            error=apiError.already_in_project(user_id, project_id),
        )
    # insert one relationship
    new = model.ProjectUserRole(project_id=project_id, user_id=user_id, role_id=role_id)
    db.session.add(new)
    db.session.commit()

    user_relation = nexus.nx_get_user_plugin_relation(user_id=user_id)
    project_relation = nx_get_project_plugin_relation(nexus_project_id=project_id)
    redmine_role_id = user.to_redmine_role_id(role_id)

    # get project name
    pj_row = model.Project.query.filter_by(id=project_id).one()
    # get user name
    ur_row = model.User.query.filter_by(id=user_id).one()

    services = ["redmine", "gitlab", "sonarqube"]
    targets = {
        "redmine": redmine.rm_create_memberships,
        "gitlab": gitlab.gl_project_add_member,
        "sonarqube": sonarqube.sq_add_member,
    }
    service_args = {
        "redmine": (
            project_relation.plan_project_id,
            user_relation.plan_user_id,
            redmine_role_id,
        ),
        "gitlab": (
            project_relation.git_repository_id,
            user_relation.repository_user_id,
        ),
        "sonarqube": (pj_row.name, ur_row.login),
    }
    helper = util.ServiceBatchOpHelper(services, targets, service_args)
    helper.run()
    for e in helper.errors.values():
        if e is not None:
            raise e

    return util.success()


@record_activity(ActionType.REMOVE_MEMBER)
def project_remove_member(project_id, user_id):
    role_id = user.get_role_id(user_id)
    project = model.Project.query.filter_by(id=project_id).first()
    if project.owner_id == user_id:
        raise apiError.DevOpsError(
            404,
            "Error while removing a member from the project.",
            error=apiError.is_project_owner_in_project(user_id, project_id),
        )

    user_relation = nexus.nx_get_user_plugin_relation(user_id=user_id)
    project_relation = nx_get_project_plugin_relation(nexus_project_id=project_id)
    if project_relation is None:
        raise apiError.DevOpsError(
            404,
            "Error while removing a member from the project.",
            error=apiError.project_not_found(project_id),
        )

    # get membership id
    memberships = redmine.rm_get_memberships_list(project_relation.plan_project_id)
    redmine_membership_id = None
    for membership in memberships["memberships"]:
        if membership["user"]["id"] == user_relation.plan_user_id:
            redmine_membership_id = membership["id"]
    if redmine_membership_id is not None:
        # delete membership
        try:
            redmine.rm_delete_memberships(redmine_membership_id)
        except DevOpsError as e:
            if e.status_code == 404:
                # Already deleted, let it go
                pass
            else:
                raise e
    else:
        # Redmine does not have this membership, just let it go
        pass

    try:
        gitlab.gl_project_delete_member(project_relation.git_repository_id, user_relation.repository_user_id)
    except DevOpsError as e:
        if e.status_code != 404:
            raise e

    # get project name
    pj_row = model.Project.query.filter_by(id=project_id).one()
    # get user name
    ur_row = model.User.query.filter_by(id=user_id).one()

    try:
        sonarqube.sq_remove_member(pj_row.name, ur_row.login)
    except DevOpsError as e:
        if e.status_code != 404:
            raise e

    # delete relationship from ProjectUserRole table.
    try:
        row = model.ProjectUserRole.query.filter_by(project_id=project_id, user_id=user_id, role_id=role_id).one()
    except NoResultFound:
        raise apiError.DevOpsError(
            404,
            "Relation not found, project_id={0}, role_id={1}.".format(project_id, role_id),
            error=apiError.user_not_found(user_id),
        )
    db.session.delete(row)
    db.session.commit()
    spj_unset(user_id, project_id)
    return util.success()


# May throws NoResultFound
def get_plan_project_id(project_id):
    return model.ProjectPluginRelation.query.filter_by(project_id=project_id).one().plan_project_id


def get_project_by_plan_project_id(plan_project_id):
    result = db.engine.execute(
        "SELECT * FROM public.project_plugin_relation" " WHERE plan_project_id = {0}".format(plan_project_id)
    )
    project = result.fetchone()
    result.close()
    return project


def get_test_summary(project_id):
    """
    -1: fail
    0: No lastest
    1: success
    2: running
    """
    ret = {}
    project_name = nexus.nx_get_project(id=project_id).name
    not_found_ret = {
        "message": "",
        "status": 0,
        "result": {},
        "run_at": None,
    }

    def not_found_ret_message(plugin):
        return f"The latest scan is not Found in the {plugin} server"

    # sonarqube ..
    # if not plugins.get_plugin_config("sonarqube")["disabled"]:
    items = sonarqube.sq_get_current_measures(project_name)
    if items != []:
        sonar_result = {"result": {item["metric"]: item["value"] for item in items if item["metric"] != "run_at"}}

        sonar_result.update(
            {
                "message": "success",
                "status": 1,
                "run_at": items[-1]["value"] if items[-1]["metric"] == "run_at" else None,
            }
        )
        ret["sonarqube"] = sonar_result
    else:
        not_found_ret["message"] = not_found_ret_message("sonarqube")
        ret["sonarqube"] = not_found_ret.copy()

    return util.success({"test_results": ret})


def get_all_reports(project_id):
    project_name = nexus.nx_get_project(id=project_id).name
    memory_file = BytesIO()
    with zipfile.ZipFile(memory_file, "w", zipfile.ZIP_DEFLATED) as zf:
        # newman
        if not plugins.get_plugin_config("postman")["disabled"]:
            row = (
                model.TestResults.query.filter_by(project_id=project_id)
                .order_by(desc(model.TestResults.id))
                .limit(1)
                .first()
            )
            if row is not None:
                zf.writestr("postman.json", row.report)

        if not plugins.get_plugin_config("sonarqube")["disabled"]:
            zf.writestr("sonarqube.json", str(sonarqube.sq_get_current_measures(project_name)))

    memory_file.seek(0)
    return memory_file


def get_plugin_usage(project_id):
    project_plugin_relation = model.ProjectPluginRelation.query.filter_by(project_id=project_id).first()
    plugin_info = []
    # plugin_info.append(harbor.get_storage_usage(project_plugin_relation.harbor_project_id))
    plugin_info.append(gitlab.gl_get_storage_usage(project_plugin_relation.git_repository_id))
    return util.success(plugin_info)


def check_project_args_patterns(args):
    keys_to_check = ["name", "display", "description"]
    for key in keys_to_check:
        if args.get(key, None):
            if key != "name":
                pattern = "&|<"
                result = re.findall(pattern, args[key])
                if any(result):
                    raise apiError.DevOpsError(
                        400,
                        "Error while creating project.",
                        error=apiError.invalid_project_content(key, args[key]),
                    )
            else:
                pattern = "^[a-z][a-z0-9-]{0,28}[a-z0-9]$"
                result = re.findall(pattern, args[key])
                if result is None:
                    raise apiError.DevOpsError(
                        400,
                        "Error while creating project.",
                        error=apiError.invalid_project_name(args[key]),
                    )


def check_project_owner_id(new_owner_id, user_id, project_id):
    origin_owner_id = model.Project.query.get(project_id).owner_id
    # 你是皇帝，你說了算
    if role.is_role(role.ADMIN):
        pass
    # 不更動 owner_id，僅修改其他資訊 (由 project 中 owner 的 PM 執行)
    elif origin_owner_id == user_id and new_owner_id == user_id:
        pass
    # 更動 owner_id (由 project 中 owner 的 PM 執行)
    elif origin_owner_id == user_id and new_owner_id != user_id:
        # 檢查 new_owner_id 的 role 是否為 PM
        if not bool(
            model.ProjectUserRole.query.filter_by(project_id=project_id, user_id=new_owner_id, role_id=3).all()
        ):
            raise apiError.DevOpsError(
                400,
                "Error while updating project info.",
                error=apiError.invalid_project_owner(new_owner_id),
            )
    # 不更動 owner_id，僅修改其他資訊 (由 project 中其他 PM 執行)
    elif origin_owner_id != user_id and new_owner_id == origin_owner_id:
        pass
    # 其餘權限不足
    else:
        raise apiError.NotAllowedError("Error while updating project info.")


def get_projects_by_user(user_id):
    try:
        model.ProjectUserRole.query.filter_by(project_id=-1, user_id=user_id).one()
    except NoResultFound:
        raise apiError.DevOpsError(
            404,
            "User id {0} does not exist.".format(user_id),
            apiError.user_not_found(user_id),
        )
    projects_id_list = [
        pj_id[0]
        for pj_id in model.ProjectUserRole.query.filter_by(user_id=user_id).with_entities(
            model.ProjectUserRole.project_id
        )
    ]
    projects = [NexusProject().set_project_id(id).to_json() for id in projects_id_list if id != -1]
    return projects


def sync_project_issue_calculate():
    project_issue_calculate = {}
    for project in model.Project.query.all():
        pj_id = project.id
        plan_id = get_plan_id(project.id)
        if plan_id != -1:
            try:
                project_object = redmine_lib.redmine.project.get(plan_id)
                rm_project = {
                    "updated_on": project_object.updated_on,
                    "id": project_object.id,
                }
                project_issue_calculate[pj_id] = json.dumps(
                    calculate_project_issues(rm_project, username=None, sync=True)
                )
            except:
                continue

    update_pj_issue_calcs(project_issue_calculate)


# --------------------- Resources ---------------------
