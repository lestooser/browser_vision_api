from api_client import BrowserVisionClient
from config import FOLDER_ID

client = BrowserVisionClient()

if not FOLDER_ID:
    raise RuntimeError("Set FOLDER_ID in .env before running this script.")

profiles = client.get_profile_list(FOLDER_ID)
count = client.get_profile_count(FOLDER_ID)
print(f"Всего профилей: {count}")

profile_id = input("ID профиля для поиска (Enter — пропустить): ").strip()
if profile_id:
    profile = client.get_profile_by_id(FOLDER_ID, profile_id)
    if profile is None:
        raise RuntimeError("Профиль не найден или запрос к API завершился ошибкой.")
    print(profile)
