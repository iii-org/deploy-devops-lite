from flask_apispec import marshal_with, doc, use_kwargs
from flask_apispec.views import MethodResource
from flask_jwt_extended import jwt_required, get_jwt_identity
from accessories import redmine_lib
from resources.apiError import DevOpsError
from flask_restful import Resource, reqparse
import resources.apiError as apiError
import util
import werkzeug
from redminelib.exceptions import ResourceAttrError
from . import router_model
from resources.issue import (
    get_issue,
    require_issue_visible,
    get_issue_tags,
    get_issue_extensions,
    update_issue,
    get_issue_family,
    delete_issue,
    create_issue,
    NexusIssue,
    get_issue_statistics,
    get_open_issue_statistics,
    get_issue_statistics_in_period,
    post_issue_relation,
    put_issue_relation,
    delete_issue_relation,
    check_issue_closable,
    get_commit_hook_issues,
    modify_hook,
    sync_issue_relation,
    get_issue_children,
    get_all_sons,
    find_head_and_close_issues,
)
from resources.system_parameter import check_upload_type
# from resources.excalidraw import get_excalidraw_by_issue_id
from resources import role

##### Issue single #####


class SingleIssueV2(MethodResource):
    @doc(tags=["Issue"], description="Get single issue")
    # @marshal_with(router_model.SingleIssueGetResponse)
    @jwt_required()
    def get(self, issue_id):
        issue_info = get_issue(issue_id, operator_id=get_jwt_identity()["user_id"])
        require_issue_visible(issue_id, issue_info)
        if "parent_id" in issue_info:
            parent_check_info = get_issue(issue_info["parent_id"])
            identity = get_jwt_identity()
            user_id = identity["user_id"]
            if not identity["role_id"] == role.ADMIN.id or parent_check_info["assigned_to"]["id"] != user_id:
                issue_info.pop("parent_id", None)
            else:
                parent_info = get_issue(issue_info["parent_id"], with_children=False)
                parent_info["name"] = parent_info.pop("subject", None)
                parent_info["tags"] = get_issue_tags(parent_info["id"])
                issue_info.pop("parent_id", None)
                issue_info["parent"] = parent_info

        for items in ["children", "relations"]:
            if issue_info.get(items) is not None:
                for item in issue_info[items]:
                    item["tags"] = get_issue_tags(item["id"])
        issue_info["name"] = issue_info.pop("subject", None)
        issue_info |= get_issue_extensions(issue_id)
        issue_info["tags"] = get_issue_tags(issue_id)
        # issue_info["excalidraw"] = get_excalidraw_by_issue_id(issue_id)
        return util.success(issue_info)

    @doc(tags=["Issue"], description="Update single issue")
    @use_kwargs(router_model.SingleIssuePutSchema, location="form")
    @use_kwargs(router_model.FileSchema, location="files")
    @marshal_with(router_model.SingleIssuePutResponse)
    @jwt_required()
    def put(self, issue_id, **kwargs):
        require_issue_visible(issue_id)

        redmine_issue = redmine_lib.redmine.issue.get(issue_id, include=["children"])
        has_children = redmine_issue.children.total_count > 0
        if has_children:
            validate_field_mapping = {
                "priority_id": redmine_issue.priority.id if hasattr(redmine_issue, "priority") else None,
                "start_date": redmine_issue.start_date.isoformat() if hasattr(redmine_issue, "start_date") else "",
                "due_date": redmine_issue.due_date.isoformat() if hasattr(redmine_issue, "due_date") else "",
            }
            for invalidate_field in ["priority_id", "start_date", "due_date"]:
                if (
                    kwargs.get(invalidate_field) is not None
                    and kwargs.get(invalidate_field) != validate_field_mapping[invalidate_field]
                ):
                    raise DevOpsError(
                        400,
                        f"Argument {invalidate_field} can not be alerted when children issue exist.",
                        error=apiError.redmine_argument_error(invalidate_field),
                    )

        # Check due_date is greater than start_date
        due_date = None
        start_date = None

        if kwargs.get("due_date") is not None and len(kwargs.get("due_date")) > 0:
            due_date = kwargs.get("due_date")
        else:
            try:
                due_date = str(redmine_lib.redmine.issue.get(issue_id).due_date)
            except ResourceAttrError:
                pass

        if kwargs.get("start_date") is not None and len(kwargs.get("start_date")) > 0:
            start_date = kwargs.get("start_date")
        else:
            try:
                start_date = str(redmine_lib.redmine.issue.get(issue_id).start_date)
            except ResourceAttrError:
                pass

        if start_date is not None and due_date is not None and due_date < start_date:
            arg = "due_date" if kwargs.get("due_date") is not None and len(kwargs.get("due_date")) > 0 else "start_date"
            raise DevOpsError(
                400,
                "Due date must be greater than start date.",
                error=apiError.argument_error(arg),
            )

        # Handle removable int parameters
        keys_int_or_null = ["assigned_to_id", "fixed_version_id", "parent_id"]
        for k in keys_int_or_null:
            if kwargs.get(k) == "null":
                kwargs[k] = ""

        kwargs["subject"] = kwargs.pop("name", None)
        if get_jwt_identity()["role_id"] == 7:
            from resources.user import get_sysadmin_info
            import config

            operator_id = get_sysadmin_info(config.get("ADMIN_INIT_LOGIN")).get("id")
        else:
            operator_id = get_jwt_identity()["user_id"]

        output = update_issue(issue_id, kwargs, operator_id)
        return util.success(output)

    @doc(tags=["Issue"], description="Delete single issue")
    @use_kwargs(router_model.SingleIssueDeleteSchema, location="form")
    @marshal_with(router_model.SingleIssueDeleteResponse)
    @jwt_required()
    def delete(self, issue_id, **kwargs):
        if kwargs.get("force") is None or not kwargs.get("force"):
            redmine_issue = redmine_lib.redmine.issue.get(issue_id, include=["children"])
            children = get_issue_children(redmine_issue, redmine_lib.redmine)
            if children != []:
                raise DevOpsError(
                    400,
                    'Unable to delete issue with children issue, unless parameter "force" is True.',
                    error=apiError.unable_to_delete_issue_has_children(children),
                )
        return util.success(delete_issue(issue_id, kwargs["delete_excalidraw"]))


