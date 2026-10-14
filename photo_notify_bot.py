"""
Telegram-бот этого проекта для автономного управления профилями и уведомлений tebor.
"""

import html
import logging
import os
import threading
import time
from pathlib import Path

import telebot
from dotenv import load_dotenv
from telebot import apihelper

import queue_manager  # 🆕 Менеджер очереди
import state_manager  # Единый менеджер состояний
import tebor_state  # 🆕 Менеджер статусов
from api_client import BrowserVisionClient
from auto_runner import (
    _extract_person_id_from_profile,
    _get_photo_folder_by_person_id,
    _is_process_alive,
    _run_tebor_for_profile,
)
from config import FOLDER_ID
from profile_creator import ProfileCreator
from window_utils import (  # 🆕 Для убийства зомби
    kill_browser_by_port,
    kill_console_and_process,
)

load_dotenv()
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

TOKEN = os.getenv("TG_BOT_TOKEN")
CHAT_ID = os.getenv("TG_CHAT_ID")
if not TOKEN or not CHAT_ID:
    raise RuntimeError("❌ TG_BOT_TOKEN или TG_CHAT_ID не указаны в .env")
if not FOLDER_ID:
    raise RuntimeError("❌ FOLDER_ID не указан в .env")

BASE_DIR = Path(__file__).parent
PHOTO_NEEDED_DIR = BASE_DIR / "logs" / "photo_needed"
TG_EVENT_DIR = BASE_DIR / "logs" / "tg_events"
PHOTO_NEEDED_DIR.mkdir(parents=True, exist_ok=True)
TG_EVENT_DIR.mkdir(parents=True, exist_ok=True)

CHECK_INTERVAL_SECONDS = 30
RENOTIFY_INTERVAL_SECONDS = 5 * 60
RESTART_DELAY_SECONDS = 5  # 🆕 Пауза между закрытием и открытием при /menu 3
MAX_ACTIVE_PROFILES = 10  # 🆕 Лимит одновременно работающих профилей
AUTO_START_ALL_PROFILE = os.getenv("AUTO_START_ALL_PROFILE", "0").strip().lower() in (
    "1",
    "true",
    "yes",
    "on",
)

bot = telebot.TeleBot(TOKEN)
notified_photo_flags = {}
processed_events = set()

apihelper.CONNECT_TIMEOUT = 15


def _is_allowed(message) -> bool:
    return str(message.chat.id) == str(CHAT_ID)


def _get_status_line(profile_id: str) -> str:
    """🆕 Формирует строку статуса с эмодзи на основе tebor_state."""
    st = tebor_state.get_state(profile_id)
    state = st.get("state", "Не запущен")
    details = st.get("details", "")
    emoji_map = {
        "Инициализация": "🔄",
        "Авторизация": "🔐",
        "Переход в галерею": "📍",
        "Мониторинг": "🟢",
        "Загрузка фото": "📤",
        "Пауза (антибан)": "⏸️",
        "Пауза (лимит)": "⚠️",
        "Ожидание фото": "🟡",
        "Краш": "❌",
        "Остановлен": "⚫",
        "Не запущен": "⚫",
    }
    emoji = emoji_map.get(state, "❓")
    return f"{emoji} {state}" + (f" ({details})" if details else "")


# ================== ФОНОВЫЕ ПРОВЕРКИ ==================
def _read_photo_folder(flag_file: Path) -> str:
    try:
        for line in flag_file.read_text(encoding="utf-8").splitlines():
            if line.startswith("folder="):
                return line.split("=", 1)[1].strip()
    except Exception:
        pass
    return ""


def _count_photos(photo_folder: str) -> int:
    if not photo_folder or not os.path.isdir(photo_folder):
        return 0
    return sum(
        1
        for name in os.listdir(photo_folder)
        if name.lower().endswith((".jpg", ".jpeg", ".png", ".gif", ".bmp", ".webp"))
    )


