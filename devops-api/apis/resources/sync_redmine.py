import os
import model
import threading
import util
from . import role
from sqlalchemy import func
from operator import itemgetter
from resources.project import get_project_list
from resources.user import user_list_by_project
from resources.issue import get_issue_by_project
from datetime import datetime
from decimal import Decimal, ROUND_HALF_UP
from flask_jwt_extended import jwt_required, get_jwt_identity
from flask_restful import Resource, reqparse
from model import db, Lock
from sqlalchemy.exc import IntegrityError
from resources import logger
import resources.apiError as apiError


STATUS_IN_PROGRESS = "in_progress"
STATUS_NOT_STARTED = "not_started"
STATUS_OVERDUE = "overdue"
STATUS_CLOSED = "closed"

# Get admin account from environment
admin_account = os.environ.get("ADMIN_INIT_LOGIN")
if not admin_account:
    admin_account = "sysadmin"


# --------------------- Useful Functions ---------------------


def round_off_float(num):
    if isinstance(num, float):
        num = str(num)
    return float(Decimal(num).quantize(Decimal("0.000"), rounding=ROUND_HALF_UP))


def calculate_expired_days(last):
    first_date = datetime.utcnow().date()
    last_date = datetime.strptime(last, "%Y-%m-%d").date()
    expired_days = (last_date - first_date).days
    return expired_days


def get_complete_percent(project):
    complete_percent = 0.0
    if project["closed_count"] and project["total_count"]:
        complete_percent = round_off_float(project["closed_count"] / project["total_count"])
    return complete_percent


def get_expired_days(project):
    if project["due_date"] is not None:
        return calculate_expired_days(project["due_date"])
    else:
        return None


def check_overdue(last):
    if last is not None:
        last_date = datetime.strptime(last, "%Y-%m-%d")
        if last_date < datetime.utcnow():
            return True
        else:
            return False
    else:
        return None


def get_passing_rate(total, fail):
    passing_rate = 0.0
    try:
        passing_rate = round_off_float(1 - (fail / total))
    except ZeroDivisionError:
        pass
    return passing_rate


def get_admin_user_id():
    user_detail = model.User.query.filter_by(login=admin_account).first()
    return user_detail.id


def clear_all_tables():
    model.RedmineIssue.query.delete()
    model.ProjectMember.query.delete()
    model.ProjectMemberCount.query.delete()
    model.db.session.commit()


# --------------------- Sync Redmine ---------------------


def sync_redmine(sync_date):
    need_to_track_issue = []
    all_projects = get_project_list(user_id=get_admin_user_id(), role="pm", sync=True)
    if all_projects:
        for project in all_projects:
            project_status = project["project_status"]
            if project_status == STATUS_IN_PROGRESS:
                need_to_track_issue.append(project["id"])
            if check_overdue(project["due_date"]) and project_status != STATUS_CLOSED:
                project_status = STATUS_OVERDUE
            member_count = insert_project_member(project["id"], project["display"])
            insert_project(project, member_count, sync_date, project_status)
            insert_project_member_count(project, member_count)
    return need_to_track_issue


def insert_project(project, member_count, sync_date, project_status):
    new_data = {
        "project_id": project["id"],
        "project_name": project["display"],
        "owner_id": project["owner_id"],
        "owner_login": model.User.query.get(project["owner_id"]).login,
        "owner_name": project["owner_name"],
        "complete_percent": get_complete_percent(project),
        "closed_issue_count": project["closed_count"],
        "unclosed_issue_count": project["total_count"] - project["closed_count"],
        "total_issue_count": project["total_count"],
        "member_count": member_count,
        "expired_day": get_expired_days(project),
        "start_date": project.get("start_date"),
        "end_date": project.get("due_date"),
        "sync_date": sync_date,
        "project_status": project_status,
    }
    new_project = model.RedmineProject(**new_data)
    exist_data = model.RedmineProject.query.filter(model.RedmineProject.project_id == project["id"]).first()
    if exist_data is not None:
        model.RedmineProject.query.filter_by(id=exist_data.id).update(new_data)
    else:
        model.db.session.add(new_project)
    model.db.session.commit()


