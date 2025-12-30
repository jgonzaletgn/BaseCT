from pathlib import Path

# Application metadata
APP_NAME = "BaseCT"
APP_VERSION = "0.1"
APP_RELEASE_DATE = "2025-12-30"
APP_AUTHOR = "Jorge González"


# Working folders (created next to app.py)
BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "data"
VAULT_DIR = BASE_DIR / "vault"
FILES_DIR = VAULT_DIR / "files"

DATA_DIR.mkdir(parents=True, exist_ok=True)
VAULT_DIR.mkdir(parents=True, exist_ok=True)
FILES_DIR.mkdir(parents=True, exist_ok=True)

DB_PATH = DATA_DIR / "baserow_lite.sqlite3"