@doc(tags=["Issue"], description="Create single issue")
@use_kwargs(router_model.SingleIssuePostSchema, location="form")
@use_kwargs(router_model.FileSchema, location="files")
@marshal_with(router_model.SingleIssuePostResponse)
class CreateSingleIssueV2(MethodResource):
    @jwt_required()
    def post(self, **kwargs):
        # Check due_date is greater than start_date
        if (
            kwargs.get("start_date") is not None
            and kwargs.get("due_date") is not None
            and kwargs["due_date"] < kwargs["start_date"]
        ):
            raise DevOpsError(
                400,
                "Due date must be greater than start date.",
                error=apiError.argument_error("due_date"),
            )
        user_role_id = get_jwt_identity()["role_id"]
        if user_role_id == 5 and kwargs.get("creator_id") is not None:
            creator_id = kwargs.pop("creator_id")
        elif user_role_id == 7:
            from resources.user import get_sysadmin_info
            import config

            creator_id = get_sysadmin_info(config.get("ADMIN_INIT_LOGIN")).get("id")
        else:
            creator_id = get_jwt_identity()["user_id"]

        # Handle removable int parameters
        keys_int_or_null = ["assigned_to_id", "fixed_version_id", "parent_id"]
        for k in keys_int_or_null:
            if kwargs.get(k) == "null":
                kwargs[k] = ""

        kwargs["subject"] = kwargs.pop("name")
        return util.success(create_issue(kwargs, creator_id))


