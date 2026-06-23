"""
Отдельный Telegram-бот для уведомлений о пополнении фото в tebor.
Работает независимо от easy_tg_bot.py.

Логика:
1. Каждые 30 сек проверяет папку logs/photo_needed/
2. Если там есть файлы — отправляет уведомления в Telegram
3. Принимает команду /photo_resume <id> — удаляет файл-флаг
4. tebor.py обнаруживает удаление файла и продолжает работу
"""

import logging
import os
import time
from pathlib import Path

import telebot
from dotenv import load_dotenv

load_dotenv()

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# ================== КОНФИГУРАЦИЯ ==================
TOKEN = os.getenv("TG_BOT_TOKEN")
CHAT_ID = os.getenv("TG_CHAT_ID")  # ID чата для уведомлений (твой личный)

if not TOKEN or not CHAT_ID:
    raise RuntimeError(
        "❌ TG_BOT_TOKEN или TG_CHAT_ID не указаны в .env\n"
        "Добавь в .env:\n"
        "TG_BOT_TOKEN=твой_токен\n"
        "TG_CHAT_ID=твой_chat_id"
    )

# Папка с файлами-флагами
BASE_DIR = Path(__file__).parent
PHOTO_NEEDED_DIR = BASE_DIR / "logs" / "photo_needed"
PHOTO_NEEDED_DIR.mkdir(parents=True, exist_ok=True)

bot = telebot.TeleBot(TOKEN)

# Множество уже отправленных уведомлений (чтобы не спамить)
notified_ids = set()


# ================== ФОНОВАЯ ПРОВЕРКА ФАЙЛОВ ==================
def check_photo_needed_files():
    """
    Проверяет папку logs/photo_needed/ и отправляет уведомления.
    Запускается в отдельном потоке каждые 30 сек.
    """
    import threading

    def loop():
        while True:
            try:
                for flag_file in PHOTO_NEEDED_DIR.glob("*.txt"):
                    id_value = flag_file.stem

                    # Пропускаем, если уже уведомляли
                    if id_value in notified_ids:
                        continue

                    # Читаем содержимое файла
                    try:
                        with open(flag_file, "r", encoding="utf-8") as f:
                            content = f.read()
                    except Exception as e:
                        logger.warning(f"Не удалось прочитать {flag_file}: {e}")
                        continue

                    # Извлекаем папку из файла
                    photo_folder = None
                    for line in content.splitlines():
                        if line.startswith("folder="):
                            photo_folder = line.split("=", 1)[1].strip()
                            break

                    # Формируем сообщение
                    message = (
                        f"📸 <b>Фотографии закончились!</b>\n\n"
                        f"🆔 ID: <code>{id_value}</code>\n"
                    )
                    if photo_folder:
                        message += f"📁 Папка: <code>{photo_folder}</code>\n"
                    message += (
                        f"\n"
                        f"🔄 Добавьте фото в папку и выполните команду:\n"
                        f"<code>/photo_resume {id_value}</code>"
                    )

                    # Отправляем уведомление
                    try:
                        bot.send_message(
                            CHAT_ID,
                            message,
                            parse_mode="HTML",
                        )
                        notified_ids.add(id_value)
                        logger.info(f"✅ Уведомление отправлено для ID {id_value}")
                    except Exception as e:
                        logger.error(f"❌ Ошибка отправки уведомления: {e}")

            except Exception as e:
                logger.error(f"Ошибка в check_photo_needed_files: {e}")

            time.sleep(30)  # Проверяем каждые 30 сек

    thread = threading.Thread(target=loop, daemon=True)
    thread.start()
    logger.info("🔍 Фоновая проверка файлов запущена (каждые 30 сек)")


# ================== КОМАНДЫ БОТА ==================
@bot.message_handler(commands=["start", "help"])
def cmd_start(message):
    bot.reply_to(
        message,
        "🤖 Бот уведомлений о пополнении фото.\n\n"
        "Когда в tebor заканчиваются фото, бот отправляет уведомление.\n"
        "После добавления фото выполните:\n"
        "<code>/photo_resume &lt;id&gt;</code>\n\n"
        "Пример: <code>/photo_resume 1348</code>",
        parse_mode="HTML",
    )


