"""
Конфигурация для Browser Vision API
"""

import os
from pathlib import Path


def _load_env_file() -> None:
    env_path = Path(__file__).resolve().parent / ".env"
    if not env_path.exists():
        return

    with env_path.open("r", encoding="utf-8") as env_file:
        for raw_line in env_file:
            line = raw_line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, value = line.split("=", 1)
            key = key.strip()
            value = value.strip()
            if not key:
                continue
            os.environ.setdefault(key, value)


_load_env_file()

PROJECT_ROOT = Path(__file__).resolve().parent
TOKEN = os.getenv("TOKEN_PROF") or os.getenv("TOKEN") or ""
LOCAL_TOKEN = os.getenv("LOCAL_TOKEN") or TOKEN
FOLDER_ID = os.getenv("FOLDER_ID", "").strip()
AUTO_PHOTO_ROOT = Path(
    os.getenv("AUTO_PHOTO_ROOT") or str(PROJECT_ROOT / "downloads" / "extracted")
).expanduser()

# URL API
API_BASE_URL = "https://api.browser.vision/api/v1"
LOCAL_URL = "http://127.0.0.1:58712"

# ✅ ИСПРАВЛЕНО: с заглавной буквы!
DEFAULT_PLATFORM = "Windows"
DEFAULT_BROWSER = "Chrome"
DEFAULT_VERSION = "latest"
DEFAULT_PROXY_TYPE = "HTTP"

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
