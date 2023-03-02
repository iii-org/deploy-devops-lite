from flask_jwt_extended import get_jwt_identity
from flask_socketio import emit
from sqlalchemy.sql import and_, or_
from sqlalchemy import desc
from datetime import datetime, timedelta
from time import strptime, mktime
import json
import util
from resources import role
from model import (
    UserMessageType,
    db,
    NotificationMessage,
    NotificationMessageReply,
    NotificationMessageRecipient,
    ProjectUserRole,
    User,
    SystemParameter,
    Project,
)
from resources.mail import Mail


"""
websocket parameters:
{"user_id"=234}

https://github.com/iii-org/devops-system/wiki/Notification-Message
"""


class AlertLevel:
    def __init__(self, id_, name, users_can_read):
        self.id = id_
        self.name = name
        self.users_can_read = users_can_read


INF = AlertLevel(1, "INFO", True)
WAR = AlertLevel(2, "WARNING", True)
URG = AlertLevel(3, "Urgent", True)

# System
NEW = AlertLevel(101, "New Version", False)
SAL = AlertLevel(102, "System Alert", False)
SWA = AlertLevel(103, "System Warming", True)

# GitLab
MR = AlertLevel(201, "Merge Request", True)

# GitHub
GHT = AlertLevel(301, "GitHub Token Invalid", False)

ALL_ALERTS = [INF, WAR, URG, NEW, SAL, SWA, MR, GHT]


def get_alert_level(alert_id):
    for alert in ALL_ALERTS:
        if alert.id == alert_id:
            return {"id": alert.id, "name": alert.name}
    return "Unknown Alert"


def get_users_can_read(alert_id):
    for alert in ALL_ALERTS:
        if alert.id == alert_id:
            return alert.users_can_read


def check_message_exist(message_key, alert_level):
    count = (
        NotificationMessage.query.filter(NotificationMessage.alert_level == alert_level)
        .filter(NotificationMessage.message.like(f"%{message_key}%"))
        .filter(NotificationMessage.title.like(f"%{message_key}%"))
        .count()
    )
    if count > 0:
        return True
    else:
        return False


def clear_has_expired_notifications_message(name, units, value_key):
    db.session.query(SystemParameter).filter_by(name=name).update({"value": {value_key: units}})
    db.session.commit()

    NotificationMessage.query.filter(
        util.get_few_months_ago_utc_datetime(units, value_key) > NotificationMessage.created_at
    ).delete()
    db.session.commit()


def combine_message_and_recipient(rows):
    out_dict = {}
    for row in rows:
        if row[1] is not None:
            if row[0].id not in out_dict:
                out_dict[row[0].id] = {
                    **json.loads(str(row[0])),
                    **{"types": [json.loads(str(row[1]))]},
                }
            else:
                out_dict[row[0].id]["types"].append(json.loads(str(row[1])))
            if row[0].alert_level:
                out_dict[row[0].id]["alert_level"] = get_alert_level(row[0].alert_level)
                out_dict[row[0].id]["users_can_read"] = get_users_can_read(row[0].alert_level)
            if row[0].creator_id:
                from resources.user import NexusUser

                out_dict[row[0].id]["creator"] = NexusUser().set_user_id(row[0].creator_id).to_json()
            out_dict[row[0].id].pop("creator_id", None)
            if len(row) > 2:
                if row[2] is not None:
                    out_dict[row[0].id]["read"] = True
                else:
                    out_dict[row[0].id]["read"] = False
            if row[0].created_at:
                convert_datetime = out_dict[row[0].id]["created_at"].split(".")[0]
                out_dict[row[0].id]["created_at"] = datetime.strptime(convert_datetime, "%Y-%m-%d %H:%M:%S").isoformat()
            if row[0].updated_at:
                convert_datetime = out_dict[row[0].id]["updated_at"].split(".")[0]
                out_dict[row[0].id]["updated_at"] = datetime.strptime(convert_datetime, "%Y-%m-%d %H:%M:%S").isoformat()
    return list(out_dict.values())


