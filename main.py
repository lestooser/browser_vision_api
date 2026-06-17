"""
Основной скрипт для работы с Browser Vision API
"""

import subprocess
import sys
import time
from typing import Dict, Optional

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
    Используется для нестабильных GET-запросов к API.
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
        print("❌ Не удалось получить профили")
        return

    total = profiles_data.get("total", 0)
    profiles = profiles_data.get("items", [])

    print(f"📊 Всего профилей: {total}\n")

    if not profiles:
        print("⚠️  В группе нет профилей")
        return

    for i, profile in enumerate(profiles, 1):
        name = profile.get("profile_name", "N/A")
        browser = profile.get("browser", "N/A")
        platform = profile.get("platform", "N/A")
        running = "🟢" if profile.get("running") else "⚫"
        worktime = profile.get("worktime", 0)

        hours = worktime // 3600
        minutes = (worktime % 3600) // 60
        worktime_str = f"{hours}ч {minutes}м" if hours > 0 else f"{minutes}м"

        print(f"{i}. {running} {name}")
        print(f"   ID: {profile.get('id')}")
        print(f"   {browser.upper()} / {platform} | ⏱️ {worktime_str}")

        proxy = profile.get("proxy")
        if proxy:
            geo = proxy.get("geo_info", {})
            if geo:
                print(f"   🌐 {geo.get('city', 'N/A')}, {geo.get('country', 'N/A')}")
            print(f"   🔒 {proxy.get('proxy_ip')}:{proxy.get('proxy_port')}")

        print()

    print("=" * 60)


def create_single_profile(client, fg, creator):
    """Создаёт один профиль"""
    print(f"\n📝 Создание профиля в группу: {FOLDER_ID}")
    print("-" * 60)
    print("🧾 Имя будет взято последовательно из config/pers_id.txt и config/town.txt")
    print("🔌 Прокси будет взят последовательно из config/proxy.txt")
    print("🔌 Selenium CDP порт будет сгенерирован автоматически")

    print("\n⚙️  Применяются обязательные настройки профиля:")
    print("  • Canvas: Noise")
    print("  • WebGL: Noise")
    print("  • Audio: Noise")
    print("  • Client Rects: Noise")
    print("  • Media devices: 1 / 1 / 1")

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
        print("⚠️  Создание отменено")
        return

    result = creator.create_with_sequential_config(fingerprint)
    if result:
        profile_id = creator._extract_profile_id(result)
        if profile_id:
            cdp_port = ProfileCreator.generate_cdp_port()
            print(f"🔌 Генерируем CDP порт: {cdp_port}")
            start_result = client.start_profile(FOLDER_ID, profile_id, port=cdp_port)
            if start_result:
                print(f"   📊 Ответ сервера: {start_result}")
                actual_port = start_result.get("port") or cdp_port
                profile_name = (
                    result.get("profile_name")
                    or result.get("name")
                    or start_result.get("profile_name")
                )
                print("✅ Профиль запущен автоматически")
                print(f"🔗 CDP URL: http://127.0.0.1:{actual_port}")
                run_tebor_py(profile_id, actual_port, profile_name)
            else:
                print("⚠️  Профиль создан, но не удалось автоматически запустить")
                print("   Проверьте:")
                print(
                    "   - Запущен ли Browser Vision локальный сервер (127.0.0.1:3030)"
                )
                print("   - Правильный ли токен в config.py")


def ask_photo_folder(profile_name: str = None) -> str:
    """Запрашивает у пользователя путь к папке с фото для профиля."""
    name_hint = f' для профиля "{profile_name}"' if profile_name else ""
    print()
    print("📁 Укажите путь к папке с фотографиями" + name_hint)
    print("   (оставьте пустым, чтобы использовать FOLDER_PHOTO_PATH из .env)")
    folder = input("👉 Путь к папке: ").strip()
    return folder if folder else None


