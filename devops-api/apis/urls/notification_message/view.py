import json

import util
from flask_apispec import doc, marshal_with
from flask_apispec.views import MethodResource
from flask_jwt_extended import jwt_required
from flask_restful import Resource, reqparse
from flask_socketio import Namespace, join_room, leave_room
from resources import role
from resources.apiError import (
    DevOpsError,
    argument_error,
    not_enough_authorization,
    resource_not_found,
)
from resources.notification_message import (
    close_notification_message,
    create_notification_message,
    create_notification_message_reply_slip,
    delete_notification_message,
    get_notification_message_list,
    notification_room,
)

from . import router_model


def parameter_check(args):
    if args.get("alert_level") not in (1, 2, 3, 101, 102, 103, 301):
        raise DevOpsError(
            400,
            "Argument alert_level not in range.",
            error=argument_error("alert_level"),
        )
    for type_id in args.get("type_ids"):
        if type_id not in range(1, 6):
            raise DevOpsError(400, "Argument type_id not in range.", error=argument_error("type_id"))
        if type_id in range(2, 6) and args.get("type_parameters") is None:
            raise DevOpsError(400, "Missing type_parameters", error=argument_error("type_parameters"))
        elif type_id in [2, 5] and "project_ids" not in json.loads(args["type_parameters"]):
            raise DevOpsError(
                400,
                "Argument project_ids not exist in type_parameters.",
                error=argument_error("project_ids"),
            )
        elif type_id == 3 and "user_ids" not in json.loads(args["type_parameters"]):
            raise DevOpsError(
                400,
                "Argument user_id not exist in type_parameters.",
                error=argument_error("user_ids"),
            )
        elif type_id == 4 and "role_ids" not in json.loads(args["type_parameters"]):
            raise DevOpsError(
                400,
                "Argument role_ids not exist in type_parameters.",
                error=argument_error("role_ids"),
            )


class GetNotificationMessage(Namespace):
    def on_connect(self):
        print("Connect")

    def on_disconnect(self):
        print("Client disconnected")

    def on_join(self, data):
        # verify jwt token
        # verify user_id
        if "user_id" not in data:
            return
        print("Join room")
        join_room(f"user/{data['user_id']}")

    def on_leave(self, data):
        print("Leave room")
        leave_room(f"user/{data['user_id']}")

    def on_get_message(self, data):
        notification_room.get_message(data)


class MessageV2(MethodResource):
    @doc(
        tags=["Notification Message"],
        description="Create a notification message. Only for administrator",
    )
    # @use_kwargs(router_model.CreateNotificationMessageSchema, location="form")
    @marshal_with(util.CommonResponse)
    @jwt_required()
    def post(self):
        role.require_admin()
        parser = reqparse.RequestParser()
        parser.add_argument("alert_level", type=int, required=True)
        parser.add_argument("title", type=str)
        parser.add_argument("alert_service_id", type=int, default=0)
        parser.add_argument("message", type=str, required=True)
        parser.add_argument("type_ids", type=str, required=True)
        parser.add_argument("type_parameters", type=str)
        args = parser.parse_args()
        args["type_ids"] = json.loads(args["type_ids"].replace("'", '"'))
        parameter_check(args)
        if args.get("type_parameters") is not None:
            args["type_parameters"] = json.loads(args["type_parameters"].replace("'", '"'))
        else:
            args["type_parameters"] = ""
        return util.success(create_notification_message(args))


class MessageIdV2(MethodResource):
    @doc(
        tags=["Notification Message"],
        description="Delete the notification message. Only for administrator",
    )
    @marshal_with(util.CommonResponse)
    @jwt_required()
    def delete(self, message_id):
        role.require_admin()
        return util.success(delete_notification_message(message_id))


class MessageListV2(MethodResource):
    @doc(
        tags=["Notification Message"],
        description="User get notification message history.",
    )
    @jwt_required()
    def get(self):
        parser = reqparse.RequestParser()
        parser.add_argument("limit", type=int, default=10, location="args")
        parser.add_argument("offset", type=int, default=0, location="args")
        parser.add_argument("from_date", type=str, location="args")
        parser.add_argument("to_date", type=str, location="args")
        parser.add_argument("search", type=str, location="args")
        parser.add_argument("alert_ids", type=str, location="args")
        parser.add_argument("unread", type=bool, location="args")
        args = parser.parse_args()
        if args["alert_ids"]:
            args["alert_ids"] = json.loads(args["alert_ids"].replace("'", '"'))
        return util.success(get_notification_message_list(args))


class MessageListForAdminV2(MethodResource):
    @doc(
        tags=["Notification Message"],
        description="Administrator get all notification message. Only for administrator.",
    )
    @jwt_required()
    def get(self):
        role.require_admin()
        parser = reqparse.RequestParser()
        parser.add_argument("limit", type=int, default=10, location="args")
        parser.add_argument("offset", type=int, default=0, location="args")
        parser.add_argument("from_date", type=str, location="args")
        parser.add_argument("to_date", type=str, location="args")
        parser.add_argument("search", type=str, location="args")
        parser.add_argument("alert_ids", type=str, location="args")
        parser.add_argument("include_system_message", type=bool, location="args")
        args = parser.parse_args()
        if args["alert_ids"]:
            args["alert_ids"] = json.loads(args["alert_ids"].replace("'", '"'))
        return util.success(get_notification_message_list(args, admin=True))


class MessageReplyV2(MethodResource):
    @doc(tags=["Notification Message"], description="Send back after user read message.")
    @jwt_required()
    def post(self, user_id):
        role.require_user_himself(user_id, even_admin=True)
        parser = reqparse.RequestParser()
        parser.add_argument("message_ids", type=list, location="json", required=True)
        args = parser.parse_args()
        return util.success(create_notification_message_reply_slip(user_id, args))


class MessageCloseV2(MethodResource):
    @doc(
        tags=["Notification Message"],
        description="Close message (mean all user read message). Only for administrator.",
    )
    @jwt_required()
    def post(self, message_id):
        role.require_admin()
        return util.success(close_notification_message(message_id))