def insert_project_member_count(project, member_count):
    new_project_member = model.ProjectMemberCount(
        project_id=project["id"],
        project_name=project["display"],
        member_count=member_count,
    )
    model.db.session.add(new_project_member)
    model.db.session.commit()


def insert_project_member(project_id, project_name):
    members_list = []
    all_members = user_list_by_project(project_id=project_id, args={"exclude": None})
    for member in all_members:
        if int(member["role_id"]) in [role.ADMIN.id, role.QA.id]:
            continue
        new_member = model.ProjectMember(
            user_id=member["id"],
            user_name=member["name"],
            project_id=project_id,
            project_name=project_name,
            role_id=member["role_id"],
            role_name=member["role_name"],
            department=member["department"] if member["department"] else "",
            title=member["title"] if member["title"] else "",
        )
        members_list.append(new_member)
    model.db.session.add_all(members_list)
    model.db.session.commit()
    return len(members_list)


def insert_all_issues(project_id, sync_date):
    all_issues = get_issue_by_project(project_id=project_id, args=None)
    for issue in all_issues:
        if "id" in issue["assigned_to"]:
            issue["assigned_to"]["login"] = model.User.query.get(issue["assigned_to"]["id"]).login
        try:
            new_issue = model.RedmineIssue(
                issue_id=issue["id"],
                project_id=issue["project"]["id"],
                project_name=issue["project"]["display"],
                assigned_to=issue["assigned_to"].get("name", None),
                assigned_to_id=issue["assigned_to"].get("id", None),
                assigned_to_login=issue["assigned_to"].get("login", None),
                issue_type=issue["tracker"]["name"],
                issue_name=issue["name"],
                status_id=issue["status"]["id"],
                status=issue["status"]["name"],
                is_closed=issue["is_closed"],
                start_date=issue["start_date"],
                sync_date=sync_date,
            )
            model.db.session.add(new_issue)
            model.db.session.commit()
        except IntegrityError:
            model.db.session.rollback()
        finally:
            model.db.session.close()


# --------------------- Complicated Query ---------------------


def get_sync_date():
    default_sync_date = datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")
    response = model.RedmineProject.query.order_by(model.RedmineProject.sync_date.desc()).distinct().first()
    if response:
        default_sync_date = response.sync_date
    return default_sync_date


def get_current_sync_date_project_id_by_user():
    sync_date = get_sync_date()
    user_id = get_jwt_identity()["user_id"]
    role_id = get_jwt_identity()["role_id"]
    project_id_collections = model.RedmineProject.query.with_entities(model.RedmineProject.project_id).filter(
        model.RedmineProject.sync_date == sync_date
    )

    if role_id == role.ADMIN.id:
        project_id_collections = project_id_collections.order_by(model.RedmineProject.end_date).all()
    else:
        reverse_query_projects = (
            model.ProjectUserRole.query.with_entities(model.ProjectUserRole.project_id)
            .filter_by(user_id=user_id)
            .subquery()
        )

        project_id_collections = (
            project_id_collections.filter(model.RedmineProject.project_id.in_(reverse_query_projects))
            .order_by(model.RedmineProject.end_date)
            .all()
        )

    return [project_id_collection[0] for project_id_collection in project_id_collections]


def get_project_by_current_sync_date(detail, own_project):
    sync_date = get_sync_date()
    project_collections = model.RedmineProject.query.filter(
        model.RedmineProject.sync_date == sync_date,
        model.RedmineProject.project_id.in_(own_project),
    ).order_by(model.RedmineProject.end_date)
    if detail:
        return project_collections.all()
    else:
        return project_collections.limit(5).all()


def get_user_id_by_project(own_project):
    user_id_collections = (
        model.RedmineIssue.query.filter(
            model.RedmineIssue.project_id.in_(own_project),
            model.RedmineIssue.assigned_to_id.isnot(None),
        )
        .with_entities(model.RedmineIssue.assigned_to_id)
        .distinct()
        .all()
    )
    return [user_id_collection[0] for user_id_collection in user_id_collections]


