"""
Основной скрипт для работы с Browser Vision API
"""

import json
import os
import subprocess
import sys
import time
from datetime import datetime
from typing import Optional

import state_manager  # Импортируем менеджер состояний
from api_client import BrowserVisionClient
from config import FOLDER_ID, MODES
from fingerprint_generator import FingerprintGenerator
from profile_creator import ProfileCreator


def print_separator():
    """Выводит разделитель"""
    print("\n" + "=" * 60 + "\n")


def api_retry(func, *args, max_retries=3, delay=2, **kwargs):
    """
    Вызывает func(*args, **kwargs) с повторными попытками при ошибках.
    """
    for attempt in range(max_retries):
        try:
            return func(*args, **kwargs)
        except Exception as e:
            if attempt < max_retries - 1:
                print(
                    f"⚠️  Ошибка запроса (попытка {attempt + 1}/{max_retries}): {e}. Повтор через {delay}с..."
                )
                time.sleep(delay)
            else:
                raise


def show_current_folder_profiles(client):
    """Показывает профили в группе"""
    print("\n📂 Профили в группе")
    print(f"   ID группы: {FOLDER_ID}")
    print("-" * 60)
    profiles_data = api_retry(client.get_profiles, FOLDER_ID)
    if not profiles_data:
        print("❌ Не удалось получить профили ")
        return

    total = profiles_data.get("total", 0)
    profiles = profiles_data.get("items", [])

    print(f"📊 Всего профилей: {total}\n")

    if not profiles:
        print("⚠️  В группе нет профилей ")
        return

    for i, profile in enumerate(profiles, 1):
        name = profile.get("profile_name", "N/A")
        browser = profile.get("browser", "N/A")
        platform = profile.get("platform", "N/A")
        running = "🟢 " if profile.get("running") else "⚫ "
        worktime = profile.get("worktime", 0)

        hours = worktime // 3600
        minutes = (worktime % 3600) // 60
        worktime_str = f"{hours}ч {minutes}м " if hours > 0 else f"{minutes}м "

        print(f"{i}. {running} {name} ")
        print(f"   ID: {profile.get('id')} ")
        print(f"   {browser.upper()} / {platform} | ⏱️ {worktime_str} ")

        proxy = profile.get("proxy")
        if proxy:
            geo = proxy.get("geo_info", {})
            if geo:
                print(f"   🌐 {geo.get('city', 'N/A')}, {geo.get('country', 'N/A')} ")
            print(f"   🔒 {proxy.get('proxy_ip')}:{proxy.get('proxy_port')} ")
        print()
    print("=" * 60)


def create_single_profile(client, fg, creator):
    """Создаёт один профиль"""
    print(f"\n📝 Создание профиля в группу: {FOLDER_ID} ")
    print("-" * 60)

    fingerprint = fg.generate(
        webrtc_mode=MODES["AUTO"],
        webgl_mode=MODES["MANUAL"],
        canvas_mode=MODES["MANUAL"],
        audio_mode=MODES["MANUAL"],
        client_rects_mode=MODES["MANUAL"],
        random_gpu=True,
        random_webcam=True,
        random_language=False,
        random_timezone=False,
    )
    fg.print_info(fingerprint)

    confirm = input("\nСоздать профиль? (y/n): ").strip().lower()
    if confirm != "y":
        print("⚠️  Создание отменено ")
        return

    result = creator.create_with_sequential_config(fingerprint)
    if result:
        profile_id = creator._extract_profile_id(result)
        if profile_id:
            cdp_port = ProfileCreator.generate_cdp_port()
            print(f"🔌 Генерируем CDP порт: {cdp_port} ")
            start_result = client.start_profile(FOLDER_ID, profile_id, port=cdp_port)
            if start_result:
                actual_port = start_result.get("port") or cdp_port
                profile_name = (
                    result.get("profile_name")
                    or result.get("name")
                    or start_result.get("profile_name")
                )

                # Сохраняем в файл
                state_manager.add(profile_id, actual_port, profile_name)

                print("✅ Профиль запущен автоматически ")
                print(f"🔗 CDP URL: http://127.0.0.1:{actual_port} ")
                run_tebor_py(profile_id, actual_port, profile_name)
            else:
                print("⚠️  Профиль создан, но не удалось автоматически запустить ")


