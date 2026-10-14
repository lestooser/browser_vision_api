# check_all_folders.py
from api_client import BrowserVisionClient


def main():
    client = BrowserVisionClient()

    # Получаем все группы
    folders = client.get_folders()

    if not folders:
        print("❌ Не удалось получить список групп")
        return

    print(f"📁 Найдено групп: {len(folders)}\n")

    for folder in folders:
        folder_id = folder["id"]
        folder_name = folder["folder_name"]

        print(f"\n{'=' * 60}")
        print(f"📂 Группа: {folder_name}")
        print(f"   ID: {folder_id}")
        print(f"{'=' * 60}")

        # Получаем профили
        profiles_data = client.get_profiles(folder_id)

        if not profiles_data:
            print("❌ Не удалось получить профили")
            continue

        total = profiles_data.get("total", 0)
        profiles = profiles_data.get("items", [])

        print(f"📊 Всего профилей: {total}\n")

        if profiles:
            for i, profile in enumerate(profiles, 1):
                print(f"{i}. {profile.get('profile_name', 'N/A')}")
                print(f"   ID: {profile.get('id')}")

                proxy = profile.get("proxy")
                if proxy:
                    geo = proxy.get("geo_info", {})
                    print(
                        f"   Proxy: {proxy.get('proxy_ip')}:{proxy.get('proxy_port')}"
                    )
                    print(
                        f"   Geo: {geo.get('city', 'N/A')}, {geo.get('country', 'N/A')}"
                    )
                print()
        else:
            print("⚠️  В папке нет профилей")


if __name__ == "__main__":
    main()
