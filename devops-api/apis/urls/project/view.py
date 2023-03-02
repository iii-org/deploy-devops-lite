from flask_apispec import marshal_with, doc, use_kwargs
from flask_apispec.views import MethodResource
from flask_jwt_extended import jwt_required, get_jwt_identity
from flask_restful import Resource, reqparse
import util
import ast
import model
from threading import Thread
from resources.project_relation import (
    project_has_child,
    get_root_project_id,
    sync_project_relation,
    get_project_family_members_by_user,
    get_relation_list,
    remove_relation,
    get_all_relation_project,
    project_has_parent,
)
from resources.issue import (
    get_issue_list_by_project_helper,
    get_issue_by_tree_by_project,
    get_issue_by_status_by_project,
    get_issue_progress_or_statistics_by_project,
    get_issue_by_date_by_project,
    get_custom_issue_filter,
    create_custom_issue_filter,
    put_custom_issue_filter,
    get_lock_status,
    DownloadIssueAsExcel,
    pj_download_file_is_exist,
)
from resources import project, user, version, wiki, release
from resources.gitlab import gitlab
from resources.project_permission import (
    get_project_issue_check,
    create_project_issue_check,
    update_project_issue_check,
    delete_project_issue_check,
)
from resources.resource_storage import (
    get_project_resource_storage_level,
    update_project_resource_storage_level,
)

from sqlalchemy.exc import NoResultFound
from model import CustomIssueFilter
from resources import role
from . import router_model
from urls.issue.router_model import FileSchema
from model import db
from resources.apiError import DevOpsError
import resources.apiError as apiError
import threading
from flask import send_file
import nexus
from resources.redmine import redmine, get_redmine_obj
import werkzeug


##### Project Relation ######


@doc(tags=["Project"], description="Check project has son project or not")
@marshal_with(router_model.CheckhasSonProjectResponse)
class CheckhasSonProjectV2(MethodResource):
    @jwt_required()
    def get(self, project_id):
        return {"has_child": project_has_child(project_id)}


class CheckhasSonProject(Resource):
    @jwt_required()
    def get(self, project_id):
        return {"has_child": project_has_child(project_id)}


@doc(tags=["Project"], description="Check project has father, son project or not")
@marshal_with(router_model.CheckRelationProjectResponse)
class CheckhasRelationProjectV2(MethodResource):
    @jwt_required()
    def get(self, project_id):
        has_father, has_child = project_has_parent(project_id), project_has_child(project_id)
        return {
            "has_relations": has_father or has_child,
            "has_father": has_father,
            "has_child": has_child,
        }


class CheckhasRelationProject(Resource):
    @jwt_required()
    def get(self, project_id):
        has_father, has_child = project_has_parent(project_id), project_has_child(project_id)
        return {
            "has_relations": has_father or has_child,
            "has_father": has_father,
            "has_child": has_child,
        }


@doc(tags=["Project"], description="Gey root project_id")
@marshal_with(router_model.GetProjectRootIDResponse)
class GetProjectRootIDV2(MethodResource):
    @jwt_required()
    def get(self, project_id):
        return {"root_project_id": get_root_project_id(project_id)}


class GetProjectRootID(Resource):
    @jwt_required()
    def get(self, project_id):
        return {"root_project_id": get_root_project_id(project_id)}


@doc(tags=["Sync"], description="Sync IIIDevops project's relationship with Redmine")
@marshal_with(util.CommonResponse)
class SyncProjectRelationV2(MethodResource):
    @jwt_required()
    def post(self):
        Thread(target=sync_project_relation).start()
        return util.success()


class SyncProjectRelation(Resource):
    @jwt_required()
    def post(self):
        Thread(target=sync_project_relation).start()
        return util.success()


@doc(tags=["Project"], description="Get all sons' project members")
@marshal_with(router_model.GetProjectFamilymembersByUserResponse)
class GetProjectFamilymembersByUserV2(MethodResource):
    @jwt_required()
    def get(self, project_id):
        return util.success(get_project_family_members_by_user(project_id))


class GetProjectFamilymembersByUser(Resource):
    @jwt_required()
    def get(self, project_id):
        return util.success(get_project_family_members_by_user(project_id))


class ProjectRelationV2(MethodResource):
    @doc(tags=["Project"], description="Get all sons' project id")
    @marshal_with(router_model.ProjectRelationGetResponse)
    @jwt_required()
    def get(self, project_id):
        return util.success(get_relation_list(project_id, []))

    @doc(tags=["Project"], description="Delete specific project and subproject relation")
    @use_kwargs(router_model.ProjectRelationDeleteSchema, location="form")
    @jwt_required()
    def delete(self, project_id, **kwargs):
        return remove_relation(project_id, kwargs["parent_id"])


class ProjectRelation(Resource):
    @jwt_required()
    def get(self, project_id):
        return util.success(get_relation_list(project_id, []))

    @jwt_required()
    def delete(self, project_id):
        parser = reqparse.RequestParser()
        parser.add_argument("parent_id", type=int, required=True, location="args")
        args = parser.parse_args()
        return remove_relation(project_id, args["parent_id"])


class ProjectRelationsV2(MethodResource):
    @doc(tags=["Project"], description="Get all parents' and sons' project id")
    @marshal_with(router_model.ProjectRelationsGetResponse)
    @jwt_required()
    def get(self, project_id):
        return util.success(get_all_relation_project(project_id))


##### Project issue_list ######


@doc(tags=["Issue"], description="Get issue list by project")
@use_kwargs(router_model.IssueByProjectSchema, location="query")
@marshal_with(router_model.IssueByProjectResponse, code=200)
@marshal_with(router_model.IssueByProjectResponseWithPage, code="with_pagination")
class IssueByProjectV2(MethodResource):
    @jwt_required()
    def get(self, project_id, **kwargs):
        role.require_in_project(project_id, "Error to get issue.")
        kwargs["project_id"] = project_id
        if kwargs.get("search") is not None and len(kwargs["search"]) < 2:
            output = []
        else:
            output = get_issue_list_by_project_helper(project_id, kwargs, operator_id=get_jwt_identity()["user_id"])
        return util.success(output)


