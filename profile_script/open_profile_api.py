import os
import sys
from pathlib import Path

import requests
from dotenv import load_dotenv

sys.path.insert(0, str(Path(__file__).parent.parent))

# profileID = "3fce8bfa-d422-474f-b708-d8f99b47bbee"
folder_ID = "30289184-2163-4265-9b00-5d74f1a8c2af"
load_dotenv()


TOKEN = os.getenv("TOKEN_PROF")


# !!! ОБЯЗАТЕЛЬНО: укажите ID профиля, который хотите запустить
def openProfule(profileID, PORT_NUMBER):
    # Формируем URL согласно документации
    url = f"http://127.0.0.1:3030/start/{folder_ID}/{profileID}"
    headers = {"X-Token": TOKEN, "Content-Type": "application/json"}
    body = {"args": [f"--remote-debugging-port={PORT_NUMBER}"]}

    print(f"Запрос к: {url}")

    try:
        response = requests.post(url, headers=headers, json=body)

        # Диагностика ответа
        print(f"Статус: {response.status_code}")
        print(f"Тело ответа: {response.text}")

        # Парсим JSON только если ответ не пустой
        if response.text:
            print(response.json())
        else:
            print("Сервер вернул пустой ответ. Проверьте:")
            print("- Запущен ли Vision?")
            print("- Правильные ли folderId и profileId?")
            print("- Есть ли у бота доступ к этому профилю?")

    except requests.exceptions.ConnectionError:
        print(
            "Ошибка: Не удалось подключиться к Vision. Убедитесь, что он запущен на 127.0.0.1:3030"
        )
    except Exception as e:
        print(f"Другая ошибка: {e}")

    print(response.json())
