from marshmallow import Schema, fields
from util import CommonBasicResponse
import re
from urls.route_model import (
    BasicIsssueResponse,
    SingleIssueGetDataAuthorResponse,
    ProjectExtraResponse,
    RelationsResponse,
    PaginationPageResponse,
    CommonIssueSchema,
)

### Project Relation

#################################### Schema ####################################

########## API Action ##########


class GetProjectFamilymembersByUserDataSchema(Schema):
    id = fields.Int(required=True)
    name = fields.Str(required=True)
    role_id = fields.Int(required=True)
    role_name = fields.Str(required=True)


class ProjectRelationDeleteSchema(Schema):
    parent_id = fields.Int(required=True, example=1)


#################################### Response ####################################

########## Module ##########


class GetProjectFamilymembersByUserDataSchema(Schema):
    id = fields.Int(required=True)
    name = fields.Str(required=True)
    role_id = fields.Int(required=True)
    role_name = fields.Str(required=True)


class ProjectRelationGetData(Schema):
    parent = fields.Dict(example={"id": 1, "name": "name"})
    child = fields.List(fields.Dict(example={"id": 1, "name": "name"}))


class ProjectRelationsGetData(Schema):
    id = fields.Int(required=True)
    name = fields.Str(required=True)
    display = fields.Str(required=True)
    type = fields.Str(required=True)


########## API Action ##########


class CheckRelationProjectResponse(Schema):
    has_relations = fields.Bool(required=True)
    has_father = fields.Bool(required=True)
    has_child = fields.Bool(required=True)


class CheckhasSonProjectResponse(Schema):
    has_child = fields.Bool(required=True)


class GetProjectRootIDResponse(Schema):
    root_project_id = fields.Int(required=True)


class GetProjectFamilymembersByUserResponse(CommonBasicResponse):
    data = fields.List(fields.Nested(GetProjectFamilymembersByUserDataSchema, required=True))


class ProjectRelationGetResponse(CommonBasicResponse):
    data = fields.List(fields.Nested(ProjectRelationGetData, required=True))


class ProjectRelationsGetResponse(CommonBasicResponse):
    data = fields.List(fields.Nested(ProjectRelationsGetData, required=True))


### Project issue_list

#################################### Schema ####################################

########## API Action ##########


class IssueByProjectSchema(CommonIssueSchema):
    parent_id = fields.Str(doc="parent_id", example="1")
    due_date_start = fields.Str(doc="due_date_start", example="1970-01-01")
    due_date_end = fields.Str(doc="due_date_end", example="1970-01-01")
    with_point = fields.Str(doc="with_point", example=True)
    tags = fields.Str(doc="tags", example="1,2,3")


class IssuesProgressByProjectSchema(Schema):
    fixed_version_id = fields.Int(doc="fixed_version_id", example=-1)
    due_date_status = fields.Str(doc="due_date_status", example="expire")


#################################### Response ####################################

########## Module ##########


class PaginationResponse(Schema):
    page = fields.Nested(PaginationPageResponse, required=True)


class IssueTagResponse(Schema):
    tags = fields.List(fields.Nested(BasicIsssueResponse, required=True, default=[]))


class BasicParentResponse(BasicIsssueResponse):
    status = fields.Nested(BasicIsssueResponse, default={})
    tracker = fields.Nested(BasicIsssueResponse, default={})
    assigned_to = fields.Nested(SingleIssueGetDataAuthorResponse, default={})


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


class IssueByProjectDataResponse(CommonSingleIssueResponse, IssueTagResponse):
    estimated_hours = fields.Float(required=True)
    created_date = fields.Str(required=True, example="1970-01-01T00:00:00")
    point = fields.Int(required=True)
    relations = fields.List(fields.Nested(RelationsResponse, required=True))
    project = fields.Nested(ProjectExtraResponse, required=True)
    is_private = fields.Bool(required=True)
    updated_on = fields.Str(required=True, example="1970-01-01T00:00:00")
    closed_on = fields.Str(required=True, example="1970-01-01T00:00:00", default=None)
    family = fields.Bool(required=True)
    has_children = fields.Bool(required=True)


class IssueByProjectDataWithPageResponse(PaginationResponse):
    issue_list = fields.Nested(IssueByProjectDataResponse, required=True)


