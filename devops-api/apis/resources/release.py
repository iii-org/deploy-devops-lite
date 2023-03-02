"""
import json
from datetime import date, datetime, timedelta
from typing import Any

from flask_jwt_extended import get_jwt_identity, jwt_required
from flask_restful import Resource, reqparse
from gitlab.v4 import objects
from sqlalchemy import desc
from sqlalchemy.exc import NoResultFound

import config
import model
import nexus
import util as util
from model import db
from resources import apiError, logger, role

# from resources.harbor import (
#     hb_copy_artifact,
#     hb_copy_artifact_and_re_tag,
#     hb_create_artifact_tag,
#     hb_delete_artifact,
#     hb_delete_artifact_tag,
#     hb_get_artifact,
#     hb_get_artifact_wtih_digrest,
#     hb_get_artifacts_with_tag,
#     hb_list_artifacts_with_params,
#     hb_list_repositories,
#     hb_list_tags,
# )
from .gitlab import gitlab, gl_release

# from .harbor import hb_release
from .redmine import get_redmine_obj, redmine, rm_release

error_redmine_issues_closed = "Unable closed all issues"
error_issue_not_all_closed = "Not All Issues are closed in Versions"
error_harbor_no_image = "No such image found in harbor"
error_gitlab_not_found = "No such repository found in database."
error_release_build = "Unable to build the release."
version_info_keys = ["id", "name", "status"]
release_info_keys = ["description", "created_at", "released_at"]
key_return_json = ["versions", "issues"]


def row_to_dict(row):
    ret = {}
    if row is None:
        return row
    for key in type(row).__table__.columns.keys():
        value = getattr(row, key)
        if type(value) is datetime or type(value) is date:
            ret[key] = str(value)
        elif key in key_return_json and value is not None:
            ret[key] = json.loads(value)
        else:
            ret[key] = value
    return ret


def transfer_array_to_object(targets, key):
    output = {}
    for target in targets:
        key_value = str(target[key])
        output[key_value] = target
    return output


def mapping_function_by_key(versions, releases):
    output = {}
    for key in versions:
        info = {}
        if key in releases:
            for version_key in version_info_keys:
                info[version_key] = versions[key][version_key]
            for release_keys in release_info_keys:
                info[release_keys] = releases[key][release_keys]
            output[key] = info
    return output


def get_mapping_list_info(versions, releases):
    output = {}
    rm_key_versions = {}
    gl_key_releases = {}
    rm_key_versions = transfer_array_to_object(versions, "name")
    gl_key_releases = transfer_array_to_object(releases, "tag_name")
    output = mapping_function_by_key(rm_key_versions, gl_key_releases)
    return list(output.values())


def create_release(project_id, args, versions, issues, branch_name, release_name, user_id, image_path):
    new = model.Release(
        project_id=project_id,
        version_id=args.get("main"),
        versions=json.dumps(versions),
        issues=json.dumps(issues),
        branch=branch_name,
        commit=args.get("commit"),
        tag_name=release_name,
        note=args.get("note"),
        creator_id=user_id,
        create_at=str(datetime.utcnow()),
        update_at=str(datetime.utcnow()),
        image_paths=image_path,
    )
    db.session.add(new)
    db.session.commit()

    release_id = new.id

    row_list = []
    for repo_tag in image_path:
        temp = repo_tag.split("/")[-1].split(":")
        repo, tag = temp[0], temp[1]
        new = model.ReleaseRepoTag(release_id=release_id, tag=tag, custom_path=repo)
        row_list.append(new)
    db.session.add_all(row_list)
    db.session.commit()


def get_hb_tags(artifacts):
    output = []
    for artifact in artifacts:
        output.append(artifact.get("name"))
    return output


def get_hb_branch_tags(project_name, branch_name):
    output = []
    artifacts = hb_release.get_list_artifacts(project_name, branch_name)
    for artifact in artifacts:
        output.append(artifact.get("name"))
    return output


def get_gitlab_base(url):
    return url[:-4]


def analysis_release(release, info, hb_list_tags, image_need):
    ret = row_to_dict(release)
    ret["docker"] = []
    gitlab_project_url = info.get("gitlab_project_url")
    tag_mapping, repo_mapping = {}, {}

    if ret.get("branch") is not None and ret.get("commit") is not None:
        ret["git_url"] = f'{gitlab_project_url}/-/releases/{ret.get("tag_name")}'

        release_repo_tags = model.ReleaseRepoTag.query.filter_by(release_id=release.id).all()
        tag_mapping = {}
        repo_mapping = {}

        for release_repo_tag in release_repo_tags:
            if release_repo_tag.tag != ret["tag_name"]:
                tag_mapping.setdefault(release_repo_tag.tag, []).append(release_repo_tag.custom_path)
            if release_repo_tag.custom_path == info["project_name"]:
                repo_mapping.setdefault(release_repo_tag.custom_path, []).append(release_repo_tag.tag)

    # Generate field: "image_tags"
    ret["image_tags"] = [{tag: data} for tag, data in tag_mapping.items()]
    ret["docker"] = [
        {
            "repo": repo,
            "tags": tags,
            "project": "" if ret["image_paths"] == [] else ret["image_paths"][0].split("/")[0],
            "default": repo == ret["branch"],
        }
        for repo, tags in repo_mapping.items()
    ]
    ret["harbor_external_base_url"] = config.get("HARBOR_EXTERNAL_BASE_URL").split("//")[-1]

    if image_need and ret.get("docker") == []:
        ret = None

    return ret, hb_list_tags


def get_releases_by_project_id(project_id: int, args: dict):
    project: model.Project = model.Project.query.filter_by(id=project_id).first()
    releases: list[Release] = (
        model.Release.query.filter(model.Release.project_id == project_id).order_by(desc(model.Release.create_at)).all()
    )
    output: list[dict] = []
    info: dict[str, str] = {
        "project_name": project.name,
        "gitlab_project_url": f"{project.http_url[:-4]}",
    }
    _list_tags: dict = {}
    for release in releases:
        if releases is not None:
            ret, _list_tags = analysis_release(release, info, _list_tags, args.get("image", False))
            if ret is not None:
                output.append(ret)
    return output


def get_release_image_list(project_id, args):
    from resources.gitlab import get_project_plugin_object

    project_name = model.Project.query.filter_by(id=project_id).first().name
    branch_name = args["branch_name"]
    not_all = args.get("not_all", "false") == "true"
    only_image = args.get("only_image", "false") == "true"

    releases = model.Release.query.filter_by(project_id=project_id).all()
    release_tag_mapping = {release.commit: release.tag_name for release in releases}

    last_push_time = None
    if not_all and releases != []:
        last_push_time = releases[-1].create_at

    image_list = hb_list_artifacts_with_params(project_name, branch_name, push_time=last_push_time)
    commits = gitlab.gl_get_commits(
        get_project_plugin_object(project_id).git_repository_id,
        branch_name,
        per_page=3000,
        since=last_push_time,
    )
    if only_image:
        commit_images = {commit["short_id"][:-1]: commit["title"] for commit in commits}
        ret = [
            {
                "image": image["digest"],
                "push_time": image["push_time"][:-5],
                "commit_id": image["name"],
                "commit_message": commit_images[image["name"]],
                "tag": release_tag_mapping.get(image["name"]),
            }
            for image in image_list
            if image["name"] in commit_images
        ]
        total_count = len(ret)
        ret = ret[args["offset"] : args["offset"] + args["limit"]]
    else:
        image_mapping = {image["name"]: image for image in image_list}
        total_count = len(commits)
        ret = []
        for commit in commits[args["offset"] : args["offset"] + args["limit"]]:
            short_commit = commit["short_id"][:-1]
            image = image_mapping.get(short_commit)
            data = {
                "image": image["digest"] if image is not None else None,
                "push_time": image["push_time"][:-5]
                if image is not None
                else handle_gitlab_datetime(commit["created_at"]),
                "commit_id": commit["short_id"][:-1],
                "commit_message": commit["title"],
                "tag": release_tag_mapping.get(short_commit),
            }
            ret.append(data)

    page_dict = util.get_pagination(total_count, args["limit"], args["offset"])
    output = {"image_list": ret, "page": page_dict}
    return output


def handle_gitlab_datetime(create_time):
    datetime_obj = datetime.strptime(create_time, "%Y-%m-%dT%H:%M:%S.%f%z") - timedelta(hours=8)
    return datetime_obj.isoformat()


def get_distinct_repo(release_id, project_name):
    ret = []
    for repo_tag in (
        model.ReleaseRepoTag.query.filter_by(custom_path=project_name).filter_by(release_id=release_id).all()
    ):
        if repo_tag.custom_path not in ret:
            ret.append(repo_tag.custom_path)
    return ret


def get_distinct_image_path(release_id):
    ret = []
    for repo_tag in model.ReleaseRepoTag.query.filter_by(release_id=release_id).all():
        if repo_tag.custom_path not in ret:
            ret.append(repo_tag.custom_path)
    return ret


def create_release_image_repo(project_id, release_id, args):
    project_name = model.Project.query.filter_by(id=project_id).first().name
    release = model.Release.query.filter_by(id=release_id).first()
    if release is not None:
        dest_image_path = args["image_path"]
        temp = dest_image_path.split(":")
        dest_repo, dest_tag = temp[0], temp[1]
        before_update_at = release.update_at
        repo_list = [hb_repo["name"].split("/")[-1] for hb_repo in hb_list_repositories(project_name)]
        if (
            model.ReleaseRepoTag.query.filter_by(release_id=release.id, tag=dest_tag, custom_path=dest_repo).first()
            is None
        ):
            release.update_at = str(datetime.utcnow())
            new = model.ReleaseRepoTag(release_id=release.id, tag=dest_tag, custom_path=dest_repo)
            db.session.add(new)
            db.session.commit()
            digest = hb_get_artifact(project_name, release.branch, release.tag_name)[0]["digest"]
            try:
                copy_image = add_tag = False
                if dest_repo not in repo_list or hb_get_artifact_wtih_digrest(project_name, dest_repo, digest) == {}:
                    hb_copy_artifact(
                        project_name,
                        dest_repo,
                        f"{project_name}/{release.branch}@{digest}",
                    )
                    copy_image = True
                    for removed_tag in [
                        hb_tag.get("name")
                        for hb_tag in hb_list_tags(project_name, release.branch, digest)
                        if hb_tag.get("name") is not None
                    ]:
                        hb_delete_artifact_tag(project_name, dest_repo, digest, removed_tag, keep=True)
                hb_create_artifact_tag(project_name, dest_repo, digest, dest_tag)
                add_tag = True
                return util.success()
            except Exception as e:
                model.ReleaseRepoTag.query.filter_by(
                    release_id=release.id, tag=dest_tag, custom_path=dest_repo
                ).delete()
                release.update_at = before_update_at
                db.session.commit()
                if copy_image:
                    hb_delete_artifact(project_name, dest_repo, digest)
                elif add_tag:
                    hb_delete_artifact_tag(project_name, dest_repo, digest, dest_tag)
                return util.respond(500, str(e))


def delete_release_image_repo(project_id: int, release_id: int, args: dict):
    project: model.Project = model.Project.query.filter_by(id=project_id).first()
    release: model.Release = model.Release.query.filter_by(id=release_id).first()
    target_repo: str = args.get("repo_name")

    if release is not None and target_repo != release.branch:
        before_update_at: datetime = release.update_at

        delete_tags: list[str] = [
            release_repo_tag.tag
            for release_repo_tag in model.ReleaseRepoTag.query.filter_by(
                release_id=release_id, custom_path=target_repo
            ).all()
        ]

        model.ReleaseRepoTag.query.filter_by(release_id=release_id, custom_path=target_repo).delete()
        release.update_at = datetime.utcnow()
        db.session.commit()

        digest: str = hb_get_artifact(project.name, release.branch, release.tag_name)[0]["digest"]

        try:
            hb_delete_artifact(project.name, target_repo, digest)
            return util.success()

        except apiError.DevOpsError as e:
            if e.status_code == 404 and e.error_value["details"]["service_name"] == "Harbor":
                return util.success()
            return util.respond(500, str(e))

        except Exception as e:
            _r: list[model.ReleaseRepoTag] = []
            for tag in delete_tags:
                new_data: model.ReleaseRepoTag = model.ReleaseRepoTag()
                new_data.release_id = release.id
                new_data.tag = tag
                new_data.custom_path = target_repo
                _r.append(new_data)
            db.session.add_all(_r)
            release.update_at = before_update_at
            db.session.commit()
            return util.respond(500, str(e))


def check_tag_not_exist(forced: bool, repos: list[str], project_name: str, target_label: str):
    if not forced:
        for repo in repos:
            if hb_get_artifacts_with_tag(project_name, repo, target_label):
                raise apiError.DevOpsError(
                    500,
                    f"{target_label} already exist in this Harbor repository.",
                    error=apiError.harbor_tag_already_exist(target_label, repo),
                )


def add_release_tag(project_id: int, release_id: int, args: dict[str, Any]):
    project: model.Project = model.Project.query.filter_by(id=project_id).first()
    project_name: str = project.name

    release: model.Release = model.Release.query.filter_by(id=release_id).first()

    gitlab_repo: objects.Project = gitlab.gl.projects.get(nexus.nx_get_repository_id(project_id))

    if release:
        target_label: str = args.get("tags")
        forced: bool = args.get("forced", False)
        _repos: list[str] = get_distinct_repo(release.id, project_name)
        updated_at: datetime = release.update_at

        if not _repos:
            raise apiError.DevOpsError(
                400,
                "Can not add tag on no image's repo",
                error=apiError.no_image_error(project_name),
            )

        # Check tag is not exist in target image_paths
        check_tag_not_exist(forced, _repos, project_name, target_label)

        # Persist data
        repo_tag: model.ReleaseRepoTag = model.ReleaseRepoTag()
        repo_tag.release_id = release.id
        repo_tag.tag = target_label
        repo_tag.custom_path = _repos[0]
        db.session.add(repo_tag)

        release.update_at = datetime.utcnow()
        db.session.commit()

        digest: str = hb_get_artifact(project_name, project_name, release.tag_name)[0]["digest"]

        gitlab_created: bool = False
        try:
            # Then add tag on all image_path
            release_image_tag_helper(project_name, _repos, target_label, digest, forced=forced)

            if gitlab_repo.commits.list():
                # 如果有東西再去 GitLab 建立 tag
                gitlab.create_tag(gitlab_repo.get_id(), target_label, release.commit)
                gitlab_created = True

            return util.success()
        except Exception as e:
            # Rollback
            model.ReleaseRepoTag.query.filter_by(release_id=release_id, tag=target_label).delete()
            release.update_at = updated_at
            db.session.commit()

            release_image_tag_helper(project_name, _repos, target_label, digest, delete=True)

            if gitlab_created:
                gitlab.delete_tag(gitlab_repo.get_id(), target_label)
                gitlab.get_tags()

            return util.respond(500, str(e))


def delete_release_tag(project_id: int, release_id: int, args: dict[str, Any]):
    project: model.Project = model.Project.query.filter_by(id=project_id).first()
    project_name: str = project.name

    gitlab_repo: objects.Project = gitlab.gl.projects.get(nexus.nx_get_repository_id(project_id))

    release: model.Release = model.Release.query.filter_by(id=release_id).first()

    if release:
        target_label: str = args.get("tags")

        if target_label == release.tag_name:
            return

        _repos: list[str] = get_distinct_repo(release.id, project_name)

        # Persist data
        model.ReleaseRepoTag.query.filter_by(release_id=release_id, tag=target_label).delete()
        release.update_at = datetime.utcnow()
        db.session.commit()

        # Then add tag on all image_path
        digest: str = hb_get_artifact(project_name, release.branch, release.tag_name)[0]["digest"]

        if gitlab.is_tag_exist(gitlab_repo.get_id(), target_label):
            gitlab.delete_tag(gitlab_repo.get_id(), target_label)

        try:
            release_image_tag_helper(project_name, _repos, target_label, digest, delete=True)
        except apiError.DevOpsError as e:
            if e.status_code == 404 and e.error_value["details"]["service_name"] == "Harbor":
                return util.success()
            return util.respond(500, str(e))

        return util.success()


def release_image_tag_helper(
    project_name: str,
    _repos: list[str],
    target_label: str,
    digest: str,
    delete: bool = False,
    forced: bool = False,
):
    for repo in _repos:
        if not delete:
            if target_label not in [tag.get("name", "") for tag in hb_list_tags(project_name, repo, digest)]:
                hb_create_artifact_tag(project_name, repo, digest, target_label, forced=forced)
        else:
            if target_label in [tag.get("name", "") for tag in hb_list_tags(project_name, repo, digest)]:
                hb_delete_artifact_tag(project_name, repo, digest, target_label)


class Releases(Resource):
    def __init__(self):
        self.plugin_relation = None
        self.project = None
        self.versions = None
        self.harbor_info = {
            "check": False,
            "tag": False,
            "image": False,
            "info": "",
            "target": {},
            "errors": {},
            "type": 2,
        }
        self.gitlab_info = {"check": False, "info": "", "errors": {}}
        self.redmine_info = None
        self.versions_by_key = None
        self.closed_statuses = None
        self.valid_info = None

    def check_release_status(self, args, release_name, branch_name, commit):
        issues_by_versions = redmine.rm_list_issues_by_versions_and_closed(
            self.plugin_relation.plan_project_id, args["versions"], self.closed_statuses
        )
        self.redmine_info = rm_release.check_redemine_release(issues_by_versions, self.versions_by_key, args["main"])
        if branch_name is not None:
            self.harbor_info = hb_release.check_harbor_release(
                hb_release.get_list_artifacts(self.project.name, branch_name),
                release_name,
                commit,
            )
        if release_name is not None:
            self.gitlab_info = gl_release.check_gitlab_release(
                self.plugin_relation.git_repository_id,
                release_name,
                branch_name,
                commit,
            )

    def check_release_states(self):
        checklist = {
            "redmine": self.redmine_info,
            "gitlab": self.gitlab_info,
            "harbor": self.harbor_info,
        }
        output = {
            "check": True,
            "items": [],
            "messages": [],
            "errors": {},
            "targets": {},
        }
        for key in checklist:
            if checklist[key]["check"] is False:
                output["check"] = False
                output["items"].append(key)
                output["messages"].append(checklist[key]["info"])
                if "errors" in checklist[key]:
                    output["errors"][key] = checklist[key]["errors"]
                if "target" in checklist[key]:
                    output["targets"][key] = checklist[key]["target"]
        self.valid_info = output

    def delete_gitlab_tag(self, release_name):
        try:
            if self.valid_info["errors"]["gitlab"] != "":
                gitlab.delete_tag(self.plugin_relation.git_repository_id, release_name)
        except NoResultFound:
            return util.respond(
                404,
                error_gitlab_not_found,
                error=apiError.repository_id_not_found(self.plugin_relation.git_repository_id),
            )

    def delete_harbor_tag(self, branch_name):
        try:
            tag_artifact = self.valid_info["targets"]["harbor"].get("duplicate", None)
            if tag_artifact is not None:
                hb_release.delete_harbor_tag(self.project.name, branch_name, tag_artifact)
        except NoResultFound:
            return util.respond(
                404,
                error_harbor_no_image,
                error=apiError.release_unable_to_build(self.plugin_relation.git_repository_id),
            )

    def closed_issues(self):
        issue_ids = []
        try:
            user_id = get_jwt_identity()["user_id"]
            operator_plugin_relation = nexus.nx_get_user_plugin_relation(user_id=user_id)
            plan_operator_id = operator_plugin_relation.plan_user_id
            personal_redmine_obj = get_redmine_obj(plan_user_id=plan_operator_id)
            for issue in self.redmine_info["issues"]:
                if int(issue["status"]["id"]) not in self.closed_statuses:
                    data = {"status_id": self.closed_statuses[0]}
                    issue_ids.append(issue["id"])
                    personal_redmine_obj.rm_update_issue(issue["id"], data)
            logger.logger.info(f"Delete: {personal_redmine_obj.operator_id}")
            del personal_redmine_obj
        except NoResultFound:
            return util.respond(
                404,
                error_redmine_issues_closed,
                error=apiError.redmine_unable_to_forced_closed_issues(issue_ids),
            )

    def forced_close(self, release_name, branch_name):
        # Delete Gitlab Tags
        if "gitlab" in self.valid_info["errors"]:
            self.delete_gitlab_tag(release_name)
            self.gitlab_info["check"] = True
        # Delete Harbor Tags
        if self.valid_info["targets"].get("harbor", None) is not None:
            self.delete_harbor_tag(branch_name)
        # Forced Closed Redmine Issues
        if "redmine" in self.valid_info["errors"]:
            self.closed_issues()

    def get_redmine_issue(self):
        issue_ids = []
        issues = self.redmine_info.get("issues", None)
        if issues is not None:
            for issue in issues:
                issue_ids.append(issue["id"])
        return issue_ids

    def get_redmine_versions(self):
        version_ids = []
        versions = self.redmine_info.get("versions", None)
        if len(versions) > 0:
            for version in versions:
                version_ids.append(version)
        return version_ids

    def get_release_name_by_main(self, main):
        list_versions = redmine.rm_get_version_list(self.plugin_relation.plan_project_id)
        self.versions_by_key = transfer_array_to_object(list_versions["versions"], "id")
        return self.versions_by_key[main]["name"]

    def check_given_tag_not_exist(self, branch_name, release_name, extra_image_path, forced):
        extra_image_path_split = extra_image_path.split(":")
        if len(extra_image_path_split) > 1:
            extra_image_repo, extra_image_tag = (
                extra_image_path_split[0],
                extra_image_path_split[1],
            )
            for repo_name, tag in {
                branch_name: release_name,
                extra_image_repo: extra_image_tag,
            }.items():
                if hb_get_artifacts_with_tag(self.project.name, repo_name, tag) != [] and not forced:
                    raise apiError.DevOpsError(
                        500,
                        f"{tag.capitalize()} already exist in this Harbor repository.",
                        error=apiError.harbor_tag_already_exist(tag, repo_name),
                    )

    def release_main(self, project_id, args):
        # Initial variable
        user_id = get_jwt_identity()["user_id"]
        self.project = model.Project.query.filter_by(id=project_id).first()
        if self.project is None:
            raise apiError.DevOpsError(404, "Project not found", error=apiError.project_not_found(project_id))
        self.plugin_relation = model.ProjectPluginRelation.query.filter_by(project_id=project_id).first()

        gitlab_ref = branch_name = args.get("branch")
        branch_name = None if branch_name == "" else branch_name
        forced = args.get("forced") or False
        gitlab_ref = args.get("commit")
        args["main"] = str(args.get("main"))

        # Check given tag exist in harbor repos or not
        release_name = self.get_release_name_by_main(args["main"])
        self.check_given_tag_not_exist(branch_name, release_name, args.get("extra_image_path", ":"), forced)

        # Check release status
        list_statuses = redmine.rm_get_issue_status()
        self.closed_statuses = redmine.get_closed_status(list_statuses["issue_statuses"])
        self.check_release_status(args, release_name, branch_name, args.get("commit"))

        # Verify Issues is all closed in versions
        self.check_release_states()
        try:
            # Force close this version or release status must be true
            if forced and not self.valid_info["check"]:
                self.forced_close(release_name, branch_name)
            elif not self.valid_info["check"]:
                return util.respond(
                    404,
                    error_release_build,
                    error=apiError.release_unable_to_build(self.valid_info),
                )

            closed_version = False
            check_gitlab_release = False
            create_harbor_release = False

            # Close Redmine Versions
            for version in args["versions"]:
                params = {"version": {"status": "closed"}}
                redmine.rm_put_version(version, params)
                closed_version = True

            # Check Gitalb Release
            if self.gitlab_info.get("check") and args.get("commit") != "" and args.get("branch") != "":
                gitlab_data = {
                    "tag_name": release_name,
                    "ref": gitlab_ref,
                    "description": args["note"],
                }
                if args.get("released_at") is not None:
                    gitlab_data["release_at"] = args["released_at"]
                gitlab.gl_create_release(self.plugin_relation.git_repository_id, gitlab_data)
                check_gitlab_release = True

            #  Create Harbor Release
            image_path = [f"{self.project.name}/{branch_name}:{release_name}"]
            if self.harbor_info["target"].get("release") is not None:
                if (
                    args.get("extra_image_path") is not None
                    and f"{self.project.name}/{args.get('extra_image_path')}" not in image_path
                ):
                    image_path = [f"{self.project.name}/{args.get('extra_image_path')}"] + image_path
                    extra_image_path = args.get("extra_image_path").split(":")
                    extra_dest_repo, extra_dest_tag = (
                        extra_image_path[0],
                        extra_image_path[1],
                    )
                    hb_copy_artifact_and_re_tag(
                        self.project.name,
                        branch_name,
                        extra_dest_repo,
                        args.get("commit"),
                        extra_dest_tag,
                        forced=forced,
                    )
                hb_copy_artifact_and_re_tag(
                    self.project.name,
                    branch_name,
                    branch_name,
                    args.get("commit"),
                    release_name,
                    forced=forced,
                )
                create_harbor_release = True

            create_release(
                project_id,
                args,
                self.get_redmine_versions(),
                self.get_redmine_issue(),
                branch_name,
                release_name,
                user_id,
                image_path,
            )
        except Exception as e:
            # Roll back
            # Open redmine version
            if closed_version:
                for version in args["versions"]:
                    params = {"version": {"status": "open"}}
                    redmine.rm_put_version(version, params)

            # check  Gitalb Release
            if check_gitlab_release:
                gitlab.gl_delete_release(self.plugin_relation.git_repository_id, release_name)

            # Create Harbor Release
            if create_harbor_release:
                for image in image_path:
                    removed_image_path = image.split("/")[-1].split(":")
                    removed_dest_repo, removed_dest_tag = (
                        removed_image_path[0],
                        removed_image_path[1],
                    )
                    if removed_dest_repo != branch_name:
                        hb_copy_artifact_and_re_tag(
                            self.project.name,
                            removed_dest_repo,
                            branch_name,
                            removed_dest_tag,
                            args.get("commit"),
                        )
                    else:
                        digest = hb_get_artifact(self.project.name, branch_name, removed_dest_tag)[0]["digest"]
                        hb_delete_artifact_tag(
                            self.project.name,
                            branch_name,
                            digest,
                            removed_dest_tag,
                            keep=True,
                        )

            if NoResultFound:
                raise apiError.DevOpsError(
                    404,
                    error_redmine_issues_closed,
                    error=apiError.redmine_unable_to_forced_closed_issues(args["versions"]),
                )
            else:
                raise apiError.DevOpsError(500, str(e), error=apiError.uncaught_exception(str(e)))

    @jwt_required()
    def get(self, project_id):
        self.plugin_relation = model.ProjectPluginRelation.query.filter_by(project_id=project_id).first()
        role.require_in_project(project_id, "Error to get release")
        try:
            parser = reqparse.RequestParser()
            parser.add_argument("image", type=bool, location="args")
            args = parser.parse_args()
            return util.success({"releases": get_releases_by_project_id(project_id, args)})
        except NoResultFound:
            return util.respond(404, error_redmine_issues_closed)


class Release(Resource):
    @jwt_required()
    def get(self, project_id, release_name):
        plugin_relation = model.ProjectPluginRelation.query.filter_by(project_id=project_id).first()
        try:
            gl_release = gitlab.gl_get_release(plugin_relation.git_repository_id, release_name)
            rm_list_versions = (redmine.rm_get_version_list(plugin_relation.plan_project_id),)
            rm_key_versions = transfer_array_to_object(rm_list_versions[0]["versions"], "name")
            if release_name not in rm_key_versions:
                return util.success({})
            return util.success({"gitlab": gl_release, "redmine": rm_key_versions[release_name]})
        except NoResultFound:
            return util.respond(
                404,
                error_gitlab_not_found,
                error=apiError.repository_id_not_found(plugin_relation.git_repository_id),
            )


class ReleaseFile:
    def __init__(self, release_id):
        self.release = model.Release.query.filter_by(id=release_id).first()
        self.project_plugin_relation = model.ProjectPluginRelation.query.filter_by(
            project_id=self.release.project_id
        ).first()

    def get_release_env_from_file(self):
        if self.release.commit is None or len(self.release.commit) < 6:
            return []
        file = gitlab.gl_get_file_from_lib(
            self.project_plugin_relation.git_repository_id,
            "iiidevops/app.env",
            self.release.commit,
        )
        if file is not None:
            content = str(file.decode(), "utf-8")
            lines = content.splitlines()
            items = []
            for line in lines:
                if line[0] == "#":
                    continue
                key, value = line.split("=", 1)
                items.append({"key": key.strip(" "), "value": value, "type": "configmap"})
            return items
        else:
            return None
"""
