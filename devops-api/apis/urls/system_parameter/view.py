from flask_apispec import marshal_with, doc, use_kwargs
from flask_apispec.views import MethodResource
from resources import system_parameter
from flask_jwt_extended import jwt_required
from . import route_model
import util


class UploadFiles(MethodResource):
    @doc(tags=["System"], description="Get all upload_file_types's system parameter.")
    @marshal_with(route_model.UpdateFileGetResponse)
    @jwt_required()
    def get(self):
        return system_parameter.get_upload_file_types()

    @doc(tags=["System"], description="Create a upload_file_types in system parameter.")
    @use_kwargs(route_model.UpdateFilesPostSchema, location="form")
    @marshal_with(route_model.UpdateFilePostResponse)
    @jwt_required()
    def post(self, **kwargs):
        return system_parameter.create_upload_file_types(kwargs)


class UploadFile(MethodResource):
    @doc(
        tags=["System"],
        description="Delete a upload_file_types by upload_file_type_id.",
    )
    @marshal_with(util.CommonResponse)
    @jwt_required()
    def delete(self, upload_file_type_id):
        return system_parameter.delete_upload_file_types(upload_file_type_id)

    @doc(
        tags=["System"],
        description="Update a upload_file_types by upload_file_type_id.",
    )
    @use_kwargs(route_model.UpdateFilesPatchSchema, location="form")
    @marshal_with(route_model.UpdateFilePostResponse)
    @jwt_required()
    def patch(self, upload_file_type_id, **kwargs):
        return system_parameter.update_upload_file_types(upload_file_type_id, kwargs)


class GetUploadFileDistinctName(MethodResource):
    @doc(tags=["System"], description="Get upload_file_types distinct name.")
    @marshal_with(route_model.GetUploadFileDistinctNameResponse)
    @jwt_required()
    def get(self):
        return system_parameter.get_upload_file_distinct_name()


class UploadFileSize(MethodResource):
    @doc(tags=["System"], description="Get upload_file_size.")
    # @marshal_with(route_model.UpdateFileGetResponse)
    @jwt_required()
    def get(self):
        return system_parameter.get_upload_file_size()

    @doc(tags=["System"], description="Update upload_file_size.")
    @use_kwargs(route_model.UpdateUploadFileSizeSchema, location="json")
    @jwt_required()
    def patch(self, **kwargs):
        return system_parameter.update_upload_file_size(kwargs)
