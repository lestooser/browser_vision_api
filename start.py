from api_client import BrowserVisionClient

client = BrowserVisionClient()

# Получить все профили из папки
profiles = client.get_profile_list("30289184-2163-4265-9b00-5d74f1a8c2af")

# Получить количество профилей
count = client.get_profile_count("30289184-2163-4265-9b00-5d74f1a8c2af")
print(f"Всего профилей: {count}")

# Найти конкретный профиль
profile = client.get_profile_by_id(
    "30289184-2163-4265-9b00-5d74f1a8c2af", "1c83e9c5-b27b-495c-b26e-cecd41040a31"
)
