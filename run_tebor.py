import os
import sys
import time
from pathlib import Path

from dotenv import load_dotenv
load_dotenv()

sys.path.insert(0, str(Path(__file__).parent))

from profile_script.photo_path import get_photo_path
from profile_script.tebor import TaborPhotoUploader, send_telegram
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service

PHOTO_PATHS = get_photo_path(os.getenv("FOLDER_PHOTO_PATH")) or []

if __name__ == "__main__":
    import argparse
    import traceback

    parser = argparse.ArgumentParser(description="Tabor photo uploader")
    parser.add_argument("--profile-id", help="ID профиля")
    parser.add_argument("--port", type=int, required=True, help="CDP порт")
    parser.add_argument("--login", help="Логин")
    parser.add_argument("--password", help="Пароль")
    parser.add_argument("--auto", action="store_true", help="Автоматический режим")
    args = parser.parse_args()

    LOGIN = args.login or os.getenv("TABOR_LOGIN")
    PASSWORD = args.password or os.getenv("TABOR_PASSWORD")

    print(f"🚀 Запуск tebor.py: profile_id={args.profile_id}, port={args.port}, auto={args.auto}")

    options = Options()
    options.add_experimental_option("debuggerAddress", f"127.0.0.1:{args.port}")
    service = Service(r"C:\chromedriver_148\chromedriver-win64\chromedriver.exe")

    try:
        driver = webdriver.Chrome(service=service, options=options)
        print(f"✅ Selenium подключился к профилю {args.profile_id or 'unknown'} на порту {args.port}")

        if args.auto and LOGIN and PASSWORD:
            uploader = TaborPhotoUploader(driver, LOGIN, PASSWORD)
            uploader.login(LOGIN, PASSWORD)
            uploader.go_to_photo_section()
            uploader.monitor_photos(driver, PHOTO_PATHS)
        else:
            if args.auto and (not LOGIN or not PASSWORD):
                print("⚠️  Режим --auto включен, но не указаны TABOR_LOGIN/TABOR_PASSWORD в .env")
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