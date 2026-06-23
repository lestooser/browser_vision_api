"""
Монитор состояния консоли tebor.
Пишет heartbeat в файл logs/console_heartbeat/{profile_id}.json каждые 10 секунд.
"""

import json
import os
import threading
import time
from datetime import datetime

HEARTBEAT_DIR = os.path.join("logs", "console_heartbeat")
os.makedirs(HEARTBEAT_DIR, exist_ok=True)

_current_status = "Инициализация..."
_status_lock = threading.Lock()


def set_status(msg: str):
    """Позволяет tebor.py обновлять текущий статус (опционально)."""
    global _current_status
    with _status_lock:
        _current_status = msg


def _heartbeat_loop(profile_id: str, pid: int, title: str):
    """Фоновый цикл записи heartbeat."""
    file_path = os.path.join(HEARTBEAT_DIR, f"{profile_id}.json")
    while True:
        try:
            with _status_lock:
                status = _current_status

            data = {
                "profile_id": profile_id,
                "pid": pid,
                "title": title,
                "status": status,
                "last_update": datetime.now().isoformat(),
                "alive": True,
            }
            # Атомарная запись, чтобы другие скрипты не читали полузаписанный файл
            temp_path = file_path + ".tmp"
            with open(temp_path, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            os.replace(temp_path, file_path)
        except Exception:
            pass
        time.sleep(10)


def start_monitor(profile_id: str, pid: int, title: str):
    """Запускает фоновый поток мониторинга."""
    t = threading.Thread(
        target=_heartbeat_loop, args=(profile_id, pid, title), daemon=True
    )
    t.start()
