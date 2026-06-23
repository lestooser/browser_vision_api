import json
import os
from typing import Dict, Optional

STATE_FILE = "active_profiles.json"


def _load_state() -> Dict[str, dict]:
    """Загружает состояние из файла."""
    if not os.path.exists(STATE_FILE):
        return {}
    try:
        with open(STATE_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, IOError):
        return {}


def _save_state(data: Dict[str, dict]):
    """Сохраняет состояние в файл."""
    with open(STATE_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def get_all() -> Dict[str, dict]:
    """Получить все активные профили."""
    return _load_state()


def add(
    profile_id: str, port: int = None, name: str = None, person_id: str = None, **kwargs
):
    """Добавить или обновить профиль. Поддерживает любые доп. поля через kwargs."""
    data = _load_state()
    profile_data = data.get(profile_id, {})

    if port is not None:
        profile_data["port"] = port
    if name is not None:
        profile_data["name"] = name
    if person_id is not None:
        profile_data["person_id"] = person_id

    # Добавляем специфичные поля (например, tebor_pid, source)
    profile_data.update(kwargs)
    data[profile_id] = profile_data
    _save_state(data)


def update(profile_id: str, updates: dict):
    """Обновить конкретные поля профиля."""
    data = _load_state()
    if profile_id in data:
        data[profile_id].update(updates)
        _save_state(data)


def remove(profile_id: str):
    """Удалить профиль."""
    data = _load_state()
    if profile_id in data:
        del data[profile_id]
        _save_state(data)


def clear():
    """Очистить все профили."""
    _save_state({})


def get(profile_id: str) -> Optional[dict]:
    """Получить конкретный профиль."""
    data = _load_state()
    return data.get(profile_id)
