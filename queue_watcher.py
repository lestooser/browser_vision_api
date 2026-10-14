"""
queue_watcher.py
Независимый фоновый диспетчер очереди профилей.
"""

import logging
import subprocess
import time

import queue_manager
import state_manager
import tebor_state
from api_client import BrowserVisionClient
from auto_runner import _is_process_alive, _run_tebor_for_profile
from config import FOLDER_ID
from profile_creator import ProfileCreator

logger = logging.getLogger("QueueWatcher")

# 🆕 НАСТРОЙКА ПОВЕДЕНИЯ ПРИ КРАШЕ КОНСОЛИ:
# "close" - Автоматически закрывать браузер (через API + принудительно по порту) и удалять из трекинга.
# "keep"  - Оставлять браузер висеть, но помечать профиль как "CRASHED" для ручного закрытия (не занимает слот).
ON_CONSOLE_CRASH = "keep"

MAX_ACTIVE_PROFILES = 10


def _kill_process_tree(pid: int) -> bool:
    if not pid:
        return False
    try:
        result = subprocess.run(
            ["taskkill", "/F", "/T", "/PID", str(pid)],
            capture_output=True,
            text=True,
            timeout=5,
        )
        return result.returncode == 0
    except Exception:
        return False


def _kill_process_by_port(port: int):
    """🆕 Принудительно убивает процесс, слушающий указанный порт (на случай, если API не закрыло браузер)."""
    if not port:
        return
    try:
        result = subprocess.run(
            f"netstat -ano | findstr :{port} | findstr LISTENING",
            capture_output=True,
            text=True,
            shell=True,
            timeout=5,
        )
        for line in result.stdout.splitlines():
            parts = line.split()
            if parts:
                pid = parts[-1]
                if pid.isdigit() and pid != "0":
                    subprocess.run(
                        ["taskkill", "/F", "/T", "/PID", pid],
                        capture_output=True,
                        timeout=5,
                    )
                    logger.info(
                        f"🔪 Принудительно убит процесс браузера (PID {pid}) на порту {port}"
                    )
    except Exception as e:
        logger.debug(f"Не удалось убить процесс по порту {port}: {e}")


def _send_tg_notification(message: str):
    import os
    from datetime import datetime

    tg_event_dir = os.path.join("logs", "tg_events")
    os.makedirs(tg_event_dir, exist_ok=True)
    filename = f"{datetime.now().strftime('%Y%m%d%H%M%S%f')}_watcher_notice.txt"
    try:
        with open(os.path.join(tg_event_dir, filename), "w", encoding="utf-8") as f:
            f.write(message)
    except Exception:
        pass


def queue_watcher_loop():
    logger.info(
        f"👁️ Watcher очереди запущен. Лимит: {MAX_ACTIVE_PROFILES}, Поведение при краше: {ON_CONSOLE_CRASH}"
    )
    client = BrowserVisionClient(debug=False)

    while True:
        try:
            active_map = state_manager.get_all()
            alive_count = 0

            for pid, data in list(active_map.items()):
                tebor_pid = data.get("tebor_pid")
                profile_name = data.get("name", "N/A")
                actual_port = data.get("port")
                status = data.get("status")

                # Если профиль уже помечен как CRASHED (в режиме keep), он не занимает слот
                if status == "CRASHED":
                    continue

                if tebor_pid and _is_process_alive(tebor_pid):
                    alive_count += 1
                else:
                    # Консоль мертва
                    if ON_CONSOLE_CRASH == "keep":
                        logger.warning(
                            f"⚠️ Консоль tebor для '{profile_name}' мертва. Браузер оставлен висеть для ручного закрытия."
                        )
                        state_manager.update(
                            pid,
                            {
                                "tebor_pid": None,
                                "status": "CRASHED",
                                "crash_message": "Консоль tebor упала. Браузер висит.",
                            },
                        )
                        tebor_state.set_state(
                            pid, "Краш", "Консоль упала, браузер висит"
                        )
                        _send_tg_notification(
                            f"⚠️ <b>{profile_name}</b>\nКонсоль tebor упала. Браузер оставлен висеть.\nЗакройте его вручную через меню остановки."
                        )

                    else:  # "close"
                        logger.info(
                            f"🧹 Консоль tebor для '{profile_name}' мертва. Закрываю браузер и удаляю из трекинга."
                        )

                        # 1. Пытаемся закрыть через API
                        try:
                            client.stop_profile(FOLDER_ID, pid)
                        except Exception:
                            pass

                        # 2. 🆕 Принудительно убиваем браузер по CDP-порту, если API не справилось
                        if actual_port:
                            _kill_process_by_port(actual_port)

                        # 3. Чистим трекинг
                        state_manager.remove(pid)
                        tebor_state.clear_state(pid)

                        _send_tg_notification(
                            f"❌ <b>{profile_name}</b>\nКонсоль tebor упала. Браузер автоматически закрыт."
                        )

            # Запускаем из очереди, если есть места
            if alive_count < MAX_ACTIVE_PROFILES:
                slots_available = MAX_ACTIVE_PROFILES - alive_count
                queue_count = queue_manager.get_count()

                if queue_count > 0:
                    logger.info(
                        f"🟢 Свободно слотов: {slots_available}, в очереди: {queue_count}. Запускаю..."
                    )
                    for _ in range(min(slots_available, queue_count)):
                        next_profile = queue_manager.get_next()
                        if not next_profile:
                            break

                        uuid = next_profile["uuid"]
                        name = next_profile["name"]
                        person_id = next_profile.get("person_id")

                        if state_manager.get(uuid):
                            continue

                        cdp_port = ProfileCreator.generate_cdp_port()
                        try:
                            start_result = client.start_profile(
                                FOLDER_ID, uuid, port=cdp_port
                            )
                            if start_result:
                                actual_port = start_result.get("port") or cdp_port
                                pid, console_title = _run_tebor_for_profile(
                                    uuid, actual_port, name, person_id
                                )
                                state_manager.add(
                                    uuid,
                                    actual_port,
                                    name,
                                    person_id,
                                    tebor_pid=pid,
                                    console_title=console_title,
                                    source="queue_watcher",
                                )
                                logger.info(f"✅ Watcher запустил '{name}' из очереди")
                            else:
                                logger.warning(f"❌ Watcher: API не запустило {name}")
                        except Exception as e:
                            logger.error(f"❌ Ошибка запуска из очереди {name}: {e}")
                        time.sleep(2)
        except Exception as e:
            logger.error(f"⚠️ Ошибка в цикле Watcher: {e}")

        time.sleep(15)


def start_queue_watcher():
    import threading

    threading.Thread(target=queue_watcher_loop, daemon=True).start()
