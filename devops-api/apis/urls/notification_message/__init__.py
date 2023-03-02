from . import view


def notification_message_url(api, add_resource, socketio):
    api.add_resource(view.MessageListForAdminV2, "/v2/notification_message_list/admin")
    add_resource(view.MessageListForAdminV2, "private")

    api.add_resource(view.MessageListV2, "/v2/notification_message_list")
    add_resource(view.MessageListV2, "private")

    api.add_resource(view.MessageV2, "/v2/notification_message")
    add_resource(view.MessageV2, "private")

    api.add_resource(view.MessageIdV2, "/v2/notification_message/<int:message_id>")
    add_resource(view.MessageIdV2, "private")

    api.add_resource(view.MessageCloseV2, "/v2/notification_message/<int:message_id>/close")
    add_resource(view.MessageCloseV2, "private")

    api.add_resource(view.MessageReplyV2, "/v2/notification_message_reply/<int:user_id>")
    add_resource(view.MessageReplyV2, "private")

    socketio.on_namespace(view.GetNotificationMessage("/v2/get_notification_message"))
