import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from api_client import BrowserVisionClient
from config import FOLDER_ID


def open_profile(profile_id: str, port: int) -> None:
    if not FOLDER_ID:
        raise RuntimeError("Set FOLDER_ID in .env before running this script.")
    if not profile_id:
        raise ValueError("A profile ID is required.")

    result = BrowserVisionClient().start_profile(FOLDER_ID, profile_id, port=port)
    if result is None:
        raise RuntimeError("The profile could not be started; check the local API.")
    print(result)


if __name__ == "__main__":
    requested_profile_id = input("Profile ID to start: ").strip()
    open_profile(requested_profile_id, port=9222)
