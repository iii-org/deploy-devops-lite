import os
import sys
import threading
import traceback
from os.path import isfile
from pathlib import Path
import re

import werkzeug
from apispec import APISpec
from apispec.ext.marshmallow import MarshmallowPlugin
from flask import Flask
from flask_apispec.extension import FlaskApiSpec
from flask_cors import CORS
from flask_jwt_extended import jwt_required
from flask_restful import Resource, Api, reqparse
from flask_socketio import SocketIO
from sqlalchemy.exc import NoResultFound
from sqlalchemy_utils import database_exists, create_database
from werkzeug.routing import IntegerConverter

if str(Path(__file__).parent) not in sys.path:
    sys.path.insert(1, str(Path(__file__).parent))

import config
import migrate
import model
import plugins
import resources.apiError as apiError
import resources.pipeline as pipeline
import routine_job
import util
from jsonwebtoken import jsonwebtoken
from model import db
from resources import logger, role as role, activity, starred_project, devops_version, cicd
from resources import (
    project,
    gitlab,
    issue,
    user,
    redmine,
    apiTest,
    template,
    release,
    sync_redmine,
    plugin,
    project_permission,
    quality,
    deploy,
    alert,
    trace_order,
    system_parameter,
    maintenance,
    issue_display_field,
)
from resources.redis import should_update_template_cache
from resources.template import fetch_and_update_template_cache

if config.get("DEBUG") is False:
    import eventlet

    eventlet.monkey_patch(socket=True, select=True, thread=True)

# This import will merge to the above one after all API move to V2.
# from urls import monitoring

# from urls.harbor import harbor_url
from urls.issue import issue_url
from urls.lock import lock_url
from urls.notification_message import notification_message_url
from urls.project import project_url
from urls.router import router_url
from urls.sync_projects import sync_projects_url
from urls.sync_users import sync_users_url
from urls.system import system_url
from urls.system_parameter import sync_system_parameter_url
from urls.tag import tag_url
from urls.template import template_url
from urls.user import user_url


app = Flask(__name__)
for key in [
    "JWT_SECRET_KEY",
    "SQLALCHEMY_DATABASE_URI",
    "SQLALCHEMY_TRACK_MODIFICATIONS",
    "WTF_CSRF_CHECK_DEFAULT",
    "JSON_AS_ASCII",
]:
    app.config[key] = config.get(key)

security_definitions = {
    "bearer": {
        "type": "apiKey",
        "in": "header",
        "name": "Authorization",
    }
}
# setting swagger config
app.config.update(
    {
        "APISPEC_SPEC": APISpec(
            title="Devops API Project",
            version="v2",
            plugins=[MarshmallowPlugin()],
            securityDefinitions=security_definitions,
            openapi_version="2.0.0",
            basePath="/prod-api",
        ),
        "APISPEC_SWAGGER_URL": "/swagger/",  # URI to access API Doc JSON
        "APISPEC_SWAGGER_UI_URL": "/swagger-ui/",  # URI to access UI of API Doc
    }
)

docs = FlaskApiSpec(app)


def add_resource(classes, level):
    if (config.get("DOCUMENT_LEVEL") == "public" and level in ["public"]) or (
        config.get("DOCUMENT_LEVEL") == "private" and level in ["public", "private"]
    ):
        docs.register(classes)


app.config["PROPAGATE_EXCEPTIONS"] = True
# app.config['SQLALCHEMY_COMMIT_ON_TEARDOWN'] = True
app.config["SQLALCHEMY_ENGINE_OPTIONS"] = {
    "pool_pre_ping": True,
    "pool_recycle": 60,
    "pool_timeout": 300,
    "pool_size": 20,
}

"""
To adjust file size, there are five different plan need to change,
K8s, Ingress, UI-nginx, Redmine-setting, Flask-setting(the code below), DB(SystmeParameter)
"""
app.config["MAX_CONTENT_LENGTH"] = 100 * 1000 * 1000

