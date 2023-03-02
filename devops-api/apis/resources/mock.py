from flask_restful import Resource, reqparse

import util
from accessories import redmine_lib


def mock_cm_status(status):
    if status == 1:
        return {
            "message": "success",
            "data": {
                "test_results": {
                    "postman": {"passed": 0, "failed": 3, "total": 3},
                    "checkmarx": {
                        "message": "The scan is not completed yet.",
                        "status": 1,
                    },
                }
            },
        }, 200
    if status == 2:
        return {
            "message": "success",
            "data": {
                "test_results": {
                    "postman": {"passed": 0, "failed": 3, "total": 3},
                    "checkmarx": {
                        "message": "The report is not ready yet.",
                        "status": 2,
                        "highSeverity": 0,
                        "mediumSeverity": 0,
                        "lowSeverity": 2,
                        "infoSeverity": 0,
                        "statisticsCalculationDate": "2020-11-24T15:06:19.283",
                    },
                }
            },
        }, 200
    if status == 3:
        return {
            "message": "success",
            "data": {
                "test_results": {
                    "postman": {"passed": 0, "failed": 3, "total": 3},
                    "checkmarx": {
                        "message": "success",
                        "status": 3,
                        "highSeverity": 0,
                        "mediumSeverity": 0,
                        "lowSeverity": 2,
                        "infoSeverity": 0,
                        "statisticsCalculationDate": "2020-11-24T10:49:33.07",
                        "run_at": "2020-11-24 10:47:53.165285",
                        "report_id": 5053,
                    },
                }
            },
        }, 200


def mock_sesame_get():
    issue = redmine_lib.redmine.issue.get(448, include="journals")
    return list(issue)


# ----------- Resources -----------

# noinspection PyMethodMayBeStatic
class MockTestResult(Resource):
    def get(self):
        parser = reqparse.RequestParser()
        parser.add_argument("cm_status", type=int, location="args")
        args = parser.parse_args()

        if "cm_status" in args:
            return mock_cm_status(args["cm_status"])

        return util.respond(404, "No suck muck.")


class MockSesame(Resource):
    def get(self):
        ret = mock_sesame_get()
        return ret