def run_tebor_py(
    profile_id: str, port: int, profile_name: str = None, photo_folder: str = None
):
    """Запускает tebor.py для профиля в отдельном окне"""
    import socket
    from pathlib import Path

    run_tebor_path = Path(__file__).parent / "run_tebor.py"

    # Запрашиваем папку с фото, если не передана
    if photo_folder is None:
        photo_folder = ask_photo_folder(profile_name)

    print("   ⏳ Ожидание запуска профиля...")
    for attempt in range(15):
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(1)
            result = sock.connect_ex(("127.0.0.1", port))
            sock.close()
            if result == 0:
                print(f"   ✅ Порт {port} доступен (через {attempt + 1}s)")
                break
        except Exception:
            pass
        time.sleep(1)
    else:
        print(f"   ⚠️ Порт {port} недоступен, запустим без ожидания")

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
        print(f"   📁 Фото из папки: {photo_folder}")
    else:
        print("   📁 Фото из папки по умолчанию (FOLDER_PHOTO_PATH)")

    print(f"   🚀 Запуск Selenium: {' '.join(cmd)}")
    subprocess.Popen(cmd, creationflags=subprocess.CREATE_NEW_CONSOLE)


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

    # for i, result in enumerate(results, 1):
    #     if result:
    #         profile_id = creator._extract_profile_id(result)
    #         if profile_id:
    #             cdp_port = ProfileCreator.generate_cdp_port()
    #             profile_name = result.get("profile_name") or result.get("name")
    #             print(
    #                 f'\n[{i}/{count}] Запуск профиля "{profile_name}" ({profile_id}) на порту {cdp_port}'
    #             )

    #             start_result = client.start_profile(
    #                 FOLDER_ID, profile_id, port=cdp_port
    #             )
    #             if start_result:
    #                 actual_port = start_result.get("port") or cdp_port
    #                 print(f"   ✅ Запущен | CDP: http://127.0.0.1:{actual_port}")

    #                 # Папка для этого профиля
    #                 photo_folder = common_photo_folder
    #                 if folder_choice == "2":
    #                     photo_folder = ask_photo_folder(profile_name)

    #                 run_tebor_py(profile_id, actual_port, profile_name, photo_folder)
    #             else:
    #                 print("   ⚠️  Не удалось запустить")


def show_variations(client, variation_type, title):
    """Показывает список вариантов"""
    print(f"\n{title}")
    print("-" * 60)

    params = {}
    if variation_type == "renderer":
        params = {"os": "windows", "version": "latest"}
        variations = api_retry(client.get_variations, variation_type, **params)
    else:
        variations = api_retry(client.get_variations, variation_type)

    if not variations:
        print("❌ Не удалось получить список")
        return

    print(f"✅ Найдено: {len(variations)}\n")

    for i, var in enumerate(variations[:30], 1):
        print(f"  {i:3}. {var}")

    if len(variations) > 30:
        print(f"\n  ... и ещё {len(variations) - 30}")


def show_running_profiles(client, active_profiles: Dict[str, dict]):
    """Показывает запущенные профили из active_profiles."""
    print("\n🟢 Запущенные профили")
    print("-" * 60)

    if not active_profiles:
        print("⚠️  Нет запущенных профилей")
        print("   Используйте пункт 12 для запуска профилей")
        return

    print(f"📊 Найдено запущенных: {len(active_profiles)}\n")
    for i, (profile_id, data) in enumerate(active_profiles.items(), 1):
        name = data.get("name", "N/A")
        port = data.get("port", "N/A")
        print(f"{i}. {name}")
        print(f"   ID: {profile_id}")
        print(f"   Порт: {port}")
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
        print("❌ Профиль не найден")
        return None

    port = ProfileCreator.extract_debug_port(profile)
    if not port:
        port = ProfileCreator.generate_cdp_port()
        print(f"🔌 Генерируем CDP порт: {port}")

    result = client.start_profile(FOLDER_ID, profile_id, port=port)
    if result:
        actual_port = result.get("port") or port
        profile_name = profile.get("profile_name", "N/A")
        print("✅ Профиль запущен")
        if actual_port:
            print(f"🔗 CDP URL: http://127.0.0.1:{actual_port}")
            return profile_id, actual_port, profile_name
    else:
        print("❌ Не удалось запустить профиль")
    return None


def stop_profile(client, active_profiles: Dict[str, dict]):
    """Останавливает профиль."""
    profile_id = ask_profile_id()
    if not profile_id:
        print("❌ ID профиля не указан")
        return

    result = client.stop_profile(FOLDER_ID, profile_id)
    if result:
        print("✅ Профиль остановлен")
        # Удаляем из active_profiles если есть
        if profile_id in active_profiles:
            del active_profiles[profile_id]
            print("   Удален из списка активных")
    else:
        print("❌ Не удалось остановить профиль")


