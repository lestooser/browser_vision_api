"""
Модуль для создания профилей
"""

from typing import Any, Dict, List, Optional

from config import DEFAULT_BROWSER, DEFAULT_PROXY_TYPE, FOLDER_ID
from config_sequence import SequentialConfig


class ProfileCreator:
    """Создаёт профили с заданными настройками"""

    from test_proxy import get_proxies_id

    def __init__(self, client, fingerprint_generator):
        self.client = client
        self.fg = fingerprint_generator
        self.folder_id = FOLDER_ID
        self.sequence = SequentialConfig()

    def create(
        self,
        name: str,
        fingerprint: Dict[str, Any],
        notes: str = "",
        tags: List[str] = None,
        proxy_id: Optional[str] = get_proxies_id(),
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

    def create_with_sequential_config(
        self,
        fingerprint: Dict[str, Any],
        notes: str = "",
        tags: List[str] = None,
        browser: str = DEFAULT_BROWSER,
        platform: str = "Windows",
    ) -> Optional[Dict]:
        """Создаёт профиль с очередным именем и обязательным рабочим прокси."""
        name = self.sequence.next_profile_name()
        print(f"\n🧾 Название профиля: {name}")

        try:
            result = self._create_profile_with_next_working_proxy(
                name=name,
                fingerprint=fingerprint,
                notes=notes,
                tags=tags,
                browser=browser,
                platform=platform,
            )
        except Exception:
            self.sequence.rollback_profile_name()
            raise

        if not result:
            self.sequence.rollback_profile_name()
        return result

    def _create_profile_with_next_working_proxy(
        self,
        name: str,
        fingerprint: Dict[str, Any],
        notes: str = "",
        tags: List[str] = None,
        browser: str = DEFAULT_BROWSER,
        platform: str = "Windows",
    ) -> Optional[Dict]:
        while True:
            proxy = self.sequence.next_proxy()
            proxy_payload = proxy.to_api_payload(
                name=f"Proxy {proxy.display}", proxy_type=DEFAULT_PROXY_TYPE
            )
            print(f"🔌 Добавление прокси: {proxy.auth_display}")

            proxy_result = self.client.create_proxy(self.folder_id, proxy_payload)
            proxy_data = self._extract_created_proxy(proxy_result)
            if not proxy_data or not proxy_data.get("id"):
                print("⚠️  Прокси не поставился, используется следующий")
                continue

            proxy_id = proxy_data["id"]
            result = self.create(
                name=name,
                fingerprint=fingerprint,
                notes=notes,
                tags=tags,
                proxy_id=proxy_id,
                browser=browser,
                platform=platform,
            )
            if not result:
                return None

            if self._profile_has_proxy(result, proxy_id):
                self._print_bound_proxy(proxy)
                return result

            profile_id = self._extract_profile_id(result)
            if not profile_id:
                print("⚠️  Не удалось проверить прокси профиля, используется следующий")
                continue

            fixed_result = self._attach_next_proxy_to_existing_profile(profile_id, name)
            if fixed_result:
                return fixed_result

    def _attach_next_proxy_to_existing_profile(
        self, profile_id: str, profile_name: str
    ) -> Optional[Dict]:
        while True:
            proxy = self.sequence.next_proxy()
            proxy_payload = proxy.to_api_payload(
                name=f"Proxy {proxy.display}", proxy_type=DEFAULT_PROXY_TYPE
            )
            print(f"🔌 Добавление следующего прокси: {proxy.auth_display}")

            proxy_result = self.client.create_proxy(self.folder_id, proxy_payload)
            proxy_data = self._extract_created_proxy(proxy_result)
            if not proxy_data or not proxy_data.get("id"):
                print("⚠️  Прокси не поставился, используется следующий")
                continue

            proxy_id = proxy_data["id"]
            update_result = self.client.update_profile(
                self.folder_id, profile_id, {"proxy_id": proxy_id}
            )
            if self._profile_has_proxy(update_result, proxy_id):
                self._print_bound_proxy(proxy, profile_name)
                return update_result

            profile = self.client.get_profile_by_id(self.folder_id, profile_id)
            if profile and profile.get("proxy_id") == proxy_id:
                self._print_bound_proxy(proxy, profile_name)
                return {"data": profile}

            print("⚠️  Прокси не привязался к профилю, используется следующий")

    @staticmethod
    def _print_bound_proxy(proxy, profile_name: Optional[str] = None) -> None:
        credentials = "с логином/паролем" if proxy.has_auth else "без логина/пароля"
        if profile_name:
            print(
                f"🔒 Прокси {credentials} привязан к профилю '{profile_name}': {proxy.display}"
            )
        else:
            print(f"🔒 Прокси {credentials} привязан к профилю: {proxy.display}")

    @staticmethod
    def _extract_created_proxy(result: Optional[Dict]) -> Optional[Dict]:
        if not result:
            return None
        data = result.get("data")
        if isinstance(data, list) and data:
            return data[0]
        if isinstance(data, dict):
            return data
        return None

    @staticmethod
    def _extract_profile_id(result: Optional[Dict]) -> Optional[str]:
        if not result:
            return None
        data = result.get("data")
        if isinstance(data, dict):
            return data.get("id")
        return None

    @staticmethod
    def _profile_has_proxy(result: Optional[Dict], proxy_id: str) -> bool:
        if not result:
            return False
        data = result.get("data")
        if not isinstance(data, dict):
            return False
        if data.get("proxy_id") == proxy_id:
            return True
        proxy = data.get("proxy")
        return isinstance(proxy, dict) and proxy.get("id") == proxy_id

    def create_batch(
        self, count: int, name_prefix: str = "Profile", **fingerprint_kwargs
    ) -> List[Optional[Dict]]:
        """Создаёт несколько профилей"""
        results = []

        print(f"\n🚀 Создание {count} профилей...")
        print("=" * 50)

        for i in range(1, count + 1):
            fingerprint = self.fg.generate(**fingerprint_kwargs)
            result = self.create_with_sequential_config(
                fingerprint, notes=f"Auto-generated profile #{i}"
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
