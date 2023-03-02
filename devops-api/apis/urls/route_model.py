from marshmallow import Schema, fields
from util import CommonBasicResponse


#################################### Schema ####################################

########## Module ##########
# !!!


class CommonIssueSchema(Schema):
    fixed_version_id = fields.Str(doc="fixed_version_id", example="1")
    status_id = fields.Str(doc="status_id", example="1")
    tracker_id = fields.Str(doc="tracker_id", example="1")
    assigned_to_id = fields.Str(doc="assigned_to_id", example="1")
    priority_id = fields.Str(doc="priority_id", example="1")
    only_superproject_issues = fields.Bool(doc="only_superproject_issues", example=True, load_default=False)
    limit = fields.Int(doc="limit", example=1)
    offset = fields.Int(doc="offset", example=1)
    search = fields.Str(doc="search", example="string")
    selection = fields.Str(doc="selection", example="string")
    sort = fields.Str(doc="sort", example="string")


class GitlabSourceCodeSchema(Schema):
    repo_name = fields.Str(doc="repo_name", example="ui-cteate")
    branch_name = fields.Str(doc="branch_name", example="master")
    commit_id = fields.Str(doc="commit_id", example="4419301qa")
    source_code_num = fields.Int(doc="source_code_num", example=3352)


class GitlabPostProjectBranchesSch(Schema):
    branch = fields.Str(doc="branch", example="new branch name")
    ref = fields.Str(doc="ref", example="branch name")


class GitGetBranchCommitsSch(Schema):
    branch = fields.Str(doc="branch", example="master", required=True)
    filter = fields.Str(doc="filter", example="Administrator")


class GitGetProjectIdFromURISch(Schema):
    repository_url = fields.Str(
        doc="repository_url",
        example="http://gitlab-dev.iiidevops.org/root/testcreateproject.git",
        required=True,
    )


class GitGetProjectURLFromIdSch(Schema):
    project_id = fields.Int(doc="project_id", example=1, required=True)
    repository_id = fields.Int(doc="repository_id", example=30, required=True)


class RancherCreateAppSchema(Schema):
    name = fields.Str(doc="name", example="daily-check1")
    namespace = fields.Str(doc="namespace", example="daily-check-0711")
    externalId = fields.Str(
        doc="externalId",
        example="catalog://?catalog=iii-dev-charts3&template=test-sideex&version=0.3.1",
    )
    appRevisionId = fields.Str(doc="appRevisionId", example="apprevision - tdwxf")
    targetNamespace = fields.Str(doc="targetNamespace", example="daily-check-0711")
    anwsers = fields.Dict(
        doc="answers",
        example={
            "git.branch": "master",
            "git.commitID": "a32c8ab",
            "git.repoName": "daily-check-0711",
            "git.url": "http://gitlab-dev.iiidevops.org/root/daily-check-0711.git",
            # "harbor.host": "harbor-dev.iiidevops.org",
            "pipeline.sequence": "2",
            "web.deployName": "daily-check-0711-master-serv",
            "web.port": "5000",
        },
    )


class GitGetMembersCommitsSch(Schema):
    branch = fields.Str(doc="branch", example="master", required=True)


class RouterSimpleSchema(Schema):
    simple = fields.Boolean(example=True)


########## API Action ##########

# class FileSchema(Schema):
#     upload_file = fields.Raw(type='werkzeug.datastructures.FileStorage', doc='upload_file', example="")


# !!!
class IssueVesionListSchema(CommonIssueSchema):
    fixed_version_id = fields.Str(doc="fixed_version_id", required=True, example="1")


class IssueByUserSchema(CommonIssueSchema):
    project_id = fields.Int(doc="project_id", example=1)
    # this one is reserved word!!!
    # from = fields.Str(doc='from', example="string")
    tags = fields.Str(doc="tags", example="string")


class GitlabSourceCodeResponse(CommonBasicResponse):
    data = fields.Nested(GitlabSourceCodeSchema, required=False)


class IssueTrackerSchema(Schema):
    new = fields.Bool()
    project_id = fields.Int()


#################################### Response ####################################

########## Module ##########
class PaginationPageResponse(Schema):
    current = fields.Int(required=True)
    prev = fields.Int(required=True, default=None)
    next = fields.Int(required=True)
    pages = fields.Int(required=True)
    limit = fields.Int(required=True)
    offset = fields.Int(required=True)
    total = fields.Int(required=True)


class PaginationResponse(Schema):
    page = fields.Nested(PaginationPageResponse, required=True)