api = Api(app, errors=apiError.custom_errors)
CORS(app)

if config.get("DEBUG") is False:
    socketio = SocketIO(
        app,
        message_queue=f'redis://{config.get("REDIS_BASE_URL")}',
        cors_allowed_origins="*",
        logger=False,
        engineio_logger=False,
        timeout=60000,
    )
else:
    socketio = SocketIO(app, cors_allowed_origins="*", logger=True, engineio_logger=True, timeout=60000)


class SignedIntConverter(IntegerConverter):
    regex = r"-?\d+"


app.url_map.converters["sint"] = SignedIntConverter


@app.errorhandler(Exception)
def internal_error(exception):
    if type(exception) is NoResultFound:
        return util.respond(404, "Resource not found.", error=apiError.resource_not_found())
    if type(exception) is werkzeug.exceptions.NotFound:
        return util.respond(404, "Path not found.", error=apiError.path_not_found())
    if type(exception) is apiError.DevOpsError:
        traceback.print_exc()
        logger.logger.exception(str(exception))
        return util.respond(exception.status_code, exception.message, error=exception.error_value)
    if type(exception) is werkzeug.exceptions.UnprocessableEntity:
        mes = exception.data.get("messages", {})
        error_message = mes.get("json") or mes.get("query") or mes.get("form")
        return util.respond(422, error_message)
    traceback.print_exc()
    logger.logger.exception(str(exception))
    return util.respond(500, "Unexpected internal error", error=apiError.uncaught_exception(exception))


class NexusVersion(Resource):
    @jwt_required()
    def get(self):
        row = model.NexusVersion.query.one()
        return util.success({"api_version": row.api_version, "deploy_version": row.deploy_version})

    @jwt_required()
    def post(self):
        role.require_admin()
        keys = ["api_version", "deploy_version"]
        parser = reqparse.RequestParser()
        for k in keys:
            parser.add_argument(k, type=str)
        args = parser.parse_args()
        row = model.NexusVersion.query.one()
        for k in keys:
            if args[k] is not None:
                setattr(row, k, self._check(args[k]))
        db.session.commit()
        return util.success()

    @staticmethod
    def _check(check: str) -> str:
        error: apiError.DevOpsError = apiError.DevOpsError(400, "api_version is not valid")
        # check regex only digit and dot
        if re.match(r"^[Vv]?\d+(\.\d+)*$", check) is None:
            # Check string is only 'develop'
            if check.lower() != "develop":
                raise error

        return check


def initialize(db_uri):
    if database_exists(db_uri):
        return
    logger.logger.info("Initializing...")
    logger.logger.info(f"db_url is {db_uri}")
    if config.get("DEBUG"):
        print("Initializing...")
    # Create database
    create_database(db_uri)
    db.create_all()
    logger.logger.info("Database created.")
    # Fill alembic revision with latest
    head = None
    revs = []
    downs = []
    for fn in os.listdir("apis/alembic/versions"):
        fp = "apis/alembic/versions/%s" % fn
        if not isfile(fp):
            continue
        with open(fp, "r") as f:
            for line in f:
                if line.startswith("revision"):
                    revs.append(line.split("=")[1].strip()[1:-1])
                elif line.startswith("down_revision"):
                    downs.append(line.split("=")[1].strip()[1:-1])

    for rev in revs:
        is_head = True
        for down in downs:
            if down == rev:
                is_head = False
                break
        if is_head:
            head = rev
            break
    if head is not None:
        v = model.AlembicVersion(version_num=head)
        db.session.add(v)
        db.session.commit()
    logger.logger.info(f"Alembic revision set to ${head}")
    # Create dummy project
    new = model.Project(id=-1, name="__dummy_project")
    db.session.add(new)
    db.session.commit()
    logger.logger.info("Project -1 created.")
    # Init admin
    args = {
        "login": config.get("ADMIN_INIT_LOGIN"),
        "email": config.get("ADMIN_INIT_EMAIL"),
        "password": config.get("ADMIN_INIT_PASSWORD"),
        "phone": "00000000000",
        "name": "初始管理者",
        "role_id": role.ADMIN.id,
        "status": "enable",
    }
    user.create_user(args)
    logger.logger.info("Initial admin created.")
    migrate.init()
    my_uuid = devops_version.set_deployment_uuid()
    logger.logger.info(f"Deployment UUID set as {my_uuid}.")
    logger.logger.info("Server initialized.")


