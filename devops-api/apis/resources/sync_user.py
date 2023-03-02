import model
import util

from collections import defaultdict
from flask_restful import Resource

import config
from resources.notification_message import (
    create_notification_message,
    get_unread_notification_message_list,
)
from resources.role import get_role_name
from model import db
from resources.project import get_projects_by_user
from nexus import nx_get_project_plugin_relation, nx_get_user_plugin_relation
from plugins.sonarqube import sonarqube_main as sonarqube
from accessories import redmine_lib
from resources import redmine, gitlab, logger


# 新建用戶預設密碼
DEFAULT_PASSWORD = config.get("ADMIN_INIT_PASSWORD")


class ResourceUsers(object):
    def __init__(self):
        self.all_users = defaultdict(list)

    # 取得 redmine, gitlab, harbor, k8s, sonarqube 個別所有使用者
    def set_all_members(self):
        for context in redmine_lib.redmine.user.all():
            self.all_users["rm_all_users"].append(context["login"])
            if hasattr(context, "email"):
                self.all_users["rm_all_users_email"].append(context["email"])

        for context in self.handle_gl_user_page():
            self.all_users["gl_all_users"].append(context["username"])
            self.all_users["gl_all_users_email"].append(context["email"])
            if context["state"] == "blocked":
                self.all_users["gl_all_blocked_users"].append(context["username"])

        self.all_users["hb_all_users"] = [context["username"] for context in self.handle_hb_user_page()]

    # 處理 gitlab list user api page 參數
    def handle_gl_user_page(self):
        gl_users = []
        page = 1
        x_total_pages = 10
        while page <= x_total_pages:
            params = {"page": page}
            output = gitlab.gitlab.gl_get_user_list(params)
            gl_users.extend(output.json())
            x_total_pages = int(output.headers["X-Total-Pages"])
            page += 1
        return gl_users

    # 處理 harbor list user api page 參數
    """
    def handle_hb_user_page(self):
        hb_users = []
        page = 1
        page_size = 10
        total_size = 20
        while total_size > 0:
            params = {"page": page, "page_size": page_size}
            output = harbor.hb_list_user(params)
            hb_users.extend(output.json())
            if output.headers.get("X-Total-Count", None):
                total_size = int(output.headers["X-Total-Count"]) - (page * page_size)
                page += 1
            else:
                total_size = -1
        return hb_users
    """

    # 處理 sonarqube list user api page 參數
    def handle_sq_user_page(self):
        sq_users = []
        page = 1
        page_size = 50
        total_size = 20
        while total_size > 0:
            params = {"p": page, "ps": page_size}
            output = sonarqube.sq_list_user(params).json()
            sq_users.extend(output["users"])
            total_size = int(output["paging"]["total"]) - (page * page_size)
            page += 1
        return sq_users


# rc_users = ResourceUsers()


# 設置 create user 需要的 args
def set_args(user_row):
    user_id = user_row.id
    role_id = model.ProjectUserRole.query.filter_by(project_id=-1, user_id=user_id).first().role_id
    args = {
        "id": user_id,
        "name": user_row.name,
        "email": user_row.email,
        "login": user_row.login,
        "role": role_id,
        "password": DEFAULT_PASSWORD,
        "is_admin": False,
        "from_ad": user_row.from_ad,
        "last_login": user_row.last_login,
    }
    return args


# def users_process(admin_users_id, all_users):
#     rc_users.set_all_members()
#     for user_row in all_users:
#         args = set_args(user_row)
#         if user_row.id in admin_users_id:
#             args['is_admin'] = True
#         check_rm_users(args, rc_users.all_users['rm_all_users'], rc_users.all_users['rm_all_users_email'])
#         check_gl_users(
#             args, rc_users.all_users['gl_all_users'], rc_users.all_users['gl_all_users_email'], rc_users.all_users['gl_all_blocked_users'])
#         check_hb_users(args, rc_users.all_users['hb_all_users'])
#         check_k8s_users(args, rc_users.all_users['k8s_all_users_sa'])
#         check_sq_users(args, rc_users.all_users['sq_all_users_login'])


