from marshmallow import Schema, fields
from util import CommonBasicResponse
from resources.system_parameter import check_upload_type
from urls.route_model import (
    BasicIsssueResponse,
    SingleIssueGetDataAuthorResponse,
    ProjectExtraResponse,
    RelationsResponse,
    CommonSingleIssueResponse,
)

### Issue single

#################################### Schema ####################################

########## Module ##########
class FileSchema(Schema):
    upload_file = fields.Raw(doc="upload_file", example="(binary)", validate=check_upload_type)
    upload_files = fields.List(fields.Raw(doc="upload_files", example="(binary)", validate=check_upload_type))


class CommonSingleIssueSchema(Schema):
    description = fields.Str(doc="description", example="此為自動產生專案")
    assigned_to_id = fields.Str(doc="assigned_to_id", example="-1")
    estimated_hours = fields.Int(doc="estimated_hours", example=0)
    parent_id = fields.Str(doc="parent_id", example="-1")
    fixed_version_id = fields.Str(doc="fixed_version_id", example="-1")
    start_date = fields.Str(doc="start_date", example="1970-01-01")
    due_date = fields.Str(doc="due_date", example="1970-01-01")
    done_ratio = fields.Int(doc="done_ratio", example=-1)
    point = fields.Int(doc="point", example=0)
    tags = fields.Str(doc="tags", example="1,2")
    # Attachment upload
    # still finding how to test file type.
    upload_filename = fields.Str(doc="upload_filename", example="sport.csv")
    upload_description = fields.Str(doc="upload_description", example="運動數據")
    upload_content_type = fields.Str(doc="upload_content_type", example="string")


########## API Action ##########


class SingleIssuePostSchema(CommonSingleIssueSchema):
    project_id = fields.Int(doc="project_id", example=-1, required=True)
    tracker_id = fields.Int(doc="tracker_id", example=-1, missing=1)
    status_id = fields.Int(doc="status_id", example=-1, missing=1)
    priority_id = fields.Int(doc="priority_id", example=-1, missing=3)
    name = fields.Str(doc="name", example="string", required=True)
    creator_id = fields.Int(doc="creator_id", example=-1, required=False)
    changeNo = fields.Str(doc="changeNo", examplpe="str")
    changeUrl = fields.Str(doc="changeUrl", examplpe="str")


class SingleIssuePutSchema(CommonSingleIssueSchema):
    project_id = fields.Int(doc="project_id", example=-1)
    tracker_id = fields.Int(doc="tracker_id", example=-1)
    status_id = fields.Int(doc="status_id", example=-1)
    priority_id = fields.Int(doc="priority_id", example=-1)
    name = fields.Str(doc="name", example="專案子議題")
    note = fields.Str(doc="name", example="string")
    close_all = fields.Bool(doc="close_all", example="True")


class SingleIssueDeleteSchema(Schema):
    force = fields.Bool(doc="force", example="True")
    delete_excalidraw = fields.Bool(doc="force", example="True", missing=False)


#################################### Response ####################################

########## Module ##########


class IssueTagResponse(Schema):
    tags = fields.List(fields.Nested(BasicIsssueResponse, required=True, default=[]))


class SingleIssueGetDataChildrenResponse(BasicIsssueResponse, IssueTagResponse):
    status = fields.Nested(BasicIsssueResponse, required=True)
    assigned_to = fields.Nested(SingleIssueGetDataAuthorResponse, required=True)
    tracker = fields.Nested(BasicIsssueResponse, required=True)


class SingleIssueGetDataAttachResponse(Schema):
    id = fields.Int(required=True)
    filename = fields.Str(required=True)
    filesize = fields.Int(required=True)
    content_type = fields.Str(required=True)
    description = fields.Str(required=True)
    content_url = fields.Str(required=True)
    thumbnail_url = fields.Str(required=True)
    author = fields.Nested(BasicIsssueResponse, required=True)
    created_on = fields.Str(required=True, example="1970-01-01T00:00:00")


class JournalDetailsResponse(Schema):
    name = fields.Str()
    property = fields.Str(allow_none=True)
    old_value = fields.Str(allow_none=True)
    new_value = fields.Str(allow_none=True)


class SingleIssueGetDataJournalSchema(Schema):
    id = fields.Int(required=True)
    user = fields.Nested(BasicIsssueResponse, required=True)
    notes = fields.Str(required=True)
    created_on = fields.Str(required=True, example="1970-01-01T00:00:00")
    # private_notes = fields.Bool
    details = fields.List(fields.Nested(JournalDetailsResponse, required=True))
    private_notes = fields.Bool(required=True)


class ParentResponse(CommonSingleIssueResponse):
    estimated_hours = fields.Float(required=True)
    created_date = fields.Str(required=True, example="1970-01-01T00:00:00")
    point = fields.Int(required=True)
    attachments = fields.List(fields.Nested(SingleIssueGetDataAttachResponse), default=[])
    relations = fields.List(fields.Nested(RelationsResponse, required=True))
    parent = fields.List(fields.Nested(RelationsResponse, required=True))
    # changesets = fields.List(default=[])
    journals = fields.List(fields.Nested(SingleIssueGetDataJournalSchema, required=True))
    # watchers = fields.List(default=[])
    updated_date = fields.Str(required=True, example="1970-01-01T00:00:00")


# ? Nested parent info
class SingleIssueGetDataResponse(CommonSingleIssueResponse):
    estimated_hours = fields.Float(required=True)
    created_date = fields.Str(required=True, example="1970-01-01T00:00:00")
    point = fields.Int(required=True)
    relations = fields.List(fields.Dict(), required=True)
    children = fields.List(fields.Dict(), required=True)
    attachments = fields.List(fields.Nested(SingleIssueGetDataAttachResponse), default=[])
    parent = fields.Nested(ParentResponse, required=True)
    # changesets = fields.List(default=[])
    journals = fields.List(fields.Nested(SingleIssueGetDataJournalSchema, required=True))
    # watchers = fields.List(default=[])
    updated_date = fields.Str(required=True, example="1970-01-01T00:00:00")


