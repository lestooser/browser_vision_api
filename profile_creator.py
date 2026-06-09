"""
Модуль для создания профилей
"""

from typing import Any, Dict, List, Optional

from config import DEFAULT_BROWSER, FOLDER_ID


class ProfileCreator:
    """Создаёт профили с заданными настройками"""

    def __init__(self, client, fingerprint_generator):
        self.client = client
        self.fg = fingerprint_generator
        self.folder_id = FOLDER_ID

    def create(
        self,
        name: str,
        fingerprint: Dict[str, Any],
        notes: str = "",
        tags: List[str] = None,
        proxy_id: Optional[str] = None,
        browser: str = DEFAULT_BROWSER,
        platform: str = "Windows",
    ) -> Optional[Dict]:
        """Создаёт новый профиль"""
        profile_data = {
            "profile_name": name,
            "profile_notes": notes,
            "profile_tags": tags or [],
            "proxy_id": proxy_id,
            "profile_status": None,
            "browser": browser,
            "platform": platform,
            "fingerprint": fingerprint,
        }

        result = self.client.create_profile(self.folder_id, profile_data)

        if result:
            print(f"✅ Профиль '{name}' создан успешно!")
            if "data" in result and "id" in result["data"]:
                print(f"📝 ID профиля: {result['data']['id']}")
            return result
        else:
            print(f"❌ Не удалось создать профиль '{name}'")
            return None

    def create_batch(
        self, count: int, name_prefix: str = "Profile", **fingerprint_kwargs
    ) -> List[Optional[Dict]]:
        """Создаёт несколько профилей"""
        results = []

        print(f"\n🚀 Создание {count} профилей...")
        print("=" * 50)

        for i in range(1, count + 1):
            name = f"{name_prefix} #{i}"
            fingerprint = self.fg.generate(**fingerprint_kwargs)
            result = self.create(
                name, fingerprint, notes=f"Auto-generated profile #{i}"
            )
            results.append(result)
            print(f"Progress: {i}/{count} ({i / count * 100:.1f}%)\n")

        successful = sum(1 for r in results if r is not None)
        print(f"\n✅ Создано {successful} из {count} профилей")

        return results

    def list_profiles(self, folder_id: Optional[str] = None) -> Optional[List[Dict]]:
        """
        Выводит список профилей в папке

        Args:
            folder_id: ID папки (если None, используется self.folder_id)

        Returns:
            Список профилей или None
        """
        if folder_id is None:
            folder_id = self.folder_id

        profiles_data = self.client.get_profiles(folder_id)

        if not profiles_data:
            print("❌ Не удалось получить список профилей")
            return None

        total = profiles_data.get("total", 0)
        profiles = profiles_data.get("items", [])

        print(f"\n📂 Профили в папке (всего: {total})")
        print("=" * 60)

        if not profiles:
            print("⚠️  В папке нет профилей")
            return []

        for i, profile in enumerate(profiles, 1):
            print(f"\n{i}. {profile.get('profile_name', 'N/A')}")
            print(f"   ID: {profile.get('id', 'N/A')}")
            print(f"   Browser: {profile.get('browser', 'N/A')}")
            print(f"   Platform: {profile.get('platform', 'N/A')}")
            print(f"   Running: {'✅' if profile.get('running') else '❌'}")
            print(f"   Worktime: {profile.get('worktime', 0)} сек")

            # Информация о прокси
            proxy = profile.get("proxy")
            if proxy:
                print(f"   Proxy: {proxy.get('proxy_name', 'N/A')}")
                print(f"   Proxy IP: {proxy.get('proxy_ip')}:{proxy.get('proxy_port')}")
                geo = proxy.get("geo_info", {})
                if geo:
                    print(
                        f"   Geo: {geo.get('city', 'N/A')}, {geo.get('country', 'N/A')}"
                    )

            print(f"   Created: {profile.get('created_at', 'N/A')}")

        print("\n" + "=" * 60)

        return profiles
