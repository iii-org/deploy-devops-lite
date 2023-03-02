from . import view


def tag_url(api, add_resource):
    api.add_resource(view.Tags, "/tags")
    api.add_resource(view.TagsV2, "/v2/tags")
    add_resource(view.TagsV2, "private")

    api.add_resource(view.Tag, "/tags/<int:tag_id>")
    api.add_resource(view.TagV2, "/v2/tags/<int:tag_id>")
    add_resource(view.TagV2, "private")
    api.add_resource(view.UserTags, "/user/tags")
