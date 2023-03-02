import json
import urllib
from datetime import timedelta
from flask_apispec import MethodResource
from flask_apispec import marshal_with, doc, use_kwargs

from flask_jwt_extended import jwt_required
from flask_restful import Resource
from requests.auth import HTTPBasicAuth
from sqlalchemy import desc
from . import router_model

import config
import model
import nexus
import util
from model import db
from resources import apiError, gitlab

# ------------- Internal API methods -------------
from resources.logger import logger

SONARQUBE_DATE_FORMAT = "%Y-%m-%dT%H:%M:%S+0000"
METRICS = (
    "alert_status,bugs,reliability_rating,vulnerabilities,security_hotspots"
    ",security_rating,sqale_index,code_smells,sqale_rating,coverage"
    ",duplicated_blocks,duplicated_lines_density"
)
PAGE_SIZE = 1000
SONAR_SCAN_PATH = "sonar-scanner4.7.0/bin"
# ./sonar-scanner -Dsonar.host.url='{config.get("SONARQUBE_EXTERNAL_BASE_URL")}' -Dsonar.login='{config.get("SONARQUBE_ADMIN_TOKEN")}' -Dsonar.projectKey='projectkey' -Dsonar.projectName='projectnewname'


def __api_request(method, path, headers=None, params=None, data=None):
    if headers is None:
        headers = {}
    if params is None:
        params = {}
    if "Content-Type" not in headers:
        headers["Content-Type"] = "application/json"

    url = f"{config.get('SONARQUBE_INTERNAL_BASE_URL')}{path}"
    output = util.api_request(
        method,
        url,
        headers,
        params,
        data,
        auth=HTTPBasicAuth(config.get("SONARQUBE_ADMIN_TOKEN"), ""),
    )

    logger.debug(
        f"SonarQube api {method} {url}, params={params.__str__()}, body={data},"
        f" response={output.status_code} {output.text}"
    )
    if int(output.status_code / 100) != 2:
        raise apiError.DevOpsError(
            output.status_code,
            "Got non-2xx response from SonarQube.",
            apiError.error_3rd_party_api("SonarQube", output),
        )
    return output


def __api_get(path, params=None, headers=None):
    return __api_request("GET", path, params=params, headers=headers)


def __api_post(
    path,
    params=None,
    headers=None,
    data=None,
):
    return __api_request("POST", path, headers=headers, data=data, params=params)


# ------------- Regular methods -------------
def sq_create_user(args):
    params = {
        "login": args.get("login"),
        "password": args.get("password"),
        "name": args.get("name"),
    }
    return __api_post("/users/create", params=params)


def sq_deactivate_user(user_login):
    return __api_post(f"/users/deactivate?login={user_login}")


def sq_list_user(params):
    return __api_get("/users/search", params=params)


def sq_list_project(params):
    return __api_post("/projects/search", params=params)


def sq_update_project_key(oldname, newname):
    data = {"from": oldname, "to": newname}
    return __api_post("/projects/update_key", params=data).json()


def sq_create_project(project_name, display):
    return __api_post(f"/projects/create?name={display}&project={project_name}" f"&visibility=private")


def sq_delete_project(project_name):
    return __api_post(f"/projects/delete?project={project_name}")


def sq_list_member(project_name, params):
    return __api_get(
        f"/permissions/users?projectKey={project_name}" f"&permission=codeviewer&permission=user",
        params=params,
    )


def sq_add_member(project_name, user_login):
    __api_post(f"/permissions/add_user?login={user_login}" f"&projectKey={project_name}&permission=user")
    return __api_post(f"/permissions/add_user?login={user_login}" f"&projectKey={project_name}&permission=codeviewer")


def sq_remove_member(project_name, user_login):
    return __api_post(f"/permissions/remove_user?login={user_login}" f"&projectKey={project_name}&permission=user")


def sq_create_access_token(login):
    params = {"login": login, "name": "iiidevops-bot"}
    return __api_post("/user_tokens/generate", params=params).json()["token"]


def sq_update_password(login, new_password):
    params = {"login": login, "password": new_password}
    return __api_post("/users/change_password", params=params)


def sq_update_user_name(login, new_name):
    params = {"login": login, "name": new_name}
    return __api_post("/users/update", params=params)


