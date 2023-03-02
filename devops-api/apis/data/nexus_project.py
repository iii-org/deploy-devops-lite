# Use lazy loading to avoid redundant db queries, build up this object like:
# NexusProject().set_project_id(4) or NexusProject().set_project_row(row)
import json
from datetime import date
from operator import and_

from sqlalchemy import inspect

import config
import model
import nexus
from model import ProjectUserRole
from resources import user
from resources.apiError import DevOpsError
# from resources.rancher import get_ci_last_test_result
from accessories import redmine_lib


class NexusProject:
    STATUS_IN_PROGRESS = "in_progress"
    STATUS_NOT_STARTED = "not_started"
    STATUS_CLOSED = "closed"

    def __init__(self):
        self.__project_id = None
        self.__project_row = None
        self.__project_members_dict = None
        self.__owner = None
        self.__extra_fields = {}

    # Usually for a single project query in an API flow
    def set_project_id(self, project_id, do_query=True):
        self.__project_id = project_id
        if do_query:
            self.get_project_row()
            self.get_owner()
        return self

    def set_plan_project_id(self, plan_project_id, do_query=True):
        row = model.ProjectPluginRelation.query.filter_by(plan_project_id=plan_project_id).one()
        self.set_project_id(row.project_id, do_query=do_query)
        return self

    def set_project_row(self, project_row):
        self.__project_row = project_row
        self.set_project_id(project_row.id, False)
        # Mirror data model fields to this object, so it can be used like an ORM row
        inst = inspect(model.Project)
        attr_names = [c_attr.key for c_attr in inst.mapper.column_attrs]
        for attr in attr_names:
            setattr(self, attr, getattr(project_row, attr))
        return self

    # Owner is a NexusUser object
    def set_owner(self, owner):
        self.__owner = owner
        return self

    def set_project_members(self):
        pj_numbers_dict = {}
        rows = ProjectUserRole.query.filter(
            and_(ProjectUserRole.project_id != -1, ProjectUserRole.role_id.in_([1, 3]))
        ).all()
        i = 0
        while i < len(rows):
            if rows[i].project_id not in pj_numbers_dict:
                pj_numbers_dict[rows[i].project_id] = 1
            else:
                pj_numbers_dict[rows[i].project_id] = pj_numbers_dict[rows[i].project_id] + 1
            i += 1
        self.__project_members_dict = pj_numbers_dict
        return self

    def set_starred_info(self, user_id):
        starred = False
        for u in self.get_project_row().starred_by:
            if u.id == user_id:
                starred = True
                break
        self.__extra_fields["starred"] = starred
        return self

    def get_project_id(self):
        if self.__project_id is None:
            raise DevOpsError(500, "Project id or row is not set!")
        return self.__project_id

    def get_project_row(self):
        if self.__project_row is None:
            self.set_project_row(model.Project.query.filter_by(id=self.get_project_id()).one())
        return self.__project_row

    def get_owner(self):
        if self.__owner is None:
            self.__owner = user.NexusUser().set_user_id(self.get_project_row().owner_id)
        return self.__owner

    def get_extra_fields(self):
        return self.__extra_fields

    def check_has_commit(self):
        from resources.gitlab import gitlab, GITLAB_NOTFOUND

        row = model.ProjectPluginRelation.query.filter_by(project_id=self.__project_id).first()
        try:
            pj = gitlab.gl.projects.get(row.git_repository_id)
            branch = pj.default_branch
            return branch is None
        except GITLAB_NOTFOUND.GitlabGetError:
            return True

    def to_json(self):
        from resources.project_relation import project_has_child

        ret = json.loads(str(self.get_project_row()))
        ret["git_url"] = ret["http_url"]
        del ret["http_url"]
        ret["repository_ids"] = [self.get_project_row().plugin_relation.git_repository_id]
        ret["redmine_url"] = (
            f'{config.get("REDMINE_EXTERNAL_BASE_URL")}/projects/'
            f"{self.get_project_row().plugin_relation.plan_project_id}"
        )
        # ret['harbor_url'] = \
        #     f'{config.get("HARBOR_EXTERNAL_BASE_URL")}/harbor/projects/' \
        #     f'{self.get_project_row().plugin_relation.harbor_project_id}/repositories'
        ret["owner_id"] = self.get_owner().id
        ret["owner_name"] = self.get_owner().name
        ret["department"] = self.get_owner().department
        ret["has_son"] = project_has_child(self.__project_id)
        project_relation = model.ProjectParentSonRelation.query.filter_by(son_id=ret["id"]).first()
        ret["parent_id"] = None if project_relation is None else project_relation.parent_id
        ret["is_empty_project"] = ret["is_empty_project"] and self.check_has_commit()
        for key, value in self.get_extra_fields().items():
            ret[key] = value
        if self.__project_members_dict is not None:
            ret["members"] = self.__project_members_dict.get(ret["id"], None)
        return ret

    def fill_pm_extra_fields(self, rm_project, username, sync=False):
        project_issue_info = calculate_project_issues(rm_project, username, sync)
        self.__extra_fields["closed_count"] = project_issue_info["closed_count"]
        self.__extra_fields["overdue_count"] = project_issue_info["overdue_count"]
        self.__extra_fields["total_count"] = project_issue_info["total_count"]
        self.__extra_fields["project_status"] = project_issue_info["project_status"]
        self.__extra_fields["updated_time"] = project_issue_info["updated_time"]
        return self

    def fill_extra_fields(self):
        pass 
        # self.__extra_fields.update(get_ci_last_test_result(self.get_project_row().plugin_relation))
        # return self