def count_must_receiver_number(out):
    for item in out:
        user_ids = set()
        for type in item.get("types"):
            if type["type_id"] == 1:
                user_ids = user_ids | set(
                    db.session.query(ProjectUserRole.user_id)
                    .filter(
                        ProjectUserRole.project_id == -1,
                        ProjectUserRole.role_id != role.BOT.id,
                    )
                    .all()
                )
            if type["type_id"] == 2:
                for type_project_id in type.get("type_parameter").get("project_ids"):
                    user_ids = user_ids | set(
                        db.session.query(ProjectUserRole.user_id)
                        .filter(
                            ProjectUserRole.project_id == type_project_id,
                            ProjectUserRole.role_id != role.BOT.id,
                        )
                        .all()
                    )
            if type["type_id"] == 3:
                user_ids = user_ids | set(type.get("type_parameter").get("user_ids"))
            if type["type_id"] == 4:
                for type_role_id in type.get("type_parameter").get("role_ids"):
                    user_ids = user_ids | set(
                        db.session.query(ProjectUserRole.user_id)
                        .filter(
                            ProjectUserRole.project_id == -1,
                            ProjectUserRole.role_id == type_role_id,
                        )
                        .group_by(ProjectUserRole.user_id)
                        .all()
                    )
            if type["type_id"] == 5:
                for type_project_id in type.get("type_parameter").get("project_ids"):
                    user_ids = user_ids | set(db.session.query(Project.owner_id).filter_by(id=type_project_id).first())
        item["total_receive_number"] = len(user_ids)
        item["already_receive_number"] = NotificationMessageReply.query.filter_by(message_id=item["id"]).count()
    return out


def filter_by_user(rows, user_id, role_id=None):
    project_ids = (
        db.session.query(ProjectUserRole.project_id)
        .filter(and_(ProjectUserRole.user_id == user_id, ProjectUserRole.project_id != -1))
        .all()
    )

    out_list = []
    for row in rows:
        if row[1] is not None:
            if row[1].type_id == 1 and row not in out_list:
                out_list.append(row)
            if row[1].type_id == 2:
                for type_project_id in row[1].type_parameter["project_ids"]:
                    if (type_project_id,) in project_ids and row not in out_list:
                        out_list.append(row)
            if row[1].type_id == 3:
                for type_user_id in row[1].type_parameter["user_ids"]:
                    if type_user_id == user_id and row not in out_list:
                        out_list.append(row)
            if role_id and row[1].type_id == 4:
                for type_role_id in row[1].type_parameter["role_ids"]:
                    if type_role_id == role_id and row not in out_list:
                        out_list.append(row)
            if row[1].type_id == 5:
                for type_project_id in row[1].type_parameter["project_ids"]:
                    pj_row = Project.query.filter_by(id=type_project_id).first()
                    if pj_row.owner_id == user_id:
                        out_list.append(row)
    return out_list


def get_notification_message_list(args, admin=False):
    out = []
    page_dict = None
    base_query = db.session.query(
        NotificationMessage,
        NotificationMessageRecipient,
        NotificationMessageReply,
        User,
    ).outerjoin(
        NotificationMessageReply,
        and_(
            NotificationMessageReply.user_id == get_jwt_identity()["user_id"],
            NotificationMessage.id == NotificationMessageReply.message_id,
        ),
    )
    base_query = base_query.outerjoin(
        NotificationMessageRecipient,
        NotificationMessageRecipient.message_id == NotificationMessage.id,
    )
    base_query = base_query.join(User, NotificationMessage.creator_id == User.id)
    if args.get("search") is not None:
        base_query = base_query.filter(
            or_(
                NotificationMessage.title.ilike(f'%{args.get("search")}%'),
                User.name.ilike(f'%{args.get("search")}%'),
            )
        )
    a_from_date = args["from_date"]
    a_to_date = args["to_date"]
    if a_from_date is not None:
        from_date = datetime.fromtimestamp(mktime(strptime(a_from_date, "%Y-%m-%d")))
        base_query = base_query.filter(NotificationMessage.created_at >= from_date)
    if a_to_date is not None:
        to_date = datetime.fromtimestamp(mktime(strptime(a_to_date, "%Y-%m-%d")))
        to_date += timedelta(days=1)
        base_query = base_query.filter(NotificationMessage.created_at < to_date)
    if args.get("alert_ids") is not None:
        base_query = base_query.filter(NotificationMessage.alert_level.in_(args.get("alert_ids")))
    if args.get("unread"):
        base_query = base_query.filter(NotificationMessageReply.user_id == None)
    if admin and args.get("include_system_message") is not True:
        base_query = base_query.filter(NotificationMessage.alert_level <= 100)
    rows = base_query.order_by(desc(NotificationMessage.id)).all()

    if admin is False:
        rows = filter_by_user(rows, get_jwt_identity()["user_id"], get_jwt_identity()["role_id"])
    out = combine_message_and_recipient(rows)
    if admin:
        out = count_must_receiver_number(out)
    # print(out)
    out, page_dict = util.list_pagination(out, args["limit"], args["offset"])
    out_dict = {"notification_message_list": out}

    if page_dict:
        out_dict["page"] = page_dict
    return out_dict


