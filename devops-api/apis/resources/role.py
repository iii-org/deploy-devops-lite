from flask_jwt_extended import get_jwt_identity, jwt_required
from flask_restful import Resource

import nexus
from resources import apiError
import util
import model
from resources.apiError import DevOpsError


class Role:
    def __init__(self, id_, name):
        self.id = id_
        self.name = name


RD = Role(1, "Engineer")
PM = Role(3, "Project Manager")
ADMIN = Role(5, "Administrator")
BOT = Role(6, "Project BOT")
QA = Role(7, "QA")
ALL_ROLES = [
    # RD, 
    PM, 
    ADMIN, 
    BOT,
    # QA
]


def is_role(role):
    return get_jwt_identity()["role_id"] == role.id


def get_role_name(role_id):
    for role in ALL_ROLES:
        if role.id == role_id:
            return role.name
    return "Unknown Role"


def require_role(
    allowed_roles,
    err_message="Your role does not have the permission for this operation.",
):
    if type(allowed_roles) is int:
        allowed_roles = [allowed_roles]
    for allowed_role in allowed_roles:
        if allowed_role == get_jwt_identity()["role_id"]:
            return
    raise apiError.NotAllowedError(err_message)


def require_admin(err_message="You must be an admin for this operation."):
    require_role([ADMIN.id], err_message)


def require_pm(
    err_message="You must be a PM for this operation.",
    exclude_admin=False,
    exclude_qa=False,
):
    allowed_roles = [PM.id]
    if not exclude_admin:
        allowed_roles.append(ADMIN.id)
    if not exclude_qa:
        allowed_roles.append(QA.id)
    require_role(allowed_roles, err_message)


def require_in_project(
    project_id=None,
    err_message="You need to be in the project for this operation.",
    even_admin=False,
    project_name=None,
    repository_id=None,
):
    if repository_id is not None:
        project_id = nexus.nx_get_project_plugin_relation(repo_id=repository_id).project_id
    if project_id is None and project_name is not None:
        project_id = nexus.nx_get_project(name=project_name).id
    identity = get_jwt_identity()
    user_id = identity["user_id"]
    if not even_admin and identity["role_id"] == ADMIN.id:
        return
    check_result = verify_project_user(project_id, user_id)
    if check_result:
        return
    else:
        raise apiError.NotInProjectError(err_message)


def require_user_himself(user_id, err_message=None, even_pm=True, even_admin=False):
    identity = get_jwt_identity()
    my_user_id = identity["user_id"]
    role_id = identity["role_id"]
    if my_user_id == int(user_id):
        return
    if role_id == RD.id or even_pm and role_id == PM.id or even_admin and role_id == ADMIN.id:
        if err_message is None:
            if even_admin:
                err_message = "Only the user himself can access another user's data."
            elif even_pm:
                err_message = "Only admin can access another user's data."
            else:
                err_message = "Only admin and PM can access another user's data."
        raise apiError.NotUserHimselfError(err_message)
    return


def verify_project_user(project_id, user_id):
    if util.is_dummy_project(project_id):
        return True
    count = model.ProjectUserRole.query.filter_by(project_id=project_id, user_id=user_id).count()
    return count > 0


def get_user_roles(is_option=False):
    output_array = []
    for r in ALL_ROLES:
        if r is BOT:
            continue
        if is_option:
            role_info = {"value": r.id, "name": r.name}
        else:
            role_info = {"id": r.id, "name": r.name}
        output_array.append(role_info)
    return output_array


def get_role_list():
    return util.success({"role_list": get_user_roles()})


def update_role(user_id, new_role_id):
    rows = model.ProjectUserRole.query.filter_by(user_id=user_id).all()
    if len(rows) == 0:
        raise DevOpsError(404, "User not found.", apiError.user_not_found(user_id))
    if len(rows) > 1:
        # No change will be made, just returns
        if rows[0].role_id == new_role_id:
            return
        # Can not change role when belonging to a project
        raise DevOpsError(400, "User is in a project.", apiError.user_in_a_project(user_id))
    rows[0].role_id = new_role_id
    model.db.session.commit()


def is_admin():
    if get_jwt_identity()["role_id"] == ADMIN.id:
        return True
    else:
        return False


def require_project_owner(user_id, project_id):
    if not is_admin() and model.Project.query.get(project_id).owner_id != user_id:
        raise apiError.NotAllowedError("Only admin and Project owner can operate.")


# --------------------- Resources ---------------------
class RoleList(Resource):
    # noinspection PyMethodMayBeStatic
    @jwt_required()
    def get(self):
        return get_role_list()
