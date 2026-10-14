"""
Вспомогательные функции для работы с прокси Browser Vision API.

Очередь прокси управляется единственным источником истины —
SequentialConfig (config_sequence.py), индекс хранится в config/_state.json.
"""

from config import DEFAULT_PROXY_TYPE, FOLDER_ID
from config_sequence import SequentialConfig


def next_proxy():
    """Возвращает следующий прокси из очереди (индекс в config/_state.json)."""
    return SequentialConfig().next_proxy()


def get_proxies_id():
    """Создаёт прокси через API и возвращает его id, продвигая очередь."""
    from api_client import BrowserVisionClient

    proxy_config = next_proxy()

    client = BrowserVisionClient()
    result = client.create_proxy(
        FOLDER_ID,
        proxy_config.to_api_payload(name="Proxy", proxy_type=DEFAULT_PROXY_TYPE),
    )

    if not result:
        raise RuntimeError("Не удалось создать прокси через API")

    data = result.get("data")
    if isinstance(data, list) and data:
        first = data[0]
        if isinstance(first, dict) and first.get("id"):
            return first["id"]
    elif isinstance(data, dict) and data.get("id"):
        return data["id"]

    message = result.get("message") or result.get("error") or "id прокси не найден"
    raise RuntimeError(f"Не удалось получить id прокси: {message}")


if __name__ == "__main__":
    get_proxies_id()
