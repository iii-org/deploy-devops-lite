"""
Steps to modify the ORM model:
1. Change python codes in this file.
2. In command line: $ alembic revision --autogenerate -m <message>
3. A file named <some hash>_<message>.py will appear at apis/alembic/versions
4. Check if the migration can work: $ alembic upgrade head
5. If no error, rollback: $ alembic downgrade -1
6. If with error, modify the file generated in step 3 then repeat step 4.
7. Add an API server version in migrate.py's VERSION array.
8. Add an alembic_upgrade() statement for that version, or add it in the ONLY_UPDATE_DB_MODELS array.
9. Commit all files includes the file generated in step 3 to git.
10. Restart the API server, then you're done.

If you don't have the alembic.ini, copy _alembic.ini and replace the postgres uri by yourself.
"""
import json
from typing import Optional

from flask_sqlalchemy import SQLAlchemy
from sqlalchemy import (
    Column,
    Integer,
    String,
    Boolean,
    DateTime,
    ForeignKey,
    Date,
    Enum,
    JSON,
    Float,
    ARRAY,
    PickleType,
)
from sqlalchemy.orm import relationship, backref, validates
from sqlalchemy.dialects import postgresql
from sqlalchemy.dialects.postgresql import JSONB

import util
from enums.action_type import ActionType

db = SQLAlchemy()


class AlembicVersion(db.Model):
    version_num = Column(String(32), primary_key=True)


class User(db.Model):
    id = Column(Integer, primary_key=True)
    name = Column(String(45))
    email = Column(String(45))
    phone = Column(String(40))
    login = Column(String(45))
    password = Column(String(100))
    create_at = Column(DateTime)
    update_at = Column(DateTime)
    disabled = Column(Boolean)
    from_ad = Column(Boolean, default=False)
    title = Column(String(45))
    department = Column(String(300))
    plugin_relation = relationship("UserPluginRelation", uselist=False)
    project_role = relationship("ProjectUserRole", back_populates="user")
    last_login = Column(DateTime)

    def __repr__(self):
        fields = {}
        for field in [
            x
            for x in dir(self)
            if not x.startswith("query") and not x.startswith("_") and x not in ["metadata", "registry"]
        ]:
            if field in ["starred_project", "plugin_relation", "project_role"]:
                continue
            data = self.__getattribute__(field)
            try:
                # this will fail on unencodable values, like other classes
                json.dumps(data)
                if field == "password":
                    continue
                elif field == "disabled":
                    if data:
                        fields["status"] = "disable"
                    else:
                        fields["status"] = "enable"
                else:
                    fields[field] = data
            except TypeError:
                fields[field] = util.date_to_str(data)
        return json.dumps(fields)


class Project(db.Model):
    __tablename__ = "projects"

    id = Column(Integer, primary_key=True)
    name = Column(String, unique=True)
    description = Column(String)
    ssh_url = Column(String)
    http_url = Column(String)
    start_date = Column(Date)
    due_date = Column(Date)
    create_at = Column(DateTime)
    update_at = Column(DateTime)
    disabled = Column(Boolean)
    display = Column(String)
    owner_id = Column(Integer, ForeignKey(User.id, ondelete="SET NULL"), nullable=True)
    creator_id = Column(Integer, ForeignKey(User.id, ondelete="SET NULL"), nullable=True)
    is_lock = Column(Boolean, default=False)
    lock_reason = Column(String)
    base_example = Column(String)
    example_tag = Column(String)
    uuid = Column(String)
    is_inheritance_member = Column(Boolean, default=False)
    is_empty_project = Column(Boolean, server_default="false")
    starred_by = relationship(User, secondary="starred_project", backref="starred_project")
    plugin_relation = relationship("ProjectPluginRelation", uselist=False)
    user_role = relationship("ProjectUserRole", back_populates="project")
    alert = Column(Boolean, default=False)
    trace_order = relationship("TraceOrder", backref="project")
    excalidraws = relationship("Excalidraw", back_populates="project")

    def __repr__(self):
        fields = {}
        for field in [
            x
            for x in dir(self)
            if not x.startswith("query") and not x.startswith("_") and x not in ["metadata", "registry"]
        ]:
            if field in ["starred_by", "plugin_relation", "user_role"]:
                continue
            data = self.__getattribute__(field)
            try:
                # this will fail on unencodable values, like other classes
                json.dumps(data)
                fields[field] = data
            except TypeError:
                fields[field] = str(data)
        return json.dumps(fields)


class Release(db.Model):
    __tablename__ = "release"
    id = Column(Integer, primary_key=True)
    project_id = Column(Integer, ForeignKey(Project.id, ondelete="CASCADE"))
    version_id = Column(Integer)
    versions = Column(String)
    issues = Column(String)
    branch = Column(String)
    commit = Column(String)
    tag_name = Column(String)
    note = Column(String)
    creator_id = Column(Integer, ForeignKey(User.id, ondelete="SET NULL"), nullable=True)
    create_at = Column(DateTime)
    update_at = Column(DateTime)
    image_paths = Column(postgresql.ARRAY(String))