class IssueByProject(Resource):
    @jwt_required()
    def get(self, project_id):
        role.require_in_project(project_id, "Error to get issue.")
        parser = reqparse.RequestParser()
        parser.add_argument("fixed_version_id", type=str, location="args")
        parser.add_argument("status_id", type=str, location="args")
        parser.add_argument("tracker_id", type=str, location="args")
        parser.add_argument("assigned_to_id", type=str, location="args")
        parser.add_argument("priority_id", type=str, location="args")
        parser.add_argument("only_superproject_issues", type=bool, default=False, location="args")
        parser.add_argument("limit", type=int, location="args")
        parser.add_argument("offset", type=int, location="args")
        parser.add_argument("search", type=str, location="args")
        parser.add_argument("selection", type=str, location="args")
        parser.add_argument("sort", type=str, location="args")
        parser.add_argument("parent_id", type=str, location="args")
        parser.add_argument("due_date_start", type=str, location="args")
        parser.add_argument("due_date_end", type=str, location="args")
        parser.add_argument("with_point", type=bool, location="args")
        parser.add_argument("tags", type=str, location="args")
        args = parser.parse_args()
        args["project_id"] = project_id
        if args.get("search") is not None and len(args["search"]) < 2:
            output = []
        else:
            output = get_issue_list_by_project_helper(project_id, args, operator_id=get_jwt_identity()["user_id"])
        return util.success(output)


@doc(tags=["Issue"], description="Get issue list by tree by project")
# @marshal_with(route_model.IssueByTreeByProjectResponse)
class IssueByTreeByProjectV2(MethodResource):
    @jwt_required()
    def get(self, project_id):
        role.require_in_project(project_id, "Error to get issue.")
        output = get_issue_by_tree_by_project(project_id)
        return util.success(output)


class IssueByTreeByProject(Resource):
    @jwt_required()
    def get(self, project_id):
        role.require_in_project(project_id, "Error to get issue.")
        output = get_issue_by_tree_by_project(project_id)
        return util.success(output)


@doc(tags=["Issue"], description="Get issue list by status by project")
@marshal_with(router_model.IssueByStatusByProjectResponse)
class IssueByStatusByProjectV2(MethodResource):
    @jwt_required()
    def get(self, project_id):
        role.require_in_project(project_id)
        return get_issue_by_status_by_project(project_id)


class IssueByStatusByProject(Resource):
    @jwt_required()
    def get(self, project_id):
        role.require_in_project(project_id)
        return get_issue_by_status_by_project(project_id)


@doc(tags=["Issue"], description="Get issue Progress by tree by project")
@use_kwargs(router_model.IssuesProgressByProjectSchema, location="query")
@marshal_with(router_model.IssuesProgressByProjectResponse)
class IssuesProgressByProjectV2(MethodResource):
    @jwt_required()
    def get(self, project_id, **kwargs):
        role.require_in_project(project_id)
        output = get_issue_progress_or_statistics_by_project(project_id, kwargs, progress=True)
        return util.success(output)


class IssuesProgressByProject(Resource):
    @jwt_required()
    def get(self, project_id):
        role.require_in_project(project_id)
        parser = reqparse.RequestParser()
        parser.add_argument("fixed_version_id", type=int, location="args")
        parser.add_argument("due_date_status", type=str, location="args")
        args = parser.parse_args()
        output = get_issue_progress_or_statistics_by_project(project_id, args, progress=True)
        return util.success(output)


@doc(tags=["Issue"], description="Get issue Progress by tree by project")
@use_kwargs(router_model.IssuesProgressByProjectSchema, location="query")
@marshal_with(router_model.IssuesStatisticsByProjectResponse)
class IssuesStatisticsByProjectV2(MethodResource):
    @jwt_required()
    def get(self, project_id, **kwargs):
        role.require_in_project(project_id)
        output = get_issue_progress_or_statistics_by_project(project_id, kwargs, statistics=True)
        return util.success(output)


class IssuesStatisticsByProject(Resource):
    @jwt_required()
    def get(self, project_id):
        role.require_in_project(project_id)
        parser = reqparse.RequestParser()
        parser.add_argument("fixed_version_id", type=int, location="args")
        parser.add_argument("due_date_status", type=str, location="args")
        args = parser.parse_args()
        output = get_issue_progress_or_statistics_by_project(project_id, args, statistics=True)
        return util.success(output)


@doc(tags=["Pending"], description="Get issue list by date")
class IssueByDateByProjectV2(MethodResource):
    @jwt_required()
    def get(self, project_id):
        role.require_in_project(project_id)
        return get_issue_by_date_by_project(project_id)


class IssueByDateByProject(Resource):
    @jwt_required()
    def get(self, project_id):
        role.require_in_project(project_id)
        return get_issue_by_date_by_project(project_id)


##### Filter issue by project ######


class IssueFilterByProjectV2(MethodResource):
    @doc(tags=["Project"], description="Get project's issues' filter.")
    @marshal_with(router_model.IssueFilterByProjectGetResponse)
    @jwt_required()
    def get(self, project_id):
        return util.success(get_custom_issue_filter(get_jwt_identity()["user_id"], project_id))

    @doc(tags=["Project"], description="Create project's issues' filter.")
    @use_kwargs(router_model.IssueFilterByProjectPostAndPutSchema, location="form")
    @marshal_with(router_model.IssueFilterByProjectPostResponse)
    @jwt_required()
    def post(self, project_id, **kwargs):
        user_id = get_jwt_identity()["user_id"]

        if kwargs["type"] != "issue_board" and kwargs.get("group_by") is not None:
            raise DevOpsError(
                400,
                "Column group_by is only available when type is issue_board",
                error=apiError.argument_error("group_by"),
            )
        if kwargs["type"] != "my_work" and kwargs.get("focus_tab") is not None:
            raise DevOpsError(
                400,
                "Column focus_tab is only available when type is my_work",
                error=apiError.argument_error("focus_tab"),
            )

        return util.success(create_custom_issue_filter(user_id, project_id, kwargs))


