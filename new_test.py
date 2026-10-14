import os
from profile_script.photo_path import get_photo_path

# ================== НАСТРОЙКИ ==================
# LOGIN = "your_email_or_phone"  # Замените на свои данные
# PASSWORD = "your_password"
PHOTO_PATHS = get_photo_path(os.getenv("FOLDER_PHOTO_PATH"))
print(PHOTO_PATHS)
