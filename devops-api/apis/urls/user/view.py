from flask_apispec import marshal_with, doc, use_kwargs
from flask_apispec.views import MethodResource
from flask_jwt_extended import jwt_required
from flask_restful import Resource, reqparse
import util
from urls.user import router_model
from resources.user import (
    login,
    change_user_status,
    create_user,
    NexusUser,
    delete_user,
    update_user,
    user_list,
    # user_sa_config,
    get_user_message_types,
    update_user_message_types,
    get_user_message_type,
    get_decode_password,
    update_newpassword,
)
from resources import role
from . import router_model
import json
from model import db, User

security_params = [{"bearer": []}]
# --------------------- Resources ---------------------


@doc(tags=["User"], description="Login API", security=security_params)
@use_kwargs(router_model.LoginSchema, location=("json"))
@marshal_with(router_model.LoginResponse)  # marshalling
class LoginV2(MethodResource):
    # noinspection PyMethodMayBeStatic
    def post(self, **kwargs):
        return login(kwargs)


# class Login(Resource):
#     # noinspection PyMethodMayBeStatic
#     def post(self):
#         parser = reqparse.RequestParser()
#         parser.add_argument('username', type=str, required=True)
#         parser.add_argument('password', type=str, required=True)
#         args = parser.parse_args()
#         return login(args)


class UserStatus(Resource):
    @jwt_required()
    def put(self, user_id):
        role.require_admin("Only admins can modify user.")
        parser = reqparse.RequestParser()
        parser.add_argument("status", type=str, required=True)
        args = parser.parse_args()
        return change_user_status(user_id, args)


@doc(tags=["User"], description="SingleUser API")
class PostSingleUserV2(MethodResource):
    @use_kwargs(router_model.PostSingleUserSchema, location=("form"))
    @marshal_with(router_model.CreateSingleUserResponse)
    @jwt_required()
    def post(self, **kwargs):
        role.require_admin("Only admins can create user.")
        return util.success(create_user(kwargs))


@doc(tags=["User"], description="SingleUser API")
class GetSingleUserV2(MethodResource):
    @marshal_with(router_model.GetSingleUserResponse)
    @jwt_required()
    def get(self, user_id):
        role.require_user_himself(
            user_id,
            even_pm=False,
            err_message="Only admin and PM can access another user's data.",
        )
        return util.success(NexusUser().set_user_id(user_id).to_json())

    @marshal_with(router_model.SingleUserResponse)
    @jwt_required()
    def delete(self, user_id):
        role.require_admin("Only admin can delete user.")
        return util.success(delete_user(user_id))

    @use_kwargs(router_model.PutSingleUserSchema, location="form")
    @marshal_with(router_model.SingleUserResponse)
    @jwt_required()
    def put(self, user_id, **kwargs):
        role.require_user_himself(user_id)
        return update_user(user_id, kwargs)


class SingleUser(Resource):
    @jwt_required()
    def get(self, user_id):
        role.require_user_himself(
            user_id,
            even_pm=False,
            err_message="Only admin and PM can access another user's data.",
        )
        return util.success(NexusUser().set_user_id(user_id).to_json())

    @jwt_required()
    def put(self, user_id):
        role.require_user_himself(user_id)
        parser = reqparse.RequestParser()
        parser.add_argument("name", type=str)
        parser.add_argument("password", type=str)
        parser.add_argument("old_password", type=str)
        parser.add_argument("phone", type=str)
        parser.add_argument("email", type=str)
        parser.add_argument("status", type=str)
        parser.add_argument("department", type=str)
        parser.add_argument("title", type=str)
        parser.add_argument("role_id", type=int)
        args = parser.parse_args()
        return update_user(user_id, args)

    @jwt_required()
    def delete(self, user_id):
        role.require_admin("Only admin can delete user.")
        return util.success(delete_user(user_id))

    @jwt_required()
    def post(self):
        role.require_admin("Only admins can create user.")
        parser = reqparse.RequestParser()
        parser.add_argument("name", type=str, required=True)
        parser.add_argument("email", type=str, required=True)
        parser.add_argument("phone", type=str)
        parser.add_argument("login", type=str, required=True)
        parser.add_argument("password", type=str, required=True)
        parser.add_argument("role_id", type=int, required=True)
        parser.add_argument("status", type=str)
        parser.add_argument("force", type=bool)
        args = parser.parse_args()
        return util.success(create_user(args))


