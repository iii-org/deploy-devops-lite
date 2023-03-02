from . import view


def router_url(api, add_resource):

    # Router
    api.add_resource(view.Router, "/router")
    api.add_resource(view.UI_Router, "/ui_router")
