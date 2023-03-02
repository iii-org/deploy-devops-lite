from . import view


def sync_projects_url(api, add_resource):
    api.add_resource(view.SyncProject, "/sync_projects")
    api.add_resource(view.RecreateProjectV2, "/v2/sync_projects/<int:project_id>")
    add_resource(view.RecreateProjectV2, "private")
    api.add_resource(view.CheckProjectExistV2, "/v2/sync_projects/check_project_exist")
    add_resource(view.CheckProjectExistV2, "private")