class IssueFilterByProjectWithFilterIDV2(MethodResource):
    @doc(tags=["Project"], description="Update project's issues' filter.")
    @use_kwargs(router_model.IssueFilterByProjectPostAndPutSchema, location="form")
    @marshal_with(router_model.IssueFilterByProjectPutResponse)
    @jwt_required()
    def put(self, project_id, custom_filter_id, **kwargs):
        if kwargs["type"] != "issue_board" and kwargs.get("group_by") is not None:
            raise DevOpsError(
                400,
                "Column group_by is only available when type is issue_board",
                error=apiError.argument_error("group_by"),
            )
        if kwargs["type"] != "my_work" and kwargs.get("focus_tab") is not None:
            raise DevOpsError(
                400,
                "Column focus_tab is only available when type is my_work",
                error=apiError.argument_error("focus_tab"),
            )

        return util.success(put_custom_issue_filter(custom_filter_id, project_id, kwargs))

    @doc(tags=["Project"], description="Delete project's issues' filter.")
    @jwt_required()
    def delete(self, project_id, custom_filter_id):
        CustomIssueFilter.query.filter_by(id=custom_filter_id).delete()
        db.session.commit()


class IssueFilterByProject(Resource):
    @jwt_required()
    def get(self, project_id):
        return util.success(get_custom_issue_filter(get_jwt_identity()["user_id"], project_id))

    @jwt_required()
    def post(self, project_id):
        user_id = get_jwt_identity()["user_id"]
        parser = reqparse.RequestParser()
        parser.add_argument("name", type=str, required=True)
        parser.add_argument("type", type=str, required=True)
        parser.add_argument("assigned_to_id", type=str)
        parser.add_argument("fixed_version_id", type=str)
        parser.add_argument("focus_tab", type=str)
        parser.add_argument("group_by", type=dict)
        parser.add_argument("priority_id", type=str)
        parser.add_argument("show_closed_issues", type=bool)
        parser.add_argument("show_closed_versions", type=bool)
        parser.add_argument("status_id", type=str)
        parser.add_argument("tags", type=str)
        parser.add_argument("tracker_id", type=str)
        args = parser.parse_args()

        if args["type"] != "issue_board" and args.get("group_by") is not None:
            raise DevOpsError(
                400,
                "Column group_by is only available when type is issue_board",
                error=apiError.argument_error("group_by"),
            )
        if args["type"] != "my_work" and args.get("focus_tab") is not None:
            raise DevOpsError(
                400,
                "Column focus_tab is only available when type is my_work",
                error=apiError.argument_error("focus_tab"),
            )

        return util.success(create_custom_issue_filter(user_id, project_id, args))

    @jwt_required()
    def put(self, project_id, custom_filter_id):
        parser = reqparse.RequestParser()
        parser.add_argument("name", type=str, required=True)
        parser.add_argument("type", type=str, required=True)
        parser.add_argument("assigned_to_id", type=str)
        parser.add_argument("fixed_version_id", type=str)
        parser.add_argument("focus_tab", type=str)
        parser.add_argument("group_by", type=dict)
        parser.add_argument("priority_id", type=str)
        parser.add_argument("show_closed_issues", type=bool)
        parser.add_argument("show_closed_versions", type=bool)
        parser.add_argument("status_id", type=str)
        parser.add_argument("tags", type=str)
        parser.add_argument("tracker_id", type=str)
        args = parser.parse_args()

        if args["type"] != "issue_board" and args.get("group_by") is not None:
            raise DevOpsError(
                400,
                "Column group_by is only available when type is issue_board",
                error=apiError.argument_error("group_by"),
            )
        if args["type"] != "my_work" and args.get("focus_tab") is not None:
            raise DevOpsError(
                400,
                "Column focus_tab is only available when type is my_work",
                error=apiError.argument_error("focus_tab"),
            )

        return util.success(put_custom_issue_filter(custom_filter_id, project_id, args))

    @jwt_required()
    def delete(self, project_id, custom_filter_id):
        CustomIssueFilter.query.filter_by(id=custom_filter_id).delete()
        db.session.commit()


##### Download project issue as excel ######


class DownloadProjectExecuteV2(MethodResource):
    # download/execute
    @doc(tags=["Issue"], description="Execute download project's issues as excel.")
    @use_kwargs(router_model.DownloadProjectSchema, location="form")
    @marshal_with(util.CommonResponse)
    @jwt_required()
    def post(self, project_id, **kwargs):
        if get_lock_status("download_pj_issues")["is_lock"]:
            return util.success("previous is still running")
        download_issue_excel = DownloadIssueAsExcel(kwargs, project_id, get_jwt_identity()["user_id"])
        threading.Thread(target=download_issue_excel.execute).start()
        return util.success()


class DownloadProjectIsExistV2(MethodResource):
    # download/is_exist
    @doc(tags=["Issue"], description="Check excel file is exist.")
    @marshal_with(router_model.DownloadProjectIsExistResponse)
    @jwt_required()
    def get(self, project_id):
        return util.success(pj_download_file_is_exist(project_id))


class DownloadProjectV2(MethodResource):
    # download/execute
    @doc(tags=["Issue"], description="Download project's issues' excel.")
    @jwt_required()
    def patch(self, project_id):
        if not pj_download_file_is_exist(project_id)["file_exist"]:
            raise apiError.DevOpsError(
                404,
                "This file can not be downloaded because it is not exist.",
                apiError.project_issue_file_not_exits(project_id),
            )

        return send_file(f"../logs/project_excel_file/{project_id}.xlsx")