class IssueByTreeByProjectDataResponse(CommonSingleIssueResponse, IssueTagResponse):
    project = fields.Nested(ProjectExtraResponse, required=True)
    updated_on = fields.Str(required=True, example="1970-01-01T00:00:00")
    has_children = fields.Bool(required=True)
    parent = fields.Dict()
    children = fields.List(fields.Dict(), default=[])


class IssueByStatusByProjectDataContentResponse(CommonSingleIssueResponse):
    updated_on = fields.Str(required=True, example="1970-01-01T00:00:00")
    parent = fields.Nested(BasicParentResponse, default=None)
    relations = fields.List(fields.Dict(), default=[])


class IssueByStatusByProjectDataResponse(Schema):
    Assigned = fields.List(fields.Nested(IssueByStatusByProjectDataContentResponse))
    Active = fields.List(fields.Nested(IssueByStatusByProjectDataContentResponse))
    Verified = fields.List(fields.Nested(IssueByStatusByProjectDataContentResponse))
    InProgress = fields.List(fields.Nested(IssueByStatusByProjectDataContentResponse))
    Closed = fields.List(fields.Nested(IssueByStatusByProjectDataContentResponse))
    Solved = fields.List(fields.Nested(IssueByStatusByProjectDataContentResponse))


class IssuesProgressByProjectDataResponse(Schema):
    Assigned = fields.Int()
    Active = fields.Int()
    Verified = fields.Int()
    InProgress = fields.Int()
    Closed = fields.Int()
    Solved = fields.Int()


########## API Action ##########


class IssueByProjectResponseWithPage(CommonBasicResponse):
    data = fields.Raw(
        example={
            "issue_list": [
                {
                    "assigned_to": {"id": 1, "login": "login", "name": "name"},
                    "author": {"id": 1, "name": "author"},
                    "closed_on": None,
                    "description": None,
                    "done_ratio": 0,
                    "due_date": None,
                    "estimated_hours": None,
                    "family": True,
                    "fixed_version": {"id": 1, "name": "name"},
                    "has_children": True,
                    "has_father": True,
                    "id": 1,
                    "is_closed": False,
                    "is_private": False,
                    "issue_link": "http://",
                    "name": "name",
                    "priority": {"id": 3, "name": "Normal"},
                    "project": {"display": "display", "id": 176, "name": "name"},
                    "start_date": "1970-01-01",
                    "status": {"id": 4, "name": "Solved"},
                    "tags": [],
                    "tracker": {"id": 6, "name": "Change Request"},
                    "updated_on": "2022-03-23T07:36:42",
                }
            ],
            "page": {
                "current": 1,
                "limit": 5,
                "next": 2,
                "offset": 0,
                "pages": 2,
                "prev": None,
                "total": 10,
            },
        },
        required=True,
    )


class IssueByProjectResponse(CommonBasicResponse):
    data = fields.Raw(
        example=[
            {
                "assigned_to": {"id": 1, "login": "login", "name": "name"},
                "author": {"id": 1, "name": "author"},
                "closed_on": None,
                "description": None,
                "done_ratio": 0,
                "due_date": None,
                "estimated_hours": None,
                "family": True,
                "fixed_version": {"id": 1, "name": "name"},
                "has_children": True,
                "has_father": True,
                "id": 1,
                "is_closed": False,
                "is_private": False,
                "issue_link": "http://",
                "name": "name",
                "priority": {"id": 3, "name": "Normal"},
                "project": {"display": "display", "id": 176, "name": "name"},
                "start_date": "1970-01-01",
                "status": {"id": 4, "name": "Solved"},
                "tags": [],
                "tracker": {"id": 6, "name": "Change Request"},
                "updated_on": "2022-03-23T07:36:42",
            }
        ],
        required=True,
    )


class IssueByTreeByProjectResponse(CommonBasicResponse):
    data = fields.List(fields.Nested(IssueByTreeByProjectDataResponse, required=True))


class IssueByStatusByProjectResponse(CommonBasicResponse):
    data = fields.Nested(IssueByStatusByProjectDataResponse, required=True)


class IssuesProgressByProjectResponse(CommonBasicResponse):
    data = fields.Nested(IssuesProgressByProjectDataResponse, required=True)


class IssuesStatisticsByProjectResponse(CommonBasicResponse):
    """hard to implement
    "data": {
        "assigned_to": {
            "李毅山(John)": {
                "Active": 0,
                "Assigned": 1,
                "InProgress": 1,
                "Solved": 0,
                "Verified": 1,
                "Closed": 1
            },
        }
    }
    """

    data = fields.Dict()


##### Filter issue by project ######