router_url(api, add_resource)

# Git
# api.add_resource(project.GitRepoIdToCiPipeId, "/git_repo_id_to_ci_pipe_id/<repository_id>")
# api.add_resource(project.GitRepoIdToCiPipeIdV2, "/v2/git_repo_id_to_ci_pipe_id/<repository_id>")
# add_resource(project.GitRepoIdToCiPipeIdV2, "private")

# Projects
api.add_resource(starred_project.StarredProject, "/project/<sint:project_id>/star")

api.add_resource(
    gitlab.SyncGitCommitIssueRelationByPjName,
    "/project/issues_commit_by_name",
)
api.add_resource(pipeline.PipelineFile, "/project/<string:project_name>/pipeline_file")


# App
# api.add_resource(project.AllPodsAndServicesUnderApp, "/project/<sint:project_id>/app/<app_name>")


# Project son relation
api.add_resource(
    gitlab.SyncGitCommitIssueRelation,
    "/project/<sint:project_id>/issues_commit",
    "/project/<sint:project_id>/issues_commit/<issue_id>",
)
api.add_resource(gitlab.GetCommitIssueHookByBranch, "/project/<sint:project_id>/issues_commit/by_branch")

project_url(api, add_resource)

# Tag
tag_url(api, add_resource)
template_url(api, add_resource)


api.add_resource(template.TemplateList, "/template_list")
api.add_resource(template.TemplateListForCronJob, "/template_list_for_cronjob")
api.add_resource(template.SingleTemplate, "/template", "/template/<repository_id>")
api.add_resource(template.ProjectPipelineBranches, "/project/<repository_id>/pipeline/branches")
api.add_resource(template.ProjectPipelineDefaultBranch, "/project/<repository_id>/pipeline/default_branch")

