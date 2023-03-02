'''
import json
import urllib.parse
from distutils.util import strtobool
import pandas as pd
import numpy as np
from io import BytesIO
from flask import send_file
import copy
import re
from pathlib import Path
import os

import model
import util as util
import werkzeug
from flask_restful import Resource, reqparse
from model import db
from nexus import nx_get_project_plugin_relation

import resources.apiError as apiError
import resources.pipeline as pipeline
# from plugins.sideex import sideex_main as sideex
from resources import apiTest
from resources.redmine import redmine
from resources.issue import get_issue_tags
from data.nexus_project import NexusProject
from accessories import redmine_lib
from flask_jwt_extended import jwt_required

from . import issue
from .gitlab import gitlab

request_trace_flow = {
    "Epic": {"tracker_id": -1},
    "Feature": {"tracker_id": -1},
    "Test Plan": {"tracker_id": -1},
}

paths = [
    {
        "software_name": "Postman",
        "path": "iiidevops/postman",
        "file_name_key": "postman_collection.json",
        "variables_file_name": "postman_environment.json",
    },
    {
        "software_name": "SideeX",
        "path": "iiidevops/sideex",
        "file_name_key": "",
        "variables_file_name": "Global Variables.json",
    },
]

filename_validate_mapping = {"Postman": ".postman_collection.json$", "SideeX": ".json$"}


class PostmanJSON:
    def __init__(self, input_dict):
        self.info = input_dict.get("info")
        self.item = input_dict.get("item")


class PostmanJSONInfo:
    def __init__(self, info_dict):
        self.name = info_dict.get("name")


class PostmanJSONItem:
    def __init__(self, item_dict):
        self.name = item_dict.get("name")


class SideeXJSON:
    def __init__(self, input_dict):
        self.suites = input_dict.get("suites")


class SideeXJSONSuite:
    def __init__(self, input_dict):
        self.title = input_dict.get("title")
        self.cases = input_dict.get("cases")


class SideeXJSONCase:
    def __init__(self, input_dict):
        self.title = input_dict.get("title")
        self.records = input_dict.get("records")


class SideeXJSONRecord:
    def __init__(self, record_dict):
        self.name = record_dict.get("name")


def qu_get_testplan_list(project_id):
    testplan = "Test Plan"
    testplan_id = -1
    for tracker in redmine.rm_get_trackers()["trackers"]:
        if tracker["name"] == testplan:
            testplan_id = tracker["id"]
    if testplan_id != -1:
        args = {"tracker_id": testplan_id}
        issue_infos = issue.get_issue_by_project(project_id, args)
        test_plan_file_conn_list = qu_get_testplan_testfile_relate_list(project_id)
        for issue_info in issue_infos:
            issue_info["test_files"] = []
            for test_plan_file_conn in test_plan_file_conn_list:
                if issue_info["id"] == test_plan_file_conn["issue_id"]:
                    issue_info["test_files"].append(test_plan_file_conn)
        return issue_infos


def qu_get_testplan(project_id, testplan_id, journals=0):
    journals = True if journals == 1 else False
    issue_info = issue.get_issue(testplan_id, journals=journals)
    test_plan_file_conn_list = qu_get_testplan_testfile_relate_list(project_id)
    issue_info["test_files"] = []
    for test_plan_file_conn in test_plan_file_conn_list:
        if issue_info["id"] == test_plan_file_conn["issue_id"]:
            the_last_result = {}
            if test_plan_file_conn["software_name"] == "Postman":
                the_last_result = apiTest.get_the_last_result(project_id)
            elif test_plan_file_conn["software_name"] == "SideeX":
                the_last_result = sideex.sd_get_latest_test(project_id)
            test_plan_file_conn["the_last_test_result"] = the_last_result
            issue_info["test_files"].append(test_plan_file_conn)
    return issue_info


def qu_get_testfile_by_testplan(project_id, testplan_id):
    test_plan_file_conn_list = qu_get_testplan_testfile_relate_list(project_id)
    test_files = []
    for test_plan_file_conn in test_plan_file_conn_list:
        if testplan_id == test_plan_file_conn["issue_id"]:
            the_last_result = {}
            if test_plan_file_conn["software_name"] == "Postman":
                the_last_result = apiTest.get_the_last_result(project_id)
            elif test_plan_file_conn["software_name"] == "SideeX":
                the_last_result = sideex.sd_get_latest_test(project_id)
            test_plan_file_conn["the_last_test_result"] = the_last_result
            test_files.append(test_plan_file_conn)
    return test_files


def qu_get_testfile_list(project_id):
    repository_id = nx_get_project_plugin_relation(nexus_project_id=project_id).git_repository_id
    out_list = []
    issues_info = qu_get_testplan_list(project_id)
    for path in paths:
        trees = gitlab.ql_get_tree(repository_id, path["path"], all=True)
        for tree in trees:
            if (
                path["file_name_key"] in tree["name"]
                and path["variables_file_name"] != tree["name"]
                and tree["name"][-5:] == ".json"
                and tree["name"][0] != "_"
                and tree["name"][0] != "*"
            ):
                path_file = f'{path["path"]}/{tree["name"]}'
                gl_raw_lib = gitlab.gl_get_raw_from_lib(repository_id, path_file).decode()
                if gl_raw_lib is None:
                    raise apiError.DevOpsError(
                        500,
                        "Error when decoding gitlab file.",
                        error=apiError.gitlab_error(f"repository_id: {repository_id}, path_file: {path_file}"),
                    )
                coll_json = json.loads(gl_raw_lib)
                test_plans = []
                rows = get_test_plans_from_params(project_id, path["software_name"], tree["name"])
                for row in rows:
                    for issue_info in issues_info:
                        if row["issue_id"] == issue_info["id"]:
                            issue_info.update({"tags": get_issue_tags(issue_info["id"])})
                            test_plans.append(issue_info)
                            break
                if path["file_name_key"] == "postman_collection.json":
                    postmane_test_plans = copy.deepcopy(test_plans)
                    for postmane_test_plan in postmane_test_plans:
                        i = 0
                        while i < len(postmane_test_plan["test_files"]):
                            if (
                                postmane_test_plan["test_files"][i]["software_name"] != path["software_name"]
                                or postmane_test_plan["test_files"][i]["file_name"] != tree["name"]
                            ):
                                del postmane_test_plan["test_files"][i]
                            else:
                                i += 1
                    collection_obj = PostmanJSON(coll_json)
                    postman_info_obj = PostmanJSONInfo(collection_obj.info)
                    the_last_result = apiTest.get_the_last_result(
                        project_id, tree["name"].split("postman")[0].replace(".", "")
                    )
                    out_list.append(
                        {
                            "software_name": path["software_name"],
                            "file_name": tree["name"],
                            "name": postman_info_obj.name,
                            "test_plans": postmane_test_plans,
                            "the_last_test_result": the_last_result,
                        }
                    )
                # sideex
                # sideex's file name is not necessary to have 'sideex' in it.
                elif path["file_name_key"] == "":
                    for test_plan in test_plans:
                        i = 0
                        while i < len(test_plan["test_files"]):
                            if (
                                test_plan["test_files"][i]["software_name"] != path["software_name"]
                                or test_plan["test_files"][i]["file_name"] != tree["name"]
                            ):
                                del test_plan["test_files"][i]
                            else:
                                i += 1
                    sideex_obj = SideeXJSON(coll_json)
                    if sideex_obj.suites is None:
                        name = None
                    else:
                        name = SideeXJSONSuite(sideex_obj.suites[0]).title
                    the_last_result = sideex.sd_get_latest_test(project_id)
                    out_list.append(
                        {
                            "software_name": path["software_name"],
                            "file_name": tree["name"],
                            "name": name,
                            "test_plans": test_plans,
                            "the_last_test_result": the_last_result,
                        }
                    )
    print(out_list)
    return out_list


def get_test_plans_from_params(project_id, software_name, file_name):
    rows = model.IssueCollectionRelation.query.filter_by(
        project_id=project_id, software_name=software_name, file_name=file_name
    ).all()
    return util.rows_to_list(rows)


def qu_create_testplan_testfile_relate(project_id, issue_id, software_name, file_name):
    row_num = model.IssueCollectionRelation.query.filter_by(
        project_id=project_id,
        issue_id=issue_id,
        software_name=software_name,
        file_name=file_name,
    ).count()
    if row_num == 0:
        new = model.IssueCollectionRelation(
            project_id=project_id,
            issue_id=issue_id,
            software_name=software_name,
            file_name=file_name,
        )
        db.session.add(new)
        db.session.commit()
        return {"id": new.id}


def qu_put_testplan_testfiles_relate(project_id, issue_id, test_files):
    rows = model.IssueCollectionRelation.query.filter_by(project_id=project_id, issue_id=issue_id).all()
    for row in rows:
        db.session.delete(row)
        db.session.commit()
    for test_file in test_files:
        qu_create_testplan_testfile_relate(project_id, issue_id, test_file["software_name"], test_file["file_name"])


def qu_get_testplan_testfile_relate_list(project_id):
    rows = model.IssueCollectionRelation.query.filter_by(project_id=project_id).all()
    return util.rows_to_list(rows)


def qu_del_testplan_testfile_relate_list(project_id, item_id):
    row = model.IssueCollectionRelation.query.filter_by(id=item_id).first()
    if row is not None:
        db.session.delete(row)
        db.session.commit()
    else:
        raise apiError.DevOpsError(400, f"Can not find relate id: {item_id}")


def save_file_to_local(local_file_path, file):
    Path(local_file_path).mkdir(parents=True, exist_ok=True)
    if os.path.isfile(f"{local_file_path}/{file.filename}"):
        os.remove(f"{local_file_path}/{file.filename}")
    file.save(f"{local_file_path}/{file.filename}")


def remove_file_from_local(local_file_path, file_name):
    if os.path.isfile(f"{local_file_path}/{file_name}"):
        os.remove(f"{local_file_path}/{file_name}")


# here
def qu_upload_testfile(project_id, file, software_name):
    file_name = file.filename
    if re.search(filename_validate_mapping[software_name], file_name) is None:
        validate_form = filename_validate_mapping[software_name].split("$")[0]
        raise apiError.DevOpsError(
            409,
            f"Filename must end up with {validate_form}.",
            error=apiError.argument_error("test_file"),
        )
    if re.search('[*?"< >|#}{%~&]', file_name) is not None:
        raise apiError.DevOpsError(
            409,
            'Filename must not include special characters *?"<>|#}{%~&',
            error=apiError.argument_error("test_file"),
        )
    repository_id = nx_get_project_plugin_relation(nexus_project_id=project_id).git_repository_id
    soft_path = next(path for path in paths if path["software_name"].lower() == software_name.lower())
    trees = gitlab.ql_get_tree(repository_id, soft_path["path"])
    if len(trees) != 0:
        file_exist = next((True for tree in trees if tree["name"] == file_name), False)
        if file_exist:
            raise apiError.DevOpsError(
                409,
                f"Test File {file_name} already exists in git repository",
                error=apiError.argument_error("test_file"),
            )
    file_path = f"{soft_path['path']}/{file_name}"
    pj = gitlab.gl.projects.get(repository_id)
    local_file_path = f"pj_upload_file/{pj.id}"
    save_file_to_local(local_file_path, file)
    for br in gitlab.gl_get_branches(repository_id):
        next_run = pipeline.get_pipeline_next_run(repository_id)
        gitlab.gl_create_file(pj, file_path, file_name, local_file_path, branch=br["name"])
        pipeline.stop_and_delete_pipeline(repository_id, next_run, branch=br["name"])
    print(f"file_name: {file_name}")
    remove_file_from_local(local_file_path, file_name)


def qu_del_testfile(project_id, software_name, test_file_name):
    rows = model.IssueCollectionRelation.query.filter_by(
        software_name=software_name.capitalize(), file_name=test_file_name
    ).all()
    if len(rows) > 0:
        for row in rows:
            db.session.delete(row)
        db.session.commit()
    repository_id = nx_get_project_plugin_relation(nexus_project_id=project_id).git_repository_id
    for path in paths:
        if (
            path["software_name"].lower() == software_name.lower()
            and path["file_name_key"] in test_file_name
            and test_file_name[-5:] == ".json"
        ):
            url = urllib.parse.quote(f"{path['path']}/{test_file_name}", safe="")
            gitlab.gl_delete_file(
                repository_id,
                url,
                {"commit_message": f"Delete {software_name} test file {path['path']}/{test_file_name} from UI"},
            )
            next_run = pipeline.get_pipeline_next_run(repository_id)
            pipeline.stop_and_delete_pipeline(repository_id, next_run)


def get_the_execl_report(project_id):
    def issue_format(one_issue):
        return f"#{one_issue.id}-{one_issue}"

    def postman_testresult_format(the_last_result):
        return f"{the_last_result['success']}/{the_last_result['success']+the_last_result['failure']}, {the_last_result['branch']}, Commit: {the_last_result['commit_id']}"

    def sideex_testresult_format(the_last_result):
        return f"{the_last_result['result']['casesPassed']}/{the_last_result['result']['casesTotal']}, {the_last_result['branch']}, Commit: {the_last_result['commit_id']}"

    def get_another_issue_id_from_relate(relate, issue_id):
        if relate.issue_id == issue_id:
            return relate.issue_to_id
        elif relate.issue_to_id == issue_id:
            return relate.issue_id
        else:
            pass

    def get_child_or_relation(issue, tracker_id):
        next_level_issues = []
        if len(issue.children) > 0:
            for child in issue.children:
                if child.tracker.id == tracker_id:
                    next_level_issues.append(child)
        elif len(issue.relations) > 0:
            for relate in issue.relations:
                relate_issue = redmine_lib.redmine.issue.get(get_another_issue_id_from_relate(relate, issue.id))
                if relate_issue.tracker.id == tracker_id:
                    next_level_issues.append(relate_issue)
        return next_level_issues

    for tracker in redmine.rm_get_trackers()["trackers"]:
        if tracker["name"] in request_trace_flow:
            request_trace_flow[tracker["name"]]["tracker_id"] = tracker["id"]
    nx_project = NexusProject().set_project_id(project_id)
    plan_id = nx_project.get_project_row().plugin_relation.plan_project_id
    request_trace_flow["Epic"]["issue_infos"] = redmine_lib.redmine.issue.filter(
        project_id=plan_id,
        tracker_id=request_trace_flow["Epic"]["tracker_id"],
        status_id="*",
    )

    out_list = []
    for epic_issue in request_trace_flow["Epic"]["issue_infos"]:
        features = []
        next_level_issues = get_child_or_relation(epic_issue, request_trace_flow["Feature"]["tracker_id"])
        features.extend(next_level_issues)
        if len(features) == 0:
            out_list.append([issue_format(epic_issue)])
            continue
        i = 0
        while i < len(features):
            test_plans = []
            features.extend(get_child_or_relation(features[i], request_trace_flow["Feature"]["tracker_id"]))
            out = get_child_or_relation(features[i], request_trace_flow["Test Plan"]["tracker_id"])
            if len(out) == 0:
                out_list.append([issue_format(epic_issue), issue_format(features[i])])
                features.remove(features[i])
                continue
            test_plans.extend(out)
            j = 0
            while j < len(test_plans):
                test_plans.extend(get_child_or_relation(test_plans[j], request_trace_flow["Test Plan"]["tracker_id"]))
                rows = model.IssueCollectionRelation.query.filter_by(
                    project_id=project_id, issue_id=test_plans[j].id
                ).all()
                if len(rows) == 0:
                    out_list.append(
                        [
                            issue_format(epic_issue),
                            issue_format(features[i]),
                            issue_format(test_plans[j]),
                        ]
                    )
                    test_plans.remove(test_plans[j])
                    continue
                for row in rows:
                    if row.software_name == "SideeX":
                        the_last_result = sideex_testresult_format(sideex.sd_get_latest_test(project_id))
                    else:
                        the_last_result = postman_testresult_format(
                            apiTest.get_the_last_result(project_id, row.file_name.split("postman")[0])
                        )
                    out_list.append(
                        [
                            issue_format(epic_issue),
                            issue_format(features[i]),
                            issue_format(test_plans[j]),
                            row.file_name,
                            the_last_result,
                        ]
                    )
                test_plans.remove(test_plans[j])
                j += 1
            i += 1
    max_column = 0
    for row in out_list:
        if len(row) > max_column:
            max_column = len(row)
    columns_name = ["需求規格", "功能設計", "測試計畫", "測試檔案", "測試結果"]
    if max_column > len(columns_name):
        raise apiError.DevOpsError(500, f"Report's data columns is {max_column}, over 5!")
    elif len(out_list) == 0:
        return
    bio = BytesIO()
    writer = pd.ExcelWriter(bio, engine="xlsxwriter")
    df = pd.DataFrame(out_list, columns=columns_name[:max_column])
    df.index = np.arange(1, len(df) + 1)
    df.to_excel(writer)
    writer.save()
    bio.seek(0)
    return send_file(bio, attachment_filename="report.xlsx")


class TestPlanList(Resource):
    @jwt_required()
    def get(self, project_id):
        out = qu_get_testplan_list(project_id)
        return util.success(out)


# class TestPlan(Resource):
#     def get(self, project_id, testplan_id):
#         parser = reqparse.RequestParser()
#         parser.add_argument('journals', type=str)
#         args = parser.parse_args()
#         journals = None
#         if args['journals'] is not None:
#             journals = strtobool(args['journals'])
#         out = qu_get_testplan(project_id, testplan_id, journals)
#         return util.success(out)


class TestFileByTestPlan(Resource):
    @jwt_required()
    def get(self, project_id, testplan_id):
        out = qu_get_testfile_by_testplan(project_id, testplan_id)
        return util.success(out)


class TestFileList(Resource):
    @jwt_required()
    def get(self, project_id):
        out = qu_get_testfile_list(project_id)
        return util.success(out)


class TestFile(Resource):
    @jwt_required()
    def post(self, project_id, software_name):
        parser = reqparse.RequestParser()
        parser.add_argument(
            "test_file",
            type=werkzeug.datastructures.FileStorage,
            location="files",
            required=True,
        )
        args = parser.parse_args()
        return util.success(qu_upload_testfile(project_id, args["test_file"], software_name))

    @jwt_required()
    def delete(self, project_id, software_name, test_file_name):
        qu_del_testfile(project_id, software_name, test_file_name)
        return util.success()


class TestPlanWithTestFile(Resource):
    @jwt_required()
    def post(self, project_id):
        parser = reqparse.RequestParser()
        parser.add_argument("issue_id", type=int, required=True)
        parser.add_argument("software_name", type=str, required=True)
        parser.add_argument("file_name", type=str, required=True)
        args = parser.parse_args()
        out = qu_create_testplan_testfile_relate(project_id, args["issue_id"], args["software_name"], args["file_name"])
        return util.success(out)

    @jwt_required()
    def put(self, project_id):
        parser = reqparse.RequestParser()
        parser.add_argument("issue_id", type=int, required=True)
        parser.add_argument("test_files", type=list, location="json", required=True)
        args = parser.parse_args()
        qu_put_testplan_testfiles_relate(project_id, args["issue_id"], args["test_files"])
        return util.success()

    # def get(self, project_id):
    #     out = qu_get_testplan_testfile_relate_list(project_id)
    #     return util.success(out)

    @jwt_required()
    def delete(self, project_id, item_id):
        qu_del_testplan_testfile_relate_list(project_id, item_id)
        return util.success()


class Report(Resource):
    @jwt_required()
    def get(self, project_id):
        return get_the_execl_report(project_id)
'''