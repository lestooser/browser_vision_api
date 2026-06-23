import logging
import os
import random
import time
from datetime import datetime
from typing import List

from dotenv import load_dotenv
from selenium import webdriver
from selenium.common.exceptions import (
    NoSuchElementException,
    TimeoutException,
    WebDriverException,
)
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait

from profile_script.photo_path import get_photo_path

load_dotenv()
PHOTO_PATHS = get_photo_path(os.getenv("FOLDER_PHOTO_PATH"))

# ================== НАСТРОЙКА ЛОГГИРОВАНИЯ ==================
LOG_DIR = "logs"
os.makedirs(LOG_DIR, exist_ok=True)

logger = logging.getLogger("TaborPhotoUploader")
logger.setLevel(logging.DEBUG)


# ================== ИНТЕГРАЦИЯ С TELEGRAM БОТОМ ==================
# Папка для флагов запросов пополнения
REPLENISH_FLAG_DIR = os.path.join(LOG_DIR, "replenish_needed")
os.makedirs(REPLENISH_FLAG_DIR, exist_ok=True)

TG_EVENT_DIR = os.path.join(LOG_DIR, "tg_events")
os.makedirs(TG_EVENT_DIR, exist_ok=True)


def _write_tg_event(event_type: str, message: str, id_value: str = None) -> bool:
    """Передаёт уведомление локальному Telegram-боту через файл события."""
    try:
        safe_id = id_value or "general"
        filename = (
            f"{datetime.now().strftime('%Y%m%d%H%M%S%f')}_{safe_id}_{event_type}.txt"
        )
        event_file = os.path.join(TG_EVENT_DIR, filename)
        with open(event_file, "w", encoding="utf-8") as f:
            f.write(message)
        return True
    except Exception as e:
        print(f"⚠️ Не удалось создать Telegram-событие: {e}")
        logger.error(f"Не удалось создать Telegram-событие: {e}")
        return False


def _send_tg_notification(message: str) -> bool:
    """Совместимость со старым кодом: уведомления забирает бот этого проекта."""
    return _write_tg_event("notice", message)


log_filename = os.path.join(LOG_DIR, f"tabor_{datetime.now().strftime('%Y%m%d')}.log")
file_handler = logging.FileHandler(log_filename, encoding="utf-8")
file_handler.setLevel(logging.DEBUG)
formatter = logging.Formatter(
    "%(asctime)s - %(levelname)s - %(message)s", datefmt="%Y-%m-%d %H:%M:%S"
)
file_handler.setFormatter(formatter)
logger.addHandler(file_handler)

console_handler = logging.StreamHandler()
console_handler.setLevel(logging.ERROR)
console_handler.setFormatter(formatter)
logger.addHandler(console_handler)


