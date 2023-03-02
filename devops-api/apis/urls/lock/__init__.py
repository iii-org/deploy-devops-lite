from . import view


def lock_url(api, add_resource):
    api.add_resource(view.LockStatus, "/lock")
    api.add_resource(view.LockStatusV2, "/v2/lock")
    add_resource(view.LockStatusV2, "private")
