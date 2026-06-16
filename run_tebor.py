import os
import sys
import time
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

sys.path.insert(0, str(Path(__file__).parent))

from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service

from profile_script.photo_path import get_photo_path
from profile_script.tebor import TaborPhotoUploader

if __name__ == "__main__":
    import argparse
    import traceback

    parser = argparse.ArgumentParser(description="Tabor photo uploader")
    parser.add_argument("--profile-id", help="ID профиля")
    parser.add_argument("--port", type=int, required=True, help="CDP порт")
    parser.add_argument("--login", help="Логин")
    parser.add_argument("--password", help="Пароль")
    parser.add_argument("--auto", action="store_true", help="Автоматический режим")
    parser.add_argument(
        "--profile-name", help="Имя профиля для отображения", default=None
    )
    parser.add_argument(
        "--photo-folder", help="Путь к папке с фотографиями", default=None
    )

    args = parser.parse_args()

    profile_id = args.profile_id or "unknown"
    profile_name = args.profile_name or "без имени"
    print(
        f'🚀 Запуск tebor.py: профиль "{profile_name}" (ID: {profile_id}), порт: {args.port}, auto={args.auto}'
    )

    LOGIN = args.login or os.getenv("TABOR_LOGIN")
    PASSWORD = args.password or os.getenv("TABOR_PASSWORD")

    # Определяем папку с фото
    if args.photo_folder:
        photo_folder = args.photo_folder
    else:
        photo_folder = os.getenv("FOLDER_PHOTO_PATH")

    if photo_folder:
        PHOTO_PATHS = get_photo_path(photo_folder) or []
        print(f"📁 Папка с фото: {photo_folder}")
        print(f"🖼️  Найдено фото: {len(PHOTO_PATHS)}")
    else:
        PHOTO_PATHS = []
        print("⚠️  Папка с фото не указана. Загрузка будет пропущена.")

    if not PHOTO_PATHS:
        print("❌ Нет фотографий для загрузки. Скрипт завершится после авторизации.")

    options = Options()
    options.add_experimental_option("debuggerAddress", f"127.0.0.1:{args.port}")
    service = Service(r"C:\chromedriver_148\chromedriver-win64\chromedriver.exe")

    try:
        driver = webdriver.Chrome(service=service, options=options)
        print(
            f"✅ Selenium подключился к профилю {args.profile_id or 'unknown'} на порту {args.port}"
        )

        uploader = TaborPhotoUploader(driver, LOGIN, PASSWORD)

        if args.auto:
            if LOGIN and PASSWORD:
                uploader.login(LOGIN, PASSWORD)
                if PHOTO_PATHS:
                    # uploader.go_to_photo_section()
                    uploader.monitor_photos(PHOTO_PATHS)  # исправлено
                else:
                    print("⚠️  Нет фото для загрузки.")
            else:
                print("\n🔐 Отсутствуют логин/пароль. Перехожу в ручной режим.")
                driver.get("https://tabor.ru")
                print("👆 Авторизуйтесь вручную, затем нажмите Enter.")
                input("⏎ Нажмите Enter после успешного входа...")
                if PHOTO_PATHS:
                    # uploader.go_to_photo_section()
                    uploader.monitor_photos(PHOTO_PATHS)  # исправлено
                else:
                    print("⚠️  Нет фото для загрузки. Ожидание завершения.")
                    input("Нажмите Enter для выхода...")
        else:
            driver.get("https://tabor.ru")
            print("✅ Браузер открыт на tabor.ru")
            print("Нажмите Ctrl+C для завершения.")
            try:
                while True:
                    time.sleep(1)
            except KeyboardInterrupt:
                pass

    except Exception as e:
        print(f"❌ Ошибка: {e}")
        traceback.print_exc()
        input("Enter для выхода...")
    finally:
        try:
            driver.quit()
        except:
            pass
