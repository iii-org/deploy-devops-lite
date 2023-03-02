from flask_apispec import doc, marshal_with, use_kwargs
from flask_apispec.views import MethodResource
from flask_jwt_extended import jwt_required
from flask_restful import Resource
import util
from resources import sync_user

from . import route_model


class SyncUsers(Resource):
    def get(self):
        return util.success(sync_user.recreate_users())


@doc(tags=["System"], description="Check third part user is exist")
@use_kwargs(route_model.IsUserExistsSchema, location="form")
@marshal_with(route_model.IsUserExistsResponse)
class CheckUserExistV2(MethodResource):
    @jwt_required()
    def post(self, **kwargs):
        return util.success(sync_user.check_user_exist(kwargs["router"]))


@doc(tags=["System"], description="Recreate third part users")
class RecreateUserV2(MethodResource):
    @jwt_required()
    def post(self, user_id):
        return util.success(sync_user.recreate_user(user_id))