def _send_photo_needed(flag_file: Path, repeated: bool = False) -> None:
    id_value = flag_file.stem
    photo_folder = _read_photo_folder(flag_file)
    if repeated:
        message = f" <code>{html.escape(id_value)}</code> — фотографии всё ещё отсутствуют!\n\n"
    else:
        message = (
            f"📸 <code>{html.escape(id_value)}</code> — фотографии закончились!\n\n"
        )

    if photo_folder:
        message += f"📁 Папка: <code>{html.escape(photo_folder)}</code>\n\n"

    message += f"🔄 Добавьте фото и отправьте:\n<code>/photo_continue {html.escape(id_value)}</code>"

    bot.send_message(CHAT_ID, message, parse_mode="HTML")
    notified_photo_flags[id_value] = time.time()
    logger.info("Уведомление о фото отправлено для %s", id_value)


def _check_photo_needed_files() -> None:
    now = time.time()
    active_ids = set()
    for flag_file in PHOTO_NEEDED_DIR.glob("*.txt"):
        id_value = flag_file.stem
        active_ids.add(id_value)
        last_sent = notified_photo_flags.get(id_value)
        if last_sent is None:
            _send_photo_needed(flag_file)
            continue
        if now - last_sent < RENOTIFY_INTERVAL_SECONDS:
            continue
        photo_folder = _read_photo_folder(flag_file)
        if _count_photos(photo_folder) > 0:
            try:
                flag_file.unlink()
                notified_photo_flags.pop(id_value, None)
                bot.send_message(
                    CHAT_ID,
                    f"✅ <b>{html.escape(id_value)}</b> — фото найдены. tebor продолжит работу.",
                    parse_mode="HTML",
                )
            except Exception:
                pass
        else:
            _send_photo_needed(flag_file, repeated=True)

    for old_id in list(notified_photo_flags):
        if old_id not in active_ids:
            notified_photo_flags.pop(old_id, None)


def _check_tg_events() -> None:
    for event_file in sorted(TG_EVENT_DIR.glob("*.txt")):
        if event_file.name in processed_events:
            continue
        try:
            text = event_file.read_text(encoding="utf-8").strip()
            if text:
                bot.send_message(CHAT_ID, text, parse_mode="HTML")
                processed_events.add(event_file.name)
                event_file.unlink(missing_ok=True)
        except Exception:
            pass


def start_background_watchers() -> None:
    def loop():
        while True:
            try:
                _check_photo_needed_files()
                _check_tg_events()
            except Exception:
                pass
            time.sleep(CHECK_INTERVAL_SECONDS)

    threading.Thread(target=loop, daemon=True).start()


# ================== 🆕 WATCHER ОЧЕРЕДИ ==================
def queue_watcher_loop():
    """Фоновый процесс, который поддерживает количество активных профилей."""
    logger.info(f"👁️ Watcher очереди запущен. Лимит: {MAX_ACTIVE_PROFILES}")
    client = BrowserVisionClient(debug=False)

    while True:
        try:
            active_map = state_manager.get_all()
            alive_count = 0

            # Считаем живые и чистим мертвые
            for pid, data in list(active_map.items()):
                tebor_pid = data.get("tebor_pid")
                port = data.get("port")

                if tebor_pid and _is_process_alive(tebor_pid):
                    alive_count += 1
                else:
                    # Консоль мертва. Проверяем, не остался ли браузер висеть (Зомби)
                    if port and kill_browser_by_port(port):
                        logger.warning(
                            f"🧟 Убит зомби-браузер на порту {port} для {data.get('name')}"
                        )

                    # Закрываем через API на всякий случай
                    try:
                        client.stop_profile(FOLDER_ID, pid)
                    except:
                        pass

                    state_manager.remove(pid)
                    tebor_state.clear_state(pid)

            # Запуск из очереди
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
                            logger.error(f" Ошибка запуска из очереди {name}: {e}")
                        time.sleep(2)
        except Exception as e:
            logger.error(f"⚠️ Ошибка в цикле Watcher: {e}")
        time.sleep(15)