def parse_selection(text: str, max_index: int) -> Optional[list]:
    """Разбор пользовательского ввода '1,3-5,7' в список 0-based индексов."""
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
                start = int(start_str)
                end = int(end_str)
            except ValueError:
                print(f"❌ Неверный диапазон: {part}")
                return None
            # Ограничиваем диапазон
            if start < 1:
                start = 1
            if end > max_index:
                end = max_index
                print(f"⚠️  Диапазон скорректирован до {max_index}")
            if start > end:
                print(f"❌ Некорректный диапазон: {start}-{end}")
                return None
            selected.extend(list(range(start - 1, end)))
        else:
            try:
                idx = int(part)
            except ValueError:
                print(f"❌ Неверный номер: {part}")
                return None
            if idx < 1:
                idx = 1
            if idx > max_index:
                print(f"⚠️  Номер {idx} скорректирован до {max_index}")
                idx = max_index
            selected.append(idx - 1)
    return sorted(set(selected))


def launch_selected_profiles(
    client,
    selection_text: str,
    active_map: Dict[str, dict],
    common_photo_folder: str = None,
) -> bool:
    """Запускает несколько профилей из группы по номерам и сразу открывает tebor."""
    profiles_data = api_retry(client.get_profiles, FOLDER_ID)
    if not profiles_data:
        print("❌ Не удалось получить профили")
        return False
    profiles = profiles_data.get("items", [])
    if not profiles:
        print("⚠️  В группе нет профилей")
        return False

    indices = parse_selection(selection_text, len(profiles))
    if indices is None:
        return False

    # Если папка не общая, спросим для каждого
    use_individual_folders = common_photo_folder is None

    launched_any = False
    for idx in indices:
        profile = profiles[idx]
        profile_id = profile.get("id")
        name = profile.get("profile_name", "N/A")
        if profile_id in active_map:
            print(
                f"\n⚠️  Профиль {idx + 1}. {name} ({profile_id}) уже запущен на порту {active_map[profile_id]['port']}"
            )
            continue

        cdp_port = ProfileCreator.generate_cdp_port()
        print(f"\n[{idx + 1}/{len(profiles)}] Запуск профиля {name}")
        print(f"   ID: {profile_id}")
        print(f"   Порт: {cdp_port}")

        start_result = client.start_profile(FOLDER_ID, profile_id, port=cdp_port)
        if start_result:
            actual_port = start_result.get("port") or cdp_port
            active_map[profile_id] = {"port": actual_port, "name": name}
            print(f"   ✅ Запущен | CDP: http://127.0.0.1:{actual_port}")

            # Папка для этого профиля
            photo_folder = common_photo_folder
            if use_individual_folders:
                photo_folder = ask_photo_folder(name)

            run_tebor_py(profile_id, actual_port, name, photo_folder)
            launched_any = True
        else:
            print("   ❌ Не удалось запустить")
    return launched_any


def run_tebor_for_selected(selection_text: str, active_map: Dict[str, dict]) -> bool:
    """Запускает tebor для уже запущенных профилей по номерам."""
    if not active_map:
        print("⚠️  Нет запущенных через эту сессию профилей")
        return False

    profiles = list(active_map.items())
    numbered = "\n".join(
        f"  {i}. {p[1]['name']} (порт {p[1]['port']}) — {p[0]}"
        for i, p in enumerate(profiles)
    )
    print("\n🟢 Запущенные в этой сессии:")
    print(numbered)
    print(f"Всего: {len(profiles)}")

    indices = parse_selection(selection_text, len(profiles))
    if indices is None:
        return False

    # Спрашиваем про папки
    print("\n📁 Настройка папок с фотографиями:")
    print("   1. Одна папка для всех выбранных профилей")
    print("   2. Разные папки (будет запрошено для каждого)")
    folder_choice = input("👉 Выберите (1/2): ").strip()

    common_photo_folder = None
    if folder_choice == "1":
        common_photo_folder = ask_photo_folder()
    elif folder_choice != "2":
        print("⚠️  Неверный выбор, будет запрошено для каждого профиля отдельно")

    launched_any = False
    for idx in indices:
        pid, data = profiles[idx]
        port = data["port"]
        name = data["name"]
        print(f'\n🚀 Запускаем tebor для профиля "{name}" ({pid}) на порту {port}')

        photo_folder = common_photo_folder
        if folder_choice == "2":
            photo_folder = ask_photo_folder(name)

        run_tebor_py(pid, port, name, photo_folder)
        launched_any = True
    return launched_any