def get_current_sync_date_project_by_project_id(project_id, sync_date):
    return (
        model.RedmineProject.query.filter(
            model.RedmineProject.project_id == project_id,
            model.RedmineProject.sync_date == sync_date,
        )
        .order_by(model.RedmineProject.end_date)
        .first()
    )


def get_last_test_results(project_id):
    return (
        model.TestResults.query.filter(
            model.TestResults.run_at < datetime.today(),
            model.TestResults.project_id == project_id,
        )
        .order_by(model.TestResults.run_at.desc())
        .first()
    )


def get_test_results_count(project_id):
    return model.TestResults.query.filter(
        model.TestResults.run_at < datetime.today(),
        model.TestResults.project_id == project_id,
    ).count()


def get_unclosed_issue_count_by_user_and_project(user_id, own_project):
    return model.RedmineIssue.query.filter(
        model.RedmineIssue.assigned_to_id == user_id,
        model.RedmineIssue.is_closed == False,
        model.RedmineIssue.project_id.in_(own_project),
    ).count()


def get_project_count_by_user_and_project(user_id, own_project):
    return model.ProjectMember.query.filter(
        model.ProjectMember.user_id == user_id,
        model.ProjectMember.project_id.in_(own_project),
    ).count()


def get_current_sync_date_project_count_by_status(own_project, sync_date, status=None):
    project_collections = model.RedmineProject.query.filter(
        model.RedmineProject.project_id.in_(own_project),
        model.RedmineProject.sync_date == sync_date,
    )
    if status:
        return project_collections.filter(model.RedmineProject.project_status == status).count()
    else:
        return project_collections.count()


def update_lock_redmine(is_lock=None, sync_date=None):
    lock_redmine = Lock.query.filter_by(name="sync_redmine").first()
    if is_lock is not None:
        lock_redmine.is_lock = is_lock
    if sync_date is not None:
        lock_redmine.sync_date = sync_date
    db.session.commit()


# --------------------- API Tasks ---------------------


def init_data_first_time():
    """
    Use for the first time to sync redmine(Alembic migratation)
    """
    clear_all_tables()
    sync_date = datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")
    need_to_track_issue = sync_redmine(sync_date)
    if need_to_track_issue:
        for project_id in need_to_track_issue:
            insert_all_issues(project_id, sync_date)


def init_data(now=False):
    try:
        clear_all_tables()
        sync_date = datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")
        if now:
            update_lock_redmine(is_lock=True, sync_date=sync_date)
        else:
            update_lock_redmine(sync_date=sync_date)

        need_to_track_issue = sync_redmine(sync_date)
        if need_to_track_issue:
            for project_id in need_to_track_issue:
                insert_all_issues(project_id, sync_date)
        if now:
            update_lock_redmine(is_lock=False)
    except Exception as e:
        update_lock_redmine(is_lock=False)
        logger.logger.info(str(e))
        raise apiError(404, str(e))


def get_project_members_count(own_project):
    query_collections = (
        model.ProjectMemberCount.query.filter(model.ProjectMemberCount.project_id.in_(own_project))
        .order_by(model.ProjectMemberCount.member_count.desc())
        .limit(10)
        .all()
    )

    project_members_list = [
        {
            "id": context.project_id,
            "name": context.project_name,
            "value": context.member_count,
        }
        for context in query_collections
    ]
    return project_members_list


def get_project_members_detail(own_project):
    query_collections = get_project_by_current_sync_date(detail=True, own_project=own_project)
    project_member_detail = [
        {
            "project_id": context.project_id,
            "project_name": context.project_name,
            "owner_id": context.owner_id,
            "owner_name": context.owner_name,
            "owner_login": context.owner_login,
            "member_count": context.member_count,
            "start_date": context.start_date.strftime("%Y-%m-%d") if context.start_date is not None else None,
            "end_date": context.end_date.strftime("%Y-%m-%d") if context.end_date is not None else None,
            "sync_date": context.sync_date.strftime("%Y-%m-%d"),
        }
        for context in query_collections
    ]
    return sorted(project_member_detail, key=itemgetter("project_id"))


