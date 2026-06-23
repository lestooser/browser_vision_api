"""
Модуль для автоматического запуска и остановки всех профилей.
Работает аналогично запуску нескольких профилей через main.py,
но для всех профилей в группе.
"""

import json
import logging
import os
import socket
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Dict, Optional

# Пути
BROWSER_VISION_PATH = Path(__file__).parent
LOG_DIR = BROWSER_VISION_PATH / "logs"
TEBOR_PROCESSES_FILE = LOG_DIR / "tebor_processes.json"
ACTIVE_PROFILES_FILE = LOG_DIR / "active_profiles.json"

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


# ================== УПРАВЛЕНИЕ СПИСКОМ ПРОЦЕССОВ TEBOR ==================
def _load_tebor_processes() -> Dict[str, dict]:
    """Загружает список запущенных процессов tebor из файла."""
    if TEBOR_PROCESSES_FILE.exists():
        try:
            with open(TEBOR_PROCESSES_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception as e:
            logger.warning(f"Не удалось загрузить tebor_processes.json: {e}")
    return {}


def _save_tebor_processes(processes: Dict[str, dict]) -> None:
    """Сохраняет список запущенных процессов tebor в файл."""
    try:
        with open(TEBOR_PROCESSES_FILE, "w", encoding="utf-8") as f:
            json.dump(processes, f, ensure_ascii=False, indent=2)
    except Exception as e:
        logger.error(f"Не удалось сохранить tebor_processes.json: {e}")


def _register_tebor_process(
    profile_uuid: str,
    pid: int,
    port: int,
    profile_name: str,
    person_id: Optional[str] = None,
):
    """Регистрирует запущенный процесс tebor."""
    processes = _load_tebor_processes()
    processes[profile_uuid] = {
        "pid": pid,
        "port": port,
        "name": profile_name,
        "person_id": person_id,
        "started_at": datetime.now().isoformat(),
    }
    _save_tebor_processes(processes)
    logger.info(f"Зарегистрирован tebor процесс: {profile_name} (PID {pid})")


def _unregister_tebor_process(profile_uuid: str):
    """Удаляет регистрацию процесса tebor."""
    processes = _load_tebor_processes()
    if profile_uuid in processes:
        del processes[profile_uuid]
        _save_tebor_processes(processes)


# ================== УПРАВЛЕНИЕ СПИСКОМ АКТИВНЫХ ПРОФИЛЕЙ ==================
def _load_active_profiles() -> Dict[str, dict]:
    """Загружает профили, запущенные автоматикой/ботом этого проекта."""
    if ACTIVE_PROFILES_FILE.exists():
        try:
            with open(ACTIVE_PROFILES_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception as e:
            logger.warning(f"Не удалось загрузить active_profiles.json: {e}")
    return {}


def _save_active_profiles(profiles: Dict[str, dict]) -> None:
    """Сохраняет карту активных профилей аналогично active_map из main.py."""
    try:
        with open(ACTIVE_PROFILES_FILE, "w", encoding="utf-8") as f:
            json.dump(profiles, f, ensure_ascii=False, indent=2)
    except Exception as e:
        logger.error(f"Не удалось сохранить active_profiles.json: {e}")


def _register_active_profile(
    profile_id: str,
    port: Optional[int],
    profile_name: str,
    person_id: Optional[str] = None,
    tebor_pid: Optional[int] = None,
) -> None:
    """Регистрирует запущенный профиль для последующей остановки через бота."""
    if not profile_id:
        return
    active_profiles = _load_active_profiles()
    current = active_profiles.get(profile_id, {})
    current.update(
        {
            "port": port,
            "name": profile_name,
            "person_id": person_id,
            "tebor_pid": tebor_pid or current.get("tebor_pid"),
            "started_at": current.get("started_at") or datetime.now().isoformat(),
            "updated_at": datetime.now().isoformat(),
        }
    )
    active_profiles[profile_id] = current
    _save_active_profiles(active_profiles)


def _unregister_active_profile(profile_id: str) -> None:
    """Удаляет профиль из persistent active_map."""
    active_profiles = _load_active_profiles()
    if profile_id in active_profiles:
        del active_profiles[profile_id]
        _save_active_profiles(active_profiles)


# ================== ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ ==================


def _get_profile_identifier(profile: dict) -> Optional[str]:
    """Возвращает идентификатор профиля так же, как пункты меню main.py."""
    profile_id = profile.get("uuid") or profile.get("profile_id") or profile.get("id")
    return str(profile_id) if profile_id is not None else None


def _get_profile_port(profile: dict) -> Optional[int]:
    """Достаёт CDP-порт из разных возможных полей ответа API."""
    port = profile.get("port") or profile.get("debug_port") or profile.get("cdp_port")
    try:
        return int(port) if port else None
    except (TypeError, ValueError):
        return None


def _extract_person_id_from_profile(profile: dict) -> Optional[str]:
    """Извлекает ID человека из имени профиля (формат: {id}-{город})."""
    profile_name = profile.get("profile_name", "")
    if not profile_name:
        return None
    if "-" in profile_name:
        person_id = profile_name.split("-")[0].strip()
        if person_id:
            return person_id
    return None


def _get_photo_folder_by_person_id(person_id: str) -> Optional[str]:
    """Возвращает путь к папке с фото по ID человека."""
    if not person_id:
        return None
    auto_folder = f"D:\\python\\selenium-test\\downloads\\extracted\\{person_id}"
    if os.path.exists(auto_folder):
        return auto_folder
    return None


def _wait_for_port(port: int, timeout: int = 30) -> bool:
    """Ждёт, пока порт станет доступен."""
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
    """Проверяет, жив ли процесс по PID."""
    try:
        import ctypes

        kernel32 = ctypes.windll.kernel32
        handle = kernel32.OpenProcess(0x100000, False, pid)  # SYNCHRONIZE
        if handle:
            kernel32.CloseHandle(handle)
            return True
        return False
    except Exception:
        return False


def _kill_process_tree(pid: int) -> bool:
    """Убивает процесс и его дочерние процессы по PID."""
    try:
        # Используем taskkill для Windows
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
) -> Optional[int]:
    """
    Запускает run_tebor.py для одного профиля.
    Возвращает PID процесса или None при ошибке.
    """
    run_tebor_path = BROWSER_VISION_PATH / "run_tebor.py"

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
        time.sleep(2)
        process = subprocess.Popen(
            cmd,
            creationflags=subprocess.CREATE_NEW_CONSOLE,
        )
        pid = process.pid
        logger.info(f"🚀 Запущен tebor для '{profile_name}' (PID {pid}, порт {port})")

        # Регистрируем процесс
        _register_tebor_process(profile_uuid, pid, port, profile_name, person_id)

        return pid
    except Exception as e:
        logger.error(f"❌ Не удалось запустить tebor для '{profile_name}': {e}")
        return None


# ================== ОСНОВНЫЕ ФУНКЦИИ ==================


def _kill_registered_tebor_for_profile(
    profile_id: str, profile: dict, tebor_processes: Dict[str, dict]
) -> int:
    """Закрывает зарегистрированный tebor/консоль для профиля по всем известным ID."""
    killed = 0
    ids_to_check = [profile_id, profile.get("uuid"), profile.get("profile_id")]
    if profile.get("id") is not None:
        ids_to_check.append(str(profile.get("id")))

    for candidate_id in dict.fromkeys(str(i) for i in ids_to_check if i):
        tebor_info = tebor_processes.get(candidate_id) or _load_tebor_processes().get(
            candidate_id
        )
        if not tebor_info:
            continue
        pid = tebor_info.get("pid")
        if pid and _is_process_alive(pid):
            logger.info(f"   🔪 Убиваем процесс tebor (PID {pid}) для {candidate_id}")
            if _kill_process_tree(pid):
                killed += 1
            else:
                logger.warning(f"   ⚠️ Не удалось убить tebor PID {pid}")
        _unregister_tebor_process(candidate_id)
    return killed


def launch_all_profiles(
    auto_start_tebor: bool = True,
) -> Dict:
    """
    Запускает ВСЕ профили из рабочей группы FOLDER_ID.

    Логика повторяет menu_launch_multiple_profiles/launch_selected_profiles,
    только без ручного выбора: берутся все профили, каждый успешно запущенный
    профиль записывается в persistent active_map (logs/active_profiles.json),
    чтобы /stop_all_profile видел именно те профили, которые открыл бот.
    """
    logger.info(f"🚀 Запуск всех профилей (auto_start_tebor={auto_start_tebor})")

    result = {
        "success": False,
        "launched": 0,
        "failed": 0,
        "already_running": 0,
        "tebor_started": 0,
        "tracked": 0,
        "profiles": [],
    }

    try:
        from api_client import BrowserVisionClient
        from config import FOLDER_ID
        from profile_creator import ProfileCreator

        client = BrowserVisionClient(debug=False)

        if not client.test_connection():
            logger.error("❌ Не удалось подключиться к API")
            result["error"] = "Не удалось подключиться к API"
            return result

        profiles_data = client.get_profiles(FOLDER_ID)
        if not profiles_data:
            logger.error("❌ Не удалось получить профили")
            result["error"] = "Не удалось получить профили"
            return result

        profiles = profiles_data.get("items", [])
        total = profiles_data.get("total", len(profiles))
        logger.info(f"📊 Найдено профилей: {total}")

        if not profiles:
            logger.warning("⚠️ В группе нет профилей")
            result["error"] = "В группе нет профилей"
            return result

        tebor_processes = _load_tebor_processes()
        active_profiles = _load_active_profiles()

        for i, profile in enumerate(profiles, 1):
            profile_name = profile.get("profile_name", "N/A")
            profile_id = _get_profile_identifier(profile)
            person_id = _extract_person_id_from_profile(profile)

            if not profile_id:
                logger.warning(f"[{i}/{len(profiles)}] ⚠️ '{profile_name}' без ID")
                result["failed"] += 1
                result["profiles"].append(
                    {"name": profile_name, "uuid": None, "status": "failed_no_id"}
                )
                continue

            logger.info(
                f"[{i}/{len(profiles)}] Обработка '{profile_name}' ({profile_id})"
            )
            actual_port = _get_profile_port(profile)
            status = "already_running" if profile.get("running") else "launched"

            if profile.get("running"):
                result["already_running"] += 1
                logger.info(f"   ⚫ Уже запущен")
            else:
                cdp_port = ProfileCreator.generate_cdp_port()
                logger.info(f"   🟢 Запуск на порту {cdp_port}")
                start_result = client.start_profile(
                    FOLDER_ID, profile_id, port=cdp_port
                )
                if not start_result:
                    logger.error(f"   ❌ Не удалось запустить '{profile_name}'")
                    result["failed"] += 1
                    result["profiles"].append(
                        {
                            "name": profile_name,
                            "uuid": profile_id,
                            "status": "failed",
                            "person_id": person_id,
                        }
                    )
                    continue
                actual_port = start_result.get("port") or cdp_port
                result["launched"] += 1
                logger.info(f"   ✅ Запущен | CDP: http://127.0.0.1:{actual_port}")

            if actual_port and _wait_for_port(actual_port, timeout=30):
                logger.info(f"   ✅ Порт {actual_port} доступен")
            elif actual_port:
                logger.warning(f"   ⚠️ Порт {actual_port} не стал доступен за 30 сек")
            else:
                logger.warning("   ⚠️ API не вернул CDP-порт")

            tebor_pid = None
            tebor_info = tebor_processes.get(profile_id) or {}
            existing_tebor_pid = tebor_info.get("pid") or active_profiles.get(
                profile_id, {}
            ).get("tebor_pid")
            tebor_alive = bool(
                existing_tebor_pid and _is_process_alive(existing_tebor_pid)
            )

            if auto_start_tebor and actual_port:
                if tebor_alive:
                    tebor_pid = existing_tebor_pid
                    logger.info(f"   ⚫ tebor уже запущен (PID {tebor_pid})")
                else:
                    tebor_pid = _run_tebor_for_profile(
                        profile_id, actual_port, profile_name, person_id
                    )
                    if tebor_pid:
                        result["tebor_started"] += 1
            elif auto_start_tebor and not actual_port:
                logger.warning("   ⚠️ tebor не запущен: неизвестен порт профиля")

            _register_active_profile(
                profile_id, actual_port, profile_name, person_id, tebor_pid
            )
            result["tracked"] += 1
            result["profiles"].append(
                {
                    "name": profile_name,
                    "uuid": profile_id,
                    "port": actual_port,
                    "status": status,
                    "tebor_pid": tebor_pid,
                    "person_id": person_id,
                }
            )

            time.sleep(3)
            if i % 5 == 0 and i < len(profiles):
                logger.info(f"   ⏸️ Пауза после {i} профилей (10 сек)...")
                time.sleep(10)

        result["success"] = True
        logger.info(
            f"✅ Итог: запущено {result['launched']}, уже работали {result['already_running']}, "
            f"tebor запущено {result['tebor_started']}, отслеживается {result['tracked']}, "
            f"ошибок {result['failed']}"
        )
        return result

    except Exception as e:
        logger.exception(f"❌ Критическая ошибка: {e}")
        result["error"] = str(e)
        return result


def stop_all_profiles() -> Dict:
    """
    Останавливает все профили, которые отслеживает бот, плюс все профили,
    которые API показывает как running.

    Это автоматический аналог menu_stop_multiple: сначала строится active_map
    из logs/active_profiles.json, затем он дополняется текущими running-профилями
    из API, после чего каждый профиль останавливается и удаляется из tracking.
    """
    logger.info("⛔ Остановка всех отслеживаемых/запущенных профилей")

    result = {
        "success": False,
        "stopped": 0,
        "failed": 0,
        "skipped": 0,
        "tebor_killed": 0,
        "profiles": [],
    }

    try:
        from api_client import BrowserVisionClient
        from config import FOLDER_ID

        client = BrowserVisionClient(debug=False)

        if not client.test_connection():
            logger.error("❌ Не удалось подключиться к API")
            result["error"] = "Не удалось подключиться к API"
            return result

        profiles_data = client.get_profiles(FOLDER_ID)
        if not profiles_data:
            logger.error("❌ Не удалось получить профили")
            result["error"] = "Не удалось получить профили"
            return result

        profiles = profiles_data.get("items", [])
        api_profiles_by_id = {
            _get_profile_identifier(profile): profile
            for profile in profiles
            if _get_profile_identifier(profile)
        }

        stop_map = _load_active_profiles()
        for profile_id, profile in api_profiles_by_id.items():
            if profile.get("running") and profile_id not in stop_map:
                stop_map[profile_id] = {
                    "name": profile.get("profile_name", "N/A"),
                    "port": _get_profile_port(profile),
                    "person_id": _extract_person_id_from_profile(profile),
                    "source": "api_running",
                }

        if not stop_map:
            logger.info("⚫ Нет отслеживаемых или запущенных профилей")
            result["success"] = True
            return result

        tebor_processes = _load_tebor_processes()

        for i, (profile_id, data) in enumerate(list(stop_map.items()), 1):
            profile = api_profiles_by_id.get(profile_id, {})
            profile_name = data.get("name") or profile.get("profile_name", "N/A")
            logger.info(
                f"[{i}/{len(stop_map)}] ⛔ Остановка '{profile_name}' ({profile_id})"
            )

            should_stop = bool(profile.get("running", True))
            stop_success = False
            if should_stop:
                try:
                    stop_result = client.stop_profile(FOLDER_ID, profile_id)
                    stop_success = stop_result is not None
                except Exception as e:
                    logger.warning(f"   ⚠️ stop_profile не удался: {e}")
                    stop_success = False
            else:
                logger.info("   ⚫ API считает профиль уже остановленным")
                result["skipped"] += 1
                stop_success = True

            if stop_success:
                time.sleep(1)
                check_profile = None
                try:
                    check_profile = client.get_profile_by_id(FOLDER_ID, profile_id)
                except Exception as e:
                    logger.warning(f"   ⚠️ Не удалось проверить статус: {e}")

                if check_profile and check_profile.get("running"):
                    logger.warning("   ⚠️ Профиль всё ещё running после stop_profile")
                    result["failed"] += 1
                    final_status = "failed"
                else:
                    if should_stop:
                        result["stopped"] += 1
                    final_status = "stopped" if should_stop else "skipped"
                    _unregister_active_profile(profile_id)
            else:
                result["failed"] += 1
                final_status = "failed"

            killed = _kill_registered_tebor_for_profile(
                profile_id, profile, tebor_processes
            )
            result["tebor_killed"] += killed

            result["profiles"].append(
                {
                    "name": profile_name,
                    "uuid": profile_id,
                    "status": final_status,
                    "tebor_killed": killed,
                }
            )
            time.sleep(0.5)

        # Дополнительная очистка: если остались зарегистрированные tebor-процессы,
        # они тоже были вызваны ботом/автоматикой и должны закрыться.
        for uuid, info in list(_load_tebor_processes().items()):
            pid = info.get("pid")
            if pid and _is_process_alive(pid):
                logger.info(f"🔪 Доп. очистка tebor для {uuid} (PID {pid})")
                if _kill_process_tree(pid):
                    result["tebor_killed"] += 1
            _unregister_tebor_process(uuid)

        result["success"] = True
        logger.info(
            f"✅ Итог: остановлено {result['stopped']}, "
            f"консолей tebor закрыто {result['tebor_killed']}, "
            f"пропущено {result['skipped']}, ошибок {result['failed']}"
        )
        return result

    except Exception as e:
        logger.exception(f"❌ Критическая ошибка: {e}")
        result["error"] = str(e)
        return result


def get_running_profiles() -> Dict:
    """Возвращает список всех запущенных профилей в группе."""
    result = {
        "success": False,
        "count": 0,
        "profiles": [],
    }

    try:
        from api_client import BrowserVisionClient
        from config import FOLDER_ID

        client = BrowserVisionClient(debug=False)
        profiles_data = client.get_profiles(FOLDER_ID)

        if not profiles_data:
            result["error"] = "Не удалось получить профили"
            return result

        profiles = profiles_data.get("items", [])
        running = [p for p in profiles if p.get("running")]

        # Загружаем информацию о tebor-процессах
        tebor_processes = _load_tebor_processes()

        result["success"] = True
        result["count"] = len(running)
        result["profiles"] = []

        for p in running:
            uuid = p.get("uuid") or p.get("profile_id") or str(p.get("id"))
            tebor_info = tebor_processes.get(uuid, {})
            result["profiles"].append(
                {
                    "name": p.get("profile_name", "N/A"),
                    "uuid": uuid,
                    "port": p.get("port") or p.get("debug_port"),
                    "person_id": _extract_person_id_from_profile(p),
                    "tebor_pid": tebor_info.get("pid"),
                    "tebor_alive": (
                        _is_process_alive(tebor_info.get("pid", 0))
                        if tebor_info.get("pid")
                        else False
                    ),
                }
            )

        return result

    except Exception as e:
        result["error"] = str(e)
        return result


# ================== УДОБНЫЕ ОБЁРТКИ ДЛЯ БОТА ==================


def quick_start_all() -> str:
    """Быстрый запуск всех профилей с tebor. Возвращает строку-отчёт."""
    result = launch_all_profiles(auto_start_tebor=True)

    if not result["success"]:
        return f"❌ Ошибка запуска: {result.get('error', 'неизвестно')}"

    report = (
        f"✅ Запуск завершён\n\n"
        f"🟢 Запущено новых: {result['launched']}\n"
        f"⚫ Уже работали: {result['already_running']}\n"
        f"🚀 tebor запущено: {result.get('tebor_started', 0)}\n"
        f"📌 Отслеживается профилей: {result.get('tracked', 0)}\n"
        f"❌ Ошибок: {result['failed']}"
    )
    return report


def quick_stop_all() -> str:
    """Быстрая остановка всех профилей и их консолей tebor. Возвращает строку-отчёт."""
    result = stop_all_profiles()

    if not result["success"]:
        return f"❌ Ошибка остановки: {result.get('error', 'неизвестно')}"

    report = (
        f"⛔ Остановка завершена\n\n"
        f"✅ Остановлено профилей: {result['stopped']}\n"
        f"🔪 Закрыто консолей tebor: {result['tebor_killed']}\n"
        f"⏭️ Пропущено (не запущены): {result['skipped']}\n"
        f"❌ Ошибок: {result['failed']}"
    )

    # 🆕 Добавляем детали по каждому профилю
    if result["profiles"]:
        report += "\n\n📋 Детали:\n"
        for p in result["profiles"][:15]:
            status_emoji = {
                "stopped": "✅",
                "failed": "❌",
                "skipped": "⏭️",
            }.get(p["status"], "❓")
            report += f"  {status_emoji} {p['name']}\n"

        if len(result["profiles"]) > 15:
            report += f"  ... и ещё {len(result['profiles']) - 15} профилей"

    return report


def quick_status() -> str:
    """Быстрый статус: сколько профилей запущено. Возвращает строку-отчёт."""
    result = get_running_profiles()

    if not result["success"]:
        return f"❌ Ошибка: {result.get('error', 'неизвестно')}"

    if result["count"] == 0:
        return "⚫ Нет запущенных профилей"

    lines = [f"🟢 Запущено профилей: {result['count']}\n"]
    for p in result["profiles"]:
        tebor_status = "🟢" if p.get("tebor_alive") else "⚫"
        lines.append(
            f"  • {p['name']} (порт {p.get('port', 'N/A')}) tebor:{tebor_status}"
        )

    return "\n".join(lines)


# ================== ТОЧКА ВХОДА ДЛЯ ПРЯМОГО ЗАПУСКА ==================

if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Автозапуск/остановка профилей")
    parser.add_argument(
        "action",
        choices=["start", "stop", "status"],
        help="Действие: start — запустить все, stop — остановить все, status — показать запущенные",
    )
    parser.add_argument(
        "--no-tebor",
        action="store_true",
        help="Не запускать tebor.py при старте",
    )

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
