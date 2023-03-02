from datetime import datetime
from typing import Any, Optional

from flask_apispec import doc, marshal_with, use_kwargs
from flask_apispec.views import MethodResource
from flask_jwt_extended import jwt_required
from flask_restful import Resource, reqparse

import util as util
from resources.lock import get_lock_status
from urls.lock import router_model


class LockStatus(Resource):
    @jwt_required()
    def get(self):
        parser = reqparse.RequestParser()
        parser.add_argument("name", type=str, required=True, location="args")
        args = parser.parse_args()

        ret: dict[str, Any] = get_lock_status(args["name"])
        sync_date: Optional[datetime] = ret.get("sync_date")

        if sync_date:
            ret["sync_date"] = sync_date.isoformat()
        return util.success(ret)


@doc(tags=["System"], description="Lock API")
class LockStatusV2(MethodResource):
    @use_kwargs(router_model.LockSchema, location="query")
    @marshal_with(router_model.LockResponse)
    @jwt_required()
    def get(self, **kwargs):
        ret: dict[str, Any] = get_lock_status(kwargs["name"])
        sync_date: Optional[datetime] = ret.get("sync_date")

        if sync_date:
            ret["sync_date"] = sync_date.isoformat()
        return util.success(ret)