def sq_get_current_measures(project_name):
    params = {
        "metricKeys": METRICS,
        "component": project_name,
        "additionalFields": "periods",
    }
    j = __api_get("/measures/component", params).json()
    ret = j["component"]["measures"]
    if "periods" in j:
        ret.append({"metric": "run_at", "value": j["periods"][0]["date"]})
    return ret


def sq_get_history_measures(project_name):
    # Final output
    ret = {}
    # First get data in db
    project_id = nexus.nx_get_project(name=project_name).id
    rows = model.Sonarqube.query.filter_by(project_name=project_name).order_by(desc(model.Sonarqube.date)).all()
    latest = None
    if len(rows) > 0:
        latest = rows[0].date.strftime(SONARQUBE_DATE_FORMAT)
    for row in rows:
        ret[row.date.strftime(SONARQUBE_DATE_FORMAT)] = json.loads(row.measures)

    # Get new data and extract into return dict
    params = {"p": 1, "ps": PAGE_SIZE, "component": project_name, "metrics": METRICS}
    if latest is not None:
        params["from"] = latest
    fetch = {}
    while True:
        data = __api_get(f"/measures/search_history", params).json()
        for measure in data["measures"]:
            metric = measure["metric"]
            history = measure["history"]
            for h in history:
                if "date" not in h:
                    continue
                date = h["date"]
                if date not in fetch:
                    fetch[date] = {}
                if "value" in h:
                    value = h["value"]
                else:
                    value = ""
                fetch[date][metric] = value
        if len(data) < PAGE_SIZE:
            break
        params["p"] = params["p"] + 1

    # Get branch and commit id information
    params = {"project": project_name}
    if latest is not None:
        params["from"] = latest
    res = __api_get("/project_analyses/search", params).json()
    for ana in res["analyses"]:
        date = ana["date"]
        git_info = ana["projectVersion"].split(":")
        if len(git_info) != 2:
            del fetch[date]
            continue
        branch = git_info[0]
        commit_id = git_info[1]
        fetch[date]["branch"] = branch
        fetch[date]["commit_id"] = commit_id
        fetch[date]["issue_link"] = gitlab.commit_id_to_url(project_id, commit_id)

    # Write new data into db
    for (date, measures) in fetch.items():
        if date == latest:
            continue
        new = model.Sonarqube(project_name=project_name, date=date, measures=json.dumps(measures))
        db.session.add(new)
        db.session.commit()
    ret.update(fetch)
    return ret


def sq_get_history_by_commit(project_id, commit_id):
    project_name = nexus.nx_get_project(id=project_id).name
    sq_get_history_measures(project_name)
    rows = model.Sonarqube.query.filter_by(project_name=project_name).order_by(desc(model.Sonarqube.date)).all()
    if len(rows) == 0:
        return {}
    for row in rows:
        measures = json.loads(row.measures)
        if measures["commit_id"] == commit_id:
            date = (row.date + timedelta(hours=8)).strftime(SONARQUBE_DATE_FORMAT)
            return {
                "link": f'{config.get("SONARQUBE_EXTERNAL_BASE_URL")}/project/activity'
                f"?id={project_name}"
                f"&selected_date={urllib.parse.quote_plus(date)}",
                "history": {date: measures},
            }
    return {}


def get_code_length(project_name):
    METRICS = "ncloc"
    api_url = f"/measures/component?component={project_name}&metricKeys={METRICS}"
    return __api_get(api_url)


# --------------------- Resources ---------------------
class SonarqubeHistory(Resource):
    @jwt_required()
    def get(self, project_name):
        return util.success(
            {
                "link": f'{config.get("SONARQUBE_EXTERNAL_BASE_URL")}/dashboard?id={project_name}',
                "history": sq_get_history_measures(project_name),
            }
        )


class SonarqubeHistoryV2(MethodResource):
    @doc(tags=["Plugin"], description="Get Sonarqube testing history.")
    @marshal_with(router_model.SonarqubeHistoryResponse)
    @jwt_required()
    def get(self, project_name):
        return util.success(
            {
                "link": f'{config.get("SONARQUBE_EXTERNAL_BASE_URL")}/dashboard?id={project_name}',
                "history": sq_get_history_measures(project_name),
            }
        )


class SonarqubeCodelen(Resource):
    @jwt_required()
    def get(self, project_name):
        result = get_code_length(project_name)
        return util.success({"code_length": result.json()["component"]["measures"][0]["value"]})