# Gitlab project
api.add_resource(gitlab.GitProjectBranches, "/repositories/<repository_id>/branches")
api.add_resource(gitlab.GitProjectBranchesV2, "/v2/repositories/<repository_id>/branches")
add_resource(gitlab.GitProjectBranchesV2, "public")
api.add_resource(gitlab.GitProjectBranch, "/repositories/<repository_id>/branch/<branch_name>")
api.add_resource(gitlab.GitProjectBranchV2, "/v2/repositories/<repository_id>/branch/<branch_name>")
add_resource(gitlab.GitProjectBranchV2, "public")
api.add_resource(gitlab.GitProjectRepositories, "/repositories/<repository_id>/branch/<branch_name>/tree")
api.add_resource(gitlab.GitProjectRepositoriesV2, "/v2/repositories/<repository_id>/branch/<branch_name>/tree")
add_resource(gitlab.GitProjectRepositoriesV2, "public")
api.add_resource(
    gitlab.GitProjectFile,
    "/repositories/<repository_id>/branch/files",
    "/repositories/<repository_id>/branch/<branch_name>/files/<file_path>",
)
api.add_resource(
    gitlab.GitProjectTag, "/repositories/<repository_id>/tags/<tag_name>", "/repositories/<repository_id>/tags"
)
api.add_resource(
    gitlab.GitProjectTagV2, "/v2/repositories/<repository_id>/tags/<tag_name>", "/v2/repositories/<repository_id>/tags"
)
add_resource(gitlab.GitProjectTagV2, "public")
api.add_resource(gitlab.GitProjectBranchCommits, "/repositories/<repository_id>/commits")
api.add_resource(gitlab.GitProjectBranchCommitsV2, "/v2/repositories/<repository_id>/commits")
add_resource(gitlab.GitProjectBranchCommitsV2, "public")
api.add_resource(gitlab.GitProjectMembersCommits, "/repositories/<repository_id>/members_commits")
api.add_resource(gitlab.GitProjectMembersCommitsV2, "/v2/repositories/<repository_id>/members_commits")
add_resource(gitlab.GitProjectMembersCommitsV2, "public")
api.add_resource(gitlab.GitProjectNetwork, "/repositories/<repository_id>/overview")
api.add_resource(gitlab.GitProjectNetworkV2, "/v2/repositories/<repository_id>/overview")
add_resource(gitlab.GitProjectNetworkV2, "public")
api.add_resource(gitlab.GitProjectId, "/repositories/<repository_id>/id")
api.add_resource(gitlab.GitProjectIdV2, "/v2/repositories/<repository_id>/id")
add_resource(gitlab.GitProjectIdV2, "public")
api.add_resource(gitlab.GitProjectIdFromURL, "/repositories/id")
api.add_resource(gitlab.GitProjectIdFromURLV2, "/v2/repositories/id")
add_resource(gitlab.GitProjectIdFromURLV2, "public")
api.add_resource(gitlab.GitProjectURLFromId, "/repositories/url")
api.add_resource(gitlab.GitProjectURLFromIdV2, "/v2/repositories/url")
add_resource(gitlab.GitProjectURLFromIdV2, "public")
api.add_resource(gitlab.GitlabSingleCommit, "/repositories/<repo_id>/<commit_id>")
api.add_resource(gitlab.GitlabSingleCommitV2, "/v2/repositories/<repo_id>/<commit_id>")
add_resource(gitlab.GitlabSingleCommitV2, "public")
api.add_resource(gitlab.GitlabSourceCodeV2, "/repositories/pipline")
add_resource(gitlab.GitlabSourceCodeV2, "public")

# User
user_url(api, add_resource)

# Role
api.add_resource(role.RoleList, "/user/role/list")

# pipeline
api.add_resource(pipeline.PipelineExecAction, "/pipelines/<repository_id>/pipelines_exec/action")
api.add_resource(pipeline.PipelineExec, "/pipelines/<repository_id>/pipelines_exec")
api.add_resource(pipeline.PipelineConfig, "/pipelines/<repository_id>/config")


api.add_resource(pipeline.Pipeline, "/pipelines/<repository_id>/pipelines")
# api.add_resource(pipeline.PipelineExecLogs, "/pipelines/logs")
# api.add_resource(pipeline.PipelinePhaseYaml, "/pipelines/<repository_id>/branch/<branch_name>/phase_yaml")
# api.add_resource(pipeline.PipelineYaml, "/pipelines/<repository_id>/branch/<branch_name>/generate_ci_yaml")

# Websocket
# socketio.on_namespace(system_parameter.SyncTemplateWebsocketLog("/sync_template/websocket/logs"))
socketio.on_namespace(pipeline.PipelineWebsocketLog("/pipeline/websocket/logs"))
socketio.on_namespace(issue.IssueSocket("/issues/websocket"))

# issue
issue_url(api, add_resource)

api.add_resource(issue.IssueByUser, "/user/<sint:user_id>/issues")
api.add_resource(issue.IssueByUserV2, "/v2/user/<sint:user_id>/issues")
add_resource(issue.IssueByUserV2, "public")

api.add_resource(issue.IssueByVersion, "/issues_by_versions")
api.add_resource(issue.IssueByVersionV2, "/v2/issues_by_versions")
add_resource(issue.IssueByVersionV2, "public")

api.add_resource(issue.IssueStatus, "/issues_status")
api.add_resource(issue.IssueStatusV2, "/v2/issues_status")
add_resource(issue.IssueStatusV2, "public")

api.add_resource(issue.IssuePriority, "/issues_priority")
api.add_resource(issue.IssuePriorityV2, "/v2/issues_priority")
add_resource(issue.IssuePriorityV2, "public")