def get_project_members(project_id):
    query_collections = model.ProjectMember.query.filter_by(project_id=project_id).all()
    project_members = [
        {
            "user_id": context.user_id,
            "user_name": context.user_name,
            "role_id": context.role_id,
            "role_name": context.role_name,
            "department": context.department,
            "title": context.title,
        }
        for context in query_collections
    ]
    return project_members


def get_project_overview(own_project):
    sync_date = get_sync_date()
    projects = get_current_sync_date_project_count_by_status(own_project=own_project, sync_date=sync_date)
    overdue = get_current_sync_date_project_count_by_status(
        own_project=own_project, sync_date=sync_date, status=STATUS_OVERDUE
    )
    not_started = get_current_sync_date_project_count_by_status(
        own_project=own_project, sync_date=sync_date, status=STATUS_NOT_STARTED
    )
    index = {
        "projects": projects,
        STATUS_OVERDUE: overdue,
        STATUS_NOT_STARTED: not_started,
    }
    project_overview = [{"project_status": key, "count": value} for key, value in index.items()]
    return project_overview


def get_redmine_projects(detail, own_project):
    query_collections = get_project_by_current_sync_date(detail=detail, own_project=own_project)
    redmine_projects = [
        {
            "project_id": context.project_id,
            "project_name": context.project_name,
            "owner_id": context.owner_id,
            "owner_login": context.owner_login,
            "owner_name": context.owner_name,
            "complete_percent": context.complete_percent,
            "unclosed_issue_count": context.unclosed_issue_count,
            "closed_issue_count": context.closed_issue_count,
            "member_count": context.member_count,
            "expired_day": context.expired_day,
            "end_date": context.end_date.strftime("%Y-%m-%d") if context.end_date is not None else None,
            "sync_date": context.sync_date.strftime("%Y-%m-%dT%H:%M:%S"),
            "project_status": context.project_status,
        }
        for context in query_collections
    ]
    return redmine_projects


def get_redmine_issue_rank(own_project, all=False):
    issue_rank = []
    project_user = get_user_id_by_project(own_project)
    for user_id in project_user:
        user = model.User.query.filter_by(id=user_id).first()
        unclosed_issue_count = get_unclosed_issue_count_by_user_and_project(user_id=user_id, own_project=own_project)
        project_count = get_project_count_by_user_and_project(user_id=user_id, own_project=own_project)
        issue_rank.append(
            {
                "user_id": user.id,
                "user_name": user.name,
                "user_login": user.login,
                "unclosed_count": unclosed_issue_count,
                "project_count": project_count,
            }
        )
    if not all:
        return sorted(issue_rank, key=itemgetter("unclosed_count"), reverse=True)[:5]
    return sorted(
        issue_rank,
        key=lambda x: (x["unclosed_count"], x["project_count"]),
        reverse=True,
    )


def get_unclosed_issues_by_user(user_id):
    query_collections = model.RedmineIssue.query.filter_by(assigned_to_id=user_id, is_closed=False)
    unclosed_issues = [
        {
            "issue_id": context.issue_id,
            "project_id": context.project_id,
            "project_name": context.project_name,
            "assigned_to": context.assigned_to,
            "assigned_to_id": context.assigned_to_id,
            "assigned_to_login": context.assigned_to_login,
            "issue_type": context.issue_type,
            "issue_name": context.issue_name,
            "status_id": context.status_id,
            "status": context.status,
            "is_closed": context.is_closed,
            "start_date": context.start_date.strftime("%Y-%m-%d") if context.start_date is not None else None,
            "sync_date": context.sync_date.strftime("%Y-%m-%d"),
        }
        for context in query_collections
    ]
    return sorted(unclosed_issues, key=itemgetter("project_id"))