class PluginSoftware(db.Model):
    id = Column(Integer, primary_key=True)
    name = Column(String)
    parameter = Column(String)
    disabled = Column(Boolean)
    create_at = Column(DateTime)
    update_at = Column(DateTime)


class ProjectPluginRelation(db.Model):
    id = Column(Integer, primary_key=True)
    project_id = Column(Integer, ForeignKey(Project.id, ondelete="CASCADE"))
    plan_project_id = Column(Integer, unique=True)
    git_repository_id = Column(Integer, unique=True)
    ci_project_id = Column(String)
    ci_pipeline_id = Column(String)
    harbor_project_id = Column(Integer)


class PipelineLogsCache(db.Model):
    id = Column(Integer, primary_key=True)
    project_id = Column(Integer, ForeignKey(Project.id, ondelete="CASCADE"))
    ci_pipeline_id = Column(String)
    run = Column(Integer)
    logs = Column(JSON)


class ProjectUserRole(db.Model):
    project_id = Column(Integer, ForeignKey(Project.id, ondelete="CASCADE"), primary_key=True)
    user_id = Column(Integer, ForeignKey(User.id, ondelete="CASCADE"), primary_key=True)
    role_id = Column(Integer, primary_key=True)
    user = relationship("User", back_populates="project_role")
    project = relationship("Project", back_populates="user_role")


class Requirements(db.Model):
    id = Column(Integer, primary_key=True)
    project_id = Column(Integer, ForeignKey(Project.id, ondelete="CASCADE"))
    issue_id = Column(Integer)
    flow_info = Column(String)
    create_at = Column(DateTime)
    update_at = Column(DateTime)
    disabled = Column(Boolean)


class TestCases(db.Model):
    id = Column(Integer, primary_key=True)
    name = Column(String(255))
    description = Column(String(255))
    issue_id = Column(Integer)
    project_id = Column(Integer, ForeignKey(Project.id, ondelete="CASCADE"))
    create_at = Column(DateTime)
    update_at = Column(DateTime)
    disabled = Column(Boolean)
    # JSON string like
    # {
    #  "type": "API",
    #  "url": "/user/forgot",
    #  "method": "POST",
    #  "method_id": "2"
    # }
    data = Column(String)
    type_id = Column(Integer)


class TestItems(db.Model):
    id = Column(Integer, primary_key=True)
    test_case_id = Column(Integer, ForeignKey(TestCases.id, ondelete="CASCADE"))
    project_id = Column(Integer, ForeignKey(Project.id, ondelete="CASCADE"))
    issue_id = Column(Integer)
    name = Column(String(255))
    is_passed = Column(Boolean)
    create_at = Column(DateTime)
    update_at = Column(DateTime)
    disabled = Column(Boolean)


class TestResults(db.Model):
    """Postman test result table"""

    id = Column(Integer, primary_key=True)
    status = Column(String)
    project_id = Column(Integer, ForeignKey(Project.id, ondelete="CASCADE"))
    branch = Column(String(50))
    commit_id = Column(String)
    report = Column(String)
    total = Column(Integer)
    fail = Column(Integer)
    run_at = Column(DateTime)
    logs = Column(String)


class TestValues(db.Model):
    id = Column(Integer, primary_key=True)
    type_id = Column(Integer)  # Request = 1, response = 2
    key = Column(String(255))
    value = Column(String)
    location_id = Column(Integer)  # Header = 1, Body = 2
    test_item_id = Column(Integer, ForeignKey(TestItems.id, ondelete="CASCADE"))
    test_case_id = Column(Integer, ForeignKey(TestCases.id, ondelete="CASCADE"))
    issue_id = Column(Integer)
    project_id = Column(Integer, ForeignKey(Project.id, ondelete="CASCADE"))
    create_at = Column(DateTime)
    update_at = Column(DateTime)
    disabled = Column(Boolean)


class UserPluginRelation(db.Model):
    user_id = Column(Integer, ForeignKey(User.id, ondelete="CASCADE"), primary_key=True)
    plan_user_id = Column(Integer)
    repository_user_id = Column(Integer)
    harbor_user_id = Column(Integer)
    kubernetes_sa_name = Column(String)


class Checkmarx(db.Model):
    scan_id = Column(Integer, primary_key=True)
    cm_project_id = Column(Integer)
    repo_id = Column(Integer, ForeignKey(ProjectPluginRelation.git_repository_id, ondelete="CASCADE"))
    branch = Column(String)
    commit_id = Column(String)
    # -1 if report is not registered yet
    report_id = Column(Integer, default=-1)
    # The time scan registered
    run_at = Column(DateTime)
    # Store if a final status (Finished, Failed, Cancelled) is checked
    # Null if scan is in non-final status
    scan_final_status = Column(String, nullable=True)
    stats = Column(String)
    # The time report is generated
    finished_at = Column(DateTime)
    # True only if report is available
    finished = Column(Boolean)
    logs = Column(String)


