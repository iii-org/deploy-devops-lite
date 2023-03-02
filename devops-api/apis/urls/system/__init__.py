from . import view


def system_url(api, add_resource):
    # System administrations
    api.add_resource(view.SystemGitCommitID, "/system_git_commit_id")  # git commit
    api.add_resource(view.SystemInfoReport, "/system_info_report")
    api.add_resource(view.SendMergeRequestNotification, "/v2/system/send_merge_request_notification")

    add_resource(view.SendMergeRequestNotification, "private")

    # api.add_resource(view.SystemCheckPipelineUpdate, "/pipeline/check_update")
