from flask_apispec import doc, marshal_with
from flask_apispec.views import MethodResource
from flask_jwt_extended import jwt_required
from flask_restful import Resource
import util
from resources import sync_project

from . import route_model


class SyncProject(Resource):
    def get(self):
        sync_project.main_process()
        return util.success()


@doc(tags=["System"], description="Recreate third part projects")
class RecreateProjectV2(MethodResource):
    def patch(self, project_id):
        sync_project.recreate_project(project_id)
        return util.success()


@doc(tags=["System"], description="Check third part project is exist")
@marshal_with(route_model.IsProjectExists)
class CheckProjectExistV2(MethodResource):
    @jwt_required()
    def get(self):
        return util.success(sync_project.check_project_exist())
