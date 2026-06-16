import os
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

    def __init__(self, driver, login: str, password: str):
        self.driver = driver
        self.wait = WebDriverWait(driver, 20)
        self._login = login
        self._password = password

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

    # ================== ЗАГРУЗКА ФОТО ==================
    def upload_photo(self, photo_path: str, max_retries: int = 3) -> bool:
        """
        Загрузка фотографии с повторными попытками.
        Возвращает True при успехе, False при пропуске (дубликат, низкое качество).
        """
        if not os.path.isfile(photo_path):
            raise FileNotFoundError(f"Файл не найден: {photo_path}")

        for attempt in range(max_retries):
            try:
                print(f"\n🔄 Попытка загрузки {attempt + 1}/{max_retries}")
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
                    time.sleep(5)
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
        Выполняет одну попытку загрузки.
        Возвращает словарь с результатом: {"success": bool, "error": str, "type": str}
        """
        # 1. Открыть модалку загрузки
        upload_btn = self.wait.until(
            EC.element_to_be_clickable(
                (By.CSS_SELECTOR, "a.button.button_green[href='/photo_uploader/new']")
            )
        )
        upload_btn.click()
        time.sleep(1.5)

        # 2. Дождаться появления модального окна
        self.wait.until(
            EC.presence_of_element_located((By.CSS_SELECTOR, ".arcticmodal-container"))
        )

        # 3. Найти input[type=file] и отправить файл
        file_input = self._find_file_input()
        if not file_input:
            raise Exception("Не удалось найти input для загрузки файла")

        self._make_input_visible(file_input)
        file_input.send_keys(os.path.abspath(photo_path))
        print(f"📤 Файл {os.path.basename(photo_path)} отправлен")

        # 4. Нажать кнопку «Сохранить» через JavaScript (точный селектор)
        try:
            # Ждём появления кнопки по точному ID/CSS
            save_btn = WebDriverWait(self.driver, 10).until(
                EC.presence_of_element_located(
                    (By.CSS_SELECTOR, "#crop_action > input.button.button_green")
                )
            )
            # Клик через JS (обход любых перекрытий)
            self.driver.execute_script("arguments[0].click();", save_btn)
            print("✅ Кнопка 'Сохранить' нажата через JS")
        except TimeoutException:
            # Запасной вариант (если селектор изменится)
            try:
                save_btn = WebDriverWait(self.driver, 3).until(
                    EC.element_to_be_clickable(
                        (By.CSS_SELECTOR, "input.button_green[name='commit']")
                    )
                )
                self.driver.execute_script("arguments[0].click();", save_btn)
                print("✅ Кнопка 'Сохранить' нажата через JS (запасной селектор)")
            except TimeoutException:
                print("⚠️ Кнопка 'Сохранить' не появилась. Продолжаем без неё.")

        # 5. Ожидать результат загрузки (отслеживание ошибок, прогресс-бар)
        return self._wait_for_upload_result(timeout=45)

    def _find_file_input(self):
        """Находит input для загрузки файла"""
        selectors = [
            # "#fileupload_master",
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

    def _wait_for_upload_result(self, timeout: int = 45) -> dict:
        """Ожидает завершения загрузки, отслеживает ошибки."""
        result = {"success": False, "error": "", "type": "unknown"}
        start = time.time()

        while time.time() - start < timeout:
            # 1. Проверяем ошибки в списке загрузки
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
                return {"success": False, "error": text, "type": "unknown"}

            # 2. Системные ошибки
            try:
                sys_error = self.driver.find_element(
                    By.CSS_SELECTOR, ".system__msg_err:not(.hidden)"
                )
                if sys_error.is_displayed():
                    return {
                        "success": False,
                        "error": sys_error.text,
                        "type": "system",
                    }
            except NoSuchElementException:
                pass

            # 3. Шаг "Завершить" = успех
            try:
                last_step = self.driver.find_element(
                    By.CSS_SELECTOR, ".photos_last_step_action:not(.hidden)"
                )
                if last_step.is_displayed():
                    uploaded = self.driver.find_elements(
                        By.CSS_SELECTOR,
                        ".upload__list .upload__item:not(.upload__item_err)",
                    )
                    if uploaded:
                        return {"success": True, "error": "", "type": "success"}
            except NoSuchElementException:
                pass

            # 4. Прогресс-бар 100%
            try:
                progress = self.driver.find_element(
                    By.CSS_SELECTOR, ".photos_second_step_action:not(.hidden)"
                )
                if progress.is_displayed():
                    pbar = self.driver.find_element(
                        By.CSS_SELECTOR, ".progressbar__status"
                    )
                    if "100%" in pbar.text:
                        time.sleep(1)
                        continue
            except NoSuchElementException:
                pass

            time.sleep(1)

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

            # Шаг 1: если галерея пуста – загружаем следующее фото
            if not photos:
                if queue:
                    photo_path = queue[0]
                    print(
                        f"\n📸 Галерея пуста. Загружаем: {os.path.basename(photo_path)}"
                    )
                    success = self.upload_photo(photo_path)
                    if success:
                        queue.pop(0)
                        photo_index += 1
                        print(
                            f"✅ Загружено {photo_index} фото. Осталось: {len(queue)}"
                        )
                    else:
                        print(
                            "❌ Загрузка не удалась, пробуем снова на следующей итерации"
                        )
                    # После загрузки переходим к следующей итерации (даём время на модерацию)
                    continue
                else:
                    print("📋 Очередь пуста, галерея пуста. Завершаем.")
                    break

            # Шаг 2: галерея не пуста – обрабатываем все фото
            print(f"📸 Найдено фото: {len(photos)}")
            any_processed = False

            for i, photo in enumerate(photos):
                try:
                    status = self._get_photo_status(photo)
                except Exception as e:
                    print(f"⚠️ Ошибка получения статуса фото {i}: {e}")
                    # Если элемент стал stale, выходим из цикла и перезагружаем страницу
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
                            any_processed = True
                            # Удаляем фото из очереди? Нет, мы его уже загрузили ранее, просто удаляем,
                            # и на следующей итерации загрузится новое (если галерея станет пустой).
                            # Но статус "Главная" означает, что фото было загружено и прошло модерацию,
                            # но пользователь его отверг. Значит, это фото больше не нужно.
                            # Можно либо удалить его (уже сделано), либо пропустить.
                            # После удаления галерея может стать пустой, тогда загрузится следующее.
                        else:
                            print("⚠️ Не удалось удалить фото")
                        # Выходим из цикла, чтобы перезагрузить страницу и избежать stale элементов
                        break

                elif status == self.STATUS_BLOCKED:
                    print("⚠️ Заблокированное фото. Удаляем.")
                    if self.delete_photo(photo):
                        any_processed = True
                    else:
                        print("⚠️ Не удалось удалить фото")
                    break  # выходим из цикла, чтобы перезагрузить страницу

                else:
                    print("⏳ Фото на модерации, ничего не делаем.")

            # Шаг 3: если не было никаких действий (все фото на модерации) – ждём 15 секунд
            if not any_processed:
                print("⏳ Ничего не сделано, ждём 15 секунд...")
                time.sleep(15)
            else:
                # Если были изменения (удаления), даём время на обновление страницы
                print("🔄 Были изменения, обновляем страницу...")
                time.sleep(3)

        # Завершение
        if not queue:
            print("📋 Все фото обработаны, главная не выбрана.")
        else:
            print("⏰ Таймаут мониторинга.")


# ================== ЗАПУСК ==================


def start_connect(LOGIN, PASSWORD, PORT_NUMBER):
    options = Options()
    options.add_experimental_option("debuggerAddress", f"127.0.0.1:{PORT_NUMBER}")
    service = Service(r"C:\chromedriver_148\chromedriver-win64\chromedriver.exe")
    driver = webdriver.Chrome(service=service, options=options)
    driver.get("https://tabor.ru")
    print("✅ Selenium подключился, текущий URL:", driver.current_url)

    try:
        uploader = TaborPhotoUploader(driver, LOGIN, PASSWORD)
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

    start_connect(args.login, args.password, args.port)
