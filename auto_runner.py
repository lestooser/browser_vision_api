"""
Модуль для автоматического запуска и остановки всех профилей.
Использует единый state_manager для отслеживания состояний.
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

import state_manager  # Единый менеджер состояний

# Пути
BROWSER_VISION_PATH = Path(__file__).parent
LOG_DIR = BROWSER_VISION_PATH / "logs"
os.makedirs(LOG_DIR, exist_ok=True)

# ================== НАСТРОЙКА ЛОГГИРОВАНИЯ ==================
logger = logging.getLogger("AutoRunner")
logger.setLevel(logging.DEBUG)
log_filename = LOG_DIR / f"auto_runner_{datetime.now().strftime('%Y%m%d')}.log"
file_handler = logging.FileHandler(log_filename, encoding="utf-8")
file_handler.setLevel(logging.DEBUG)
formatter = logging.Formatter(
    "%(asctime)s - %(levelname)s - %(message)s", datefmt="%Y-%m-%d %H:%M:%S"
)
file_handler.setFormatter(formatter)
logger.addHandler(file_handler)
console_handler = logging.StreamHandler()
console_handler.setLevel(logging.INFO)
console_handler.setFormatter(formatter)
logger.addHandler(console_handler)


# ================== ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ ==================
def _get_profile_identifier(profile: dict) -> Optional[str]:
    profile_id = profile.get("uuid") or profile.get("profile_id") or profile.get("id")
    return str(profile_id) if profile_id is not None else None


def _get_profile_port(profile: dict) -> Optional[int]:
    port = profile.get("port") or profile.get("debug_port") or profile.get("cdp_port")
    try:
        return int(port) if port else None
    except (TypeError, ValueError):
        return None


def _extract_person_id_from_profile(profile: dict) -> Optional[str]:
    profile_name = profile.get("profile_name", "")
    if not profile_name:
        return None
    if "-" in profile_name:
        person_id = profile_name.split("-")[0].strip()
        if person_id:
            return person_id
    return None


def _get_photo_folder_by_person_id(person_id: str) -> Optional[str]:
    if not person_id:
        return None
    auto_folder = f"D:\\python\\selenium-test\\downloads\\extracted\\{person_id}"
    return auto_folder if os.path.exists(auto_folder) else None


def _extract_created_proxy(result: Optional[Dict]) -> Optional[Dict]:
    if not result:
        return None
    data = result.get("data")
    if isinstance(data, list) and data:
        return data[0]
    if isinstance(data, dict):
        return data
    return None


def _profile_has_proxy(update_result: Optional[Dict], proxy_id: str) -> bool:
    if not update_result:
        return False
    data = update_result.get("data")
    if not isinstance(data, dict):
        return False
    if data.get("proxy_id") == proxy_id:
        return True
    proxy = data.get("proxy")
    return isinstance(proxy, dict) and proxy.get("id") == proxy_id


def _attach_next_proxy_to_profile(
    client, folder_id: str, profile_id: str, profile_name: str
) -> Optional[str]:
    from config import DEFAULT_PROXY_TYPE
    from config_sequence import SequentialConfig

    sequence = SequentialConfig()
    while True:
        try:
            proxy = sequence.next_proxy()
        except ValueError as e:
            logger.error(f"   ❌ Не удалось получить следующий прокси: {e}")
            return None

        proxy_payload = proxy.to_api_payload(
            name=f"Proxy {proxy.display}", proxy_type=DEFAULT_PROXY_TYPE
        )
        proxy_result = client.create_proxy(folder_id, proxy_payload)
        proxy_data = _extract_created_proxy(proxy_result)
        if not proxy_data or not proxy_data.get("id"):
            continue

        proxy_id = proxy_data["id"]
        update_result = client.update_profile(
            folder_id, profile_id, {"proxy_id": proxy_id}
        )
        if _profile_has_proxy(update_result, proxy_id):
            return proxy_id

        profile = client.get_profile_by_id(folder_id, profile_id)
        if profile and profile.get("proxy_id") == proxy_id:
            return proxy_id


def _start_profile_with_proxy_retry(
    client, folder_id: str, profile_id: str, profile_name: str, cdp_port: int
) -> tuple:
    start_result = client.start_profile(folder_id, profile_id, port=cdp_port)
    if start_result:
        return start_result, 1, None

    proxy_id = _attach_next_proxy_to_profile(
        client, folder_id, profile_id, profile_name
    )
    if not proxy_id:
        return None, 1, None

    time.sleep(2)
    return client.start_profile(folder_id, profile_id, port=cdp_port), 2, proxy_id


def _wait_for_port(port: int, timeout: int = 30) -> bool:
    start_time = time.time()
    while time.time() - start_time < timeout:
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(1)
            result = sock.connect_ex(("127.0.0.1", port))
            sock.close()
            if result == 0:
                return True
        except Exception:
            pass
        time.sleep(1)
    return False


def _is_process_alive(pid: int) -> bool:
    try:
        import ctypes

        kernel32 = ctypes.windll.kernel32
        handle = kernel32.OpenProcess(0x100000, False, pid)
        if handle:
            kernel32.CloseHandle(handle)
            return True
        return False
    except Exception:
        return False


def _kill_process_tree(pid: int) -> bool:
    try:
        result = subprocess.run(
            ["taskkill", "/F", "/T", "/PID", str(pid)],
            capture_output=True,
            text=True,
            timeout=10,
        )
        return result.returncode == 0
    except Exception as e:
        logger.error(f"Не удалось убить процесс {pid}: {e}")
        return False


def _run_tebor_for_profile(
    profile_uuid: str,
    port: int,
    profile_name: str,
    person_id: Optional[str] = None,
) -> tuple:
    """
    Запускает run_tebor.py для одного профиля.
    Возвращает кортеж (PID процесса, console_title) или (None, None) при ошибке.
    """
    run_tebor_path = BROWSER_VISION_PATH / "run_tebor.py"
    console_title = f"Tebor - {profile_name} ({profile_uuid[:8]}...)"

    # Определяем папку с фото
    photo_folder = None
    if person_id:
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
        time.sleep(2)  # Небольшая задержка перед открытием окна
        process = subprocess.Popen(
            cmd,
            creationflags=subprocess.CREATE_NEW_CONSOLE,
        )
        pid = process.pid
        logger.info(f"🚀 Запущен tebor для '{profile_name}' (PID {pid}, порт {port})")
        return pid, console_title
    except Exception as e:
        logger.error(f"❌ Не удалось запустить tebor для '{profile_name}': {e}")
        return None, None


def _kill_registered_tebor_for_profile(profile_id: str) -> int:
    """Закрывает tebor для профиля, читая PID из state_manager."""
    killed = 0
    profile_data = state_manager.get(profile_id)
    if not profile_data:
        return 0

    pid = profile_data.get("tebor_pid")
    if pid and _is_process_alive(pid):
        logger.info(f"   🔪 Убиваем процесс tebor (PID {pid}) для {profile_id}")
        if _kill_process_tree(pid):
            killed += 1
        else:
            logger.warning(f"   ⚠️ Не удалось убить tebor PID {pid}")
    return killed


# ================== ОСНОВНЫЕ ФУНКЦИИ ==================
def launch_all_profiles(auto_start_tebor: bool = True) -> Dict:
    logger.info(f"🚀 Запуск всех профилей (auto_start_tebor={auto_start_tebor})")
    result = {
        "success": False,
        "launched": 0,
        "failed": 0,
        "already_running": 0,
        "tebor_started": 0,
        "proxy_changed": 0,
        "tracked": 0,
        "profiles": [],
    }

    try:
        from api_client import BrowserVisionClient
        from config import FOLDER_ID
        from profile_creator import ProfileCreator

        client = BrowserVisionClient(debug=False)
        if not client.test_connection():
            result["error"] = "Не удалось подключиться к API"
            return result

        profiles_data = client.get_profiles(FOLDER_ID)
        if not profiles_data:
            result["error"] = "Не удалось получить профили"
            return result

        profiles = profiles_data.get("items", [])
        if not profiles:
            result["error"] = "В группе нет профилей"
            return result

        for i, profile in enumerate(profiles, 1):
            profile_name = profile.get("profile_name", "N/A")
            profile_id = _get_profile_identifier(profile)
            person_id = _extract_person_id_from_profile(profile)

            if not profile_id:
                logger.warning(f"[{i}/{len(profiles)}] ⚠️ '{profile_name}' без ID")
                result["failed"] += 1
                continue

            actual_port = _get_profile_port(profile)
            changed_proxy_id = None

            if profile.get("running"):
                result["already_running"] += 1
            else:
                cdp_port = ProfileCreator.generate_cdp_port()
                start_result, start_attempts, changed_proxy_id = (
                    _start_profile_with_proxy_retry(
                        client, FOLDER_ID, profile_id, profile_name, cdp_port
                    )
                )
                if changed_proxy_id:
                    result["proxy_changed"] += 1
                if not start_result:
                    result["failed"] += 1
                    continue
                actual_port = start_result.get("port") or cdp_port
                result["launched"] += 1

            if actual_port and not _wait_for_port(actual_port, timeout=30):
                logger.warning(f"   ⚠️ Порт {actual_port} не стал доступен за 30 сек")

            tebor_pid = None
            console_title = None

            # Проверяем, не запущен ли tebor уже ранее (например, если профиль был running)
            existing_data = state_manager.get(profile_id)
            existing_tebor_pid = (
                existing_data.get("tebor_pid") if existing_data else None
            )
            tebor_alive = bool(
                existing_tebor_pid and _is_process_alive(existing_tebor_pid)
            )

            if auto_start_tebor and actual_port:
                if tebor_alive:
                    tebor_pid = existing_tebor_pid
                    console_title = existing_data.get("console_title")
                else:
                    # Запускаем tebor и получаем PID + заголовок окна
                    tebor_pid, console_title = _run_tebor_for_profile(
                        profile_id, actual_port, profile_name, person_id
                    )
                    if tebor_pid:
                        result["tebor_started"] += 1

            # Сохраняем в ЕДИНЫЙ state_manager ТОЛЬКО после успешного запуска
            state_manager.add(
                profile_id=profile_id,
                port=actual_port,
                name=profile_name,
                person_id=person_id,
                tebor_pid=tebor_pid,
                console_title=console_title,
                source="auto_runner",
            )
            result["tracked"] += 1

            # Пауза между запусками, чтобы не перегружать API и ПК
            if i % 5 == 0 and i < len(profiles):
                logger.info(f"   ⏸️ Пауза после {i} профилей (10 сек)...")
                time.sleep(10)
            else:
                time.sleep(3)

        result["success"] = True
        logger.info(
            f"✅ Итог: запущено {result['launched']}, уже работали {result['already_running']}, "
            f"tebor запущено {result['tebor_started']}, proxy заменено {result['proxy_changed']}, "
            f"отслеживается {result['tracked']}, ошибок {result['failed']}"
        )
        return result

    except Exception as e:
        logger.exception(f"❌ Критическая ошибка: {e}")
        result["error"] = str(e)
        return result


def stop_all_profiles() -> Dict:
    """
    Останавливает все профили из state_manager.
    Логика полностью синхронизирована с menu_stop_multiple из main.py,
    но с защитой от зависания API и принудительным закрытием консолей tebor.
    """
    from window_utils import kill_console_and_process

    logger.info("⛔ Остановка всех отслеживаемых профилей (через state_manager)")
    result = {
        "success": False,
        "stopped": 0,
        "failed": 0,
        "tebor_killed": 0,
        "profiles": [],
    }

    try:
        from api_client import BrowserVisionClient
        from config import FOLDER_ID

        client = BrowserVisionClient(debug=False)
        if not client.test_connection():
            result["error"] = "Не удалось подключиться к API"
            return result

        # 1. Читаем ТОЛЬКО из state_manager (как это делает main.py)
        stop_map = state_manager.get_all()
        if not stop_map:
            logger.info("⚫ В state_manager нет активных профилей")
            result["success"] = True
            return result

        for i, (profile_id, data) in enumerate(list(stop_map.items()), 1):
            profile_name = data.get("name", "N/A")
            logger.info(
                f"[{i}/{len(stop_map)}] ⛔ Остановка '{profile_name}' ({profile_id})"
            )

            # 2. Отправляем команду остановки в API (с повторными попытками)
            stop_success = False
            for attempt in range(3):
                try:
                    # API запрос
                    api_result = client.stop_profile(FOLDER_ID, profile_id)
                    if api_result is not None:
                        stop_success = True
                        break
                except Exception as e:
                    logger.warning(f"   ⚠️ Попытка {attempt + 1} не удалась: {e}")
                    time.sleep(1)

            # 3. ВСЕГДА удаляем из state_manager, чтобы не осталось "зомби"
            state_manager.remove(profile_id)

            if stop_success:
                result["stopped"] += 1
                logger.info("   ✅ Браузер остановлен через API")
            else:
                result["failed"] += 1
                logger.warning(
                    "   ❌ API не подтвердило остановку, но запись удалена из трекинга"
                )

            # 4. Убиваем консоль tebor (этого не было в старом main.py, но это необходимо)
            console_title = data.get("console_title", "")
            tebor_pid = data.get("tebor_pid")

            if console_title or tebor_pid:
                killed = kill_console_and_process(console_title, tebor_pid)
                result["tebor_killed"] += killed
            if tebor_pid:
                try:
                    # Принудительное закрытие дерева процессов
                    kill_cmd = ["taskkill", "/F", "/T", "/PID", str(tebor_pid)]
                    proc = subprocess.run(
                        kill_cmd, capture_output=True, text=True, timeout=5
                    )
                    if proc.returncode == 0:
                        result["tebor_killed"] += 1
                        logger.info(f"   🔪 Консоль tebor (PID {tebor_pid}) закрыта")
                except Exception as e:
                    logger.debug(
                        f"   ⚠️ Не удалось убить tebor PID {tebor_pid} (возможно, уже закрыт): {e}"
                    )

            result["profiles"].append(
                {"name": profile_name, "uuid": profile_id, "status": "stopped"}
            )
            time.sleep(0.5)

        result["success"] = True
        logger.info(
            f"✅ Итог: остановлено {result['stopped']}, консолей закрыто {result['tebor_killed']}"
        )
        return result

    except Exception as e:
        logger.exception(f"❌ Критическая ошибка: {e}")
        result["error"] = str(e)
        return result


def get_running_profiles() -> Dict:
    result = {"success": False, "count": 0, "profiles": []}
    try:
        # Читаем ЕДИНЫЙ state_manager
        active_map = state_manager.get_all()
        result["success"] = True
        result["count"] = len(active_map)
        for pid, data in active_map.items():
            tebor_pid = data.get("tebor_pid")
            result["profiles"].append(
                {
                    "name": data.get("name", "N/A"),
                    "uuid": pid,
                    "port": data.get("port"),
                    "person_id": data.get("person_id"),
                    "tebor_pid": tebor_pid,
                    "tebor_alive": bool(tebor_pid and _is_process_alive(tebor_pid)),
                }
            )
        return result
    except Exception as e:
        result["error"] = str(e)
        return result


# ================== ОБЁРТКИ ==================
def quick_start_all() -> str:
    result = launch_all_profiles(auto_start_tebor=True)
    if not result["success"]:
        return f"❌ Ошибка запуска: {result.get('error')}"
    return f"✅ Запуск завершён\n🟢 Новых: {result['launched']}\n⚫ Уже работали: {result['already_running']}\n🚀 tebor: {result['tebor_started']}"


def quick_stop_all() -> str:
    result = stop_all_profiles()
    if not result["success"]:
        return f"❌ Ошибка остановки: {result.get('error')}"
    return f"⛔ Остановка завершена\n✅ Остановлено: {result['stopped']}\n🔪 Закрыто tebor: {result['tebor_killed']}"


def quick_status() -> str:
    result = get_running_profiles()
    if not result["success"]:
        return f"❌ Ошибка: {result.get('error')}"
    if result["count"] == 0:
        return "⚫ Нет запущенных профилей"
    lines = [f"🟢 Запущено профилей: {result['count']}\n"]
    for p in result["profiles"]:
        tebor_status = "🟢" if p.get("tebor_alive") else "⚫"
        lines.append(
            f"  • {p['name']} (порт {p.get('port', 'N/A')}) tebor:{tebor_status}"
        )
    return "\n".join(lines)


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument("action", choices=["start", "stop", "status"])
    parser.add_argument("--no-tebor", action="store_true")
    args = parser.parse_args()

    if args.action == "start":
        print(
            quick_start_all()
            if not args.no_tebor
            else launch_all_profiles(auto_start_tebor=False)
        )
    elif args.action == "stop":
        print(quick_stop_all())
    elif args.action == "status":
        print(quick_status())