class BasicIsssueResponse(Schema):
    id = fields.Int(required=True)
    name = fields.Str(required=True)


class ProjectExtraResponse(BasicIsssueResponse):
    id = fields.Int(required=True)
    name = fields.Str(required=True)
    display = fields.Str(required=True)


class SingleIssueGetDataAuthorResponse(BasicIsssueResponse):
    login = fields.Str(required=True, example="postman_test_rd")


class IssueTagResponse(Schema):
    tags = fields.List(fields.Nested(BasicIsssueResponse, required=True, default=[]))


class RelationsResponse(IssueTagResponse):
    id = fields.Int(required=True)
    issue_id = fields.Int(required=True)
    issue_to_id = fields.Int(required=True)
    relation_type = fields.Str(required=True)
    delay = fields.Str(required=True, allow_none=True)


class CommonSingleIssueResponse(Schema):
    id = fields.Int(required=True)
    name = fields.Str(required=True)
    project = fields.Nested(BasicIsssueResponse, required=True)
    description = fields.Str(required=True)
    start_date = fields.Str(required=True, example="1970-01-01", default=None)
    assigned_to = fields.Nested(SingleIssueGetDataAuthorResponse, default={})
    fixed_version = fields.Nested(BasicIsssueResponse, default={})
    due_date = fields.Str(required=True, example="1970-01-01", default=None)
    done_ratio = fields.Int(required=True)
    is_closed = fields.Bool(required=True)
    issue_link = fields.Str(required=True)
    tracker = fields.Nested(BasicIsssueResponse, default={})
    priority = fields.Nested(BasicIsssueResponse, default={})
    status = fields.Nested(BasicIsssueResponse, default={})
    author = fields.Nested(BasicIsssueResponse, default={})


class IssueByUserDataResponse(CommonSingleIssueResponse, IssueTagResponse):
    estimated_hours = fields.Float(required=True)
    created_date = fields.Str(required=True, example="1970-01-01T00:00:00")
    point = fields.Int(required=True)
    relations = fields.List(fields.Nested(RelationsResponse, required=True))
    updated_on = fields.Str(required=True, example="1970-01-01T00:00:00")
    family = fields.Bool(required=True)
    has_children = fields.Bool(required=True)


class IssueByUserDataWithPageResponse(PaginationResponse):
    issue_list = fields.List(fields.Nested(IssueByUserDataResponse, required=True))


class IssueStatusDataResponse(BasicIsssueResponse):
    is_closed = fields.Bool(required=True)


class IssuePriorityDataResponse(BasicIsssueResponse):
    is_closed = fields.Bool(required=True)


class IssueTrackerDataResponse(BasicIsssueResponse):
    pass


class BasicParentResponse(BasicIsssueResponse):
    status = fields.Nested(BasicIsssueResponse, default={})
    tracker = fields.Nested(BasicIsssueResponse, default={})
    assigned_to = fields.Nested(SingleIssueGetDataAuthorResponse, default={})


class MyIssuePeirodStatisticsDataResponse(Schema):
    open = fields.Int(required=True)
    closed = fields.Int(required=True)


class BasicDashboardIssueDataResponse(Schema):
    name = fields.Str(required=True)
    number = fields.Int(required=True)


class GetFlowTypeDataResponse(Schema):
    name = fields.Str(required=True)
    flow_type_id = fields.Int(required=True)


class GitPostProjectTagSch(Schema):
    tag_name = fields.Str(doc="tag_name", required=True, example="v1.1")
    ref = fields.Str(doc="ref", required=True, example="master")
    message = fields.Str(doc="message", example="add v1.1")
    release_description = fields.Str(doc="release_description", example="This is a new tag")


class IssueFilterByProjectDataResponse(BasicIsssueResponse):
    user_id = fields.Int(required=True)
    project_id = fields.Int(required=True)
    type = fields.Str(required=True)
    custom_filter = fields.Dict(required=True)


########## API Action#############
class IssueByUserResponseWithPage(CommonBasicResponse):
    data = fields.List(fields.Nested(IssueByUserDataWithPageResponse, required=True))


class IssueStatusResponse(CommonBasicResponse):
    data = fields.List(fields.Nested(IssueStatusDataResponse, required=True))


class IssuePriorityResponse(CommonBasicResponse):
    data = fields.List(fields.Nested(IssuePriorityDataResponse, required=True))


class IssueTrackerResponse(CommonBasicResponse):
    data = fields.List(fields.Nested(IssueTrackerDataResponse, required=True))


class DashboardIssuePriorityResponse(CommonBasicResponse):
    data = fields.List(fields.Nested(BasicDashboardIssueDataResponse, required=True))