# 檢查 user plugin relation table 有此 user_id 的資料，沒有的話則建立
def check_user_relation(nexus_user_id):
    user_relation = model.UserPluginRelation.query.filter_by(user_id=nexus_user_id).all()
    if not user_relation:
        logger.logger.info(f"User id {nexus_user_id} relation not exist, create new one.")
        new_user_relation = model.UserPluginRelation(user_id=nexus_user_id)
        model.db.session.add(new_user_relation)
        model.db.session.commit()
        user_relation = model.UserPluginRelation.query.filter_by(user_id=nexus_user_id).all()
    return user_relation[0]


def check_rm_users(args, rm_all_users, rm_all_users_email):
    # 如果帳號不存在，但是 email 已被使用的話，需要特別注意
    if args["login"] not in rm_all_users:
        if args["email"] in rm_all_users_email:
            logger.logger.info(
                f'Need attention: User {args["login"]} not found in redmine, \
                    but email {args["email"]} is used in redmin.'
            )
        if len(redmine_lib.redmine.user.filter(name=args["login"], status=3)) > 0:
            return f'User {args["login"]} is locked in redmine.'
        return f'User {args["login"]} not found in redmine.'


# Here if redmine is locked
def recreate_rm_users(args, rm_all_users, rm_all_users_email):
    login_name = args["login"]
    check_rm_user_res = check_rm_users(args, rm_all_users, rm_all_users_email)
    if check_rm_user_res == f'User {args["login"]} is locked in redmine.':
        logger.logger.info(f"Unlock User {login_name} in redmine.")
        user_relation = nx_get_user_plugin_relation(user_id=args["id"])
        redmine.redmine.rm_update_user_active(user_relation.plan_user_id, 1)
        logger.logger.info(f"Unlock User {login_name} done.")
    elif check_rm_user_res == f"User {login_name} not found in redmine.":
        logger.logger.info(f"User {login_name} not found in redmine.")
        logger.logger.info(f"Create {login_name} redmine user.")
        try:
            redmine_user = redmine.redmine.rm_create_user(args, args["password"], is_admin=args["is_admin"])
            args2 = {
                "alert_level": 1,
                "title": "Sync user recreate automation",
                "message": f"{args['name']}redmine account was recreate by system",
                "type_ids": [3],
                "type_parameters": {"user_ids": [args["id"]]},
            }
            create_notification_message(args2, user_id=args["id"])
            args3 = {
                "alert_level": 1,
                "title": "Sync user recreate automation",
                "message": f"{args['name']}redmine account was recreate by system",
                "type_ids": [4],
                "type_parameters": {"role_ids": [5]},
            }
            create_notification_message(args3, user_id=args["id"])
            redmine_user_id = redmine_user["user"]["id"]

            logger.logger.info("Add redmine user back into user's projects")
            for project in get_projects_by_user(args["id"]):
                project_relation = nx_get_project_plugin_relation(nexus_project_id=project["id"])

                from . import user

                redmine_role_id = user.to_redmine_role_id(args["role"])
                redmine.redmine.rm_create_memberships(
                    project_relation.plan_project_id, redmine_user_id, redmine_role_id
                )
            logger.logger.info("Add redmine user back into user's projects is done")
        except Exception as e:
            logger.logger.info(f"{login_name} redmine user create failed.")
            logger.logger.info(e)
            return

        logger.logger.info(f"Redmine user created, id={redmine_user_id}")
        logger.logger.info("Update user relation.")
        user_relation = check_user_relation(args["id"])
        user_relation.plan_user_id = redmine_user_id
        model.db.session.commit()
    # else:
    #     user_relation = nx_get_user_plugin_relation(user_id=args["id"])
    #     logger.logger.info(f"Change {login_name} redmine user's password to DEFAULT_PASSWORD.")
    #     redmine.redmine.rm_update_password(user_relation.plan_user_id, DEFAULT_PASSWORD)
    #     logger.logger.info(f"Change {login_name} redmine user's password to DEFAULT_PASSWORD done")


