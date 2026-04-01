import datetime
from typing import Union

import jdatetime
import requests

from config import BOT_TOKEN  # فرض بر این که توکن در config موجود است
from services import IBSng
from services.IBSng import change_group
from services.db import (
    get_waiting_for_payment_orders, get_user_balance, get_order_data, update_order_status, get_order_plan_duration,
    get_order_plan_group_name, update_user_balance, get_plan_name

)


def activate_waiting_for_payment_orders() -> None:
    for waiting_for_payment in get_waiting_for_payment_orders():
        _maybe_waiting_for_payment_order(waiting_for_payment)


def _maybe_waiting_for_payment_order(waiting_for_payment: dict) -> None:
    user_id = waiting_for_payment.get("user_id")
    plan_price = waiting_for_payment.get("price")
    current_balance = get_user_balance(user_id=user_id)
    if current_balance < plan_price:
        return  # هنوز موجودیش کافی نیست.

    prev_id: int | None = waiting_for_payment.get("is_renewal_of_order")
    if not prev_id:
        return  # No linked order → nothing to do

    previous = get_order_data(prev_id)
    if not previous:
        return  # Previous order missing
    # کسر موجودی
    new_balance = current_balance - plan_price
    update_user_balance(user_id, new_balance)

    if _is_previous_order_expired(previous):
        update_order_status(order_id=previous["id"], new_status="renewed")
        update_order_status(order_id=waiting_for_payment["id"], new_status="active")

        group_info = get_order_plan_group_name(order_id=waiting_for_payment["id"]) or {}
        group_name = group_info.get("group_name", "Starter-Bot")

        IBSng.reset_account_client(username=waiting_for_payment["username"])
        change_group(waiting_for_payment["username"], group_name)
        _notify_user_payment_activated(reserved_order=waiting_for_payment, new_balance=new_balance)

    else:
        update_order_status(order_id=previous["id"], new_status="waiting_for_renewal")
        update_order_status(order_id=waiting_for_payment["id"], new_status="reserved")

        _notify_user_payment_reserved(reserved_order=waiting_for_payment, new_balance=new_balance)


def _is_previous_order_expired(order: dict) -> bool:
    exp_str: str | None = order.get("expires_at")
    if not exp_str:
        return False

    exp_jdt = jdatetime.datetime.strptime(exp_str, "%Y-%m-%d %H:%M")
    exp_greg = exp_jdt.togregorian()
    return exp_greg < datetime.datetime.now()


def format_price(amount: Union[int, float]) -> str:
    try:
        return f"{int(amount):,}"
    except Exception:
        return str(amount)


def _notify_user_payment_activated(reserved_order: dict, new_balance: int) -> None:
    plan_id = reserved_order.get("plan_id")
    plan_name = get_plan_name(plan_id=plan_id)
    username = reserved_order["username"]

    msg = (
        f"✅ پرداخت شما با موفقیت ثبت شد و سرویس شما فعال گردید.\n\n"
        f"🔸 پلن: {plan_name}\n"
        f"👤 نام کاربری: `{username}`\n"
        f"💰 موجودی: {format_price(new_balance)} تومان"
    )
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
    data = {
        "chat_id": reserved_order["user_id"],
        "text": msg,
        "parse_mode": "HTML"
    }

    response = requests.post(url, data=data)
    if not response.ok:
        raise Exception(f"Telegram API error: {response.text}")


def _notify_user_payment_reserved(reserved_order: dict, new_balance: int) -> None:
    plan_id = reserved_order.get("plan_id")
    plan_name = get_plan_name(plan_id=plan_id)
    username = reserved_order["username"]

    msg = (

        f"✅ پرداخت شما با موفقیت ثبت شد.\n"
        f" سرویس شما پس از پایان دوره‌ی فعلی به‌صورت خودکار فعال می گردد.\n\n"
        f"🔸 پلن: {plan_name}\n"
        f"👤 نام کاربری: `{username}`\n"
        f"💰 موجودی: {format_price(new_balance)} تومان"
    )

    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
    data = {
        "chat_id": reserved_order["user_id"],
        "text": msg,
        "parse_mode": "HTML"
    }

    response = requests.post(url, data=data)
    if not response.ok:
        raise Exception(f"Telegram API error: {response.text}")