def start_queue_watcher():
    """Запускает поток наблюдателя за очередью."""
    threading.Thread(target=queue_watcher_loop, daemon=True).start()


def _enqueue_all_profiles_and_notify(target_chat_id: str) -> None:
    """Добавляет все профили в очередь и отправляет результат в Telegram."""
    try:
        from auto_runner import launch_all_profiles

        result = launch_all_profiles()
        if result["success"]:
            bot.send_message(
                target_chat_id, f"✅ В очередь добавлено {result['queued']} профилей."
            )
        else:
            bot.send_message(target_chat_id, f"❌ Ошибка: {result.get('error')}")
    except Exception as exc:
        bot.send_message(
            target_chat_id,
            f"❌ Ошибка: <code>{html.escape(str(exc))}</code>",
            parse_mode="HTML",
        )


# ================== КОМАНДЫ БОТА ==================
@bot.message_handler(commands=["start", "help"])
def cmd_start(message):
    if not _is_allowed(message):
        return
    bot.reply_to(
        message,
        "🤖 Управление Browser Vision\n\n"
        "<code>/photo_continue [id]</code> — фото пополнены\n"
        "<code>/start_all_profile</code> — добавить все в очередь\n"
        "<code>/stop_all_profile</code> — остановить все и очистить очередь\n"
        "<code>/list_active</code> — список активных\n"
        "<code>/list_needed</code> — список ожиданий фото\n"
        "<code>/queue_status</code> — статус очереди\n"
        "<code>/menu</code> — интерактивное меню\n"
        "<code>/menu 12</code> — сразу выбрать пункт 12\n"
        "<code>/menu 3</code> — перезапустить профили\n",
        parse_mode="HTML",
    )


@bot.message_handler(commands=["photo_continue"])
def cmd_photo_continue(message):
    if not _is_allowed(message):
        return
    parts = message.text.split()
    flags = list(PHOTO_NEEDED_DIR.glob("*.txt"))
    if len(parts) >= 2:
        flags = [PHOTO_NEEDED_DIR / f"{parts[1].strip()}.txt"]
    elif len(flags) != 1:
        bot.reply_to(
            message,
            "❌ Укажите ID: <code>/photo_continue <id></code>",
            parse_mode="HTML",
        )
        return
    flag_file = flags[0]
    id_value = flag_file.stem
    if not flag_file.exists():
        bot.reply_to(
            message,
            f"ℹ️ Для ID <code>{html.escape(id_value)}</code> нет запроса.",
            parse_mode="HTML",
        )
        return

    try:
        flag_file.unlink()
        notified_photo_flags.pop(id_value, None)
    except Exception:
        pass

    bot.reply_to(
        message,
        f"✅ Команда продолжения отправлена для ID <code>{html.escape(id_value)}</code>.",
        parse_mode="HTML",
    )


@bot.message_handler(commands=["start_all_profile"])
def cmd_start_all_profile(message):
    """🆕 Теперь добавляет все профили в очередь, а не запускает сразу."""
    if not _is_allowed(message):
        return
    bot.reply_to(message, "🚀 Добавляю все профили в очередь...")
    threading.Thread(
        target=_enqueue_all_profiles_and_notify, args=(str(CHAT_ID),), daemon=True
    ).start()


@bot.message_handler(commands=["stop_all_profile"])
def cmd_stop_all_profile(message):
    """Очищает очередь и останавливает все профили."""
    if not _is_allowed(message):
        return
    bot.reply_to(message, " Очищаю очередь и останавливаю все профили...")

    def run():
        try:
            from auto_runner import stop_all_profiles

            result = stop_all_profiles()
            if result["success"]:
                bot.send_message(
                    CHAT_ID, f"⛔ Остановлено {result['stopped']} профилей."
                )
            else:
                bot.send_message(CHAT_ID, f"❌ Ошибка: {result.get('error')}")
        except Exception as exc:
            bot.send_message(
                CHAT_ID,
                f"❌ Ошибка: <code>{html.escape(str(exc))}</code>",
                parse_mode="HTML",
            )

    threading.Thread(target=run, daemon=True).start()


