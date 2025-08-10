import datetime
import asyncio

import jdatetime
import requests
from aiogram.enums import ParseMode

from services.bot_instance import bot

from services import IBSng
from services.IBSng import change_group
from services.db import (
    get_reserved_orders,
    get_order_data,
    update_order_status,
    get_order_plan_duration,
)
from config import BOT_TOKEN  # فرض بر این که توکن در config موجود است


# ----------------------------------------------------------------------------
# Public API – called by scheduler/cron
# ----------------------------------------------------------------------------

def activate_reserved_orders() -> None:
    """Activate reserved renewal orders whose previous cycle has finished.

    This function should be executed periodically (e.g. every 5‑10 minutes).
    It performs three simple steps:

    1. Fetch all orders with status = "reserved".
    2. For each one, fetch its linked *previous* order (via ``is_renewal_of_order``).
    3. If the previous order has truly expired, mark it expired, activate the
       reserved order, reset the account in IBSng and assign the proper group.
    """

    for reserved in get_reserved_orders():
        _maybe_activate_reserved_order(reserved)


# ----------------------------------------------------------------------------
# Internal helpers
# ----------------------------------------------------------------------------

def _maybe_activate_reserved_order(reserved_order: dict) -> None:
    prev_id: int | None = reserved_order.get("is_renewal_of_order")
    if not prev_id:
        return  # No linked order → nothing to do

    previous = get_order_data(prev_id)
    if not previous:
        return  # Previous order missing

    if not _is_previous_order_expired(previous):
        return  # Still active – wait for next run

    # Previous order renewed → activate reserved one
    update_order_status(order_id=previous["id"], new_status="renewed")
    update_order_status(order_id=reserved_order["id"], new_status="active")

    # Sync IBSng group according to plan duration
    duration_months = get_order_plan_duration(order_id=reserved_order["id"]).get("duration_months", 1)
    group_name = f"{duration_months}-Month"

    IBSng.reset_account_client(username=reserved_order["username"])
    change_group(reserved_order["username"], group_name)

    # Notify the user via Telegram
    _notify_user_activation(reserved_order, duration_months)

def _is_previous_order_expired(order: dict) -> bool:
    """Return True if previous order expired (status or timestamp)."""

    if order.get("status") == "expired":
        return True

    exp_str: str | None = order.get("expires_at")
    if not exp_str:
        return False

    exp_jdt = jdatetime.datetime.strptime(exp_str, "%Y-%m-%d %H:%M")
    exp_greg = exp_jdt.togregorian()
    return exp_greg < datetime.datetime.now()


def _notify_user_activation(reserved_order: dict, duration_months: int) -> None:
    msg = (
        "✅ دوست عزیز، دورهٔ قبلی سرویس شما به پایان رسید و تمدید {duration} ماهه به‌طور خودکار فعال شد.\n"
        "نام کاربری: <code>{username}</code>\n"
        "لطفاً در صورت مشکل با پشتیبانی در تماس باشید."
    ).format(duration=duration_months, username=reserved_order["username"])


    """ارسال پیام به کاربر در تلگرام"""
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
    data = {
        "chat_id": reserved_order["user_id"],
        "text": msg,
        "parse_mode": "HTML"
    }
    response = requests.post(url, data=data)
    if not response.ok:
        raise Exception(f"Telegram API error: {response.text}")