def get_photo_folder(profile_id: str, custom_folder: str = None) -> str:
    if custom_folder:
        return custom_folder
    if profile_id and profile_id != "unknown":
        auto_folder = f"D:\\python\\selenium-test\\downloads\\extracted\\{profile_id}"
        if os.path.exists(auto_folder):
            return auto_folder
    return None


def run_tebor_py(
    profile_id: str,
    port: int,
    profile_name: str = None,
    photo_folder: str = None,
    person_id: str = None,
):
    """Запускает tebor.py для профиля в отдельном окне"""
    import socket
    from pathlib import Path

    run_tebor_path = Path(__file__).parent / "run_tebor.py"

    if photo_folder is None and person_id:
        photo_folder = get_photo_folder_by_person_id(person_id)
    if photo_folder is None:
        photo_folder = ask_photo_folder(person_id, profile_name)

    print("   ⏳ Ожидание запуска профиля... ")
    for attempt in range(15):
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(1)
            result = sock.connect_ex(("127.0.0.1", port))
            sock.close()
            if result == 0:
                print(f"   ✅ Порт {port} доступен (через {attempt + 1}s) ")
                break
        except Exception:
            pass
        time.sleep(1)
    else:
        print(f"   ⚠️ Порт {port} недоступен, запустим без ожидания ")

    console_title = f"Tebor - {profile_name} ({profile_id[:8]}...)"
    cmd = [
        sys.executable,
        str(run_tebor_path),
        "--profile-id",
        profile_id,
        "--port",
        str(port),
        "--auto",
    ]
    if profile_name:
        cmd.extend(["--profile-name", profile_name])
    if photo_folder:
        cmd.extend(["--photo-folder", photo_folder])
        print(f"   📁 Фото из папки: {photo_folder} ")

    print(f"   🚀 Запуск Selenium: {' '.join(cmd)} ")
    process = subprocess.Popen(cmd, creationflags=subprocess.CREATE_NEW_CONSOLE)
    return process.pid, console_title  # 🆕 Возвращаем PID и заголовок


def create_batch_profiles(client, fg, creator):
    """Создаёт несколько профилей и автоматически запускает их"""
    print(f"\n🚀 Массовое создание в группу: {FOLDER_ID}")
    print("-" * 60)

    try:
        count = int(input("Количество профилей (1-100): ").strip())
        if count < 1 or count > 100:
            print("❌ Количество должно быть от 1 до 100")
            return
    except ValueError:
        print("❌ Введите корректное число")
        return

    print(
        "🧾 Имена будут взяты последовательно из config/pers_id.txt и config/town.txt"
    )
    print("🔌 Прокси будут взяты последовательно из config/proxy.txt")
    print("🔌 Selenium CDP порты будут сгенерированы автоматически")

    # Спрашиваем про папку с фото: одну для всех или для каждого отдельно
    print("\n📁 Настройка папок с фотографиями:")
    print("   1. Одна папка для всех профилей")
    print("   2. Разные папки (будет запрошено для каждого)")
    folder_choice = input("👉 Выберите (1/2): ").strip()

    common_photo_folder = None
    if folder_choice == "1":
        common_photo_folder = ask_photo_folder()
    elif folder_choice != "2":
        print("⚠️  Неверный выбор, будет запрошено для каждого профиля отдельно")

    confirm = input(f"\nСоздать {count} профилей? (y/n): ").strip().lower()
    if confirm != "y":
        print("⚠️  Создание отменено")
        return

    results = creator.create_batch(
        count=count,
        webrtc_mode=MODES["AUTO"],
        webgl_mode=MODES["MANUAL"],
        canvas_mode=MODES["MANUAL"],
        audio_mode=MODES["MANUAL"],
        client_rects_mode=MODES["MANUAL"],
        random_gpu=True,
        random_webcam=True,
    )