class DashboardIssueProjectResponse(CommonBasicResponse):
    data = fields.List(fields.Nested(BasicDashboardIssueDataResponse, required=True))


class DashboardIssueTypeResponse(CommonBasicResponse):
    data = fields.List(fields.Nested(BasicDashboardIssueDataResponse, required=True))


class GetFlowTypeResponse(CommonBasicResponse):
    data = fields.List(fields.Nested(GetFlowTypeDataResponse, required=True))


class DateTimeStatusGetRes(CommonBasicResponse):
    data = fields.Dict(
        example={
            "expire_num": 1,
            "no_due_date_num": 36,
            "normal_num": 0,
            "total_num": 37,
        }
    )


###### TraceOrder ######

#################################### Schema ####################################


class TraceOrdersSchema(Schema):
    project_id = fields.Int(example=1, required=True)


class TraceOrdersPostSchema(Schema):
    name = fields.Str(example="name", required=True)
    project_id = fields.Int(example=1, required=True)
    order = fields.List(fields.Str(), required=True)
    default = fields.Bool(example=True, required=True)


class TraceOrdersPutSchema(Schema):
    name = fields.Str(example="name")
    project_id = fields.Int(example=1)
    order = fields.List(fields.Str())
    default = fields.Bool(example=True)


#################################### Response ####################################

########## Module ##########


class TraceOrdersGetData(BasicIsssueResponse):
    order = fields.List(fields.Str(), example=["Epic", "Feature", "Test Plan"])
    default = fields.Bool(example=True)


class GetTraceResultData(Schema):
    project_id = fields.Int()
    total_num = fields.Int()
    current_num = fields.Int()
    result = fields.List(
        fields.Dict(
            example={
                "Epic": {
                    "id": 1,
                    "name": "name",
                    "tracker": "Epic",
                    "status": {"id": 1, "name": "Active"},
                }
            }
        )
    )
    start_time = fields.Str(example="1970-01-01 00:00:00.000000")
    finish_time = fields.Str(example="1970-01-01 00:00:00.000000")
    exception = fields.Str(default=None)


########## API action ##########


class TraceOrdersGetResponse(CommonBasicResponse):
    data = fields.List(fields.Nested(TraceOrdersGetData))


class TraceOrdersPostResponse(CommonBasicResponse):
    data = fields.Dict(example={"trace_order": 1})


class GetTraceResultResponse(CommonBasicResponse):
    data = fields.Nested(GetTraceResultData)


class GitlabGetProjectBranchesRes(CommonBasicResponse):
    data = fields.Dict(
        example={
            "branch_list": [
                {
                    "name": "allow-nothing",
                    "last_commit_message": "UI 編輯 .rancher-pipeline.yaml 啟用 checkmarx.",
                    "last_commit_time": "2022-11-14T03:37:36.000+00:00",
                    "short_id": "6191154",
                    "id": "6191154fb259a711e3b2172ceb8eb6a230bbb515",
                    "commit_url": "http://gitlab-dev.iiidevops.org/root/ui-create-case/-/commit/6191154f",
                },
                {
                    "name": "master",
                    "last_commit_message": "UI 編輯 .rancher-pipeline.yaml 啟用 checkmarx.",
                    "last_commit_time": "2022-11-14T03:37:39.000+00:00",
                    "short_id": "7297500",
                    "id": "7297500ee16248e9d837e11046f80418a893ef7d",
                    "commit_url": "http://gitlab-dev.iiidevops.org/root/ui-create-case/-/commit/7297500e",
                },
            ]
        }
    )


class GitlabPostProjectBranchesRes(CommonBasicResponse):
    data = fields.Dict(
        example={
            "name": "postman_test",
            "commit": {
                "id": "9f5bc8fcf41cba25be0e27b4aa0c0759119aeba5",
                "short_id": "9f5bc8fc",
                "created_at": "2020-10-21T07:25:18.000+00:00",
                "parent_ids": ["7c53e711f281a2d30323d452f6f559f15b69f464"],
                "title": "add .rancher-pipeline.yml",
                "message": "add .rancher-pipeline.yml",
                "author_name": "admin",
                "author_email": "admin@example.com",
                "authored_date": "2020-10-21T07:25:18.000+00:00",
                "committer_name": "Administrator",
                "committer_email": "admin@example.com",
                "committed_date": "2020-10-21T07:25:18.000+00:00",
                "web_url": "http://10.50.1.53/root/newtest/-/commit/9f5bc8fcf41cba25be0e27b4aa0c0759119aeba5",
            },
            "merged": False,
            "protected": False,
            "developers_can_push": False,
            "developers_can_merge": False,
            "can_push": True,
            "default": False,
        }
    )


