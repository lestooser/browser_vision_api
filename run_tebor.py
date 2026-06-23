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

from console_monitor import start_monitor
from profile_script.photo_path import get_photo_path
from profile_script.tebor import TaborPhotoUploader

load_dotenv()
sys.path.insert(0, str(Path(__file__).parent))


def set_console_title(title: str):
    """Устанавливает заголовок окна консоли."""
    try:
        ctypes.windll.kernel32.SetConsoleTitleW(title)
    except Exception:
        pass


def get_photo_folder(profile_id: str, custom_folder: str = None) -> str:
    r"""
    Определяет папку с фотографиями для профиля.
    Приоритет:
    1. custom_folder (если передан через --photo-folder)
    2. Автоматический путь: D:\python\selenium-test\downloads\extracted\<profile_id>
    3. Переменная окружения FOLDER_PHOTO_PATH (если задана)
    """
    if custom_folder:
        return custom_folder

    if profile_id and profile_id != "unknown":
        auto_folder = f"D:\\python\\selenium-test\\downloads\\extracted\\{profile_id}"
        if os.path.exists(auto_folder):
            print(f"📁 Найдена папка профиля: {auto_folder}")
            return auto_folder
        else:
            print(f"⚠️ Папка профиля не найдена: {auto_folder}")

    env_folder = os.getenv("FOLDER_PHOTO_PATH")
    if env_folder:
        print(f"⚠️ Используем папку из .env: {env_folder}")
        return env_folder

    return None


if __name__ == "__main__":
    import argparse

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
        "--photo-folder",
        help="Путь к папке с фотографиями (переопределяет авто-путь)",
        default=None,
    )

    args = parser.parse_args()

    profile_id = args.profile_id or "unknown"
    profile_name = args.profile_name or "без имени"

    title = f"Tebor - {profile_name} ({profile_id[:8]}...)"
    set_console_title(title)

    start_monitor(profile_id, os.getpid(), title)

    print(
        f'🚀 Запуск tebor.py: профиль "{profile_name}" (ID: {profile_id}), '
        f"порт: {args.port}, auto={args.auto}"
    )

    LOGIN = args.login or os.getenv("TABOR_LOGIN")
    PASSWORD = args.password or os.getenv("TABOR_PASSWORD")

    # Определяем папку с фото
    photo_folder = get_photo_folder(profile_id, args.photo_folder)

    if photo_folder:
        PHOTO_PATHS = get_photo_path(photo_folder) or []
        print(f"📁 Папка с фото: {photo_folder}")
        print(f"🖼️  Найдено фото: {len(PHOTO_PATHS)}")
        if PHOTO_PATHS:
            for i, path in enumerate(PHOTO_PATHS[:3], 1):
                print(f"   {i}. {os.path.basename(path)}")
            if len(PHOTO_PATHS) > 3:
                print(f"   ... и ещё {len(PHOTO_PATHS) - 3} файлов")
    else:
        PHOTO_PATHS = []
        print("⚠️  Папка с фото не найдена. Будет предложено пополнение.")

    options = Options()
    options.add_experimental_option("debuggerAddress", f"127.0.0.1:{args.port}")
    service = Service(r"C:\chromedriver_148\chromedriver-win64\chromedriver.exe")

    driver = None
    try:
        driver = webdriver.Chrome(service=service, options=options)
        print(
            f"✅ Selenium подключился к профилю {args.profile_id or 'unknown'} "
            f"на порту {args.port}"
        )

        uploader = TaborPhotoUploader(driver, LOGIN, PASSWORD, id_value=profile_id)

        if args.auto:
            # 🆕 ВСЕГДА сначала проверяем авторизацию, даже без логина/пароля
            driver.get("https://tabor.ru")
            if uploader.is_already_logged_in(timeout=10):
                print("🔑 Профиль уже авторизован")
                # go_to_photo_section() сам кликнет по элементу профиля
            elif LOGIN and PASSWORD:
                print("🔐 Требуется авторизация...")
                uploader.login()  # ← БЕЗ аргументов! Они уже в __init__
                time.sleep(2)
            else:
                print("❌ Профиль не авторизован и нет логина/пароля.")
                print("   Укажите логин/пароль через --login/--password или в .env")
                sys.exit(1)

            # Переходим в галерею
            uploader.go_to_photo_section()

            # Запускаем мониторинг
            uploader.monitor_photos(PHOTO_PATHS)
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
            if driver:
                driver.quit()
        except Exception:
            pass
