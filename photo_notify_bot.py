"""
Telegram-бот этого проекта для автономного управления профилями и уведомлений tebor.
"""

import html
import json
import logging
import os
import threading
import time
from datetime import datetime
from pathlib import Path

import telebot
from dotenv import load_dotenv

import state_manager  # Единый менеджер состояний

load_dotenv()
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

TOKEN = os.getenv("TG_BOT_TOKEN")
CHAT_ID = os.getenv("TG_CHAT_ID")
if not TOKEN or not CHAT_ID:
    raise RuntimeError("❌ TG_BOT_TOKEN или TG_CHAT_ID не указаны в .env")

BASE_DIR = Path(__file__).parent
PHOTO_NEEDED_DIR = BASE_DIR / "logs" / "photo_needed"
TG_EVENT_DIR = BASE_DIR / "logs" / "tg_events"
PHOTO_NEEDED_DIR.mkdir(parents=True, exist_ok=True)
TG_EVENT_DIR.mkdir(parents=True, exist_ok=True)

CHECK_INTERVAL_SECONDS = 30
RENOTIFY_INTERVAL_SECONDS = 5 * 60
bot = telebot.TeleBot(TOKEN)
notified_photo_flags = {}
processed_events = set()


def _is_allowed(message) -> bool:
    return str(message.chat.id) == str(CHAT_ID)


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
    title = (
        "📸 <b>Фотографии всё ещё отсутствуют!</b>"
        if repeated
        else "📸 <b>Фотографии закончились!</b>"
    )
    message = f"{title}\n\n🆔 ID: <code>{html.escape(id_value)}</code>\n"
    if photo_folder:
        message += f"📁 Папка: <code>{html.escape(photo_folder)}</code>\n"
    message += f"\nДобавьте фото и отправьте: <code>/photo_continue {html.escape(id_value)}</code>"

    bot.send_message(CHAT_ID, message, parse_mode="HTML")
    notified_photo_flags[id_value] = time.time()


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
                    f"✅ Фото для ID <code>{html.escape(id_value)}</code> найдены.",
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


# ================== КОМАНДЫ БОТА ==================
@bot.message_handler(commands=["start", "help"])
def cmd_start(message):
    if not _is_allowed(message):
        return
    bot.reply_to(
        message,
        "🤖 Управление Browser Vision\n\n"
        "<code>/photo_continue [id]</code> — фото пополнены\n"
        "<code>/start_all_profile</code> — открыть все профили\n"
        "<code>/stop_all_profile</code> — закрыть все профили\n"
        "<code>/list_active</code> — список активных (из state_manager)\n"
        "<code>/list_needed</code> — список ожиданий фото",
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
            "❌ Укажите ID: <code>/photo_continue &lt;id&gt;</code>",
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
    if not _is_allowed(message):
        return
    bot.reply_to(message, "🚀 Запускаю все профили...")

    def run():
        try:
            from auto_runner import quick_start_all

            bot.send_message(CHAT_ID, quick_start_all())
        except Exception as exc:
            bot.send_message(
                CHAT_ID,
                f"❌ Ошибка: <code>{html.escape(str(exc))}</code>",
                parse_mode="HTML",
            )

    threading.Thread(target=run, daemon=True).start()


@bot.message_handler(commands=["stop_all_profile"])
def cmd_stop_all_profile(message):
    if not _is_allowed(message):
        return
    bot.reply_to(message, "⛔ Останавливаю все профили...")

    def run():
        try:
            from auto_runner import quick_stop_all

            bot.send_message(CHAT_ID, quick_stop_all())
        except Exception as exc:
            bot.send_message(
                CHAT_ID,
                f"❌ Ошибка: <code>{html.escape(str(exc))}</code>",
                parse_mode="HTML",
            )

    threading.Thread(target=run, daemon=True).start()


@bot.message_handler(commands=["list_active"])
def cmd_list_active(message):
    if not _is_allowed(message):
        return

    active_map = state_manager.get_all()
    if not active_map:
        bot.reply_to(message, "⚫ Нет активных профилей в state_manager.")
        return

    lines = [f"🟢 <b>Активные профили ({len(active_map)}):</b>\n"]
    for pid, data in active_map.items():
        name = data.get("name", "N/A")
        port = data.get("port", "N/A")

        # 🆕 Читаем heartbeat
        hb_file = BASE_DIR / "logs" / "console_heartbeat" / f"{pid}.json"
        console_status = "⚫ Нет данных"
        if hb_file.exists():
            try:
                hb = json.loads(hb_file.read_text(encoding="utf-8"))
                last_update = datetime.fromisoformat(hb["last_update"])
                diff = (datetime.now() - last_update).total_seconds()
                if diff < 30:
                    console_status = f"🟢 {hb.get('status', 'Working')} ({int(diff)}с)"
                else:
                    console_status = f"🟡 Зависла ({int(diff)}с)"
            except Exception:
                console_status = "⚠️ Ошибка"

        lines.append(f"• {name} (порт {port})\n  Консоль: {console_status}")

    bot.reply_to(message, "\n".join(lines), parse_mode="HTML")


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


if __name__ == "__main__":
    print("🚀 Telegram-бот проекта запущен")
    start_background_watchers()
    try:
        bot.infinity_polling(timeout=60, long_polling_timeout=60)
    except KeyboardInterrupt:
        print("\n👋 Бот остановлен")
