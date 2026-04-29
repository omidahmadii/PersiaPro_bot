from pathlib import Path
from dotenv import load_dotenv
import os

BASE_DIR = Path(__file__).resolve().parent
load_dotenv(BASE_DIR / ".env")


def env_bool(name: str, default: bool = False) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def env_int(name: str, default: int) -> int:
    raw = os.getenv(name)
    if raw is None:
        return default
    try:
        return int(raw.strip())
    except Exception:
        return default

BOT_TOKEN = os.getenv("BOT_TOKEN", "")
ADMINS = [int(x) for x in os.getenv("ADMINS", "").split(',') if x]
CHANNEL_ID = int(os.getenv("CHANNEL_ID", "0"))

APP_ENV = (os.getenv("APP_ENV") or "development").strip().lower()
if APP_ENV not in {"development", "staging", "production"}:
    APP_ENV = "development"

IS_PRODUCTION = APP_ENV == "production"
IS_NON_PRODUCTION = not IS_PRODUCTION

DB_PATH = os.getenv("DB_PATH", str(BASE_DIR / "database" / "vpn_bot.db"))

ENABLE_SCHEDULER = env_bool("ENABLE_SCHEDULER", default=IS_PRODUCTION)
SCHEDULER_UPDATE_ORDER_TIMES = env_bool("SCHEDULER_UPDATE_ORDER_TIMES", default=IS_PRODUCTION)
SCHEDULER_EXPIRE_ORDERS = env_bool("SCHEDULER_EXPIRE_ORDERS", default=IS_PRODUCTION)
SCHEDULER_ACTIVATE_RESERVED = env_bool("SCHEDULER_ACTIVATE_RESERVED", default=IS_PRODUCTION)
SCHEDULER_NOTIFIER = env_bool("SCHEDULER_NOTIFIER", default=IS_PRODUCTION)
SCHEDULER_CONVERSION_NOTIFIER = env_bool("SCHEDULER_CONVERSION_NOTIFIER", default=ENABLE_SCHEDULER)
SCHEDULER_USAGE_LOGGER = env_bool("SCHEDULER_USAGE_LOGGER", default=IS_PRODUCTION)
SCHEDULER_USAGE_NOTIFIER = env_bool("SCHEDULER_USAGE_NOTIFIER", default=IS_PRODUCTION)
SCHEDULER_MEMBERSHIP = env_bool("SCHEDULER_MEMBERSHIP", default=IS_PRODUCTION)
SCHEDULER_LIMIT_SPEED = env_bool("SCHEDULER_LIMIT_SPEED", default=IS_PRODUCTION)
SCHEDULER_ACTIVATE_WAITING_FOR_PAYMENT = env_bool("SCHEDULER_ACTIVATE_WAITING_FOR_PAYMENT", default=IS_PRODUCTION)
SCHEDULER_CANCEL_NOT_PAID = env_bool("SCHEDULER_CANCEL_NOT_PAID", default=IS_PRODUCTION)
SCHEDULER_AUTO_RENEW = env_bool("SCHEDULER_AUTO_RENEW", default=IS_PRODUCTION)
ORDER_ARCHIVE_AFTER_DAYS = max(env_int("ORDER_ARCHIVE_AFTER_DAYS", 30), 1)

IBS_USERNAME = os.getenv("IBS_USERNAME", "")
IBS_PASSWORD = os.getenv("IBS_PASSWORD", "")
IBS_URL_BASE = os.getenv("IBS_URL_BASE", "")
IBS_URL_INFO = os.getenv("IBS_URL_INFO", "")
IBS_URL_EDIT = os.getenv("IBS_URL_EDIT", "")
IBS_URL_CONNECTIONS = os.getenv("IBS_URL_CONNECTIONS", "")
IBS_URL_DELETE = os.getenv("IBS_URL_DELETE", "")

# Cloudflare config
CF_ZONE_ID = os.getenv("CF_ZONE_ID")
CF_EMAIL = os.getenv("CF_EMAIL")
CF_API_KEY = os.getenv("CF_API_KEY")


# Sites
CF_RECORD_NAME = os.getenv("CF_RECORD_NAME", "ov")


ANDROID_OVPN_VIDEO = os.getenv("ANDROID_OVPN_VIDEO", "")
ANDROID_L2TP_VIDEO = os.getenv("ANDROID_L2TP_VIDEO", "")
ANDROID_ANYCONNECT_VIDEO = os.getenv("ANDROID_ANYCONNECT_VIDEO", "")

IOS_OVPN_VIDEO = os.getenv("IOS_OVPN_VIDEO", "")
IOS_L2TP_VIDEO = os.getenv("IOS_L2TP_VIDEO", "")
IOS_ANYCONNECT_VIDEO = os.getenv("IOS_ANYCONNECT_VIDEO", "")
WINDOWS_L2TP_VIDEO = os.getenv("WINDOWS_L2TP_VIDEO", "")