def check_gl_users(args, gl_all_users, gl_all_users_email, gl_all_blocked_users):
    if args["login"] in gl_all_blocked_users:
        return f'User {args["login"]} is blocked in gitlab.'
    # 如果帳號不存在，但是 email 已被使用的話，需要特別注意
    if args["login"] not in gl_all_users:
        if args["email"] in gl_all_users_email:
            logger.logger.info(
                f'Need attention: User {args["login"]} not found in gitlab, \
                but email {args["email"]} is used in gitlab.'
            )
        return f'User {args["login"]} not found in gitlab.'


def recreate_gl_users(args, gl_all_users, gl_all_users_email, gl_all_blocked_users):
    login_name = args["login"]
    check_gl_user_res = check_gl_users(args, gl_all_users, gl_all_users_email, gl_all_blocked_users)
    if check_gl_user_res == f'User {args["login"]} is blocked in gitlab.':
        logger.logger.info(f"Unblocked User {login_name} in gitlab.")
        user_relation = nx_get_user_plugin_relation(user_id=args["id"])
        gitlab.gitlab.gl_update_user_state(user_relation.repository_user_id, block_status=False)
        logger.logger.info(f"Unblocked User {login_name} done.")
    elif check_gl_user_res == f'User {args["login"]} not found in gitlab.':
        logger.logger.info(f"User {login_name} not found in gitlab.")
        logger.logger.info(f"Create {login_name} gitlab user.")
        try:
            gitlab_user = gitlab.gitlab.gl_create_user(args, args["password"], is_admin=args["is_admin"])
            args2 = {
                "alert_level": 1,
                "title": "Sync user recreate automation",
                "message": f"{args['name']} gitlab account was recreate by system",
                "type_ids": [3],
                "type_parameters": {"user_ids": [args["id"]]},
            }
            create_notification_message(args2, user_id=args["id"])
            args3 = {
                "alert_level": 1,
                "title": "Sync user recreate automation",
                "message": f"{args['name']} gitlab account was recreate by system",
                "type_ids": [4],
                "type_parameters": {"role_ids": [5]},
            }
            create_notification_message(args3, user_id=args["id"])
            gitlab_user_id = gitlab_user["id"]

            logger.logger.info("Add gitlab user back into user's projects")
            for project in get_projects_by_user(args["id"]):
                project_relation = nx_get_project_plugin_relation(nexus_project_id=project["id"])
                gitlab.gitlab.gl_project_add_member(project_relation.git_repository_id, gitlab_user_id)
            logger.logger.info("Add gitlab user back into user's projects is done")
        except Exception as e:
            logger.logger.info(f"{login_name} gitlab user create failed.")
            logger.logger.info(e)
            return

        logger.logger.info(f"Gitlab user created, id={gitlab_user_id}")
        logger.logger.info("Update user relation.")
        user_relation = check_user_relation(args["id"])
        user_relation.repository_user_id = gitlab_user_id
        model.db.session.commit()
    # else:
    #     user_relation = nx_get_user_plugin_relation(user_id=args["id"])
    #     logger.logger.info(f"Change {login_name} gitlab user's password to DEFAULT_PASSWORD.")
    #     gitlab.gitlab.gl_update_password(user_relation.repository_user_id, DEFAULT_PASSWORD)
    #     logger.logger.info(f"Change {login_name} gitlab user's password to DEFAULT_PASSWORD done")


"""
def check_hb_users(args, hb_all_users):
    if args["login"] not in hb_all_users:
        return f'User {args["login"]} not found in harbor.'
"""

