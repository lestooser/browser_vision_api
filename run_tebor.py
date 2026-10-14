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

from config import AUTO_PHOTO_ROOT
from profile_script.photo_path import get_photo_path
from profile_script.tebor import TaborPhotoUploader, _resolve_chromedriver_path
from tebor_state import clear_state, set_state

load_dotenv()
sys.path.insert(0, str(Path(__file__).parent))


def create_chrome_service() -> Service:
    """Создаёт Service для ChromeDriver.

    Приоритет:
    1) CHROMEDRIVER_PATH (если задан и файл существует)
    2) Локальная папка chromedriver-win64 в проекте
    3) Selenium Manager (Service() без пути)
    """
    driver_path = _resolve_chromedriver_path()
    if driver_path:
        print(f"🔧 Использую ChromeDriver: {driver_path}")
        return Service(driver_path)
    return Service()


def set_console_title(title: str):
    try:
        ctypes.windll.kernel32.SetConsoleTitleW(title)
    except:
        pass


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument("--profile-id", required=True)
    parser.add_argument("--port", type=int, required=True)
    parser.add_argument("--profile-name", default="без имени")
    parser.add_argument("--photo-folder", default=None)
    parser.add_argument("--auto", action="store_true")
    args = parser.parse_args()

    profile_id = args.profile_id
    profile_name = args.profile_name

    set_console_title(f"Tebor - {profile_name} ({profile_id[:8]}...)")

    photo_folder = args.photo_folder
    if not photo_folder:
        person_id = profile_name.split("-")[0].strip() if "-" in profile_name else None
        if person_id:
            auto_path = str(AUTO_PHOTO_ROOT / person_id)
            if os.path.exists(auto_path):
                photo_folder = auto_path

    PHOTO_PATHS = get_photo_path(photo_folder) if photo_folder else []

    options = Options()
    options.add_experimental_option("debuggerAddress", f"127.0.0.1:{args.port}")
    service = create_chrome_service()
    driver = None

    try:
        driver = webdriver.Chrome(service=service, options=options)
        set_state(profile_id, "Инициализация", "Подключение к порту")

        safe_id = "".join(c for c in profile_name if c not in r'<>:"/\|?*').strip()
        uploader = TaborPhotoUploader(
            driver,
            os.getenv("TABOR_LOGIN"),
            os.getenv("TABOR_PASSWORD"),
            id_value=safe_id,
            photo_folder=photo_folder,
            profile_uuid=profile_id,
        )

        if args.auto:
            if not uploader.is_already_logged_in(timeout=10):
                set_state(profile_id, "Авторизация", "Ожидание капчи")
                uploader.login()
            uploader.go_to_photo_section()
            uploader.monitor_photos(PHOTO_PATHS)
        else:
            driver.get("https://tabor.ru")
            while True:
                time.sleep(1)

    except Exception as e:
        set_state(profile_id, "Краш", str(e))
        traceback.print_exc()
    finally:
        set_state(profile_id, "Остановлен", "Скрипт завершил работу")
        clear_state(profile_id)
        try:
            if driver:
                driver.quit()
        except:
            pass

        try:
            input("Нажмите Enter...")
        except EOFError:
            time.sleep(5)