#################################### Schema ####################################
class IssueFilterByProjectPostAndPutSchema(Schema):
    name = fields.Str(doc="name", example="程式碼檢查", required=True)
    type = fields.Str(doc="type", example="測試計畫", required=True)
    assigned_to_id = fields.Str(doc="assigned_to_id", example="1", allow_none=True)
    fixed_version_id = fields.Str(doc="fixed_version_id", example="1", allow_none=True)
    focus_tab = fields.Str(doc="focus_tab", example="string", allow_none=True)
    group_by = fields.Dict(
        doc="group_by",
        example={
            "dimension": "status",
            "value": [{"id": 1, "name": "Active", "is_closed": False}],
        },
        allow_none=True,
    )
    priority_id = fields.Str(doc="priority_id", example="1", allow_none=True)
    show_closed_issues = fields.Bool(doc="show_closed_issues", example=True, allow_none=True)
    show_closed_versions = fields.Bool(doc="show_closed_versions", example=True, allow_none=True)
    status_id = fields.Str(doc="status_id", example="1", allow_none=True)
    tags = fields.Str(doc="tags", example="1,2,3", allow_none=True)
    tracker_id = fields.Str(doc="tracker_id", example="1", allow_none=True)


#################################### Response ####################################

########## Module ##########


class IssueFilterByProjectDataResponse(BasicIsssueResponse):
    user_id = fields.Int(required=True)
    project_id = fields.Int(required=True)
    type = fields.Str(required=True)
    custom_filter = fields.Dict(required=True)


class IssueFilterByProjectPostDataResponse(Schema):
    custom_filter_id = fields.Int(required=True)


########## API Action ##########


class IssueFilterByProjectGetResponse(CommonBasicResponse):
    data = fields.List(fields.Nested(IssueFilterByProjectDataResponse, required=True))


class IssueFilterByProjectPostResponse(CommonBasicResponse):
    data = fields.Nested(IssueFilterByProjectPostDataResponse, required=True)


class IssueFilterByProjectPutResponse(CommonBasicResponse):
    data = fields.Nested(IssueFilterByProjectDataResponse, required=True)


##### # Download project's issue as excel ######

#################################### Schema ####################################


class DownloadProjectSchema(Schema):
    fixed_version_id = fields.Str(doc="fixed_version_id", example="1")
    status_id = fields.Str(doc="status_id", example="1")
    tracker_id = fields.Str(doc="tracker_id", example="1")
    assigned_to_id = fields.Str(doc="assigned_to_id", example="1")
    priority_id = fields.Str(doc="fixed_version_id", example="1")
    only_superproject_issues = fields.Bool(doc="only_superproject_issues", example=True, load_default=False)
    search = fields.Str(doc="search", example="string")
    selection = fields.Str(doc="selection", example="1")
    sort = fields.Str(doc="sort", example="string")
    parent_id = fields.Str(doc="parent_id", example="1")
    due_date_start = fields.Str(doc="due_date_start", example="1970-01-01")
    due_date_end = fields.Str(doc="due_date_end", example="1970-01-01")
    with_point = fields.Str(doc="with_point", example=True, load_default=True)
    tags = fields.Str(doc="tags", example="1,2,3")
    levels = fields.Int(doc="levels", example=1, load_default=3)
    deploy_column = fields.List(
        fields.Dict(example={"field": "name", "display": "議題名稱"}),
        doc="deploy_column",
        required=True,
    )


#################################### Response ####################################

########## Module ##########


class DownloadProjectIsExistDataResponse(Schema):
    file_exist = fields.Bool(required=True)
    create_at = fields.Str(required=True, example="1970-01-01T00:00:00")


########## API Action ##########


class DownloadProjectIsExistResponse(CommonBasicResponse):
    data = fields.Nested(DownloadProjectIsExistDataResponse, required=True)


##### List projects ######

#################################### Schema ####################################

########## API Action ##########


class ListMyProjectsSchema(Schema):
    simple = fields.Str(doc="simple", example="true")
    limit = fields.Int(doc="limit", example=1)
    offset = fields.Int(doc="offset", example=1)
    search = fields.Str(doc="search", example="string")
    accsearch = fields.Str(doc="search", example="string")
    disabled = fields.Int(doc="disabled", example="1")
    test_result = fields.Str(doc="test_result", example="true")
    pj_members_count = fields.Str(doc="pj_members_count", example="true")
    pj_due_date_start = fields.Str(doc="pj_due_date_start", example="1970-01-01")
    pj_due_date_end = fields.Str(doc="pj_due_date_end", example="1970-01-01")


