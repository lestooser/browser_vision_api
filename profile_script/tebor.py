import os
import random
import time
from typing import List

from dotenv import load_dotenv
from selenium import webdriver
from selenium.common.exceptions import NoSuchElementException, TimeoutException
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait

from profile_script.photo_path import get_photo_path

load_dotenv()
PHOTO_PATHS = get_photo_path(os.getenv("FOLDER_PHOTO_PATH"))


class TaborPhotoUploader:
    STATUS_MAIN = "Главная"
    STATUS_BLOCKED = "Заблокировано"
    STATUS_PENDING = ""

    def __init__(self, driver, login: str, password: str, id_value: str = None):
        self.driver = driver
        self.wait = WebDriverWait(driver, 20)
        self._login = login
        self._password = password
        self.id_value = id_value
        self._turbolinks_disabled = False
        self._gallery_url = None  # 🆕 Сохраняем точный URL галереи

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
        time.sleep(delay)

    # ================== ЗАЩИТА ОТ БАНА: ИМИТАЦИЯ ЧЕЛОВЕКА ==================
    def _simulate_human_activity(self):
        """Имитирует человеческую активность между загрузками."""
        print("\n👤 Имитация человеческой активности...")

        actions = [
            (
                "скролл страницы",
                lambda: self.driver.execute_script(
                    "window.scrollBy(0, {});".format(random.randint(100, 400))
                ),
            ),
            (
                "скролл вверх",
                lambda: self.driver.execute_script(
                    "window.scrollBy(0, {});".format(random.randint(-300, -100))
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

        print(f"\n⏸️  Пауза между загрузками: {base_delay:.0f} секунд (защита от бана)")
        print("   (человек выбирает следующее фото, пьёт кофе, думает)")

        elapsed = 0
        while elapsed < base_delay:
            chunk = min(random.uniform(5, 15), base_delay - elapsed)
            time.sleep(chunk)
            elapsed += chunk

            if int(elapsed) % 20 < 5:
                self._simulate_human_activity()

        print("✅ Пауза завершена, можно загружать следующее фото\n")

    # ================== ОТКЛЮЧЕНИЕ TURBOLINKS ==================
    def _disable_turbolinks(self):
        """Отключает Turbolinks для корректной навигации и очистки."""
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
        except Exception as e:
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
            WebDriverWait(self.driver, 10).until(
                lambda d: d.execute_script("""
                    return document.querySelector('#fileupload_master') !== null ||
                           document.querySelector('.arcticmodal-container') !== null ||
                           document.querySelector('#crop_action') !== null;
                """)
            )
            print("✅ Скрипт загрузчика загружен")
        except TimeoutException:
            print("⚠️  Скрипт загрузчика не загрузился за 10 сек")

    # ================== 🆕 ПРОВЕРКА И ВОЗВРАТ В ГАЛЕРЕЮ ==================
    def _ensure_on_gallery(self) -> bool:
        """
        Проверяет, что мы на точном URL галереи.
        Если нет — возвращает на сохранённый URL.
        Возвращает True если успех.
        """
        if not self._gallery_url:
            print("⚠️  URL галереи не сохранён, переходим в галерею...")
            self.go_to_photo_section()
            return True

        current_url = self.driver.current_url
        print(f"🔍 Проверка URL: {current_url}")
        print(f"📍 Ожидаемый URL: {self._gallery_url}")

        # Проверяем точное совпадение URL (без query параметров)
        current_base = current_url.split("?")[0].split("#")[0]
        gallery_base = self._gallery_url.split("?")[0].split("#")[0]

        if current_base != gallery_base:
            print("⚠️  Не на странице галереи! Возвращаемся...")
            try:
                self.driver.get(self._gallery_url)
                time.sleep(2)
                self.wait.until(
                    EC.presence_of_element_located((By.CSS_SELECTOR, "ul.gallery"))
                )
                print("✅ Вернулись в галерею")
                return True
            except Exception as e:
                print(f"❌ Не удалось вернуться в галерею: {e}")
                return False

        print("✅ Мы на странице галереи")
        return True

    # ================== ОЧИСТКА СОСТОЯНИЯ ЗАГРУЗОК ==================
    def _clear_upload_state(self):
        """Очистка cookies/storage с учётом Turbolinks."""
        print("\n🧹 === Очистка состояния загрузок ===")

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
                    print(f"  ⚠️  Не удалось удалить cookie '{cookie['name']}': {e}")
            else:
                kept_cookies.append(cookie["name"])

        if deleted_cookies:
            print(
                f"  🗑️  Удалено cookies ({len(deleted_cookies)}): {', '.join(deleted_cookies)}"
            )
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
                print(
                    f"  🗑️  Очищено из storage ({len(cleared_ls)}): {', '.join(cleared_ls)}"
                )
            else:
                print("  ℹ️  Storage загрузок пуст")
        except Exception as e:
            print(f"  ⚠️  Ошибка очистки storage: {e}")

        print("  🔄 Полная перезагрузка страницы (hard reload)...")
        try:
            self.driver.execute_script("window.location.reload(true);")
            time.sleep(3)
        except Exception:
            self.driver.refresh()
            time.sleep(2)

        print("🧹 === Очистка завершена ===\n")

    # ================== АВТОРИЗАЦИЯ ==================
    def login(self) -> bool:
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
        return True

    def go_to_photo_section(self):
        """Переход в раздел 'Фото' и сохранение URL галереи."""
        self._disable_turbolinks()

        photo_link = self.wait.until(
            EC.element_to_be_clickable((By.CSS_SELECTOR, "a.user__gallery__link_photo"))
        )
        photo_link.click()
        self.wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, "ul.gallery")))
        self._random_delay(1.5, 3, "загрузка галереи")

        # 🆕 СОХРАНЯЕМ ТОЧНЫЙ URL ГАЛЕРЕИ
        self._gallery_url = self.driver.current_url
        print(f"📍 URL галереи сохранён: {self._gallery_url}")

        csrf = self._get_csrf_token()
        if csrf:
            print(f"🔑 CSRF token получен: {csrf[:12]}...")

    def _trigger_main_processing(self):
        if not self.id_value:
            print("❌ Ошибка: Не указан ID для запроса к main.py")
            return False

        print(f"\n🔄 Отправка запроса в main для ID: {self.id_value} (итераций: 5)...")

        try:
            import sys

            sys.path.insert(0, r"D:\python\selenium-test")
            from main import start_uniq

            result = start_uniq(
                id_path=self.id_value,
                iter_count=5,
                progress_callback=lambda i, t: print(
                    f"📊 Прогресс main: {i}/{t} ({int(i / t * 100)}%)"
                ),
            )

            if result is True:
                print("✅ Запрос к main успешно выполнен.")
                return True
            else:
                print(f"❌ start_uniq вернул {result}, а не True")
                return False
        except Exception as e:
            print(f"❌ Ошибка при выполнении main.py: {e}")
            return False

    # ================== РАБОТА С ГАЛЕРЕЕЙ ==================
    def _get_gallery_photos(self) -> list:
        return self.driver.find_elements(By.CSS_SELECTOR, "li.gallery__item")

    def _get_photo_status(self, photo_element) -> str:
        try:
            status_elem = photo_element.find_element(
                By.CSS_SELECTOR, "span.meta__item__lbl"
            )
            return status_elem.text.strip()
        except NoSuchElementException:
            return ""

    def _get_photo_link(self, photo_element) -> str:
        link = photo_element.find_element(By.CSS_SELECTOR, "a.gallery__img-link")
        return link.get_attribute("href")

    def _delete_photo_file(self, photo_path: str):
        try:
            if os.path.isfile(photo_path):
                os.remove(photo_path)
                print(f"🗑️  Файл {os.path.basename(photo_path)} удалён с диска.")
        except Exception as e:
            print(f"⚠️  Не удалось удалить файл {photo_path}: {e}")

    # ================== ЗАГРУЗКА ФОТО ==================
    def upload_photo(self, photo_path: str, max_retries: int = 3) -> bool:
        if not os.path.isfile(photo_path):
            print(f"⚠️  Файл не найден: {photo_path}")
            return False

        for attempt in range(max_retries):
            if not os.path.isfile(photo_path):
                return False

            try:
                print(f"\n🔄 Попытка загрузки {attempt + 1}/{max_retries}")
                self._random_delay(3, 7, "подготовка перед загрузкой")

                result = self._do_upload(photo_path)

                if result["success"]:
                    print("✅ Фото успешно загружено!")
                    self._random_delay(2, 4, "после успешной загрузки")
                    self._close_upload_modal()
                    return True

                error_type = result.get("type", "unknown")
                if error_type == "rate_limit":
                    print("⏳ Лимит загрузок. Ждём 10 минут...")
                    self._random_delay(610, 630, "лимит загрузок")
                    continue
                elif error_type == "duplicate":
                    print("⚠️  Фото уже существует. Пропускаем.")
                    return False
                elif error_type == "quality":
                    print("⚠️  Фото не прошло проверку качества. Пропускаем.")
                    return False
                else:
                    print(f"❌ Ошибка: {result.get('error')}. Повтор...")
                    self._random_delay(10, 15, "перед повтором")
                    continue

            except Exception as e:
                print(f"⚠️  Ошибка загрузки: {e}")
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
                break

            except TimeoutException as e:
                print(f"⚠️  Модальное окно не появилось (попытка {attempt + 1}/3): {e}")
                if attempt < 2:
                    # 🆕 Вместо refresh — возвращаемся в галерею по сохранённому URL
                    if self._gallery_url:
                        print(f"🔄 Возвращаемся в галерею: {self._gallery_url}")
                        self.driver.get(self._gallery_url)
                    else:
                        self.driver.refresh()
                    self._random_delay(3, 5, "после обновления")
                    continue
                else:
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
                break

            except Exception as e:
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
                print(f"⚠️  Ошибка при проверке: {e}")

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
                    return {"success": True, "error": "", "type": "success"}
            except:
                pass

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
                return False

            print(f"🗑️  Открываем страницу фото: {photo_url}")
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

            self.driver.get(current_url)
            self.wait.until(
                EC.presence_of_element_located((By.CSS_SELECTOR, "ul.gallery"))
            )
            self._random_delay(1, 2, "возврат в галерею")
            return True

        except Exception as e:
            print(f"❌ Ошибка при удалении фото: {e}")
            try:
                self.driver.get(current_url)
            except:
                pass
            return False

    # ================== ОСНОВНОЙ МОНИТОРИНГ ==================
    def monitor_photos(self, photo_paths: List[str]):
        queue = list(photo_paths)

        initial_count = len(queue)
        queue = [p for p in queue if os.path.isfile(p)]
        removed_count = initial_count - len(queue)
        if removed_count > 0:
            print(f"⚠️  Удалено из очереди {removed_count} несуществующих файлов")
        if not queue:
            if self.id_value:
                response = (
                    input(
                        "📸 Фотографии кончились, отправить запрос на пополнение? (да/нет): "
                    )
                    .strip()
                    .lower()
                )
                if response in ("да", "yes", "y", "д"):
                    if self._trigger_main_processing():
                        print("🔄 Запрос успешен.")
                    else:
                        return
                else:
                    print("📋 Запрос отменен.")
            else:
                print("📋 Очередь пуста.")
            return

        photo_index = 0
        self.go_to_photo_section()  # 🆕 Здесь сохраняется self._gallery_url
        max_iterations = 60
        iteration = 0

        while iteration < max_iterations and queue:
            iteration += 1
            print(f"\n{'=' * 50}")
            print(f"--- Итерация {iteration} ---")
            print(f"{'=' * 50}")

            if iteration > 1:
                self._random_delay(5, 15, "между итерациями")

            # 🆕 ПЕРЕД каждой итерацией проверяем, что мы в галерее
            self._ensure_on_gallery()

            self.driver.refresh()
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

                    if photo_index > 0:
                        self._anti_ban_delay()

                    # 🆕 ПЕРЕД загрузкой — гарантируем, что мы в галерее
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
                        self._random_delay(3, 8, "после загрузки")
                    else:
                        print("❌ Загрузка не удалась.")
                        queue.remove(photo_path)
                        self._random_delay(2, 5, "после неудачной загрузки")
                    continue
                else:
                    if self.id_value:
                        response = (
                            input(
                                "📸 Фотографии кончились, отправить запрос? (да/нет): "
                            )
                            .strip()
                            .lower()
                        )
                        if response in ("да", "yes", "y", "д"):
                            self._trigger_main_processing()
                            break
                    break

            print(f"📸 Найдено фото: {len(photos)}")
            self._random_delay(1, 3, "анализ галереи")
            any_processed = False

            for i, photo in enumerate(photos):
                try:
                    status = self._get_photo_status(photo)
                except Exception as e:
                    print(f"⚠️  Ошибка получения статуса фото {i}: {e}")
                    break

                print(f"Фото {i + 1}: статус '{status}'")

                if status == self.STATUS_MAIN:
                    self._random_delay(1, 2, "проверка главной")
                    decision = (
                        input("✅ Это правильная главная? (да/нет): ").strip().lower()
                    )
                    if decision in ("да", "yes", "y"):
                        print("✅ Главная принята. Завершаем.")
                        return
                    else:
                        print("🗑️  Удаляем неподходящую главную.")
                        self._random_delay(1, 3, "перед удалением")
                        if self.delete_photo(photo):
                            self._random_delay(2, 4, "после удаления")
                            any_processed = True
                        break

                elif status == self.STATUS_BLOCKED:
                    print("⚠️  Заблокированное фото. Удаляем.")
                    self._random_delay(1, 3, "перед удалением")
                    if self.delete_photo(photo):
                        self._random_delay(2, 4, "после удаления")
                        self._clear_upload_state()
                        any_processed = True
                    break

                else:
                    print("⏳ Фото на модерации.")

            if not any_processed:
                wait_time = random.uniform(50, 70)
                print(f"⏳ Ничего не сделано, ждём {wait_time:.0f} секунд...")
                time.sleep(wait_time)
            else:
                print("🔄 Были изменения, обновляем страницу...")
                self._random_delay(2, 5, "после изменений")

        if not queue:
            print("📋 Все фото обработаны.")
        else:
            print("⏰ Таймаут мониторинга.")


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
        input("Подтвердите авторизацию и нажмите Enter...")
        time.sleep(2)
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