@bot.message_handler(commands=["list_active"])
def cmd_list_active(message):
    """🆕 Теперь показывает статусы из tebor_state."""
    if not _is_allowed(message):
        return
    active_map = state_manager.get_all()
    if not active_map:
        bot.reply_to(message, "⚫ Нет активных профилей.")
        return

    lines = [
        f"🟢 <b>Активные ({len(active_map)}) | В очереди: {queue_manager.get_count()}</b>\n"
    ]
    for pid, data in active_map.items():
        name = data.get("name", "N/A")
        port = data.get("port", "N/A")
        status_line = _get_status_line(pid)
        lines.append(f"\n• <b>{name}</b> (порт {port})\n  {status_line}")

    bot.reply_to(message, "\n".join(lines), parse_mode="HTML")


@bot.message_handler(commands=["queue_status"])
def cmd_queue_status(message):
    """🆕 Показывает статус очереди."""
    if not _is_allowed(message):
        return

    active_map = state_manager.get_all()
    alive_count = sum(
        1 for d in active_map.values() if _is_process_alive(d.get("tebor_pid"))
    )
    queue_count = queue_manager.get_count()

    msg = "📊 <b>Статус очереди и профилей</b>\n\n"
    msg += f"🟢 Активных (живых): <b>{alive_count}</b> / {MAX_ACTIVE_PROFILES}\n"
    msg += f" В очереди на запуск: <b>{queue_count}</b>\n\n"

    if queue_count > 0:
        msg += "<b>Следующие в очереди:</b>\n"
        for i, p in enumerate(queue_manager.get_all()[:5], 1):
            msg += f"  {i}. {p['name']}\n"
        if queue_count > 5:
            msg += f"  ... и ещё {queue_count - 5}\n"

    bot.reply_to(message, msg, parse_mode="HTML")


@bot.message_handler(commands=["list_needed"])
def cmd_list_needed(message):
    if not _is_allowed(message):
        return
    flags = list(PHOTO_NEEDED_DIR.glob("*.txt"))
    if not flags:
        bot.reply_to(message, "ℹ️ Нет активных запросов на пополнение.")
        return
    response = f"📋 Активные запросы ({len(flags)}):\n\n"
    for flag_file in flags:
        response += f"• <code>{html.escape(flag_file.stem)}</code>\n"
    bot.reply_to(message, response, parse_mode="HTML")


# ================== ИНТЕРАКТИВНОЕ МЕНЮ ==================
user_states = {}


def _get_client():
    return BrowserVisionClient(debug=False)


def _parse_selection(text: str, max_index: int):
    if not text.strip():
        return None
    selected = []
    parts = text.split(",")
    for part in parts:
        part = part.strip()
        if not part:
            continue
        if "-" in part:
            try:
                start_str, end_str = part.split("-", 1)
                start, end = int(start_str), int(end_str)
            except ValueError:
                return None
            if start < 1:
                start = 1
            if end > max_index:
                end = max_index
            if start > end:
                return None
            selected.extend(list(range(start - 1, end)))
        else:
            try:
                idx = int(part)
            except ValueError:
                return None
            if idx < 1:
                idx = 1
            if idx > max_index:
                idx = max_index
            selected.append(idx - 1)
    return sorted(set(selected))