class SingleIssue(Resource):
    @jwt_required()
    def get(self, issue_id):
        issue_info = get_issue(issue_id, operator_id=get_jwt_identity()["user_id"])
        require_issue_visible(issue_id, issue_info)
        if "parent_id" in issue_info:
            parent_info = get_issue(issue_info["parent_id"], with_children=False)
            parent_info["name"] = parent_info.pop("subject", None)
            parent_info["tags"] = get_issue_tags(parent_info["id"])
            issue_info.pop("parent_id", None)
            issue_info["parent"] = parent_info

        for items in ["children", "relations"]:
            if issue_info.get(items) is not None:
                for item in issue_info[items]:
                    item["tags"] = get_issue_tags(item["id"])
        issue_info["name"] = issue_info.pop("subject", None)
        issue_info |= get_issue_extensions(issue_id)
        issue_info["tags"] = get_issue_tags(issue_id)
        # issue_info["excalidraw"] = get_excalidraw_by_issue_id(issue_id)

        return util.success(issue_info)

    @jwt_required()
    def post(self):
        parser = reqparse.RequestParser()
        parser.add_argument("project_id", type=int, required=True, location="form")
        parser.add_argument("tracker_id", type=int, default=1, location="form")
        parser.add_argument("status_id", type=int, default=1, location="form")
        parser.add_argument("priority_id", type=int, default=3, location="form")
        parser.add_argument("name", type=str, required=True, location="form")
        parser.add_argument("description", type=str, location="form")
        parser.add_argument("assigned_to_id", type=str, location="form")
        parser.add_argument("creator_id", type=str, location="form")
        parser.add_argument("parent_id", type=str, location="form")
        parser.add_argument("fixed_version_id", type=str, location="form")
        parser.add_argument("start_date", type=str, location="form")
        parser.add_argument("due_date", type=str, location="form")
        parser.add_argument("done_ratio", type=int, location="form")
        parser.add_argument("estimated_hours", type=int, location="form")
        parser.add_argument("point", type=int, location="form")
        parser.add_argument("tags", type=str, location="form")
        parser.add_argument("changeNo", type=str, location="form")
        parser.add_argument("changeUrl", type=str, location="form")

        # Attachment upload
        parser.add_argument(
            "upload_files",
            type=werkzeug.datastructures.FileStorage,
            location="files",
            action="append",
        )
        parser.add_argument("upload_filename", type=str, location="form")
        parser.add_argument("upload_description", type=str, location="form")
        parser.add_argument("upload_content_type", type=str, location="form")

        args = parser.parse_args()
        user_role_id = get_jwt_identity()["role_id"]
        if user_role_id == 5 and args.get("creator_id") is not None:
            creator_id = args.pop("creator_id")
        elif user_role_id == 7:
            from resources.user import get_sysadmin_info
            import config

            creator_id = get_sysadmin_info(config.get("ADMIN_INIT_LOGIN")).get("id")
        else:
            creator_id = get_jwt_identity()["user_id"]

        if args.get("upload_file") is not None:
            check_upload_type(args["upload_file"])

        # Check due_date is greater than start_date
        if (
            args.get("start_date") is not None
            and args.get("due_date") is not None
            and args["due_date"] < args["start_date"]
        ):
            raise DevOpsError(
                400,
                "Due date must be greater than start date.",
                error=apiError.argument_error("due_date"),
            )

        # Handle removable int parameters
        keys_int_or_null = ["assigned_to_id", "fixed_version_id", "parent_id"]
        for k in keys_int_or_null:
            if args[k] == "null":
                args[k] = ""

        args["subject"] = args.pop("name")
        return util.success(create_issue(args, creator_id))

    @jwt_required()
    def put(self, issue_id):
        require_issue_visible(issue_id)
        parser = reqparse.RequestParser()
        parser.add_argument("assigned_to_id", type=str, location="form")
        parser.add_argument("tracker_id", type=int, location="form")
        parser.add_argument("status_id", type=int, location="form")
        parser.add_argument("priority_id", type=int, location="form")
        parser.add_argument("project_id", type=int, location="form")
        parser.add_argument("estimated_hours", type=int, location="form")
        parser.add_argument("description", type=str, location="form")
        parser.add_argument("parent_id", type=str, location="form")
        parser.add_argument("fixed_version_id", type=str, location="form")
        parser.add_argument("name", type=str, location="form")
        parser.add_argument("start_date", type=str, location="form")
        parser.add_argument("due_date", type=str, location="form")
        parser.add_argument("done_ratio", type=int, location="form")
        parser.add_argument("notes", type=str, location="form")
        parser.add_argument("point", type=int, location="form")
        parser.add_argument("tags", type=str, location="form")
        parser.add_argument("close_all", type=bool, location="form")

        # Attachment uploadsd
        parser.add_argument(
            "upload_files",
            type=werkzeug.datastructures.FileStorage,
            location="files",
            action="append",
        )
        parser.add_argument("upload_filename", type=str, location="form")
        parser.add_argument("upload_description", type=str, location="form")
        parser.add_argument("upload_content_type", type=str, location="form")

        args = parser.parse_args()

        if args.get("upload_file") is not None:
            check_upload_type(args["upload_file"])

        redmine_issue = redmine_lib.redmine.issue.get(issue_id, include=["children"])
        has_children = redmine_issue.children.total_count > 0
        if has_children:
            validate_field_mapping = {
                "priority_id": redmine_issue.priority.id if hasattr(redmine_issue, "priority") else None,
                "start_date": redmine_issue.start_date.isoformat() if hasattr(redmine_issue, "start_date") else "",
                "due_date": redmine_issue.due_date.isoformat() if hasattr(redmine_issue, "due_date") else "",
            }
            for invalidate_field in ["priority_id", "start_date", "due_date"]:
                if (
                    args[invalidate_field] is not None
                    and args[invalidate_field] != validate_field_mapping[invalidate_field]
                ):
                    raise DevOpsError(
                        400,
                        f"Argument {invalidate_field} can not be alerted when children issue exist.",
                        error=apiError.redmine_argument_error(invalidate_field),
                    )

        # Check due_date is greater than start_date
        due_date = None
        start_date = None

        if args.get("due_date") is not None and len(args.get("due_date")) > 0:
            due_date = args.get("due_date")
        else:
            try:
                due_date = str(redmine_lib.redmine.issue.get(issue_id).due_date)
            except ResourceAttrError:
                pass

        if args.get("start_date") is not None and len(args.get("start_date")) > 0:
            start_date = args.get("start_date")
        else:
            try:
                start_date = str(redmine_lib.redmine.issue.get(issue_id).start_date)
            except ResourceAttrError:
                pass

        if start_date is not None and due_date is not None and due_date < start_date:
            arg = "due_date" if args.get("due_date") is not None and len(args.get("due_date")) > 0 else "start_date"
            raise DevOpsError(
                400,
                "Due date must be greater than start date.",
                error=apiError.argument_error(arg),
            )

        # Handle removable int parameters
        keys_int_or_null = ["assigned_to_id", "fixed_version_id", "parent_id"]
        for k in keys_int_or_null:
            if args[k] == "null":
                args[k] = ""

        args["subject"] = args.pop("name", None)

        if get_jwt_identity()["role_id"] == 7:
            from resources.user import get_sysadmin_info
            import config

            operator_id = get_sysadmin_info(config.get("ADMIN_INIT_LOGIN")).get("id")
        else:
            operator_id = get_jwt_identity()["user_id"]

        output = update_issue(issue_id, args, operator_id)
        return util.success(output)

    @jwt_required()
    def delete(self, issue_id):
        parser = reqparse.RequestParser()
        parser.add_argument("force", type=bool, location="args")
        parser.add_argument("delete_excalidraw", type=bool, location="args", default=False)
        args = parser.parse_args()
        if args["force"] is None or not args["force"]:
            redmine_issue = redmine_lib.redmine.issue.get(issue_id, include=["children"])
            children = get_issue_children(redmine_issue, redmine_lib.redmine)
            if children != []:
                raise DevOpsError(
                    400,
                    'Unable to delete issue with children issue, unless parameter "force" is True.',
                    error=apiError.unable_to_delete_issue_has_children(children),
                )
        return util.success(delete_issue(issue_id, args["delete_excalidraw"]))


