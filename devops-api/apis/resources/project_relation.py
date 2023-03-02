import model
from flask_jwt_extended import get_jwt_identity
from datetime import datetime
from accessories import redmine_lib
from sqlalchemy.orm import joinedload
from resources import role
from model import db


def get_plan_id(project_id):
    row = model.ProjectPluginRelation.query.filter_by(project_id=project_id).first()
    if row:
        return row.plan_project_id
    else:
        return -1


def get_project_id(plan_id):
    row = model.ProjectPluginRelation.query.filter_by(plan_project_id=plan_id).first()
    if row:
        return row.project_id
    else:
        return -1


def get_project_name(project_id):
    return model.Project.query.get(project_id).display


def get_all_fathers_project(project_id, father_id_list):
    parent_son_relations_object = model.ProjectParentSonRelation.query.filter_by(son_id=project_id).first()
    if parent_son_relations_object is None:
        return father_id_list
    parent_id = parent_son_relations_object.parent_id
    father_id_list.append(parent_id)
    return get_all_fathers_project(parent_id, father_id_list)


def get_all_sons_project(project_id, son_id_list):
    parent_son_relations_object = model.ProjectParentSonRelation.query.filter_by(parent_id=project_id).all()
    son_ids = [relation.son_id for relation in parent_son_relations_object]
    son_id_list += son_ids
    for id in son_ids:
        get_all_sons_project(id, son_id_list)
    return son_id_list


def user_in_project(project_id):
    return (
        model.ProjectUserRole.query.filter_by(project_id=project_id, user_id=get_jwt_identity()["user_id"]).first()
        is not None
    )


def get_all_relation_project(project_id):
    father_projects, son_projects = get_all_fathers_project(project_id, []), get_all_sons_project(project_id, [])
    all_relation_pj_ids = father_projects + son_projects
    if get_jwt_identity()["role_id"] != 5:
        all_relation_pj_ids = list(filter(user_in_project, all_relation_pj_ids))
    ret = [
        {
            "id": int(pj_id),
            "name": model.Project.query.get(pj_id).name,
            "display": model.Project.query.get(pj_id).display,
            "type": "father" if pj_id in father_projects else "son",
        }
        for pj_id in all_relation_pj_ids
    ]
    ret.sort(key=lambda x: x["display"])
    return ret


def is_user_in_project(project_id, force):
    if force:
        return True
    if get_jwt_identity()["role_id"] == 5:
        return True
    return (
        model.ProjectUserRole.query.filter_by(project_id=project_id, user_id=get_jwt_identity()["user_id"]).first()
        is not None
    )


def get_root_project_id(project_id, force=False):
    parent_son_relations_object = model.ProjectParentSonRelation.query.filter_by(son_id=project_id).first()
    if parent_son_relations_object is None or not is_user_in_project(parent_son_relations_object.parent_id, force):
        return project_id
    parent_id = parent_son_relations_object.parent_id
    return get_root_project_id(parent_id, force)


def __check_project_relation(relation_pj_ids: list[int]):
    try:
        user_id = get_jwt_identity()["user_id"]
        role_id = get_jwt_identity()["role_id"]
    except Exception as e:
        user_id, role_id = 1, role.ADMIN.id

    query = model.ProjectUserRole.query.filter(model.ProjectUserRole.project_id.in_(relation_pj_ids))
    if role_id != role.ADMIN.id:
        query = query.filter_by(user_id=user_id)
    return query.first() is not None


def project_has_child(project_id):
    relation_pj_ids = [row.son_id for row in model.ProjectParentSonRelation.query.filter_by(parent_id=project_id).all()]
    return __check_project_relation(relation_pj_ids)


def project_has_parent(project_id):
    relation_pj_ids = [row.parent_id for row in model.ProjectParentSonRelation.query.filter_by(son_id=project_id).all()]
    return __check_project_relation(relation_pj_ids)