class DownloadProject(Resource):
    # download/execute
    @jwt_required()
    def post(self, project_id):
        parser = reqparse.RequestParser()
        parser.add_argument("fixed_version_id", type=str)
        parser.add_argument("status_id", type=str)
        parser.add_argument("tracker_id", type=str)
        parser.add_argument("assigned_to_id", type=str)
        parser.add_argument("priority_id", type=str)
        parser.add_argument("only_superproject_issues", type=bool, default=False)
        parser.add_argument("search", type=str)
        parser.add_argument("selection", type=str)
        parser.add_argument("sort", type=str)
        parser.add_argument("parent_id", type=str)
        parser.add_argument("due_date_start", type=str)
        parser.add_argument("due_date_end", type=str)
        parser.add_argument("with_point", type=bool, default=True)
        parser.add_argument("tags", type=str)
        parser.add_argument("levels", type=int, default=3)
        parser.add_argument("deploy_column", type=dict, action="append", required=True)
        args = parser.parse_args()

        if get_lock_status("download_pj_issues")["is_lock"]:
            return util.success("previous is still running")

        # Because QA not the member of any project, so it will get error when it get issue by user_id.
        user_id = get_jwt_identity()["user_id"] if get_jwt_identity()["role_id"] != 7 else 1

        download_issue_excel = DownloadIssueAsExcel(args, project_id, user_id)
        threading.Thread(target=download_issue_excel.execute).start()
        return util.success()

    # download/is_exist
    @jwt_required()
    def get(self, project_id):
        return util.success(pj_download_file_is_exist(project_id))

    # download/execute
    @jwt_required()
    def patch(self, project_id):
        if not pj_download_file_is_exist(project_id)["file_exist"]:
            raise apiError.DevOpsError(
                404,
                "This file can not be downloaded because it is not exist.",
                apiError.project_issue_file_not_exits(project_id),
            )

        return send_file(f"../logs/project_excel_file/{project_id}.xlsx")


##### List project ######
@doc(tags=["Project"], description="List projects")
@use_kwargs(router_model.ListMyProjectsSchema, location="query")
@marshal_with(router_model.ListMyProjectsResponse)
class ListMyProjectsV2(MethodResource):
    @jwt_required()
    def get(self, **kwargs):
        disabled = None
        if kwargs.get("disabled") is not None:
            disabled = kwargs["disabled"] == 1
        if kwargs.get("simple", "false") == "true":
            return util.success(
                {"project_list": project.get_project_list(get_jwt_identity()["user_id"], "simple", kwargs, disabled)}
            )
        else:
            return util.success(
                {"project_list": project.get_project_list(get_jwt_identity()["user_id"], "pm", kwargs, disabled)}
            )


class ListMyProjects(Resource):
    @jwt_required()
    def get(self):
        parser = reqparse.RequestParser()
        parser.add_argument("simple", type=str, location="args")
        parser.add_argument("limit", type=int, location="args")
        parser.add_argument("offset", type=int, location="args")
        parser.add_argument("search", type=str, location="args")
        parser.add_argument("accsearch", type=str, location="args")
        parser.add_argument("is_empty_project", type=bool, location="args")
        parser.add_argument("disabled", type=int, location="args")
        parser.add_argument("pj_members_count", type=str, location="args")
        parser.add_argument("pj_due_date_start", type=str, location="args")
        parser.add_argument("pj_due_date_end", type=str, location="args")
        parser.add_argument("test_result", type=str, location="args")
        args = parser.parse_args()
        disabled = None
        if args.get("disabled") is not None:
            disabled = args["disabled"] == 1
        if args.get("simple", "false") == "true":
            return util.success(
                {"project_list": project.get_project_list(get_jwt_identity()["user_id"], "simple", args, disabled)}
            )
        else:
            return util.success(
                {"project_list": project.get_project_list(get_jwt_identity()["user_id"], "pm", args, disabled)}
            )


@doc(tags=["Project"], description="List projects calculated issues count")
@use_kwargs(router_model.CalculateProjectIssuesSchema, location="query")
@marshal_with(router_model.CalculateProjectIssuesResponse)
class CalculateProjectIssuesV2(MethodResource):
    @jwt_required()
    def get(self, **kwargs):

        project_ids = kwargs.get("project_ids").split(",")

        return util.success(
            {"project_list": project.get_project_issue_calculation(get_jwt_identity()["user_id"], project_ids)}
        )


class CalculateProjectIssues(Resource):
    @jwt_required()
    def get(self):
        parser = reqparse.RequestParser()
        parser.add_argument("project_ids", type=str, required=True, location="args")
        args = parser.parse_args()
        project_ids = args.get("project_ids").split(",")

        return util.success(
            {"project_list": project.get_project_issue_calculation(get_jwt_identity()["user_id"], project_ids)}
        )


@doc(tags=["Project"], description="List projects by user")
@marshal_with(router_model.ListMyProjectsByUserResponse)
class ListProjectsByUserV2(MethodResource):
    @jwt_required()
    def get(self, user_id):
        role.require_pm("Error while get project by user.")
        projects = project.get_projects_by_user(user_id)
        return util.success(projects)


class ListProjectsByUser(Resource):
    @jwt_required()
    def get(self, user_id):
        role.require_pm("Error while get project by user.")
        projects = project.get_projects_by_user(user_id)
        return util.success(projects)


class SyncProjectIssueCalculateV2(MethodResource):
    @doc(tags=["System"], description="Sync project's issue calculate.")
    @jwt_required()
    def post(self):
        return util.success(project.sync_project_issue_calculate())


##### Single project ######