##### Issue Family #####


@doc(tags=["Issue"], description="Get issue's family(relation, parent, children)")
@use_kwargs(router_model.IssueIssueFamilySchema, location="query")
@marshal_with(router_model.IssueFamilyResponse)
class IssueFamilyV2(MethodResource):
    @jwt_required()
    def get(self, issue_id, **kwargs):
        user_account = get_jwt_identity()["user_account"]
        redmine_issue = redmine_lib.rm_impersonate(user_account).issue.get(issue_id, include=["children", "relations"])
        require_issue_visible(
            issue_id,
            issue_info=NexusIssue().set_redmine_issue_v2(redmine_issue).to_json(),
        )
        family = get_issue_family(redmine_issue, kwargs)
        return util.success(family)


class IssueFamily(Resource):
    @jwt_required()
    def get(self, issue_id):
        parser = reqparse.RequestParser()
        parser.add_argument("with_point", type=bool, location="args")
        args = parser.parse_args()
        user_account = get_jwt_identity()["user_account"]
        redmine_issue = redmine_lib.rm_impersonate(user_account).issue.get(issue_id, include=["children", "relations"])
        require_issue_visible(
            issue_id,
            issue_info=NexusIssue().set_redmine_issue_v2(redmine_issue).to_json(),
        )
        family = get_issue_family(redmine_issue, args)
        return util.success(family)


