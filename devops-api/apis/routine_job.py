from flask_restful import Resource
from flask_jwt_extended import jwt_required
from threading import Thread
import util
from resources import notification_message, devops_version


class DoJobByMonth(Resource):
    @jwt_required()
    def post(self):
        Thread(
            target=notification_message.clear_has_expired_notifications_message,
            args=(
                "notification_message_period_of_validity",
                1,
                "months",
            ),
        ).start()
        return util.success()


class DoJobByDay(Resource):
    @jwt_required()
    def post(self):
        Thread(target=devops_version.has_devops_update).start()
        return util.success()
