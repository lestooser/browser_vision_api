import os
import time

import requests
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

TELEGRAM_TOKEN = os.getenv("TOKEN_BOT")
TELEGRAM_CHAT_ID = os.getenv("TG_CHAT_ID")
PHOTO_PATHS = get_photo_path(os.getenv("FOLDER_PHOTO_PATH"))


# ================== ФУНКЦИИ УВЕДОМЛЕНИЙ ==================
def send_telegram(message):
    """Отправка сообщения в Telegram"""
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    try:
        requests.post(
            url, json={"chat_id": TELEGRAM_CHAT_ID, "text": message}, timeout=5
        )
    except Exception as e:
        print(f"Ошибка отправки уведомления: {e}")


# ================== ОСНОВНОЙ КЛАСС ==================
class TaborPhotoUploader:
    def __init__(self, driver, LOGIN, PASSWORD):
        self.driver = driver
        self.wait = WebDriverWait(driver, 20)
        self._login = LOGIN
        self._password = PASSWORD

    def login(self, _login, _password):
        """Авторизация на сайте с ручным обходом Turnstile (один раз)"""
        self.driver.get("https://tabor.ru")

        # Клик по кнопке "Войти"
        time.sleep(4)
        login_btn = self.wait.until(
            EC.element_to_be_clickable((By.CSS_SELECTOR, "a[href='/signin']"))
        )
        login_btn.click()

        # Ввод логина и пароля
        email_input = self.wait.until(
            EC.presence_of_element_located((By.ID, "session_user_login"))
        )
        email_input.send_keys(_login)

        pass_input = self.driver.find_element(By.ID, "session_user_password")
        pass_input.send_keys(_password)

        # Ожидание ручного прохождения Cloudflare Turnstile
        input("👉 Пройдите капчу 'Я не робот' в браузере и нажмите Enter...")

        # Нажатие кнопки "Войти"
        submit_btn = self.driver.find_element(
            By.CSS_SELECTOR, "input[type='submit'][value='Войти']"
        )
        submit_btn.click()

    def go_to_photo_section(self):
        """Переход в раздел 'Фото'"""
        photo_link = self.wait.until(
            EC.element_to_be_clickable((By.CSS_SELECTOR, "a.user__gallery__link_photo"))
        )
        photo_link.click()
        time.sleep(2)

    def get_current_photo_count(self):
        """Возвращает текущее количество фото в галерее"""
        photos = self.driver.find_elements(By.CSS_SELECTOR, ".gallery__item")
        return len(photos)

    # ========== ОСНОВНЫЕ МЕТОДЫ ЗАГРУЗКИ ==========

    def upload_photo(self, photo_path, max_retries=3):
        """Загрузка фотографии только прямым методом (без открытия системного диалога)"""
        if not os.path.isfile(photo_path):
            raise FileNotFoundError(f"Файл не найден: {photo_path}")

        for attempt in range(max_retries):
            try:
                print(f"\n🔄 Попытка загрузки {attempt + 1}/{max_retries}")

                # 1. Открываем модалку
                upload_btn = self.wait.until(
                    EC.element_to_be_clickable(
                        (By.CSS_SELECTOR, "a[href='/photo_uploader/new']")
                    )
                )
                upload_btn.click()
                print("1. Нажата кнопка 'Загрузить фото'")
                time.sleep(1.5)

                self.wait.until(
                    EC.presence_of_element_located(
                        (By.CSS_SELECTOR, ".arcticmodal-container")
                    )
                )
                print("2. Модальное окно открыто")

                # 2. Находим input
                file_input = self._find_file_input()
                if not file_input:
                    raise Exception("Не удалось найти input для загрузки файла")

                # 3. Делаем input видимым и отправляем файл
                self._make_input_visible(file_input)
                try:
                    file_input.send_keys(os.path.abspath(photo_path))
                    print(f"3. Файл {os.path.basename(photo_path)} отправлен напрямую")
                except Exception as e:
                    print(f"⚠️ send_keys не сработал: {e}")
                    self.driver.execute_script(
                        "arguments[0].value = arguments[1];",
                        file_input,
                        os.path.abspath(photo_path),
                    )
                    self.driver.execute_script(
                        "arguments[0].dispatchEvent(new Event('change', { bubbles: true }));",
                        file_input,
                    )
                    print("3. Файл отправлен через JavaScript")

                # 4. Ждём результат загрузки
                result = self._wait_for_upload_result(timeout=45)

                if result["success"]:
                    print("✅ Фото успешно загружено!")
                    self._close_upload_modal()
                    return True
                else:
                    error_msg = result.get("error", "Неизвестная ошибка")
                    error_type = result.get("type", "unknown")
                    print(f"❌ Ошибка загрузки: {error_msg}")
                    self._close_upload_modal()

                    if error_type == "rate_limit":
                        print(
                            "⏳ Обнаружено ограничение по частоте загрузок. Ждём 10 минут..."
                        )
                        time.sleep(620)
                        continue
                    elif error_type == "duplicate":
                        print("⚠️ Фото уже существует. Пропускаем.")
                        return False
                    elif error_type == "quality":
                        print("⚠️ Фото не прошло проверку качества. Пропускаем.")
                        return False
                    else:
                        print("Повторная попытка через 5 секунд...")
                        time.sleep(5)
                        continue

            except Exception as e:
                print(f"⚠️ Критическая ошибка при загрузке: {e}")
                try:
                    self._close_upload_modal()
                except:
                    pass
                if attempt < max_retries - 1:
                    print("Повторная попытка через 10 секунд...")
                    time.sleep(10)
                    continue
                else:
                    raise Exception(
                        f"Не удалось загрузить фото после {max_retries} попыток: {e}"
                    )

        return False

    def _find_file_input(self):
        """Находит input для загрузки файла несколькими способами"""
        selectors = [
            "#fileupload_master",
            "#fileupload_master-styler input[type='file']",
            ".modal input[type='file']",
            "input[name='files[]']",
            "input[type='file'][self_photo='true']",
            ".arcticmodal-container input[type='file']",
        ]

        for selector in selectors:
            try:
                element = self.driver.find_element(By.CSS_SELECTOR, selector)
                if element and element.is_enabled():
                    print(f"✅ Input найден по селектору: {selector}")
                    return element
            except:
                continue

        # Если ничего не найдено, пробуем найти все inputs и проверить
        try:
            all_inputs = self.driver.find_elements(
                By.CSS_SELECTOR, "input[type='file']"
            )
            for inp in all_inputs:
                if inp.is_enabled():
                    print("✅ Input найден через поиск всех file inputs")
                    return inp
        except:
            pass

        return None

    def _make_input_visible(self, element):
        """Делает input видимым и доступным для взаимодействия"""
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
            arguments[0].removeAttribute('style');
            arguments[0].setAttribute('style', 'display: block !important; visibility: visible !important; opacity: 1 !important; position: relative !important; z-index: 9999 !important;');
        """,
            element,
        )

    def _wait_for_upload_result(self, timeout=10):
        """Ожидает результат загрузки и проверяет наличие ошибок"""
        result = {"success": False, "error": "", "type": "unknown"}

        start_time = time.time()
        while time.time() - start_time < timeout:
            try:
                # Проверяем наличие ошибок в списке загрузки
                error_items = self.driver.find_elements(
                    By.CSS_SELECTOR, ".upload__item_err"
                )

                for item in error_items:
                    error_text = item.text.lower()
                    print(f"🔍 Обнаружена ошибка: {error_text}")

                    if "слишком часто" in error_text or "10 минут" in error_text:
                        return {
                            "success": False,
                            "error": error_text,
                            "type": "rate_limit",
                        }
                    elif "уже существует" in error_text or "дубликат" in error_text:
                        return {
                            "success": False,
                            "error": error_text,
                            "type": "duplicate",
                        }
                    elif "качество" in error_text or "плохо" in error_text:
                        return {
                            "success": False,
                            "error": error_text,
                            "type": "quality",
                        }
                    else:
                        return {
                            "success": False,
                            "error": error_text,
                            "type": "unknown",
                        }

                # Проверяем системные сообщения об ошибках
                try:
                    sys_error = self.driver.find_element(
                        By.CSS_SELECTOR, ".system__msg_err:not(.hidden)"
                    )
                    if sys_error.is_displayed():
                        error_text = sys_error.text
                        print(f"🔍 Системная ошибка: {error_text}")
                        return {"success": False, "error": error_text, "type": "system"}
                except:
                    pass

                # Проверяем, появился ли третий шаг (успешная загрузка)
                try:
                    last_step = self.driver.find_element(
                        By.CSS_SELECTOR, ".photos_last_step_action:not(.hidden)"
                    )
                    if last_step.is_displayed():
                        uploaded_items = self.driver.find_elements(
                            By.CSS_SELECTOR,
                            ".upload__list .upload__item:not(.upload__item_err)",
                        )
                        if uploaded_items:
                            result["success"] = True
                            return result
                except:
                    pass

                # Проверяем прогресс бар (второй шаг)
                try:
                    progress = self.driver.find_element(
                        By.CSS_SELECTOR, ".photos_second_step_action:not(.hidden)"
                    )
                    if progress.is_displayed():
                        progress_text = self.driver.find_element(
                            By.CSS_SELECTOR, ".progressbar__status"
                        ).text
                        if "100%" in progress_text:
                            print("Прогресс достиг 100%")
                            time.sleep(1)
                            continue
                except:
                    pass

                time.sleep(0.5)

            except Exception as e:
                print(f"⚠️ Ошибка при проверке результата: {e}")
                time.sleep(0.5)

        # Если не удалось определить результат, проверяем наличие фото в галерее
        try:
            old_count = self.get_current_photo_count()
            time.sleep(2)
            if self.get_current_photo_count() > old_count:
                result["success"] = True
                return result
        except:
            pass

        result["error"] = "Таймаут ожидания результата загрузки"
        return result

    def _close_upload_modal(self):
        """Надежное закрытие модального окна загрузки"""
        try:
            # Пробуем закрыть через крестик
            close_btn = self.driver.find_element(
                By.CSS_SELECTOR, ".modal__close.arcticmodal-close"
            )
            if close_btn.is_displayed():
                close_btn.click()
                print("Модальное окно закрыто через крестик")
                time.sleep(0.5)
                return
        except:
            pass

        # Альтернатива - ESC
        try:
            self.driver.find_element(By.TAG_NAME, "body").send_keys(Keys.ESCAPE)
            print("Модальное окно закрыто через ESC")
            time.sleep(0.5)
            return
        except:
            pass

        # Последний вариант - клик по overlay
        try:
            overlay = self.driver.find_element(By.CSS_SELECTOR, ".arcticmodal-overlay")
            self.driver.execute_script("arguments[0].click()", overlay)
            print("Модальное окно закрыто через клик по overlay")
            time.sleep(0.5)
        except:
            print("⚠️ Не удалось закрыть модальное окно")

    # ========== МЕТОДЫ РАБОТЫ СО СТАТУСАМИ И УДАЛЕНИЕМ ==========

    def get_photo_status(self, photo_element):
        """Возвращает статус фотографии ('Главная' или 'Заблокировано')"""
        try:
            status_elem = photo_element.find_element(
                By.CSS_SELECTOR, ".meta__item__lbl"
            )
            return status_elem.text.strip()
        except NoSuchElementException:
            return ""

    def delete_photo(self, driver, photo_element):
        """Удаление заблокированной фотографии"""
        current_url = driver.current_url
        photo_link = photo_element.find_element(By.CSS_SELECTOR, ".gallery__img-link")
        photo_url = photo_link.get_attribute("href")
        print(f"Открываем страницу фото: {photo_url}")

        self.driver.get(photo_url)
        time.sleep(2)

        delete_btn = self.wait.until(
            EC.element_to_be_clickable((By.CSS_SELECTOR, "a[data-method='delete']"))
        )
        delete_btn.click()
        print("Нажата кнопка 'Удалить'")
        time.sleep(2)

        confirm_btn = self.wait.until(
            EC.element_to_be_clickable(
                (By.CSS_SELECTOR, "a.button.button_yellow.confirm_action")
            )
        )
        confirm_btn.click()
        print("Подтверждено удаление")

        try:
            alert = self.wait.until(EC.alert_is_present())
            alert.accept()
            print("Фотография удалена")
        except TimeoutException:
            print("Alert не появился, возможно удаление без подтверждения")

        self.wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, ".gallery")))
        time.sleep(1)
        driver.get(current_url)
        time.sleep(1)
        self.driver.refresh()

    def monitor_photos(self, driver, photo_paths):
        """Цикл мониторинга статуса фотографий"""
        photo_index = 0

        while photo_index < len(photo_paths):
            print(
                f"\n📸 Загружаем фото {photo_index + 1}/{len(photo_paths)}: {os.path.basename(photo_paths[photo_index])}"
            )

            try:
                success = self.upload_photo(photo_paths[photo_index])
                if not success:
                    print(
                        f"⚠️ Фото {os.path.basename(photo_paths[photo_index])} не загружено"
                    )
                    photo_index += 1
                    continue
            except Exception as e:
                print(f"❌ Критическая ошибка при загрузке: {e}")
                photo_index += 1
                continue

            monitoring_attempts = 0
            max_monitoring_attempts = 30

            while monitoring_attempts < max_monitoring_attempts:
                self.driver.refresh()
                time.sleep(5)

                photos = self.driver.find_elements(By.CSS_SELECTOR, ".gallery__item")
                if not photos:
                    print("Нет фотографий в галерее")
                    monitoring_attempts += 1
                    continue

                last_photo = photos[-1]
                if last_photo:
                    status = self.get_photo_status(last_photo)
                    print(f"📊 Статус фото: '{status}'")

                    if status == "Главная":
                        message = f"✅ Фото '{os.path.basename(photo_paths[photo_index])}' успешно прошло модерацию!"
                        print(message)
                        send_telegram(message)
                        return

                    elif status == "Заблокировано":
                        print(
                            f"⚠️ Фото '{os.path.basename(photo_paths[photo_index])}' заблокировано. Удаляем..."
                        )
                        self.delete_photo(driver, last_photo)
                        photo_index += 1
                        break

                    else:
                        print(f"⏳ Статус фото: '{status}', ожидаем модерации...")

                monitoring_attempts += 1
                time.sleep(15)

            if monitoring_attempts >= max_monitoring_attempts:
                print(
                    f"⏰ Таймаут мониторинга для фото {os.path.basename(photo_paths[photo_index])}"
                )
                photo_index += 1

        print("📋 Все фото обработаны")
        send_telegram("📋 Все фото обработаны (загружены или отклонены)")


# ================== ФУНКЦИИ ЗАПУСКА ==================


def start_connect(LOGIN, PASSWORD, PORT_NUMBER):
    options = Options()
    options.add_experimental_option("debuggerAddress", f"127.0.0.1:{PORT_NUMBER}")
    service = Service(r"C:\chromedriver_148\chromedriver-win64\chromedriver.exe")
    driver = webdriver.Chrome(service=service, options=options)
    driver.get("https://tabor.ru")
    print("✅ Selenium подключился, текущий URL:", driver.current_url)

    try:
        uploader = TaborPhotoUploader(driver, LOGIN, PASSWORD)
        input("Подтвердите авторизацию")
        time.sleep(2)
        uploader.go_to_photo_section()
        uploader.monitor_photos(driver, PHOTO_PATHS)
    except Exception as e:
        print(f"Критическая ошибка: {e}")
        send_telegram(f"❌ Ошибка в скрипте: {e}")
    finally:
        input("Нажмите Enter для закрытия браузера...")
        driver.quit()


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Tabor photo uploader")
    parser.add_argument("--profile-id", help="ID профиля")
    parser.add_argument("--port", type=int, required=True, help="CDP порт")
    parser.add_argument("--login", help="Логин")
    parser.add_argument("--password", help="Пароль")
    parser.add_argument(
        "--auto", action="store_true", help="Автоматический режим без ввода"
    )
    args = parser.parse_args()

    LOGIN = args.login or os.getenv("TABOR_LOGIN")
    PASSWORD = args.password or os.getenv("TABOR_PASSWORD")

    options = Options()
    options.add_experimental_option("debuggerAddress", f"127.0.0.1:{args.port}")
    service = Service(r"C:\chromedriver_148\chromedriver-win64\chromedriver.exe")

    driver = webdriver.Chrome(service=service, options=options)
    print(
        f"✅ Selenium подключился к профилю {args.profile_id or 'unknown'} на порту {args.port}"
    )

    try:
        if args.auto and LOGIN and PASSWORD:
            uploader = TaborPhotoUploader(driver, LOGIN, PASSWORD)
            uploader.login(LOGIN, PASSWORD)
            uploader.go_to_photo_section()
            uploader.monitor_photos(driver, PHOTO_PATHS)
        else:
            input("Нажмите Enter после готовности...")
            driver.get("https://tabor.ru")
    except Exception as e:
        print(f"❌ Ошибка: {e}")
    finally:
        if not args.auto:
            input("Нажмите Enter для закрытия браузера...")
            driver.quit()