##### Issue Statistics #####


@doc(tags=["Pending"], description="Get issue Statistics")
class MyIssueStatisticsV2(MethodResource):
    @jwt_required()
    def get(self):
        parser = reqparse.RequestParser()
        parser.add_argument("from_time", type=str, required=True, location="args")
        parser.add_argument("to_time", type=str, location="args")
        parser.add_argument("status_id", type=int, location="args")
        args = parser.parse_args()
        output = get_issue_statistics(args, get_jwt_identity()["user_id"])
        return output


class MyIssueStatistics(Resource):
    @jwt_required()
    def get(self):
        parser = reqparse.RequestParser()
        parser.add_argument("from_time", type=str, required=True, location="args")
        parser.add_argument("to_time", type=str, location="args")
        parser.add_argument("status_id", type=int, location="args")
        args = parser.parse_args()
        output = get_issue_statistics(args, get_jwt_identity()["user_id"])
        return output


@doc(tags=["Issue"], description="Get my active issue number")
@marshal_with(router_model.MyOpenIssueStatisticsResponse)
class MyOpenIssueStatisticsV2(MethodResource):
    @jwt_required()
    def get(self):
        return get_open_issue_statistics(get_jwt_identity()["user_id"])


class MyOpenIssueStatistics(Resource):
    @jwt_required()
    def get(self):
        return get_open_issue_statistics(get_jwt_identity()["user_id"])


@doc(tags=["Issue"], description="Get my weekly active issue number")
@marshal_with(router_model.MyIssueWeekStatisticsResponse)
class MyIssueWeekStatisticsV2(MethodResource):
    @jwt_required()
    def get(self):
        return get_issue_statistics_in_period("week", get_jwt_identity()["user_id"])


class MyIssueWeekStatistics(Resource):
    @jwt_required()
    def get(self):
        return get_issue_statistics_in_period("week", get_jwt_identity()["user_id"])


@doc(tags=["Issue"], description="Get my monthly active issue number")
@marshal_with(router_model.MyIssueMonthStatisticsResponse)
class MyIssueMonthStatisticsV2(MethodResource):
    @jwt_required()
    def get(self):
        return get_issue_statistics_in_period("month", get_jwt_identity()["user_id"])


class MyIssueMonthStatistics(Resource):
    @jwt_required()
    def get(self):
        return get_issue_statistics_in_period("month", get_jwt_identity()["user_id"])


##### Issue's Relation issue #####


class RelationV2(MethodResource):
    @doc(tags=["Pending"], description="Create issue's relation.")
    @jwt_required()
    def post(self):
        parser = reqparse.RequestParser()
        parser.add_argument("issue_id", type=int, required=True)
        parser.add_argument("issue_to_id", type=int, required=True)
        args = parser.parse_args()
        output = post_issue_relation(args["issue_id"], args["issue_to_id"], get_jwt_identity()["user_account"])
        return util.success(output)

    @doc(tags=["Issue"], description="Update issue's relation.")
    @use_kwargs(router_model.RelationSchema, location="form")
    @marshal_with(util.CommonResponse)
    @jwt_required()
    def put(self, **kwargs):
        put_issue_relation(
            kwargs["issue_id"],
            kwargs["issue_to_ids"],
            get_jwt_identity()["user_account"],
        )
        return util.success()


