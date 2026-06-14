"""
Последовательная выдача имён профилей и прокси из файлов config/.
"""

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional

CONFIG_DIR = Path(__file__).resolve().parent / "config"
STATE_PATH = CONFIG_DIR / "_state.json"
PERS_ID_PATH = CONFIG_DIR / "pers_id.txt"
TOWN_PATH = CONFIG_DIR / "town.txt"
PROXY_PATH = CONFIG_DIR / "proxy.txt"


@dataclass(frozen=True)
class ProxyConfig:
    """Данные прокси из строки host:port[:username:password]."""

    host: str
    port: int
    username: Optional[str] = None
    password: Optional[str] = None
    raw: str = ""

    @property
    def display(self) -> str:
        return f"{self.host}:{self.port}"

    @property
    def has_auth(self) -> bool:
        return bool(self.username and self.password)

    @property
    def auth_display(self) -> str:
        if not self.has_auth:
            return self.display
        return f"{self.username}:***@{self.display}"

    def to_api_payload(self, name: str, proxy_type: str) -> Dict[str, Any]:
        payload: Dict[str, Any] = {
            "proxy_name": name,
            "proxy_type": proxy_type,
            "proxy_ip": self.host,
            "proxy_port": self.port,
        }
        if self.username:
            payload["proxy_username"] = self.username
        if self.password:
            payload["proxy_password"] = self.password
        return payload


class SequentialConfig:
    """Управляет последовательными индексами в config/_state.json."""

    def __init__(
        self,
        state_path: Path = STATE_PATH,
        pers_id_path: Path = PERS_ID_PATH,
        town_path: Path = TOWN_PATH,
        proxy_path: Path = PROXY_PATH,
    ):
        self.state_path = state_path
        self.pers_id_path = pers_id_path
        self.town_path = town_path
        self.proxy_path = proxy_path

    def next_profile_name(self) -> str:
        state = self._load_state()
        pers_ids = self._read_non_empty_lines(self.pers_id_path)
        towns = self._read_non_empty_lines(self.town_path)

        pers_index = self._get_index(state, "prof_id_current")
        town_index = self._get_index(
            state, "town_current", fallback_key="tower_current"
        )

        if pers_index >= len(pers_ids):
            state["prof_id_current"] = 0
            pers_index = self._get_index(state, "prof_id_current")

        if town_index >= len(towns):
            state["town_current"] = 0
            town_index = self._get_index(
                state, "town_current", fallback_key="tower_current"
            )

        pers_id = self._normalize_pers_id(pers_ids[pers_index])
        town = towns[town_index]

        state["prof_id_current"] = pers_index + 1
        state["town_current"] = town_index + 1
        # Оставляем старый ключ для совместимости с существующим _state.json.
        state["tower_current"] = town_index + 1
        self._save_state(state)

        return f"{pers_id}-{town}"

    def next_proxy(self) -> ProxyConfig:
        state = self._load_state()
        proxies = self._read_non_empty_lines(self.proxy_path)
        proxy_index = self._get_index(state, "proxy_current")

        if proxy_index >= len(proxies):
            raise ValueError("Закончились значения в config/proxy.txt")

        state["proxy_current"] = proxy_index + 1
        self._save_state(state)

        return self._parse_proxy(proxies[proxy_index])

    def rollback_profile_name(self) -> None:
        """Возвращает индексы имени на один шаг, если профиль не был создан."""
        state = self._load_state()
        pers_index = max(0, self._get_index(state, "prof_id_current") - 1)
        town_index = max(
            0, self._get_index(state, "town_current", fallback_key="tower_current") - 1
        )
        state["prof_id_current"] = pers_index
        state["town_current"] = town_index
        state["tower_current"] = town_index
        self._save_state(state)

    def _load_state(self) -> Dict[str, Any]:
        if not self.state_path.exists():
            return {}
        with self.state_path.open("r", encoding="utf-8") as state_file:
            return json.load(state_file)

    def _save_state(self, state: Dict[str, Any]) -> None:
        self.state_path.parent.mkdir(parents=True, exist_ok=True)
        with self.state_path.open("w", encoding="utf-8") as state_file:
            json.dump(state, state_file, ensure_ascii=False, indent=2)
            state_file.write("\n")

    @staticmethod
    def _read_non_empty_lines(path: Path) -> List[str]:
        with path.open("r", encoding="utf-8") as source_file:
            return [line.strip() for line in source_file if line.strip()]

    @staticmethod
    def _get_index(
        state: Dict[str, Any], key: str, fallback_key: Optional[str] = None
    ) -> int:
        value = state.get(key)
        if value is None and fallback_key:
            value = state.get(fallback_key)
        if value is None:
            return 0
        try:
            return int(value)
        except (TypeError, ValueError):
            return 0

    @staticmethod
    def _normalize_pers_id(raw_pers_id: str) -> str:
        parts = raw_pers_id.split()
        if len(parts) == 2 and parts[0].lower() == "id":
            return parts[1]
        return raw_pers_id

    @staticmethod
    def _parse_proxy(raw_proxy: str) -> ProxyConfig:
        # В config/proxy.txt может лежать полный прокси:
        # pool.proxys.io:10842:user331393o5596r781204:6t9ija
        # Для Browser Vision логин и пароль нужно передавать отдельными полями
        # proxy_username/proxy_password, а не склеенной строкой.
        parts = raw_proxy.split(":")
        if len(parts) not in (2, 4):
            raise ValueError(
                "Прокси должен быть в формате host:port или host:port:login:password"
            )
        try:
            port = int(parts[1])
        except ValueError as exc:
            raise ValueError(f"Некорректный порт прокси: {raw_proxy}") from exc

        username = parts[2] if len(parts) == 4 else None
        password = parts[3] if len(parts) == 4 else None
        return ProxyConfig(parts[0], port, username, password, raw_proxy)
