from flask_jwt_extended import jwt_required
from flask_restful import Resource

import model
import nexus
import util
from resources import role
from resources.apiError import DevOpsError, maximum_error


def spj_set(user_id, project_id):
    row = model.StarredProject.query.filter_by(user_id=user_id, project_id=project_id).first()
    if row:
        # Already has the record
        return
    if model.StarredProject.query.filter_by(user_id=user_id).count() >= 10:
        # Limit to 10
        raise DevOpsError(
            400,
            f"User {user_id} can not added {project_id} to starred projects, reached the limit of 10",
            error=maximum_error("Stared projects", 10),
        )
    new = model.StarredProject(user_id=user_id, project_id=project_id)
    model.db.session.add(new)
    model.db.session.commit()


def spj_unset(user_id, project_id):
    row = model.StarredProject.query.filter_by(user_id=user_id, project_id=project_id).first()
    if not row:
        # Already does not have the record
        return
    model.db.session.delete(row)
    model.db.session.commit()


# --------------------- Resources ---------------------
class StarredProject(Resource):
    @jwt_required()
    def post(self, project_id):
        role.require_in_project(project_id)
        spj_set(nexus.nx_get_current_user_id(), project_id)
        return util.success()

    @jwt_required()
    def delete(self, project_id):
        spj_unset(nexus.nx_get_current_user_id(), project_id)
        return util.success()