def create_notification_message(args, user_id=None):
    if user_id is None:
        user_id = get_jwt_identity()["user_id"]
    # Do not need to create same notification message if previous one is on read and alert level is 102 or 301
    if args["alert_level"] in [102, 301] and get_unread_notification_message_list(title=args["title"]) != []:
        return
    row = NotificationMessage(
        alert_level=args["alert_level"],
        title=args["title"],
        alert_service_id=args.get("alert_service_id", 0),
        message_parameter=args.get("message_parameter"),
        message=args["message"],
        creator_id=user_id,
        created_at=datetime.utcnow(),
        updated_at=datetime.utcnow(),
        close=False,
    )
    db.session.add(row)
    db.session.commit()
    message_id = row.id
    for type_id in args["type_ids"]:
        row_recipient = NotificationMessageRecipient(
            message_id=message_id,
            type_id=type_id,
            type_parameter=args["type_parameters"],
        )
        db.session.add(row_recipient)
    db.session.commit()
    notification_room.send_message_to_all(row.id)


def close_notification_message(message_id):
    for user_id, v in choose_send_to_who(message_id, send_message_id=True).items():
        if NotificationMessageReply.query.filter_by(message_id=message_id, user_id=user_id).first() is None:
            args = {"message_ids": [message_id]}
            create_notification_message_reply_slip(user_id, args)
    row = NotificationMessage.query.filter_by(id=message_id).first()
    row.close = True
    db.session.commit()


def delete_notification_message(message_id):
    out_dict = choose_send_to_who(message_id, send_message_id=True)
    for k, v in out_dict.items():
        emit(
            "delete_message",
            v,
            namespace="/v2/get_notification_message",
            to=f"user/{k}",
        )

    row = NotificationMessage.query.filter_by(id=message_id).first()
    db.session.delete(row)
    db.session.commit()


def create_notification_message_reply_slip(user_id, args):
    row_list = []
    for message_id in args["message_ids"]:
        row = NotificationMessageReply(
            message_id=message_id,
            user_id=user_id,
            created_at=datetime.utcnow(),
        )
        row_list.append(row)
    db.session.add_all(row_list)
    db.session.commit()
    for message_id in args["message_ids"]:
        emit(
            "read_message",
            message_id,
            namespace="/v2/get_notification_message",
            to=f"user/{user_id}",
        )


def choose_send_to_who(message_id, send_message_id=None):
    # out_dict: {user_id: message}
    out_dict = {}
    message_rows = (
        db.session.query(NotificationMessage, NotificationMessageRecipient)
        .join(
            NotificationMessageRecipient,
            and_(
                NotificationMessage.id == message_id,
                NotificationMessage.id == NotificationMessageRecipient.message_id,
            ),
        )
        .all()
    )

    for message_row in message_rows:
        if message_row[1].type_id == 1:
            # Send message to all
            for user_row in User.query.all():
                if user_row not in out_dict:
                    if send_message_id:
                        out_dict[user_row.id] = message_id
                    else:
                        out_dict[user_row.id] = json.loads(str(message_row[0]))
        elif message_row[1].type_id == 2:
            for project_id in message_row[1].type_parameter["project_ids"]:
                # Send message to user in project
                for user_row in ProjectUserRole.query.filter_by(project_id=project_id).all():
                    if user_row.user_id not in out_dict:
                        if send_message_id:
                            out_dict[user_row.user_id] = message_id
                        else:
                            out_dict[user_row.user_id] = json.loads(str(message_row[0]))
        elif message_row[1].type_id == 3:
            # Send message to the user
            for user_id in message_row[1].type_parameter["user_ids"]:
                if user_id not in out_dict:
                    if send_message_id:
                        out_dict[user_id] = message_id
                    else:
                        out_dict[user_id] = json.loads(str(message_row[0]))
        elif message_row[1].type_id == 4:
            # Send message to same role account
            for role_id in message_row[1].type_parameter["role_ids"]:
                for user_row in ProjectUserRole.query.filter_by(role_id=role_id, project_id=-1).all():
                    if user_row.user_id not in out_dict:
                        if send_message_id:
                            out_dict[user_row.user_id] = message_id
                        else:
                            out_dict[user_row.user_id] = json.loads(str(message_row[0]))
        elif message_row[1].type_id == 5:
            for project_id in message_row[1].type_parameter["project_ids"]:
                # Send message to project owner
                pj_row = Project.query.filter_by(id=project_id).first()
                if send_message_id:
                    out_dict[pj_row.owner_id] = message_id
                else:
                    out_dict[pj_row.owner_id] = json.loads(str(message_row[0]))
    return out_dict