def menu_launch_multiple_profiles(client, active_map: Dict[str, dict]):
    """Меню запуска нескольких профилей из текущей группы (с номерами)."""
    while True:
        print_separator()
        print("📂 Профили в рабочей группе")
        print("-" * 60)

        profiles_data = api_retry(client.get_profiles, FOLDER_ID)
        if not profiles_data:
            print("❌ Не удалось получить профили")
            return
        profiles = profiles_data.get("items", [])
        total = profiles_data.get("total", 0)
        print(f"📊 Всего: {total}\n")
        for i, profile in enumerate(profiles, 1):
            name = profile.get("profile_name", "N/A")
            status = "🟢" if profile.get("running") else "⚫"
            print(f"{i}. {status} {name}")

        print()
        print("Введите номера через запятую или диапазон (1-5, 7, 9-12)")
        print("0 — назад")
        sel = input("👉 Номера: ").strip()
        if sel == "0":
            return

        # Спрашиваем про папки
        print("\n📁 Настройка папок с фотографиями:")
        print("   1. Одна папка для всех выбранных профилей")
        print("   2. Разные папки (будет запрошено для каждого)")
        folder_choice = input("👉 Выберите (1/2): ").strip()

        common_photo_folder = None
        if folder_choice == "1":
            common_photo_folder = ask_photo_folder()
        elif folder_choice != "2":
            print("⚠️  Неверный выбор, будет запрошено для каждого профиля отдельно")

        if launch_selected_profiles(client, sel, active_map, common_photo_folder):
            print("✅ Команда запуска выполнена")


def menu_run_tebor_multiple(active_map: Dict[str, dict]):
    """Меню запуска tebor для нескольких уже запущенных профилей."""
    if not active_map:
        print("⚠️  Нет запущенных через эту сессию профилей")
        input("Enter для возврата...")
        return
    while True:
        print_separator()
        print("🚀 Запуск tebor для запущенных профилей")

        profiles = list(active_map.items())
        for i, (pid, data) in enumerate(profiles, 1):
            print(f"{i}. {data['name']} (порт {data['port']}) — {pid}")

        print()
        print("Введите номера через запятую или диапазон")
        print("0 — назад")
        sel = input("👉 Номера: ").strip()
        if sel == "0":
            return
        if run_tebor_for_selected(sel, active_map):
            print("✅ tebor запущен(а)")


def menu_stop_multiple(client, active_profiles: Dict[str, dict]):
    """Меню остановки нескольких профилей из active_profiles."""
    while True:
        print_separator()
        print("⛔ Остановка нескольких профилей")
        print("-" * 60)

        if not active_profiles:
            print("⚠️  Нет запущенных профилей")
            print("   Используйте пункт 12 для запуска профилей")
            input("\nНажмите Enter для возврата...")
            return

        profiles_list = list(active_profiles.items())
        print(f"📊 Запущено профилей: {len(profiles_list)}\n")
        for i, (profile_id, data) in enumerate(profiles_list, 1):
            name = data.get("name", "N/A")
            port = data.get("port", "N/A")
            print(f"{i}. 🟢 {name} (порт: {port})")

        print()
        print("Введите номера через запятую или диапазон (1-5, 7, 9-12)")
        print("0 — назад")
        sel = input("👉 Номера: ").strip()

        if sel == "0":
            return

        indices = parse_selection(sel, len(profiles_list))
        if indices is None:
            continue

        stopped_count = 0
        for idx in indices:
            if idx >= len(profiles_list):
                print(f"⚠️  Номер {idx + 1} вне диапазона")
                continue

            profile_id, data = profiles_list[idx]
            name = data.get("name", "N/A")
            port = data.get("port", "N/A")

            print(f"\n⛔ Останавливаем {name} ({profile_id})...")

            result = client.stop_profile(FOLDER_ID, profile_id)
            if result is not None:
                print("   ✅ Остановлен")
                del active_profiles[profile_id]  # Удаляем из списка
                stopped_count += 1
            else:
                print("   ❌ Не удалось остановить")

        if stopped_count > 0:
            print(f"\n✅ Успешно остановлено профилей: {stopped_count}")
        else:
            print("\n❌ Не удалось остановить ни одного профиля")

        input("\nНажмите Enter для продолжения...")


# def stop_profile_by_id(client, profile_id: str) -> bool:
#     """
#     Останавливает профиль по его ID через API Browser.vision.
#     URL: GET /stop/{folderId}/{profileId}
#     """
#     try:
#         # Формируем URL для остановки
#         url = f"/stop/{FOLDER_ID}/{profile_id}"
#         response = client._make_request("GET", url)