'''
def recreate_hb_users(args, hb_all_users):
    """
    Recreate harbor instead of change origin accout's password is because
    update harbor password needs old_password.
    harbor.hb_update_user_password(harbor_user_id, new_pwd, old_pwd)
    """
    login_name = args["login"]
    if check_hb_users(args, hb_all_users) is not None:
        logger.logger.info(f"User {login_name} not found in harbor.")
        logger.logger.info(f"Create {login_name} harbor user.")
        try:
            harbor_user_id = harbor.hb_create_user(args, is_admin=args["is_admin"])
            args2 = {
                "alert_level": 1,
                "title": "Sync user recreate automation",
                "message": f"{args['name']} habor account was recreate by system",
                "type_ids": [3],
                "type_parameters": {"user_ids": [args["id"]]},
            }
            create_notification_message(args2, user_id=args["id"])
            args3 = {
                "alert_level": 1,
                "title": "Sync user recreate automation",
                "message": f"{args['name']} habor account was recreate by system",
                "type_ids": [4],
                "type_parameters": {"role_ids": [5]},
            }
            create_notification_message(args3, user_id=args["id"])
            logger.logger.info("Add harbor user back into user's projects")
            for project in get_projects_by_user(args["id"]):
                project_relation = nx_get_project_plugin_relation(nexus_project_id=project["id"])
                harbor.hb_add_member(project_relation.harbor_project_id, harbor_user_id)
            logger.logger.info("Add harbor user back into user's projects is done")
        except Exception as e:
            logger.logger.info(f"{login_name} harbor user create failed.")
            logger.logger.info(e)
            return

        logger.logger.info(f"Harbor user created, id={harbor_user_id}")
        logger.logger.info("Update user relation.")
        user_relation = check_user_relation(args["id"])
        user_relation.harbor_user_id = harbor_user_id
        model.db.session.commit()
    # else:
    #     logger.logger.info(f'ReCreate {login_name} harbor user.')
    #     user_relation = nx_get_user_plugin_relation(user_id=args["id"])
    #     harbor.hb_delete_user(user_relation.harbor_user_id)
'''


def check_k8s_users(args, k8s_all_users_sa):
    login_sa_name = util.encode_k8s_sa(args["login"])
    if login_sa_name not in k8s_all_users_sa:
        return f'User {args["login"]} k8s sa not found in k8s.'


def check_sq_users(args, sq_all_users_login):
    if args["login"] not in sq_all_users_login:
        return f'User {args["login"]} not found in sonarqube.'


def recreate_sq_users(args, sq_all_users_login):
    login_name = args["login"]
    if check_sq_users(args, sq_all_users_login) is not None:
        logger.logger.info(f"User {login_name} not found in sonarqube.")
        logger.logger.info(f"Create {login_name} sonarqube user.")
        try:
            sq_user = sonarqube.sq_create_user(args).json()
            args2 = {
                "alert_level": 1,
                "title": "Sync user recreate automation",
                "message": f"{args['name']} sonarqube account was recreate by system",
                "type_ids": [3],
                "type_parameters": {"user_ids": [args["id"]]},
            }
            create_notification_message(args2, user_id=args["id"])
            args3 = {
                "alert_level": 1,
                "title": "Sync user recreate automation",
                "message": f"{args['name']} sonarqube account was recreate by system",
                "type_ids": [4],
                "type_parameters": {"role_ids": [5]},
            }
            create_notification_message(args3, user_id=args["id"])
            logger.logger.info("Add sonarqube user back into user's projects")
            for project in get_projects_by_user(args["id"]):
                sonarqube.sq_add_member(project["name"], login_name)
            logger.logger.info("Add sonarqube user back into user's projects is done")
        except Exception as e:
            logger.logger.info(f"{login_name} sonarqube user create failed.")
            logger.logger.info(e)
            return
        logger.logger.info(f'Sonarqube user created, login={sq_user["login"]}')
    # else:
    #     logger.logger.info(f"Change {login_name} sonarqube user's password to DEFAULT_PASSWORD.")
    #     sonarqube.sq_update_password(login_name, DEFAULT_PASSWORD)
    #     logger.logger.info(f"Change {login_name} sonarqube user's password to DEFAULT_PASSWORD done")


