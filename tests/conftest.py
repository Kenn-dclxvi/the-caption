import sys
from unittest.mock import MagicMock

_mock_settings = MagicMock()
_mock_settings.LOG_FILE = "logs/test.log"
_mock_settings.LOG_DIR = "logs"
_mock_settings.APP_NAME = "THE CAPTION"
_mock_settings.VERSION = "3.5"
_mock_settings.DATA_DIR = "data"
_mock_settings.LLM_TRACE_FILE = "logs/llm_trace.log"
_mock_settings.HISTORY_FILE = "data/history.csv"
_mock_settings.LAST_ACCESS_FILE = "data/last_access_date.txt"
_mock_settings.STORAGE_STATE_PATH = "auth/state.json"
_mock_settings.LAST_SENT_FILE_CURRENT = "data/last_sent_mail_V2.txt"
_mock_settings.LAST_SENT_FILE_WEEKLY = "data/last_sent_weekly.txt"
_mock_settings.LAST_SENT_FILE_MONTHLY = "data/last_sent_monthly.txt"
_mock_settings.DIR_ARCHIVE = "data/archive"
_mock_settings.DIR_CURRENT = "data/current"
_mock_settings.DIR_COLLECTION = "data/collection"
_mock_settings.DIR_COLLECTION_HISTORY = "data/collection/history"
_mock_settings.LAST_SENT_FILE_COLLECTION = "data/last_sent_collection.txt"
_mock_settings.LLM_PRIORITY_ORDER = ["claude", "google"]
_mock_settings.CONTEXT_REPORT_THRESHOLD_PCT = 0.5
_mock_settings.LLM_CONFIG = {}
_mock_settings.LLM_RETRY_PARAMS = {"max_retries": 0, "base_delay": 0.0, "timeout": 10.0, "enable_dynamic_wait": False}
_mock_settings.SMTP_SERVER = "smtp.test"
_mock_settings.SMTP_PORT = 465
_mock_settings.SMTP_USER = "test@test.com"
_mock_settings.SMTP_PASS = "testpass"
_mock_settings.SMTP_TO = "to@test.com"
_mock_settings.BROKER_ASSET_MAP = {}
_mock_settings.BROKER_ASSET_MAP_PENDING = {}
_mock_settings.URL_VIEW = "https://example.com"
_mock_settings.URL_LOGIN = "https://example.com"
_mock_settings.BROKER_VIEW_BASE_URL = "https://example.com"
_mock_settings.CHROME_PATH = "/usr/bin/google-chrome"

_mock_prompts = MagicMock()
_mock_prompts.CURATOR_EXHIBITION_REPORT = (
    "{jp_date}{theme}{angle}{us_date}{us_market_context}"
    "{total_diff_pct}{safe_ratio}{total_return}{gallery_text}"
)
_mock_prompts.EXHIBITION_THEMES = {
    "CRASH": ("CRASH_THEME", "CRASH_ANGLE"),
    "BEAR":  ("BEAR_THEME",  "BEAR_ANGLE"),
    "FLAT":  ("FLAT_THEME",  "FLAT_ANGLE"),
    "BULL":  ("BULL_THEME",  "BULL_ANGLE"),
}
_mock_prompts.CURATOR_BANNED_WORDS = ["禁止ワード"]
_mock_prompts.US_MARKET_CONTEXT_NORMAL  = "Normal: {cal_label}"
_mock_prompts.US_MARKET_CONTEXT_HOLIDAY = "Holiday: {cal_label} -> {trading_label}"

sys.modules.setdefault("playwright",          MagicMock())
sys.modules.setdefault("playwright.sync_api", MagicMock())
sys.modules.setdefault("jpholiday",            MagicMock())
sys.modules.setdefault("pandas_market_calendars", MagicMock())
sys.modules.setdefault("openai",               MagicMock())
sys.modules.setdefault("anthropic",            MagicMock())
sys.modules.setdefault("yfinance",             MagicMock())
sys.modules.setdefault("jinja2",              MagicMock())
_certifi_stub = MagicMock()
_certifi_stub.where.return_value = "/mock/cacert.pem"
sys.modules.setdefault("certifi",             _certifi_stub)

try:
    import pandas  # type: ignore  # noqa: F401
except Exception:
    sys.modules.setdefault("pandas", MagicMock())

try:
    import pydantic  # type: ignore  # noqa: F401
except Exception:
    sys.modules.setdefault("pydantic", MagicMock())

sys.modules.setdefault("src.config", MagicMock())
sys.modules["src.config.settings"] = _mock_settings
sys.modules["src.config.prompts"]  = _mock_prompts
