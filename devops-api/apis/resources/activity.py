import inspect
from datetime import datetime, timedelta
from functools import wraps
from time import strptime, mktime
from accessories.redmine_lib import redmine

from flask import has_request_context
from flask_jwt_extended import get_jwt_identity, jwt_required
from flask_restful import Resource, reqparse
from sqlalchemy import desc, or_

import model
import nexus
import util
from enums.action_type import ActionType
from model import db
from resources import role


def record_activity(action_type):
    # Must be used after @jwt_required() decorator!
    def decorator(fn):
        @wraps(fn)
        def wrapper(*args, **kwargs):
            if not has_request_context():
                # Not in request context, do not record activity
                return fn(*args, **kwargs)

            try:
                identity = get_jwt_identity()
            except RuntimeError:
                identity = {"user_id": 1, "user_account": "system"}
            new = Activity(
                operator_id=identity["user_id"],
                action_type=action_type,
                operator_name=identity["user_account"],
                act_at=datetime.utcnow(),
            )
            itargs = kwargs.copy()
            for i, key in enumerate(inspect.getfullargspec(fn).args):
                if i >= len(args):
                    break
                if key == "self":
                    continue
                itargs[key] = args[i]
            new.fill_by_arguments(itargs)
            ret = fn(*args, **kwargs)
            new.fill_by_return_value(ret)
            db.session.add(new)
            db.session.commit()
            return ret

        return wrapper

    return decorator


def get_activities(args, query):
    offset = args.get("offset")
    limit = args.get("limit")
    total = query.count()
    pagination_dict = util.get_pagination(total, limit, offset)

    rows = query.offset(offset).limit(limit).all()
    result = [
        {
            "id": row.id,
            "action_type": row.action_type.name,
            "action_parts": row.action_parts,
            "operator_id": row.operator_id,
            "operator_name": row.operator_name,
            "object_id": row.object_id,
            "act_at": str(row.act_at),
        }
        for row in rows
    ]

    return {"activities_list": result, "page": pagination_dict}


def build_query(args, base_query=None):
    if base_query is not None:
        query = base_query
    else:
        query = model.Activity.query
    query = query.order_by(desc(model.Activity.act_at))
    search = args["search"]
    if search is not None:
        action_types = [
            ActionType[action_type] for action_type in dir(ActionType)[:-4] if search.upper() in action_type
        ]
        query = query.filter(
            or_(
                model.Activity.action_type.in_(action_types),
                model.Activity.action_parts.like(f"%{search}%"),
                model.Activity.operator_name.like(f"%{search}%"),
            )
        )

    a_from_date = args["from_date"]
    a_to_date = args["to_date"]
    if a_from_date is not None:
        from_date = datetime.fromtimestamp(mktime(strptime(a_from_date, "%Y-%m-%d")))
        query = query.filter(model.Activity.act_at >= from_date)
    if a_to_date is not None:
        to_date = datetime.fromtimestamp(mktime(strptime(a_to_date, "%Y-%m-%d")))
        to_date += timedelta(days=1)
        query = query.filter(model.Activity.act_at < to_date)

    return query


def limit_to_project(project_id):
    query = model.Activity.query.filter(
        model.Activity.action_type.in_(
            [
                ActionType.CREATE_PROJECT,
                ActionType.UPDATE_PROJECT,
                ActionType.DELETE_PROJECT,
                ActionType.ADD_MEMBER,
                ActionType.REMOVE_MEMBER,
                ActionType.DELETE_ISSUE,
                ActionType.MODIFY_HOOK,
                ActionType.RECREATE_PROJECT,
                ActionType.ENABLE_ISSUE_CHECK,
                ActionType.DISABLE_ISSUE_CHECK,
                ActionType.ENABLE_PLUGIN,
                ActionType.DISABLE_PLUGIN,
                ActionType.DELETE_SIDEEX_JSONFILE,
                ActionType.DELETE_EXCALIDRAW,
                ActionType.RESTORE_EXCALIDRAW_HISTORY,
            ]
        )
    )
    query = query.filter(
        or_(
            model.Activity.object_id.like(f"%@{project_id}"),
            model.Activity.object_id.like(f"%@{project_id}@%"),
            model.Activity.object_id == str(project_id),
        )
    )
    return query