class UserList(Resource):
    @jwt_required()
    def get(self):
        role.require_pm()
        parser = reqparse.RequestParser()
        parser.add_argument("role_ids", type=str, location="args")
        parser.add_argument("page", type=int, location="args")
        parser.add_argument("per_page", type=int, location="args")
        parser.add_argument("search", type=str, location="args")
        args = parser.parse_args()
        filters = {}
        if args["role_ids"] is not None:
            filters["role_ids"] = json.loads(f'[{args["role_ids"]}]')
        if args["page"] is not None:
            filters["page"] = args["page"]
        if args["per_page"] is not None:
            filters["per_page"] = args["per_page"]
        if args["search"] is not None:
            filters["search"] = args["search"]
        return util.success(user_list(filters))


@doc(tags=["User"], description="SingleUser API")
class GetUserByemailV2(MethodResource):
    @marshal_with(router_model.GetSingleUserResponse)
    @jwt_required()
    def get(self, email):
        query = User.query.filter(User.email == email).first()
        role.require_user_himself(
            query.id,
            even_pm=False,
            err_message="Only admin and PM can access another user's data.",
        )
        return util.success(NexusUser().set_user_id(query.id).to_json())


@doc(tags=["User"], description="SingleUser API", security=security_params)
class UserListV2(MethodResource):
    @use_kwargs(router_model.UserListSchema, location="query")
    @marshal_with(router_model.GetUserListResponse)  # marshalling
    @jwt_required()
    def get(self, **kwargs):
        role.require_pm()
        filters = {}
        if kwargs.get("role_ids") is not None:
            filters["role_ids"] = json.loads(f'[{kwargs.get("role_ids")}]')
        if kwargs.get("page") is not None:
            filters["page"] = kwargs.get("page")
        if kwargs.get("per_page") is not None:
            filters["per_page"] = kwargs.get("per_page")
        if kwargs.get("search") is not None:
            filters["search"] = kwargs.get("search")
        return util.success(user_list(filters))


# class UserSaConfig(Resource):
#     @jwt_required()
#     def get(self, user_id):
#         role.require_user_himself(
#             user_id,
#             even_pm=False,
#             err_message="Only admin and PM can access another user's data.",
#         )
#         return user_sa_config(user_id)


class MessageTypes(MethodResource):
    @doc(tags=["User"], description="Users' message Types open situation.")
    @use_kwargs(router_model.GetUserMessageTypeSchema, location="query")
    @marshal_with(router_model.GetUsersMessageTypeRes)
    @jwt_required()
    def get(self, **kwargs):
        return util.success(get_user_message_types(**kwargs))


class MessageType(MethodResource):
    @doc(tags=["User"], description="Users' message Types open situation.")
    @marshal_with(router_model.GetUserMessageTypeRes)
    @jwt_required()
    def get(self, user_id):
        role.require_user_himself(user_id)
        return util.success(get_user_message_type(user_id))

    @doc(tags=["User"], description="Update Users' message Types open situation.")
    @use_kwargs(router_model.PatchUserMessageTypeSchema, location="json")
    @marshal_with(util.CommonResponse)
    @jwt_required()
    def patch(self, user_id, **kwargs):
        role.require_user_himself(user_id)
        update_user_message_types(user_id, kwargs)
        return util.success()


@doc(tags=["User"], description="User's server password operate")
class UserNewpasswordInfoV2(MethodResource):
    @marshal_with(router_model.GetUserPasswordInfoRes)
    @jwt_required()
    def get(self, user_id):
        password_info = get_decode_password(user_id)
        return util.success(password_info)

    @marshal_with(util.CommonResponse)
    @use_kwargs(router_model.NewpasswordResponse, location="json")
    @jwt_required()
    def put(self, user_id, **kwargs):
        msg, valid = update_newpassword(user_id, kwargs)
        if valid:
            return util.success()
        else:
            return util.respond(400, msg)
