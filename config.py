from pathlib import Path
from dotenv import load_dotenv
import os

BASE_DIR = Path(__file__).resolve().parent
load_dotenv(BASE_DIR / ".env")

BOT_TOKEN = os.getenv("BOT_TOKEN", "")
ADMINS = [int(x) for x in os.getenv("ADMINS", "").split(',') if x]
CHANNEL_ID = int(os.getenv("CHANNEL_ID", "0"))

DB_PATH = os.getenv("DB_PATH", str(BASE_DIR / "database" / "vpn_bot.db"))

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


