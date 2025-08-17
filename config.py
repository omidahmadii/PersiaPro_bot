from pathlib import Path
from dotenv import load_dotenv
import os

BASE_DIR = Path(__file__).resolve().parent
load_dotenv(BASE_DIR / ".env")

BOT_TOKEN = os.getenv("BOT_TOKEN", "")
ADMINS = [int(x) for x in os.getenv("ADMINS", "").split(',') if x]
CHANNEL_ID = int(os.getenv("CHANNEL_ID", "0"))

DB_PATH = os.getenv("DB_PATH", str(BASE_DIR / "database" / "vpn_bot.db"))

IBS_BASE_URL = os.getenv("IBS_BASE_URL", "")
IBS_USERNAME = os.getenv("IBS_USERNAME", "")
IBS_PASSWORD = os.getenv("IBS_PASSWORD", "")