class SingleIssuePostDataResponse(CommonSingleIssueResponse):
    estimated_hours = fields.Float(required=True)
    created_date = fields.Str(required=True, example="1970-01-01T00:00:00")
    point = fields.Int(required=True)
    relations = fields.List(fields.Nested(RelationsResponse, required=True))
    updated_on = fields.Str(required=True, example="1970-01-01T00:00:00")
    has_children = fields.Bool(required=True)
    children = fields.List(fields.Dict(), required=True)
    parent = fields.Nested(ParentResponse, required=True)
    family = fields.Bool(required=True)
    changeNo = fields.Str(example="ITSMS_no")
    changeUrl = fields.Str(example="www.google.com")
    issue_url = fields.Str(example="www.google.com")


class SingleIssuePutDataResponse(CommonSingleIssueResponse):
    estimated_hours = fields.Float(required=True)
    created_date = fields.Str(required=True, example="1970-01-01T00:00:00")
    point = fields.Int(required=True)
    relations = fields.List(fields.Dict(), required=True)
    project = fields.Nested(ProjectExtraResponse, required=True)
    updated_on = fields.Str(required=True, example="1970-01-01T00:00:00")
    has_children = fields.Bool(required=True)
    children = fields.List(fields.Dict(), required=True)
    parent = fields.Nested(ParentResponse, required=True)
    family = fields.Bool(required=True)


class IssueFamilyDataParentResponse(CommonSingleIssueResponse, IssueTagResponse):
    project = fields.Nested(ProjectExtraResponse, required=True)


class IssueFamilyDataChildrenResponse(CommonSingleIssueResponse, IssueTagResponse):
    project = fields.Nested(ProjectExtraResponse, required=True)
    updated_on = fields.Str(required=True, example="1970-01-01T00:00:00")
    family = fields.Bool(required=True)
    has_children = fields.Bool(required=True)


class IssueFamilyDataRelationResponse(CommonSingleIssueResponse, IssueTagResponse):
    project = fields.Nested(ProjectExtraResponse, required=True)
    updated_on = fields.Str(required=True, example="1970-01-01T00:00:00")
    has_children = fields.Bool(required=True)
    relation_id = fields.Int(required=True)


class IssueFamilyDataResponse(Schema):
    parent = fields.Nested(IssueFamilyDataParentResponse)
    children = fields.List(fields.Nested(IssueFamilyDataChildrenResponse))
    relations = fields.List(fields.Nested(IssueFamilyDataRelationResponse))


class MyOpenIssueStatisticsDataResponse(Schema):
    active_issue_number = fields.Int(required=True)


########## API Action ##########


class SingleIssueGetResponse(CommonBasicResponse):
    data = fields.Nested(SingleIssueGetDataResponse, required=True)


class SingleIssuePostResponse(CommonBasicResponse):
    data = fields.Nested(SingleIssuePostDataResponse, required=True)


class SingleIssuePutResponse(CommonBasicResponse):
    data = fields.Nested(SingleIssuePutDataResponse, required=True)


class SingleIssueDeleteResponse(CommonBasicResponse):
    data = fields.Str(default="success")


### Issue Family

#################################### Schema ####################################


class IssueIssueFamilySchema(Schema):
    with_point = fields.Str(doc="with_point", example=True)


class ClosableAllSchema(Schema):
    issue_ids = fields.List(fields.Int(), required=True)


class IssueSonsSchema(Schema):
    # Add a valiate
    fixed_version_ids = fields.Str(example="15,18", required=True)


#################################### Response ####################################


class IssueFamilyResponse(CommonBasicResponse):
    data = fields.Nested(IssueFamilyDataResponse, required=True)


### Issue Statistics

#################################### Response ####################################

########## Module ##########


class MyIssuePeirodStatisticsDataResponse(Schema):
    open = fields.Int(required=True)
    closed = fields.Int(required=True)


########## API Action ##########


class MyOpenIssueStatisticsResponse(CommonBasicResponse):
    data = fields.Nested(MyOpenIssueStatisticsDataResponse, required=True)


class MyIssueWeekStatisticsResponse(CommonBasicResponse):
    data = fields.Nested(MyIssuePeirodStatisticsDataResponse, required=True)


class MyIssueMonthStatisticsResponse(CommonBasicResponse):
    data = fields.Nested(MyIssuePeirodStatisticsDataResponse, required=True)


##### Issue's Relation issue

#################################### Schema ####################################


class RelationSchema(Schema):
    issue_id = fields.Int(doc="issue_id", example=1)
    issue_to_ids = fields.List(fields.Int(), doc="issue_id", example=[1, 2, 3])


#################################### Response ####################################


class CheckIssueClosableResponse(CommonBasicResponse):
    data = fields.Bool(required=True)


##### Issue commit relationship

#################################### Schema ####################################


class IssueCommitRelationGetSchema(Schema):
    commit_id = fields.Str(doc="commit_id", example="abc123def456", required=True)


class IssueCommitRelationPatchSchema(IssueCommitRelationGetSchema):
    issue_ids = fields.List(fields.Int(), doc="issue_ids", required=True, example=[1, 2, 3])


#################################### Response ####################################

########## Module ##########


class IssueCommitRelationDataResponse(Schema):
    issue_ids = fields.Dict(required=True, example={"1": True})


########## API Action ##########


class IssueCommitRelationResponse(CommonBasicResponse):
    data = fields.Nested(IssueCommitRelationDataResponse, required=True)
