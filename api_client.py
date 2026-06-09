"""
Клиент для работы с Browser Vision API
"""

import json
from typing import Any, Dict, List, Optional

import requests

from config import API_BASE_URL, LOCAL_URL, TOKEN


class BrowserVisionClient:
    """Клиент для взаимодействия с API Browser Vision"""

    def __init__(self, token: str = TOKEN, debug: bool = False):
        self.token = token
        self.api_url = API_BASE_URL
        self.local_url = LOCAL_URL
        self.debug = debug
        self.headers = {"X-Token": token, "Content-Type": "application/json"}
        self.session = requests.Session()
        # Не используем proxy-переменные окружения для запросов к Browser Vision API:
        # без requests[socks] SOCKS-прокси из окружения приводят к ошибке
        # "Missing dependencies for SOCKS support". Прокси из config/proxy.txt
        # передаются в Browser Vision как данные создаваемого профиля, а не как
        # транспортный прокси для самого API-клиента.
        self.session.trust_env = False
        self.session.headers.update(self.headers)

    def _request(self, method: str, url: str, **kwargs) -> Optional[Dict[str, Any]]:
        """Выполняет HTTP запрос с детальным логированием"""
        try:
            # Логируем запрос
            if self.debug:
                print(f"\n🔍 DEBUG: {method} {url}")
                if "json" in kwargs:
                    print("📤 Request Body:")
                    print(json.dumps(kwargs["json"], indent=2, ensure_ascii=False))

            response = self.session.request(method, url, timeout=30, **kwargs)

            # Логируем ответ
            if self.debug:
                print(f"📊 Response Status: {response.status_code}")
                print("📥 Response Body:")
                try:
                    print(json.dumps(response.json(), indent=2, ensure_ascii=False))
                except:
                    print(response.text[:500])

            response.raise_for_status()
            return response.json()

        except requests.exceptions.HTTPError as e:
            print(f"\n❌ HTTP Ошибка: {e}")
            print("📄 Ответ сервера:")
            try:
                error_data = e.response.json()
                print(json.dumps(error_data, indent=2, ensure_ascii=False))
            except:
                print(e.response.text[:500])
            return None

        except requests.exceptions.RequestException as e:
            print(f"❌ Ошибка запроса: {e}")
            return None

    def get_fingerprint(
        self, platform: str = "windows", version: str = "latest"
    ) -> Optional[Dict]:
        """Получает базовый fingerprint"""
        url = f"{self.api_url}/fingerprints/{platform}/{version}"
        result = self._request("GET", url)
        if result and "data" in result:
            return result["data"].get("fingerprint", {})
        return None

    def get_variations(self, variation_type: str, **params) -> Optional[List[str]]:
        """Получает список вариантов"""
        # Пробуем локальный сервер
        local_url = f"{self.local_url}/variations/{variation_type}"
        if params:
            local_url += "?" + "&".join(f"{k}={v}" for k, v in params.items())

        result = self._request("GET", local_url)
        if result and isinstance(result, list):
            return result

        # Пробуем API
        api_url = f"{self.api_url}/variations/{variation_type}"
        if params:
            api_url += "?" + "&".join(f"{k}={v}" for k, v in params.items())

        result = self._request("GET", api_url)
        if result and isinstance(result, list):
            return result

        return None

    def get_gpus(
        self, platform: str = "windows", version: str = "latest"
    ) -> Optional[List[str]]:
        """Получает список доступных видеокарт"""
        return self.get_variations("renderer", os=platform, version=version)

    def get_languages(self) -> Optional[List[str]]:
        """Получает список доступных языков"""
        return self.get_variations("language")

    def get_timezones(self) -> Optional[List[str]]:
        """Получает список доступных часовых поясов"""
        return self.get_variations("timezone")

    def get_folders(self) -> Optional[List[Dict]]:
        """Получает список групп"""
        url = f"{self.api_url}/folders"
        result = self._request("GET", url)
        if result and "data" in result:
            return result["data"]
        return None

    def get_profiles(self, folder_id: str) -> Optional[Dict[str, Any]]:
        """Получает список профилей в папке"""
        url = f"{self.api_url}/folders/{folder_id}/profiles"
        result = self._request("GET", url)
        if result and "data" in result:
            return result["data"]
        return None

    def get_profile_list(self, folder_id: str) -> Optional[List[Dict]]:
        """Получает только список профилей"""
        profiles_data = self.get_profiles(folder_id)
        if profiles_data and "items" in profiles_data:
            return profiles_data["items"]
        return None

    def get_profile_count(self, folder_id: str) -> int:
        """Получает количество профилей в папке"""
        profiles_data = self.get_profiles(folder_id)
        if profiles_data and "total" in profiles_data:
            return profiles_data["total"]
        return 0

    def get_profile_by_id(self, folder_id: str, profile_id: str) -> Optional[Dict]:
        """Получает информацию о конкретном профиле"""
        profiles = self.get_profile_list(folder_id)
        if profiles:
            for profile in profiles:
                if profile.get("id") == profile_id:
                    return profile
        return None

    def create_profile(self, folder_id: str, profile_data: Dict) -> Optional[Dict]:
        """Создаёт новый профиль"""
        url = f"{self.api_url}/folders/{folder_id}/profiles"
        return self._request("POST", url, json=profile_data)

    def update_profile(
        self, folder_id: str, profile_id: str, profile_data: Dict
    ) -> Optional[Dict]:
        """Обновляет существующий профиль"""
        url = f"{self.api_url}/folders/{folder_id}/profiles/{profile_id}"
        return self._request("PATCH", url, json=profile_data)

    def create_proxy(self, folder_id: str, proxy_data: Dict) -> Optional[Dict]:
        """Создаёт прокси в папке"""
        url = f"{self.api_url}/folders/{folder_id}/proxies"
        return self._request("POST", url, json={"proxies": [proxy_data]})

    def test_connection(self) -> bool:
        """Проверяет соединение с API"""
        try:
            fingerprint = self.get_fingerprint()
            return fingerprint is not None
        except:
            return False
