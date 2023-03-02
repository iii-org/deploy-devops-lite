import util
from flask_apispec import doc, marshal_with, use_kwargs
from flask_apispec.views import MethodResource
from flask_restful import Resource
from resources.system import (
    send_merge_request_notification,
    system_git_commit_id,
    system_info_report,
)
# from resources.check_version import update_pipeline


class SystemInfoReport(Resource):
    def put(self):
        system_info_report()
        return util.success()


# noinspection PyMethodMayBeStatic
class SystemGitCommitID(Resource):
    def get(self):
        return util.success(system_git_commit_id())


@doc(
    tags=["Merge Request"],
    description="Check system all merge request and send notification message to user",
)
class SendMergeRequestNotification(MethodResource):
    def get(self):
        send_merge_request_notification()
        return util.success()


# class SystemCheckPipelineUpdate(Resource):
#     def post(self):
#         return util.success(update_pipeline())