class Activity(model.Activity):
    def fill_by_arguments(self, args):
        if self.action_type in [
            ActionType.UPDATE_PROJECT,
            ActionType.DELETE_PROJECT,
            ActionType.RECREATE_PROJECT,
        ]:
            self.fill_project(args["project_id"])
        if self.action_type == ActionType.UPDATE_PROJECT:
            self.action_parts += f'@{str(args["args"])}'
        if self.action_type in [ActionType.ADD_MEMBER, ActionType.REMOVE_MEMBER]:
            self.object_id = f'{args["user_id"]}@{args["project_id"]}'
            project = nexus.nx_get_project(id=args["project_id"])
            user = nexus.nx_get_user(id=args["user_id"])
            self.action_parts = f"{user.name}@{project.name}"
        if self.action_type in [ActionType.UPDATE_USER, ActionType.DELETE_USER]:
            self.fill_user(args["user_id"])
        if self.action_type == ActionType.UPDATE_USER:
            content = args["args"].copy()
            for sensitive_key in ["password", "old_password"]:
                if sensitive_key in content:
                    content[sensitive_key] = "********"
            self.action_parts += f"@{str(content)}"
        if self.action_type == ActionType.DELETE_ISSUE:
            self.fill_issue(args["issue_id"])
        if self.action_type == ActionType.MODIFY_HOOK:
            issue_commit_relation = model.IssueCommitRelation.query.get(args["args"]["commit_id"])
            action_parts = f"{issue_commit_relation.commit_id[:8]} \
                {issue_commit_relation.author_name} {issue_commit_relation.commit_message} is modified the relation from \
                {issue_commit_relation.issue_ids} to {args['args']['issue_ids']}"
            self.action_parts = action_parts

            if len(issue_commit_relation.issue_ids) <= len(args["args"]["issue_ids"]):
                self.fill_modify_hook(issue_commit_relation.issue_ids, args["args"]["issue_ids"])
            else:
                self.fill_modify_hook(args["args"]["issue_ids"], issue_commit_relation.issue_ids)
        if self.action_type == ActionType.ENABLE_ISSUE_CHECK:
            self.object_id = str(args["project_id"])
            self.action_parts = "開啟檢查創建議題之狀態"
        if self.action_type == ActionType.DISABLE_ISSUE_CHECK:
            self.object_id = str(args["project_id"])
            self.action_parts = "關閉檢查創建議題之狀態"
        if self.action_type == ActionType.ENABLE_PLUGIN:
            self.object_id = get_jwt_identity()["user_id"]
            self.action_parts = f'Enable plugin: {args["plugin_name"]}'
        if self.action_type == ActionType.DISABLE_PLUGIN:
            self.object_id = get_jwt_identity()["user_id"]
            self.action_parts = f'Disable plugin: {args["plugin_name"]}'
        if self.action_type == ActionType.DELETE_SIDEEX_JSONFILE:
            self.object_id = f'{get_jwt_identity()["user_id"]}@{args["project_id"]}'
            self.action_parts = (
                f'The sideex records and setting files of project:{args["project_id"]} '
                f'was deleted by user:{get_jwt_identity()["user_id"]}!'
            )
        # if self.action_type == ActionType.DELETE_EXCALIDRAW:
        #     self.object_id = get_jwt_identity()["user_id"]
        #     self.action_parts = f'Delete excalidraw: {args["excalidraw_id"]}'
        # if self.action_type == ActionType.RESTORE_EXCALIDRAW_HISTORY:
        #     excalidraw_id = args["excalidraw_history_id"]
        #     project_id = model.ExcalidrawHistory.query.get(excalidraw_id).excalidraw.project.id
        #     self.object_id = f'{get_jwt_identity()["user_id"]}@{project_id}'
        #     self.action_parts = f'Restore excalidraw history: {args["excalidraw_history_id"]}'
        # 20230202 為建立 storage class 到資料庫而產生 ACTIVITY 而新增下列一段程式
        if self.action_type == ActionType.CREATE_SC:
            self.object_id = f'{get_jwt_identity()["user_id"]}@{args["cluster_id"]}'
            self.action_parts = (
                f'Create storage class records of cluster:{args["storage_name"]}{args["cluster_id"]} '
                f'was deleted by user:{get_jwt_identity()["user_id"]}!'
            )
        # 20230202 為建立 storage class 到資料庫而產生 ACTIVITY 而新增上列一段程式

    def __get_issue_project_id(self, issue_id):
        row = model.ProjectPluginRelation.query.filter_by(
            plan_project_id=redmine.issue.get(issue_id).project.id
        ).first()
        return str(row.project_id) if row is not None else "-1"

    def fill_modify_hook(self, short_issue_ids, long_issue_ids):
        copy_short_issue_ids = short_issue_ids.copy()
        copy_long_issue_ids = long_issue_ids.copy()
        for issue_id in short_issue_ids:
            if issue_id in long_issue_ids:
                copy_short_issue_ids.remove(issue_id)
                copy_long_issue_ids.remove(issue_id)

        self.object_id = "@" + "@".join(
            list(
                map(
                    self.__get_issue_project_id,
                    copy_short_issue_ids + copy_long_issue_ids,
                )
            )
        )

    def fill_by_return_value(self, ret):
        if self.action_type == ActionType.CREATE_PROJECT:
            self.fill_project(ret["project_id"])
        if self.action_type == ActionType.CREATE_USER:
            self.fill_user(ret["user_id"])

    def fill_project(self, project_id):
        project = nexus.nx_get_project(id=project_id)
        self.object_id = project_id
        self.action_parts = f"{project.display}({project.name}/{project.id})"

    def fill_user(self, user_id):
        user = nexus.nx_get_user(id=user_id)
        self.object_id = user_id
        self.action_parts = f"{user.name}({user.login}/{user.id})"

    def fill_issue(self, issue_id):
        from resources import issue

        iss = issue.get_issue(issue_id, False, False)
        self.object_id = iss["project"]["id"]
        self.action_parts = f'{issue_id}/{iss["subject"]}({iss["project"]["name"]})'


# --------------------- Resources ---------------------
class AllActivities(Resource):
    @jwt_required()
    def get(self):
        role.require_admin()
        parser = reqparse.RequestParser()
        parser.add_argument("limit", type=int, default=10, location="args")
        parser.add_argument("offset", type=int, default=0, location="args")
        parser.add_argument("from_date", type=str, location="args")
        parser.add_argument("to_date", type=str, location="args")
        parser.add_argument("search", type=str, location="args")
        args = parser.parse_args()
        query = build_query(args)
        return util.success(get_activities(args, query))


class ProjectActivities(Resource):
    @jwt_required()
    def get(self, project_id):
        role.require_pm()
        role.require_in_project(project_id)
        parser = reqparse.RequestParser()
        parser.add_argument("limit", type=int, default=10, location="args")
        parser.add_argument("offset", type=int, default=0, location="args")
        parser.add_argument("from_date", type=str, location="args")
        parser.add_argument("to_date", type=str, location="args")
        parser.add_argument("search", type=str, location="args")
        args = parser.parse_args()
        query = build_query(args, base_query=limit_to_project(project_id))
        return util.success(get_activities(args, query))