class Flows(db.Model):
    id = Column(Integer, primary_key=True)
    project_id = Column(Integer, ForeignKey(Project.id, ondelete="CASCADE"))
    issue_id = Column(Integer)
    requirement_id = Column(Integer, ForeignKey(Requirements.id, ondelete="CASCADE"))
    type_id = Column(Integer)
    name = Column(String)
    description = Column(String)
    serial_id = Column(Integer)
    create_at = Column(DateTime)
    update_at = Column(DateTime)
    disabled = Column(Boolean)


class Parameters(db.Model):
    id = Column(Integer, primary_key=True)
    issue_id = Column(Integer)
    project_id = Column(Integer, ForeignKey(Project.id, ondelete="CASCADE"))
    parameter_type_id = Column(Integer)
    name = Column(String(50))
    description = Column(String(100))
    limitation = Column(String(50))
    length = Column(Integer)
    create_at = Column(DateTime)
    update_at = Column(DateTime)
    disabled = Column(Boolean)


class WebInspect(db.Model):
    scan_id = Column(String, primary_key=True)
    project_name = Column(String, ForeignKey(Project.name, ondelete="CASCADE"))
    branch = Column(String)
    commit_id = Column(String)
    stats = Column(String)
    # The time scan registered
    run_at = Column(DateTime)
    finished = Column(Boolean, default=False)

    def __repr__(self):
        fields = {}
        for field in [
            x
            for x in dir(self)
            if not x.startswith("query") and not x.startswith("_") and x not in ["metadata", "registry"]
        ]:
            data = self.__getattribute__(field)
            try:
                # this will fail on unencodable values, like other classes
                json.dumps(data)
                if field == "stats":
                    fields[field] = json.loads(data)
                else:
                    fields[field] = data
            except TypeError:
                fields[field] = str(data)
        return json.dumps(fields)


class Activity(db.Model):
    id = Column(Integer, primary_key=True)
    action_type = Column(Enum(ActionType), nullable=False)
    action_parts = Column(String)
    operator_id = Column(Integer, ForeignKey(User.id, ondelete="SET NULL"), nullable=True)
    operator_name = Column(String)
    object_id = Column(String)
    act_at = Column(DateTime)

    def __repr__(self):
        return (
            f"<{self.id}:{self.action_type.name}>"
            f" {self.operator_name}({self.operator_id})"
            f" on {self.action_parts} at {str(self.act_at)}."
        )


class NexusVersion(db.Model):
    id = Column(Integer, primary_key=True)
    api_version = Column(String)
    deploy_version = Column(String)
    deployment_uuid = Column(String)


class Sonarqube(db.Model):
    id = Column(Integer, primary_key=True)
    project_name = Column(String, ForeignKey(Project.name, ondelete="CASCADE"))
    date = Column(DateTime, nullable=False)
    measures = Column(String)


class Zap(db.Model):
    id = Column(Integer, primary_key=True)
    project_name = Column(String, ForeignKey(Project.name, ondelete="CASCADE"))
    branch = Column(String)
    commit_id = Column(String)
    status = Column(String)
    result = Column(String)
    full_log = Column(String)
    # The time scan registered
    run_at = Column(DateTime)
    finished_at = Column(DateTime)

    def __repr__(self):
        fields = {}
        for field in [
            x
            for x in dir(self)
            if not x.startswith("query") and not x.startswith("_") and x not in ["metadata", "registry"]
        ]:
            data = self.__getattribute__(field)
            try:
                # this will fail on unencodable values, like other classes
                json.dumps(data)
                if field == "result":
                    fields[field] = json.loads(data)
                else:
                    fields[field] = data
            except TypeError:
                fields[field] = str(data)
        return json.dumps(fields)


class Sideex(db.Model):
    id = Column(Integer, primary_key=True)
    project_name = Column(String, ForeignKey(Project.name, ondelete="CASCADE"))
    branch = Column(String)
    commit_id = Column(String)
    status = Column(String)
    result = Column(String)
    report = Column(String)
    # The time scan registered
    run_at = Column(DateTime)
    finished_at = Column(DateTime)

    def __repr__(self):
        fields = {}
        for field in [
            x
            for x in dir(self)
            if not x.startswith("query") and not x.startswith("_") and x not in ["metadata", "registry"]
        ]:
            data = self.__getattribute__(field)
            try:
                # this will fail on unencodable values, like other classes
                json.dumps(data)
                if field == "result":
                    fields[field] = json.loads(data)
                elif field == "report":
                    fields["has_report"] = data is not None
                else:
                    fields[field] = data
            except TypeError:
                fields[field] = str(data)
        return json.dumps(fields)


