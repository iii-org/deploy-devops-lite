from model import db, Lock, SystemParameter
from util import model_insert_default_value
from migrate.upgrade_function.upload_file_types import upload_file_types
from resources.redmine import redmine


def insert_default_value_in_lock():
    data_list = [
        {"name": "sync_redmine", "is_lock": False, "sync_date": "2000-01-01 00:00:00"},
        {"name": "download_pj_issues", "is_lock": False},
        {"name": "execute_sync_templ", "is_lock": False},
    ]
    model_insert_default_value(Lock, data_list)


def insert_default_value_in_system_parameter():
    mail_setting = redmine.rm_get_mail_setting()
    email_address = redmine.rm_get_or_set_emission_email_address(None)
    mail_setting["emission_email_address"] = email_address["message"]

    data_list = [
        {
            "name": "k8s_pod_restart_times_limit",
            "value": {"limit_times": 20},
            "active": True,
        },
        {
            "name": "github_verify_info",
            "value": {"token": "", "account": ""},
            "active": False,
        },
        {
            "name": "k8s_pipline_executions_remain_limit",
            "value": {"limit_pods": 5},
            "active": True,
        },
        {"name": "git_commit_history", "value": {"keep_days": 30}, "active": False},
        {
            "name": "sync_redmine_project_relation",
            "value": {"hours": 1},
            "active": True,
        },
        {
            "name": "notification_message_period_of_validity",
            "value": {"months": 12},
            "active": True,
        },
        {
            "name": "upload_file_types",
            "value": {"upload_file_types": upload_file_types},
            "active": True,
        },
        {
            "name": "gitlab_domain_connection",
            "value": {"gitlab_domain_connection": False},
            "active": True,
        },
        {"name": "mail_config", "value": mail_setting, "active": False},
        {
            "name": "rancher_app_revision_limit",
            "value": {"limit_nums": 3000},
            "active": True,
        },
        {"name": "upload_file_size", "value": {"upload_file_size": 5}, "active": True},
    ]
    model_insert_default_value(SystemParameter, data_list)