class SingleProjectV2(MethodResource):
    @doc(tags=["Project"], description="Get project info")
    @marshal_with(router_model.SingleProjectGetResponse)
    @jwt_required()
    def get(self, project_id):
        role.require_pm("Error while getting project info.")
        role.require_in_project(project_id, "Error while getting project info.")
        return util.success(project.get_project_info(project_id))

    @doc(tags=["Project"], description="Update project info")
    @use_kwargs(router_model.SingleProjectPutSchema, location="form")
    @marshal_with(util.CommonResponse)
    @jwt_required()
    def put(self, project_id, **kwargs):
        role.require_pm("Error while updating project info.", exclude_qa=True)
        role.require_in_project(project_id, "Error while updating project info.")
        project.check_project_args_patterns(kwargs)
        project.check_project_owner_id(kwargs["owner_id"], get_jwt_identity()["user_id"], project_id)
        project.pm_update_project(project_id, kwargs)
        return util.success()

    @doc(tags=["Project"], description="Update project owner")
    @use_kwargs(router_model.SingleProjectPatchSchema, location="form")
    @marshal_with(util.CommonResponse)
    @jwt_required()
    def patch(self, project_id, **kwargs):
        role.require_pm("Error while updating project info.", exclude_qa=True)
        role.require_in_project(project_id, "Error while updating project info.")
        project.check_project_args_patterns(kwargs)
        if kwargs.get("owner_id", None) is not None:
            project.check_project_owner_id(kwargs["owner_id"], get_jwt_identity()["user_id"], project_id)
        project.nexus_update_project(project_id, kwargs)
        return util.success()

    @doc(tags=["Project"], description="Delete project")
    @marshal_with(util.CommonResponse)
    @jwt_required()
    def delete(self, project_id):
        role.require_pm()
        role.require_in_project(project_id)
        role_id = get_jwt_identity()["role_id"]
        user_id = get_jwt_identity()["user_id"]
        if role_id == role.QA.id and not bool(model.Project.query.filter_by(id=project_id, creator_id=user_id).count()):
            raise apiError.NotAllowedError("Error while deleting project.")
        parser = reqparse.RequestParser()
        parser.add_argument("force_delete_project", type=bool, location="args")
        args = parser.parse_args()
        return project.delete_project(project_id)


class SingleProjectCreateV2(MethodResource):
    @doc(tags=["Project"], description="Create project")
    @use_kwargs(router_model.SingleProjectPostSchema, location="form")
    @marshal_with(router_model.SingleProjectPostResponse)
    @jwt_required()
    def post(self, **kwargs):
        role.require_pm()
        user_id = get_jwt_identity()["user_id"]

        if kwargs.get("arguments") is not None:
            kwargs["arguments"] = ast.literal_eval(kwargs["arguments"])
        project.check_project_args_patterns(kwargs)
        return util.success(project.create_project(user_id, kwargs))


class SingleProject(Resource):
    @jwt_required()
    def get(self, project_id):
        role.require_pm("Error while getting project info.")
        role.require_in_project(project_id, "Error while getting project info.")
        return util.success(project.get_project_info(project_id))

    @jwt_required()
    def put(self, project_id):
        role.require_pm("Error while updating project info.", exclude_qa=True)
        role.require_in_project(project_id, "Error while updating project info.")
        parser = reqparse.RequestParser()
        parser.add_argument("display", type=str, required=True)
        parser.add_argument("description", type=str)
        parser.add_argument("disabled", type=bool, required=True)
        parser.add_argument("template_id", type=int)
        parser.add_argument("tag_name", type=str)
        parser.add_argument("arguments", type=str)
        parser.add_argument("start_date", type=str, required=True)
        parser.add_argument("due_date", type=str, required=True)
        parser.add_argument("owner_id", type=int, required=True)
        parser.add_argument("parent_id", type=str)
        parser.add_argument("is_inheritance_member", type=bool)
        args = parser.parse_args()
        args = {key: value for key, value in args.items() if value is not None or key == "description"}

        project.check_project_args_patterns(args)
        project.check_project_owner_id(args["owner_id"], get_jwt_identity()["user_id"], project_id)
        project.pm_update_project(project_id, args)
        return util.success()

    @jwt_required()
    def patch(self, project_id):
        role.require_pm("Error while updating project info.", exclude_qa=True)
        role.require_in_project(project_id, "Error while updating project info.")
        parser = reqparse.RequestParser()
        parser.add_argument("owner_id", type=int, required=False)
        args = parser.parse_args()
        project.check_project_args_patterns(args)
        if args.get("owner_id", None) is not None:
            project.check_project_owner_id(args["owner_id"], get_jwt_identity()["user_id"], project_id)
        project.nexus_update_project(project_id, args)
        return util.success()

    @jwt_required()
    def delete(self, project_id):
        role.require_pm()
        role.require_in_project(project_id)
        role_id = get_jwt_identity()["role_id"]
        user_id = get_jwt_identity()["user_id"]
        if role_id == role.QA.id and not bool(model.Project.query.filter_by(id=project_id, creator_id=user_id).count()):
            raise apiError.NotAllowedError("Error while deleting project.")
        return project.delete_project(project_id)

    @jwt_required()
    def post(self):
        role.require_pm()
        user_id = get_jwt_identity()["user_id"]
        parser = reqparse.RequestParser()
        parser.add_argument("name", type=str, required=True)
        parser.add_argument("display", type=str)
        parser.add_argument("description", type=str)
        parser.add_argument("disabled", type=bool, required=True)
        parser.add_argument("template_id", type=int)
        parser.add_argument("tag_name", type=str)
        parser.add_argument("arguments", type=str)
        parser.add_argument("start_date", type=str, required=True)
        parser.add_argument("due_date", type=str, required=True)
        parser.add_argument("owner_id", type=int)
        parser.add_argument("parent_id", type=int)
        parser.add_argument("is_inheritance_member", type=bool)
        args = parser.parse_args()
        if args["arguments"] is not None:
            args["arguments"] = ast.literal_eval(args["arguments"])
        project.check_project_args_patterns(args)
        return util.success(project.create_project(user_id, args))


@doc(tags=["Project"], description="Get project by project name.")
@marshal_with(router_model.SingleProjectByNameResponse)
class SingleProjectByNameV2(MethodResource):
    @jwt_required()
    def get(self, project_name):
        project_id = nexus.nx_get_project(name=project_name).id
        role.require_pm("Error while getting project info.")
        role.require_in_project(project_id, "Error while getting project info.")
        return util.success(project.get_project_info(project_id))