class CalculateProjectIssuesSchema(Schema):
    project_ids = fields.Str(doc="project_ids", example="1,2,3,4", required=True)


#################################### Response ####################################

########## Module ##########


class ProjectsBasicResponse(BasicIsssueResponse):
    alert = fields.Bool(required=True)
    create_at = fields.Str(required=True, example="1970-01-01 00:00:00.000000", default=None)
    creator_id = fields.Int(required=True)
    description = fields.Str(required=True, default=None)
    disabled = fields.Bool(required=True, default=None)
    display = fields.Str(required=True)
    due_date = fields.Str(required=True, example="1970-01-01", default=None)
    is_lock = fields.Bool(required=True)
    lock_reason = fields.Str(required=True, default=None)
    owner_id = fields.Int(required=True)
    # projects = fields.List()
    ssh_url = fields.Str(required=True)
    start_date = fields.Str(required=True, example="1970-01-01", default=None)
    # trace_order = fields.List()
    update_at = fields.Str(required=True, example="1970-01-01 00:00:00.000000", default=None)
    git_url = fields.Str(required=True, example="http://gitlab-dev.iiidevops123.org/root/")
    repository_ids = fields.List(fields.Int())
    redmine_url = fields.Str(required=True, example="http://redmine-dev3.iiidevops123.org/")
    # harbor_url = fields.Str(required=True, example="https://harbor-dev3.iiidevops234.org/harbor/")
    owner_name = fields.Str(required=True, example="初始管理者")
    department = fields.Str(required=True, example="數位轉型院所")
    is_empty_project = fields.Bool()


class ListMyProjectsDataProjectListResponse(ProjectsBasicResponse):
    starred = fields.Bool()
    last_test_time = fields.Str()
    last_test_result = fields.Dict(example={"total": 12, "success": 12})
    members = fields.Int()
    has_son = fields.Bool()
    parent_id = fields.Int(default=None)
    is_inheritance_member = fields.Bool()


class CalculateProjectIssuesListResponse(Schema):
    id = fields.Str(required=True)
    closed_count = fields.Int()
    overdue_count = fields.Int()
    total_count = fields.Int()
    project_status = fields.Str()
    updated_time = fields.Str(example="1970-01-01 00:00:00", default=None)
    issues = fields.Int()
    next_d_time = fields.Str(default=None)


class ListMyProjectsProjectListResponse(PaginationResponse):
    project_list = fields.List(fields.Nested(ListMyProjectsDataProjectListResponse), required=True)


class ListMyProjectsDataResponse(Schema):
    project_list = fields.Nested(ListMyProjectsProjectListResponse, required=True)


class CalculateProjectIssuesDataResponse(Schema):
    project_list = fields.List(fields.Nested(CalculateProjectIssuesListResponse), required=True)


########## API Action ##########


class ListMyProjectsResponse(CommonBasicResponse):
    data = fields.Nested(ListMyProjectsDataResponse, required=True)


class CalculateProjectIssuesResponse(CommonBasicResponse):
    data = fields.Nested(CalculateProjectIssuesDataResponse, required=True)


class ListMyProjectsByUserResponse(CommonBasicResponse):
    data = fields.List(fields.Nested(ListMyProjectsDataProjectListResponse), required=True)


##### Single project ######

#################################### Schema ####################################


class SingleProjectPutSchema(Schema):
    display = fields.Str(doc="display", example="議題測試專案", required=True)
    description = fields.Str(doc="description", example="此為測試專案")
    disabled = fields.Bool(doc="disabled", example=True, required=True)
    start_date = fields.Str(doc="start_date", example="1970-01-01", required=True)
    due_date = fields.Str(doc="due_date", example="1970-01-01", required=True)
    owner_id = fields.Int(doc="owner_id", example=1, required=True)
    parent_id = fields.Str(doc="parent_id", example="1")
    is_inheritance_member = fields.Bool(doc="is_inheritance_member", example=True)
    template_id = fields.Int(doc="template_id", example=1)
    tag_name = fields.Str(doc="tag_name", example="子專案")
    arguments = fields.Str(doc="arguments", example="string")


class SingleProjectPatchSchema(Schema):
    owner_id = fields.Int(doc="owner_id", example=1, required=True)