def fill_rd_extra_fields(user_id, redmine_project_id):
    plan_user_id = nexus.nx_get_user_plugin_relation(user_id=user_id).plan_user_id
    user_name = model.User.query.get(user_id).login
    extras = {"issues": None, "next_d_time": None}
    all_issues = redmine_lib.rm_impersonate(user_name).issue.filter(
        project_id=redmine_project_id, assigned_to_id=plan_user_id, status_id="*"
    )
    extras["issues"] = len(all_issues)
    # get next_d_time
    issue_due_date_list = []
    for issue in all_issues:
        if getattr(issue, "due_date", None) is not None:
            issue_due_date_list.append(issue.due_date)
    next_d_time = None
    if len(issue_due_date_list) != 0:
        next_d_time = min(issue_due_date_list, key=lambda d: abs(d - date.today()))
    if next_d_time is not None:
        extras["next_d_time"] = next_d_time.isoformat()
    return extras


def calculate_project_issues(rm_project, username, sync=False):
    ret = {}
    updated_on, project_id = rm_project["updated_on"], rm_project["id"]
    if project_id == -1:
        ret["closed_count"] = 0
        ret["overdue_count"] = 0
        ret["total_count"] = 0
        ret["project_status"] = NexusProject.STATUS_CLOSED
        ret["updated_time"] = str(updated_on)
        return ret

    total_count = closed_count = overdue_count = 0

    if sync:
        redmine_obj = redmine_lib.redmine
    else:
        redmine_obj = redmine_lib.rm_impersonate(username)

    rm_issues = redmine_obj.issue.filter(status_id="*", project_id=project_id, sort="updated_on:desc")
    total_count = len(rm_issues)
    if total_count == 0:
        project_status = NexusProject.STATUS_NOT_STARTED
    else:
        updated_on = max(rm_issues[0].updated_on, updated_on)

        close_rm_issues = redmine_obj.issue.filter(status_id=redmine_lib.STATUS_ID_ISSUE_CLOSED, project_id=project_id)
        closed_count = len(close_rm_issues)

        overdue_rm_issues = redmine_obj.issue.filter(due_date=f"<={date.today()}", project_id=project_id)
        overdue_count = len(overdue_rm_issues)

        if closed_count == total_count:
            project_status = NexusProject.STATUS_CLOSED
        else:
            project_status = NexusProject.STATUS_IN_PROGRESS

    ret["closed_count"] = closed_count
    ret["overdue_count"] = overdue_count
    ret["total_count"] = total_count
    ret["project_status"] = project_status
    ret["updated_time"] = str(updated_on)
    return ret
