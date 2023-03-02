import json
from datetime import datetime

from dateutil.tz import tz
from redminelib.exceptions import ResourceNotFoundError

import model
import nexus
from accessories import redmine_lib
from resources import issue
from resources.logger import logger

TGI_TRACKER_ID = 9


def tgi_feed_postman(row):
    collections = json.loads(row.report).get("json_file")
    total = row.total
    passed = row.total - row.fail
    for col_key, result in collections.items():
        assertions = result.get("assertions")
        if assertions.get("failed") > 0:
            _handle_test_failed(
                row.project_id,
                "postman",
                col_key,
                _get_postman_issue_description(col_key, row, result),
                row.branch,
                row.commit_id,
                "test_results",
                row.id,
                total,
                passed,
            )
        else:
            _handle_test_success(
                row.project_id,
                "postman",
                col_key,
                _get_postman_issue_close_description(row, result),
            )


def tgi_feed_sideex(row):
    project_id = nexus.nx_get_project(name=row.project_name).id
    logger.debug(f"Sideex result is {row.result}")
    suites = json.loads(row.result).get("suites")
    for col_key, result in suites.items():
        total = result.get("total")
        passed = result.get("passed")
        if total - passed > 0:
            _handle_test_failed(
                project_id,
                "sideex",
                col_key,
                _get_sideex_issue_description(col_key, row, total, passed),
                row.branch,
                row.commit_id,
                "test_results",
                row.id,
                total,
                passed,
            )
        else:
            _handle_test_success(
                project_id,
                "sideex",
                col_key,
                _get_sideex_issue_close_description(row, total),
            )


def _handle_test_failed(
    project_id,
    software_name,
    filename,
    description,
    branch,
    commit_id,
    result_table,
    result_id,
    total,
    passed,
):
    relation_row = model.TestGeneratedIssue.query.filter_by(
        project_id=project_id, software_name=software_name, file_name=filename
    ).first()
    # First check if issue exists
    iss = None
    if relation_row is None:
        issue_exists = False
    else:
        issue_id = relation_row.issue_id
        try:
            iss = redmine_lib.redmine.issue.get(issue_id, include=["journals"])
            issue_exists = True
        except ResourceNotFoundError:
            model.db.session.delete(relation_row)
            model.db.session.commit()
            issue_exists = False

    if software_name == "sideex":
        description_upper_line = "詳細報告請前往[測試報告列表](/#/scan/sideex)"
    else:
        description_upper_line = "詳細報告請前往[測試報告列表]"

    if not issue_exists:
        description = f"{description_upper_line}\n\n{description}"
        args = {
            "project_id": project_id,
            "tracker_id": TGI_TRACKER_ID,
            "status_id": 1,
            "priority_id": 3,
            "subject": _get_issue_subject(filename, software_name),
            "description": description,
        }
        # Create Issue
        issues = tgi_create_issue(args, software_name, filename, branch, commit_id, result_table, result_id)

        iss = redmine_lib.redmine.issue.get(issues.issue_id, include=["journals"])
        iss.notes = f"{_cst_now_string()} {branch} #{commit_id} 自動化測試失敗 ({passed}/{total})"
        iss.save()
        # Update Note

    else:
        # Check if is closed by human
        for j in reversed(iss.journals):
            if len(j.details) > 0:
                detail = j.details[0]
                if (
                    detail.get("name", "") == "status_id" and detail.get("new_value", "-1") == "6" and j.user.id != 1
                ):  # User id 1 means Redmine admin == system operation
                    # Do nothing
                    return
        # Check if is previously closed (by the system). If so, reopen it.
        if iss.status.id == 6:
            iss.status_id = 1
        iss.description = description
        iss.notes = f"{_cst_now_string()} {branch} #{commit_id} 自動化測試失敗 ({passed}/{total})"
        iss.save()


SOFTWARE_ISSUE_TITLE = {
    "sideex": "SideeX",
    "postman": "Postman",
    "zap": "Zap",
    "webinspect": "WebInspect",
    "sonarqube": "SonarQube",
    "checkmarx": "CheckMarx",
}


