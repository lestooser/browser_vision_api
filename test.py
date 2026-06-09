import requests

token = "eyJ0eXAiOiJKV1QiLCJhbGciOiJIUzI1NiJ9.eyJ1c2VyX2lkIjoiM2IzMzY1OWItYmQxOC00MDQxLTk4NTktMTExODVhYzRmZWE4IiwidXNlcm5hbWUiOiJzdmV0YWVnb3JvdmF3dzFAZ21haWwuY29tIiwiaWF0IjoxNzgwOTkzMjIwLCJleHAiOjE4MTI1MjkyMjB9.PSaCcKgzOmef9X_HoEoCAy_wTqodv86azPeU0mSk-7g"
folder_id = "30289184-2163-4265-9b00-5d74f1a8c2af"

headers = {"X-Token": token}

# Getting a fingerprint of the current version
fingerprint = requests.get(
    "https://api.browser.vision/api/v1/fingerprints/windows/latest", headers=headers
).json()["data"]["fingerprint"]

# Adding required parameters to the fingerprint object
fingerprint["webrtc_pref"] = "auto"
fingerprint["canvas_pref"] = "real"
fingerprint["webgl_pref"] = "real"
fingerprint["audio_pref"] = None
fingerprint["proxy_id"] = "pool.proxys.io:10848:user331393o5596r781204:6t9ija"
fingerprint["ports_protection"] = [
    3389,
    5900,
    5901,
    5800,
    7070,
    6568,
    5938,
    1080,
    8080,
    3128,
    3030,
]

# Change language to auto
fingerprint["navigator"]["language"] = "auto"
fingerprint["navigator"]["languages"] = []


# Profile creating
result = requests.post(
    f"https://api.browser.vision/api/v1/folders/{folder_id}/profiles",
    headers={**headers, "Content-Type": "application/json"},
    json={
        "profile_name": "Profile name2",
        "profile_notes": "",
        "profile_tags": [],
        # "proxy_id": "pool.proxys.io:10848:user331393o5596r781204:6t9ija",
        "new_profile_tags": [],
        "profile_status": None,
        "browser": "Chrome",
        "platform": "Windows",
        "fingerprint": fingerprint,
    },
).json()

print(result)