api.add_resource(issue.IssueTracker, "/issues_tracker")
api.add_resource(issue.IssueTrackerV2, "/v2/issues_tracker")
add_resource(issue.IssueTrackerV2, "public")

api.add_resource(issue.DatetimeStatusV2, "/v2/<sint:project_id>/datetime_status")
add_resource(issue.DatetimeStatusV2, "public")

# Issue Field Display
api.add_resource(issue_display_field.IssueFieldDisplay, "/issue_field_display")

# Release
# api.add_resource(release.Releases, "/project/<project_id>/releases")
# api.add_resource(release.Release, "/project/<project_id>/releases/<release_name>")

# Plugins
api.add_resource(plugin.Plugins, "/plugins")
api.add_resource(plugin.Plugin, "/plugins/<plugin_name>")

# dashboard
api.add_resource(issue.DashboardIssuePriority, "/dashboard_issues_priority/<user_id>")
api.add_resource(issue.DashboardIssuePriorityV2, "/v2/dashboard_issues_priority/<user_id>")
add_resource(issue.DashboardIssuePriorityV2, "private")

api.add_resource(issue.DashboardIssueProject, "/dashboard_issues_project/<user_id>")
api.add_resource(issue.DashboardIssueProjectV2, "/v2/dashboard_issues_project/<user_id>")
add_resource(issue.DashboardIssueProjectV2, "private")

api.add_resource(issue.DashboardIssueType, "/dashboard_issues_type/<user_id>")
api.add_resource(issue.DashboardIssueTypeV2, "/v2/dashboard_issues_type/<user_id>")
add_resource(issue.DashboardIssueTypeV2, "private")

api.add_resource(gitlab.GitTheLastHoursCommits, "/dashboard/the_last_hours_commits")
api.add_resource(sync_redmine.ProjectMembersCount, "/dashboard/project_members_count")
api.add_resource(sync_redmine.ProjectMembersDetail, "/dashboard/project_members_detail")
api.add_resource(sync_redmine.ProjectMembers, "/dashboard/<project_id>/project_members")
api.add_resource(sync_redmine.ProjectOverview, "/dashboard/project_overview")
api.add_resource(sync_redmine.RedmineProjects, "/dashboard/redmine_projects")
api.add_resource(sync_redmine.RedminProjectDetail, "/dashboard/redmine_projects_detail")
api.add_resource(sync_redmine.RedmineIssueRank, "/dashboard/issue_rank")
api.add_resource(sync_redmine.UnclosedIssues, "/dashboard/<user_id>/unclosed_issues")
api.add_resource(sync_redmine.PassingRate, "/dashboard/passing_rate")
api.add_resource(sync_redmine.PassingRateDetail, "/dashboard/passing_rate_detail")

# testPhase Requirement
api.add_resource(issue.RequirementByIssue, "/requirements_by_issue/<issue_id>")
api.add_resource(issue.RequirementByIssueV2, "/v2/requirements_by_issue/<issue_id>")
add_resource(issue.RequirementByIssueV2, "private")

api.add_resource(issue.Requirement, "/requirements/<requirement_id>")
api.add_resource(issue.RequirementV2, "/v2/requirements/<requirement_id>")
add_resource(issue.RequirementV2, "private")

# testPhase Flow
api.add_resource(issue.FlowByIssue, "/flows_by_issue/<issue_id>")
api.add_resource(issue.FlowByIssueV2, "/v2/flows_by_issue/<issue_id>")
add_resource(issue.FlowByIssueV2, "private")

api.add_resource(issue.GetFlowType, "/flows/support_type")
api.add_resource(issue.GetFlowTypeV2, "/v2/flows/support_type")
add_resource(issue.GetFlowTypeV2, "private")

api.add_resource(issue.Flow, "/flows/<flow_id>")
api.add_resource(issue.FlowV2, "/v2/flows/<flow_id>")
add_resource(issue.FlowV2, "private")

