from marshmallow import Schema, fields
from util import CommonBasicResponse


class IsUserExistsSchema(Schema):
    router = fields.Str(required=True)


class IsUserExistsResponse(CommonBasicResponse):
    data = fields.List(fields.Dict())
