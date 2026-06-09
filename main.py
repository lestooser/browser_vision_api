"""
Основной скрипт для работы с Browser Vision API
"""

from api_client import BrowserVisionClient
from config import FOLDER_ID, MODES
from fingerprint_generator import FingerprintGenerator
from profile_creator import ProfileCreator


def print_separator():
    """Выводит разделитель"""
    print("\n" + "=" * 60 + "\n")


def show_current_folder_profiles(client):
    """Показывает профили в текущей группе"""
    print("\n📂 Профили в группе")
    print(f"   ID группы: {FOLDER_ID}")
    print("-" * 60)

    profiles_data = client.get_profiles(FOLDER_ID)

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

    name = input("Имя профиля (Enter для авто): ").strip()
    if not name:
        gpu = fg.get_random_gpu()
        gpu_model = gpu.split()[-1] if gpu else "Default"
        name = f"Profile - {gpu_model}"

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
    if confirm == "y":
        creator.create(name, fingerprint)
    else:
        print("⚠️  Создание отменено")


def create_batch_profiles(client, fg, creator):
    """Создаёт несколько профилей"""
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

    prefix = input("Префикс имени (Enter для 'Profile'): ").strip()
    if not prefix:
        prefix = "Profile"

    confirm = input(f"\nСоздать {count} профилей? (y/n): ").strip().lower()
    if confirm == "y":
        creator.create_batch(
            count=count,
            name_prefix=prefix,
            webrtc_mode=MODES["AUTO"],
            webgl_mode=MODES["MANUAL"],
            canvas_mode=MODES["MANUAL"],
            audio_mode=MODES["MANUAL"],
            client_rects_mode=MODES["MANUAL"],
            random_gpu=True,
            random_webcam=True,
        )
    else:
        print("⚠️  Создание отменено")


def show_variations(client, variation_type, title):
    """Показывает список вариантов"""
    print(f"\n{title}")
    print("-" * 60)

    params = {}
    if variation_type == "renderer":
        params = {"os": "windows", "version": "latest"}
        variations = client.get_variations("renderer", **params)
    else:
        variations = client.get_variations(variation_type)

    if not variations:
        print("❌ Не удалось получить список")
        return

    print(f"✅ Найдено: {len(variations)}\n")

    for i, var in enumerate(variations[:30], 1):
        print(f"  {i:3}. {var}")

    if len(variations) > 30:
        print(f"\n  ... и ещё {len(variations) - 30}")


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
        print("  ⚙️  ДРУГОЕ:")
        print("    8. Проверить соединение")
        print("    0. Выход")
        print("-" * 60)

        choice = input("\n👉 Выберите действие: ").strip()

        try:
            if choice == "1":
                show_current_folder_profiles(client)

            elif choice == "2":
                folders = client.get_folders()
                if folders:
                    print(f"\n📁 Всего групп: {len(folders)}")
                    for folder in folders:
                        count = client.get_profile_count(folder["id"])
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