class RedmineIssue(db.Model):
    issue_id = Column(Integer, primary_key=True)
    project_id = Column(Integer)
    project_name = Column(String)
    assigned_to = Column(String)
    assigned_to_id = Column(Integer)
    assigned_to_login = Column(String)
    issue_type = Column(String)
    issue_name = Column(String)
    status_id = Column(Integer)
    status = Column(String)
    is_closed = Column(Boolean)
    start_date = Column(DateTime)
    sync_date = Column(DateTime)
    point = Column(Integer)


class RedmineProject(db.Model):
    id = Column(Integer, primary_key=True)
    project_id = Column(Integer)
    project_name = Column(String)
    owner_id = Column(Integer)
    owner_login = Column(String)
    owner_name = Column(String)
    complete_percent = Column(Float)
    closed_issue_count = Column(Integer)
    unclosed_issue_count = Column(Integer)
    total_issue_count = Column(Integer)
    member_count = Column(Integer)
    expired_day = Column(Integer)
    start_date = Column(DateTime)
    end_date = Column(DateTime)
    sync_date = Column(DateTime)
    project_status = Column(String)


class ProjectMember(db.Model):
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer)
    user_name = Column(String)
    project_id = Column(Integer)
    project_name = Column(String)
    role_id = Column(Integer)
    role_name = Column(String)
    department = Column(String)
    title = Column(String)


class ProjectMemberCount(db.Model):
    project_id = Column(Integer, primary_key=True)
    project_name = Column(String)
    member_count = Column(Integer)


class GitCommitNumberEachDays(db.Model):
    id = Column(Integer, primary_key=True)
    repo_id = Column(Integer)
    repo_name = Column(String)
    date = Column(Date)
    commit_number = Column(Integer)
    total_commit_number = Column(Integer, default=0)
    created_at = Column(DateTime)


class IssueCollectionRelation(db.Model):
    id = Column(Integer, primary_key=True)
    project_id = Column(Integer, ForeignKey(Project.id, ondelete="CASCADE"))
    issue_id = Column(Integer)
    software_name = Column(String)
    file_name = Column(String)
    plan_name = Column(String)
    items = Column(JSON)


class TestGeneratedIssue(db.Model):
    id = Column(Integer, primary_key=True)
    project_id = Column(Integer, ForeignKey(Project.id, ondelete="CASCADE"))
    issue_id = Column(Integer)
    software_name = Column(String)
    file_name = Column(String)
    branch = Column(String)
    commit_id = Column(String)
    result_table = Column(String, nullable=False)
    result_id = Column(Integer, nullable=False)


class StarredProject(db.Model):
    id = Column(Integer, primary_key=True)
    project_id = Column(Integer, ForeignKey(Project.id, ondelete="CASCADE"), nullable=False)
    user_id = Column(Integer, ForeignKey(User.id, ondelete="CASCADE"), nullable=False)


class RancherPiplineNumberEachDays(db.Model):
    id = Column(Integer, primary_key=True)
    project_id = Column(Integer, ForeignKey(Project.id, ondelete="CASCADE"), nullable=False)
    date = Column(Date)
    pipline_number = Column(Integer)
    created_at = Column(DateTime)


class Alert(db.Model):
    id = Column(Integer, primary_key=True)
    project_id = Column(Integer, ForeignKey(Project.id, ondelete="CASCADE"), nullable=False)
    condition = Column(String)
    days = Column(Integer)
    disabled = Column(Boolean)


class Registries(db.Model):
    __tablename__ = "registries"
    registries_id = Column(Integer, primary_key=True)
    name = Column(String)
    user_id = Column(Integer, ForeignKey(User.id, ondelete="CASCADE"))
    description = Column(String)
    access_key = Column(String)
    access_secret = Column(String)
    url = Column(String)
    type = Column(String)
    application = relationship("Application", backref=backref("registries"))
    disabled = Column(Boolean)


class Cluster(db.Model):
    __tablename__ = "cluster"
    id = Column(Integer, primary_key=True)
    name = Column(String)
    disabled = Column(Boolean)
    creator_id = Column(Integer, ForeignKey(User.id, ondelete="SET NULL"), nullable=True)
    create_at = Column(DateTime)
    update_at = Column(DateTime)
    cluster_name = Column(String)
    cluster_host = Column(String)
    cluster_user = Column(String)
    application = relationship("Application", backref=backref("cluster"))

    def __repr__(self):
        fields = {}
        for field in [
            x
            for x in dir(self)
            if not x.startswith("query") and not x.startswith("_") and x not in ["metadata", "registry"]
        ]:
            if field in ["application"]:
                continue
            data = self.__getattribute__(field)
            try:
                # this will fail on unencodable values, like other classes
                json.dumps(data)
                fields[field] = data
            except TypeError:
                fields[field] = str(data)
        return json.dumps(fields)