class SingleProjectByName(Resource):
    @jwt_required()
    def get(self, project_name):
        project_id = nexus.nx_get_project(name=project_name).id
        role.require_pm("Error while getting project info.")
        role.require_in_project(project_id, "Error while getting project info.")
        return util.success(project.get_project_info(project_id))


##### Project member ######


class ProjectMemberV2(MethodResource):
    @doc(tags=["User"], description="Create project member.")
    @use_kwargs(router_model.SingleProjectMemberPutSchema, location="form")
    @marshal_with(util.CommonResponse)
    @jwt_required()
    def post(self, project_id, **kwargs):
        role.require_pm()
        role.require_in_project(project_id)
        return project.project_add_member(project_id, kwargs["user_id"])


@doc(tags=["User"], description="Delete project member.")
@marshal_with(util.CommonResponse)
class ProjectMemberDeleteV2(MethodResource):
    @jwt_required()
    def delete(self, project_id, user_id):
        role.require_pm()
        role.require_in_project(project_id)
        return project.project_remove_member(project_id, user_id)


class ProjectMember(Resource):
    @jwt_required()
    def post(self, project_id):
        role.require_pm()
        role.require_in_project(project_id)
        parser = reqparse.RequestParser()
        parser.add_argument("user_id", type=int, required=True)
        args = parser.parse_args()
        return project.project_add_member(project_id, args["user_id"])

    @jwt_required()
    def delete(self, project_id, user_id):
        role.require_pm()
        role.require_in_project(project_id)
        return project.project_remove_member(project_id, user_id)


class ProjectUserListV2(MethodResource):
    @doc(tags=["User"], description="Get users which able to add in the project.")
    @use_kwargs(router_model.ProjectUserListSchema, location="query")
    @marshal_with(router_model.ProjectUserListResponse)
    @jwt_required()
    def get(self, project_id, **kwargs):
        return util.success({"user_list": user.user_list_by_project(project_id, kwargs)})


class ProjectUserList(Resource):
    @jwt_required()
    def get(self, project_id):
        parser = reqparse.RequestParser()
        parser.add_argument("exclude", type=int, location="args")
        args = parser.parse_args()
        return util.success({"user_list": user.user_list_by_project(project_id, args)})


##### Project report ######


@doc(tags=["Project"], description="Get project test summary.")
@marshal_with(router_model.TestSummaryResponse)
class TestSummaryV2(MethodResource):
    @jwt_required()
    def get(self, project_id):
        role.require_in_project(project_id)
        return project.get_test_summary(project_id)


class TestSummary(Resource):
    @jwt_required()
    def get(self, project_id):
        role.require_in_project(project_id)
        return project.get_test_summary(project_id)


@doc(tags=["Project"], description="Get project all test reports' zip.")
class AllReportsV2(MethodResource):
    @jwt_required()
    def get(self, project_id):
        role.require_pm()
        role.require_in_project(project_id)
        return send_file(
            project.get_all_reports(project_id),
            attachment_filename="reports.zip",
            as_attachment=True,
        )


class AllReports(Resource):
    @jwt_required()
    def get(self, project_id):
        role.require_pm()
        role.require_in_project(project_id)
        return send_file(
            project.get_all_reports(project_id),
            attachment_filename="reports.zip",
            as_attachment=True,
        )


class ProjectFileV2(MethodResource):
    @doc(tags=["File"], description="Upload file to project.")
    @use_kwargs(router_model.ProjectFilePostSchema, location="form")
    @use_kwargs(FileSchema, location="files")
    @jwt_required()
    def post(self, project_id, **kwargs):
        try:
            plan_project_id = project.get_plan_project_id(project_id)
        except NoResultFound:
            raise apiError.DevOpsError(
                404,
                "Error while uploading a file to a project.",
                error=apiError.project_not_found(project_id),
            )

        plan_operator_id = None
        if get_jwt_identity()["user_id"] is not None:
            operator_plugin_relation = nexus.nx_get_user_plugin_relation(user_id=get_jwt_identity()["user_id"])
            plan_operator_id = operator_plugin_relation.plan_user_id
        personal_redmine_obj = get_redmine_obj(plan_user_id=plan_operator_id)
        return personal_redmine_obj.rm_upload_to_project(plan_project_id, kwargs)

    @doc(tags=["File"], description="Get project file list.")
    @marshal_with(router_model.ProjectFileGetResponse)
    @jwt_required()
    def get(self, project_id):
        try:
            plan_project_id = project.get_plan_project_id(project_id)
        except NoResultFound:
            raise apiError.DevOpsError(
                404,
                "Error while getting project files.",
                error=apiError.project_not_found(project_id),
            )
        return util.success(redmine.rm_list_file(plan_project_id))


class ProjectFile(Resource):
    @jwt_required()
    def post(self, project_id):
        try:
            plan_project_id = project.get_plan_project_id(project_id)
        except NoResultFound:
            raise apiError.DevOpsError(
                404,
                "Error while uploading a file to a project.",
                error=apiError.project_not_found(project_id),
            )
        parser = reqparse.RequestParser()
        parser.add_argument("file", type=werkzeug.datastructures.FileStorage, location="files")
        parser.add_argument("filename", type=str, location="form")
        parser.add_argument("version_id", type=str, location="form")
        parser.add_argument("description", type=str, location="form")
        args = parser.parse_args()
        plan_operator_id = None
        if get_jwt_identity()["user_id"] is not None:
            operator_plugin_relation = nexus.nx_get_user_plugin_relation(user_id=get_jwt_identity()["user_id"])
            plan_operator_id = operator_plugin_relation.plan_user_id

        file = args["file"]
        if file is None:
            raise DevOpsError(400, "No file is sent.", error=apiError.argument_error("file"))
        from resources.system_parameter import check_upload_type

        check_upload_type(file)
        personal_redmine_obj = get_redmine_obj(plan_user_id=plan_operator_id)
        return personal_redmine_obj.rm_upload_to_project(plan_project_id, args)

    @jwt_required()
    def get(self, project_id):
        try:
            plan_project_id = project.get_plan_project_id(project_id)
        except NoResultFound:
            raise apiError.DevOpsError(
                404,
                "Error while getting project files.",
                error=apiError.project_not_found(project_id),
            )
        return util.success(redmine.rm_list_file(plan_project_id))