# testPhase Parameters FLow
api.add_resource(issue.ParameterByIssue, "/parameters_by_issue/<issue_id>")
api.add_resource(issue.ParameterByIssueV2, "/v2/parameters_by_issue/<issue_id>")
add_resource(issue.ParameterByIssueV2, "private")

api.add_resource(issue.Parameter, "/parameters/<parameter_id>")
api.add_resource(issue.ParameterV2, "/v2/parameters/<parameter_id>")
add_resource(issue.ParameterV2, "private")

api.add_resource(issue.ParameterType, "/parameter_types")
api.add_resource(issue.ParameterTypeV2, "/v2/parameter_types")
add_resource(issue.ParameterTypeV2, "private")

# testPhase TestCase Support Case Type
api.add_resource(apiTest.TestCases, "/test_cases")
api.add_resource(apiTest.TestCase, "/test_cases/<sint:tc_id>", "/testCases/<sint:tc_id>")

api.add_resource(apiTest.GetTestCaseType, "/testCases/support_type")

# testPhase TestCase
api.add_resource(apiTest.TestCaseByIssue, "/testCases_by_issue/<issue_id>")
api.add_resource(apiTest.TestCaseByProject, "/testCases_by_project/<project_id>")
# api.add_resource(apiTest.TestCase, '/testCases/<sint:tc_id>')

# testPhase TestCase Support API Method
api.add_resource(apiTest.GetTestCaseAPIMethod, "/testCases/support_RestfulAPI_Method")

# testPhase TestItem Support API Method
api.add_resource(apiTest.TestItemByTestCase, "/testItems_by_testCase/<tc_id>")
api.add_resource(apiTest.TestItem, "/testItems/<item_id>")

# testPhase Testitem Value
api.add_resource(apiTest.GetTestValueLocation, "/testValues/support_locations")
api.add_resource(apiTest.GetTestValueType, "/testValues/support_types")
api.add_resource(apiTest.TestValueByTestItem, "/testValues_by_testItem/<item_id>")
api.add_resource(apiTest.TestValue, "/testValues/<value_id>")

# Integrated test results
api.add_resource(cicd.CommitCicdSummary, "/project/<sint:project_id>/test_summary/<commit_id>")


# Get everything by issue_id
api.add_resource(issue.DumpByIssue, "/dump_by_issue/<issue_id>")


# Files
api.add_resource(redmine.RedmineFile, "/download", "/file/<int:file_id>")

api.add_resource(redmine.RedmineMail, "/mail")
api.add_resource(redmine.RedmineMailActive, "/mail/active")

system_url(api, add_resource)

# Mocks
# api.add_resource(mock.MockTestResult, '/mock/test_summary')
# api.add_resource(mock.MockSesame, '/mock/sesame')
# api.add_resource(mock.UserDefaultFromAd, '/mock/userdefaultad')

# Harbor
# harbor_url(api, add_resource)

# Maintenance
# api.add_resource(maintenance.UpdateDbRcProjectPipelineId, "/maintenance/update_rc_pj_pipe_id")
# api.add_resource(
#     maintenance.SecretesIntoRcAll,
#     "/maintenance/secretes_into_rc_all",
#     "/maintenance/secretes_into_rc_all/<secret_name>",
# )
# api.add_resource(
#     maintenance.RegistryIntoRcAll,
#     "/maintenance/registry_into_rc_all",
#     "/maintenance/registry_into_rc_all/<registry_name>",
# )
# api.add_resource(maintenance.UpdatePjHttpUrl, "/maintenance/update_pj_http_url")


# Activity
api.add_resource(activity.AllActivities, "/all_activities")
api.add_resource(activity.ProjectActivities, "/project/<sint:project_id>/activities")


