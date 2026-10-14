# Browser Vision Profile Manager

A Python toolkit for managing browser profiles through the Browser Vision API. It brings profile creation, configurable fingerprints, queue-based launching, local process tracking, and optional Telegram controls together in a modular codebase.

This repository is also a portfolio example of integrating a third-party REST API with local browser automation and persistent process state. Use it only with accounts, profiles, and systems you own or are authorized to manage.

## Highlights

- Create and configure browser profiles through a small API client.
- Build profile fingerprints from reusable configuration.
- Queue profile launches and persist queue/state between runs.
- Track local processes and browser debugging ports on Windows.
- Optionally operate the runner through a Telegram bot.
- Keep credentials and machine-specific inputs in local configuration files.

## How it fits together

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

Key modules:

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
- A Browser Vision installation/account and API access.
- ChromeDriver compatible with the installed browser when running Selenium automation.
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

If you use proxy rotation, also copy `config\proxy.example.txt` to `config\proxy.txt` and replace its example entry with your own proxy.

Edit `.env` with your own values. At minimum, set `TOKEN_PROF` and `FOLDER_ID`. The optional Telegram bot also needs `TG_BOT_TOKEN` and `TG_CHAT_ID`. `AUTO_PHOTO_ROOT` can point to a local directory containing per-profile photo folders; by default the application uses `downloads\extracted`. Keep `.env`, local configuration inputs, runtime state, and downloaded browser drivers out of version control.

For Selenium automation, set `CHROMEDRIVER_EXE` to the path of a compatible ChromeDriver executable, or place the driver at the default project path expected by the automation script.

## Running

Start the interactive profile manager:

```powershell
python main.py
```

Start the optional Telegram interface:

```powershell
python photo_notify_bot.py
```

The automation expects the Browser Vision desktop application to be installed and available locally. Review the profile actions and local automation inputs before running them; this project does not provision a Browser Vision account or validate third-party account permissions.

## Configuration

`.env.example` lists supported environment variables. Profile naming/proxy rotation inputs belong in `config\pers_id.txt`, `config\town.txt`, and optionally `config\proxy.txt`. Examples are provided with the `.example.txt` suffix. The application writes its indexes and runtime state locally; these files are ignored by Git.

Do not put real account identifiers, passwords, API tokens, proxy credentials, or personal data in example files or commits. If a credential has ever been committed, revoke or rotate it; adding it to `.gitignore` does not remove it from Git history.

## Limitations

- Process management is Windows-specific.
- API behavior depends on the Browser Vision service and local desktop application.
- This repository has no bundled ChromeDriver binary; download a compatible driver separately.
- The project does not include a live API integration test suite; test against a non-production profile first.
