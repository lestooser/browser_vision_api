# Browser Vision Profile Manager

Python-инструмент для управления профилями браузера через Browser Vision API. Проект объединяет создание профилей, настройку отпечатков браузера, запуск через очередь, отслеживание локальных процессов и, при необходимости, управление через Telegram.

Репозиторий также демонстрирует интеграцию стороннего REST API с локальной автоматизацией браузера и хранением состояния процессов. Используйте его только с собственными аккаунтами и системами либо при наличии разрешения на их использование.

## Возможности

- Создание и настройка профилей через клиент Browser Vision API.
- Формирование настроек отпечатка браузера из конфигурации.
- Очередь запуска профилей с сохранением состояния между запусками.
- Отслеживание локальных процессов и портов удалённой отладки в Windows.
- Дополнительное управление запуском через Telegram-бота.
- Хранение учётных данных и настроек конкретной машины в локальных файлах.

## Архитектура

```text
main.py / photo_notify_bot.py
              |
      auto_runner.py
       /           \
queue_manager.py  api_client.py ---- Browser Vision API
       |
state_manager.py / console_monitor.py
       |
profile_script/tebor.py ---- локальный профиль браузера
```

| Модуль | Назначение |
| --- | --- |
| `api_client.py` | Запросы к Browser Vision API и локальному API управления профилями |
| `fingerprint_generator.py` | Подготовка настроек отпечатка профиля |
| `profile_creator.py` | Создание профилей и настройка их параметров |
| `queue_manager.py` | Сохранение и обработка очереди профилей |
| `auto_runner.py` | Координация запуска и остановки профилей |
| `state_manager.py`, `tebor_state.py` | Сохранение состояния процессов и автоматизации |
| `config_sequence.py` | Чтение локальных списков имён и прокси, переключение индексов |
| `photo_notify_bot.py` | Необязательный интерфейс управления через Telegram |
| `profile_script/tebor.py` | Автоматизация Selenium в запущенном профиле |

## Требования

- Windows для функций управления процессами и портами.
- Python 3.8 или новее.
- Установленное приложение Browser Vision, аккаунт и доступ к API.
- Совместимая версия ChromeDriver для Selenium-автоматизации.
- Данные Telegram-бота, если планируется запускать `photo_notify_bot.py`.

## Установка

```powershell
git clone https://github.com/lestooser/browser_vision_api2.git
cd browser_vision_api2
py -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
Copy-Item .env.example .env
Copy-Item config\pers_id.example.txt config\pers_id.txt
Copy-Item config\town.example.txt config\town.txt
```

Для ротации прокси скопируйте `config\proxy.example.txt` в `config\proxy.txt` и замените пример собственными данными прокси.

Укажите свои значения в `.env`. Как минимум нужны `TOKEN_PROF` и `FOLDER_ID`. Для Telegram-бота дополнительно укажите `TG_BOT_TOKEN` и `TG_CHAT_ID`. Переменная `AUTO_PHOTO_ROOT` задаёт локальную папку с фотографиями профилей; по умолчанию используется `downloads\extracted`.

Для Selenium-автоматизации укажите путь к совместимому ChromeDriver в `CHROMEDRIVER_EXE` либо установите драйвер в ожидаемую скриптом папку проекта.

## Запуск

Интерактивный менеджер профилей:

```powershell
python main.py
```

Необязательный Telegram-интерфейс:

```powershell
python photo_notify_bot.py
```

Для работы требуется установленное и доступное локально приложение Browser Vision. Перед запуском проверьте действия профилей и локальные входные данные. Проект не создаёт аккаунт Browser Vision и не проверяет права доступа к сторонним аккаунтам.

## Конфигурация и безопасность

Файл `.env.example` содержит перечень переменных окружения. Локальные списки для имён и ротации прокси хранятся в `config\pers_id.txt`, `config\town.txt` и, при необходимости, `config\proxy.txt`. Шаблоны этих файлов имеют суффикс `.example.txt`. Индексы и состояние работы сохраняются локально; такие файлы исключены из Git.

Не добавляйте в репозиторий реальные идентификаторы аккаунтов, пароли, API-токены, данные прокси или персональную информацию. Если секрет уже попадал в Git-коммит, отзовите или замените его: добавление файла в `.gitignore` не удаляет данные из истории Git.

