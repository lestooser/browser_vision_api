import json
import os
from typing import List, Optional

QUEUE_FILE = "profile_queue.json"


def _load_queue() -> List[dict]:
    if not os.path.exists(QUEUE_FILE):
        return []
    try:
        with open(QUEUE_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return []


def _save_queue(data: List[dict]):
    with open(QUEUE_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def add_profiles(profiles_list: List[dict]):
    current = _load_queue()
    existing_ids = {p["uuid"] for p in current}
    for p in profiles_list:
        if p["uuid"] not in existing_ids:
            current.append(p)
            existing_ids.add(p["uuid"])
    _save_queue(current)


def get_next() -> Optional[dict]:
    current = _load_queue()
    if not current:
        return None
    next_profile = current.pop(0)
    _save_queue(current)
    return next_profile


def clear():
    _save_queue([])


def get_all() -> List[dict]:
    return _load_queue()


def get_count() -> int:
    return len(_load_queue())