# Sync Redmine, Gitlab, Rancher
api.add_resource(sync_redmine.SyncRedmine, "/sync_redmine")
api.add_resource(sync_redmine.SyncRedmineNow, "/sync_redmine/now")
api.add_resource(gitlab.GitCountEachPjCommitsByDays, "/sync_gitlab/count_each_pj_commits_by_days")
api.add_resource(issue.ExecuteIssueAlert, "/sync_issue_alert")

# Subadmin Projects Permission
api.add_resource(project_permission.AdminProjects, "/project_permission/admin_projects")
api.add_resource(project_permission.SubadminProjects, "/project_permission/subadmin_projects")
api.add_resource(project_permission.Subadmins, "/project_permission/subadmins")
api.add_resource(project_permission.SetPermission, "/project_permission/set_permission")

# Quality
# api.add_resource(quality.TestPlanList, "/quality/<int:project_id>/testplan_list")
# api.add_resource(quality.TestPlan,
#                  '/quality/<int:project_id>/testplan/<int:testplan_id>')
# api.add_resource(quality.TestFileByTestPlan, "/quality/<int:project_id>/testfile_by_testplan/<int:testplan_id>")
# api.add_resource(quality.TestFileList, "/quality/<int:project_id>/testfile_list")
# api.add_resource(
#     quality.TestFile,
#     "/quality/<int:project_id>/testfile/<software_name>",
#     "/quality/<int:project_id>/testfile/<software_name>/<test_file_name>",
# )
# api.add_resource(
#     quality.TestPlanWithTestFile,
#     "/quality/<int:project_id>/testplan_with_testfile",
#     "/quality/<int:project_id>/testplan_with_testfile/<int:item_id>",
# )
# api.add_resource(quality.Report, "/quality/<int:project_id>/report")

# # System versions
# api.add_resource(NexusVersion, "/system_versions")

# sync_projects_url(api, add_resource)
# sync_users_url(api, add_resource)


# Centralized version check
# api.add_resource(devops_version.DevOpsVersion, "/devops_version")
# api.add_resource(devops_version.DevOpsVersionCheck, "/devops_version/check")
# api.add_resource(devops_version.DevOpsVersionUpdate, "/devops_version/update")

'''
# Deploy
api.add_resource(deploy.Clusters, "/deploy/clusters")
api.add_resource(deploy.Cluster, "/deploy/clusters/<int:cluster_id>")
api.add_resource(deploy.Registries, "/deploy/registries")
api.add_resource(deploy.Registry, "/deploy/registries/<int:registry_id>")

api.add_resource(deploy.ReleaseApplication, "/deploy/release/<int:release_id>")

api.add_resource(deploy.Applications, "/deploy/applications")
api.add_resource(deploy.Application, "/deploy/applications/<int:application_id>")
# 20230215 為新增 application_header table 而新增下列一段程式
api.add_resource(deploy.ApplicationHeaders, "/deploy/app_headers")
api.add_resource(deploy.ApplicationHeader, "/deploy/app_headers/<int:app_header_id>")
api.add_resource(deploy.DeleteApplicationHeader, "/deploy/app_headers/<int:app_header_id>/<int:application_id>")
# 20230215 為新增 application_header table 而新增上列一段程式

api.add_resource(deploy.RedeployApplication, "/deploy/applications/<int:application_id>/redeploy")

api.add_resource(deploy.UpdateApplication, "/deploy/applications/<int:application_id>/update")

api.add_resource(deploy.Cronjob, "/deploy/applications/cronjob")

# 20230118 新增下列API程式，以解決因遠端機器不存在造成TIMEOUT使得無法取得APPLICATION的資料列表
api.add_resource(deploy.Deployment, "/deploy/applications/deployment/<int:application_id>")
# 20230118 新增上列API程式，以解決因遠端機器不存在造成TIMEOUT使得無法取得APPLICATION的資料列表
# 20230118 為取得 storage class 資訊而新增下列API
api.add_resource(deploy.StorageClass, "/deploy/clusters/storage/<int:cluster_id>")
# 20230118 為取得 storage class 資訊而新增上列API
# 20230201 為變更 storage class disabled 布林值而新增下列API
api.add_resource(deploy.UpdateStorageClass, "/deploy/storage/<int:storage_class_id>")
# 20230201 為變更 storage class disabled 布林值而新增上列API
# 20230202 為取得 persistent volume claim 資訊而新增下列API
api.add_resource(deploy.PersistentVolumeClaim, "/deploy/clusters/storage/pvc/<int:storage_class_id>")
# 20230202 為取得 persistent volume claim 資訊而新增上列API
'''
# Alert
api.add_resource(alert.ProjectAlert, "/project/<sint:project_id>/alert")
api.add_resource(alert.ProjectAlertUpdate, "/alert/<int:alert_id>")
api.add_resource(alert.DefaultAlertDaysUpdate, "/alert/default_days")

