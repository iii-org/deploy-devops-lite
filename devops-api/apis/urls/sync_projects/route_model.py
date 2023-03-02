from marshmallow import Schema, fields
from util import CommonBasicResponse


class IsProjectExists(CommonBasicResponse):
    data = fields.Dict(key=fields.Str(), values=fields.Str())