class GitlabGetProjectBranchRes(CommonBasicResponse):
    data = fields.Dict(
        example={
            "name": "master",
            "commit": {
                "id": "7297500ee16248e9d837e11046f80418a893ef7d",
                "short_id": "7297500e",
                "created_at": "2022-11-14T03:37:39.000+00:00",
                "parent_ids": ["1037ecf258c27ca7a2583c5b458dbed2e53f8252"],
                "title": "UI 編輯 .rancher-pipeline.yaml 啟用 checkmarx.",
                "message": "UI 編輯 .rancher-pipeline.yaml 啟用 checkmarx.",
                "author_name": "iiidevops",
                "author_email": "system@iiidevops.org.tw",
                "authored_date": "2022-11-14T03:37:39.000+00:00",
                "committer_name": "Administrator",
                "committer_email": "admin@example.com",
                "committed_date": "2022-11-14T03:37:39.000+00:00",
                "web_url": "http://gitlab-dev.iiidevops.org/root/ui-create-case/-/commit/7297500ee16248e9d837e11046f80418a893ef7d",
            },
            "merged": False,
            "protected": True,
            "developers_can_push": True,
            "developers_can_merge": True,
            "can_push": True,
            "default": True,
        }
    )


class GitGetProjectRepositoriesRes(CommonBasicResponse):
    data = fields.Dict(
        example={
            "file_list": [
                {
                    "id": "c2ec416b4b0031972b933ac8e39597d8318d84ae",
                    "name": ".rancher-pipeline.yml",
                    "type": "blob",
                    "path": ".rancher-pipeline.yml",
                    "mode": "100644",
                },
                {
                    "id": "e69de29bb2d1d6434b8b29ae775ad8c2e48c5391",
                    "name": "file0721",
                    "type": "blob",
                    "path": "file0721",
                    "mode": "100644",
                },
                {
                    "id": "d5ca058c35040faa0ec459ffe82d21a6e0e3450b",
                    "name": "file0730",
                    "type": "blob",
                    "path": "file0730",
                    "mode": "100644",
                },
            ]
        }
    )


class GitGetBranchCommitsRes(CommonBasicResponse):
    data = fields.List(
        fields.Dict(
            example={
                "id": "fb27d44348487405a2dfe475a627e2c351f5d4ca",
                "short_id": "fb27d443",
                "created_at": "2020-10-21T08:19:57.000+00:00",
                "parent_ids": ["0df211b34886fbf99d85f19b926aa8cc9dab2cd6"],
                "title": "update file0721",
                "message": "update file0721",
                "author_name": "randy",
                "author_email": "randy@iii.org.tw",
                "authored_date": "2020-10-21T08:19:57.000+00:00",
                "committer_name": "Administrator",
                "committer_email": "admin@example.com",
                "committed_date": "2020-10-21T08:19:57.000+00:00",
                "web_url": "http://10.50.1.53/root/ro-test/-/commit/fb27d44348487405a2dfe475a627e2c351f5d4ca",
            }
        )
    )


class GitGetMembersCommitsRes(CommonBasicResponse):
    data = fields.List(
        fields.Dict(
            example={
                "id": "0222c58ee5c9a321f540b85815a8161d21b0d2bc",
                "short_id": "0222c58e",
                "created_at": "2021-09-10T07:55:10.000+00:00",
                "parent_ids": ["43e6cab822a323654e841e6219d3bc13a312d800"],
                "title": "Update .rancher-pipeline.yml",
                "message": "Update .rancher-pipeline.yml",
                "author_name": "李毅山(John)",
                "author_email": "john19968010@gmail.com",
                "authored_date": "2021-09-10T07:55:10.000+00:00",
                "committer_name": "李毅山(John)",
                "committer_email": "john19968010@gmail.com",
                "committed_date": "2021-09-10T07:55:10.000+00:00",
                "web_url": "http://gitlab-dev3.iiidevops.org/root/johntestspring/-/commit/0222c58ee5c9a321f540b85815a8161d21b0d2bc",
            }
        )
    )


