from flask_restful import Resource, reqparse
from flask_jwt_extended import jwt_required, get_jwt_identity
from model import IssueDisplayField, db
import util

DEFAULT_DISPLAY_FIELD = ["name", "tracker", "status", "priority", "assigned_to"]


def create_issue_display_field(user_id, pj_id, field_type, display_field=DEFAULT_DISPLAY_FIELD):
    wbs_cache = IssueDisplayField(user_id=user_id, project_id=pj_id, type=field_type, display_field=display_field)
    db.session.add(wbs_cache)
    db.session.commit()


def get_issue_display_field(user_id, pj_id, field_type):
    lock_info = IssueDisplayField.query.filter_by(user_id=user_id, project_id=pj_id, type=field_type).first()
    if lock_info is None:
        create_issue_display_field(user_id, pj_id, field_type)
        return DEFAULT_DISPLAY_FIELD

    return lock_info.display_field


def put_issue_display_field(user_id, pj_id, field_type, display_field):
    lock_info = IssueDisplayField.query.filter_by(user_id=user_id, type=field_type, project_id=pj_id).first()
    if lock_info is None:
        create_issue_display_field(user_id, pj_id, field_type, display_field)
    else:
        lock_info.display_field = display_field
        db.session.commit()
    return display_field


# --------------------- Resources ---------------------
class IssueFieldDisplay(Resource):
    @jwt_required()
    def get(self):
        user_id = get_jwt_identity()["user_id"]
        parser = reqparse.RequestParser()
        parser.add_argument("project_id", type=int, required=True, location="args")
        parser.add_argument("type", type=str, required=True, location="args")
        args = parser.parse_args()

        return util.success(get_issue_display_field(user_id, args["project_id"], args["type"]))

    @jwt_required()
    def put(self):
        user_id = get_jwt_identity()["user_id"]
        parser = reqparse.RequestParser()
        parser.add_argument("project_id", type=int, required=True)
        parser.add_argument("type", type=str, required=True)
        parser.add_argument("display_fields", type=str, action="append", required=True)
        args = parser.parse_args()

        return util.success(put_issue_display_field(user_id, args["project_id"], args["type"], args["display_fields"]))
