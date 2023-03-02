import os
import util
from model import db, UIRouteData
from datetime import datetime
import copy


UI_ROUTE_FOLDER_NAME = "apis/ui_routes"


def insert_into_ui_route_table(ui_route_dict, parent_name, old_brother_name):
    if "meta" in ui_route_dict and "roles" in ui_route_dict["meta"]:
        role = ui_route_dict["meta"]["roles"][0]
    else:
        role = ""
    parent_id = 0
    if parent_name != "":
        parent_row = UIRouteData.query.filter_by(name=parent_name, role=role).first()
        parent_id = parent_row.id if parent_row else 0
    old_brother_id = 0
    if old_brother_name != "":
        old_brother_row = UIRouteData.query.filter_by(name=old_brother_name, role=role).first()
        old_brother_id = old_brother_row.id if old_brother_row else 0
    num = UIRouteData.query.filter_by(name=ui_route_dict["name"], role=role).count()
    if num == 0:
        new_ui_route = copy.deepcopy(ui_route_dict)
        if "children" in new_ui_route:
            del new_ui_route["children"]
        new_row = UIRouteData(
            name=ui_route_dict["name"],
            role=role,
            parent=parent_id,
            old_brother=old_brother_id,
            ui_route=new_ui_route,
            created_at=datetime.utcnow(),
            updated_at=datetime.utcnow(),
        )
        db.session.add(new_row)
        db.session.commit()
    if "children" in ui_route_dict:
        j = 0
        while j < len(ui_route_dict["children"]):
            old_brother_name = "" if j == 0 else ui_route_dict["children"][j - 1]["name"]
            insert_into_ui_route_table(ui_route_dict["children"][j], ui_route_dict["name"], old_brother_name)
            j += 1


def ui_route_first_version():
    for ui_route_file_name in next(os.walk(UI_ROUTE_FOLDER_NAME))[2]:
        if ui_route_file_name[-5:] == ".json":
            ui_route_dicts = util.read_json_file(f"{UI_ROUTE_FOLDER_NAME}/{ui_route_file_name}")
            i = 0
            while i < len(ui_route_dicts):
                old_brother_name = "" if i == 0 else ui_route_dicts[i - 1]["name"]
                insert_into_ui_route_table(ui_route_dicts[i], "", old_brother_name)
                i += 1


# get parent_id
def get_ui_route_id(role, ui_route_name):
    if ui_route_name == "":
        return 0
    else:
        row = UIRouteData.query.filter_by(role=role, name=ui_route_name).first()
        if row:
            return row.id
        else:
            print("could not find parent or old_brother")


def get_ui_route_by_parent_and_old_bro_id(role, parent_id, old_brother_id):
    row = UIRouteData.query.filter_by(role=role, parent=parent_id, old_brother=old_brother_id).first()
    if row:
        return row
    return None


def get_young_brother_id(role, name):
    row = UIRouteData.query.filter_by(role=role, name=name).first()
    if row:
        young_row = UIRouteData.query.filter_by(role=role, old_brother=row.id).first()
        if young_row:
            return young_row
    return None


def create_ui_route_object(name, role, ui_route_json, parent_name, old_brother_name):
    # check existing route
    row = UIRouteData.query.filter_by(role=role, name=name).first()
    if row:
        return
    # create a new route ob
    parent_id = get_ui_route_id(role, parent_name)
    old_brother_id = get_ui_route_id(role, old_brother_name)
    origin_ui_route = get_ui_route_by_parent_and_old_bro_id(role, parent_id, old_brother_id)
    if old_brother_id == 0:
        # insert into the first
        new = UIRouteData(
            name=name,
            role=role,
            parent=parent_id,
            old_brother=0,
            ui_route=ui_route_json,
            created_at=datetime.utcnow(),
            updated_at=datetime.utcnow(),
        )
        db.session.add(new)
        db.session.commit()
        if origin_ui_route:
            origin_ui_route.old_brother = new.id
            origin_ui_route.updated_at = datetime.utcnow()
            db.session.commit()
    elif origin_ui_route is None:
        # insert into the last
        new = UIRouteData(
            name=name,
            role=role,
            parent=parent_id,
            old_brother=old_brother_id,
            ui_route=ui_route_json,
            created_at=datetime.utcnow(),
            updated_at=datetime.utcnow(),
        )
        db.session.add(new)
        db.session.commit()
    else:
        # insert into the middle
        new = UIRouteData(
            name=name,
            role=role,
            parent=parent_id,
            old_brother=old_brother_id,
            ui_route=ui_route_json,
            created_at=datetime.utcnow(),
            updated_at=datetime.utcnow(),
        )
        db.session.add(new)
        db.session.commit()
        origin_ui_route.old_brother = new.id
        origin_ui_route.updated_at = datetime.utcnow()
        db.session.commit()


def adjust_ui_router_order(role, target_name, moved_name):
    def find_after_route_obj(route_name):
        target = UIRouteData.query.filter_by(name=route_name, role=role).first()
        if target is None:
            return None, None
        target_id = target.id
        return target, UIRouteData.query.filter_by(old_brother=target_id).first()

    target_obj, after_target_obj = find_after_route_obj(target_name)
    moved_obj, after_moved_obj = find_after_route_obj(moved_name)

    if moved_obj is None or target_obj is None or after_target_obj is None:
        return
    before_moved_obj_id = None if after_moved_obj is None else moved_obj.old_borther

    moved_obj.old_brother = target_obj.id
    db.session.commit()
    after_target_obj.old_brother = moved_obj.id
    db.session.commit()

    if before_moved_obj_id is not None:
        after_moved_obj.old_brother = before_moved_obj_id
        db.session.commit()


def put_ui_route_object(name, role, ui_route_json, parent_name=None, old_brother_name=None):
    # update the route object
    if parent_name is not None or old_brother_name is not None:
        delete_ui_route_object(name, role)
        create_ui_route_object(name, role, ui_route_json, parent_name, old_brother_name)
    else:
        route_row = UIRouteData.query.filter_by(role=role, name=name).first()
        route_row.ui_route = ui_route_json
        route_row.updated_at = datetime.utcnow()
        db.session.commit()


# delete the old route object
def delete_ui_route_object(name, role):
    route_row = UIRouteData.query.filter_by(role=role, name=name).first()
    old_brother_id = route_row.old_brother
    young_brother = get_young_brother_id(role, name)
    # check ui_route has children or not, if exists, then delete it.
    chile_route_rows = UIRouteData.query.filter_by(role=role, parent=route_row.id).all()
    if len(chile_route_rows) > 0:
        for chile_route_row in chile_route_rows:
            delete_ui_route_object(chile_route_row.name, role)

    db.session.delete(route_row)
    db.session.commit()
    if old_brother_id == 0:
        # on the first
        if young_brother:
            young_brother.old_brother = 0
            young_brother.updated_at = datetime.utcnow()
            db.session.commit()
    elif young_brother is None:
        # on the last
        pass
    else:
        # insert into the middle
        young_brother.old_brother = old_brother_id
        young_brother.updated_at = datetime.utcnow()
        db.session.commit()


def rename_ui_route(old_name, new_name, role):
    route_row = UIRouteData.query.filter_by(role=role, name=old_name).first()
    if route_row:
        route_row.name = new_name
        route_dict = dict(route_row.ui_route)
        route_dict["name"] = new_name
        route_row.ui_route = route_dict
        db.session.commit()