class Application(db.Model):
    __tablename__ = "application"
    id = Column(Integer, primary_key=True)
    project_id = Column(Integer, ForeignKey(Project.id, ondelete="CASCADE"), nullable=False)
    name = Column(String)
    cluster_id = Column(Integer, ForeignKey(Cluster.id))
    registry_id = Column(Integer, ForeignKey(Registries.registries_id))
    namespace = Column(String)
    status = Column(String)
    created_at = Column(DateTime)
    updated_at = Column(DateTime)
    disabled = Column(Boolean)
    status_id = Column(Integer)
    release_id = Column(Integer)
    k8s_yaml = Column(String)
    harbor_info = Column(String)
    project = relationship("Project", backref=backref("projects"))
    restart_number = Column(Integer, default=0)
    restarted_at = Column(DateTime)
    # 20230119 為取得 storage class 資訊而新增下列一段程式
    storage_class_id = Column(Integer)
    order = Column(Integer, default=0)
    # 20230119 為取得 storage class 資訊而新增下列一段程式


class DefaultAlertDays(db.Model):
    id = Column(Integer, primary_key=True)
    unchange_days = Column(Integer)
    comming_days = Column(Integer)


class TraceOrder(db.Model):
    id = Column(Integer, primary_key=True)
    name = Column(String)
    project_id = Column(Integer, ForeignKey(Project.id, ondelete="CASCADE"), nullable=False)
    order = Column(ARRAY(String))
    default = Column(Boolean)


class TraceResult(db.Model):
    id = Column(Integer, primary_key=True)
    project_id = Column(Integer, ForeignKey(Project.id, ondelete="CASCADE"), nullable=False)
    current_num = Column(Integer)
    results = Column(String)
    execute_time = Column(DateTime)
    finish_time = Column(DateTime)
    exception = Column(String)


class AlertUnchangeRecord(db.Model):
    id = Column(Integer, primary_key=True)
    project_id = Column(Integer, ForeignKey(Project.id, ondelete="CASCADE"), nullable=False)
    issue_id = Column(Integer, nullable=False)
    before_update_time = Column(DateTime)
    after_update_time = Column(DateTime)


class IssueExtensions(db.Model):
    issue_id = Column(Integer, primary_key=True)
    point = Column(Integer)
    ITSMS_no = Column(String)
    ITSMS_url = Column(String)


class Tag(db.Model):
    id = Column(Integer, primary_key=True)
    project_id = Column(Integer, ForeignKey(Project.id, ondelete="CASCADE"), nullable=False)
    name = Column(String)


class IssueTag(db.Model):
    issue_id = Column(Integer, primary_key=True)
    tag_id = Column(postgresql.ARRAY(Integer))


class SystemParameter(db.Model):
    id = Column(Integer, primary_key=True)
    name = Column(String)
    value = Column(JSON)
    active = Column(Boolean)


class Lock(db.Model):
    id = Column(Integer, primary_key=True)
    name = Column(String)
    is_lock = Column(Boolean)
    sync_date = Column(DateTime)


class IssueDisplayField(db.Model):
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey(User.id, ondelete="CASCADE"), nullable=False)
    project_id = Column(Integer, ForeignKey(Project.id, ondelete="CASCADE"), nullable=False)
    display_field = Column(ARRAY(String))
    type = Column(String)

    @validates("type")
    def validate_type(self, key, type):
        if type is not None and type not in ["wbs_cache", "issue_list"]:
            raise AssertionError("Type must in wbs_cache / issue_list.")
        return type


class ServerType(db.Model):
    id = Column(Integer, primary_key=True)
    server = Column(String)
    type = Column(String)


class ServerDataCollection(db.Model):
    id = Column(Integer, primary_key=True)
    type_id = Column(Integer, ForeignKey(ServerType.id, ondelete="CASCADE"), nullable=False)
    project_id = Column(Integer, ForeignKey(Project.id, ondelete="CASCADE"), nullable=False)
    detail = Column(JSON)
    value = Column(JSON)
    create_at = Column(DateTime)
    collect_at = Column(DateTime)


class AlertMessage(db.Model):
    id = Column(Integer, primary_key=True)
    resource_type = Column(String)
    # response name not id
    detail = Column(JSON)
    code = Column(Integer)
    message = Column(String)
    create_at = Column(DateTime)

    @validates("resource_type")
    def validate_resource_type(self, key, resource_type):
        if resource_type is not None and resource_type not in [
            "system",
            "kubernetes",
            "redmine",
            "gitlab",
            "harbor",
            "sonarqube",
            "rancher",
            "github",
        ]:
            raise AssertionError(
                "Resource_type must in system / kubernetes / redmine / gitlab / harbor / sonarqube / rancher / github."
            )
        return resource_type


