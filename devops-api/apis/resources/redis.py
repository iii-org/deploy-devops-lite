import json
from datetime import datetime
from typing import Any, Optional

import redis

import config
from resources import logger
import ast

ISSUE_FAMILIES_KEY = "issue_families"
PROJECT_ISSUE_CALCULATE_KEY = "project_issue_calculation"
SERVER_ALIVE_KEY = "system_all_alive"
TEMPLATE_CACHE = "template_list_cache"
SHOULD_UPDATE_TEMPLATE = "should_update_template"


class RedisOperator:
    def __init__(self):
        self.redis_base_url = config.get("REDIS_BASE_URL")
        # prod
        self.pool = redis.ConnectionPool(
            host=self.redis_base_url.split(":")[0],
            port=int(self.redis_base_url.split(":")[1]),
            decode_responses=True,
        )
        """
        # local
        self.pool = redis.ConnectionPool(
            host='10.20.0.96', 
            port='31852',
            decode_responses=True
        )
        """
        self.r = redis.Redis(connection_pool=self.pool)

    #####################
    # String type
    #####################
    def str_get(self, key):
        return self.r.get(key)

    def str_set(self, key, value):
        return self.r.set(key, value)

    def str_delete(self, key):
        self.r.delete(key)

    #####################
    # Boolean type
    #####################
    def bool_get(self, key: str) -> bool:
        """
        Get a boolean value from redis. Redis stores boolean into strings,
        so this function will convert strings below to ``True``.

            - "1"
            - "true"
            - "yes"

        Other values will be converted to ``False``.

        :param key: The key to get
        :return: The result from redis server
        """
        value: Optional[str] = self.r.get(key)
        if value:  # if value is not None or not empty string
            if value.lower() in ("1", "true", "yes"):
                return True
        return False

    def bool_set(self, key: str, value: bool) -> bool:
        """
        Set a boolean value to redis.

        :param key: The key to set
        :param value: The boolean value to set
        :return: True if set successfully, False if not
        """
        return self.r.set(key, str(value).lower())

    def bool_delete(self, key: str) -> bool:
        """
        Delete a key from redis.

        :param key: The key to delete
        :return: True if the key was deleted, False if the key did not exist
        """
        result: int = self.r.delete(key)
        if result == 1:
            return True
        else:
            return False

    #####################
    # Dictionary type
    #####################
    def dict_set_all(self, key, value):
        return self.r.hset(key, mapping=value)

    def dict_set_certain(self, key, sub_key, value):
        return self.r.hset(key, sub_key, value)

    def dict_calculate_certain(self, key, sub_key, num=1):
        return self.r.hincrby(key, sub_key, amount=num)

    def dict_get_all(self, key):
        return self.r.hgetall(key)

    def dict_get_certain(self, key, sub_key):
        return self.r.hget(key, sub_key)

    def dict_delete_certain(self, key, sub_key):
        return self.r.hdel(key, sub_key)

    def dict_delete_all(self, key):
        value = self.r.hgetall(key)
        self.r.delete(key)
        return value

    def list_keys(self, pattern):
        return [key for key in self.r.scan_iter(pattern)]

    def dict_len(self, key):
        return self.r.hlen(key)


redis_op = RedisOperator()

# Server Alive
"""
'True': Alive, 'False': Not alive
"""


def get_server_alive():
    status = redis_op.str_get(SERVER_ALIVE_KEY)
    return status == "True" if status is not None else status


def update_server_alive(alive):
    return redis_op.str_set(SERVER_ALIVE_KEY, alive)


# Issue Family Cache
def get_all_issue_relations():
    return redis_op.dict_get_all(ISSUE_FAMILIES_KEY)


def check_issue_has_son(issue_id):
    return redis_op.r.hexists(ISSUE_FAMILIES_KEY, issue_id)


def update_issue_relations(issue_families):
    redis_op.dict_delete_all(ISSUE_FAMILIES_KEY)
    if issue_families != {}:
        return redis_op.dict_set_all(ISSUE_FAMILIES_KEY, issue_families)


def update_issue_relation(parent_issue_id, son_issue_ids):
    return redis_op.dict_set_certain(ISSUE_FAMILIES_KEY, parent_issue_id, son_issue_ids)


