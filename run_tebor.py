import ctypes
import os
import sys
import time
import traceback
from pathlib import Path
from dotenv import load_dotenv
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from profile_script.photo_path import get_photo_path
# 🆕 Импортируем write_tg_event для отправки уведомлений о падении
from profile_script.tebor import TaborPhotoUploader, write_tg_event

load_dotenv()
sys.path.insert(0, str(Path(__file__).parent))

def set_console_title(title: str):
    try:
        ctypes.windll.kernel32.SetConsoleTitleW(title)
    except Exception:
        pass

def get_photo_folder(profile_id: str, person_id: str = None, custom_folder: str = None) -> str:
    """
    Определяет папку с фотографиями.
    Приоритет: custom_folder -> person_id -> profile_id -> .env
    """
    if custom_folder:
        return custom_folder

    # 🆕 Приоритет 1: Ищем по person_id (так как папки называются по ID человека)
    if person_id and person_id != "unknown":
        auto_folder = f"D:\\python\\selenium-test\\downloads\\extracted\\{person_id}"
        if os.path.exists(auto_folder):
            print(f"📁 Найдена папка профиля (по person_id): {auto_folder}")
            return auto_folder

    # Приоритет 2: Ищем по profile_id (UUID)
    if profile_id and profile_id != "unknown":
        auto_folder = f"D:\\python\\selenium-test\\downloads\\extracted\\{profile_id}"
        if os.path.exists(auto_folder):
            print(f"📁 Найдена папка профиля (по profile_id): {auto_folder}")
            return auto_folder

    env_folder = os.getenv("FOLDER_PHOTO_PATH")
    if env_folder:
        return env_folder

    return None

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Tabor photo uploader")
    parser.add_argument("--profile-id", help="UUID профиля")
    parser.add_argument("--person-id", help="ID человека (для уведомлений и папок)") # 🆕
    parser.add_argument("--port", type=int, required=True, help="CDP порт")
    parser.add_argument("--login", help="Логин")
    parser.add_argument("--password", help="Пароль")
    parser.add_argument("--auto", action="store_true", help="Автоматический режим")
    parser.add_argument("--profile-name", help="Имя профиля", default=None)
    parser.add_argument("--photo-folder", help="Путь к папке с фото", default=None)

    args = parser.parse_args()

    profile_id = args.profile_id or "unknown"
    person_id = args.person_id or None
    profile_name = args.profile_name or "без имени"

    # 🆕 Для уведомлений и поиска папок используем person_id, если он есть
    notify_id = person_id if person_id and person_id != "unknown" else profile_id

    title = f"Tebor - {profile_name} ({notify_id[:8]}...)"
    set_console_title(title)

    print(f'🚀 Запуск tebor.py: профиль "{profile_name}" (ID: {notify_id}), порт: {args.port}')

    LOGIN = args.login or os.getenv("TABOR_LOGIN")
    PASSWORD = args.password or os.getenv("TABOR_PASSWORD")

    # Определяем папку с фото (передаем person_id)
    photo_folder = get_photo_folder(profile_id, person_id, args.photo_folder)

    if photo_folder:
        PHOTO_PATHS = get_photo_path(photo_folder) or []
        print(f"📁 Папка с фото: {photo_folder}")
        print(f"🖼️ Найдено фото: {len(PHOTO_PATHS)}")
    else:
        PHOTO_PATHS = []
        print("⚠️ Папка с фото не найдена. Будет ожидание пополнения.")

    options = Options()
    options.add_experimental_option("debuggerAddress", f"127.0.0.1:{args.port}")
    service = Service(r"C:\chromedriver_148\chromedriver-win64\chromedriver.exe")

    driver = None
    try:
        driver = webdriver.Chrome(service=service, options=options)
        print(f"✅ Selenium подключился к порту {args.port}")

        # 🆕 Передаем notify_id (person_id), чтобы бот и tebor использовали его
        uploader = TaborPhotoUploader(driver, LOGIN, PASSWORD, id_value=notify_id)

        if args.auto:
            driver.get("https://tabor.ru")
            if uploader.is_already_logged_in(timeout=10):
                print("🔑 Профиль уже авторизован")
            elif LOGIN and PASSWORD:
                print("🔐 Требуется авторизация...")
                uploader.login()
                time.sleep(2)
            else:
                print("❌ Профиль не авторизован и нет логина/пароля.")
                sys.exit(1)

            uploader.go_to_photo_section()
            uploader.monitor_photos(PHOTO_PATHS)
        else:
            driver.get("https://tabor.ru")
            print("✅ Браузер открыт. Нажмите Ctrl+C для завершения.")
            try:
                while True:
                    time.sleep(1)
            except KeyboardInterrupt:
                pass

    except Exception as e:
        error_text = (
            f"❌ <b>Tebor упал!</b>\n"
            f"🆔 ID: <code>{notify_id}</code>\n"
            f"📛 Имя: {profile_name}\n\n"
            f"⚠️ Ошибка:\n<code>{str(e)}</code>"
        )
        print(error_text)
        traceback.print_exc()

        # 🆕 Оповещаем бота о падении консоли
        try:
            write_tg_event("crash", error_text, notify_id)
        except Exception as tg_err:
            print(f"⚠️ Не удалось отправить уведомление о падении в ТГ: {tg_err}")

        input("Enter для выхода...")
    finally:
        try:
            if driver:
                driver.quit()
        except Exception:
            pass
