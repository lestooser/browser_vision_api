@echo off
cd /d "D:\python\browser_vision_api"
set "AUTO_START_ALL_PROFILE=1"
start "VisionTGbotAuto" cmd /c "call venv\Scripts\activate && python photo_notify_bot.py"
exit /b