def extract_person_id_from_profile(profile: dict) -> Optional[str]:
    profile_name = profile.get("profile_name", "")
    if not profile_name:
        return None
    if "-" in profile_name:
        person_id = profile_name.split("-")[0].strip()
        if person_id:
            return person_id
    person_id = profile.get("id")
    return str(person_id) if person_id else None


def get_photo_folder_by_person_id(person_id: str) -> str:
    if person_id:
        auto_folder = f"D:\\python\\selenium-test\\downloads\\extracted\\{person_id}"
        if os.path.exists(auto_folder):
            return auto_folder
    return None


def ask_photo_folder(person_id: str = None, profile_name: str = None) -> str:
    auto_folder = get_photo_folder_by_person_id(person_id) if person_id else None
    name_hint = f' для профиля "{profile_name}"' if profile_name else ""
    print("\n📁 Укажите путь к папке с фотографиями" + name_hint)
    if auto_folder:
        print(f"   (Enter = использовать автоматический путь: {auto_folder})")
    folder = input("👉 Путь к папке: ").strip()
    if not folder and auto_folder:
        return auto_folder
    return folder if folder else None


def launch_selected_profiles(
    client, selection_text: str, common_photo_folder: str = None
) -> bool:
    """Запускает несколько профилей из группы по номерам и сразу открывает tebor."""
    profiles_data = api_retry(client.get_profiles, FOLDER_ID)
    if not profiles_data:
        return False
    profiles = profiles_data.get("items", [])
    if not profiles:
        return False

    indices = parse_selection(selection_text, len(profiles))
    if indices is None:
        return False

    # Читаем актуальное состояние из файла
    active_map = state_manager.get_all()

    use_auto_folders = common_photo_folder == "auto"
    use_individual_folders = common_photo_folder is None and not use_auto_folders

    launched_any = False
    for idx in indices:
        profile = profiles[idx]
        person_id = extract_person_id_from_profile(profile)
        profile_uuid = (
            profile.get("uuid") or profile.get("profile_id") or str(profile.get("id"))
        )
        name = profile.get("profile_name", "N/A")

        if profile_uuid in active_map:
            print(
                f"\n⚠️ Профиль {idx + 1}. {name} ({profile_uuid}) уже запущен на порту {active_map[profile_uuid]['port']} "
            )
            continue

        # 1. СНАЧАЛА определяем папку с фото для этого профиля
        if use_auto_folders:
            photo_folder = get_photo_folder_by_person_id(person_id)
        elif use_individual_folders:
            photo_folder = ask_photo_folder(person_id, name)
        else:
            photo_folder = common_photo_folder

        cdp_port = ProfileCreator.generate_cdp_port()
        print(f"\n[{idx + 1}/{len(profiles)}] Запуск профиля {name} ")

        start_result = client.start_profile(FOLDER_ID, profile_uuid, port=cdp_port)
        if start_result:
            actual_port = start_result.get("port") or cdp_port

            # 2. Запускаем tebor ОДИН раз с уже известной папкой
            pid, console_title = run_tebor_py(
                profile_uuid, actual_port, name, photo_folder, person_id
            )

            # 3. Сохраняем в state_manager
            state_manager.add(
                profile_uuid,
                actual_port,
                name,
                person_id,
                tebor_pid=pid,
                console_title=console_title,
            )
            print(f"   ✅ Запущен | CDP: http://127.0.0.1:{actual_port} ")
            launched_any = True
        else:
            print("   ❌ Не удалось запустить ")

    return launched_any