class SingleProjectPostSchema(SingleProjectPutSchema):
    name = fields.Str(doc="name", example="API開發專案", required=True)
    display = fields.Str(doc="display", example="議題測試專案")
    template_id = fields.Int(doc="template_id", example=1)
    tag_name = fields.Str(doc="tag_name", example="子專案")
    arguments = fields.Str(doc="arguments", example="string")
    owner_id = fields.Int(doc="owner_id", example=1)


#################################### Response ####################################

########## Module ##########


class SingleProjectDataGetResponse(ProjectsBasicResponse):
    pass


class SingleProjectDataPostResponse(Schema):
    project_id = fields.Int(required=True)
    plan_project_id = fields.Int(required=True)
    git_repository_id = fields.Int(required=True)
    # harbor_project_id = fields.Int(required=True)


########## API Action ##########


class SingleProjectGetResponse(CommonBasicResponse):
    data = fields.Nested(SingleProjectDataGetResponse, required=True)


class SingleProjectPostResponse(CommonBasicResponse):
    data = fields.Nested(SingleProjectDataPostResponse, required=True)


class SingleProjectByNameResponse(CommonBasicResponse):
    data = fields.Nested(ProjectsBasicResponse, required=True)


##### Project member ######

#################################### Schema ####################################


class SingleProjectMemberPutSchema(Schema):
    user_id = fields.Int(doc="user_id", example=1, required=True)


class ProjectUserListSchema(Schema):
    exclude = fields.Int(doc="exclude", example=1)


#################################### Response ####################################

########## Module ##########


class ProjectUserLists(BasicIsssueResponse):
    create_at = fields.Str(example="1970-01-01 00:00:00.000000", default=None)
    department = fields.Str(example="數位轉型院所")
    status = fields.Str(example="enable")
    email = fields.Str(example="rd@vapor.nowhere")
    from_ad = fields.Bool(example=True)
    login = fields.Str(example="postman_test_rd")
    phone = fields.Str()
    title = fields.Str(example="專案經理")
    update_at = fields.Str(example="1970-01-01 00:00:00.000000", default=None)
    default_role = fields.Dict()
    role_id = fields.Int(example=1)
    role_name = fields.Str(example="PM")


class ProjectUserListData(Schema):
    user_list = fields.List(fields.Nested(ProjectUserLists), required=True)


########## API Action ##########
class ProjectUserListResponse(Schema):
    data = fields.Nested(ProjectUserListData, required=True)


##### Project report ######

#################################### Schema ####################################


class ProjectFilePostSchema(Schema):
    filename = fields.Str(example="filename")
    version_id = fields.Str(example="v1.0")
    description = fields.Str(example="description")


#################################### Response ####################################

########## Module ##########


class TestSummaryDataTestResult(Schema):
    postman = fields.Dict()
    checkmarx = fields.Dict()
    webinspect = fields.Dict()
    sonarqube = fields.Dict()
    zap = fields.Dict()
    sideex = fields.Dict()
    cmas = fields.Dict()


class TestSummaryData(Schema):
    test_results = fields.Nested(TestSummaryDataTestResult, required=True)


class ProjectFileGetDataFiles(Schema):
    id = fields.Int(example=1)
    filename = fields.Str(example="filename")
    filesize = fields.Int(example=1)
    content_type = fields.Str(example="string", default=None)
    description = fields.Str(example="此為重點專案")
    content_url = fields.Str()
    thumbnail_url = fields.Str()
    author = fields.Dict()
    version = fields.Dict()
    created_on = fields.Str(example="1970-01-01 00:00:00.000000")
    digest = fields.Str()
    downloads = fields.Int(example=1)


class ProjectFileGetData(Schema):
    files = fields.List(fields.Nested(ProjectFileGetDataFiles, required=True), required=True)


########## API Action ##########
class TestSummaryResponse(CommonBasicResponse):
    data = fields.Nested(TestSummaryData, required=True)


class ProjectFileGetResponse(CommonBasicResponse):
    data = fields.Nested(ProjectFileGetData, required=True)


##### Project plugin(k8s) ######

#################################### Schema ####################################


class ProjectUserResourceSchema(Schema):
    this_one_has_issue = fields.Str(example="services.nodeports")
    # memory
    # pods
    # secrets
    # configmaps
    # services.nodeports
    # persistentvolumeclaims


class ProjectUserResourcePodLogSchema(Schema):
    container_name = fields.Str(example="sonarqube-scan-00000-00", required=True)


class ProjectPluginPodSchema(Schema):
    plugin_name = fields.Str(example="plugin_name", required=True)


