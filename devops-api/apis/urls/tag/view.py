from flask_apispec import marshal_with, doc, use_kwargs
from flask_apispec.views import MethodResource
from flask_jwt_extended import jwt_required
from flask_restful import Resource, reqparse
from flask_jwt_extended import jwt_required, get_jwt_identity
import util
from urls.tag import router_model
from resources.tag import (
    get_user_project_ids,
    get_tags_for_dict,
    get_tags,
    check_tags,
    create_tags,
    get_tag,
    update_tag,
    delete_tag,
)

import model
import util as util
from model import db
from resources import role
from sqlalchemy.exc import NoResultFound

error_tag_name_is_exists = "Tag Name was Created"


class UserTags(Resource):
    @jwt_required()
    def get(self):
        try:
            identity = get_jwt_identity()
            user_id = identity["user_id"]
            project_id = get_user_project_ids(user_id)
            return util.success({"tags": get_tags_for_dict(project_id)})
        except NoResultFound:
            return util.respond(404)


class Tags(Resource):
    @jwt_required()
    def get(self):
        try:
            parser = reqparse.RequestParser()
            parser.add_argument("project_id", type=int, location="args")
            parser.add_argument("tag_name", type=str, location="args")
            args = parser.parse_args()
            if args.get("project_id", None) is None:
                return util.success({"tags": get_tags()})
            else:
                return util.success({"tags": get_tags(args.get("project_id"), args.get("tag_name", None))})
        except NoResultFound:
            return util.respond(404)

    @jwt_required()
    def post(self):
        try:
            parser = reqparse.RequestParser()
            parser.add_argument("project_id", type=str, required=True, location="form")
            parser.add_argument("name", type=str, required=True, location="form")
            args = parser.parse_args()
            tag_name = args.get("name")
            project_id = args.get("project_id")
            if check_tags(project_id, tag_name) > 0:
                return util.respond(403, error_tag_name_is_exists)
            return util.success({"tags": {"id": create_tags(project_id, args)}})
        except NoResultFound:
            return util.respond(404)


@doc(tags=["Issue"], description="Tags API")
class TagsV2(MethodResource):
    @use_kwargs(router_model.TagsSchema, location="query")
    @marshal_with(router_model.GetTagsResponse)
    @jwt_required()
    def get(self, **kwargs):
        try:
            if kwargs.get("project_id", None) is None:
                return util.success({"tags": get_tags()})
            else:
                return util.success({"tags": get_tags(kwargs.get("project_id"), kwargs.get("tag_name", None))})
        except NoResultFound:
            return util.respond(404)

    @use_kwargs(router_model.TagsSchema, location="form")
    @marshal_with(router_model.TagResponse)
    @jwt_required()
    def post(self, **kwargs):
        try:
            tag_name = kwargs.get("name")
            project_id = kwargs.get("project_id")
            if check_tags(project_id, tag_name) > 0:
                return util.respond(403, error_tag_name_is_exists)
            return util.success({"tags": {"id": create_tags(project_id, kwargs)}})
        except NoResultFound:
            return util.respond(404)


class Tag(Resource):
    @jwt_required()
    def get(self, tag_id):
        try:
            return util.success({"tag": get_tag(tag_id)})
        except NoResultFound:
            return util.respond(404)

    @jwt_required()
    def put(self, tag_id):
        try:
            parser = reqparse.RequestParser()
            parser.add_argument("name", type=str, required=True, location="form")
            args = parser.parse_args()
            return util.success({"tag": update_tag(tag_id, args.get("name"))})
        except NoResultFound:
            return util.respond(404)

    @jwt_required()
    def delete(self, tag_id):
        try:
            return util.success({"tag": delete_tag(tag_id)})
        except NoResultFound:
            return util.respond(404)


@doc(tags=["Issue"], description="Tag API")
class TagV2(MethodResource):
    @marshal_with(router_model.TagResponse)
    @jwt_required()
    def get(self, tag_id):
        try:
            return util.success({"tag": get_tag(tag_id)})
        except NoResultFound:
            return util.respond(404)

    @use_kwargs(router_model.TagsSchema, location="form")
    @marshal_with(router_model.PutTagResponse)
    @jwt_required()
    def put(self, tag_id, **kwargs):
        try:
            return util.success({"tag": update_tag(tag_id, kwargs["name"])})
        except NoResultFound:
            return util.respond(404)

    @marshal_with(router_model.PutTagResponse)
    @jwt_required()
    def delete(self, tag_id):
        try:
            return util.success({"tag": delete_tag(tag_id)})
        except NoResultFound:
            return util.respond(404)
