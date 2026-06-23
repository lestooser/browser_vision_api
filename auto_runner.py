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


# ================== ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ ==================
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


def launch_all_profiles(
    auto_start_tebor: bool = True,
) -> Dict:
    """
    Запускает ВСЕ профили из рабочей группы FOLDER_ID.
    Работает аналогично запуску нескольких профилей через main.py:
    - Запуск профилей через API
    - Ожидание доступности CDP-порта
    - Запуск tebor.py с автовыбором папки по ID человека
    - Регистрация PID процессов tebor для последующей остановки

    Returns:
        dict с результатами
    """
    logger.info(f"🚀 Запуск всех профилей (auto_start_tebor={auto_start_tebor})")

    result = {
        "success": False,
        "launched": 0,
        "failed": 0,
        "already_running": 0,
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

        # Получаем все профили
        profiles_data = client.get_profiles(FOLDER_ID)
        if not profiles_data:
            logger.error("❌ Не удалось получить профили")
            result["error"] = "Не удалось получить профили"
            return result

        profiles = profiles_data.get("items", [])
        total = profiles_data.get("total", 0)

        logger.info(f"📊 Найдено профилей: {total}")

        if not profiles:
            logger.warning("⚠️ В группе нет профилей")
            result["error"] = "В группе нет профилей"
            return result

        launched_count = 0
        failed_count = 0
        already_running = 0

        for i, profile in enumerate(profiles, 1):
            profile_name = profile.get("profile_name", "N/A")
            profile_uuid = (
                profile.get("uuid")
                or profile.get("profile_id")
                or str(profile.get("id"))
            )
            person_id = _extract_person_id_from_profile(profile)

            # Проверяем, не запущен ли уже
            if profile.get("running"):
                logger.info(f"[{i}/{len(profiles)}] ⚫ '{profile_name}' уже запущен")
                already_running += 1
                result["profiles"].append(
                    {
                        "name": profile_name,
                        "uuid": profile_uuid,
                        "status": "already_running",
                        "person_id": person_id,
                    }
                )
                continue

            # Генерируем порт
            cdp_port = ProfileCreator.generate_cdp_port()
            logger.info(
                f"[{i}/{len(profiles)}] 🟢 Запуск '{profile_name}' на порту {cdp_port}"
            )

            # Запускаем профиль
            start_result = client.start_profile(FOLDER_ID, profile_uuid, port=cdp_port)

            if start_result:
                actual_port = start_result.get("port") or cdp_port
                logger.info(f"   ✅ Запущен | CDP: http://127.0.0.1:{actual_port}")

                # Ждём доступности порта
                if _wait_for_port(actual_port, timeout=30):
                    logger.info(f"   ✅ Порт {actual_port} доступен")
                else:
                    logger.warning(
                        f"   ⚠️ Порт {actual_port} не стал доступен за 30 сек"
                    )

                # Запускаем tebor, если нужно
                tebor_pid = None
                if auto_start_tebor:
                    tebor_pid = _run_tebor_for_profile(
                        profile_uuid, actual_port, profile_name, person_id
                    )

                launched_count += 1
                result["profiles"].append(
                    {
                        "name": profile_name,
                        "uuid": profile_uuid,
                        "port": actual_port,
                        "status": "launched",
                        "tebor_pid": tebor_pid,
                        "person_id": person_id,
                    }
                )
            else:
                logger.error(f"   ❌ Не удалось запустить '{profile_name}'")
                failed_count += 1
                result["profiles"].append(
                    {
                        "name": profile_name,
                        "uuid": profile_uuid,
                        "status": "failed",
                        "person_id": person_id,
                    }
                )

            # Небольшая пауза между запусками
            time.sleep(3)

            # Каждые 5 профилей — делаем паузу подольше, чтобы система "переварила"
            if i % 5 == 0 and i < len(profiles):
                logger.info(f"   ⏸️ Пауза после {i} профилей (10 сек)...")
                time.sleep(10)

        result["success"] = True
        result["launched"] = launched_count
        result["failed"] = failed_count
        result["already_running"] = already_running

        logger.info(
            f"✅ Итог: запущено {launched_count}, "
            f"уже работали {already_running}, "
            f"ошибок {failed_count}"
        )

        return result

    except Exception as e:
        logger.exception(f"❌ Критическая ошибка: {e}")
        result["error"] = str(e)
        return result


def stop_all_profiles() -> Dict:
    """
    Останавливает ВСЕ профили в рабочей группе и закрывает их консоли tebor.

    Логика:
    1. Получает список всех профилей из API
    2. Для каждого запущенного профиля:
       a. Останавливает профиль через API (с проверкой и повторами)
       b. Находит PID процесса tebor (из tebor_processes.json)
       c. Убивает процесс tebor (вместе с консолью)
       d. Проверяет, что профиль действительно остановлен

    Returns:
        dict с результатами
    """
    logger.info("⛔ Остановка всех профилей и их консолей tebor")

    result = {
        "success": False,
        "stopped": 0,
        "failed": 0,
        "skipped": 0,
        "tebor_killed": 0,
        "profiles": [],
    }

    try:
        import requests as req_lib

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
        total = profiles_data.get("total", 0)

        logger.info(f"📊 Найдено профилей: {total}")

        if not profiles:
            logger.warning("⚠️ В группе нет профилей")
            result["error"] = "В группе нет профилей"
            return result

        # Загружаем список процессов tebor
        tebor_processes = _load_tebor_processes()

        stopped_count = 0
        failed_count = 0
        skipped_count = 0
        tebor_killed = 0

        for i, profile in enumerate(profiles, 1):
            profile_name = profile.get("profile_name", "N/A")

            # 🆕 ВАЖНО: используем 'id' как основной идентификатор
            profile_uuid = (
                profile.get("id") or profile.get("uuid") or profile.get("profile_id")
            )

            if not profile_uuid:
                logger.warning(
                    f"[{i}/{len(profiles)}] ⚠️ '{profile_name}' не имеет ID — пропускаем"
                )
                skipped_count += 1
                continue

            is_running = profile.get("running", False)

            # Пропускаем незапущенные
            if not is_running:
                logger.info(
                    f"[{i}/{len(profiles)}] ⚫ '{profile_name}' не запущен — пропускаем"
                )
                skipped_count += 1
                result["profiles"].append(
                    {
                        "name": profile_name,
                        "uuid": profile_uuid,
                        "status": "skipped",
                    }
                )
                continue

            logger.info(
                f"[{i}/{len(profiles)}] ⛔ Остановка '{profile_name}' (ID: {profile_uuid})..."
            )

            # 🆕 ШАГ 1: Пытаемся остановить профиль через API с повторами
            stop_success = False
            for attempt in range(3):
                try:
                    # Способ 1: через клиент
                    stop_result = client.stop_profile(FOLDER_ID, profile_uuid)

                    if stop_result is not None:
                        logger.info(
                            f"   ✅ Попытка {attempt + 1}: stop_profile вернул результат"
                        )
                        stop_success = True
                        break

                    # Способ 2: прямой HTTP-запрос к API
                    logger.info(
                        f"   🔄 Попытка {attempt + 1}: пробуем прямой HTTP-запрос..."
                    )
                    from config import LOCAL_URL, TOKEN

                    url = f"{LOCAL_URL}/stop/{FOLDER_ID}/{profile_uuid}"
                    headers = {"Authorization": f"Bearer {TOKEN}"}

                    response = req_lib.get(url, headers=headers, timeout=10)

                    if response.status_code == 200:
                        logger.info(
                            f"   ✅ Прямой запрос успешен (статус {response.status_code})"
                        )
                        stop_success = True
                        break
                    else:
                        logger.warning(
                            f"   ⚠️ Прямой запрос вернул статус {response.status_code}"
                        )

                except Exception as e:
                    logger.warning(f"   ⚠️ Попытка {attempt + 1} не удалась: {e}")

                if attempt < 2:
                    time.sleep(1)

            # 🆕 ШАГ 2: Проверяем, что профиль действительно остановлен
            if stop_success:
                time.sleep(1)  # Даём API время обновить статус

                # Повторно получаем профиль
                try:
                    check_profile = client.get_profile_by_id(FOLDER_ID, profile_uuid)
                    if check_profile and not check_profile.get("running"):
                        logger.info("   ✅ Профиль действительно остановлен")
                        stopped_count += 1
                    elif check_profile and check_profile.get("running"):
                        logger.warning(
                            "   ⚠️ Профиль всё ещё запущен! Принудительная остановка..."
                        )
                        # Принудительная остановка через прямой запрос
                        try:
                            from config import LOCAL_URL, TOKEN

                            url = f"{LOCAL_URL}/stop/{FOLDER_ID}/{profile_uuid}"
                            headers = {"Authorization": f"Bearer {TOKEN}"}
                            req_lib.get(url, headers=headers, timeout=10)
                            time.sleep(1)

                            # Ещё раз проверяем
                            check_profile = client.get_profile_by_id(
                                FOLDER_ID, profile_uuid
                            )
                            if check_profile and not check_profile.get("running"):
                                logger.info("   ✅ Принудительная остановка успешна")
                                stopped_count += 1
                            else:
                                logger.error("   ❌ Не удалось остановить профиль")
                                failed_count += 1
                        except Exception as e:
                            logger.error(f"   ❌ Ошибка принудительной остановки: {e}")
                            failed_count += 1
                    else:
                        # Не удалось получить профиль, но stop_profile вернул результат
                        logger.info("   ✅ Предполагаем, что профиль остановлен")
                        stopped_count += 1
                except Exception as e:
                    logger.warning(f"   ⚠️ Не удалось проверить статус: {e}")
                    stopped_count += (
                        1  # Считаем остановленным, т.к. stop_profile вернул результат
                    )
            else:
                logger.error("   ❌ Все попытки остановки не удались")
                failed_count += 1

            # 🆕 ШАГ 3: Убиваем процесс tebor, если он зарегистрирован
            if profile_uuid in tebor_processes:
                tebor_info = tebor_processes[profile_uuid]
                pid = tebor_info.get("pid")
                if pid and _is_process_alive(pid):
                    logger.info(f"   🔪 Убиваем процесс tebor (PID {pid})...")
                    if _kill_process_tree(pid):
                        logger.info("   ✅ Процесс tebor убит")
                        tebor_killed += 1
                    else:
                        logger.warning("   ⚠️ Не удалось убить процесс tebor")
                else:
                    logger.info("   ℹ️ Процесс tebor уже не активен")

                # Удаляем из списка
                _unregister_tebor_process(profile_uuid)

            # Также ищем по UUID из других полей
            for alt_uuid in [profile.get("uuid"), profile.get("profile_id")]:
                if (
                    alt_uuid
                    and alt_uuid in tebor_processes
                    and alt_uuid != profile_uuid
                ):
                    tebor_info = tebor_processes[alt_uuid]
                    pid = tebor_info.get("pid")
                    if pid and _is_process_alive(pid):
                        logger.info(
                            f"   🔪 Убиваем процесс tebor (альт. UUID, PID {pid})..."
                        )
                        if _kill_process_tree(pid):
                            tebor_killed += 1
                    _unregister_tebor_process(alt_uuid)

            result["profiles"].append(
                {
                    "name": profile_name,
                    "uuid": profile_uuid,
                    "status": "stopped" if stop_success else "failed",
                }
            )

            # Небольшая пауза между остановками
            time.sleep(0.5)

        # Дополнительная очистка: убиваем все оставшиеся tebor-процессы
        remaining = _load_tebor_processes()
        for uuid, info in remaining.items():
            pid = info.get("pid")
            if pid and _is_process_alive(pid):
                logger.info(
                    f"🔪 Дополнительная очистка: убиваем tebor для {uuid} (PID {pid})"
                )
                if _kill_process_tree(pid):
                    tebor_killed += 1
                _unregister_tebor_process(uuid)

        result["success"] = True
        result["stopped"] = stopped_count
        result["failed"] = failed_count
        result["skipped"] = skipped_count
        result["tebor_killed"] = tebor_killed

        logger.info(
            f"✅ Итог: остановлено {stopped_count}, "
            f"консолей tebor закрыто {tebor_killed}, "
            f"пропущено {skipped_count}, "
            f"ошибок {failed_count}"
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
                    "tebor_alive": _is_process_alive(tebor_info.get("pid", 0))
                    if tebor_info.get("pid")
                    else False,
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
        f"🟢 Запущено: {result['launched']}\n"
        f"⚫ Уже работали: {result['already_running']}\n"
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