def run_tebor_for_selected(selection_text: str) -> bool:
    """Запускает tebor для уже запущенных профилей по номерам."""
    active_map = state_manager.get_all()
    if not active_map:
        print("⚠️  Нет запущенных через эту сессию профилей")
        return False

    profiles = list(active_map.items())
    numbered = "\n".join(
        f"  {i}. {p[1]['name']} (порт {p[1]['port']}, человек ID={p[1].get('person_id', 'N/A')}) — {p[0]}"
        for i, p in enumerate(profiles)
    )
    print("\n🟢 Запущенные в этой сессии: ")
    print(numbered)

    indices = parse_selection(selection_text, len(profiles))
    if indices is None:
        return False

    print("\n📁 Настройка папок с фотографиями: ")
    print("   1. Одна папка для всех выбранных профилей ")
    print("   2. Разные папки (будет запрошено для каждого) ")
    print("   3. Автоматически (по ID человека из имени профиля) для каждого ")
    folder_choice = input("👉 Выберите (1/2/3): ").strip()

    common_photo_folder = None
    if folder_choice == "1":
        common_photo_folder = ask_photo_folder()
    elif folder_choice == "3":
        common_photo_folder = "auto"

    launched_any = False
    for idx in indices:
        pid, data = profiles[idx]
        port = data["port"]
        name = data["name"]
        person_id = data.get("person_id")

        if folder_choice == "2":
            photo_folder = ask_photo_folder(person_id, name)
        elif folder_choice == "3" or common_photo_folder == "auto":
            photo_folder = get_photo_folder_by_person_id(person_id)
        else:
            photo_folder = common_photo_folder

        run_tebor_py(pid, port, name, photo_folder, person_id)
        launched_any = True
    return launched_any


def show_running_profiles(client):
    print("\n🟢 Запущенные профили")
    print("-" * 60)
    active_profiles = state_manager.get_all()
    if not active_profiles:
        print("⚠️  Нет запущенных профилей ")
        return

    for i, (profile_id, data) in enumerate(active_profiles.items(), 1):
        name = data.get("name", "N/A")
        port = data.get("port", "N/A")

        # 🆕 Читаем состояние консоли из heartbeat-файла
        hb_file = os.path.join("logs", "console_heartbeat", f"{profile_id}.json")
        console_status = "⚫ Нет данных"
        if os.path.exists(hb_file):
            try:
                with open(hb_file, "r", encoding="utf-8") as f:
                    hb = json.load(f)
                last_update = datetime.fromisoformat(hb["last_update"])
                diff = (datetime.now() - last_update).total_seconds()
                if diff < 30:
                    console_status = (
                        f"🟢 {hb.get('status', 'Working')} ({int(diff)}с назад)"
                    )
                else:
                    console_status = f"🟡 Зависла? ({int(diff)}с назад)"
            except Exception:
                console_status = "⚠️ Ошибка чтения"

        print(f"{i}. {name} (порт: {port})")
        print(f"   Консоль: {console_status}")
        print()


def ask_profile_id() -> Optional[str]:
    profile_id = input("\nID профиля: ").strip()
    return profile_id or None


def start_profile_with_stored_port(client):
    """Запускает профиль с сохранённым CDP-портом."""
    profile_id = ask_profile_id()
    if not profile_id:
        print("❌ ID профиля не указан")
        return None
    profile = client.get_profile_by_id(FOLDER_ID, profile_id)
    if not profile:
        print("❌ Профиль не найден ")
        return None

    port = ProfileCreator.extract_debug_port(profile)
    if not port:
        port = ProfileCreator.generate_cdp_port()
        print(f"🔌 Генерируем CDP порт: {port} ")

    result = client.start_profile(FOLDER_ID, profile_id, port=port)
    if result:
        actual_port = result.get("port") or port
        profile_name = profile.get("profile_name", "N/A")
        print("✅ Профиль запущен ")
        if actual_port:
            print(f"🔗 CDP URL: http://127.0.0.1:{actual_port} ")
            # Сохраняем в файл
            state_manager.add(profile_id, actual_port, profile_name)
            return profile_id, actual_port, profile_name
    else:
        print("❌ Не удалось запустить профиль ")
    return None


def stop_profile(client):
    """Останавливает профиль."""
    profile_id = ask_profile_id()
    if not profile_id:
        print("❌ ID профиля не указан")
        return
    result = client.stop_profile(FOLDER_ID, profile_id)
    if result:
        print("✅ Профиль остановлен")
        # Удаляем из файла
        state_manager.remove(profile_id)
        print("   Удален из списка активных")
    else:
        print("❌ Не удалось остановить профиль")


