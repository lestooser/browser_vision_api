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
    # Статусы фото (из наблюдений)
    STATUS_MAIN = "Главная"
    STATUS_BLOCKED = "Заблокировано"
    STATUS_PENDING = ""  # на модерации (нет метки)

    def __init__(self, driver, login: str, password: str, id_value: str = None):
        self.driver = driver
        self.wait = WebDriverWait(driver, 20)
        self._login = login
        self._password = password
        self.id_value = id_value

    # ================== АВТОРИЗАЦИЯ ==================
    def login(self) -> bool:
        """Авторизация с ручным обходом Turnstile."""
        self.driver.get("https://tabor.ru")

        login_btn = self.wait.until(
            EC.element_to_be_clickable((By.CSS_SELECTOR, "a[href='/signin']"))
        )
        login_btn.click()

        email_input = self.wait.until(
            EC.presence_of_element_located((By.ID, "session_user_login"))
        )
        email_input.send_keys(self._login)

        pass_input = self.driver.find_element(By.ID, "session_user_password")
        pass_input.send_keys(self._password)

        input("👉 Пройдите капчу 'Я не робот' и нажмите Enter...")

        submit_btn = self.driver.find_element(
            By.CSS_SELECTOR, "input[type='submit'][value='Войти']"
        )
        submit_btn.click()
        return True

    def go_to_photo_section(self):
        """
        Переход в раздел 'Фото' (галерею).
        Используем актуальный селектор из HTML.
        """
        photo_link = self.wait.until(
            EC.element_to_be_clickable((By.CSS_SELECTOR, "a.user__gallery__link_photo"))
        )
        photo_link.click()
        # Ждём, пока загрузится хотя бы контейнер галереи
        self.wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, "ul.gallery")))
        time.sleep(2)

    def _trigger_main_processing(self):
        """Вызывает логику из main.py для обработки фотографий."""
        if not self.id_value:
            print("❌ Ошибка: Не указан ID для запроса к main.py")
            return False

        print(f"\n🔄 Отправка запроса в main для ID: {self.id_value} (итераций: 5)...")

        try:
            import sys

            # 🆕 Используем insert(0, ...) для приоритета и r"" для raw string
            sys.path.insert(0, r"D:\python\selenium-test")

            print("🔧 Проверка: можем ли импортировать main?")
            from main import start_uniq

            print("✅ Импорт main успешен")

            # Запускаем обработку
            result = start_uniq(
                id_path=self.id_value,
                iter_count=5,
                progress_callback=lambda i, t: print(
                    f"📊 Прогресс main: {i}/{t} ({int(i / t * 100)}%)"
                ),
            )

            print(f"🔍 Результат вызова start_uniq: {repr(result)}")

            if result is True:
                print(
                    "✅ Запрос к main успешно выполнен. Папка download/extracted/ обновлена."
                )
                return True
            else:
                print(f"❌ start_uniq вернул {result}, а не True")
                return False

        except ImportError as e:
            print(f"❌ Ошибка импорта: {e}")
            print("💡 Убедитесь, что main.py находится в D:\\python\\selenium-test\\")
            return False
        except Exception as e:
            print(f"❌ Ошибка при выполнении main.py: {e}")
            import traceback

            traceback.print_exc()
            return False

    # ================== РАБОТА С ГАЛЕРЕЕЙ ==================
    def _get_gallery_photos(self) -> list:
        """Возвращает список всех элементов фото (li.gallery__item)."""
        return self.driver.find_elements(By.CSS_SELECTOR, "li.gallery__item")

    def _is_gallery_empty(self) -> bool:
        """Проверяет, пуста ли галерея."""
        return len(self._get_gallery_photos()) == 0

    def _get_photo_status(self, photo_element) -> str:
        """
        Возвращает текст статуса фото.
        Если статус отсутствует – возвращает пустую строку (означает "на модерации").
        """
        try:
            status_elem = photo_element.find_element(
                By.CSS_SELECTOR, "span.meta__item__lbl"
            )
            return status_elem.text.strip()
        except NoSuchElementException:
            return ""

    def _get_photo_link(self, photo_element) -> str:
        """Возвращает URL страницы фото (из a.gallery__img-link)."""
        link = photo_element.find_element(By.CSS_SELECTOR, "a.gallery__img-link")
        return link.get_attribute("href")

    def _delete_photo_file(self, photo_path: str):
        """Удаляет файл фото с диска, если он существует."""
        try:
            if os.path.isfile(photo_path):
                os.remove(photo_path)
                print(f"🗑️ Файл {os.path.basename(photo_path)} удалён с диска.")
            else:
                print(f"⚠️ Файл {os.path.basename(photo_path)} уже не существует.")
        except Exception as e:
            print(f"⚠️ Не удалось удалить файл {photo_path}: {e}")

    # ================== ЗАГРУЗКА ФОТО ==================
    def upload_photo(self, photo_path: str, max_retries: int = 3) -> bool:
        """
        Загрузка фотографии. Сначала пробует основной способ (через send_keys),
        если не получается – альтернативный (через клик по кнопке «Выбрать файл»).
        """
        # 📌 ПРОВЕРКА: файл существует?
        if not os.path.isfile(photo_path):
            print(f"⚠️ Файл не найден: {photo_path}")
            return False

        # Сначала пробуем основной способ
        for attempt in range(max_retries):
            # 📌 ПЕРЕПРОВЕРКА: перед каждой попыткой проверяем, существует ли файл
            if not os.path.isfile(photo_path):
                print(
                    f"⚠️ Файл {os.path.basename(photo_path)} был удалён другим процессом. Пропускаем."
                )
                return False

            try:
                print(
                    f"\n🔄 Попытка загрузки (основной способ) {attempt + 1}/{max_retries}"
                )
                result = self._do_upload(photo_path)

                if result["success"]:
                    print("✅ Фото успешно загружено!")
                    self._close_upload_modal()
                    return True

                error_type = result.get("type", "unknown")
                if error_type == "rate_limit":
                    print("⏳ Лимит загрузок. Ждём 10 минут...")
                    time.sleep(620)
                    continue
                elif error_type == "duplicate":
                    print("⚠️ Фото уже существует. Пропускаем.")
                    return False
                elif error_type == "quality":
                    print("⚠️ Фото не прошло проверку качества. Пропускаем.")
                    return False
                else:
                    print(f"❌ Ошибка: {result.get('error')}. Повтор через 5 сек...")
                    time.sleep(10)
                    continue

            except Exception as e:
                print(f"⚠️ Ошибка загрузки: {e}")
                try:
                    self._close_upload_modal()
                except Exception:
                    pass
                if attempt < max_retries - 1:
                    time.sleep(10)
                    continue
                raise

        return False

    def _do_upload(self, photo_path: str) -> dict:
        """
        Основной способ загрузки фото.
        Возвращает dict: {"success": bool, "error": str, "type": str}
        type может быть: "success", "rate_limit", "duplicate", "quality", "no_save_button", "unknown"
        """
        # ================== ШАГ 1: ОТКРЫТИЕ МОДАЛЬНОГО ОКНА ==================
        for attempt in range(3):
            try:
                # Проверяем, что мы в галерее
                if (
                    "photos" not in self.driver.current_url
                    and "gallery" not in self.driver.current_url
                ):
                    print("🔄 Не в галерее, переходим...")
                    self.go_to_photo_section()
                    time.sleep(2)

                # Кликаем по кнопке "Загрузить фото" через JS
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

                # 🆕 Ждём изменения URL на photo_uploader/new
                print("⏳ Ожидание открытия загрузчика...")
                try:
                    WebDriverWait(self.driver, 10).until(
                        lambda d: "photo_uploader/new" in d.current_url
                    )
                    print(f"✅ URL изменился на загрузчик: {self.driver.current_url}")
                except TimeoutException:
                    print("⚠️ URL не изменился, пробуем найти модалку по элементам...")
                    # Fallback — ждём появления элементов модалки
                    self.wait.until(
                        EC.presence_of_element_located(
                            (
                                By.CSS_SELECTOR,
                                ".arcticmodal-container, #fileupload_master",
                            )
                        )
                    )

                time.sleep(2)

                # Ждём появления input для файла
                self.wait.until(
                    EC.presence_of_element_located(
                        (By.CSS_SELECTOR, "#fileupload_master")
                    )
                )
                print("✅ Модальное окно открыто и готово")
                break

            except TimeoutException as e:
                print(f"⚠️ Модальное окно не появилось (попытка {attempt + 1}/3): {e}")
                if attempt < 2:
                    print("🔄 Обновляем страницу...")
                    self.driver.refresh()
                    time.sleep(3)
                    continue
                else:
                    raise Exception("Не удалось открыть модальное окно после 3 попыток")

        # ================== ШАГ 2: ОТПРАВКА ФАЙЛА ==================
        file_input = None
        for attempt in range(3):
            try:
                file_input = self.driver.execute_script(
                    "return document.querySelector('#fileupload_master');"
                )

                if not file_input:
                    file_input = self._find_file_input()

                if not file_input:
                    print(f"⚠️ Инпут не найден, попытка {attempt + 1}/3")
                    time.sleep(1)
                    continue

                self._make_input_visible(file_input)
                abs_path = os.path.abspath(photo_path)
                file_input.send_keys(abs_path)
                print(
                    f"📤 Файл {os.path.basename(photo_path)} отправлен через send_keys"
                )
                break

            except Exception as e:
                print(f"⚠️ Ошибка отправки (попытка {attempt + 1}/3): {e}")
                time.sleep(1)
                continue
        else:
            # Fallback — отправка через JS
            try:
                file_input = self.driver.execute_script(
                    "return document.querySelector('#fileupload_master');"
                )
                if file_input:
                    self.driver.execute_script(
                        """
                        arguments[0].style.display = 'block';
                        arguments[0].style.visibility = 'visible';
                        arguments[0].value = arguments[1];
                        arguments[0].dispatchEvent(new Event('change', { bubbles: true }));
                        """,
                        file_input,
                        os.path.abspath(photo_path).replace("\\", "/"),
                    )
                    print("📤 Файл отправлен через JS")
                else:
                    raise Exception("Инпут не найден")
            except Exception as e:
                raise Exception(f"Не удалось отправить файл: {e}")

        # ================== ШАГ 3: ОЖИДАНИЕ 10 СЕКУНД ПОСЛЕ ЗАГРУЗКИ ==================
        print("⏳ Ожидание 10 секунд после отправки файла...")
        time.sleep(10)

        # ================== ШАГ 4: ПРОВЕРКА URL ==================
        current_url = self.driver.current_url
        print(f"🔍 Текущий URL после загрузки: {current_url}")

        # Проверяем, изменился ли URL обратно на галерею
        if "photos/list" in current_url or "gallery" in current_url:
            print("✅ URL изменился на галерею - фото загружено успешно!")

            # ================== ШАГ 5: ПОИСК КНОПКИ "СОХРАНИТЬ" (5 секунд) ==================
            print("⏳ Поиск кнопки 'Сохранить' (5 секунд)...")

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
                        print(f"✅ Найдена кнопка 'Сохранить' по селектору: {selector}")
                        break
                except:
                    continue
            else:
                # Fallback — поиск через JS
                try:
                    save_btn = self.driver.execute_script(
                        """
                        return document.querySelector('#crop_action input.button_green') ||
                            document.querySelector('input.button_green[name="commit"]') ||
                            document.querySelector('input[value="Сохранить"]') ||
                            Array.from(document.querySelectorAll('input')).find(el => el.value === 'Сохранить');
                        """
                    )
                    if save_btn:
                        print("✅ Найдена кнопка 'Сохранить' через JS")
                except:
                    pass

            if save_btn:
                self.driver.execute_script("arguments[0].click();", save_btn)
                print("✅ Кнопка 'Сохранить' нажата через JS")
                time.sleep(3)

            # Закрываем модалку (если ещё открыта)
            self._close_upload_modal()

            # Обновляем страницу
            print("🔄 Обновляем страницу...")
            self.driver.refresh()
            time.sleep(3)

            return {"success": True, "error": "", "type": "success"}

        else:
            # URL НЕ изменился (остался photo_uploader/new)
            print("⚠️ URL не изменился - что-то пошло не так!")

            # ================== ШАГ 6: ПРОВЕРКА НА ОШИБКИ ==================
            print("🔍 Проверка на ошибки загрузки...")
            time.sleep(2)

            try:
                error_items = self.driver.find_elements(
                    By.CSS_SELECTOR, ".upload__item_err"
                )
                for item in error_items:
                    text = item.text.lower()
                    if "слишком часто" in text or "10 минут" in text:
                        print(f"❌ Ошибка rate_limit: {item.text}")
                        return {
                            "success": False,
                            "error": item.text,
                            "type": "rate_limit",
                        }
                    if "уже существует" in text or "дубликат" in text:
                        print(f"❌ Ошибка duplicate: {item.text}")
                        return {
                            "success": False,
                            "error": item.text,
                            "type": "duplicate",
                        }
                    if "качество" in text or "плохо" in text:
                        print(f"❌ Ошибка quality: {item.text}")
                        return {"success": False, "error": item.text, "type": "quality"}
            except Exception as e:
                print(f"⚠️ Ошибка при проверке ошибок: {e}")

            # ================== ШАГ 7: ПРОВЕРКА КОЛИЧЕСТВА ФОТО В ГАЛЕРЕЕ ==================
            # Пробуем проверить, добавилось ли фото (хотя URL другой)
            try:
                # Переходим временно в галерею для проверки
                print("🔍 Проверка количества фото в галерее...")
                gallery_url = current_url.split("photo_uploader")[0] + "photos/list"
                # Не переходим, просто логируем
                print(f"⚠️ URL остался: {current_url}")
            except Exception as e:
                print(f"⚠️ Не удалось проверить галерею: {e}")

            # ================== ШАГ 8: ЖДЁМ ЕЩЁ 5 СЕКУНД ==================
            print("⏳ Ждём ещё 5 секунд...")
            time.sleep(5)

            # ================== ШАГ 9: ПОВТОРНАЯ ПРОВЕРКА URL И ОШИБОК ==================
            current_url = self.driver.current_url
            print(f"🔍 Повторная проверка URL: {current_url}")

            # Проверяем, не изменился ли URL за это время
            if "photos/list" in current_url or "gallery" in current_url:
                print("✅ URL изменился на галерею с задержкой!")
                self._close_upload_modal()
                self.driver.refresh()
                time.sleep(3)
                return {"success": True, "error": "", "type": "success"}

            # Повторная проверка ошибок
            try:
                error_items = self.driver.find_elements(
                    By.CSS_SELECTOR, ".upload__item_err"
                )
                for item in error_items:
                    text = item.text.lower()
                    if "слишком часто" in text or "10 минут" in text:
                        print(f"❌ Ошибка rate_limit: {item.text}")
                        return {
                            "success": False,
                            "error": item.text,
                            "type": "rate_limit",
                        }
                    if "уже существует" in text or "дубликат" in text:
                        print(f"❌ Ошибка duplicate: {item.text}")
                        return {
                            "success": False,
                            "error": item.text,
                            "type": "duplicate",
                        }
                    if "качество" in text or "плохо" in text:
                        print(f"❌ Ошибка quality: {item.text}")
                        return {"success": False, "error": item.text, "type": "quality"}
            except Exception as e:
                print(f"⚠️ Ошибка при повторной проверке: {e}")

            # ================== ШАГ 10: ОБНОВЛЯЕМ СТРАНИЦУ В ЛЮБОМ СЛУЧАЕ ==================
            print("🔄 Обновляем страницу в любом случае...")
            self.driver.refresh()
            time.sleep(3)

            # Проверяем результат после обновления
            try:
                photos = self.driver.find_elements(By.CSS_SELECTOR, "li.gallery__item")
                if photos:
                    print(f"✅ После обновления найдено {len(photos)} фото в галерее")
                    return {"success": True, "error": "", "type": "success"}
            except:
                pass

            return {
                "success": False,
                "error": "URL не изменился после загрузки, причина неизвестна",
                "type": "unknown",
            }

    def _find_file_input(self):
        """Находит input для загрузки файла"""
        # Пробуем разные способы
        methods = [
            # 1. Прямой поиск по ID
            lambda: self.driver.find_element(By.CSS_SELECTOR, "#fileupload_master"),
            # 2. Через JS
            lambda: self.driver.execute_script(
                "return document.querySelector('#fileupload_master');"
            ),
            # 3. По name
            lambda: self.driver.find_element(By.CSS_SELECTOR, "input[name='files[]']"),
            # 4. По атрибуту self_photo
            lambda: self.driver.find_element(
                By.CSS_SELECTOR, "input[type='file'][self_photo='true']"
            ),
            # 5. Все file inputs
            lambda: (
                self.driver.find_elements(By.CSS_SELECTOR, "input[type='file']")[0]
                if self.driver.find_elements(By.CSS_SELECTOR, "input[type='file']")
                else None
            ),
        ]

        for method in methods:
            try:
                element = method()
                if element:
                    print("✅ Input найден")
                    self._make_input_visible(element)
                    return element
            except Exception:
                continue

        return None

    # def _click_save_button(self):
    #     # === Ждём кнопку "Сохранить" и кликаем через JS ===
    #     try:
    #         # Используем точный селектор, который вы дали
    #         save_btn = WebDriverWait(self.driver, 10).until(
    #             EC.presence_of_element_located(
    #                 (By.CSS_SELECTOR, "#crop_action > input.button.button_green")
    #             )
    #         )
    #         # Кликаем через JavaScript (гарантированный обход перекрытий)
    #         self.driver.execute_script("arguments[0].click();", save_btn)
    #         print("✅ Кнопка 'Сохранить' нажата через JS")
    #     except TimeoutException:
    #         # Запасной вариант – по старому селектору
    #         try:
    #             save_btn = WebDriverWait(self.driver, 3).until(
    #                 EC.element_to_be_clickable(
    #                     (By.CSS_SELECTOR, "input.button_green[name='commit']")
    #                 )
    #             )
    #             self.driver.execute_script("arguments[0].click();", save_btn)
    #             print("✅ Кнопка 'Сохранить' нажата через JS (запасной селектор)")
    #         except TimeoutException:
    #             print("⚠️ Кнопка 'Сохранить' не появилась. Продолжаем без неё.")

    #     return self._wait_for_upload_result(timeout=45)

    def _make_input_visible(self, element):
        """Делает input видимым, убирая все скрывающие стили"""
        self.driver.execute_script(
            """
            arguments[0].style.display = 'block';
            arguments[0].style.visibility = 'visible';
            arguments[0].style.opacity = '1';
            arguments[0].style.position = 'relative';
            arguments[0].style.height = 'auto';
            arguments[0].style.width = 'auto';
            arguments[0].style.zIndex = '99999';
            arguments[0].style.pointerEvents = 'auto';
            arguments[0].style.overflow = 'visible';
            arguments[0].style.clip = 'auto';
            arguments[0].style.margin = '10px';
            arguments[0].style.padding = '10px';
            arguments[0].style.border = '2px solid red';
            arguments[0].style.background = 'white';
            arguments[0].removeAttribute('disabled');
            arguments[0].removeAttribute('hidden');
            arguments[0].removeAttribute('class');
            arguments[0].className = '';
            // Убираем !important через установку атрибута
            arguments[0].setAttribute('style',
                'display: block !important; ' +
                'visibility: visible !important; ' +
                'opacity: 1 !important; ' +
                'position: relative !important; ' +
                'z-index: 99999 !important; ' +
                'height: auto !important; ' +
                'width: auto !important; ' +
                'pointer-events: auto !important; ' +
                'margin: 10px !important; ' +
                'padding: 10px !important; ' +
                'border: 2px solid red !important; ' +
                'background: white !important;'
            );
            // Создаем событие, чтобы браузер понял, что элемент изменился
            arguments[0].dispatchEvent(new Event('change', { bubbles: true }));
            arguments[0].dispatchEvent(new Event('click', { bubbles: true }));
        """,
            element,
        )
        time.sleep(0.5)  # Даем время на применение стилей

    def _wait_for_upload_result(self, timeout: int = 45) -> dict:
        """Ожидает завершения загрузки."""
        start = time.time()

        while time.time() - start < timeout:
            try:
                # Проверяем наличие кнопки "Сохранить" - если есть, нажимаем
                save_btns = self.driver.find_elements(
                    By.CSS_SELECTOR,
                    "#crop_action > input.button.button_green, input.button_green[name='commit']",
                )

                for btn in save_btns:
                    if btn.is_displayed() and btn.is_enabled():
                        print("✅ Найдена кнопка 'Сохранить', нажимаем...")
                        self.driver.execute_script("arguments[0].click();", btn)
                        time.sleep(2)
                        return {"success": True, "error": "", "type": "success"}
            except:
                pass

            # Проверяем ошибки
            try:
                error_items = self.driver.find_elements(
                    By.CSS_SELECTOR, ".upload__item_err"
                )
                for item in error_items:
                    text = item.text.lower()
                    if "слишком часто" in text or "10 минут" in text:
                        return {"success": False, "error": text, "type": "rate_limit"}
                    if "уже существует" in text or "дубликат" in text:
                        return {"success": False, "error": text, "type": "duplicate"}
                    if "качество" in text or "плохо" in text:
                        return {"success": False, "error": text, "type": "quality"}
            except:
                pass

            # Проверяем прогресс
            try:
                progress = self.driver.find_element(
                    By.CSS_SELECTOR, ".progressbar__status"
                )
                if "100%" in progress.text:
                    print("✅ Прогресс 100%")
                    time.sleep(2)
                    # Проверяем, появилась ли кнопка завершения
                    try:
                        last_step = self.driver.find_element(
                            By.CSS_SELECTOR, ".photos_last_step_action:not(.hidden)"
                        )
                        if last_step.is_displayed():
                            return {"success": True, "error": "", "type": "success"}
                    except:
                        pass
                    return {"success": True, "error": "", "type": "success"}
            except:
                pass

            # Проверяем, закрылось ли модальное окно (успех)
            try:
                modal = self.driver.find_element(
                    By.CSS_SELECTOR, ".arcticmodal-container"
                )
                if not modal.is_displayed():
                    print("✅ Модальное окно закрыто - загрузка завершена")
                    return {"success": True, "error": "", "type": "success"}
            except:
                # Модального окна нет - возможно загрузка завершена
                pass

            time.sleep(2)

        return {"success": False, "error": "Таймаут", "type": "timeout"}

    def _close_upload_modal(self):
        """Закрывает модальное окно загрузки."""
        for selector in [
            ".modal__close.arcticmodal-close",
            ".arcticmodal-close",
        ]:
            try:
                btn = self.driver.find_element(By.CSS_SELECTOR, selector)
                if btn.is_displayed():
                    btn.click()
                    time.sleep(0.5)
                    return
            except (NoSuchElementException, Exception):
                pass
        # Fallback: ESC
        try:
            self.driver.find_element(By.TAG_NAME, "body").send_keys(Keys.ESCAPE)
            time.sleep(0.5)
        except Exception:
            pass

    def _check_upload_completed(self) -> bool:
        """Проверяет, завершена ли загрузка."""
        try:
            # Проверяем наличие новых фото в галерее
            photos = self._get_gallery_photos()
            if photos:
                # Проверяем статус последнего фото
                status = self._get_photo_status(photos[-1])
                if status in [
                    self.STATUS_MAIN,
                    self.STATUS_BLOCKED,
                    self.STATUS_PENDING,
                ]:
                    return True
        except:
            pass
        return False

    def _make_input_visible(self, element):
        """Делает input видимым"""
        self.driver.execute_script(
            """
            arguments[0].style.display = 'block';
            arguments[0].style.visibility = 'visible';
            arguments[0].style.opacity = '1';
            arguments[0].style.position = 'relative';
            arguments[0].style.height = 'auto';
            arguments[0].style.width = 'auto';
            arguments[0].style.zIndex = '9999';
            arguments[0].style.pointerEvents = 'auto';
            arguments[0].removeAttribute('disabled');
            arguments[0].removeAttribute('hidden');
            arguments[0].setAttribute('style', 'display: block !important; visibility: visible !important; opacity: 1 !important; position: relative !important; z-index: 9999 !important;');
            """,
            element,
        )

    # def _wait_for_upload_result(self, timeout: int = 45) -> dict:
    #     """Ожидает завершения загрузки, отслеживает ошибки."""
    #     result = {"success": False, "error": "", "type": "unknown"}
    #     start = time.time()

    #     while time.time() - start < timeout:
    #         # 1. Проверяем ошибки в списке загрузки
    #         error_items = self.driver.find_elements(
    #             By.CSS_SELECTOR, ".upload__item_err"
    #         )
    #         for item in error_items:
    #             text = item.text.lower()
    #             if "слишком часто" in text or "10 минут" in text:
    #                 return {"success": False, "error": text, "type": "rate_limit"}
    #             if "уже существует" in text or "дубликат" in text:
    #                 return {"success": False, "error": text, "type": "duplicate"}
    #             if "качество" in text or "плохо" in text:
    #                 return {"success": False, "error": text, "type": "quality"}
    #             return {"success": False, "error": text, "type": "unknown"}

    #         # 2. Системные ошибки
    #         try:
    #             sys_error = self.driver.find_element(
    #                 By.CSS_SELECTOR, ".system__msg_err:not(.hidden)"
    #             )
    #             if sys_error.is_displayed():
    #                 return {
    #                     "success": False,
    #                     "error": sys_error.text,
    #                     "type": "system",
    #                 }
    #         except NoSuchElementException:
    #             pass

    #         # 3. Шаг "Завершить" = успех
    #         try:
    #             last_step = self.driver.find_element(
    #                 By.CSS_SELECTOR, ".photos_last_step_action:not(.hidden)"
    #             )
    #             if last_step.is_displayed():
    #                 uploaded = self.driver.find_elements(
    #                     By.CSS_SELECTOR,
    #                     ".upload__list .upload__item:not(.upload__item_err)",
    #                 )
    #                 if uploaded:
    #                     return {"success": True, "error": "", "type": "success"}
    #         except NoSuchElementException:
    #             pass

    #         # 4. Прогресс-бар 100%
    #         try:
    #             progress = self.driver.find_element(
    #                 By.CSS_SELECTOR, ".photos_second_step_action:not(.hidden)"
    #             )
    #             if progress.is_displayed():
    #                 pbar = self.driver.find_element(
    #                     By.CSS_SELECTOR, ".progressbar__status"
    #                 )
    #                 if "100%" in pbar.text:
    #                     time.sleep(1)
    #                     continue
    #         except NoSuchElementException:
    #             pass

    #         time.sleep(1)

    #     return {"success": False, "error": "Таймаут", "type": "timeout"}

    def _close_upload_modal(self):
        """Закрывает модальное окно загрузки."""
        for selector in [
            ".modal__close.arcticmodal-close",
            ".arcticmodal-close",
        ]:
            try:
                btn = self.driver.find_element(By.CSS_SELECTOR, selector)
                if btn.is_displayed():
                    btn.click()
                    time.sleep(0.5)
                    return
            except (NoSuchElementException, Exception):
                pass
        # Fallback: ESC
        try:
            self.driver.find_element(By.TAG_NAME, "body").send_keys(Keys.ESCAPE)
            time.sleep(0.5)
        except Exception:
            pass

    # ================== УДАЛЕНИЕ ФОТО ==================
    def delete_photo(self, photo_element) -> bool:
        """
        Удаляет фото, переходя на его страницу.
        Использует JavaScript-клик для кнопки «Удалить», затем ждёт появления
        кнопки «Да» и кликает по ней через JS (обход перекрытия).
        """
        try:
            photo_url = self._get_photo_link(photo_element)
            if not photo_url:
                print("❌ Не удалось получить ссылку на фото")
                return False

            print(f"🗑 Открываем страницу фото: {photo_url}")
            current_url = self.driver.current_url
            self.driver.get(photo_url)

            time.sleep(2)  # ждём загрузки страницы

            # Кнопка "Удалить"
            delete_btn = self.wait.until(
                EC.presence_of_element_located(
                    (
                        By.CSS_SELECTOR,
                        "a.button.button_yellow.modal__action-blocked[data-method='delete']",
                    )
                )
            )
            self.driver.execute_script("arguments[0].click();", delete_btn)
            print("Нажата кнопка 'Удалить' (через JS)")

            # Даём время на появление модального окна
            time.sleep(1)

            # Ждём появления кнопки "Да" и кликаем через JS по точному селектору
            try:
                # Используем точный CSS-селектор, который вы указали
                confirm_btn = WebDriverWait(self.driver, 5).until(
                    EC.presence_of_element_located(
                        (
                            By.CSS_SELECTOR,
                            "#arcticmodalDialog > div.modal__body > div > div > a.button.button_yellow.arcticmodal-close.confirm_action",
                        )
                    )
                )
                # Кликаем через JavaScript (обход перекрытия)
                self.driver.execute_script("arguments[0].click();", confirm_btn)
                print("✅ Подтверждение удаления нажато через JS")
            except TimeoutException:
                # Если точный селектор не сработал, пробуем запасной вариант
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
                    print(
                        "✅ Подтверждение удаления нажато через JS (запасной селектор)"
                    )
                except TimeoutException:
                    # Если ничего не помогло, пробуем Enter
                    print("⚠️ Кнопка подтверждения не найдена, пробуем Enter...")
                    self.driver.find_element(By.TAG_NAME, "body").send_keys(Keys.ENTER)
                    time.sleep(1)

            time.sleep(2)  # ждём удаления

            # Возврат в галерею
            self.driver.get(current_url)
            self.wait.until(
                EC.presence_of_element_located((By.CSS_SELECTOR, "ul.gallery"))
            )
            time.sleep(1)
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

        # 📌 ОЧИСТКА: удаляем из очереди все несуществующие файлы
        initial_count = len(queue)
        queue = [p for p in queue if os.path.isfile(p)]
        removed_count = initial_count - len(queue)
        if removed_count > 0:
            print(f"⚠️ Удалено из очереди {removed_count} несуществующих файлов")
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
                        print("🔄 Запрос успешен и фото добавились.")
                    else:
                        print("Не удалось выполнить операцию по добавлению")
                        return
                else:
                    print("📋 Запрос отменен пользователем. Завершаем.")
            else:
                print("📋 Очередь пуста. Завершаем.")
            return  # 🆕 Прерываем выполнение, чтобы не было ошибки с переменной photos
            photo_index = 0
        self.go_to_photo_section()
        max_iterations = 60
        iteration = 0

        while iteration < max_iterations and queue:
            iteration += 1
            print(f"\n--- Итерация {iteration} ---")
            self.driver.refresh()
            time.sleep(2)

            photos = self._get_gallery_photos()

            # ===== ШАГ 1: Галерея пуста → загружаем новое фото =====
            if not photos:
                if queue:
                    # ... (логика загрузки случайного фото без изменений) ...
                    queue = [p for p in queue if os.path.isfile(p)]
                    if not queue:
                        print("📋 Все файлы были удалены или не найдены.")
                        break

                    photo_path = random.choice(queue)
                    print(
                        f"\n📸 Галерея пуста. Загружаем случайное фото: {os.path.basename(photo_path)}"
                    )
                    success = self.upload_photo(photo_path)

                    if success:
                        self._delete_photo_file(photo_path)
                        queue.remove(photo_path)
                        photo_index += 1
                        print(
                            f"✅ Загружено {photo_index} фото. Осталось: {len(queue)}"
                        )
                    else:
                        print("❌ Загрузка не удалась. Пропускаем фото.")
                        queue.remove(photo_path)
                    continue
                else:
                    # 🆕 Очередь пуста, спрашиваем про пополнение
                    if self.id_value:
                        response = (
                            input(
                                "📸 Фотографии кончились, отправить запрос на пополнение? (да/нет): "
                            )
                            .strip()
                            .lower()
                        )
                        if response in ("да", "yes", "y", "д"):
                            self._trigger_main_processing()
                            print("🔄 Запрос выполнен. Завершаем текущий цикл.")
                            break
                        else:
                            print("📋 Запрос отменен пользователем. Завершаем.")
                            break
                    else:
                        print("📋 Очередь пуста, галерея пуста. Завершаем.")
                        break

            # ===== ШАГ 2: Галерея не пуста → проверяем статусы =====
            # ... (остальной код цикла без изменений) ...
            print(f"📸 Найдено фото: {len(photos)}")
            time.sleep(1.5)
            any_processed = False

            for i, photo in enumerate(photos):
                # ... (логика проверки статусов и удаления) ...
                try:
                    status = self._get_photo_status(photo)
                except Exception as e:
                    print(f"⚠️ Ошибка получения статуса фото {i}: {e}")
                    break

                print(f"Фото {i + 1}: статус '{status}'")

                if status == self.STATUS_MAIN:
                    decision = (
                        input("✅ Это правильная главная? (да/нет): ").strip().lower()
                    )
                    if decision in ("да", "yes", "y"):
                        print("✅ Главная принята. Завершаем.")
                        return
                    else:
                        print("🗑️ Удаляем неподходящую главную.")
                        if self.delete_photo(photo):
                            time.sleep(1.5)
                            any_processed = True
                        break
                elif status == self.STATUS_BLOCKED:
                    print("⚠️ Заблокированное фото. Удаляем.")
                    if self.delete_photo(photo):
                        time.sleep(1.5)
                        any_processed = True
                    break
                else:
                    print("⏳ Фото на модерации, ничего не делаем.")

            if not any_processed:
                print("⏳ Ничего не сделано, ждём 60 секунд...")
                time.sleep(60)
            else:
                print("🔄 Были изменения, обновляем страницу...")
                time.sleep(3)

        # Завершение
        if not queue:
            # 🆕 Дополнительная проверка на случай, если цикл завершился из-за пустой очереди
            if self.id_value and not photos:
                response = (
                    input(
                        "📸 Фотографии кончились, отправить запрос на пополнение? (да/нет): "
                    )
                    .strip()
                    .lower()
                )
                if response in ("да", "yes", "y", "д"):
                    self._trigger_main_processing()
            else:
                print("📋 Все фото обработаны, главная не выбрана.")
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
        input("Подтвердите авторизацию (если нужно) и нажмите Enter...")
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
    args = parser.parse_args()
    parser.add_argument(
        "--id",
        type=str,
        default=os.getenv("TABOR_ID"),
        help="ID для папки download/extracted/<id>",
    )

    args = parser.parse_args()

    start_connect(args.login, args.password, args.port, args.id)