def _prepare_profiles_selection(chat_id, profiles_list, heading, action):
    if not profiles_list:
        bot.send_message(chat_id, "⚫ Нет запущенных профилей.")
        return

    msg = f"{heading}\n📊 Запущено: {len(profiles_list)}\n\n"

    for i, item in enumerate(profiles_list, 1):
        profile_id, data = item
        name = data.get("name", "N/A")
        port = data.get("port", "N/A")
        status_line = _get_status_line(profile_id)
        line = f"\n{i}. {status_line} | {name} (порт {port})\n"

        if len(msg) + len(line) > 4000:
            msg += f"\n<i>... и ещё {len(profiles_list) - i + 1} профилей (список обрезан)</i>\n"
            break

        msg += line

    msg += "\n<i>Введите номера через запятую или диапазон (1-5, 7, 9-12)</i>"
    msg += "\n<i>0 — назад</i>"

    bot.send_message(chat_id, msg, parse_mode="HTML")
    user_states[chat_id] = {
        "state": "waiting_for_numbers",
        "context": {"action": action, "profiles_list": profiles_list},
    }


@bot.message_handler(commands=["menu"])
def cmd_menu(message):
    if not _is_allowed(message):
        return
    parts = message.text.split()
    chat_id = message.chat.id
    if len(parts) == 1:
        menu_text = (
            "📋 <b>Главное меню:</b>\n"
            "━━━━━━━━━━━━━━━━━━━━━━\n"
            "📊 <b>ПРОСМОТР:</b>\n"
            "  1. Профили в рабочей группе\n"
            "  9. Запущенные профили\n\n"
            "🟢 <b>ЗАПУСК / УПРАВЛЕНИЕ:</b>\n"
            "  12. Запустить несколько профилей\n"
            "  3. Перезапустить профили\n"
            "  14. Остановить несколько профилей\n\n"
            "🚀 <b>ОЧЕРЕДЬ:</b>\n"
            "  15. Добавить все в очередь\n"
            "  16. Очистить очередь и остановить все\n"
            "  17. Статус очереди\n\n"
            "⚙️ <b>ДРУГОЕ:</b>\n"
            "  8. Проверить соединение\n\n"
            "━━━━━━━━━━━━━━━━━━━━━━\n"
            "Выберите действие: <code>/menu &lt;номер&gt;</code>"
        )
        bot.reply_to(message, menu_text, parse_mode="HTML")
    else:
        choice = parts[1].strip()
        threading.Thread(target=handle_menu_choice, args=(chat_id, choice)).start()


