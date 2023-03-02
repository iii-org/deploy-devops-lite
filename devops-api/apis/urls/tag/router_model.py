from marshmallow import Schema, fields
from util import CommonBasicResponse

### Tag Get

#################################### Schema ####################################

########## API Action ##########


class TagSchema(Schema):
    name = fields.Str(required=False, doc="name", example="tag name")


#################################### Response ####################################

########## Module ##########

########## API Action ##########
class TagDataTagResponse(Schema):
    id = fields.Integer(required=False, doc=1)
    name = fields.Str(required=False, doc="name")


class TagDataResponse(Schema):
    tag = fields.Dict(example={"id": 1, "name": "name"}, required=False)


class TagResponse(CommonBasicResponse):
    data = fields.Nested(TagDataResponse, required=True)


class PutTagDataResponse(CommonBasicResponse):
    tag = fields.Integer(required=True, example=1)


class PutTagResponse(CommonBasicResponse):
    data = fields.Nested(PutTagDataResponse, required=True)


##################################################################


### Tags

#################################### Schema ####################################

########## API Action ##########


class PostTagsSchema(Schema):
    project_id = fields.Integer(required=False, doc="project_id", example=231)


class TagsSchema(PostTagsSchema):
    tag_name = fields.Str(required=False, doc="tag_name", example="1")


#################################### Response ####################################

########## Module ##########

########## API Action ##########


class GetTagsDataResponse(CommonBasicResponse):
    tags = fields.List(fields.Dict(example={"id": 1, "name": "name"}, required=False))


class GetTagsResponse(CommonBasicResponse):
    data = fields.Nested(GetTagsDataResponse, required=True)


##################################################################
