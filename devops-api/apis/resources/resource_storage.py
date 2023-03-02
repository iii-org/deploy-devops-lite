from model import ProjectResourceStoragelevel
from model import db


DEFAULT_RESOURCE_STORAGE_INFO = {"gitlab": {"limit": 0.8, "comparison": ">", "percentage": False}}


def row_to_dict(row):
    if row is None:
        return {}
    return {key: getattr(row, key) for key in type(row).__table__.columns.keys()}


def compare_operator(comparison, used, limit, max, percentage=False):
    if percentage:
        used = max * used / 100

    if comparison == "<":
        return used < limit
    elif comparison == "<=":
        return used <= limit
    elif comparison == ">":
        return used > limit
    elif comparison == ">=":
        return used >= limit


def get_project_resource_storage_level(project_id):
    row = row_to_dict(ProjectResourceStoragelevel.query.filter_by(project_id=project_id).first())
    for resource, info in DEFAULT_RESOURCE_STORAGE_INFO.items():
        if row.get(resource) is None:
            row[resource] = info

    return row


def update_project_resource_storage_level(project_id, args):
    project_res_sto = ProjectResourceStoragelevel.query.filter_by(project_id=project_id).first()
    if project_res_sto is not None:
        if args.get("gitlab") is not None:
            project_res_sto.gitlab = args["gitlab"]

    else:
        row = ProjectResourceStoragelevel(
            project_id=project_id,
            gitlab=args.get("gitlab") or DEFAULT_RESOURCE_STORAGE_INFO["gitlab"],
        )
        db.session.add(row)

    db.session.commit()
