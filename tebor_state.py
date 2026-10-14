import json
import os
from datetime import datetime

STATE_DIR = os.path.join("logs", "tebor_states")
os.makedirs(STATE_DIR, exist_ok=True)


def set_state(profile_id: str, state: str, details: str = ""):
    """Мгновенно записывает текущее состояние tebor в файл."""
    if not profile_id:
        return
    file_path = os.path.join(STATE_DIR, f"{profile_id}.json")
    data = {
        "profile_id": profile_id,
        "state": state,
        "details": details,
        "updated_at": datetime.now().isoformat(),
    }
    try:
        temp_path = file_path + ".tmp"
        with open(temp_path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        os.replace(temp_path, file_path)
    except Exception:
        pass


def get_state(profile_id: str) -> dict:
    """Читает текущее состояние профиля."""
    file_path = os.path.join(STATE_DIR, f"{profile_id}.json")
    if not os.path.exists(file_path):
        return {"state": "Не запущен", "details": "", "updated_at": ""}
    try:
        with open(file_path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {"state": "Ошибка чтения", "details": "", "updated_at": ""}


def clear_state(profile_id: str):
    """Удаляет файл состояния (вызывается при остановке)."""
    file_path = os.path.join(STATE_DIR, f"{profile_id}.json")
    try:
        if os.path.exists(file_path):
            os.remove(file_path)
    except Exception:
        pass