def parse_selection(text: str, max_index: int) -> Optional[list]:
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
                print(f"❌ Неверный диапазон: {part} ")
                return None
            if start < 1:
                start = 1
            if end > max_index:
                end = max_index
            if start > end:
                print(f"❌ Некорректный диапазон: {start}-{end} ")
                return None
            selected.extend(list(range(start - 1, end)))
        else:
            try:
                idx = int(part)
            except ValueError:
                print(f"❌ Неверный номер: {part} ")
                return None
            if idx < 1:
                idx = 1
            if idx > max_index:
                idx = max_index
            selected.append(idx - 1)
    return sorted(set(selected))


def menu_launch_multiple_profiles(client):
    """Меню запуска нескольких профилей из текущей группы (с номерами)."""
    while True:
        print_separator()
        print("📂 Профили в рабочей группе ")
        print("-" * 60)
        profiles_data = api_retry(client.get_profiles, FOLDER_ID)
        if not profiles_data:
            return
        profiles = profiles_data.get("items", [])
        total = profiles_data.get("total", 0)
        print(f"📊 Всего: {total}\n")

        for i, profile in enumerate(profiles, 1):
            name = profile.get("profile_name", "N/A")
            status = "🟢 " if profile.get("running") else "⚫ "
            print(f"{i}. {status} {name} ")

        print("\nВведите номера через запятую или диапазон (1-5, 7, 9-12) ")
        print("0 — назад ")
        sel = input("👉 Номера: ").strip()
        if sel == "0":
            return

        print("\n📁 Настройка папок с фотографиями: ")
        print("   1. Одна папка для всех выбранных профилей ")
        print("   2. Разные папки (будет запрошено для каждого) ")
        print("   3. Автоматически (по ID профиля) для каждого ")
        folder_choice = input("👉 Выберите (1/2/3): ").strip()

        common_photo_folder = None
        if folder_choice == "1":
            common_photo_folder = ask_photo_folder()
        elif folder_choice == "3":
            common_photo_folder = "auto"

        if launch_selected_profiles(client, sel, common_photo_folder):
            print("✅ Команда запуска выполнена ")


def menu_run_tebor_multiple():
    """Меню запуска tebor для нескольких уже запущенных профилей."""
    active_map = state_manager.get_all()
    if not active_map:
        print("⚠️  Нет запущенных через эту сессию профилей")
        input("Enter для возврата...")
        return

    while True:
        print_separator()
        print("🚀 Запуск tebor для запущенных профилей ")
        print("-" * 60)
        profiles = list(active_map.items())
        for i, (pid, data) in enumerate(profiles, 1):
            print(f"{i}. {data['name']} (порт {data['port']}) — {pid} ")

        print("\nВведите номера через запятую или диапазон (1-5, 7, 9-12) ")
        print("0 — назад ")
        sel = input("👉 Номера: ").strip()
        if sel == "0":
            return

        if run_tebor_for_selected(sel):
            print("✅ tebor запущен(а) ")


