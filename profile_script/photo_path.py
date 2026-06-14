import os

from dotenv import load_dotenv

load_dotenv()


def get_photo_path(FOLDER_PHOTO_PATH=os.getenv("FOLDER_PHOTO_PATH")):
    temp_list = []
    for file in os.listdir(FOLDER_PHOTO_PATH):
        filePath = os.path.join(FOLDER_PHOTO_PATH, file)
        temp_list.append(filePath)
    return temp_list