## Ограничения

- Управление процессами рассчитано на Windows.
- Работа API зависит от доступности Browser Vision и локального приложения.
- ChromeDriver не входит в репозиторий; скачайте совместимую версию отдельно.
- В проекте нет интеграционных тестов с реальным API; сначала проверяйте работу на непроизводственном профиле.

---

# Browser Vision Profile Manager

A Python toolkit for managing browser profiles through the Browser Vision API. It brings profile creation, configurable fingerprints, queue-based launching, local process tracking, and optional Telegram controls together in a modular codebase.

This repository also demonstrates integrating a third-party REST API with local browser automation and persistent process state. Use it only with accounts, profiles, and systems you own or are authorized to manage.

## Highlights

- Create and configure browser profiles through an API client.
- Build profile fingerprint settings from reusable configuration.
- Queue profile launches and persist queue state between runs.
- Track local processes and browser debugging ports on Windows.
- Optionally operate the runner through a Telegram bot.
- Keep credentials and machine-specific inputs in local configuration files.

## Architecture

```text
main.py / photo_notify_bot.py
              |
      auto_runner.py
       /           \
queue_manager.py  api_client.py ---- Browser Vision API
       |
state_manager.py / console_monitor.py
       |
profile_script/tebor.py ---- local browser profile
```

| Module | Responsibility |
| --- | --- |
| `api_client.py` | Browser Vision API and local profile-control requests |
| `fingerprint_generator.py` | Builds profile fingerprint settings |
| `profile_creator.py` | Creates profiles and configures their settings |
| `queue_manager.py` | Persists and processes queued profile work |
| `auto_runner.py` | Coordinates profile launch and stop operations |
| `state_manager.py`, `tebor_state.py` | Persists active process and automation state |
| `config_sequence.py` | Reads local name/proxy inputs and advances their indexes |
| `photo_notify_bot.py` | Optional Telegram interface |
| `profile_script/tebor.py` | Selenium-based automation for a launched profile |

## Requirements

- Windows for the process and port management features.
- Python 3.8 or newer.
- An installed Browser Vision application/account and API access.
- A ChromeDriver version compatible with the installed browser for Selenium automation.
- Telegram bot credentials only if using `photo_notify_bot.py`.

## Setup

```powershell
git clone https://github.com/lestooser/browser_vision_api2.git
cd browser_vision_api2
py -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
Copy-Item .env.example .env
Copy-Item config\pers_id.example.txt config\pers_id.txt
Copy-Item config\town.example.txt config\town.txt
```

For proxy rotation, copy `config\proxy.example.txt` to `config\proxy.txt` and replace the example entry with your own proxy.

Edit `.env` with your own values. At minimum, set `TOKEN_PROF` and `FOLDER_ID`. The optional Telegram bot also needs `TG_BOT_TOKEN` and `TG_CHAT_ID`. `AUTO_PHOTO_ROOT` can point to a local directory containing per-profile photo folders; by default, the application uses `downloads\extracted`.

For Selenium automation, set `CHROMEDRIVER_EXE` to a compatible ChromeDriver executable, or place the driver in the project location expected by the automation script.

## Running

Start the interactive profile manager:

```powershell
python main.py
```

Start the optional Telegram interface:

```powershell
python photo_notify_bot.py
```

The automation expects the Browser Vision desktop application to be installed and available locally. Review profile actions and local automation inputs before running them. This project does not provision a Browser Vision account or validate third-party account permissions.

## Configuration and security

`.env.example` lists supported environment variables. Profile naming and proxy-rotation inputs belong in `config\pers_id.txt`, `config\town.txt`, and optionally `config\proxy.txt`. Example files use the `.example.txt` suffix. The application writes indexes and runtime state locally; these files are excluded from Git.

Do not put real account identifiers, passwords, API tokens, proxy credentials, or personal data in example files or commits. If a credential has ever been committed, revoke or rotate it; adding it to `.gitignore` does not remove it from Git history.

## Limitations

- Process management is Windows-specific.
- API behavior depends on the Browser Vision service and local desktop application.
- ChromeDriver is not bundled; download a compatible version separately.
- The project has no live API integration tests; test with a non-production profile first.