class GitGetRepositoriesOverviewRes(CommonBasicResponse):
    data = fields.List(
        fields.Dict(
            example={
                "id": "44c9589322513a7620dbe8e490b6c5f816e6efaa",
                "title": "UI 編輯 .rancher-pipeline.yaml 停用 ad.",
                "message": "UI 編輯 .rancher-pipeline.yaml 停用 ad.",
                "author_name": "Administrator",
                "committed_date": "2021-12-08T01:48:22.000+00:00",
                "parent_ids": ["e69d3beb38681f425fd86c43b43d21569e6be907"],
                "branch_name": "test-merge",
                "tags": [],
            }
        )
    )


class GitGetProjectIdRes(CommonBasicResponse):
    data = fields.Int(example=1)


class GitGetProjectIdFromURIRes(CommonBasicResponse):
    data = fields.Dict(example={"project_id": 166, "repository_id": 461})


class GitGetProjectURLFromIdRes(CommonBasicResponse):
    data = fields.Dict(example={"http_url": "http://gitlab-dev.iiidevops.org/root/ui-create-case.git"})


class GitGetDomainStatusRes(CommonBasicResponse):
    data = fields.Dict(example={"status": True})


class GitGetSingleCommitRes(CommonBasicResponse):
    data = fields.Dict(
        example={
            "id": "477aa2afb38d563c5574eeea9180078ff8718ca1",
            "short_id": "477aa2af",
            "created_at": "2022-06-14T05:40:09.000+00:00",
            "parent_ids": ["fdb0e1c9453ef9973b9b7acec3970329b65c79b8"],
            "title": "UI 編輯 .rancher-pipeline.yaml 停用 zap.",
            "message": "UI 編輯 .rancher-pipeline.yaml 停用 zap.",
            "author_name": "iiidevops",
            "author_email": "system@iiidevops.org.tw",
            "authored_date": "2022-06-14T05:40:09.000+00:00",
            "committer_name": "Administrator",
            "committer_email": "admin@example.com",
            "committed_date": "2022-06-14T05:40:09.000+00:00",
            "web_url": "http://gitlab-dev.iiidevops.org/root/ui-create-case/-/commit/477aa2afb38d563c5574eeea9180078ff8718ca1",
            "stats": {"additions": 1, "deletions": 4, "total": 5},
            "status": None,
            "project_id": 30,
            "last_pipeline": None,
        }
    )


class GitGetProjectTagRes(CommonBasicResponse):
    data = fields.Dict(
        example={
            "tag_list": [
                {
                    "name": "V1.1",
                    "message": "",
                    "target": "113e530fb3ed5b9a608ba0ded97516d86da91d96",
                    "commit": {
                        "id": "113e530fb3ed5b9a608ba0ded97516d86da91d96",
                        "short_id": "113e530f",
                        "created_at": "2021-12-20T11:48:07.000+08:00",
                        "parent_ids": ["f6b60172212413c5969cee08ea3b81d92e36cffd"],
                        "title": "Test Case",
                        "message": "Test Case\n",
                        "author_name": "wyuchi99",
                        "author_email": "wyuchi99@gmail.com",
                        "authored_date": "2021-12-20T11:48:07.000+08:00",
                        "committer_name": "wyuchi99",
                        "committer_email": "wyuchi99@gmail.com",
                        "committed_date": "2021-12-20T11:48:07.000+08:00",
                        "web_url": "http://gitlab-dev.iiidevops.org/root/ui-create-case/-/commit/113e530fb3ed5b9a608ba0ded97516d86da91d96",
                    },
                    "release": {"tag_name": "V1.1", "description": None},
                    "protected": False,
                }
            ]
        }
    )


class GitPostProjectTagRes(CommonBasicResponse):
    data = fields.Dict(
        example={
            "name": "v1.0.4",
            "message": "add v1.0.4",
            "target": "8a3f8685aaa96f068622c6ed9b1de5d3cf460a9a",
            "commit": {
                "id": "5f28953344b83cfcdc2a1bcd7d59e385e9c505b2",
                "short_id": "5f289533",
                "created_at": "2020-10-14T10:40:31.000+08:00",
                "parent_ids": ["be8a7f2b5cea109c0fbe1d6396e2dd823371b9d2"],
                "title": "change path",
                "message": "change path\n",
                "author_name": "Romulus Urakagi Tsai",
                "author_email": "urakagi@gmail.com",
                "authored_date": "2020-10-14T10:40:31.000+08:00",
                "committer_name": "Romulus Urakagi Tsai",
                "committer_email": "urakagi@gmail.com",
                "committed_date": "2020-10-14T10:40:31.000+08:00",
                "web_url": "http://10.50.1.53/root/ro-test/-/commit/5f28953344b83cfcdc2a1bcd7d59e385e9c505b2",
            },
            "release": None,
            "protected": False,
        }
    )
