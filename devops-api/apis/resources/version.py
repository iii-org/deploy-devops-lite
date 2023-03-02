from flask_jwt_extended import jwt_required
from flask_restful import reqparse, Resource
from sqlalchemy.exc import NoResultFound

import resources.apiError as apiError
import resources.project as project
import util as util
from resources import role
from resources.redmine import redmine
from resources import logger
from flask_jwt_extended import get_jwt_identity
from model import db, ProjectUserRole

EMPTY_VERSIONS = {"versions": [], "total_count": 0}


def get_version_list_by_project(project_id, status, force_id):
    query = (
        ProjectUserRole.query.filter(ProjectUserRole.project_id == project_id)
        .filter(ProjectUserRole.user_id == get_jwt_identity()["user_id"])
        .all()
    )
    if query:
        logger.logger.info(f"project_id:{project_id} user_id:{get_jwt_identity()['user_id']} valid:True")
    else:
        logger.logger.info(f"project_id:{project_id} user_id:{get_jwt_identity()['user_id']} valid:False")

    if util.is_dummy_project(project_id):
        return util.success(EMPTY_VERSIONS)
    try:
        plan_id = project.get_plan_project_id(project_id)
    except NoResultFound:
        return util.respond(
            404,
            "Error while getting versions.",
            error=apiError.project_not_found(project_id),
        )
    version_list = redmine.rm_get_version_list(plan_id)
    if force_id is not None:
        force_ids = force_id.split(",")
    else:
        force_ids = []
    if status is not None:
        statuses = status.split(",")
        version_list["versions"] = list(
            filter(
                lambda x: (str(x.get("id")) in force_ids) or (x.get("status") in statuses),
                version_list["versions"],
            )
        )
        version_list["total_count"] = len(version_list["versions"])
    version_list.get("versions").sort(key=__compare_date_string)
    return version_list


def __compare_date_string(x):
    due_date = x.get("due_date", "")
    updated_on = x.get("updated_on", "")
    if due_date is None:
        due_date = "Z"
    if updated_on is None:
        updated_on = "Z"
    return due_date, updated_on


def post_version_by_project(project_id, message_args):
    try:
        plan_id = project.get_plan_project_id(project_id)
    except NoResultFound:
        return util.respond(
            404,
            "Error while getting versions.",
            error=apiError.project_not_found(project_id),
        )
    all_versions = get_version_list_by_project(project_id, None, None).get("versions")
    if all_versions != []:
        for version in all_versions:
            if version["name"] == message_args["version"]["name"]:
                return util.respond(
                    404,
                    "Project_version name is exist",
                    error=apiError.project_version_exist(message_args["version"]["name"]),
                )

    version = redmine.rm_post_version(plan_id, message_args)
    return util.success(version)


def get_version_by_version_id(version_id):
    version = redmine.rm_get_version(version_id)
    return util.success(version)


def put_version_by_version_id(version_id, args):
    redmine.rm_put_version(version_id, args)
    return util.success()


def delete_version_by_version_id(version_id):
    try:
        redmine.rm_delete_version(version_id)
    except apiError.DevOpsError as e:
        if e.status_code == 404:
            # Already deleted, let it go
            return util.respond(200, "already deleted")
        else:
            return util.respond(
                422,
                "Unable to delete the version.",
                error=apiError.redmine_unable_to_delete_version(version_id),
            )
    return util.success()
