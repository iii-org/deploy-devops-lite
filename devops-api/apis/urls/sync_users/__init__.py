from . import view


def sync_users_url(api, add_resource):
    api.add_resource(view.SyncUsers, "/sync_users")
    api.add_resource(view.RecreateUserV2, "/v2/sync_users/<int:user_id>")
    add_resource(view.RecreateUserV2, "private")
    api.add_resource(view.CheckUserExistV2, "/v2/sync_users/check_user_exist")
    add_resource(view.CheckUserExistV2, "private")
