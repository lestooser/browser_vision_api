"""
Генератор случайных fingerprint для профилей
"""

import copy
import random
from typing import Any, Dict, Optional

from config import DEFAULT_PORTS, DEFAULT_SCREEN, MODES

# Статический список названий веб-камер
WEBCAM_NAMES = [
    "USB 2.0 Webcamera",
    "Integrated Webcam",
    "HD Webcam",
    "HD User Facing",
    "Integrated Camera",
    "USB Video Device",
    "Microsoft LifeCam HD-3000",
    "Logitech HD Webcam C270",
    "Logitech HD Pro Webcam C920",
    "Realtek USB 2.0 Camera",
    "EasyCamera",
    "IR Camera",
    "1080P Camera",
    "1080P Pro HD Webcam",
    "720P HD Webcam",
    "FaceTime HD Camera",
    "FaceTime HD Camera (Built-in)",
    "USB 2.0 Camera",
    "USB Video",
    "Camera Front",
]


class FingerprintGenerator:
    """Генерирует случайные fingerprint с кастомными настройками"""

    def __init__(self, client):
        self.client = client
        self.base_fingerprint = None
        self._cache = {}

    def load_base_fingerprint(self, platform: str = "windows", version: str = "latest"):
        """Загружает базовый fingerprint"""
        self.base_fingerprint = self.client.get_fingerprint(platform, version)
        if not self.base_fingerprint:
            raise ValueError("Не удалось загрузить базовый fingerprint")
        return self.base_fingerprint

    def get_random_gpu(self, cached: bool = True) -> Optional[str]:
        """Получает случайную видеокарту ИЗ API"""
        cache_key = "gpus"

        if cached and cache_key in self._cache:
            gpus = self._cache[cache_key]
        else:
            gpus = self.client.get_gpus()
            if gpus:
                self._cache[cache_key] = gpus

        if gpus:
            return random.choice(gpus)
        return None

    def get_random_webcam(self) -> str:
        """Получает случайное название веб-камеры ИЗ ЛОКАЛЬНОГО СПИСКА"""
        return random.choice(WEBCAM_NAMES)

    def get_random_language(self, cached: bool = True) -> Optional[str]:
        """Получает случайный язык ИЗ API"""
        cache_key = "languages"

        if cached and cache_key in self._cache:
            languages = self._cache[cache_key]
        else:
            languages = self.client.get_languages()
            if languages:
                self._cache[cache_key] = languages

        if languages:
            return random.choice(languages)
        return None

    def get_random_timezone(self, cached: bool = True) -> Optional[str]:
        """Получает случайный часовой пояс ИЗ API"""
        cache_key = "timezones"

        if cached and cache_key in self._cache:
            timezones = self._cache[cache_key]
        else:
            timezones = self.client.get_timezones()
            if timezones:
                self._cache[cache_key] = timezones

        if timezones:
            return random.choice(timezones)
        return None

    def _get_gpu_vendor(self, gpu_name: str) -> str:
        """Определяет вендора видеокарты"""
        return "Google Inc. (NVIDIA)"

    def _format_pref_mode(self, mode: str, field: str) -> Any:
        """Форматирует режим защиты в формате, который принимает API."""
        if mode == MODES["OFF"]:
            return "off"

        if field == "webrtc":
            return "auto"

        if mode == MODES["MANUAL"]:
            return {"noise": 1}

        return "real"

    def generate(
        self,
        webrtc_mode: str = MODES["AUTO"],
        webgl_mode: str = MODES["MANUAL"],
        canvas_mode: str = MODES["MANUAL"],
        audio_mode: str = MODES["MANUAL"],
        client_rects_mode: str = MODES["MANUAL"],
        random_gpu: bool = True,
        random_webcam: bool = True,
        random_language: bool = False,
        random_timezone: bool = False,
        custom_webcam: Optional[str] = None,
        screen: Optional[Dict] = None,
        cpu_cores: int = 8,
        memory_gb: int = 16,
        ports: Optional[list] = None,
    ) -> Dict[str, Any]:
        """Генерирует полный fingerprint"""
        if not self.base_fingerprint:
            self.load_base_fingerprint()

        # Глубокое копирование базового fingerprint
        fingerprint = copy.deepcopy(self.base_fingerprint)

        fingerprint["webrtc_pref"] = self._format_pref_mode(webrtc_mode, "webrtc")
        fingerprint["webgl_pref"] = self._format_pref_mode(webgl_mode, "webgl")
        fingerprint["canvas_pref"] = self._format_pref_mode(canvas_mode, "canvas")

        # Audio и Client Rects: API принимает шумовые/ручные значения как 1
        if audio_mode == MODES["MANUAL"]:
            fingerprint["audio_pref"] = 1
        else:
            fingerprint["audio_pref"] = None

        if client_rects_mode == MODES["MANUAL"]:
            fingerprint["client_rects"] = 1
        else:
            fingerprint["client_rects"] = None

        # Видеокарта (ИЗ API)
        if random_gpu:
            selected_gpu = self.get_random_gpu()
            if selected_gpu:
                vendor = self._get_gpu_vendor(selected_gpu)
                if "webgl" not in fingerprint:
                    fingerprint["webgl"] = {}
                if "NVIDIA" not in selected_gpu.upper():
                    selected_gpu = "NVIDIA GeForce GTX 1080 Ti"
                fingerprint["webgl"]["unmasked_renderer"] = selected_gpu
                fingerprint["webgl"]["unmasked_vendor"] = vendor

        # Веб-камера (ИЗ ЛОКАЛЬНОГО СПИСКА)
        if custom_webcam:
            fingerprint["webcam"] = custom_webcam
        elif random_webcam:
            fingerprint["webcam"] = self.get_random_webcam()

        # Язык (ИЗ API)
        if random_language:
            language = self.get_random_language()
            if language:
                if "navigator" not in fingerprint:
                    fingerprint["navigator"] = {}
                fingerprint["navigator"]["language"] = language

        # Часовой пояс (ИЗ API)
        if random_timezone:
            timezone = self.get_random_timezone()
            if timezone:
                if "navigator" not in fingerprint:
                    fingerprint["navigator"] = {}
                fingerprint["navigator"]["timezone"] = timezone

        # Настройки экрана
        fingerprint["screen"] = screen or DEFAULT_SCREEN

        # Media devices: ручной режим (1/1/1)
        media_devices = {"audio_input": 1, "audio_output": 1, "video_input": 1}
        fingerprint["media_devices"] = media_devices

        # Navigator
        if "navigator" not in fingerprint:
            fingerprint["navigator"] = {}

        fingerprint["navigator"]["hardware_concurrency"] = cpu_cores
        fingerprint["navigator"]["device_memory"] = memory_gb
        fingerprint["navigator"]["media_devices"] = media_devices
        fingerprint["navigator"]["language"] = "ru"
        fingerprint["navigator"]["languages"] = ["ru", "ru-RU", "en-US", "en"]

        # Заблокированные порты
        fingerprint["ports_protection"] = ports or DEFAULT_PORTS

        # Геолокация
        fingerprint["geolocation"] = None

        # Аргументы запуска
        if "options" not in fingerprint:
            fingerprint["options"] = {}
        fingerprint["options"]["args"] = []

        return fingerprint

    def print_info(self, fingerprint: Dict[str, Any]):
        """Выводит информацию о fingerprint"""
        print("\n📊 Информация о fingerprint:")
        print("-" * 50)

        if "webgl" in fingerprint:
            print(f"💾 GPU: {fingerprint['webgl'].get('unmasked_renderer', 'N/A')}")

        if "webcam" in fingerprint:
            print(f"📹 Webcam: {fingerprint['webcam']}")

        if "navigator" in fingerprint:
            nav = fingerprint["navigator"]
            if "language" in nav:
                print(f"🌐 Language: {nav['language']}")
            if "timezone" in nav:
                print(f"🕐 Timezone: {nav['timezone']}")
            print(f"⚙️  CPU Cores: {nav.get('hardware_concurrency', 'N/A')}")
            print(f"🧠 Memory: {nav.get('device_memory', 'N/A')} GB")

        if "screen" in fingerprint:
            screen = fingerprint["screen"]
            print(f"🖥️  Screen: {screen.get('width')}x{screen.get('height')}")

        def render_pref(value: Any) -> str:
            if isinstance(value, dict):
                if "noise" in value:
                    return "Noise"
                if "real" in value:
                    return "Real"
            return str(value)

        print(f"🔌 WebRTC: {render_pref(fingerprint.get('webrtc_pref', 'N/A'))}")
        print(f"🎮 WebGL: {render_pref(fingerprint.get('webgl_pref', 'N/A'))}")
        print(f"🎨 Canvas: {render_pref(fingerprint.get('canvas_pref', 'N/A'))}")
        print(f"🔊 Audio: {fingerprint.get('audio_pref', 'N/A')}")
        print(f"📏 Client Rects: {fingerprint.get('client_rects', 'N/A')}")
        print("-" * 50)
