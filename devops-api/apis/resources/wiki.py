from flask_jwt_extended import jwt_required, get_jwt_identity
from flask_restful import Resource, reqparse
from sqlalchemy.exc import NoResultFound

import nexus
import resources.apiError as apiError
import resources.project as project
import resources.user as user
import util as util
from resources import role, logger
from resources.redmine import redmine, get_redmine_obj


def get_wiki_list_by_project(project_id):
    if util.is_dummy_project(project_id):
        return util.success({"wiki_pages": []})
    try:
        plan_id = project.get_plan_project_id(project_id)
    except NoResultFound:
        return util.respond(
            404,
            "Error while getting wiki.",
            error=apiError.project_not_found(project_id),
        )
    wiki_list = redmine.rm_get_wiki_list(plan_id)
    return util.success(wiki_list)


def get_wiki_by_project(project_id, wiki_name):
    try:
        plan_id = project.get_plan_project_id(project_id)
    except NoResultFound:
        return util.respond(
            404,
            "Error while getting wiki.",
            error=apiError.project_not_found(project_id),
        )
    wiki_list = redmine.rm_get_wiki(plan_id, wiki_name)
    wiki_detail = wiki_list
    if "author" in wiki_detail["wiki_page"]:
        user_info = user.get_user_id_name_by_plan_user_id(wiki_detail["wiki_page"]["author"]["id"])
        if user_info is not None:
            wiki_detail["wiki_page"]["author"] = {
                "id": user_info.id,
                "name": user_info.name,
            }
    return util.success(wiki_detail)


def put_wiki_by_project(project_id, wiki_name, args, operator_id):
    try:
        plan_id = project.get_plan_project_id(project_id)
    except NoResultFound:
        return util.respond(
            404,
            "Error while updating wiki.",
            error=apiError.project_not_found(project_id),
        )
    plan_operator_id = None
    if operator_id is not None:
        operator_plugin_relation = nexus.nx_get_user_plugin_relation(user_id=operator_id)
        plan_operator_id = operator_plugin_relation.plan_user_id
    personal_redmine_obj = get_redmine_obj(plan_user_id=plan_operator_id)
    personal_redmine_obj.rm_put_wiki(plan_id, wiki_name, args)
    logger.logger.info(f"Delete: {personal_redmine_obj.operator_id}")
    del personal_redmine_obj
    return util.success()


def delete_wiki_by_project(project_id, wiki_name):
    try:
        plan_id = project.get_plan_project_id(project_id)
    except NoResultFound:
        return util.respond(
            404,
            "Error while deleting wiki.",
            error=apiError.project_not_found(project_id),
        )
    redmine.rm_delete_wiki(plan_id, wiki_name)
    return util.success()