class CustomIssueFilter(db.Model):
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey(User.id, ondelete="CASCADE"), nullable=False)
    project_id = Column(Integer, ForeignKey(Project.id, ondelete="CASCADE"), nullable=False)
    name = Column(String)
    type = Column(String)
    custom_filter = Column(JSON)

    @validates("custom_filter")
    def validate_custom_filter(self, key, custom_filter):
        custom_filter_keys = sorted(list(custom_filter.keys()))
        expected_keys = [
            "assigned_to_id",
            "fixed_version_id",
            "focus_tab",
            "group_by",
            "priority_id",
            "show_closed_issues",
            "show_closed_versions",
            "status_id",
            "tags",
            "tracker_id",
        ]
        if custom_filter_keys != expected_keys:
            raise AssertionError(f"Custom filter keys must be the same as {expected_keys}.")
        return custom_filter

    @validates("type")
    def validate_type(self, key, type):
        if type is not None and type not in ["issue_list", "issue_board", "my_work"]:
            raise AssertionError("Type must in issue_list / issue_board / my_work.")
        return type


class CMAS(db.Model):
    task_id = Column(String, primary_key=True)
    repo_id = Column(Integer, ForeignKey(ProjectPluginRelation.git_repository_id, ondelete="CASCADE"))
    branch = Column(String)
    commit_id = Column(String)
    run_at = Column(DateTime)  # The time scan registered
    """
    Store if a final status (Finished, Failed, Cancelled) is checked
    Null if scan is in non-final status
    """
    scan_final_status = Column(String, nullable=True)
    stats = Column(String)
    finished_at = Column(DateTime)  # The time report is generated
    finished = Column(Boolean)  # True only if report is available
    filenames = Column(JSON)
    upload_id = Column(Integer)
    size = Column(Integer)
    sha256 = Column(String)
    """
    24 (Android 7.1 Root 版本)
    34 (iOS 11 iPad 越獄版本)
    """
    a_mode = Column(Integer)
    """
    0 (OWASP only)
    1 (工業局行動App規範only)
    2 (OWASP + 工業局規範)
    4 (MSTG(Mobile Security Testing Guide))
    5 (OWASP + MSTG)
    6 (MSTG + 工業局基準)
    7 (OWASP + 工業局基準 + MSTG)
    """
    a_report_type = Column(Integer)
    a_ert = Column(Integer)
    logs = Column(String)


class IssueCommitRelation(db.Model):
    commit_id = Column(String, primary_key=True)
    project_id = Column(Integer, ForeignKey(Project.id, ondelete="CASCADE"), nullable=False)
    issue_ids = Column(postgresql.ARRAY(Integer))
    author_name = Column(String)
    commit_title = Column(String)
    commit_message = Column(String)
    commit_time = Column(DateTime)
    branch = Column(String)
    web_url = Column(String)
    created_at = Column(DateTime)
    updated_at = Column(DateTime)


class ProjectCommitEndpoint(db.Model):
    id = Column(Integer, primary_key=True)
    commit_id = Column(String, unique=True)
    project_id = Column(Integer, ForeignKey(Project.id, ondelete="CASCADE"), nullable=False)
    updated_at = Column(DateTime)


class NotificationMessage(db.Model):
    id = Column(Integer, primary_key=True)
    alert_level = Column(Integer, nullable=False)
    alert_service_id = Column(Integer, default=0)
    title = Column(String)
    message = Column(String, nullable=False)
    message_parameter = Column(JSON)
    creator_id = Column(Integer, ForeignKey(User.id, ondelete="SET NULL"), nullable=True)
    created_at = Column(DateTime)
    updated_at = Column(DateTime)
    close = Column(Boolean, default=False)

    def __repr__(self):
        fields = {}
        for field in [
            x
            for x in dir(self)
            if not x.startswith("query") and not x.startswith("_") and x not in ["metadata", "registry"]
        ]:
            data = self.__getattribute__(field)
            try:
                # this will fail on unencodable values, like other classes
                json.dumps(data)
                fields[field] = data
            except TypeError:
                fields[field] = str(data)
        return json.dumps(fields)


class NotificationMessageReply(db.Model):
    message_id = Column(
        Integer,
        ForeignKey(NotificationMessage.id, ondelete="CASCADE"),
        primary_key=True,
    )
    user_id = Column(Integer, ForeignKey(User.id, ondelete="CASCADE"), primary_key=True)
    created_at = Column(DateTime)


class NotificationMessageRecipient(db.Model):
    message_id = Column(
        Integer,
        ForeignKey(NotificationMessage.id, ondelete="CASCADE"),
        primary_key=True,
    )
    type_id = Column(Integer, nullable=False, primary_key=True)
    type_parameter = Column(JSON)

    def __repr__(self):
        fields = {}
        for field in [
            x
            for x in dir(self)
            if not x.startswith("query") and not x.startswith("_") and x not in ["metadata", "registry"]
        ]:
            data = self.__getattribute__(field)
            try:
                # this will fail on unencodable values, like other classes
                json.dumps(data)
                fields[field] = data
            except TypeError:
                fields[field] = str(data)
        return json.dumps(fields)


