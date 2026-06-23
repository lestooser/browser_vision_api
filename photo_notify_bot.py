import html
import logging
import os
import threading
import time
from pathlib import Path
import telebot
from dotenv import load_dotenv

load_dotenv()
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

TOKEN = os.getenv("TG_BOT_TOKEN")
CHAT_ID = os.getenv("TG_CHAT_ID")

if not TOKEN or not CHAT_ID:
    raise RuntimeError("❌ TG_BOT_TOKEN или TG_CHAT_ID не указаны в .env")

BASE_DIR = Path(__file__).parent
TG_EVENT_DIR = BASE_DIR / "logs" / "tg_events"
TG_EVENT_DIR.mkdir(parents=True, exist_ok=True)

CHECK_INTERVAL_SECONDS = 15  # Проверяем папку событий каждые 15 секунд
bot = telebot.TeleBot(TOKEN)
processed_events = set()

def _is_allowed(message) -> bool:
    return str(message.chat.id) == str(CHAT_ID)

def _check_tg_events() -> None:
    """Читает все файлы из папки tg_events и отправляет их в Telegram."""
    for event_file in sorted(TG_EVENT_DIR.glob("*.txt")):
        if event_file.name in processed_events:
            continue
        try:
            text = event_file.read_text(encoding="utf-8").strip()
            if text:
                bot.send_message(CHAT_ID, text, parse_mode="HTML")
                processed_events.add(event_file.name)
                # Удаляем файл после успешной отправки
                event_file.unlink(missing_ok=True)
        except Exception as exc:
            logger.error("Не удалось обработать событие %s: %s", event_file, exc)

def start_background_watchers() -> None:
    def loop():
        while True:
            try:
                _check_tg_events()
            except Exception as exc:
                logger.exception("Ошибка фоновой проверки: %s", exc)
            time.sleep(CHECK_INTERVAL_SECONDS)

    threading.Thread(target=loop, daemon=True).start()
    logger.info("Фоновая проверка событий запущена")

# ================== КОМАНДЫ БОТА ==================

@bot.message_handler(commands=["start", "help"])
def cmd_start(message):
    if not _is_allowed(message): return
    bot.reply_to(
        message,
        "🤖 <b>Управление Browser Vision</b>\n\n"
        "<code>/start_all_profile</code> — запустить все профили (авто-папки)\n"
        "<code>/stop_all_profile</code> — остановить все профили и консоли\n"
        "<code>/status</code> — статус запущенных профилей\n\n"
        "💡 <i>Уведомления о фото, ошибках и статусе 'Главная' приходят автоматически.</i>",
        parse_mode="HTML",
    )

@bot.message_handler(commands=["start_all_profile"])
def cmd_start_all_profile(message):
    if not _is_allowed(message): return
    bot.reply_to(message, "🚀 Запускаю все профили (авто-папки)...")

    def run():
        try:
            from auto_runner import quick_start_all
            result_text = quick_start_all()
            bot.send_message(CHAT_ID, result_text, parse_mode="HTML")
        except Exception as exc:
            logger.exception("Ошибка /start_all_profile: %s", exc)
            bot.send_message(CHAT_ID, f"❌ Ошибка запуска: <code>{html.escape(str(exc))}</code>", parse_mode="HTML")

    threading.Thread(target=run, daemon=True).start()

@bot.message_handler(commands=["stop_all_profile"])
def cmd_stop_all_profile(message):
    if not _is_allowed(message): return
    bot.reply_to(message, "⛔ Останавливаю все профили и консоли...")

    def run():
        try:
            from auto_runner import quick_stop_all
            result_text = quick_stop_all()
            bot.send_message(CHAT_ID, result_text, parse_mode="HTML")
        except Exception as exc:
            logger.exception("Ошибка /stop_all_profile: %s", exc)
            bot.send_message(CHAT_ID, f"❌ Ошибка остановки: <code>{html.escape(str(exc))}</code>", parse_mode="HTML")

    threading.Thread(target=run, daemon=True).start()

@bot.message_handler(commands=["status"])
def cmd_status(message):
    if not _is_allowed(message): return
    def run():
        try:
            from auto_runner import quick_status
            bot.send_message(CHAT_ID, quick_status(), parse_mode="HTML")
        except Exception as exc:
            bot.send_message(CHAT_ID, f"❌ Ошибка: <code>{html.escape(str(exc))}</code>", parse_mode="HTML")
    threading.Thread(target=run, daemon=True).start()

if __name__ == "__main__":
    print("🚀 Telegram-бот проекта запущен")
    start_background_watchers()
    try:
        bot.infinity_polling(timeout=60, long_polling_timeout=60)
    except KeyboardInterrupt:
        print("\n👋 Бот остановлен")
    except Exception as exc:
        logger.critical("Критическая ошибка бота: %s", exc)
