"""
Модуль для автоматического запуска (очередь) и остановки всех профилей.
Использует ТОЛЬКО state_manager и queue_manager.
"""

import logging
import os
import socket
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Dict, Optional

import queue_manager
import state_manager
from config import AUTO_PHOTO_ROOT
from window_utils import kill_browser_by_port, kill_console_and_process

BROWSER_VISION_PATH = Path(__file__).parent
LOG_DIR = BROWSER_VISION_PATH / "logs"
os.makedirs(LOG_DIR, exist_ok=True)

logger = logging.getLogger("AutoRunner")
logger.setLevel(logging.DEBUG)
log_filename = LOG_DIR / f"auto_runner_{datetime.now().strftime('%Y%m%d')}.log"
file_handler = logging.FileHandler(log_filename, encoding="utf-8")
file_handler.setFormatter(
    logging.Formatter("%(asctime)s - %(levelname)s - %(message)s")
)
logger.addHandler(file_handler)
console_handler = logging.StreamHandler()
console_handler.setLevel(logging.INFO)
console_handler.setFormatter(logging.Formatter("%(levelname)s: %(message)s"))
logger.addHandler(console_handler)


# ================== ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ ==================
def _get_profile_identifier(profile: dict) -> Optional[str]:
    profile_id = profile.get("uuid") or profile.get("profile_id") or profile.get("id")
    return str(profile_id) if profile_id else None


def _extract_person_id_from_profile(profile: dict) -> Optional[str]:
    profile_name = profile.get("profile_name", "")
    if profile_name and "-" in profile_name:
        person_id = profile_name.split("-")[0].strip()
        if person_id:
            return person_id
    return None


def _get_photo_folder_by_person_id(person_id: str) -> Optional[str]:
    if not person_id:
        return None
    auto_folder = AUTO_PHOTO_ROOT / person_id
    return str(auto_folder) if auto_folder.exists() else None


def _is_process_alive(pid: int) -> bool:
    if not pid:
        return False
    try:
        import ctypes

        handle = ctypes.windll.kernel32.OpenProcess(0x100000, False, pid)
        if handle:
            ctypes.windll.kernel32.CloseHandle(handle)
            return True
        return False
    except Exception:
        return False


def _wait_for_port(port: int, timeout: int = 30) -> bool:
    start_time = time.time()
    while time.time() - start_time < timeout:
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(1)
            if sock.connect_ex(("127.0.0.1", port)) == 0:
                sock.close()
                return True
            sock.close()
        except Exception:
            pass
        time.sleep(1)
    return False


def _run_tebor_for_profile(
    profile_uuid: str, port: int, profile_name: str, person_id: Optional[str] = None
) -> tuple:
    """Запускает run_tebor.py. Возвращает (PID, console_title)."""
    run_tebor_path = BROWSER_VISION_PATH / "run_tebor.py"
    console_title = f"Tebor - {profile_name} ({profile_uuid[:8]}...)"
    photo_folder = _get_photo_folder_by_person_id(person_id)

    cmd = [
        sys.executable,
        str(run_tebor_path),
        "--profile-id",
        profile_uuid,
        "--port",
        str(port),
        "--auto",
    ]
    if profile_name:
        cmd.extend(["--profile-name", profile_name])
    if photo_folder:
        cmd.extend(["--photo-folder", photo_folder])

    try:
        creation_flags = (
            subprocess.CREATE_NEW_CONSOLE | subprocess.CREATE_NEW_PROCESS_GROUP
        )
        process = subprocess.Popen(cmd, creationflags=creation_flags)
        logger.info(f" Запущен tebor для '{profile_name}' (PID {process.pid})")
        return process.pid, console_title
    except Exception as e:
        logger.error(f"❌ Не удалось запустить tebor для '{profile_name}': {e}")
        return None, None


# ================== ОСНОВНЫЕ ФУНКЦИИ ==================
def launch_all_profiles() -> Dict:
    """Добавляет ВСЕ профили в очередь. Watcher сам их запустит."""
    logger.info("📥 Добавление всех профилей в очередь...")
    result = {"success": False, "queued": 0, "error": None}
    try:
        from api_client import BrowserVisionClient
        from config import FOLDER_ID

        client = BrowserVisionClient(debug=False)
        profiles_data = client.get_profiles(FOLDER_ID)
        profiles = profiles_data.get("items", [])

        queue_items = []
        for profile in profiles:
            profile_id = _get_profile_identifier(profile)
            if not profile_id:
                continue

            existing = state_manager.get(profile_id)
            if existing and _is_process_alive(existing.get("tebor_pid")):
                continue

            queue_items.append(
                {
                    "uuid": profile_id,
                    "name": profile.get("profile_name", "N/A"),
                    "person_id": _extract_person_id_from_profile(profile),
                }
            )

        queue_manager.add_profiles(queue_items)
        result["queued"] = len(queue_items)
        result["success"] = True
        logger.info(f"✅ В очередь добавлено {result['queued']} профилей.")
        return result
    except Exception as e:
        logger.exception(f"❌ Ошибка: {e}")
        result["error"] = str(e)
        return result


def stop_all_profiles() -> Dict:
    """Останавливает ВСЁ: чистит очередь, закрывает API, убивает порты и консоли."""
    logger.info(" Глобальная остановка всех профилей...")
    queue_manager.clear()

    result = {"success": False, "stopped": 0, "failed": 0}
    try:
        from api_client import BrowserVisionClient
        from config import FOLDER_ID

        client = BrowserVisionClient(debug=False)
        stop_map = state_manager.get_all()

        for profile_id, data in list(stop_map.items()):
            profile_name = data.get("name", "N/A")
            port = data.get("port")
            console_title = data.get("console_title", "")
            tebor_pid = data.get("tebor_pid")

            try:
                client.stop_profile(FOLDER_ID, profile_id)
            except:
                pass

            if console_title or tebor_pid:
                kill_console_and_process(console_title, tebor_pid)

            if port:
                kill_browser_by_port(port)

            state_manager.remove(profile_id)
            result["stopped"] += 1
            time.sleep(0.2)

        result["success"] = True
        logger.info(f"✅ Остановлено {result['stopped']} профилей.")
        return result
    except Exception as e:
        logger.exception(f"❌ Ошибка: {e}")
        result["error"] = str(e)
        return result


# ================== ОБЁРТКИ ДЛЯ БОТА ==================
def quick_start_all() -> str:
    result = launch_all_profiles()
    return (
        f"✅ В очередь добавлено {result['queued']} профилей."
        if result["success"]
        else f"❌ Ошибка: {result.get('error')}"
    )


def quick_stop_all() -> str:
    result = stop_all_profiles()
    return (
        f"⛔ Остановлено {result['stopped']} профилей."
        if result["success"]
        else f"❌ Ошибка: {result.get('error')}"
    )