class TaborPhotoUploader:
    STATUS_MAIN = "Главная"
    STATUS_BLOCKED = "Заблокировано"
    STATUS_PENDING = ""

    # 🆕 Селектор элемента профиля (появляется только при авторизации)
    PROFILE_ELEMENT_SELECTOR = (
        "body > div.page.page_auth > div.wrap.clearfix > "
        "div.sidebar > div.profile-block.clearfix > a.link-wrapper > span"
    )

    def __init__(self, driver, login: str, password: str, id_value: str = None):
        self.driver = driver
        self.wait = WebDriverWait(driver, 20)
        self._login = login
        self._password = password
        self.id_value = id_value
        self._turbolinks_disabled = False
        self._gallery_url = None  # 🆕 Сохранённый URL галереи
        logger.info(f"Инициализация TaborPhotoUploader, id_value={id_value}")

    # ================== 🆕 ПРОВЕРКА АВТОРИЗАЦИИ ==================

    def _wait_for_replenish_confirmation(self, photo_folder: str) -> List[str]:
        """
        Ждёт команды перепроверки из Telegram-бота.

        Логика:
        1. Создаёт файл-флаг в logs/replenish_needed/{id_value}.txt
        2. Отправляет уведомление в Telegram
        3. Ждёт, пока бот не удалит файл-флаг (команда /photo_continue)
        4. Перечитывает папку с фото
        5. Возвращает новый список фото

        Returns:
            Список путей к новым фото или пустой список при таймауте
        """
        flag_file = os.path.join(REPLENISH_FLAG_DIR, f"{self.id_value}.txt")

        # Создаём флаг
        try:
            with open(flag_file, "w", encoding="utf-8") as f:
                f.write(
                    f"chat_id={TG_CHAT_ID}\nfolder={photo_folder}\ncreated={datetime.now().isoformat()}"
                )
            logger.info(f"Создан флаг запроса пополнения: {flag_file}")
        except Exception as e:
            logger.error(f"Не удалось создать файл-флаг: {e}")
            return []

        # Отправляем уведомление
        notification = (
            f"📸 <b>Фотографии закончились!</b>\n\n"
            f"🆔 ID: <code>{self.id_value}</code>\n"
            f"📁 Папка: <code>{photo_folder}</code>\n\n"
            f"🔄 Добавьте фото и выполните команду:\n"
            f"<code>/photo_continue {self.id_value}</code>"
        )
        _send_tg_notification(notification)

        print("\n⏳ Ожидание команды перепроверки из Telegram...")
        print(f"   Флаг: {flag_file}")
        print(f"   Команда в боте: /photo_continue {self.id_value}")
        logger.info("Ожидание команды перепроверки из Telegram")

        # Ждём, пока флаг не будет удалён (максимум 24 часа)
        max_wait_seconds = 24 * 60 * 60
        start_time = time.time()
        check_interval = 10  # проверяем каждые 10 секунд

        while time.time() - start_time < max_wait_seconds:
            if not os.path.exists(flag_file):
                print("✅ Команда перепроверки получена!")
                logger.info("Команда перепроверки получена")

                # Перечитываем папку
                if os.path.exists(photo_folder):
                    new_photos = get_photo_path(photo_folder)
                    if new_photos:
                        print(f"📸 Найдено новых фото: {len(new_photos)}")
                        logger.info(f"Найдено новых фото: {len(new_photos)}")
                        _send_tg_notification(
                            f"✅ Получены новые фото для ID <code>{self.id_value}</code>\n"
                            f"📸 Количество: {len(new_photos)}\n"
                            f"🔄 Продолжаю загрузку..."
                        )
                        return new_photos
                    else:
                        print("⚠️ Папка пуста. Добавьте фото и повторите команду.")
                        logger.warning("Папка пуста после команды перепроверки")
                        # Повторно создаём флаг и уведомляем
                        _send_tg_notification(
                            f"⚠️ Для ID <code>{self.id_value}</code> папка пуста.\n"
                            f"Добавьте фото и повторите: <code>/photo_continue {self.id_value}</code>"
                        )
                        # Повторно создаём флаг
                        try:
                            with open(flag_file, "w", encoding="utf-8") as f:
                                f.write(
                                    f"chat_id={TG_CHAT_ID}\nfolder={photo_folder}\ncreated={datetime.now().isoformat()}"
                                )
                        except Exception:
                            pass
                        continue
                else:
                    print(f"⚠️ Папка не найдена: {photo_folder}")
                    logger.warning(f"Папка не найдена: {photo_folder}")
                    return []

            time.sleep(check_interval)

        print("⏰ Время ожидания истекло (24 часа). Завершаем.")
        logger.warning("Время ожидания истекло")
        _send_tg_notification(
            f"⏰ Время ожидания пополнения для ID <code>{self.id_value}</code> истекло."
        )
        return []

    # ================== ЛОГГИРОВАНИЕ ОШИБОК ==================
    def _log_error(
        self, error_msg: str, exception: Exception = None, save_screenshot: bool = True
    ):
        """Логирует ошибку и сохраняет скриншот."""
        logger.error(f"❌ {error_msg}")
        if exception:
            logger.exception(f"Исключение: {exception}")
        if save_screenshot:
            try:
                screenshot_dir = os.path.join(LOG_DIR, "screenshots")
                os.makedirs(screenshot_dir, exist_ok=True)
                timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                safe_msg = "".join(
                    c for c in error_msg if c.isalnum() or c in " -_"
                ).strip()[:50]
                screenshot_path = os.path.join(
                    screenshot_dir, f"error_{timestamp}_{safe_msg}.png"
                )
                self.driver.save_screenshot(screenshot_path)
                logger.info(f"📸 Скриншот сохранён: {screenshot_path}")
            except Exception as e:
                logger.error(f"Не удалось сохранить скриншот: {e}")

    # ================== 🆕 ПРОВЕРКА АВТОРИЗАЦИИ ==================
    def is_already_logged_in(self, timeout: int = 10) -> bool:
        """Проверяет, авторизован ли пользователь (по наличию элемента профиля)."""
        try:
            print(f"🔍 Проверка авторизации (ожидание до {timeout} сек)...")
            WebDriverWait(self.driver, timeout).until(
                EC.presence_of_element_located(
                    (By.CSS_SELECTOR, self.PROFILE_ELEMENT_SELECTOR)
                )
            )
            print("✅ Пользователь уже авторизован (элемент профиля найден)")
            logger.info("Пользователь уже авторизован")
            return True
        except TimeoutException:
            print("ℹ️  Элемент профиля не найден — требуется авторизация")
            logger.info("Требуется авторизация")
            return False

    def click_profile_element(self) -> bool:
        """Кликает по элементу профиля через JS (переход в анкету)."""
        try:
            profile_elem = self.wait.until(
                EC.element_to_be_clickable(
                    (By.CSS_SELECTOR, self.PROFILE_ELEMENT_SELECTOR)
                )
            )
            self.driver.execute_script("arguments[0].click();", profile_elem)
            print("✅ Клик по элементу профиля выполнен (через JS)")
            logger.info("Клик по элементу профиля")
            self._random_delay(1.5, 3, "переход в анкету")
            return True
        except Exception as e:
            self._log_error(
                f"Не удалось кликнуть по элементу профиля: {e}", exception=e
            )
            return False

    # ================== СЛУЧАЙНЫЕ ЗАДЕРЖКИ ==================
    def _random_delay(
        self, min_sec: float = 1.0, max_sec: float = 5.0, context: str = ""
    ):
        """Случайная задержка с уведомлением."""
        delay = random.uniform(min_sec, max_sec)
        msg = f"⏱️  Случайная задержка {delay:.1f} сек."
        if context:
            msg += f" [{context}]"
        print(msg)
        logger.debug(msg)
        time.sleep(delay)

    # ================== ЗАЩИТА ОТ БАНА: ИМИТАЦИЯ ЧЕЛОВЕКА ==================
    def _simulate_human_activity(self):
        """Имитирует человеческую активность между загрузками."""
        print("\n👤 Имитация человеческой активности...")
        logger.debug("Начало имитации человеческой активности")

        actions = [
            (
                "скролл страницы",
                lambda: self.driver.execute_script(
                    f"window.scrollBy(0, {random.randint(100, 400)});"
                ),
            ),
            (
                "скролл вверх",
                lambda: self.driver.execute_script(
                    f"window.scrollBy(0, {random.randint(-300, -100)});"
                ),
            ),
            (
                "движение мыши",
                lambda: self.driver.execute_script("""
                let x = Math.random() * window.innerWidth;
                let y = Math.random() * window.innerHeight;
                let event = new MouseEvent('mousemove', {
                    clientX: x, clientY: y, bubbles: true
                });
                document.body.dispatchEvent(event);
            """),
            ),
            ("пауза на раздумье", lambda: time.sleep(random.uniform(2, 5))),
        ]

        num_actions = random.randint(2, 4)
        for i in range(num_actions):
            action_name, action_func = random.choice(actions)
            print(f"  🎭 {action_name}...")
            try:
                action_func()
            except Exception:
                pass
            time.sleep(random.uniform(0.5, 1.5))

        print("✅ Имитация завершена\n")

    # ================== ЗАЩИТА ОТ БАНА: ДЛИТЕЛЬНАЯ ПАУЗА ==================
    def _anti_ban_delay(self):
        """Длительная случайная пауза между загрузками фото."""
        base_delay = random.uniform(45, 120)

        if random.random() < 0.1:
            base_delay += random.uniform(60, 180)
            print("🤔 Долгое раздумье пользователя...")
            logger.info("Запланировано долгое раздумье")

        print(f"\n⏸️  Пауза между загрузками: {base_delay:.0f} секунд (защита от бана)")
        logger.info(f"Антибан-пауза: {base_delay:.0f} сек")

        elapsed = 0
        while elapsed < base_delay:
            chunk = min(random.uniform(5, 15), base_delay - elapsed)
            time.sleep(chunk)
            elapsed += chunk
            if int(elapsed) % 20 < 5:
                self._simulate_human_activity()

        print("✅ Пауза завершена\n")
        logger.info("Антибан-пауза завершена")

    # ================== ОТКЛЮЧЕНИЕ TURBOLINKS ==================
    def _disable_turbolinks(self):
        """Отключает Turbolinks для корректной навигации."""
        if self._turbolinks_disabled:
            return
        try:
            self.driver.execute_script("""
                if (window.Turbolinks) {
                    Turbolinks.supported = false;
                }
                if (window.jQuery && jQuery.turbolinks) {
                    jQuery.turbolinks.disabled = true;
                }
                if (window.jQuery) {
                    $(document).off('page:change').off('turbolinks:load');
                }
            """)
            self._turbolinks_disabled = True
            print("🔧 Turbolinks отключён")
            logger.info("Turbolinks отключён")
        except Exception as e:
            logger.warning(f"Не удалось отключить Turbolinks: {e}")
            print(f"⚠️  Не удалось отключить Turbolinks: {e}")

    # ================== CSRF TOKEN ==================
    def _get_csrf_token(self) -> str:
        """Получает CSRF token из meta-тега."""
        try:
            token = self.driver.execute_script(
                "return document.querySelector('meta[name=\"csrf-token\"]')?.content || '';"
            )
            return token or ""
        except Exception:
            return ""

    # ================== ОЖИДАНИЕ ЗАГРУЗЧИКА ==================
    def _wait_for_uploader_script(self):
        """Ждёт, пока скрипт загрузчика photo_uploader полностью загрузится."""
        try:
            WebDriverWait(self.driver, 10).until(lambda d: d.execute_script("""
                    return document.querySelector('#fileupload_master') !== null ||
                           document.querySelector('.arcticmodal-container') !== null ||
                           document.querySelector('#crop_action') !== null;
                """))
            print("✅ Скрипт загрузчика загружен")
        except TimeoutException:
            logger.warning("Скрипт загрузчика не загрузился за 10 сек")
            print("⚠️  Скрипт загрузчика не загрузился за 10 сек")

    # ================== 🆕 ПРОВЕРКА И ВОЗВРАТ В ГАЛЕРЕЮ ==================
    def _ensure_on_gallery(self) -> bool:
        """Проверяет, что мы на точном URL галереи. Если нет — возвращает."""
        # 🆕 Сначала проверяем, жива ли сессия
        if not self._is_session_alive():
            print("❌ Сессия Selenium потеряна")
            logger.error("Сессия потеряна в _ensure_on_gallery")

            # Пытаемся переподключиться
            if self._try_reconnect():
                print("✅ Соединение восстановлено, продолжаем работу")
                # После переподключения нужно вернуться в галерею
                if self._gallery_url:
                    try:
                        self.driver.get(self._gallery_url)
                        time.sleep(2)
                        return True
                    except Exception as e:
                        logger.error(
                            f"Не удалось вернуться в галерею после переподключения: {e}"
                        )
                        return False
            else:
                print("❌ Не удалось восстановить соединение. Завершаем работу.")
                return False

        if not self._gallery_url:
            logger.warning("URL галереи не сохранён, переходим в галерею...")
            print("⚠️  URL галереи не сохранён, переходим в галерею...")
            self.go_to_photo_section()
            return True

        try:
            current_url = self.driver.current_url
            current_base = current_url.split("?")[0].split("#")[0]
            gallery_base = self._gallery_url.split("?")[0].split("#")[0]

            print(f"🔍 Проверка URL: {current_url}")
            print(f"📍 Ожидаемый URL: {self._gallery_url}")

            if current_base != gallery_base:
                logger.warning(f"Не на странице галереи! Возвращаемся с {current_url}")
                print("⚠️  Не на странице галереи! Возвращаемся...")
                try:
                    self.driver.get(self._gallery_url)
                    time.sleep(2)
                    self.wait.until(
                        EC.presence_of_element_located((By.CSS_SELECTOR, "ul.gallery"))
                    )
                    print("✅ Вернулись в галерею")
                    logger.info("Вернулись в галерею")
                    return True
                except Exception as e:
                    self._log_error(f"Не удалось вернуться в галерею: {e}", exception=e)
                    return False

            print("✅ Мы на странице галереи")
            return True

        except Exception as e:
            error_msg = str(e).lower()
            if "invalid session" in error_msg or "session deleted" in error_msg:
                logger.error(f"❌ Сессия потеряна во время проверки URL: {e}")
                print("❌ Сессия потеряна во время проверки URL")
                return False
            else:
                logger.error(f"Ошибка проверки URL: {e}")
                print(f"⚠️ Ошибка проверки URL: {e}")
                return False

    # ================== ОЧИСТКА СОСТОЯНИЯ ЗАГРУЗОК ==================
    def _clear_upload_state(self):
        """Очистка cookies/storage с учётом Turbolinks."""
        print("\n🧹 === Очистка состояния загрузок ===")
        logger.info("Начало очистки состояния загрузок")

        self._disable_turbolinks()

        all_cookies = self.driver.get_cookies()
        upload_patterns = [
            "photo",
            "upload",
            "gallery",
            "crop",
            "image",
            "file",
            "uploader",
            "media",
            "attachment",
            "temp",
        ]
        auth_patterns = [
            "session",
            "auth",
            "token",
            "remember",
            "user_id",
            "csrf",
            "sid",
            "ssid",
            "secret",
            "jwt",
            "login",
        ]

        deleted_cookies = []
        kept_cookies = []

        for cookie in all_cookies:
            name_lower = cookie["name"].lower()
            is_upload = any(p in name_lower for p in upload_patterns)
            is_auth = any(p in name_lower for p in auth_patterns)

            if is_upload and not is_auth:
                try:
                    self.driver.delete_cookie(cookie["name"])
                    deleted_cookies.append(cookie["name"])
                except Exception as e:
                    logger.warning(f"Не удалось удалить cookie '{cookie['name']}': {e}")
            else:
                kept_cookies.append(cookie["name"])

        if deleted_cookies:
            print(
                f"  🗑️  Удалено cookies ({len(deleted_cookies)}): {', '.join(deleted_cookies)}"
            )
            logger.info(f"Удалено cookies: {len(deleted_cookies)}")
        else:
            print("  ℹ️  Cookies загрузок не обнаружены")

        print(f"  🔒 Сохранено авторизационных cookies: {len(kept_cookies)}")

        try:
            cleared_ls = self.driver.execute_script("""
                let cleared = [];
                let keysToRemove = [];
                for (let i = localStorage.length - 1; i >= 0; i--) {
                    let key = localStorage.key(i);
                    if (key && (key.includes('photo') || key.includes('upload') || key.includes('gallery') || key.includes('crop') || key.includes('image') || key.includes('file') || key.includes('uploader') || key.includes('media'))) {
                        keysToRemove.push({storage: 'localStorage', key: key});
                    }
                }
                for (let i = sessionStorage.length - 1; i >= 0; i--) {
                    let key = sessionStorage.key(i);
                    if (key && (key.includes('photo') || key.includes('upload') || key.includes('gallery') || key.includes('crop') || key.includes('image') || key.includes('file') || key.includes('uploader') || key.includes('media'))) {
                        keysToRemove.push({storage: 'sessionStorage', key: key});
                    }
                }
                keysToRemove.forEach(item => {
                    if (item.storage === 'localStorage') localStorage.removeItem(item.key);
                    else sessionStorage.removeItem(item.key);
                    cleared.push(item.storage + ':' + item.key);
                });
                return cleared;
            """)
            if cleared_ls:
                print(f"  🗑️  Очищено из storage ({len(cleared_ls)})")
                logger.info(f"Очищено из storage: {len(cleared_ls)}")
            else:
                print("  ℹ️  Storage загрузок пуст")
        except Exception as e:
            logger.error(f"Ошибка очистки storage: {e}")
            print(f"  ⚠️  Ошибка очистки storage: {e}")

        print("  🔄 Полная перезагрузка страницы (hard reload)...")
        try:
            self.driver.execute_script("window.location.reload(true);")
            time.sleep(3)
        except Exception:
            self.driver.refresh()
            time.sleep(2)

        print("🧹 === Очистка завершена ===\n")
        logger.info("Очистка состояния загрузок завершена")

    # ================== АВТОРИЗАЦИЯ ==================
    def login(self) -> bool:
        """Авторизация с ручным обходом Turnstile."""
        try:
            logger.info("Начало процесса авторизации")
            self.driver.get("https://tabor.ru")
            self._random_delay(2, 4, "открытие сайта")

            login_btn = self.wait.until(
                EC.element_to_be_clickable((By.CSS_SELECTOR, "a[href='/signin']"))
            )
            login_btn.click()
            self._random_delay(1, 3, "переход на страницу входа")

            email_input = self.wait.until(
                EC.presence_of_element_located((By.ID, "session_user_login"))
            )
            email_input.send_keys(self._login)
            self._random_delay(0.5, 1.5, "ввод логина")

            pass_input = self.driver.find_element(By.ID, "session_user_password")
            pass_input.send_keys(self._password)
            self._random_delay(0.5, 1.5, "ввод пароля")

            input("👉 Пройдите капчу 'Я не робот' и нажмите Enter...")

            submit_btn = self.driver.find_element(
                By.CSS_SELECTOR, "input[type='submit'][value='Войти']"
            )
            submit_btn.click()
            self._random_delay(2, 5, "после нажатия 'Войти'")

            logger.info("Авторизация завершена")
            return True
        except Exception as e:
            self._log_error(f"Ошибка авторизации: {e}", exception=e)
            return False

    def go_to_photo_section(self, max_attempts: int = 3):
        """
        Переход в раздел 'Фото' (галерею).
        🆕 При неудаче — перезагружает страницу и пробует снова.
        """
        self._disable_turbolinks()

        for attempt in range(1, max_attempts + 1):
            try:
                print(f"📍 Попытка {attempt}/{max_attempts} перейти в галерею...")

                # 🆕 Сначала пробуем кликнуть по элементу профиля (переход в анкету)
                try:
                    profile_elem = WebDriverWait(self.driver, 5).until(
                        EC.presence_of_element_located(
                            (By.CSS_SELECTOR, self.PROFILE_ELEMENT_SELECTOR)
                        )
                    )
                    self.driver.execute_script("arguments[0].click();", profile_elem)
                    print("✅ Клик по элементу профиля выполнен (через JS)")
                    self._random_delay(1.5, 3, "переход в анкету")
                except TimeoutException:
                    print(
                        "ℹ️  Элемент профиля не найден, ищем ссылку на галерею напрямую..."
                    )

                # Ищем ссылку на галерею
                gallery_selectors = [
                    "a.user__gallery__link_photo",
                    "a.profile__ava-add",
                    "a[href*='photos']",
                ]

                photo_link = None
                for selector in gallery_selectors:
                    try:
                        photo_link = WebDriverWait(self.driver, 5).until(
                            EC.element_to_be_clickable((By.CSS_SELECTOR, selector))
                        )
                        print(f"✅ Найдена ссылка на галерею: {selector}")
                        break
                    except TimeoutException:
                        continue

                if not photo_link:
                    raise TimeoutException("Не найдена ссылка на галерею")

                self.driver.execute_script("arguments[0].click();", photo_link)
                print("✅ Клик по ссылке галереи выполнен (через JS)")

                # Ждём появления галереи
                WebDriverWait(self.driver, 10).until(
                    EC.presence_of_element_located((By.CSS_SELECTOR, "ul.gallery"))
                )
                self._random_delay(1.5, 3, "загрузка галереи")

                # 🆕 Сохраняем точный URL галереи
                self._gallery_url = self.driver.current_url
                print(f"📍 URL галереи сохранён: {self._gallery_url}")

                csrf = self._get_csrf_token()
                if csrf:
                    print(f"🔑 CSRF token получен: {csrf[:12]}...")

                print("✅ Успешно перешли в галерею")
                return  # Успех — выходим из метода

            except (TimeoutException, Exception) as e:
                print(
                    f"⚠️  Не удалось перейти в галерею (попытка {attempt}/{max_attempts}): {e}"
                )

                if attempt < max_attempts:
                    # 🆕 ПЕРЕЗАГРУЖАЕМ СТРАНИЦУ и пробуем снова
                    print("🔄 Перезагружаем страницу перед повторной попыткой...")
                    try:
                        self.driver.refresh()
                    except Exception as refresh_err:
                        print(
                            f"⚠️  Ошибка refresh: {refresh_err}, пробуем вернуться на tabor.ru"
                        )
                        try:
                            self.driver.get("https://tabor.ru")
                        except Exception:
                            pass
                    self._random_delay(3, 5, "после перезагрузки")
                else:
                    # Все попытки исчерпаны
                    print("❌ Не удалось перейти в галерею после всех попыток")
                    raise TimeoutException(
                        f"Не удалось перейти в галерею после {max_attempts} попыток"
                    )

    def _trigger_main_processing(self):
        """Автогенерация через внешний проект отключена.

        Проект больше не обращается к соседним проектам.
        Пополнение фото управляется только локальным Telegram-ботом:
        добавьте файлы в папку и выполните /photo_continue <id>.
        """
        message = (
            f"⚠️ Для ID <code>{self.id_value or 'N/A'}</code> автогенерация фото отключена.\n"
            "Добавьте фото в папку и выполните <code>/photo_continue</code>."
        )
        _write_tg_event("error", message, self.id_value)
        logger.info("Внешняя обработка отключена")
        return False

    def _get_photo_folder(self) -> str:
        """Возвращает путь к папке с фото для текущего ID."""
        if not self.id_value:
            return None

        # Пытаемся определить из PHOTO_PATHS
        if PHOTO_PATHS:
            return os.path.dirname(PHOTO_PATHS[0])

        # Fallback: авто-путь по ID
        auto_folder = (
            f"D:\\python\\selenium-test\\downloads\\extracted\\{self.id_value}"
        )
        if os.path.exists(auto_folder):
            return auto_folder

        return None

    def _wait_for_photo_replenish(self, max_wait_hours: int = 24) -> bool:
        """
        Создаёт файл-флаг в logs/photo_needed/<id>.txt и ждёт его удаления
        из Telegram-бота (команда /photo_continue <id>).

        Returns:
            True если сигнал получен, False если таймаут или ошибка
        """
        if not self.id_value:
            logger.error("Не указан ID для ожидания пополнения")
            return False

        # Определяем папку с фото
        photo_folder = self._get_photo_folder()

        # Создаём файл-флаг
        flag_dir = os.path.join(LOG_DIR, "photo_needed")
        os.makedirs(flag_dir, exist_ok=True)
        flag_file = os.path.join(flag_dir, f"{self.id_value}.txt")

        try:
            with open(flag_file, "w", encoding="utf-8") as f:
                f.write(f"folder={photo_folder or ''}\n")
                f.write(f"created={datetime.now().isoformat()}\n")
            logger.info(f"Создан файл-флаг: {flag_file}")
            print("\n📸 Фотографии кончились!")
            print(f"🆔 ID: {self.id_value}")
            print(f"📁 Папка: {photo_folder}")
            print(f"⏳ Ожидаю команды /photo_continue {self.id_value} из Telegram...")
        except Exception as e:
            logger.error(f"Не удалось создать файл-флаг: {e}")
            print(f"❌ Не удалось создать файл-флаг: {e}")
            return False

        # Ждём удаления файла (максимум max_wait_hours часов)
        max_wait_seconds = max_wait_hours * 60 * 60
        start_time = time.time()
        check_interval = 10  # проверяем каждые 10 секунд

        while time.time() - start_time < max_wait_seconds:
            if not os.path.exists(flag_file):
                print("✅ Сигнал получен! Проверяю папку...")
                logger.info("Сигнал получен из Telegram")
                return True

            time.sleep(check_interval)

        print(f"⏰ Время ожидания истекло ({max_wait_hours} часов).")
        logger.warning("Время ожидания пополнения истекло")

        # Удаляем файл-флаг при таймауте
        try:
            if os.path.exists(flag_file):
                os.remove(flag_file)
        except Exception:
            pass

        return False

    # ================== РАБОТА С ГАЛЕРЕЕЙ ==================
    def _get_gallery_photos(self) -> list:
        try:
            return self.driver.find_elements(By.CSS_SELECTOR, "li.gallery__item")
        except Exception as e:
            logger.error(f"Ошибка получения списка фото: {e}")
            return []

    def _get_photo_status(self, photo_element) -> str:
        try:
            status_elem = photo_element.find_element(
                By.CSS_SELECTOR, "span.meta__item__lbl"
            )
            return status_elem.text.strip()
        except NoSuchElementException:
            return ""
        except Exception as e:
            logger.warning(f"Ошибка получения статуса фото: {e}")
            return ""

    def _get_photo_link(self, photo_element) -> str:
        try:
            link = photo_element.find_element(By.CSS_SELECTOR, "a.gallery__img-link")
            return link.get_attribute("href")
        except Exception as e:
            logger.error(f"Ошибка получения ссылки на фото: {e}")
            return ""

    def _delete_photo_file(self, photo_path: str):
        try:
            if os.path.isfile(photo_path):
                os.remove(photo_path)
                print(f"🗑️  Файл {os.path.basename(photo_path)} удалён с диска.")
                logger.info(f"Файл удалён с диска: {photo_path}")
        except Exception as e:
            logger.error(f"Не удалось удалить файл {photo_path}: {e}")
            print(f"⚠️  Не удалось удалить файл {photo_path}: {e}")

    def _is_session_alive(self) -> bool:
        """Проверяет, что сессия Selenium всё ещё активна."""
        try:
            # Пытаемся выполнить простую команду
            _ = self.driver.current_url
            return True
        except Exception as e:
            error_msg = str(e).lower()
            if (
                "invalid session" in error_msg
                or "session deleted" in error_msg
                or "not connected" in error_msg
            ):
                logger.error(f"❌ Сессия Selenium потеряна: {e}")
                return False
            # Другие ошибки — тоже считаем потерей сессии
            logger.warning(f"⚠️ Ошибка проверки сессии: {e}")
            return False

    def _safe_execute(self, func, *args, **kwargs):
        """
        Безопасно выполняет команду драйвера с проверкой сессии.
        Если сессия потеряна, пытается переподключиться.
        """
        try:
            return func(*args, **kwargs)
        except Exception as e:
            error_msg = str(e).lower()
            if "invalid session" in error_msg or "session deleted" in error_msg:
                logger.warning(
                    f"Сессия потеряна при выполнении {func.__name__}, пытаемся переподключиться"
                )
                if self._try_reconnect():
                    # Повторяем команду после переподключения
                    try:
                        return func(*args, **kwargs)
                    except Exception as retry_error:
                        logger.error(f"Ошибка после переподключения: {retry_error}")
                        raise retry_error
                else:
                    raise e
            else:
                raise e

    def _try_reconnect(self, max_attempts: int = 3) -> bool:
        """
        Пытается переподключиться к профилю через Browser Vision API.
        Возвращает True если удалось восстановить соединение.
        """
        print("\n🔄 Попытка переподключения к профилю...")
        logger.info("Попытка переподключения к профилю")

        if not self.id_value:
            print("❌ ID профиля не указан, переподключение невозможно")
            return False

        try:
            # Импортируем API клиент
            from api_client import BrowserVisionClient
            from config import FOLDER_ID

            client = BrowserVisionClient(debug=False)

            for attempt in range(1, max_attempts + 1):
                print(f"   Попытка {attempt}/{max_attempts}...")

                # Проверяем, запущен ли профиль
                profile = client.get_profile_by_id(FOLDER_ID, self.id_value)
                if not profile:
                    print(f"   ❌ Профиль {self.id_value} не найден")
                    continue

                if not profile.get("running"):
                    print("   ⚠️ Профиль не запущен, пытаемся запустить...")
                    # Генерируем новый порт
                    from profile_creator import ProfileCreator

                    new_port = ProfileCreator.generate_cdp_port()

                    start_result = client.start_profile(
                        FOLDER_ID, self.id_value, port=new_port
                    )
                    if start_result:
                        actual_port = start_result.get("port") or new_port
                        print(f"   ✅ Профиль запущен на порту {actual_port}")

                        # Ждём доступности порта
                        import socket
                        import time

                        for wait_attempt in range(30):
                            try:
                                sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                                sock.settimeout(1)
                                result = sock.connect_ex(("127.0.0.1", actual_port))
                                sock.close()
                                if result == 0:
                                    print(f"   ✅ Порт {actual_port} доступен")
                                    break
                            except Exception:
                                pass
                            time.sleep(1)
                        else:
                            print(
                                f"   ⚠️ Порт {actual_port} не стал доступен за 30 сек"
                            )
                            continue

                        # Переподключаем Selenium
                        try:
                            options = Options()
                            options.add_experimental_option(
                                "debuggerAddress", f"127.0.0.1:{actual_port}"
                            )
                            service = Service(
                                r"C:\chromedriver_148\chromedriver-win64\chromedriver.exe"
                            )

                            new_driver = webdriver.Chrome(
                                service=service, options=options
                            )
                            self.driver = new_driver
                            self.wait = WebDriverWait(new_driver, 20)

                            print(f"   ✅ Selenium переподключён к порту {actual_port}")
                            logger.info(f"Selenium переподключён к порту {actual_port}")
                            return True

                        except Exception as e:
                            print(f"   ❌ Не удалось переподключить Selenium: {e}")
                            logger.error(f"Ошибка переподключения Selenium: {e}")
                            continue
                    else:
                        print("   ❌ Не удалось запустить профиль")
                        continue
                else:
                    # Профиль запущен, но сессия потеряна
                    print("   ⚠️ Профиль запущен, но сессия потеряна")
                    print("   💡 Попробуйте остановить и перезапустить профиль вручную")
                    return False

            print("❌ Все попытки переподключения исчерпаны")
            return False

        except Exception as e:
            logger.error(f"Ошибка при переподключении: {e}")
            print(f"❌ Ошибка при переподключении: {e}")
            return False

    # ================== ЗАГРУЗКА ФОТО ==================
    def upload_photo(self, photo_path: str, max_retries: int = 3) -> bool:
        if not os.path.isfile(photo_path):
            logger.warning(f"Файл не найден: {photo_path}")
            print(f"⚠️  Файл не найден: {photo_path}")
            return False

        for attempt in range(max_retries):
            if not os.path.isfile(photo_path):
                return False

            try:
                print(f"\n🔄 Попытка загрузки {attempt + 1}/{max_retries}")
                logger.info(
                    f"Попытка загрузки {attempt + 1}/{max_retries}: {photo_path}"
                )
                self._random_delay(3, 7, "подготовка перед загрузкой")

                result = self._do_upload(photo_path)

                if result["success"]:
                    print("✅ Фото успешно загружено!")
                    logger.info(f"Фото успешно загружено: {photo_path}")
                    self._random_delay(2, 4, "после успешной загрузки")
                    self._close_upload_modal()
                    return True

                error_type = result.get("type", "unknown")
                if error_type == "rate_limit":
                    logger.warning(f"Лимит загрузок для файла: {photo_path}")
                    print("⏳ Лимит загрузок. Ждём 10 минут...")
                    self._random_delay(3600, 7200, "лимит загрузок")
                    continue
                elif error_type == "duplicate":
                    logger.info(f"Фото уже существует: {photo_path}")
                    print("⚠️  Фото уже существует. Пропускаем.")
                    return False
                elif error_type == "quality":
                    logger.warning(f"Фото не прошло проверку качества: {photo_path}")
                    print("⚠️  Фото не прошло проверку качества. Пропускаем.")
                    return False
                else:
                    logger.error(f"Ошибка загрузки: {result.get('error')}")
                    print(f"❌ Ошибка: {result.get('error')}. Повтор...")
                    self._random_delay(10, 15, "перед повтором")
                    continue

            except Exception as e:
                self._log_error(
                    f"Ошибка загрузки (попытка {attempt + 1}): {e}", exception=e
                )
                try:
                    self._close_upload_modal()
                except Exception:
                    pass
                if attempt < max_retries - 1:
                    self._random_delay(10, 20, "перед повтором после ошибки")
                    continue
                raise

        return False

    def _do_upload(self, photo_path: str) -> dict:
        # ШАГ 1: ОТКРЫТИЕ МОДАЛЬНОГО ОКНА
        for attempt in range(3):
            try:
                # 🆕 ПЕРЕД КАЖДОЙ ПОПЫТКОЙ — проверяем, что мы в галерее
                if not self._ensure_on_gallery():
                    logger.warning("Не удалось вернуться в галерею, пробуем заново...")
                    print("⚠️  Не удалось вернуться в галерею, пробуем заново...")
                    self.go_to_photo_section()

                self._random_delay(2, 4, "переход в галерею")

                upload_btn = self.wait.until(
                    EC.presence_of_element_located(
                        (
                            By.CSS_SELECTOR,
                            "a.button.button_green[href='/photo_uploader/new']",
                        )
                    )
                )
                self.driver.execute_script("arguments[0].click();", upload_btn)
                print("✅ Нажата кнопка 'Загрузить фото'")
                logger.debug("Нажата кнопка 'Загрузить фото'")

                self._wait_for_uploader_script()
                self._random_delay(1.5, 3, "инициализация загрузчика")

                try:
                    WebDriverWait(self.driver, 10).until(
                        lambda d: "photo_uploader/new" in d.current_url
                    )
                    print(f"✅ URL изменился на загрузчик: {self.driver.current_url}")
                except TimeoutException:
                    self.wait.until(
                        EC.presence_of_element_located(
                            (
                                By.CSS_SELECTOR,
                                ".arcticmodal-container, #fileupload_master",
                            )
                        )
                    )

                self.wait.until(
                    EC.presence_of_element_located(
                        (By.CSS_SELECTOR, "#fileupload_master")
                    )
                )
                print("✅ Модальное окно открыто и готово")
                logger.info("Модальное окно загрузки открыто")
                break

            except TimeoutException as e:
                logger.warning(
                    f"Модальное окно не появилось (попытка {attempt + 1}/3): {e}"
                )
                print(f"⚠️  Модальное окно не появилось (попытка {attempt + 1}/3)")
                if attempt < 2:
                    # 🆕 Возвращаемся в галерею по сохранённому URL
                    if self._gallery_url:
                        print(f"🔄 Возвращаемся в галерею: {self._gallery_url}")
                        try:
                            self.driver.get(self._gallery_url)
                        except WebDriverException:
                            self.driver.refresh()
                    else:
                        self.driver.refresh()
                    self._random_delay(3, 5, "после обновления")
                    continue
                else:
                    self._log_error(
                        "Не удалось открыть модальное окно после 3 попыток", exception=e
                    )
                    raise Exception("Не удалось открыть модальное окно после 3 попыток")

        # ШАГ 2: ОТПРАВКА ФАЙЛА
        file_input = None
        for attempt in range(3):
            try:
                file_input = self.driver.execute_script(
                    "return document.querySelector('#fileupload_master');"
                )
                if not file_input:
                    file_input = self._find_file_input()
                if not file_input:
                    self._random_delay(1, 2, "поиск инпута")
                    continue

                self._make_input_visible(file_input)
                abs_path = os.path.abspath(photo_path)
                self._random_delay(0.5, 1.5, "перед отправкой файла")
                file_input.send_keys(abs_path)
                print(f"📤 Файл {os.path.basename(photo_path)} отправлен")
                logger.info(f"Файл отправлен: {photo_path}")
                break

            except Exception as e:
                logger.warning(f"Ошибка отправки (попытка {attempt + 1}/3): {e}")
                print(f"⚠️  Ошибка отправки (попытка {attempt + 1}/3): {e}")
                self._random_delay(1, 2, "повтор отправки")
                continue

        # ШАГ 3: ОЖИДАНИЕ
        print("⏳ Ожидание после отправки файла...")
        self._random_delay(8, 13, "загрузка файла на сервер")

        # ШАГ 4: ПРОВЕРКА URL
        current_url = self.driver.current_url
        print(f"🔍 Текущий URL: {current_url}")

        if "photos/list" in current_url or "gallery" in current_url:
            print("✅ URL изменился на галерею - фото загружено успешно!")
            logger.info("URL изменился на галерею - фото загружено успешно")
            self._random_delay(2, 4, "поиск кнопки Сохранить")

            save_btn = None
            save_selectors = [
                "#crop_action > input.button.button_green",
                "input.button_green[name='commit']",
                ".photos_second_step_action input.button_green",
                "input[value='Сохранить']",
            ]

            for selector in save_selectors:
                try:
                    save_btn = WebDriverWait(self.driver, 5).until(
                        EC.presence_of_element_located((By.CSS_SELECTOR, selector))
                    )
                    if save_btn and save_btn.is_displayed() and save_btn.is_enabled():
                        break
                except:
                    continue

            if save_btn:
                self._random_delay(0.5, 1.5, "перед нажатием Сохранить")
                self.driver.execute_script("arguments[0].click();", save_btn)
                print("✅ Кнопка 'Сохранить' нажата")
                self._random_delay(2, 4, "после сохранения")

            self._close_upload_modal()
            self.driver.refresh()
            self._random_delay(2, 4, "после обновления")

            return {"success": True, "error": "", "type": "success"}

        else:
            logger.warning("URL не изменился - проверка ошибок...")
            print("⚠️  URL не изменился - проверка ошибок...")
            self._random_delay(1.5, 3, "проверка ошибок")

            try:
                error_items = self.driver.find_elements(
                    By.CSS_SELECTOR, ".upload__item_err"
                )
                for item in error_items:
                    text = item.text.lower()
                    if "слишком часто" in text or "10 минут" in text:
                        return {
                            "success": False,
                            "error": item.text,
                            "type": "rate_limit",
                        }
                    if "уже существует" in text or "дубликат" in text:
                        return {
                            "success": False,
                            "error": item.text,
                            "type": "duplicate",
                        }
                    if "качество" in text or "плохо" in text:
                        return {"success": False, "error": item.text, "type": "quality"}
            except Exception as e:
                logger.error(f"Ошибка при проверке: {e}")

            self._random_delay(4, 7, "дополнительное ожидание")

            current_url = self.driver.current_url
            if "photos/list" in current_url or "gallery" in current_url:
                self._close_upload_modal()
                self.driver.refresh()
                self._random_delay(2, 4, "после обновления")
                return {"success": True, "error": "", "type": "success"}

            self.driver.refresh()
            self._random_delay(2, 4, "после обновления")

            try:
                photos = self.driver.find_elements(By.CSS_SELECTOR, "li.gallery__item")
                if photos:
                    logger.info(
                        f"После обновления найдено {len(photos)} фото в галерее"
                    )
                    return {"success": True, "error": "", "type": "success"}
            except:
                pass

            logger.error("URL не изменился после загрузки")
            return {"success": False, "error": "URL не изменился", "type": "unknown"}

    def _find_file_input(self):
        methods = [
            lambda: self.driver.find_element(By.CSS_SELECTOR, "#fileupload_master"),
            lambda: self.driver.execute_script(
                "return document.querySelector('#fileupload_master');"
            ),
            lambda: self.driver.find_element(By.CSS_SELECTOR, "input[name='files[]']"),
        ]
        for method in methods:
            try:
                element = method()
                if element:
                    self._make_input_visible(element)
                    return element
            except Exception:
                continue
        return None

    def _make_input_visible(self, element):
        self.driver.execute_script(
            """
            arguments[0].style.display = 'block';
            arguments[0].style.visibility = 'visible';
            arguments[0].style.opacity = '1';
            arguments[0].style.position = 'relative';
            arguments[0].style.zIndex = '9999';
            arguments[0].setAttribute('style', 'display: block !important; visibility: visible !important; opacity: 1 !important; position: relative !important; z-index: 9999 !important;');
        """,
            element,
        )
        time.sleep(0.5)

    def _close_upload_modal(self):
        for selector in [".modal__close.arcticmodal-close", ".arcticmodal-close"]:
            try:
                btn = self.driver.find_element(By.CSS_SELECTOR, selector)
                if btn.is_displayed():
                    btn.click()
                    self._random_delay(0.5, 1, "закрытие модалки")
                    return
            except:
                pass
        try:
            self.driver.find_element(By.TAG_NAME, "body").send_keys(Keys.ESCAPE)
        except:
            pass

    # ================== УДАЛЕНИЕ ФОТО ==================
    def delete_photo(self, photo_element) -> bool:
        try:
            photo_url = self._get_photo_link(photo_element)
            if not photo_url:
                logger.error("Не удалось получить ссылку на фото")
                return False

            print(f"🗑️  Открываем страницу фото: {photo_url}")
            logger.info(f"Открываем страницу фото: {photo_url}")
            current_url = self.driver.current_url
            self.driver.get(photo_url)
            self._random_delay(2, 4, "загрузка страницы фото")

            delete_btn = self.wait.until(
                EC.presence_of_element_located(
                    (
                        By.CSS_SELECTOR,
                        "a.button.button_yellow.modal__action-blocked[data-method='delete']",
                    )
                )
            )
            self._random_delay(0.5, 1.5, "перед нажатием Удалить")
            self.driver.execute_script("arguments[0].click();", delete_btn)
            print("Нажата кнопка 'Удалить'")

            self._random_delay(1, 2, "ожидание модалки")

            try:
                confirm_btn = WebDriverWait(self.driver, 5).until(
                    EC.presence_of_element_located(
                        (
                            By.CSS_SELECTOR,
                            "#arcticmodalDialog > div.modal__body > div > div > a.button.button_yellow.arcticmodal-close.confirm_action",
                        )
                    )
                )
                self._random_delay(0.3, 1, "перед подтверждением")
                self.driver.execute_script("arguments[0].click();", confirm_btn)
                print("✅ Подтверждение удаления нажато")
            except TimeoutException:
                try:
                    confirm_btn = WebDriverWait(self.driver, 3).until(
                        EC.element_to_be_clickable(
                            (
                                By.CSS_SELECTOR,
                                "a.button.button_yellow.arcticmodal-close.confirm_action",
                            )
                        )
                    )
                    self.driver.execute_script("arguments[0].click();", confirm_btn)
                except TimeoutException:
                    self.driver.find_element(By.TAG_NAME, "body").send_keys(Keys.ENTER)

            self._random_delay(2, 4, "ожидание удаления")

            # 🆕 Возвращаемся в галерею по сохранённому URL
            if self._gallery_url:
                self.driver.get(self._gallery_url)
            else:
                self.driver.get(current_url)
            self.wait.until(
                EC.presence_of_element_located((By.CSS_SELECTOR, "ul.gallery"))
            )
            self._random_delay(1, 2, "возврат в галерею")
            logger.info("Фото успешно удалено")
            self._random_delay(30, 70, "Посидим после удаления")
            return True

        except Exception as e:
            self._log_error(f"Ошибка при удалении фото: {e}", exception=e)
            try:
                if self._gallery_url:
                    self.driver.get(self._gallery_url)
                else:
                    self.driver.get(current_url)
            except:
                pass
            return False

    # ================== ОСНОВНОЙ МОНИТОРИНГ ==================
    def monitor_photos(self, photo_paths: List[str]):
        try:
            logger.info(
                f"Начало мониторинга фотографий. Всего файлов: {len(photo_paths)}"
            )
            queue = list(photo_paths)

            initial_count = len(queue)
            queue = [p for p in queue if os.path.isfile(p)]
            removed_count = initial_count - len(queue)
            if removed_count > 0:
                logger.warning(
                    f"Удалено из очереди {removed_count} несуществующих файлов"
                )
                print(f"⚠️  Удалено из очереди {removed_count} несуществующих файлов")

            if not queue:
                if self.id_value:
                    # 🆕 Создаём файл-флаг и ждём сигнала из Telegram
                    if self._wait_for_photo_replenish():
                        # Перечитываем папку
                        photo_folder = self._get_photo_folder()
                        if photo_folder:
                            from profile_script.photo_path import get_photo_path

                            new_photos = get_photo_path(photo_folder)
                            if new_photos:
                                queue = list(new_photos)
                                print(
                                    f"🔄 Продолжаем работу с {len(queue)} новыми фото"
                                )
                            else:
                                print("📋 Папка пуста. Завершаем.")
                                return
                        else:
                            print("📋 Папка не найдена. Завершаем.")
                            return
                    else:
                        print("📋 Ожидание прервано. Завершаем.")
                        return
                else:
                    print("📋 Очередь пуста.")
                    return

            photo_index = 0
            self.go_to_photo_section()
            max_iterations = 60
            iteration = 0

            while iteration < max_iterations and queue:
                iteration += 1
                print(f"\n{'=' * 50}")
                print(f"--- Итерация {iteration} ---")
                print(f"{'=' * 50}")
                logger.info(f"=== Итерация {iteration} ===")

                # 🆕 Проверяем, жива ли сессия
                if not self._is_session_alive():
                    print("\n❌ Сессия Selenium потеряна")
                    logger.error("Сессия потеряна в начале итерации")

                    if self._try_reconnect():
                        print("✅ Соединение восстановлено")
                        # Возвращаемся в галерею
                        if self._gallery_url:
                            try:
                                self.driver.get(self._gallery_url)
                                time.sleep(2)
                            except Exception as e:
                                logger.error(f"Не удалось вернуться в галерею: {e}")
                                break
                    else:
                        print(
                            "❌ Не удалось восстановить соединение. Завершаем работу."
                        )
                        logger.error("Не удалось восстановить соединение")
                        break

                if iteration > 1:
                    self._random_delay(5, 15, "между итерациями")

                # 🆕 ПЕРЕД каждой итерацией проверяем, что мы в галерее
                if not self._ensure_on_gallery():
                    print("\n❌ Невозможно вернуться в галерею. Завершаем работу.")
                    logger.error("Невозможно вернуться в галерею")
                    break

                try:
                    self.driver.refresh()
                except WebDriverException as e:
                    logger.error(f"Ошибка refresh: {e}")
                    print("⚠️  Ошибка refresh, пробуем вернуться в галерею...")
                    self.driver.get(self._gallery_url or "https://tabor.ru/photos/list")
                    time.sleep(2)

                self._random_delay(2, 4, "после обновления")

                photos = self._get_gallery_photos()

                if not photos:
                    if queue:
                        queue = [p for p in queue if os.path.isfile(p)]
                        if not queue:
                            break

                        photo_path = random.choice(queue)
                        print(
                            f"\n📸 Галерея пуста. Загружаем: {os.path.basename(photo_path)}"
                        )
                        logger.info(f"Галерея пуста. Загружаем: {photo_path}")

                        if photo_index > 0:
                            self._anti_ban_delay()

                        self._ensure_on_gallery()
                        self._random_delay(2, 5, "подготовка перед загрузкой")

                        success = self.upload_photo(photo_path)

                        if success:
                            self._delete_photo_file(photo_path)
                            queue.remove(photo_path)
                            photo_index += 1
                            print(
                                f"✅ Загружено {photo_index} фото. Осталось: {len(queue)}"
                            )
                            logger.info(
                                f"Загружено {photo_index} фото. Осталось: {len(queue)}"
                            )
                            self._random_delay(3, 8, "после загрузки")
                        else:
                            logger.warning(f"Загрузка не удалась: {photo_path}")
                            print("❌ Загрузка не удалась.")
                            queue.remove(photo_path)
                            self._random_delay(2, 5, "после неудачной загрузки")
                        continue
                    else:
                        if self.id_value:
                            if self._wait_for_photo_replenish():
                                photo_folder = self._get_photo_folder()
                                if photo_folder:
                                    from profile_script.photo_path import get_photo_path

                                    new_photos = get_photo_path(photo_folder)
                                    if new_photos:
                                        queue = list(new_photos)
                                        continue
                            break
                        break

                print(f"📸 Найдено фото: {len(photos)}")
                logger.info(f"Найдено фото: {len(photos)}")
                self._random_delay(1, 3, "анализ галереи")
                any_processed = False

                for i, photo in enumerate(photos):
                    try:
                        status = self._get_photo_status(photo)
                    except Exception as e:
                        logger.error(f"Ошибка получения статуса фото {i}: {e}")
                        print(f"⚠️  Ошибка получения статуса фото {i}: {e}")
                        break

                    print(f"Фото {i + 1}: статус '{status}'")
                    logger.debug(f"Фото {i + 1}: статус '{status}'")

                    if status == self.STATUS_MAIN:
                        self._random_delay(1, 2, "проверка главной")
                        decision = (
                            input("✅ Это правильная главная? (да/нет): ")
                            .strip()
                            .lower()
                        )
                        if decision in ("да", "yes", "y"):
                            print("✅ Главная принята. Завершаем.")
                            logger.info("Главная принята. Завершаем работу.")
                            _write_tg_event(
                                "main_photo",
                                f"✅ На фото появился статус <b>Главная</b> для ID <code>{self.id_value or 'N/A'}</code>.",
                                self.id_value,
                            )
                            return
                        else:
                            print("🗑️  Удаляем неподходящую главную.")
                            logger.info("Удаляем неподходящую главную")
                            self._random_delay(1, 3, "перед удалением")
                            if self.delete_photo(photo):
                                self._random_delay(2, 4, "после удаления")
                                any_processed = True
                            break

                    elif status == self.STATUS_BLOCKED:
                        print("⚠️  Заблокированное фото. Удаляем.")
                        logger.info("Заблокированное фото. Удаляем.")
                        self._random_delay(1, 3, "перед удалением")
                        if self.delete_photo(photo):
                            self._random_delay(2, 4, "после удаления")
                            self._clear_upload_state()
                            any_processed = True
                        break

                    else:
                        print("⏳ Фото на модерации.")
                        logger.debug("Фото на модерации")

                if not any_processed:
                    wait_time = random.uniform(50, 70)
                    print(f"⏳ Ничего не сделано, ждём {wait_time:.0f} секунд...")
                    logger.info(f"Ничего не сделано, ждём {wait_time:.0f} секунд")
                    time.sleep(wait_time)
                else:
                    print("🔄 Были изменения, обновляем страницу...")
                    logger.info("Были изменения, обновляем страницу")
                    self._random_delay(2, 5, "после изменений")

            if not queue:
                print("📋 Все фото обработаны.")
                logger.info("Все фото обработаны")
            else:
                print("⏰ Таймаут мониторинга.")
                logger.warning("Таймаут мониторинга")

        except Exception as e:
            self._log_error(f"Критическая ошибка в monitor_photos: {e}", exception=e)
            _write_tg_event(
                "error",
                f"❌ Ошибка tebor для ID <code>{self.id_value or 'N/A'}</code>: <code>{str(e)}</code>",
                self.id_value,
            )
            raise