@bot.message_handler(commands=["photo_resume"])
def cmd_photo_resume(message):
    """Команда для удаления файла-флага — tebor продолжит работу."""
    parts = message.text.split()
    if len(parts) < 2:
        bot.reply_to(
            message,
            "❌ Укажите ID: <code>/photo_resume &lt;id&gt;</code>\n"
            "Пример: <code>/photo_resume 1348</code>",
            parse_mode="HTML",
        )
        return

    id_value = parts[1].strip()
    flag_file = PHOTO_NEEDED_DIR / f"{id_value}.txt"

    if not flag_file.exists():
        bot.reply_to(
            message,
            f"ℹ️ Для ID <code>{id_value}</code> нет активного запроса.\n\n"
            f"Возможно, tebor ещё не закончил фото или уже получил сигнал.",
            parse_mode="HTML",
        )
        return

    # Читаем содержимое для отчёта
    photo_folder = None
    try:
        with open(flag_file, "r", encoding="utf-8") as f:
            for line in f:
                if line.startswith("folder="):
                    photo_folder = line.split("=", 1)[1].strip()
                    break
    except Exception:
        pass

    # Проверяем наличие фото в папке
    if photo_folder and os.path.exists(photo_folder):
        photos = [
            f
            for f in os.listdir(photo_folder)
            if f.lower().endswith((".jpg", ".jpeg", ".png", ".gif", ".bmp"))
        ]
        photos_count = len(photos)
    else:
        photos_count = 0

    # Удаляем файл-флаг
    try:
        flag_file.unlink()
        logger.info(f"🗑️ Файл-флаг удалён: {flag_file}")
    except Exception as e:
        bot.reply_to(message, f"❌ Не удалось удалить флаг: {e}")
        return

    # Убираем из списка уведомлённых
    notified_ids.discard(id_value)

    # Отвечаем пользователю
    response = f"✅ Сигнал отправлен для ID <code>{id_value}</code>.\n\n"
    if photo_folder:
        response += f"📁 Папка: <code>{photo_folder}</code>\n"
        response += f"📸 Фото в папке: {photos_count}\n\n"
    if photos_count == 0:
        response += "⚠️ Папка пуста! tebor снова запросит пополнение."
    else:
        response += f"🔄 tebor продолжит загрузку {photos_count} фото."

    bot.reply_to(message, response, parse_mode="HTML")


@bot.message_handler(commands=["list_needed"])
def cmd_list_needed(message):
    """Показать все ID, для которых ожидается пополнение."""
    flags = list(PHOTO_NEEDED_DIR.glob("*.txt"))

    if not flags:
        bot.reply_to(message, "ℹ️ Нет активных запросов на пополнение.")
        return

    response = f"📋 Активные запросы ({len(flags)}):\n\n"
    for flag_file in flags:
        id_value = flag_file.stem
        response += f"• <code>{id_value}</code>\n"

    bot.reply_to(message, response, parse_mode="HTML")


@bot.message_handler(commands=["clear_all"])
def cmd_clear_all(message):
    """Удалить все файлы-флаги (для экстренных случаев)."""
    flags = list(PHOTO_NEEDED_DIR.glob("*.txt"))

    if not flags:
        bot.reply_to(message, "ℹ️ Нет активных запросов.")
        return

    for flag_file in flags:
        try:
            flag_file.unlink()
            notified_ids.discard(flag_file.stem)
        except Exception as e:
            logger.warning(f"Не удалось удалить {flag_file}: {e}")

    bot.reply_to(message, f"🗑️ Удалено {len(flags)} файлов-флагов.")


# ================== ЗАПУСК ==================
if __name__ == "__main__":
    print("🚀 Бот уведомлений о пополнении фото запущен...")
    print(f"📁 Папка флагов: {PHOTO_NEEDED_DIR}")
    print(f"📨 Chat ID: {CHAT_ID}")
    print()
    print("Команды:")
    print("  /start — помощь")
    print("  /photo_resume <id> — сигнал tebor продолжить")
    print("  /list_needed — список активных запросов")
    print("  /clear_all — удалить все флаги")
    print()

    # Запускаем фоновую проверку файлов
    check_photo_needed_files()

    # Запускаем polling
    try:
        bot.infinity_polling(timeout=60, long_polling_timeout=60)
    except KeyboardInterrupt:
        print("\n👋 Бот остановлен")
    except Exception as e:
        logger.critical(f"💥 Критическая ошибка: {e}")