def get_postman_passing_rate(detail, own_project):
    all_passing_rate = []
    sync_date = get_sync_date()
    for project_id in own_project:
        response = get_current_sync_date_project_by_project_id(project_id=project_id, sync_date=sync_date)
        if not response:
            continue
        last_test_results = get_last_test_results(project_id)
        if not last_test_results:
            continue
        test_results_count = get_test_results_count(project_id)
        total = last_test_results.total if last_test_results.total else 0
        fail = last_test_results.fail if last_test_results.fail else 0
        success = total - fail
        if detail:
            test_results = {
                "project_id": project_id,
                "project_name": response.project_name,
                "total": total,
                "fail": fail,
                "success": success,
                "run_at": last_test_results.run_at.isoformat(),
                "count": test_results_count,
                "sync_date": response.sync_date.strftime("%Y-%m-%d"),
            }
        else:
            passing_rate = get_passing_rate(total, fail)
            test_results = {
                "project_id": project_id,
                "project_name": response.project_name,
                "test_result_id": last_test_results.id,
                "passing_rate": passing_rate,
                "total": total,
                "count": test_results_count,
            }
        all_passing_rate.append(test_results)
    if detail:
        return sorted(all_passing_rate, key=itemgetter("project_id"))
    else:
        return sorted(all_passing_rate, key=itemgetter("total"), reverse=True)[:10]


# --------------------- Resources ---------------------


class SyncRedmine(Resource):
    @jwt_required()
    def get(self):
        init_data()
        return util.success()


class SyncRedmineNow(Resource):
    def get(self):
        lock_redmine = Lock.query.filter_by(name="sync_redmine").first()
        current_datetime = datetime.utcnow()
        caculate_time = current_datetime - lock_redmine.sync_date

        if lock_redmine.is_lock and caculate_time.total_seconds() < 15 * 60:
            return {"message": "Please wait! Previous process is still running."}

        threading.Thread(target=init_data, kwargs={"now": True}).start()
        return util.success()


class ProjectMembersCount(Resource):
    @jwt_required()
    def get(self):
        own_project = get_current_sync_date_project_id_by_user()
        project_members_count = get_project_members_count(own_project=own_project)
        return util.success(project_members_count)


class ProjectMembersDetail(Resource):
    @jwt_required()
    def get(self):
        own_project = get_current_sync_date_project_id_by_user()
        project_members_detail = get_project_members_detail(own_project=own_project)
        return util.success(project_members_detail)


class ProjectMembers(Resource):
    @jwt_required()
    def get(self, project_id):
        project_members = get_project_members(project_id)
        return util.success(project_members)


class ProjectOverview(Resource):
    @jwt_required()
    def get(self):
        own_project = get_current_sync_date_project_id_by_user()
        project_overview = get_project_overview(own_project=own_project)
        return util.success(project_overview)


class RedmineProjects(Resource):
    @jwt_required()
    def get(self):
        own_project = get_current_sync_date_project_id_by_user()
        redmine_projects = get_redmine_projects(detail=False, own_project=own_project)
        return util.success(redmine_projects)


class RedminProjectDetail(Resource):
    @jwt_required()
    def get(self):
        own_project = get_current_sync_date_project_id_by_user()
        redmine_project_detail = get_redmine_projects(detail=True, own_project=own_project)
        return util.success(redmine_project_detail)


class RedmineIssueRank(Resource):
    @jwt_required()
    def get(self):
        parser = reqparse.RequestParser()
        parser.add_argument("all", type=bool, location="args")
        args = parser.parse_args()

        own_project = get_current_sync_date_project_id_by_user()
        issue_rank = get_redmine_issue_rank(own_project=own_project, all=args.get("all") is not None)
        return util.success(issue_rank)


class UnclosedIssues(Resource):
    @jwt_required()
    def get(self, user_id):
        unclosed_issues = get_unclosed_issues_by_user(user_id)
        return util.success(unclosed_issues)


class PassingRate(Resource):
    @jwt_required()
    def get(self):
        own_project = get_current_sync_date_project_id_by_user()
        passing_rate = get_postman_passing_rate(detail=False, own_project=own_project)
        return util.success(passing_rate)


class PassingRateDetail(Resource):
    @jwt_required()
    def get(self):
        own_project = get_current_sync_date_project_id_by_user()
        passing_rate_detail = get_postman_passing_rate(detail=True, own_project=own_project)
        return util.success(passing_rate_detail)
