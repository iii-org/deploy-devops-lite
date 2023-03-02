import logging
from logging import handlers

from flask import current_app, has_request_context
from flask_jwt_extended import get_jwt_identity, verify_jwt_in_request


class DevOpsFilter(logging.Filter):
    def filter(self, record):
        record.user_id = -1
        record.user_name = ""
        if has_request_context():
            try:
                jwt = get_jwt_identity()
            except RuntimeError:
                jwt = None
            if jwt is None:
                record.user_id = 1
                record.user_name = "system"
            else:
                with current_app.app_context():
                    verify_jwt_in_request()
                record.user_id = jwt["user_id"]
                record.user_name = jwt["user_account"]
        else:
            record.user_id = 1
            record.user_name = "system"
        return True


import os

if not os.path.exists("logs"):
    os.makedirs("logs")

handler = handlers.TimedRotatingFileHandler(
    "logs/devops-api.log", when="D", interval=1, backupCount=14, encoding="utf-8"
)
handler.setFormatter(
    logging.Formatter(
        "%(asctime)s %(user_name)s/%(user_id)d %(filename)s" " [line:%(lineno)d] %(levelname)s %(message)s",
        "%Y %b %d, %a %H:%M:%S",
    )
)
logger = logging.getLogger("devops.api")
logger.addFilter(DevOpsFilter())
logger.setLevel(logging.INFO)
logger.addHandler(handler)