def _get_issue_subject(filename, software_name):
    if software_name == "postman":
        if filename == "":
            full_filename = "postman_collection"
        else:
            full_filename = f"{filename}.postman_collection"
        return f"[{SOFTWARE_ISSUE_TITLE[software_name]}] Script: {full_filename}_測試失敗"
    else:
        return f"[{SOFTWARE_ISSUE_TITLE[software_name]}] Script: {filename}_測試失敗"


def _handle_test_success(project_id, software_name, filename, description):
    relation_row = model.TestGeneratedIssue.query.filter_by(
        project_id=project_id, software_name=software_name, file_name=filename
    ).first()
    if relation_row is None:
        # No fail issue, nothing to do
        return
    issue_id = relation_row.issue_id
    try:
        iss = redmine_lib.redmine.issue.get(issue_id)
    except ResourceNotFoundError:
        # Issue is deleted, nothing to do
        return
    if iss.status.id == 6:
        # Already closed, nothing to do
        return
    iss.status_id = 6
    iss.description = description
    iss.notes = description
    iss.save()


def tgi_create_issue(args, software_name, file_name, branch, commit_id, result_table, result_id):
    rm_output = issue.create_issue(args, None)
    issue_id = rm_output.get("id")
    new = model.TestGeneratedIssue(
        project_id=args["project_id"],
        issue_id=issue_id,
        software_name=software_name,
        file_name=file_name,
        branch=branch,
        commit_id=commit_id,
        result_table=result_table,
        result_id=result_id,
    )
    model.db.session.add(new)
    model.db.session.commit()
    return new


def _cst_now_string():
    return (datetime.utcnow().replace(tzinfo=tz.tzutc()).astimezone(tz.gettz("Asia/Taipei"))).strftime(
        "%Y-%m-%d %H:%M:%S"
    )


def check_postman_execution_status(execution, case_num):
    status = True
    line = ""
    assertions = execution.get("assertions")
    if len(assertions) == 0:
        return status, line
    num = 1
    line = str(case_num) + "-" + execution.get("name")
    for assertion in assertions:
        if assertion.get("error_message", None) is not None:
            line = line + "\n\tCase " + str(case_num) + ":" + str(num) + "." + assertion.get("assertion")
            status = False
            num = num + 1
    return status, line


def _get_postman_issue_description(col_key, row, result):
    executions = result.get("executions")
    assertions = result.get("assertions")
    line = (
        f"{_cst_now_string()} {row.branch} #{row.commit_id} 自動化測試失敗 -{col_key} -  ("
        + str(assertions.get("failed"))
        + "/"
        + str(assertions.get("total"))
        + ")"
        + "\n\n"
    )
    num_case = 1
    for execution in executions:
        execution_status, execution_line = check_postman_execution_status(execution, num_case)
        if execution_status is False:
            line = line + "\n" + execution_line
            num_case = num_case + 1
    return line


def _get_postman_issue_close_description(row, result):
    total = result.get("assertions").get("total")
    return f"{_cst_now_string()} {row.branch} #{row.commit_id} 自動化測試成功 ({total})"


def _get_sideex_issue_description(file_name, row, total, passed):
    logger.debug(f"Sideex result is {row.result}")
    suites = json.loads(row.result).get("suites")
    line = f"{_cst_now_string()} {row.branch} #{row.commit_id} 自動化測試失敗 - {file_name} - ({passed}/{total})" + "\n\n"
    suite_keys = suites.keys()
    for key in suite_keys:
        num = 1
        if key != file_name:
            continue
        if suites[key].get("total") != suites[key].get("passed"):
            line = line + key + "(Failed)\n"
            for case in suites[key].get("cases"):
                if case.get("status") == "fail":
                    line = line + str(num) + "." + case.get("title") + "\n"
                    num = num + 1
    return line


def _get_sideex_issue_close_description(row, total):
    return f"{_cst_now_string()} {row.branch} #{row.commit_id} 自動化測試成功 ({total})"
