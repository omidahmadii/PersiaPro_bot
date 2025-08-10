# config.py (new)
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



"""

import os

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(BASE_DIR, "database", "vpn_bot.db")

# Omidmilad_bot Token
BOT_TOKEN = "5994755065:AAHBJ0q0WaiaUFbnlUyaBbdVMkw63G77Hh0"

# Persiapro_bot Token
# BOT_TOKEN = "7389580734:AAHyaMuOZ-hsQToKPHVl3rAjwIZhXBEURO0"

# persiapro_admin_bot Token
#BOT_TOKEN = "8172961465:AAF-H9GpNedKFd0QsPinkLyrvM2Te8OvJ5s"

# لیست آیدی ادمین‌ها
ADMINS = [205280218, 5796072869]

CHANNEL_ID = -1001197717164  # آیدی کانال
"""