#################################### Response ####################################

########## Module ##########


class ProjectPluginUsageData(Schema):
    title = fields.Str()
    used = fields.Dict(example={"value": 0, "unit": ""})
    quota = fields.Dict(example={"value": 0, "unit": ""})


class ProjectUserResourceData(Schema):
    quota = fields.Dict(
        example={
            "configmaps": "60",
            "cpu": "10",
            "memory": "10G",
            "persistentvolumeclaims": "10",
            "pods": "20",
            "services.nodeports": "10",
            "deployments": "0",
            "ingresses": "0",
            "secrets": "15",
        }
    )
    used = fields.Dict(
        example={
            "configmaps": "60",
            "cpu": "10",
            "memory": "10G",
            "persistentvolumeclaims": "10",
            "pods": "20",
            "services.nodeports": "10",
            "deployments": "0",
            "ingresses": "0",
            "secrets": "15",
        }
    )


class ProjectUserResourcePodsContainers(Schema):
    name = fields.Str()
    image = fields.Str()
    restart = fields.Integer()
    state = fields.Str()
    time = fields.Str(example="1970-01-01 00:00:00+00:00")


class ProjectUserResourcePodsData(Schema):
    name = fields.Str()
    created_time = fields.Str(example="1970-01-01 00:00:00+00:00")
    containers = fields.List(fields.Nested(ProjectUserResourcePodsContainers))


class ProjectEnvironmentGetData(Schema):
    name = fields.Str()
    branch = fields.Str()
    commit_id = fields.Str()
    commit_url = fields.Str()
    pods = fields.List(
        fields.Dict(
            example={
                "app_name": "john-son1-master-db",
                "pod_name": "john-son1-master-db-dpy-b76c7495-frqqc",
                "type": "db-server",
                "containers": [
                    {
                        "name": "postgresql",
                        "image": "bitnami/postgresql:11-debian-10",
                        "status": {
                            "state": "running",
                            "time": "2022-03-02 04:17:01+00:00",
                            "restart": 0,
                            "image": "bitnami/postgresql:11-debian-10",
                            "name": "postgresql",
                            "ready": True,
                        },
                        "service_port_mapping": [
                            {
                                "container_port": 5432,
                                "name": "db",
                                "protocol": "TCP",
                                "services": [
                                    {
                                        "port_name": "db",
                                        "target_port": 5432,
                                        "port": 5432,
                                        "url": ["10.20.0.93:30533"],
                                        "name": "john-son1-master-db-svc",
                                        "service_type": "db-server",
                                    }
                                ],
                            }
                        ],
                    }
                ],
            }
        )
    )


class ProjectPluginPodData(Schema):
    has_pod = fields.Bool(example=True, required=True)
    container_name = fields.Str()
    pod_name = fields.Str()
    time = fields.Str(example="1970-01-01 00:00:00+00:00")


########## API Action ##########


class ProjectPluginUsageResponse(CommonBasicResponse):
    data = fields.List(fields.Nested(ProjectPluginUsageData, required=True), required=True)


class ProjectUserResourceResponse(CommonBasicResponse):
    data = fields.Nested(ProjectUserResourceData, required=True)


class ProjectUserResourcePodsResponse(CommonBasicResponse):
    data = fields.List(fields.Nested(ProjectUserResourcePodsData, required=True), required=True)


class ProjectUserResourcePodResponse(CommonBasicResponse):
    data = fields.Str()


class ProjectEnvironmentGetResponse(CommonBasicResponse):
    data = fields.List(fields.Nested(ProjectEnvironmentGetData), required=True)


class ProjectEnvironmentPutResponse(CommonBasicResponse):
    data = fields.List(fields.Dict())


class ProjectEnvironmentDeleteResponse(CommonBasicResponse):
    data = fields.List(fields.Str())


class ProjectEnvironmentUrlResponse(CommonBasicResponse):
    data = fields.List(fields.Str())


class ProjectPluginPodResponse(CommonBasicResponse):
    data = fields.Nested(ProjectPluginPodData, required=True)


##### k8s info ######

#################################### Schema ####################################


class ProjectUserResourceSecretSchema(Schema):
    secrets = fields.Dict(required=True)


class ProjectUserResourceConfigMapsSchema(Schema):
    configmaps = fields.Dict(required=True)


#################################### Response ####################################

########## Module ##########


class ProjectUserResourceDeploymentsContainer(Schema):
    image = fields.Str()
    name = fields.Str()