##### Project plugin(k8s) ######


@doc(tags=["Plugin"], description="Get project plugin resource info.")
@marshal_with(router_model.ProjectPluginUsageResponse)
class ProjectPluginUsageV2(MethodResource):
    @jwt_required()
    def get(self, project_id):
        role.require_in_project(project_id, "Error while getting project info.")
        return project.get_plugin_usage(project_id)


class ProjectPluginUsage(Resource):
    @jwt_required()
    def get(self, project_id):
        role.require_in_project(project_id, "Error while getting project info.")
        return project.get_plugin_usage(project_id)


##### Version ######


class ProjectVersionListV2(MethodResource):
    @doc(tags=["Version"], description="Get project version list.")
    @use_kwargs(router_model.ProjectVersionListSchema, location="query")
    @marshal_with(router_model.ProjectVersionListResponse)
    @jwt_required()
    def get(self, project_id, **kwargs):
        role.require_in_project(project_id)
        return util.success(
            version.get_version_list_by_project(project_id, kwargs.get("status"), kwargs.get("force_id"))
        )


class ProjectVersionList(Resource):
    @jwt_required()
    def get(self, project_id):
        role.require_in_project(project_id)
        root_parser = reqparse.RequestParser()
        root_parser.add_argument("status", type=str, location="args")
        root_parser.add_argument("force_id", type=str, location="args")
        root_args = root_parser.parse_args()
        return util.success(version.get_version_list_by_project(project_id, root_args["status"], root_args["force_id"]))


class ProjectVersionPostV2(MethodResource):
    @doc(tags=["Version"], description="Create project version.")
    @use_kwargs(router_model.ProjectVersionPostPutSchema, location="json")
    @marshal_with(router_model.ProjectVersionPostResponse)
    @jwt_required()
    def post(self, project_id, **kwargs):
        role.require_in_project(project_id)
        return version.post_version_by_project(project_id, kwargs)


class ProjectVersionV2(MethodResource):
    @doc(tags=["Version"], description="Get project version by version_id.")
    @marshal_with(router_model.ProjectVersionGetResponse)
    @jwt_required()
    def get(self, project_id, version_id):
        role.require_in_project(project_id)
        return version.get_version_by_version_id(version_id)

    @doc(tags=["Version"], description="Update project version by version_id.")
    @use_kwargs(router_model.ProjectVersionPostPutSchema, location="json")
    @marshal_with(util.CommonResponse)
    @jwt_required()
    def put(self, project_id, version_id, **kwargs):
        role.require_in_project(project_id)
        return version.put_version_by_version_id(version_id, kwargs)

    @doc(tags=["Version"], description="Delete project version by version_id.")
    @marshal_with(util.CommonResponse)
    @jwt_required()
    def delete(self, project_id, version_id):
        role.require_in_project(project_id)
        return version.delete_version_by_version_id(version_id)


class ProjectVersion(Resource):
    @jwt_required()
    def post(self, project_id):
        role.require_in_project(project_id)
        root_parser = reqparse.RequestParser()
        root_parser.add_argument("version", type=dict, required=True)

        root_args = root_parser.parse_args()
        return version.post_version_by_project(project_id, root_args)

    @jwt_required()
    def get(self, project_id, version_id):
        role.require_in_project(project_id)
        return version.get_version_by_version_id(version_id)

    @jwt_required()
    def put(self, project_id, version_id):
        role.require_in_project(project_id)
        root_parser = reqparse.RequestParser()
        root_parser.add_argument("version", type=dict, required=True)
        root_args = root_parser.parse_args()
        return version.put_version_by_version_id(version_id, root_args)

    @jwt_required()
    def delete(self, project_id, version_id):
        role.require_in_project(project_id)
        return version.delete_version_by_version_id(version_id)


##### Wiki ######
class ProjectWikiListV2(MethodResource):
    @doc(tags=["Project"], description="Get project wiki list")
    @marshal_with(router_model.ProjectWikiListResponse)
    @jwt_required()
    def get(self, project_id):
        role.require_in_project(project_id)
        return wiki.get_wiki_list_by_project(project_id)


class ProjectWikiList(Resource):
    @jwt_required()
    def get(self, project_id):
        role.require_in_project(project_id)
        return wiki.get_wiki_list_by_project(project_id)


class ProjectWikiV2(MethodResource):
    @doc(tags=["Project"], description="Get project wiki info by wiki name")
    @marshal_with(router_model.ProjectWikiGetResponse)
    @jwt_required()
    def get(self, project_id, wiki_name):
        role.require_in_project(project_id)
        return wiki.get_wiki_by_project(project_id, wiki_name)

    @doc(tags=["Project"], description="Update project wiki info by wiki name")
    @use_kwargs(router_model.ProjectWikiPut, location="json")
    @marshal_with(util.CommonResponse)
    @jwt_required()
    def put(self, project_id, wiki_name, **kwargs):
        role.require_in_project(project_id)
        return wiki.put_wiki_by_project(project_id, wiki_name, kwargs, get_jwt_identity()["user_id"])

    @doc(tags=["Project"], description="Delete project wiki info by wiki name")
    @marshal_with(util.CommonResponse)
    @jwt_required()
    def delete(self, project_id, wiki_name):
        role.require_in_project(project_id)
        return wiki.delete_wiki_by_project(project_id, wiki_name)


class ProjectWiki(Resource):
    @jwt_required()
    def get(self, project_id, wiki_name):
        role.require_in_project(project_id)
        return wiki.get_wiki_by_project(project_id, wiki_name)

    @jwt_required()
    def put(self, project_id, wiki_name):
        role.require_in_project(project_id)
        parser = reqparse.RequestParser()
        parser.add_argument("wiki_text", type=str, required=True)
        args = parser.parse_args()
        return wiki.put_wiki_by_project(project_id, wiki_name, args, get_jwt_identity()["user_id"])

    @jwt_required()
    def delete(self, project_id, wiki_name):
        role.require_in_project(project_id)
        return wiki.delete_wiki_by_project(project_id, wiki_name)


