from config import FOLDER_ID, TOKEN
from config_sequence import CONFIG_DIR, ProxyConfig

url = f"https://api.browser.vision/api/v1/folders/{FOLDER_ID}/proxies"

PROXY_PATH = CONFIG_DIR / "proxy.txt"
STATE_PATH = CONFIG_DIR / "_state.json"


def _read_non_empty_lines(PROXY_PATH=PROXY_PATH):
    with PROXY_PATH.open("r", encoding="utf-8") as source_file:
        return [line.strip() for line in source_file if line.strip()]

        # proxies = self._read_non_empty_lines(self.proxy_path)
        # proxy_index = self._get_index(state, "proxy_current")


def _get_index(STATE_PATH=STATE_PATH) -> int:
    with STATE_PATH.open("r", encoding="utf-8") as source_file:
        state = [line.strip() for line in source_file if line.strip()]  # list

    # state[0] = str
    # need to dict
    # print("🔍 Загруженное состояние:", state,
    # type(state), state[0] if state else "Пустой список")

    json_str = "".join(state)  # объединяем строки в одну
    try:
        state_dict = eval(json_str)  # преобразуем строку в словарь
        if not isinstance(state_dict, dict):
            # print("⚠️  Состояние не является словарем, начинаем с начала списка")
            return 0
    except Exception:
        # print(f"⚠️  Ошибка при загрузке состояния: {exc}, начинаем с начала списка")
        return 0

    value = state_dict.get("proxy_current")
    if value is None:
        # print("⚠️  Индекс прокси не найден в состоянии, начинаем с начала списка")
        return 0
    if value is None:
        return 0
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0


def next_proxy() -> ProxyConfig:
    # state = self._load_state()
    proxies = _read_non_empty_lines(PROXY_PATH)
    proxy_index = _get_index(STATE_PATH)

    # if proxy_index >= len(proxies):
    #     raise ValueError("Закончились значения в config/proxy.txt")

    # state["proxy_current"] = proxy_index + 1
    # self._save_state(state)

    return _parse_proxy(proxies[proxy_index])


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
        ip = parts[0]
        port = int(parts[1])
    except ValueError as exc:
        raise ValueError(f"Некорректный порт прокси: {raw_proxy}") from exc

    username = parts[2] if len(parts) == 4 else None
    password = parts[3] if len(parts) == 4 else None
    return ProxyConfig(parts[0], port, username, password, raw_proxy)


def api_proxy(proxy_config: ProxyConfig):
    import requests

    url = f"https://api.browser.vision/api/v1/folders/{FOLDER_ID}/proxies"

    body = {
        "proxies": [
            {
                "proxy_name": "Proxy",
                "proxy_type": "HTTP",
                "proxy_ip": proxy_config.host,
                "proxy_port": proxy_config.port,
                "proxy_username": proxy_config.username,
                "proxy_password": proxy_config.password,
            }
        ]
    }

    headers = {"X-Token": TOKEN, "Content-Type": "application/json"}

    response = requests.post(url, headers=headers, json=body)

    return response.json()


def get_proxies():
    import requests

    url = f"https://api.browser.vision/api/v1/folders/{FOLDER_ID}/proxies"
    headers = {"X-Token": TOKEN}

    response = requests.get(url, headers=headers)

    return response.json()


def get_proxies_id():
    proxy_config = next_proxy()
    api = api_proxy(proxy_config)
    return api["data"][0]["id"]


# import json

# #print(json.dumps(response.json()))


if __name__ == "__main__":
    # proxy_config = next_proxy()
    # #print(proxy_config)

    # test_proxy = _parse_proxy("pool.proxys.io:10842:user331393o5596r781204:6t9ija")
    # #print(test_proxy)
    # get_proxies = _read_non_empty_lines()
    # # #print(get_proxies)

    # idx = _get_index()
    # #print(idx)

    # print(next_proxy())
    # print(
    #     next_proxy()
    # )  # ProxyConfig(host='pool.proxys.io', port=10003, username='user331393o5596r683778', password='6t9ija', raw='pool.proxys.io:10003:user331393o5596r683778:6t9ija')
    get_proxies_id()
    pass