def check_user_exist(router=None, all=False):
    lost_user_infos = {}
    rc_users = ResourceUsers()

    def record_miss_user(args, soft_name, error_message):
        if args["login"] not in lost_user_infos:
            # In case it have duplicate users, so use id as key.
            lost_user_infos[args["id"]] = {
                "login": args["login"],
                "Redmine": "",
                "GitLab": "",
                # "Harbor": "",
                "SonarQube": "",
                "K8s": "",
                "role": get_role_name(args["role"]),
                "from_ad": args["from_ad"],
                "last_login": args["last_login"],
            }
        lost_user_infos[args["id"]][soft_name] = error_message

    # Check missing users without project_bot's users
    rc_users.set_all_members()

    for user in model.User.query.filter(~model.User.login.like("project_bot%")):
        disabled = False
        args = set_args(user)
        for service, error_message in {
            "SonarQube": check_sq_users(args, rc_users.all_users["sq_all_users_login"]),
            "GitLab": check_gl_users(
                args,
                rc_users.all_users["gl_all_users"],
                rc_users.all_users["gl_all_users_email"],
                rc_users.all_users["gl_all_blocked_users"],
            ),
            "Redmine": check_rm_users(
                args,
                rc_users.all_users["rm_all_users"],
                rc_users.all_users["rm_all_users_email"],
            ),
        }.items():
            if error_message is not None:
                record_miss_user(args, service, error_message)
                disabled = True
        if not all:
            user.disabled = disabled
            db.session.commit()

    # Process data
    ret = []
    notification_message_list = []
    for user_id, info in lost_user_infos.items():
        # result part
        temp_dict = {"id": user_id}
        temp_dict.update(info)
        ret.append(temp_dict)

        # notification part
        missing_servers = [
            server for server in ["Redmine", "GitLab", "Harbor", "SonarQube", "K8s"] if info[server] != ""
        ]
        msg = f"**{info['login']}** 用戶的帳號在 {' , '.join(missing_servers) } 出現異常"

        if not all:
            notification_message_list.append(f"**{info['login']}** 用戶的帳號在 {' , '.join(missing_servers) } 出現異常")
        else:
            logger.logger.info(f"**{info['login']}** 用戶的帳號在 {' , '.join(missing_servers) } 出現異常")

    # only send notification when the previous waring is read
    if get_unread_notification_message_list(title="帳號檢測異常通知") == [] and not all:
        notification_message = "\n".join(notification_message_list)
        notification_message += f"\n{router}"
        args = {
            "alert_level": 2,
            "title": "帳號檢測異常通知",
            "message": notification_message,
            "type_ids": [4],
            "type_parameters": {"role_ids": [5]},
        }
        create_notification_message(args, user_id=1)

    return ret


def recreate_user(user_id, all=False):
    user = model.User.query.get(user_id)
    args = set_args(user)
    rc_users = ResourceUsers()
    rc_users.set_all_members()

    logger.logger.info("SonarQube user start.")
    recreate_sq_users(args, rc_users.all_users["sq_all_users_login"])
    logger.logger.info("Gitlab user start.")
    recreate_gl_users(
        args,
        rc_users.all_users["gl_all_users"],
        rc_users.all_users["gl_all_users_email"],
        rc_users.all_users["gl_all_blocked_users"],
    )
    logger.logger.info("Redmine user start.")
    recreate_rm_users(
        args,
        rc_users.all_users["rm_all_users"],
        rc_users.all_users["rm_all_users_email"],
    )

    user = model.User.query.get(user_id)
    if not all and args["role"] != 5:
        user.disabled = True
        db.session.commit()
    logger.logger.info("All done.")


def recreate_users():
    missing_users = check_user_exist(all=True)
    for missing_user in missing_users:
        logger.logger.info(f'Start recreating user: {missing_user["login"]}.')
        recreate_user(missing_user["id"], all=True)


# def main_process():
#     # 取得 admin users id list
#     admin_users_id = list(sum(model.db.session.query(model.User).join(model.ProjectUserRole).filter(
#         model.ProjectUserRole.project_id == -1, model.ProjectUserRole.role_id == 5).with_entities(model.User.id), ()))
#     # 取得 all_users obj，除了 BOT 以外
#     all_users = model.db.session.query(model.User).join(model.ProjectUserRole).filter(
#         model.ProjectUserRole.project_id == -1, model.ProjectUserRole.role_id != 6)
#     logger.logger.info('Users process start.')
#     users_process(admin_users_id, all_users)
#     logger.logger.info('All done.')

# class SyncUser(Resource):
#     def get(self):
#         main_process()
#         return util.success()
