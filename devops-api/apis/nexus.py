# Module to store methods related to nexus database, i.e. the database used by API Server.
from datetime import datetime

from flask_jwt_extended import get_jwt_identity
from sqlalchemy.exc import NoResultFound

import model
from resources import apiError
from resources.apiError import DevOpsError


def nx_get_project_plugin_relation(nexus_project_id=None, rm_project_id=None, repo_id=None, hb_project_id=None):
    filter_params = {}
    if nexus_project_id is not None:
        it = nexus_project_id
        filter_params["project_id"] = nexus_project_id
    elif rm_project_id is not None:
        it = rm_project_id
        filter_params["plan_project_id"] = rm_project_id
    elif repo_id is not None:
        it = repo_id
        filter_params["git_repository_id"] = repo_id
    # elif hb_project_id is not None:
    #     it = hb_project_id
    #     filter_params["harbor_project_id"] = hb_project_id
    else:
        raise apiError.DevOpsError(
            500,
            "Either nexus_project_id, rm_project_id, hb_project_id or \
                  repo_id needs to be indicated for nx_get_project_plugin_relation.",
            error=apiError.invalid_code_path(
                "Either nexus_project_id, rm_project_id, hb_project_id or \
                 repo_id needs to be indicated for nx_get_project_plugin_relation."
            ),
        )
    query = model.ProjectPluginRelation.query.filter_by(**filter_params)
    try:
        row = query.one()
    except NoResultFound:
        raise DevOpsError(
            404,
            "Error when getting project relations.",
            error=apiError.project_not_found(it),
        )
    return row


def nx_get_project(id=None, name=None):
    if id is not None:
        it = id
        query = model.Project.query.filter_by(id=id)
    elif name is not None:
        it = name
        query = model.Project.query.filter_by(name=name)
    else:
        raise apiError.DevOpsError(
            500,
            "Either id or name needs to be indicated for nx_get_project.",
            error=apiError.invalid_code_path("Either id or name needs to be indicated for nx_get_project."),
        )
    try:
        row = query.one()
    except NoResultFound:
        raise apiError.DevOpsError(404, "Project not found.", error=apiError.project_not_found(it))
    return row


def nx_get_user_plugin_relation(user_id=None, plan_user_id=None, gitlab_user_id=None):
    if plan_user_id is not None:
        try:
            return model.UserPluginRelation.query.filter_by(plan_user_id=plan_user_id).one()
        except NoResultFound:
            raise apiError.DevOpsError(
                404,
                "User with redmine id {0} does not exist in redmine.".format(plan_user_id),
                apiError.user_not_found(plan_user_id),
            )
    elif gitlab_user_id is not None:
        try:
            return model.UserPluginRelation.query.filter_by(repository_user_id=gitlab_user_id).one()
        except NoResultFound:
            raise apiError.DevOpsError(
                404,
                "User with gitlab_user id {0} does not exist in gitlab.".format(gitlab_user_id),
                apiError.user_not_found(gitlab_user_id),
            )
    else:
        try:
            return model.UserPluginRelation.query.filter_by(user_id=user_id).one()
        except NoResultFound:
            raise apiError.DevOpsError(
                404,
                "User id {0} does not exist.".format(user_id),
                apiError.user_not_found(user_id),
            )


def nx_get_user(id=None, login=None):
    if id is not None:
        it = id
        query = model.User.query.filter_by(id=id)
    elif login is not None:
        it = login
        query = model.User.query.filter_by(login=login)
    else:
        raise apiError.DevOpsError(
            500,
            "Either id or login needs to be indicated for nx_get_user.",
            error=apiError.invalid_code_path("Either id or login needs to be indicated for nx_get_user."),
        )
    try:
        row = query.one()
    except NoResultFound:
        raise apiError.DevOpsError(404, "User not found.", error=apiError.user_not_found(it))
    return row


def nx_update_project(project_id, args):
    project = model.Project.query.filter_by(id=project_id).one()
    for key in args.keys():
        if not hasattr(project, key):
            continue
        setattr(project, key, args[key])
    project.update_at = str(datetime.utcnow())
    model.db.session.commit()


def nx_update_project_relation(project_id, args):
    project = model.ProjectPluginRelation.query.filter_by(project_id=project_id).one()
    for key in args.keys():
        if not hasattr(project, key):
            continue
        setattr(project, key, args[key])
    model.db.session.commit()


def nx_get_repository_id(project_id):
    return nx_get_project_plugin_relation(project_id).git_repository_id


def nx_get_redmine_id(project_id):
    return nx_get_project_plugin_relation(project_id).plan_project_id


def nx_get_current_user_id():
    return get_jwt_identity()["user_id"]
