"""
Утилиты для работы с окнами консоли в Windows.
Позволяет найти окно по заголовку и убить его вместе с процессом.
"""

import ctypes
import logging
import subprocess
from ctypes import wintypes

logger = logging.getLogger(__name__)

user32 = ctypes.windll.user32


def find_console_pids_by_title(target_title: str):
    """Ищет PID процессов, окна которых содержат target_title в заголовке."""
    pids = []

    def enum_callback(hwnd, __):
        try:
            if user32.IsWindowVisible(hwnd):
                length = user32.GetWindowTextLengthW(hwnd)
                if length > 0:
                    buff = ctypes.create_unicode_buffer(length + 1)
                    user32.GetWindowTextW(hwnd, buff, length + 1)
                    if target_title in buff.value:
                        pid = wintypes.DWORD()
                        user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
                        pids.append(pid.value)
        except Exception:
            pass
        return True

    WNDENUMPROC = ctypes.WINFUNCTYPE(ctypes.c_bool, wintypes.HWND, wintypes.LPARAM)
    user32.EnumWindows(WNDENUMPROC(enum_callback), 0)
    return pids


def kill_console_and_process(console_title: str, tebor_pid: int):
    """
    Убивает окно консоли по заголовку и процесс tebor по PID.
    Возвращает количество убитых объектов.
    """
    killed = 0

    # 1. Ищем и убиваем окно консоли (именно чёрное окно cmd/powershell)
    if console_title:
        console_pids = find_console_pids_by_title(console_title)
        for pid in set(console_pids):
            try:
                res = subprocess.run(
                    ["taskkill", "/F", "/T", "/PID", str(pid)],
                    capture_output=True,
                    text=True,
                    timeout=5,
                )
                if res.returncode == 0:
                    killed += 1
                    logger.info(
                        f"🔪 Окно консоли '{console_title}' (PID {pid}) закрыто"
                    )
            except Exception as e:
                logger.warning(f"Не удалось убить консоль PID {pid}: {e}")

    # 2. Убиваем сам процесс python.exe (tebor), если он ещё жив
    if tebor_pid:
        try:
            res = subprocess.run(
                ["taskkill", "/F", "/T", "/PID", str(tebor_pid)],
                capture_output=True,
                text=True,
                timeout=5,
            )
            if res.returncode == 0:
                killed += 1
                logger.info(f"🔪 Процесс tebor (PID {tebor_pid}) закрыт")
        except Exception as e:
            logger.debug(f"Процесс tebor {tebor_pid} уже закрыт или ошибка: {e}")

    return killed