def remove_issue_relation(parent_issue_id, son_issue_id):
    son_issue_ids = redis_op.dict_get_certain(ISSUE_FAMILIES_KEY, parent_issue_id)
    if son_issue_ids is None:
        return
    son_issue_ids = son_issue_ids.split(",")
    if son_issue_id in son_issue_ids:
        if len(son_issue_ids) == 1:
            redis_op.dict_delete_certain(ISSUE_FAMILIES_KEY, parent_issue_id)
        else:
            son_issue_ids.remove(son_issue_id)
            update_issue_relation(parent_issue_id, ",".join(son_issue_ids))


def remove_issue_relations(parent_issue_id):
    redis_op.dict_delete_certain(ISSUE_FAMILIES_KEY, parent_issue_id)


def add_issue_relation(parent_issue_id, son_issue_id):
    if not check_issue_has_son(parent_issue_id):
        redis_op.dict_set_certain(ISSUE_FAMILIES_KEY, parent_issue_id, str(son_issue_id))
    else:
        son_issue_ids = redis_op.dict_get_certain(ISSUE_FAMILIES_KEY, parent_issue_id)
        son_issue_ids = son_issue_ids.split(",")
        if son_issue_id not in son_issue_ids:
            update_issue_relation(parent_issue_id, ",".join(son_issue_ids + [str(son_issue_id)]))


# Project issue calculate Cache
def get_certain_pj_issue_calc(pj_id):
    cal_info = redis_op.dict_get_certain(PROJECT_ISSUE_CALCULATE_KEY, pj_id)
    if cal_info is None:
        return {
            "closed_count": 0,
            "overdue_count": 0,
            "total_count": 0,
            "project_status": "not_started",
            "updated_time": datetime.utcnow().isoformat(),
        }
    cal_info_dict = json.loads(cal_info)
    if "T" not in cal_info_dict["updated_time"]:
        cal_info_dict["updated_time"] = (
            datetime.strptime(cal_info_dict["updated_time"], "%Y-%m-%d %H:%M:%S").isoformat()
            if cal_info_dict["updated_time"] not in ["", None]
            else datetime.utcnow().isoformat()
        )
    return cal_info_dict


def update_pj_issue_calcs(project_issue_calculation):
    return redis_op.dict_set_all(PROJECT_ISSUE_CALCULATE_KEY, project_issue_calculation)


def update_pj_issue_calc(pj_id, total_count=0, closed_count=0):
    pj_issue_calc = get_certain_pj_issue_calc(pj_id)
    pj_issue_calc["total_count"] += int(total_count)
    pj_issue_calc["closed_count"] += int(closed_count)

    if pj_issue_calc["total_count"] == 0:
        pj_issue_calc["project_status"] = "not_started"
    elif pj_issue_calc["total_count"] == pj_issue_calc["closed_count"]:
        pj_issue_calc["project_status"] = "closed"
    else:
        pj_issue_calc["project_status"] = "in_progress"

    return redis_op.dict_set_certain(PROJECT_ISSUE_CALCULATE_KEY, pj_id, json.dumps(pj_issue_calc))


# Template cache
def update_template_cache_all(data: dict) -> None:
    logger.logger.info(f"Before data {redis_op.dict_get_all(TEMPLATE_CACHE)}")
    delete_template_cache()
    if data:
        redis_op.dict_set_all(TEMPLATE_CACHE, data)
        redis_op.bool_set(SHOULD_UPDATE_TEMPLATE, False)


def should_update_template_cache() -> bool:
    """
    Handy function to check if template cache should be updated.

    :return: Redis value of template cache update flag.
    """
    return redis_op.bool_get(SHOULD_UPDATE_TEMPLATE)


def delete_template_cache() -> None:
    """
    Delete all template cache.

    :return: None
    """
    redis_op.dict_delete_all(TEMPLATE_CACHE)
    redis_op.bool_set(SHOULD_UPDATE_TEMPLATE, True)


def update_template_cache(id, dict_val):
    redis_op.dict_set_certain(TEMPLATE_CACHE, id, json.dumps(dict_val, default=str))


def get_template_caches_all():
    redis_data: dict[str, str] = redis_op.dict_get_all(TEMPLATE_CACHE)
    out: list[dict[str, Any]] = [{_: json.loads(redis_data[_])} for _ in redis_data]
    return out


def count_template_number():
    return redis_op.dict_len(TEMPLATE_CACHE)
