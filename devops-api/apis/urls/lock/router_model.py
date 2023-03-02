from marshmallow import Schema, fields
from util import CommonBasicResponse

### Tag Get

#################################### Schema ####################################

########## API Action ##########


class LockSchema(Schema):
    name = fields.Str(required=False, doc="Lock name", example="Lock name")


#################################### Response ####################################

########## Module ##########

########## API Action ##########


class LockDataResponse(Schema):
    name = fields.Str(required=True, example="download_pj_issues")
    is_lock = fields.Bool(required=True, example=False)
    sync_date = fields.Str(required=True, example="1970-01-01 00:00:00")


class LockResponse(CommonBasicResponse):
    data = fields.Nested(LockDataResponse, required=True)


##################################################################
