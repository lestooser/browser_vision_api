"""
Утилиты для работы с окнами и процессами в Windows.
"""

import ctypes
import logging
import socket
import subprocess
from ctypes import wintypes

logger = logging.getLogger(__name__)
user32 = ctypes.windll.user32


def find_console_pids_by_title(target_title: str):
    """Ищет PID процессов, окна которых имеют точный заголовок target_title."""
    pids = []

    def enum_callback(hwnd, __):
        try:
            if user32.IsWindowVisible(hwnd):
                length = user32.GetWindowTextLengthW(hwnd)
                if length > 0:
                    buff = ctypes.create_unicode_buffer(length + 1)
                    user32.GetWindowTextW(hwnd, buff, length + 1)
                    title = buff.value
                    if title == target_title:
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
    """Убивает процесс tebor по PID и, при необходимости, консольное окно по точному заголовку."""
    killed = 0

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
            logger.warning(f"Не удалось убить tebor PID {tebor_pid}: {e}")

    elif console_title:
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

    return killed


def is_port_listening(port: int) -> bool:
    """Проверяет, слушает ли кто-то указанный CDP-порт."""
    if not port:
        return False
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.settimeout(1)
            return s.connect_ex(("127.0.0.1", port)) == 0
    except Exception:
        return False


def kill_browser_by_port(port: int) -> bool:
    """
    🧟 УНИВЕРСАЛЬНОЕ ОРУЖИЕ ПРОТИВ ЗОМБИ.
    Находит PID процесса, который слушает указанный порт, и принудительно убивает его.
    """
    if not port:
        return False
    try:
        result = subprocess.run(
            f"netstat -ano | findstr :{port} | findstr LISTENING",
            capture_output=True,
            text=True,
            shell=True,
            timeout=5,
        )
        killed = False
        for line in result.stdout.splitlines():
            parts = line.split()
            if parts:
                pid = parts[-1]
                if pid.isdigit() and pid != "0":
                    logger.info(
                        f" Найдено приложение на порту {port} (PID {pid}). Убиваю..."
                    )
                    kill_res = subprocess.run(
                        ["taskkill", "/F", "/T", "/PID", pid],
                        capture_output=True,
                        text=True,
                        timeout=5,
                    )
                    if kill_res.returncode == 0:
                        killed = True
        return killed
    except Exception as e:
        logger.debug(f"Не удалось убить процесс по порту {port}: {e}")
        return False