#         if response is not None:
#             print(f"   ✅ Профиль {profile_id} остановлен")
#             return True
#         else:
#             print(f"   ❌ Не удалось остановить профиль {profile_id}")
#             return False
#     except Exception as e:
#         print(f"   ❌ Ошибка при остановке профиля {profile_id}: {e}")
#         return False


def main():
    """Основная функция"""
    print("\n🌐 Browser Vision API Client")
    print(f"📂 Рабочая группа: {FOLDER_ID}")
    print("=" * 60)

    client = BrowserVisionClient(debug=False)

    print("\n🔌 Проверка соединения...")
    if not client.test_connection():
        print("❌ Не удалось подключиться к API")
        print("Проверьте:")
        print("  1. Корректность TOKEN в config.py")
        print("  2. Доступность API сервера")
        print("  3. Интернет-соединение")
        return

    print("✅ Соединение установлено")

    fg = FingerprintGenerator(client)

    print("\n📥 Загрузка базового fingerprint...")
    try:
        fg.load_base_fingerprint()
        print("✅ Базовый fingerprint загружен")
    except Exception as e:
        print(f"❌ Ошибка загрузки fingerprint: {e}")
        return

    creator = ProfileCreator(client, fg)
    active_profiles: Dict[str, dict] = {}

    while True:
        print_separator()
        print("📋 Главное меню:")
        print("-" * 60)
        print("  📊 ПРОСМОТР:")
        print("    1. Профили в рабочей группе")
        print("    2. Все группы (обзор)")
        print()
        print("  ➕ СОЗДАНИЕ:")
        print("    3. Создать один профиль")
        print("    4. Создать несколько профилей")
        print()
        print("  🔍 СПИСКИ ИЗ API:")
        print("    5. Доступные видеокарты (GPU)")
        print("    6. Доступные языки")
        print("    7. Доступные часовые пояса")
        print()
        print("  🟢 ЗАПУСК SELENIUM/CDP:")
        print("    9. Запущенные профили")
        print("    10. Запустить профиль с сохранённым портом")
        print("    11. Остановить профиль")
        print("    12. Запустить несколько профилей")
        print("    13. Запустить tebor для нескольких профилей")
        print("    14. Остановить несколько профилей")
        print()
        print("  ⚙️  ДРУГОЕ:")
        print("    8. Проверить соединение")
        print("    0. Выход")
        print("-" * 60)

        choice = input("\n👉 Выберите действие: ").strip()

        try:
            if choice == "1":
                show_current_folder_profiles(client)

            elif choice == "2":
                folders = api_retry(client.get_folders)
                if folders:
                    print(f"\n📁 Всего групп: {len(folders)}")
                    for folder in folders:
                        count = api_retry(client.get_profile_count, folder["id"])
                        marker = "✅" if folder["id"] == FOLDER_ID else "  "
                        print(f"{marker} {folder['folder_name']} ({count} профилей)")
                else:
                    print("❌ Не удалось получить группы")

            elif choice == "3":
                create_single_profile(client, fg, creator)

            elif choice == "4":
                create_batch_profiles(client, fg, creator)

            elif choice == "5":
                show_variations(client, "renderer", "💾 Доступные видеокарты")

            elif choice == "6":
                show_variations(client, "language", "🌐 Доступные языки")

            elif choice == "7":
                show_variations(client, "timezone", "🕐 Доступные часовые пояса")

            elif choice == "8":
                print("\n🔌 Проверка соединения...")
                if client.test_connection():
                    print("✅ Соединение работает!")
                else:
                    print("❌ Соединение не установлено")

            elif choice == "9":
                show_running_profiles(client, active_profiles)

            elif choice == "10":
                result = start_profile_with_stored_port(client)
                if result:
                    profile_id, port, name = result
                    active_profiles[profile_id] = {"port": port, "name": name}
                    print("▶️  Вы можете запустить tebor отдельно: main.py → пункт 13")

            elif choice == "11":
                stop_profile(client, active_profiles)

            elif choice == "12":
                menu_launch_multiple_profiles(client, active_profiles)

            elif choice == "13":
                menu_run_tebor_multiple(active_profiles)

            elif choice == "14":
                menu_stop_multiple(client, active_profiles)

            elif choice == "0":
                print("\n👋 До свидания!")
                break

            else:
                print("❌ Неверный выбор")

        except KeyboardInterrupt:
            print("\n\n⚠️  Операция прервана")
            continue
        except Exception as e:
            print(f"\n❌ Ошибка: {type(e).__name__}: {e}")
            import traceback

            traceback.print_exc()
            continue


if __name__ == "__main__":
    main()