# ================== ЗАПУСК ==================
def start_connect(LOGIN, PASSWORD, PORT_NUMBER, ID_VALUE=None):
    options = Options()
    options.add_experimental_option("debuggerAddress", f"127.0.0.1:{PORT_NUMBER}")
    service = Service(r"C:\chromedriver_148\chromedriver-win64\chromedriver.exe")
    driver = webdriver.Chrome(service=service, options=options)
    driver.get("https://tabor.ru")
    print("✅ Selenium подключился, текущий URL:", driver.current_url)

    try:
        uploader = TaborPhotoUploader(driver, LOGIN, PASSWORD, id_value=ID_VALUE)

        # 🆕 АВТОПРОВЕРКА: уже авторизован или нет?
        if uploader.is_already_logged_in(timeout=10):
            print("🔑 Профиль уже авторизован")
        elif LOGIN and PASSWORD:
            print("🔐 Требуется авторизация...")
            uploader.login()
            time.sleep(2)
        else:
            print("❌ Профиль не авторизован и нет логина/пароля. Завершаем.")
            return

        # Переходим в галерею
        uploader.go_to_photo_section()

        # Запускаем мониторинг
        uploader.monitor_photos(PHOTO_PATHS)

    except Exception as e:
        print(f"Критическая ошибка: {e}")
        import traceback

        traceback.print_exc()
    finally:
        input("Нажмите Enter для закрытия браузера...")
        driver.quit()


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument("--port", type=int, required=True)
    parser.add_argument("--login", default=os.getenv("TABOR_LOGIN"))
    parser.add_argument("--password", default=os.getenv("TABOR_PASSWORD"))
    parser.add_argument("--id", type=str, default=os.getenv("TABOR_ID"))

    args = parser.parse_args()
    start_connect(args.login, args.password, args.port, args.id)
