from datetime import datetime
from typing import Any

from model import Lock, db


def get_lock_status(name) -> dict[str, Any]:
    _info: Lock = Lock.query.filter_by(name=name).first()
    if _info:
        return {
            "name": _info.name,
            "is_lock": _info.is_lock,
            "sync_date": _info.sync_date,
        }
    return {}


def update_lock_status(name: str, is_lock: bool = False, sync_date: datetime = None):
    _info: Lock = Lock.query.filter_by(name=name).first()
    if _info is not None:
        _info.is_lock = is_lock
        if sync_date is not None:
            _info.sync_date = sync_date
    db.session.commit()