class ProjectParentSonRelation(db.Model):
    id = Column(Integer, primary_key=True)
    parent_id = Column(Integer, ForeignKey(Project.id, ondelete="CASCADE"), nullable=False)
    son_id = Column(Integer, ForeignKey(Project.id, ondelete="CASCADE"), nullable=False)
    created_at = Column(DateTime)


class UIRouteData(db.Model):
    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String, primary_key=True)
    role = Column(String, primary_key=True)
    parent = Column(Integer)
    old_brother = Column(Integer)
    visible = Column(Boolean, default=True)
    ui_route = Column(JSON)
    created_at = Column(DateTime)
    updated_at = Column(DateTime)

    @property
    def is_child(self) -> bool:
        return self.parent != 0

    @property
    def is_parent(self) -> bool:
        return self.query.filter_by(parent=self.id).count() > 0

    @property
    def parent_node(self) -> Optional["UIRouteData"]:
        if self.parent == 0:
            return None
        return self.query.filter_by(id=self.parent).first()

    @property
    def children_nodes(self) -> list["UIRouteData"]:
        return self.query.filter_by(parent=self.id).all()

    @property
    def node_counts(self) -> int:
        return self.query.filter_by(parent=self.parent, role=self.role).count()

    @property
    def node_index(self) -> int:
        checker: "UIRouteData" = self.first_node
        index: int = 1

        while checker.id != self.id:
            checker = checker.next_node
            index += 1

        return index

    @property
    def first_node(self) -> "UIRouteData":
        return self.query.filter_by(parent=self.parent, old_brother=0).first()

    @property
    def prev_node(self) -> Optional["UIRouteData"]:
        if self.old_brother == 0:
            return None
        return self.query.filter_by(parent=self.parent, id=self.old_brother).first()

    @prev_node.setter
    def prev_node(self, node: Optional["UIRouteData"]):
        if node:
            self.old_brother = node.id
        else:
            self.old_brother = 0

    @property
    def next_node(self) -> Optional["UIRouteData"]:
        return self.query.filter_by(parent=self.parent, old_brother=self.id).first()

    @next_node.setter
    def next_node(self, node: Optional["UIRouteData"]):
        """因為資料庫只有存 old_brother 因此，如果要設定 next_node，必須先設定 prev_node"""
        if node:
            node.prev_node = self
        else:
            if self.next_node:
                self.next_node.prev_node = None

    @property
    def last_node(self) -> "UIRouteData":
        # Time complexity: O(n)
        node: "UIRouteData" = self

        while node.next_node:
            node = node.next_node

        return node


class MonitoringRecord(db.Model):
    id = Column(Integer, primary_key=True)
    server = Column(String)
    message = Column(String)
    detail = Column(JSON)
    created_at = Column(DateTime)


class ProjectIssueCheck(db.Model):
    project_id = Column(Integer, ForeignKey(Project.id, ondelete="CASCADE"), primary_key=True)
    enable = Column(Boolean, default=False)
    need_fatherissue_trackers = Column(postgresql.ARRAY(Integer))
    created_at = Column(DateTime)
    updated_at = Column(DateTime)


class ReleaseRepoTag(db.Model):
    id = Column(Integer, primary_key=True)
    release_id = Column(Integer, ForeignKey(Release.id, ondelete="CASCADE"), nullable=False)
    tag = Column(String)
    custom_path = Column(String)


class TemplateProject(db.Model):
    id = Column(Integer, primary_key=True)
    template_repository_id = Column(Integer, nullable=False)
    template_repository_name = Column(String)
    from_project_id = Column(Integer, nullable=False)
    from_project_name = Column(String)
    creator_id = Column(Integer, nullable=True)
    created_at = Column(DateTime)
    updated_at = Column(DateTime)

    def __repr__(self):
        fields = {}
        for field in [
            x
            for x in dir(self)
            if not x.startswith("query") and not x.startswith("_") and x not in ["metadata", "registry"]
        ]:
            data = self.__getattribute__(field)
            try:
                # this will fail on unencodable values, like other classes
                json.dumps(data)
                fields[field] = data
            except TypeError:
                fields[field] = str(data)
        return json.dumps(fields)


class HarborScan(db.Model):
    id = Column(Integer, primary_key=True)
    project_id = Column(Integer, ForeignKey(Project.id, ondelete="CASCADE"))
    branch = Column(String)
    commit = Column(String)
    fully_commit = Column(String)
    digest = Column(String)
    scan_overview = Column(JSON)
    created_at = Column(DateTime)
    updated_at = Column(DateTime)
    finished_at = Column(DateTime)
    finished = Column(Boolean)

    def __repr__(self):
        fields = {}
        for field in [
            x
            for x in dir(self)
            if not x.startswith("query") and not x.startswith("_") and x not in ["metadata", "registry"]
        ]:
            data = self.__getattribute__(field)
            try:
                # this will fail on unencodable values, like other classes
                json.dumps(data)
                fields[field] = data
            except TypeError:
                fields[field] = str(data)
        return json.dumps(fields)