class ProjectUserResourceDeploymentsData(Schema):
    name = fields.Str()
    available_pod_number = fields.Integer()
    available_pod_number = fields.Integer()
    created_time = fields.Str(example="1970-01-01 00:00:00+00:00")
    containers = fields.List(fields.Nested(ProjectUserResourceDeploymentsContainer))


class ProjectUserResourceServicesData(Schema):
    name = fields.Str()
    is_iii = fields.Bool()


class ProjectUserResourceSecretsData(ProjectUserResourceServicesData):
    data = fields.Dict()


class ProjectUserResourceConfigMapsData(ProjectUserResourceSecretsData):
    pass


class ProjectUserResourceIngressesData(Schema):
    name = fields.Str()
    created_time = fields.Str(example="1970-01-01 00:00:00+00:00")
    ingress_list = fields.List(
        fields.Dict(
            example={
                "hostname_path": "10.20.0.01.xip.io/service",
                "service": "service-domain:5000",
            }
        )
    )
    tls = fields.Str(default=None)


########## API Action ##########


class ProjectUserResourceDeploymentsResponse(CommonBasicResponse):
    data = fields.List(fields.Nested(ProjectUserResourceDeploymentsData), required=True)


class ProjectUserResourceDeploymentResponse(CommonBasicResponse):
    data = fields.Str()


class ProjectUserResourceServicesResponse(CommonBasicResponse):
    data = fields.List(fields.Nested(ProjectUserResourceServicesData))


class ProjectUserResourceServiceDeleteResponse(CommonBasicResponse):
    data = fields.Str()


class ProjectUserResourceSecretsResponse(CommonBasicResponse):
    data = fields.List(fields.Nested(ProjectUserResourceSecretsData))


class ProjectUserResourceSecretGetResponse(CommonBasicResponse):
    data = fields.Dict(example={"test": "test123456"})


class ProjectUserResourceSecretDeleteResponse(CommonBasicResponse):
    data = fields.Str()


class ProjectUserResourceConfigMapsResponse(CommonBasicResponse):
    data = fields.List(fields.Nested(ProjectUserResourceConfigMapsData))


class ProjectUserResourceConfigMapResponse(CommonBasicResponse):
    data = fields.Dict()


class ProjectUserResourceConfigMapsDeleteResponse(CommonBasicResponse):
    data = fields.Str()


class ProjectUserResourceIngressesResponse(CommonBasicResponse):
    data = fields.List(fields.Nested(ProjectUserResourceIngressesData))


### Project version

#################################### Schema ####################################

########## API Action ##########


class ProjectVersionListSchema(Schema):
    status = fields.Str()
    force_id = fields.Str()


class ProjectVersionPostPutSchema(Schema):
    version = fields.Dict(
        example={
            "version": {
                "name": "V1.0",
                "description": "V1.0 version",
                "due_date": "2022-03-10",
                "status": "open",
            }
        },
        required=True,
    )


#################################### Response ####################################

########## Module ##########


class ProjectVersionListDataVersion(BasicIsssueResponse):
    project = fields.Dict()
    description = fields.Str(example="V1.0")
    status = fields.Str(example="open")
    due_date = fields.Str(example="1970-01-01")
    sharing = fields.Str(example="none")
    wiki_page_title = fields.Str(default=None)
    created_on = fields.Str(example="1970-01-01T00:00:00Z")
    updated_on = fields.Str(example="1970-01-01T00:00:00Z")


class CommonVersion(ProjectVersionListDataVersion):
    estimated_hours = fields.Int(example=0)
    spent_hours = fields.Int(example=0)


class ProjectVersionListData(Schema):
    versions = fields.List(fields.Nested(ProjectVersionListDataVersion))
    total_count = fields.Int(example=0)


class ProjectVersionData(Schema):
    version = fields.Nested(CommonVersion)


########## API Action ##########


class ProjectVersionListResponse(CommonBasicResponse):
    data = fields.Nested(ProjectVersionListData, required=True)


class ProjectVersionPostResponse(CommonBasicResponse):
    data = fields.Nested(ProjectVersionData, required=True)


class ProjectVersionGetResponse(CommonBasicResponse):
    data = fields.Nested(ProjectVersionData, required=True)


### Wiki

#################################### Schema ####################################


class ProjectWikiPut(Schema):
    wiki_text = fields.Str()


#################################### Response ####################################

########## Module ##########


