"""
Конфигурация для Browser Vision API
"""

# Ваши учетные данные
TOKEN = "eyJ0eXAiOiJKV1QiLCJhbGciOiJIUzI1NiJ9.eyJ1c2VyX2lkIjoiM2IzMzY1OWItYmQxOC00MDQxLTk4NTktMTExODVhYzRmZWE4IiwidXNlcm5hbWUiOiJzdmV0YWVnb3JvdmF3dzFAZ21haWwuY29tIiwiaWF0IjoxNzgwOTkzMjIwLCJleHAiOjE4MTI1MjkyMjB9.PSaCcKgzOmef9X_HoEoCAy_wTqodv86azPeU0mSk-7g"  # Замените на ваш токен

# ✅ ФИКСИРОВАННАЯ ГРУППА
FOLDER_ID = "30289184-2163-4265-9b00-5d74f1a8c2af"

# URL API
API_BASE_URL = "https://api.browser.vision/api/v1"
LOCAL_URL = "http://127.0.0.1:3030"

# ✅ ИСПРАВЛЕНО: с заглавной буквы!
DEFAULT_PLATFORM = "Windows"
DEFAULT_BROWSER = "Chrome"
DEFAULT_VERSION = "latest"
DEFAULT_PROXY_TYPE = "SOCKS5"

# Настройки экрана
DEFAULT_SCREEN = {
    "width": 1920,
    "height": 1080,
    "pixel_ratio": 1,
    "avail_width": 1920,
    "avail_height": 1080,
    "avail_top": 0,
    "avail_left": 0,
    "color_depth": 24,
    "pixel_depth": 24,
}

# Заблокированные порты по умолчанию
DEFAULT_PORTS = [3389, 5900, 5901, 5800, 7070, 6568, 5938, 1080, 8080, 3128, 3030]

# ✅ ИСПРАВЛЕНО: правильные значения режимов!
MODES = {
    "OFF": "off",  # Выключено
    "AUTO": "auto",  # Автоматически
    "MANUAL": "manual",  # Вручную (шум настраивается через audio_pref, client_rects и т.д.)
}