def get_relation_list(project_id, ret):
    son_project_ids = [
        {"id": relation.son_id, "name": get_project_name(relation.son_id)}
        for relation in model.ProjectParentSonRelation.query.filter_by(parent_id=project_id).all()
    ]
    son_pj_ids = []
    if son_project_ids != []:
        # Check user is project's member
        if get_jwt_identity()["role_id"] == 5:
            son_pj_ids = son_project_ids
        else:
            user_id = get_jwt_identity()["user_id"]
            son_pj_ids = [
                son_pj_id
                for son_pj_id in son_project_ids
                if model.ProjectUserRole.query.filter_by(user_id=user_id, project_id=son_pj_id["id"]).first()
                is not None
            ]

        ret.append(
            {
                "parent": {"id": project_id, "name": get_project_name(project_id)},
                "child": son_pj_ids,
            }
        )
    for pj in son_pj_ids:
        get_relation_list(pj["id"], ret)
    return ret


def sync_project_relation():
    # Check current hour is same as regular running hour that user set.
    hours = int(model.SystemParameter.query.filter_by(name="sync_redmine_project_relation").one().value["hours"])
    if hours == 0:
        return
    default_sync_date = datetime.utcnow()
    current_hour = default_sync_date.hour
    project_relations = model.ProjectParentSonRelation.query.limit(1).all()
    if current_hour % hours != 0:
        return

    if len(project_relations) != 0:
        latest_created_at = project_relations[0].created_at.hour
        current_hour = current_hour if current_hour > latest_created_at else current_hour + 24
        if (current_hour - latest_created_at) % hours != 0:
            return

    default_sync_date = default_sync_date.strftime("%Y-%m-%d %H:%M:%S")
    project_relations = []
    for project in model.Project.query.all():
        if project.id != -1:
            try:
                plan_object = redmine_lib.redmine.project.get(get_plan_id(project.id))
            except:
                continue
            if "parent" in dir(plan_object):
                project_relation = model.ProjectParentSonRelation(
                    parent_id=get_project_id(plan_object.parent.id),
                    son_id=project.id,
                    created_at=default_sync_date,
                )
                project_relations.append(project_relation)
    model.db.session.add_all(project_relations)
    model.db.session.commit()

    for project_relation in model.ProjectParentSonRelation.query.all():
        if str(project_relation.created_at) != default_sync_date:
            model.db.session.delete(project_relation)
    model.db.session.commit()


def get_project_family_members_by_user_helper(project_id):
    if get_jwt_identity()["role_id"] == 5:
        return True
    user_id = get_jwt_identity()["user_id"]
    return model.ProjectUserRole.query.filter_by(project_id=project_id, user_id=user_id).first() is not None


def get_project_family_members_by_user(project_id):
    son_project_id_list = list(
        filter(
            get_project_family_members_by_user_helper,
            get_all_sons_project(project_id, []),
        )
    )
    user_list = []
    user_ids = []
    for project_id in son_project_id_list:
        project_row = (
            model.Project.query.options(
                joinedload(model.Project.user_role)
                .joinedload(model.ProjectUserRole.user)
                .joinedload(model.User.project_role)
            )
            .filter_by(id=project_id)
            .one()
        )
        for user in project_row.user_role:
            if (
                user.role_id not in [role.BOT.id, role.ADMIN.id, role.QA.id]
                and not user.user.disabled
                and user.user.id not in user_ids
            ):
                user_list.append(user)
                user_ids.append(user.user.id)

    user_list.sort(key=lambda x: x.user_id, reverse=True)

    return [
        {
            "id": relation_row.user.id,
            "name": relation_row.user.name,
            "role_id": relation_row.role_id,
            "role_name": role.get_role_name(relation_row.role_id),
        }
        for relation_row in user_list
    ]


def remove_relation(project_id, parent_id):
    plan_project_id = model.ProjectPluginRelation.query.filter_by(project_id=project_id).first().plan_project_id
    project_relation = model.ProjectParentSonRelation.query.filter_by(parent_id=parent_id, son_id=project_id)
    if project_relation.first() is not None:
        redmine_lib.redmine.project.update(plan_project_id, parent_id="")
        project_relation.delete()
        db.session.commit()