class ProjectWikiPages(Schema):
    title = fields.Str(example="title")
    version = fields.Int(example=1)
    created_on = fields.Str(example="1970-01-01T00:00:00Z")
    updated_on = fields.Str(example="1970-01-01T00:00:00Z")


class ProjectWikiCommon(ProjectWikiPages):
    text = fields.Str(example="text")
    author = fields.Dict()
    comments = fields.Str(default=None)


class ProjectWikiListData(Schema):
    wiki_pages = fields.List(fields.Nested(ProjectWikiPages))


class ProjectWikiGetData(Schema):
    wiki_page = fields.Nested(ProjectWikiCommon)


########## API Action ##########


class ProjectWikiListResponse(CommonBasicResponse):
    data = fields.Nested(ProjectWikiListData, required=True)


class ProjectWikiGetResponse(CommonBasicResponse):
    data = fields.Nested(ProjectWikiGetData, required=True)


##### Release ######

#################################### Schema ####################################


class ReleaseExtraGetSchema(Schema):
    branch_name = fields.Str(example="master", required=True)
    not_all = fields.Str(example="true")
    only_image = fields.Str(example="true")
    limit = fields.Int(example=10, load_default=10)
    offset = fields.Int(example=0, load_default=0)


class ReleaseTagSchema(Schema):
    tags = fields.Str(required=True)
    forced = fields.Bool()


class ReleaseRepoPostSchema(Schema):
    image_path = fields.Str(validate=lambda x: re.search("\w:\w", x) is not None, required=True)


class ReleaseRepoDeleteSchema(Schema):
    repo_name = fields.Str(required=True)


class ReleasesGetSchema(Schema):
    image = fields.Bool()


class ReleasesPostSchema(Schema):
    main = fields.Int()
    versions = fields.List(fields.Int())
    branch = fields.Str()
    commit = fields.Str()
    note = fields.Str()
    released_at = fields.Str()
    forced = fields.Bool()
    extra_image_path = fields.Str()


#################################### Response ####################################

########## Module ##########


class ReleaseExtraGetData(PaginationResponse):
    image_list = fields.List(
        fields.Dict(
            example={
                "commit_id": "202959c",
                "image": "sha256:6efc1e00",
                "push_time": "1970-01-01T00:00:00",
            }
        )
    )


class ReleasesGetData(Schema):
    releases = fields.List(
        fields.Dict(
            example={
                "branch": "master",
                "commit": "1ec85c4",
                "create_at": "1970-01-01 00:00:00.00000",
                "creator_id": 1,
                "docker": [{"default": True, "repo": "repo", "tags": ["tag1", "tag2"]}],
                "git_url": "http://giturl/project_name",
                # "harbor_external_base_url": "http://harbor_external_base_url/project_name",
                "id": 1,
                "image_tags": [
                    {"1ec85c4": ["project_name/repo-name:tag"]},
                    {"name": ["project_name/repo-name:name"]},
                ],
                "issues": [],
                "note": "",
                "project_id": 1,
                "tag_name": "name",
                "update_at": None,
                "version_id": 1,
                "versions": [1],
            }
        )
    )


########## API Action ##########


class ReleaseExtraGetResponse(CommonBasicResponse):
    data = fields.Nested(ReleaseExtraGetData, required=True)


class ReleasesGetResponse(CommonBasicResponse):
    data = fields.Nested(ReleasesGetData, required=True)


##### Issue's Force Trackers  ######

#################################### Schema ####################################


class IssueForceTrackerPatchSchema(Schema):
    need_fatherissue_trackers = fields.List(fields.Int(), required=True)


#################################### Response ####################################

########## Module ##########


class IssueForceTrackerPostData(Schema):
    enable = fields.Bool(required=True)
    need_fatherissue_trackers = fields.List(fields.Dict(example={"id": 1, "name": "Epic"}))


########## API Action ##########


class IssueForceTrackerPostResponse(CommonBasicResponse):
    data = fields.Nested(IssueForceTrackerPostData, required=True)


##### Project resource info  ######

#################################### Schema ####################################


class ProjectResourceStorageUpdateSchema(Schema):
    gitlab = fields.Dict(example={"limit": 0.8, "comparison": ">", "percentage": False})


#################################### Response ####################################

########## API Action ##########


class ProjectResourceStorageRes(CommonBasicResponse):
    data = fields.Dict(
        exmaple={
            "gitlab": {"comparison": ">", "limit": 0.9, "percentage": False},
            "project_id": 1,
        }
    )
