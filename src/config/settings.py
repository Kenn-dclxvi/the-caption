import os
import io
import sys
from typing import Final, Dict, Tuple, List, Any, Optional
from dotenv import load_dotenv
from cryptography.fernet import Fernet, InvalidToken

__REV: Final[str] = "Rev. 36"

KEY_FILE: Final[str] = "secret.key"
ENC_FILE: Final[str] = ".env.enc"

if os.path.exists(KEY_FILE) and os.path.exists(ENC_FILE):
    try:
        with open(KEY_FILE, "rb") as kf: key = kf.read()
        fernet = Fernet(key)
        with open(ENC_FILE, "rb") as ef: encrypted_data = ef.read()
        decrypted_data = fernet.decrypt(encrypted_data).decode('utf-8')
        load_dotenv(stream=io.StringIO(decrypted_data))
    except (InvalidToken, ValueError) as e:
        sys.stderr.write(f"[CRITICAL] Encrypted env decryption failed: {e}. Falling back to plaintext .env\n")
        load_dotenv()
    except Exception as e:
        sys.stderr.write(f"[CRITICAL] Unexpected error loading encrypted env: {e}. Falling back to plaintext .env\n")
        load_dotenv()
else:
    load_dotenv()

VERSION: Final[str] = "4.3"
APP_NAME: Final[str] = "THE CAPTION"
DATA_DIR: Final[str] = "data"
LOG_DIR: Final[str] = "logs"
LOG_FILE: Final[str] = os.path.join(LOG_DIR, "finance_report.log")
LLM_TRACE_FILE: Final[str] = os.path.join(LOG_DIR, "llm_trace.log")
HISTORY_FILE: Final[str] = os.path.join(DATA_DIR, "history.csv")
LAST_ACCESS_FILE: Final[str] = os.path.join(DATA_DIR, "last_access_date.txt")

LAST_SENT_FILE_CURRENT: Final[str] = os.path.join(DATA_DIR, "last_sent_mail_V2.txt")
LAST_SENT_FILE_MONTHLY: Final[str] = os.path.join(DATA_DIR, "last_sent_monthly.txt")
LAST_SENT_FILE_WEEKLY: Final[str] = os.path.join(DATA_DIR, "last_sent_weekly.txt")

DIR_ARCHIVE: Final[str] = os.path.join(DATA_DIR, "archive")
DIR_CURRENT: Final[str] = os.path.join(DATA_DIR, "current")

DIR_COLLECTION: Final[str] = os.path.join(DATA_DIR, "collection")
DIR_COLLECTION_HISTORY: Final[str] = os.path.join(DIR_COLLECTION, "history")
LAST_SENT_FILE_COLLECTION: Final[str] = os.path.join(DATA_DIR, "last_sent_collection.txt")
DIR_PHASE1_COLLECTION: Final[str] = os.path.join(DATA_DIR, "phase1", "collection")

CONTEXT_REPORT_THRESHOLD_PCT: Final[float] = 0.5

LLM_CONFIG: Final[Dict[str, Dict[str, Any]]] = {
    "claude": {
        "api_key": os.getenv("ANTHROPIC_API_KEY"),
        "model": "claude-sonnet-4-6",
        "max_tokens": 8192
    },
    "google": {
        "api_key": os.getenv("GOOGLE_API_KEY"),
        "base_url": "https://generativelanguage.googleapis.com/v1beta/openai/",
        "model": "gemini-flash-latest"
    },
    "deepseek": {
        "api_key": os.getenv("DEEPSEEK_API_KEY"),
        "base_url": "https://api.deepseek.com",
        "model": "deepseek-chat"
    }
}

LLM_PRIORITY_ORDER: Final[List[str]] = ["claude", "google"]

LLM_RETRY_PARAMS: Final[Dict[str, Any]] = {
    "max_retries": 3,
    "base_delay": 5.0,
    "timeout": 90.0,
    "enable_dynamic_wait": True
}

SMTP_SERVER: Final[str] = "smtp.gmail.com"
SMTP_PORT: Final[int] = 465
SMTP_USER: Final[Optional[str]] = os.getenv("SMTP_USER")
SMTP_PASS: Final[Optional[str]] = os.getenv("SMTP_PASS")
SMTP_TO: Final[Optional[str]] = os.getenv("SMTP_TO")

for d in [DATA_DIR, LOG_DIR, DIR_ARCHIVE, DIR_CURRENT, DIR_COLLECTION, DIR_COLLECTION_HISTORY, DIR_PHASE1_COLLECTION]:
    if not os.path.exists(d): os.makedirs(d)