def handle_menu_choice(chat_id, choice):
    client = _get_client()
    if choice == "12":
        try:
            profiles_data = client.get_profiles(FOLDER_ID)
            profiles = profiles_data.get("items", [])
            total = profiles_data.get("total", len(profiles))

            msg = f"📂 <b>Профили в рабочей группе</b>\n Всего: {total}\n\n"

            for i, profile in enumerate(profiles, 1):
                name = profile.get("profile_name", "N/A")
                profile_id = (
                    profile.get("uuid")
                    or profile.get("profile_id")
                    or str(profile.get("id"))
                )
                status_line = _get_status_line(profile_id)
                line = f"\n{i}. {status_line} | {name}\n"

                if len(msg) + len(line) > 4000:
                    msg += f"\n<i>... и ещё {len(profiles) - i + 1} профилей (список обрезан)</i>\n"
                    break

                msg += line

            msg += "\n<i>Введите номера через запятую или диапазон (1-5, 7, 9-12)</i>"
            msg += "\n<i>0 — назад</i>"

            bot.send_message(chat_id, msg, parse_mode="HTML")

            user_states[chat_id] = {
                "state": "waiting_for_numbers",
                "context": {"action": "launch", "profiles": profiles},
            }
        except Exception as e:
            bot.send_message(chat_id, f"❌ Ошибка получения профилей: {e}")

    elif choice == "14":
        active_map = state_manager.get_all()
        profiles_list = list(active_map.items())
        _prepare_profiles_selection(
            chat_id,
            profiles_list,
            "⛔ <b>Остановка нескольких профилей</b>",
            "stop",
        )

    elif choice == "3":
        active_map = state_manager.get_all()
        profiles_list = list(active_map.items())
        _prepare_profiles_selection(
            chat_id,
            profiles_list,
            "🔄 <b>Перезапуск нескольких профилей</b>",
            "restart",
        )

    elif choice == "15":
        bot.send_message(chat_id, "🚀 Добавляю все профили в очередь...")

        def run():
            try:
                from auto_runner import launch_all_profiles

                result = launch_all_profiles()
                if result["success"]:
                    bot.send_message(
                        chat_id, f"✅ В очередь добавлено {result['queued']} профилей."
                    )
                else:
                    bot.send_message(chat_id, f"❌ Ошибка: {result.get('error')}")
            except Exception as exc:
                bot.send_message(chat_id, f" Ошибка: {exc}")

        threading.Thread(target=run, daemon=True).start()

    elif choice == "16":
        bot.send_message(chat_id, "⛔ Очищаю очередь и останавливаю все...")

        def run():
            try:
                from auto_runner import stop_all_profiles

                result = stop_all_profiles()
                if result["success"]:
                    bot.send_message(
                        chat_id, f"⛔ Остановлено {result['stopped']} профилей."
                    )
                else:
                    bot.send_message(chat_id, f"❌ Ошибка: {result.get('error')}")
            except Exception as exc:
                bot.send_message(chat_id, f"❌ Ошибка: {exc}")

        threading.Thread(target=run, daemon=True).start()

    elif choice == "17":
        active_map = state_manager.get_all()
        alive_count = sum(
            1 for d in active_map.values() if _is_process_alive(d.get("tebor_pid"))
        )
        queue_count = queue_manager.get_count()

        msg = "📊 <b>Статус очереди</b>\n\n"
        msg += f"🟢 Активных: <b>{alive_count}</b> / {MAX_ACTIVE_PROFILES}\n"
        msg += f" В очереди: <b>{queue_count}</b>\n"

        if queue_count > 0:
            msg += "\n<b>Следующие:</b>\n"
            for i, p in enumerate(queue_manager.get_all()[:5], 1):
                msg += f"  {i}. {p['name']}\n"
            if queue_count > 5:
                msg += f"  ... и ещё {queue_count - 5}\n"

        bot.send_message(chat_id, msg, parse_mode="HTML")

    elif choice == "8":
        try:
            if client.test_connection():
                bot.send_message(chat_id, "✅ Соединение с API работает!")
            else:
                bot.send_message(chat_id, "❌ Соединение не установлено")
        except Exception as e:
            bot.send_message(chat_id, f" Ошибка: {e}")
    else:
        bot.send_message(chat_id, "❌ Неверный выбор. Используйте /menu для списка.")


