from redminelib import Redmine, exceptions as redminelibError
import requests
import config
from resources import apiError
from resources import role

redmine = Redmine(
    config.get("REDMINE_INTERNAL_BASE_URL"),
    key=config.get("REDMINE_API_KEY"),
    requests={"verify": False},
)

STATUS_ID_ISSUE_CLOSED = 6


def __refresh_redmine_by_key(plan_operator_id=None):
    protocol = "https" if config.get("REDMINE_INTERNAL_BASE_URL")[:5] == "https" else "http"
    host = config.get("REDMINE_INTERNAL_BASE_URL")[len(protocol + "://") :]
    if plan_operator_id is None:
        redmine = Redmine(
            config.get("REDMINE_INTERNAL_BASE_URL"),
            key=config.get("REDMINE_API_KEY"),
            requests={"verify": False},
        )
    else:
        url = (
            f"{protocol}://{config.get('REDMINE_ADMIN_ACCOUNT')}"
            f":{config.get('REDMINE_ADMIN_PASSWORD')}"
            f"@{host}/users/{plan_operator_id}.json"
        )
        output = requests.get(url, headers={"Content-Type": "application/json"}, verify=False)
        redmine_key = output.json()["user"]["api_key"]
        redmine = Redmine(
            config.get("REDMINE_INTERNAL_BASE_URL"),
            key=redmine_key,
            requests={"verify": False},
        )
    return redmine


def rm_impersonate(user_name, sync=False):
    if not sync and (role.is_role(role.ADMIN) or role.is_role(role.QA)):
        return redmine
    return Redmine(
        config.get("REDMINE_INTERNAL_BASE_URL"),
        key=config.get("REDMINE_API_KEY"),
        impersonate=user_name,
    )


def rm_post_relation(issue_id, issue_to_id, user_account=None):
    if user_account is not None:
        redmine = rm_impersonate(user_account)
    relation = redmine.issue_relation.new()
    relation.issue_id = issue_id
    relation.issue_to_id = issue_to_id
    relation.relation_type = "relates"
    try:
        relation.save()
        return {"relation_id": relation.id}
    except redminelibError.ValidationError as e:
        raise apiError.DevOpsError(400, str(e), error=apiError.redmine_unable_to_relate(issue_id, issue_to_id))


def rm_delete_relation(relation_id, user_account=None):
    if user_account is not None:
        redmine = rm_impersonate(user_account)
    redmine.issue_relation.delete(relation_id)