'''
# Trace Order
api.add_resource(trace_order.TraceOrders, "/trace_order")
api.add_resource(trace_order.TraceOrdersV2, "/v2/trace_order")
add_resource(trace_order.TraceOrdersV2, "private")

api.add_resource(trace_order.SingleTraceOrder, "/trace_order/<sint:trace_order_id>")
api.add_resource(trace_order.SingleTraceOrderV2, "/v2/trace_order/<sint:trace_order_id>")
add_resource(trace_order.SingleTraceOrderV2, "private")

api.add_resource(trace_order.ExecuteTraceOrder, "/trace_order/execute")
api.add_resource(trace_order.ExecuteTraceOrderV2, "/v2/trace_order/execute")
add_resource(trace_order.ExecuteTraceOrderV2, "private")

api.add_resource(trace_order.GetTraceResult, "/trace_order/result")
api.add_resource(trace_order.GetTraceResultV2, "/v2/trace_order/result")
add_resource(trace_order.GetTraceResultV2, "private")
'''
# monitoring
# monitoring.monitoring_url(api, add_resource)

# System parameter
sync_system_parameter_url(api, add_resource)
api.add_resource(system_parameter.SystemParameters, "/system_parameter", "/system_parameter/<int:param_id>")
api.add_resource(system_parameter.ParameterGithubVerifyExecuteStatus, "/system_parameter/github_verify/status")

# Status of Sync
lock_url(api, add_resource)

# message
# notification_message_url(api, add_resource, socketio)

# routine job
api.add_resource(routine_job.DoJobByMonth, "/routine_job/by_month")
api.add_resource(routine_job.DoJobByDay, "/routine_job/by_day")


@app.before_request
def pre_check_block_ip_account():
    print("test cors")


@app.route("/user/login", methods=["POST"])
def login():
    from flask import request
    from resources.user import login

    try:
        args = request.get_json()
    except Exception:
        args = {
            "username": request.form.get("username"),
            "password": request.form.get("password"),
        }
    return login(args)


def start_prod():
    try:
        db.init_app(app)
        db.app = app
        jsonwebtoken.init_app(app)
        initialize(config.get("SQLALCHEMY_DATABASE_URI"))
        migrate.run()
        # kubernetesClient.create_iiidevops_env_secret_namespace()
        # with app.app_context():  # Prevent error appear(Working outside of application context.)
        #     kubernetesClient.create_cron_secret()

        # threading.Thread(target=kubernetesClient.apply_cronjob_yamls).start()
        logger.logger.info("Apply k8s-yaml cronjob.")

        # Template init
        if should_update_template_cache():
            fetch_and_update_template_cache()
            logger.logger.info("Created template cache.")
        template.tm_get_template_list()
        logger.logger.info("Get the public and local template list")

        plugins.create_plugins_api_router(api, add_resource)
        plugins.sync_plugins_in_db_and_code()
        return app
    except Exception as e:
        ret = internal_error(e)
        if ret[1] == 404:
            logger.logger.exception(e)
        raise e


if __name__ == "__main__":
    start_prod()
    # app.run(host="0.0.0.0", port=10010)
    socketio.run(app, host="0.0.0.0", port=10009)