def get_unread_notification_message_list(title=None, alert_service_id=None):
    from resources.user import get_am_role_user

    base_query = db.session.query(NotificationMessage, NotificationMessageReply).outerjoin(
        NotificationMessageReply,
        and_(
            NotificationMessageReply.user_id.in_(get_am_role_user()),
            NotificationMessage.id == NotificationMessageReply.message_id,
        ),
    )
    base_query = base_query.filter(NotificationMessage.close == False)
    if alert_service_id is not None:
        base_query = base_query.filter(NotificationMessage.alert_service_id == alert_service_id)
    if title is not None:
        base_query = base_query.filter(NotificationMessage.title == title)
    rows = base_query.order_by(desc(NotificationMessage.id)).all()
    return [{**json.loads(str(row[0]))} for row in rows if len(row) > 1 and row[1] is None]


def get_unclose_notification_message(alert_service_id):
    rows = (
        NotificationMessage.query.filter_by(alert_level=102, alert_service_id=alert_service_id, close=False)
        .order_by(desc(NotificationMessage.id))
        .all()
    )
    return [json.loads(str(row)) for row in rows]


def send_mail(user_id, title, message):
    user_objs = (
        db.session.query(UserMessageType, User)
        .join(User, UserMessageType.user_id == User.id)
        .filter(UserMessageType.user_id == user_id)
    )
    for user_obj in user_objs:
        user, user_message_type = user_obj.User, user_obj.UserMessageType
        if user_message_type is not None and user_message_type.mail:
            receiver = user.email
            Mail().send_email(receiver, title, message)


def get_notification_is_open(user_id, message_id):
    from resources.user import get_user_message_type

    is_not_open = get_user_message_type(user_id).get("notification", True) is False
    if is_not_open:
        args = {"message_ids": [message_id]}
        create_notification_message_reply_slip(user_id, args)
        if len(choose_send_to_who(message_id)) <= 1:
            row = NotificationMessage.query.filter_by(id=message_id).first()
            row.close = True
            db.session.commit()

    return not is_not_open


class NotificationRoom(object):
    def send_message_to_all(self, message_id):
        out_dict = choose_send_to_who(message_id)
        for k, v in out_dict.items():
            v["users_can_read"] = get_users_can_read(v["alert_level"])
            v["alert_level"] = get_alert_level(v["alert_level"])
            if "creator_id" in v:
                from resources.user import NexusUser

                v["creator"] = NexusUser().set_user_id(v["creator_id"]).to_json()
            v.pop("creator_id", None)
            send_mail(k, v["title"], v["message"])
            if get_notification_is_open(k, message_id):
                emit(
                    "create_message",
                    v,
                    namespace="/v2/get_notification_message",
                    to=f"user/{k}",
                )

    def get_message(self, data):
        rows = (
            db.session.query(NotificationMessage, NotificationMessageRecipient)
            .outerjoin(
                NotificationMessageReply,
                and_(
                    NotificationMessageReply.user_id == data["user_id"],
                    NotificationMessage.id == NotificationMessageReply.message_id,
                ),
            )
            .filter(NotificationMessageReply.message_id == None)
        )

        rows = rows.outerjoin(
            NotificationMessageRecipient,
            NotificationMessageRecipient.message_id == NotificationMessage.id,
        ).all()
        pur_row = ProjectUserRole.query.filter_by(user_id=data["user_id"]).first()
        rows = filter_by_user(rows, data["user_id"], pur_row.role_id)
        message_list = combine_message_and_recipient(rows)
        for message in message_list:
            emit(
                "create_message",
                message,
                namespace="/v2/get_notification_message",
                to=f"user/{data['user_id']}",
            )


notification_room = NotificationRoom()
