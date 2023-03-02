from flask_jwt_extended import jwt_required
from flask_restful import Resource

import model
import util
from plugins.sonarqube.sonarqube_main import sq_get_history_by_commit
from resources import apiTest, role


def check_plugin_software_open(project_id, commit_id):
    return {"sonarqube": sq_get_history_by_commit(project_id, commit_id)}



def get_commit_summary(project_id, commit_id):
    output = {}
    result = check_plugin_software_open(project_id, commit_id)
    if result is not None:
        output.update(result)
    return output


# ---------------- Resources ----------------
class CommitCicdSummary(Resource):
    @jwt_required()
    def get(self, project_id, commit_id):
        role.require_in_project(project_id)
        return util.success(get_commit_summary(project_id, commit_id))