# ================== ОБРАБОТКА ВВОДА ==================
@bot.message_handler(func=lambda message: message.chat.id in user_states)
def handle_user_states(message):
    chat_id = message.chat.id
    state_data = user_states[chat_id]
    state = state_data["state"]
    text = message.text.strip()
    context = state_data["context"]

    if state == "waiting_for_numbers":
        if text == "0":
            bot.send_message(chat_id, " Действие отменено.")
            del user_states[chat_id]
            return

        if context["action"] == "launch":
            profiles = context["profiles"]
            indices = _parse_selection(text, len(profiles))
            if indices is None:
                bot.send_message(
                    chat_id,
                    "❌ Неверный формат. Пример: <code>1,3-5,7</code>",
                    parse_mode="HTML",
                )
                return

            context["indices"] = indices
            context["state"] = "waiting_for_folder_mode"

            folder_msg = (
                "✅ Профили выбраны.\n\n"
                "📁 <b>Настройка папок с фотографиями:</b>\n"
                "1. Автоматически (по ID из имени профиля)\n"
                "2. Указать одну общую папку для всех\n"
                "0. Отмена"
            )
            bot.send_message(chat_id, folder_msg, parse_mode="HTML")
            state_data["state"] = "waiting_for_folder_mode"

        elif context["action"] == "stop":
            profiles_list = context["profiles_list"]
            indices = _parse_selection(text, len(profiles_list))
            if indices is None:
                bot.send_message(
                    chat_id,
                    "❌ Неверный формат. Пример: <code>1,3-5</code>",
                    parse_mode="HTML",
                )
                return

            del user_states[chat_id]
            threading.Thread(
                target=execute_stop_profiles, args=(chat_id, profiles_list, indices)
            ).start()

        elif context["action"] == "restart":
            profiles_list = context["profiles_list"]
            indices = _parse_selection(text, len(profiles_list))
            if indices is None:
                bot.send_message(
                    chat_id,
                    "❌ Неверный формат. Пример: <code>1,3-5</code>",
                    parse_mode="HTML",
                )
                return

            del user_states[chat_id]
            threading.Thread(
                target=execute_restart_profiles,
                args=(chat_id, profiles_list, indices, RESTART_DELAY_SECONDS),
            ).start()

    elif state == "waiting_for_folder_mode":
        if text == "0":
            bot.send_message(chat_id, "❌ Действие отменено.")
            del user_states[chat_id]
            return
        elif text == "1":
            del user_states[chat_id]
            threading.Thread(
                target=execute_launch_profiles, args=(chat_id, context, "auto")
            ).start()
        elif text == "2":
            bot.send_message(
                chat_id,
                "📁 Введите полный путь к общей папке (например, <code>D:\\photos</code>):",
                parse_mode="HTML",
            )
            state_data["state"] = "waiting_for_common_folder"
        else:
            bot.send_message(chat_id, "❌ Выберите 1, 2 или 0.")

    elif state == "waiting_for_common_folder":
        if text == "0":
            bot.send_message(chat_id, " Действие отменено.")
            del user_states[chat_id]
            return

        folder_path = text.strip()
        del user_states[chat_id]
        threading.Thread(
            target=execute_launch_profiles,
            args=(chat_id, context, "common", folder_path),
        ).start()


# ================== ФУНКЦИИ ВЫПОЛНЕНИЯ ==================
def execute_launch_profiles(chat_id, context, folder_mode, common_folder=None):
    bot.send_message(chat_id, "🚀 Начинаю запуск выбранных профилей...")
    client = _get_client()
    profiles = context["profiles"]
    indices = context["indices"]
    success_count = 0
    report = []

    for idx in indices:
        profile = profiles[idx]
        name = profile.get("profile_name", "N/A")
        profile_uuid = (
            profile.get("uuid") or profile.get("profile_id") or str(profile.get("id"))
        )
        person_id = _extract_person_id_from_profile(profile)

        if folder_mode == "auto":
            photo_folder = _get_photo_folder_by_person_id(person_id)
        else:
            photo_folder = common_folder

        cdp_port = ProfileCreator.generate_cdp_port()
        start_result = client.start_profile(FOLDER_ID, profile_uuid, port=cdp_port)

        if start_result:
            actual_port = start_result.get("port") or cdp_port
            pid, console_title = _run_tebor_for_profile(
                profile_uuid, actual_port, name, person_id
            )
            state_manager.add(
                profile_uuid,
                actual_port,
                name,
                person_id,
                tebor_pid=pid,
                console_title=console_title,
            )
            report.append(f"✅ {name} (порт {actual_port})")
            success_count += 1
        else:
            report.append(f"❌ {name} (ошибка запуска)")

    final_msg = (
        f"🏁 <b>Запуск завершен.</b>\nУспешно: {success_count}/{len(indices)}\n\n"
    )
    final_msg += "\n".join(report)
    bot.send_message(chat_id, final_msg, parse_mode="HTML")