def menu_stop_multiple(client):
    from window_utils import kill_console_and_process

    """Меню остановки нескольких профилей."""
    while True:
        print_separator()
        print("⛔ Остановка нескольких профилей")
        print("-" * 60)

        active_profiles = state_manager.get_all()
        if not active_profiles:
            print("⚠️  Нет запущенных профилей ")
            input("\nНажмите Enter для возврата... ")
            return

        profiles_list = list(active_profiles.items())
        print(f"📊 Запущено профилей: {len(profiles_list)}\n")
        for i, (profile_id, data) in enumerate(profiles_list, 1):
            name = data.get("name", "N/A")
            port = data.get("port", "N/A")
            print(f"{i}. 🟢 {name} (порт: {port}) ")

        print("\nВведите номера через запятую или диапазон (1-5, 7, 9-12) ")
        print("0 — назад ")
        sel = input("👉 Номера: ").strip()
        if sel == "0":
            return

        indices = parse_selection(sel, len(profiles_list))
        if indices is None:
            continue

        stopped_count = 0
        for idx in indices:
            profile_id, data = profiles_list[idx]
            name = data.get("name", "N/A")
            console_title = data.get("console_title", "")
            tebor_pid = data.get("tebor_pid")

            print(f"\n⛔ Останавливаем {name} ({profile_id})... ")

            result = client.stop_profile(FOLDER_ID, profile_id)
            if result is not None:
                print("   ✅ Остановлен ")
                state_manager.remove(profile_id)  # Удаляем из файла
                stopped_count += 1
            else:
                print("   ❌ Не удалось остановить ")

            if console_title or tebor_pid:
                killed = kill_console_and_process(console_title, tebor_pid)
                if killed > 0:
                    print("   🔪 Окно консоли и процесс закрыты")

            state_manager.remove(profile_id)

        if stopped_count > 0:
            print(f"\n✅ Успешно остановлено профилей: {stopped_count} ")
        input("\nНажмите Enter для продолжения... ")


def main():
    """Основная функция"""
    print("\n🌐 Browser Vision API Client")
    print(f"📂 Рабочая группа: {FOLDER_ID}")
    print("=" * 60)
    client = BrowserVisionClient(debug=False)

    print("\n🔌 Проверка соединения... ")
    if not client.test_connection():
        print("❌ Не удалось подключиться к API ")
        return
    print("✅ Соединение установлено ")

    fg = FingerprintGenerator(client)
    print("\n📥 Загрузка базового fingerprint... ")
    try:
        fg.load_base_fingerprint()
        print("✅ Базовый fingerprint загружен ")
    except Exception as e:
        print(f"❌ Ошибка загрузки fingerprint: {e} ")
        return

    creator = ProfileCreator(client, fg)
    # Словарь active_profiles больше не нужен, используем state_manager

    while True:
        print_separator()
        print("📋 Главное меню: ")
        print("-" * 60)
        print("  📊 ПРОСМОТР: ")
        print("    1. Профили в рабочей группе ")
        print("    9. Запущенные профили (из файла состояния)")
        print()
        print("  ➕ СОЗДАНИЕ: ")
        print("    3. Создать один профиль ")
        print("    4. Создать несколько профилей ")
        print()
        print("  🟢 ЗАПУСК SELENIUM/CDP: ")
        print("    10. Запустить профиль с сохранённым портом ")
        print("    11. Остановить профиль ")
        print("    12. Запустить несколько профилей ")
        print("    13. Запустить tebor для нескольких профилей ")
        print("    14. Остановить несколько профилей ")
        print()
        print("  ⚙️  ДРУГОЕ: ")
        print("    8. Проверить соединение ")
        print("    0. Выход ")
        print("-" * 60)

        choice = input("\n👉 Выберите действие: ").strip()

        try:
            if choice == "1":
                show_current_folder_profiles(client)
            elif choice == "3":
                create_single_profile(client, fg, creator)
            elif choice == "4":
                create_batch_profiles(client, fg, creator)
            elif choice == "8":
                print("\n🔌 Проверка соединения... ")
                if client.test_connection():
                    print("✅ Соединение работает! ")
                else:
                    print("❌ Соединение не установлено ")
            elif choice == "9":
                show_running_profiles(client)
            elif choice == "10":
                start_profile_with_stored_port(client)
            elif choice == "11":
                stop_profile(client)
            elif choice == "12":
                menu_launch_multiple_profiles(client)
            elif choice == "13":
                menu_run_tebor_multiple()
            elif choice == "14":
                menu_stop_multiple(client)
            elif choice == "0":
                print("\n👋 До свидания! ")
                break
            else:
                print("❌ Неверный выбор ")
        except KeyboardInterrupt:
            print("\n\n⚠️  Операция прервана ")
            continue
        except Exception as e:
            print(f"\n❌ Ошибка: {type(e).__name__}: {e} ")
            import traceback

            traceback.print_exc()
            continue


if __name__ == "__main__":
    main()