@doc(tags=["Pending"], description="Delete issue's relation.")
class RelationDeleteV2(MethodResource):
    @jwt_required()
    def delete(self, relation_id):
        output = delete_issue_relation(relation_id, get_jwt_identity()["user_account"])
        return util.success(output)


class Relation(Resource):
    @jwt_required()
    def post(self):
        parser = reqparse.RequestParser()
        parser.add_argument("issue_id", type=int, required=True)
        parser.add_argument("issue_to_id", type=int, required=True)
        args = parser.parse_args()
        output = post_issue_relation(args["issue_id"], args["issue_to_id"], get_jwt_identity()["user_account"])
        return util.success(output)

    @jwt_required()
    def put(self):
        parser = reqparse.RequestParser()
        parser.add_argument("issue_id", type=int, required=True)
        parser.add_argument("issue_to_ids", type=list, location="json", required=True)
        args = parser.parse_args()
        put_issue_relation(args["issue_id"], args["issue_to_ids"], get_jwt_identity()["user_account"])
        return util.success()

    @jwt_required()
    def delete(self, relation_id):
        output = delete_issue_relation(relation_id, get_jwt_identity()["user_account"])
        return util.success(output)


##### Issue close #####


@doc(tags=["Issue"], description="Check issue is closable or not.")
@marshal_with(router_model.CheckIssueClosableResponse)
class CheckIssueClosableV2(MethodResource):
    @jwt_required()
    def get(self, issue_id):
        output = check_issue_closable(issue_id)
        return util.success(output)


class CheckIssueClosable(Resource):
    @jwt_required()
    def get(self, issue_id):
        output = check_issue_closable(issue_id)
        return util.success(output)


class IssueSonsV2(MethodResource):
    @doc(tags=["Issue"], description="Check issue is closable or not.")
    @use_kwargs(router_model.IssueSonsSchema, location="query")
    # @marshal_with(router_model.CheckIssueClosableResponse)
    @jwt_required()
    def get(self, project_id, **kwargs):
        return util.success(get_all_sons(project_id, kwargs["fixed_version_ids"]))


class ClosableAllV2(MethodResource):
    @doc(tags=["Issue"], description="Close multi issues")
    @use_kwargs(router_model.ClosableAllSchema)
    @marshal_with(util.CommonResponse)
    @jwt_required()
    def delete(self, **kwargs):
        return util.success(find_head_and_close_issues([str(issue_id) for issue_id in kwargs["issue_ids"]]))


##### Issue commit relationship ######


class IssueCommitRelationV2(MethodResource):
    @doc(tags=["Issue"], description="Get issue relation by commit_id.")
    @use_kwargs(router_model.IssueCommitRelationGetSchema, location="query")
    @marshal_with(router_model.IssueCommitRelationResponse)
    @jwt_required()
    def get(self, **kwargs):
        return util.success(get_commit_hook_issues(commit_id=kwargs["commit_id"]))

    @doc(tags=["Issue"], description="Update issue relation by commit_id.")
    @use_kwargs(router_model.IssueCommitRelationPatchSchema, location="form")
    @marshal_with(util.CommonResponse)
    @jwt_required()
    def patch(self, **kwargs):
        print(kwargs)
        return util.success(modify_hook(kwargs))


class IssueCommitRelation(Resource):
    @jwt_required()
    def get(self):
        parser = reqparse.RequestParser()
        parser.add_argument("commit_id", type=str, required=True, location="args")
        args = parser.parse_args()
        return util.success(get_commit_hook_issues(commit_id=args["commit_id"]))

    @jwt_required()
    def patch(self):
        parser = reqparse.RequestParser()
        parser.add_argument("commit_id", type=str, required=True)
        parser.add_argument("issue_ids", type=int, action="append", required=True)
        args = parser.parse_args()
        return util.success(modify_hook(args))


class SyncIssueFamiliesV2(MethodResource):
    @doc(tags=["System"], description="Sync issues' family.")
    @jwt_required()
    def post(self):
        return util.success(sync_issue_relation())