def execute_stop_profiles(chat_id, profiles_list, indices):
    bot.send_message(chat_id, "⛔ Начинаю остановку...")
    client = _get_client()

    success_count = 0
    report = []

    for idx in indices:
        profile_id, data = profiles_list[idx]
        name = data.get("name", "N/A")
        console_title = data.get("console_title", "")
        tebor_pid = data.get("tebor_pid")
        port = data.get("port")

        result = client.stop_profile(FOLDER_ID, profile_id)
        if result is not None:
            report.append(f"✅ {name} остановлен")
            success_count += 1
        else:
            report.append(f"❌ {name} (ошибка API)")

        if console_title or tebor_pid:
            kill_console_and_process(console_title, tebor_pid)

        if port:
            kill_browser_by_port(port)

        state_manager.remove(profile_id)

    final_msg = (
        f"🏁 <b>Остановка завершена.</b>\nУспешно: {success_count}/{len(indices)}\n\n"
    )
    final_msg += "\n".join(report)
    bot.send_message(chat_id, final_msg, parse_mode="HTML")


def execute_restart_profiles(chat_id, profiles_list, indices, delay=RESTART_DELAY_SECONDS):
    bot.send_message(chat_id, "🔄 Начинаю перезапуск...")
    client = _get_client()

    success_count = 0
    report = []

    for idx in indices:
        profile_id, data = profiles_list[idx]
        name = data.get("name", "N/A")
        console_title = data.get("console_title", "")
        tebor_pid = data.get("tebor_pid")
        port = data.get("port")
        person_id = data.get("person_id")

        # 1. Остановка
        result = client.stop_profile(FOLDER_ID, profile_id)
        if result is not None:
            report.append(f"✅ {name} остановлен")
        else:
            report.append(f"⚠️ {name} — ошибка остановки API")

        if console_title or tebor_pid:
            kill_console_and_process(console_title, tebor_pid)

        if port:
            kill_browser_by_port(port)

        state_manager.remove(profile_id)
        tebor_state.clear_state(profile_id)

        time.sleep(delay)

        # 2. Запуск
        photo_folder = _get_photo_folder_by_person_id(person_id)
        cdp_port = ProfileCreator.generate_cdp_port()
        start_result = client.start_profile(FOLDER_ID, profile_id, port=cdp_port)

        if start_result:
            actual_port = start_result.get("port") or cdp_port
            pid, console_title = _run_tebor_for_profile(
                profile_id, actual_port, name, person_id
            )
            state_manager.add(
                profile_id,
                actual_port,
                name,
                person_id,
                tebor_pid=pid,
                console_title=console_title,
            )
            report.append(f"✅ {name} запущен (порт {actual_port})")
            success_count += 1
        else:
            report.append(f"❌ {name} — ошибка запуска")

    final_msg = (
        f"🏁 <b>Перезапуск завершен.</b>\nУспешно: {success_count}/{len(indices)}\n\n"
    )
    final_msg += "\n".join(report)
    bot.send_message(chat_id, final_msg, parse_mode="HTML")


# ================== ЗАПУСК ==================
if __name__ == "__main__":
    print("🚀 Telegram-бот проекта запущен")
    start_background_watchers()
    start_queue_watcher()  # 🆕 Запускаем наблюдателя за очередью

    if AUTO_START_ALL_PROFILE:
        logger.info("🚀 AUTO_START_ALL_PROFILE=1: добавляю все профили в очередь")
        threading.Thread(
            target=_enqueue_all_profiles_and_notify, args=(str(CHAT_ID),), daemon=True
        ).start()

    while True:
        try:
            bot.polling(non_stop=True, timeout=30, long_polling_timeout=20)
        except KeyboardInterrupt:
            print("\n👋 Бот остановлен пользователем")
            break
        except Exception as e:
            logger.error(f"❌ Критический сбой polling: {type(e).__name__} - {e}")
            try:
                if hasattr(bot, "session"):
                    bot.session.close()
                else:
                    apihelper._get_req_session().close()
            except Exception:
                pass
            logger.info("⏳ Перезапуск бота через 5 секунд...")
            time.sleep(5)