##### Project Release ######
class ReleaseExtraV2(MethodResource):
    @doc(tags=["Release"], description="Get able to release's image list.")
    @use_kwargs(router_model.ReleaseExtraGetSchema, location="query")
    @marshal_with(router_model.ReleaseExtraGetResponse)
    @jwt_required()
    def get(self, project_id, **kwargs):
        return util.success(release.get_release_image_list(project_id, kwargs))


class ReleaseTagV2(MethodResource):
    @doc(tags=["Release"], description="Add tag on release by release_id.")
    @use_kwargs(router_model.ReleaseTagSchema, location="form")
    @marshal_with(util.CommonResponse)
    @jwt_required()
    def post(self, project_id, release_id, **kwargs):
        return release.add_release_tag(project_id, release_id, kwargs)

    @doc(tags=["Release"], description="Delete tag on release by release_id.")
    @use_kwargs(router_model.ReleaseTagSchema, location="query")
    @marshal_with(util.CommonResponse)
    @jwt_required()
    def delete(self, project_id, release_id, **kwargs):
        return release.delete_release_tag(project_id, release_id, kwargs)


class ReleaseRepoV2(MethodResource):
    @doc(tags=["Release"], description="Add repository on release by release_id.")
    @use_kwargs(router_model.ReleaseRepoPostSchema, location="form")
    @marshal_with(util.CommonResponse)
    @jwt_required()
    def post(self, project_id, release_id, **kwargs):
        return release.create_release_image_repo(project_id, release_id, kwargs)

    @doc(tags=["Release"], description="Delete repository on release by release_id.")
    @use_kwargs(router_model.ReleaseRepoDeleteSchema, location="query")
    @marshal_with(util.CommonResponse)
    @jwt_required()
    def delete(self, project_id, release_id, **kwargs):
        return release.delete_release_image_repo(project_id, release_id, kwargs)


class ReleasesV2(MethodResource):
    @doc(tags=["Release"], description="Get release list.")
    @use_kwargs(router_model.ReleasesGetSchema, location="query")
    @marshal_with(router_model.ReleasesGetResponse)
    @jwt_required()
    def get(self, project_id, **kwargs):
        role.require_in_project(project_id, "Error to get release")
        try:
            return util.success({"releases": release.get_releases_by_project_id(project_id, kwargs)})
        except NoResultFound:
            return util.respond(404, release.error_redmine_issues_closed)

    @doc(tags=["Release"], description="Create a new release version.")
    @use_kwargs(router_model.ReleasesPostSchema, location="json")
    @marshal_with(util.CommonResponse)
    @jwt_required()
    def post(self, project_id, **kwargs):
        role.require_in_project(project_id, "Error to create release")
        release_obj = release.Releases()
        return util.success(release_obj.release_main(project_id, kwargs))


class ReleaseV2(MethodResource):
    @doc(tags=["Release"], description="Get release info by release_name.")
    @jwt_required()
    def get(self, project_id, release_name):
        plugin_relation = model.ProjectPluginRelation.query.filter_by(project_id=project_id).first()
        try:
            gl_release = gitlab.gl_get_release(plugin_relation.git_repository_id, release_name)
            rm_list_versions = (redmine.rm_get_version_list(plugin_relation.plan_project_id),)
            rm_key_versions = release.transfer_array_to_object(rm_list_versions[0]["versions"], "name")
            if release_name not in rm_key_versions:
                return util.success({})
            return util.success({"gitlab": gl_release, "redmine": rm_key_versions[release_name]})
        except NoResultFound:
            return util.respond(
                404,
                release.error_gitlab_not_found,
                error=apiError.repository_id_not_found(plugin_relation.git_repository_id),
            )


##### Issue's force tracker ######
class IssueForceTrackerV2(MethodResource):
    @doc(tags=["Issue"], description="Get issue's force trackers.")
    @marshal_with(router_model.IssueForceTrackerPostResponse)
    @jwt_required()
    def get(self, project_id):
        return util.success(get_project_issue_check(project_id))

    @doc(tags=["Issue"], description="Create issue's force trackers.")
    @marshal_with(util.CommonResponse)
    @jwt_required()
    def post(self, project_id):
        role.require_project_owner(get_jwt_identity()["user_id"], project_id)
        return util.success(create_project_issue_check(project_id))

    @doc(tags=["Issue"], description="Update issue's force trackers.")
    @use_kwargs(router_model.IssueForceTrackerPatchSchema, location="json")
    @marshal_with(util.CommonResponse)
    @jwt_required()
    def patch(self, project_id, **kwargs):
        role.require_project_owner(get_jwt_identity()["user_id"], project_id)
        return util.success(update_project_issue_check(project_id, kwargs))

    @doc(tags=["Issue"], description="Delete issue's force trackers.")
    @marshal_with(util.CommonResponse)
    @jwt_required()
    def delete(self, project_id):
        role.require_project_owner(get_jwt_identity()["user_id"], project_id)
        return util.success(delete_project_issue_check(project_id))


##### project resource storage ######


class ProjectResourceStorage(MethodResource):
    @doc(tags=["Project"], description="Get project's resource storage info.")
    @marshal_with(router_model.ProjectResourceStorageRes)
    @jwt_required()
    def get(self, project_id):
        return util.success(get_project_resource_storage_level(project_id))

    @doc(tags=["Project"], description="Update project's resource storage info.")
    @use_kwargs(router_model.ProjectResourceStorageUpdateSchema, location="json")
    @marshal_with(util.CommonResponse)
    @jwt_required()
    def patch(self, project_id, **kwargs):
        return util.success(update_project_resource_storage_level(project_id, args=kwargs))
