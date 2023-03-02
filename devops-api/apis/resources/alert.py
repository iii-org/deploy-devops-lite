from flask_jwt_extended import jwt_required, get_jwt_identity
from flask_restful import Resource, reqparse

import model
import resources.project as project
import util as util
from model import db
import resources.apiError as apiError
from resources.apiError import DevOpsError
from sqlalchemy.exc import NoResultFound


def check_alert_permission(role_id, owner_id, project_id):
    if role_id not in [5, 7] and owner_id != model.Project.query.get(project_id).owner_id:
        raise apiError.NotProjectOwnerError(
            "You must be role admin, quality assurance or project owner for this operation."
        )


def is_project_alert_enable(project_id):
    return model.Project.query.filter_by(id=project_id).first().alert


def get_alert_by_project(project_id):
    if util.is_dummy_project(project_id):
        return []
    try:
        project.get_plan_project_id(project_id)
    except NoResultFound:
        raise DevOpsError(
            404,
            "Error while getting alerts.",
            error=apiError.project_not_found(project_id),
        )
    if not is_project_alert_enable(project_id):
        return []
    rows = model.Alert.query.filter_by(project_id=project_id).order_by(model.Alert.id).all()
    return {
        "alert_list": [
            {
                "id": row.id,
                "condition": row.condition,
                "days": row.days,
                "disabled": row.disabled,
            }
            for row in rows
        ]
    }


def create_alert(project_id, args):
    enable_alert = args["enable"]
    if enable_alert:
        alerts_num = model.Alert.query.filter_by(project_id=project_id).count()
        if alerts_num == 0:
            default_alert_days = model.DefaultAlertDays.query.first()
            comming_alert = model.Alert(
                project_id=project_id,
                condition="comming",
                days=default_alert_days.comming_days,
                disabled=False,
            )
            unchange_alert = model.Alert(
                project_id=project_id,
                condition="unchange",
                days=default_alert_days.unchange_days,
                disabled=False,
            )
            db.session.add_all([comming_alert, unchange_alert])

    project = model.Project.query.filter_by(id=project_id).first()
    project.alert = enable_alert
    db.session.commit()


def update_alert(alert_id, args):
    alert = model.Alert.query.get(alert_id)
    alert.days = args.get("days", alert.days)
    alert.disabled = args.get("disabled", alert.disabled)
    db.session.commit()


def update_default_alert_days(args):
    default_alert_days = model.DefaultAlertDays.query.first()
    default_alert_days.unchange_days = args.get("unchange_days", default_alert_days.unchange_days)
    default_alert_days.comming_days = args.get("comming_days", default_alert_days.comming_days)
    db.session.commit()


# --------------------- Resources ---------------------


class ProjectAlert(Resource):
    @jwt_required()
    def get(self, project_id):
        return util.success(get_alert_by_project(project_id))

    @jwt_required()
    def post(self, project_id):
        check_alert_permission(get_jwt_identity()["role_id"], get_jwt_identity()["user_id"], project_id)
        parser = reqparse.RequestParser()
        parser.add_argument("enable", type=bool, required=True)
        args = parser.parse_args()
        return util.success(create_alert(project_id, args))


class ProjectAlertUpdate(Resource):
    @jwt_required()
    def patch(self, alert_id):
        check_alert_permission(
            get_jwt_identity()["role_id"],
            get_jwt_identity()["user_id"],
            model.Alert.query.get(alert_id).project_id,
        )
        parser = reqparse.RequestParser()
        parser.add_argument("days", type=int)
        parser.add_argument("disabled", type=bool)
        args = parser.parse_args()
        args = {k: v for k, v in args.items() if v is not None}
        return util.success(update_alert(alert_id, args))


class DefaultAlertDaysUpdate(Resource):
    @jwt_required()
    def patch(self):
        parser = reqparse.RequestParser()
        parser.add_argument("unchange_days", type=int)
        parser.add_argument("comming_days", type=int)
        args = parser.parse_args()
        args = {k: v for k, v in args.items() if v is not None}
        return util.success(update_default_alert_days(args))
