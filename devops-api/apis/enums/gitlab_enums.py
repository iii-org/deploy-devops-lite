from enum import Enum


class FileActions(Enum):
    """
    GitLab 檔案的操作列表
    See: https://docs.gitlab.com/ee/api/commits.html#create-a-commit-with-multiple-files-and-actions
    """

    CREATE = "create"
    DELETE = "delete"
    MOVE = "move"
    UPDATE = "update"
    CHMOD = "chmod"