class Excalidraw(db.Model):
    id = Column(Integer, primary_key=True)
    project_id = Column(Integer, ForeignKey(Project.id, ondelete="CASCADE"))
    name = Column(String)
    room = Column(String, nullable=False)
    key = Column(String, nullable=False)
    operator_id = Column(Integer, ForeignKey(User.id, ondelete="SET NULL"), nullable=True)
    created_at = Column(DateTime)
    updated_at = Column(DateTime)
    file_key = Column(String)
    project = relationship("Project", back_populates="excalidraws")
    excalidraw_histories = relationship("ExcalidrawHistory", back_populates="excalidraw")


class ExcalidrawJson(db.Model):
    id = Column(Integer, primary_key=True)
    excalidraw_id = Column(Integer, ForeignKey(Excalidraw.id, ondelete="CASCADE"))
    name = Column(String)
    file_value = Column(JSON)


class ExcalidrawIssueRelation(db.Model):
    id = Column(Integer, primary_key=True)
    excalidraw_id = Column(Integer, ForeignKey(Excalidraw.id, ondelete="CASCADE"))
    issue_id = Column(Integer)


class ExcalidrawHistory(db.Model):
    id = Column(Integer, primary_key=True)
    excalidraw_id = Column(Integer, ForeignKey(Excalidraw.id, ondelete="CASCADE"))
    user_id = Column(Integer, ForeignKey(User.id, ondelete="CASCADE"))
    updated_at = Column(DateTime)
    value = Column(JSON)
    excalidraw = relationship("Excalidraw", back_populates="excalidraw_histories")


class ProjectResourceStoragelevel(db.Model):
    """
    {
        "limit": integer,
        "comparison": string ("<", ">", "="),
        "percentage": bool
    }
    """

    project_id = Column(Integer, ForeignKey(Project.id, ondelete="CASCADE"), primary_key=True)
    gitlab = Column(JSON)


class UserMessageType(db.Model):
    user_id = Column(Integer, ForeignKey(User.id, ondelete="CASCADE"), primary_key=True)
    notification = Column(Boolean)
    mail = Column(Boolean)
    teams = Column(Boolean)


class GitlabSourceCodeLens(db.Model):
    branch = Column(String, primary_key=True)
    commit_id = Column(String)
    project_id = Column(Integer, ForeignKey(Project.id, ondelete="CASCADE"), primary_key=True)
    source_code_num = Column(Integer)
    updated_at = Column(DateTime)


class PipelineUpdateVersion(db.Model):
    project_id = Column(Integer, ForeignKey(Project.id, ondelete="CASCADE"), primary_key=True)
    version = Column(Integer)
    status = Column(String)
    message = Column(String)
    updated_at = Column(DateTime)


class Sbom(db.Model):
    id = Column(Integer, primary_key=True)
    project_id = Column(Integer, ForeignKey(Project.id, ondelete="CASCADE"))
    branch = Column(String)
    commit = Column(String)
    sequence = Column(Integer)
    scan_status = Column(String)
    package_nums = Column(Integer)
    scan_overview = Column(JSON)
    created_at = Column(DateTime)
    finished_at = Column(DateTime)
    finished = Column(Boolean)
    logs = Column(String)

    def __repr__(self):
        fields = {}
        for field in [
            x
            for x in dir(self)
            if not x.startswith("query") and not x.startswith("_") and x not in ["metadata", "registry"]
        ]:
            data = self.__getattribute__(field)
            try:
                # this will fail on unencodable values, like other classes
                json.dumps(data)
                fields[field] = data
            except TypeError:
                fields[field] = str(data)
        return json.dumps(fields)


class UpdatePasswordError(db.Model):
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey(User.id, ondelete="CASCADE"), nullable=False)
    server = Column(String, nullable=False)
    password = Column(String, nullable=False)
    created_at = Column(DateTime)


class Pict(db.Model):
    id = Column(Integer, primary_key=True)
    project_id = Column(Integer, ForeignKey(Project.id, ondelete="CASCADE"))
    branch = Column(String)
    commit_id = Column(String)
    run_at = Column(DateTime)
    status = Column(String)
    sideex_id = Column(Integer, ForeignKey(Sideex.id, ondelete="CASCADE"), nullable=False)


class PipelineExecution(db.Model):
    id = Column(Integer, primary_key=True)
    project_id = Column(Integer, ForeignKey(Project.id, ondelete="CASCADE"))
    del_branch = Column(String)
    commit_id = Column(String)
    created_at = Column(DateTime)
    run_num = Column(Integer)


# 20230118 為取得 storage class 資訊而新增下列一段程式
class StorageClass(db.Model):
    id = Column(Integer, primary_key=True)
    cluster_id = Column(Integer, ForeignKey(Cluster.id, ondelete="CASCADE"))
    name = Column(String)
    disabled = Column(Boolean)


# 20230118 為取得 storage class 資訊而新增下上列一段程式
