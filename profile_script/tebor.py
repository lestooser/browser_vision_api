import os
import time
from pathlib import Path

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

        # Сохраняем cookies для будущих запусков (опционально)
        # Можно добавить сохранение cookies в файл

    def go_to_photo_section(self):
        """Переход в раздел 'Фото'"""
        photo_link = self.wait.until(
            EC.element_to_be_clickable((By.CSS_SELECTOR, "a.user__gallery__link_photo"))
        )
        photo_link.click()
        time.sleep(2)  # небольшая пауза после перехода

    def get_current_photo_count(self):
        """Возвращает текущее количество фото в галерее"""
        photos = self.driver.find_elements(By.CSS_SELECTOR, ".gallery__item")
        return len(photos)

    def upload_photo(self, photo_path):
        # 1. Клик по кнопке "Загрузить фото"
        upload_btn = self.wait.until(
            EC.element_to_be_clickable(
                (By.CSS_SELECTOR, "a[href='/photo_uploader/new']")
            )
        )
        upload_btn.click()
        print("1. Нажата кнопка 'Загрузить фото'")
        time.sleep(4)  # ждём открытия модалки

        # 2. Клик по кнопке "Выбрать фотографии" внутри модального окна
        choose_btn = self.wait.until(
            EC.element_to_be_clickable(
                (By.CSS_SELECTOR, "button.photos_next_step_action")
            )
        )
        choose_btn.click()
        print("2. Нажата кнопка 'Выбрать фотографии'")

        # 3. Ждём появления input type="file" (он может создаваться динамически)
        file_input = self.wait.until(
            EC.presence_of_element_located((By.ID, "fileupload_master"))
        )
        print("3. Input найден")

        # 4. Делаем его видимым (если скрыт)
        self.driver.execute_script("arguments[0].style.display = 'block';", file_input)
        self.driver.execute_script(
            "arguments[0].style.visibility = 'visible';", file_input
        )
        self.driver.execute_script("arguments[0].style.opacity = '1';", file_input)
        self.driver.execute_script("arguments[0].style.height = 'auto';", file_input)
        self.driver.execute_script("arguments[0].style.width = 'auto';", file_input)

        # 5. Убедимся, что элемент не disabled
        if file_input.get_attribute("disabled"):
            print("⚠️ Input disabled, пытаемся убрать disabled")
            self.driver.execute_script(
                "arguments[0].removeAttribute('disabled');", file_input
            )

        # 6. Отправляем путь к файлу
        file_input.send_keys(photo_path)
        print(f"4. Файл {photo_path} отправлен")

        # 7. Небольшая пауза для начала загрузки
        time.sleep(5)

        # 8. Ожидание появления новой фотографии в галерее (или хотя бы превью)
        old_count = self.get_current_photo_count()
        try:
            self.wait.until(lambda d: self.get_current_photo_count() > old_count)
            print("5. Загрузка завершена, фото появилось в галерее")
        except TimeoutException:
            print(
                "Внимание: новое фото не обнаружено. Возможно, требуется подтверждение."
            )
            # Можно проверить, нет ли кнопки "Сохранить" или "Готово"
            save_btn = self.driver.find_elements(
                By.CSS_SELECTOR, "button.button_green, input[value='Сохранить']"
            )
            if save_btn:
                print("Найдена кнопка подтверждения, нажимаем...")
                save_btn[0].click()
                time.sleep(2)

            try:
                self.driver.find_element(By.TAG_NAME, "body").send_keys(Keys.ESCAPE)
                print("Диалог закрыт через Esc")
            except Exception:
                # Если не сработало, используем pyautogui
                try:
                    import pyautogui

                    pyautogui.press("esc")
                    print("Диалог закрыт через pyautogui")
                except ImportError:
                    print("pyautogui не установлен, диалог может остаться открытым")

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
        """
        Удаление заблокированной фотографии.
        Сначала переходит на страницу фото, затем нажимает 'Удалить'.
        """
        # 1. Находим ссылку на страницу фото
        current_url = driver.current_url
        photo_link = photo_element.find_element(By.CSS_SELECTOR, ".gallery__img-link")
        photo_url = photo_link.get_attribute("href")
        print(f"Открываем страницу фото: {photo_url}")

        # 2. Переходим на страницу фото
        self.driver.get(photo_url)
        time.sleep(2)  # ждём загрузки страницы

        # 3. Ищем кнопку "Удалить" на странице фото
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
        print("Модальное окно появилось, кнопка 'Да' найдена")

        # 3. Кликаем "Да" для подтверждения
        confirm_btn.click()
        print("Подтверждено удаление")
        # try:
        #     self.driver.find_element(By.TAG_NAME, "body").send_keys(Keys.ENTER)
        #     print("Диалог закрыт через Esc")
        # except Exception:
        #     # Если не сработало, используем pyautogui
        #     try:
        #         import pyautogui

        #         pyautogui.press("ENTER")
        #         print("Диалог закрыт через pyautogui")
        #     except ImportError:
        #         print("pyautogui не установлен, диалог может остаться открытым")

        # 4. Обработка alert подтверждения
        try:
            alert = self.wait.until(EC.alert_is_present())
            alert.accept()
            print("Фотография удалена")
        except TimeoutException:
            print("Alert не появился, возможно удаление без подтверждения")

        # 5. Возвращаемся в галерею
        # self.driver.get("https://tabor.ru/photos/list")  # или self.driver.back()
        self.wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, ".gallery")))
        time.sleep(1)

        driver.get(current_url)
        time.sleep(1)
        self.driver.refresh()

    def monitor_photos(self, driver, photo_paths):
        """
        Цикл мониторинга статуса фотографий.
        Если фото имеет статус 'Главная' -> уведомление и завершение.
        Если статус 'Заблокировано' -> удалить и загрузить следующее фото из списка.
        """
        photo_index = 0  # индекс текущей загруженной фотографии (из списка)
        # self.upload_photo(photo_paths[photo_index])

        while True:
            # Обновляем страницу, чтобы получить актуальные статусы
            self.driver.refresh()
            time.sleep(5)  # ждём загрузки элементов

            # Находим все фотографии в галерее
            photos = self.driver.find_elements(By.CSS_SELECTOR, ".gallery__item")
            if not photos:
                print("Нет фотографий в галерее. Возможно, загрузка не удалась.")
                # Попробуем загрузить снова
                self.upload_photo(photo_paths[photo_index])
                photo_index += 1
                continue

            # Проверяем статус для каждой фотографии (обычно последняя загруженная - последняя в списке)
            # Для простоты перебираем все, но можно отслеживать по времени загрузки
            for photo in photos:
                status = self.get_photo_status(photo)
                print(f"Статус фото: '{status}'")

                if status == "Главная":
                    message = f"✅ Фото '{photo_paths[photo_index]}' успешно прошло модерацию!"
                    print(message)
                    # send_telegram(message)
                    result = input("Никакой ошибки? ")
                    if result == "y" or "yes":
                        return  # завершаем работу
                    else:
                        self.delete_photo(driver, photo)

                elif status == "Заблокировано":
                    print(
                        f"⚠️ Фото '{photo_paths[photo_index]}' заблокировано. Удаляем..."
                    )
                    self.delete_photo(driver, photo)

                    # Загружаем следующее фото, если есть

                    if photo_index >= len(photo_paths):
                        print("Нет больше фотографий для загрузки. Завершение.")
                        # send_telegram(
                        #     "❌ Все фотографии заблокированы, больше нет файлов."
                        # )
                        return
                    else:
                        print(f"Загружаем следующее фото: {photo_paths[photo_index]}")
                        self.upload_photo(photo_paths[photo_index])
                        photo_index += 1
                        break  # выходим из цикла проверки, чтобы обновить страницу и смотреть новое фото

            # Пауза 15 секунд до следующей проверки
            time.sleep(15)


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
    parser.add_argument("--auto", action="store_true", help="Автоматический режим без ввода")
    args = parser.parse_args()

    LOGIN = args.login or os.getenv("TABOR_LOGIN")
    PASSWORD = args.password or os.getenv("TABOR_PASSWORD")

    options = Options()
    options.add_experimental_option("debuggerAddress", f"127.0.0.1:{args.port}")
    service = Service(r"C:\chromedriver_148\chromedriver-win64\chromedriver.exe")

    driver = webdriver.Chrome(service=service, options=options)
    print(f"✅ Selenium подключился к профилю {args.profile_id or 'unknown'} на порту {args.port}")

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
