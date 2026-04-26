from datetime import datetime, timedelta
from typing import Optional

import jdatetime

from services.db import (
    get_waiting_for_payment_orders,
    update_order_status,
    get_order_data,
    release_account_by_username,
    get_plan_name,
)
from services.scheduler_services.telegram_safe import send_scheduler_notification

PENDING_PAYMENT_TIMEOUT = timedelta(hours=24)


def cancel_not_paid_waiting_for_payment_orders() -> None:
    for waiting_for_payment in get_waiting_for_payment_orders():
        _maybe_cancel_not_paid(waiting_for_payment)


def _maybe_cancel_not_paid(waiting_for_payment: dict) -> None:
    created_at = waiting_for_payment.get("created_at")
    if not created_at:
        return

    created_time = datetime.fromisoformat(created_at)
    now = datetime.now()
    if now - created_time <= PENDING_PAYMENT_TIMEOUT:
        return

    order_id = waiting_for_payment["id"]
    previous_id: Optional[int] = waiting_for_payment.get("is_renewal_of_order")

    if previous_id:
        previous = get_order_data(previous_id)
        if previous:
            restored_status = "expired" if _is_order_expired(previous) else "active"
            update_order_status(order_id=previous_id, new_status=restored_status)
        update_order_status(order_id=order_id, new_status="canceled")
        _notify_user_pending_renewal_canceled(waiting_for_payment)
        return

    release_account_by_username(str(waiting_for_payment["username"]))
    update_order_status(order_id=order_id, new_status="canceled")
    _notify_user_pending_purchase_canceled(waiting_for_payment)


def _is_order_expired(order: dict) -> bool:
    expires_at = order.get("expires_at")
    if not expires_at:
        return False

    try:
        exp_greg = jdatetime.datetime.strptime(expires_at, "%Y-%m-%d %H:%M").togregorian()
        return exp_greg < datetime.now()
    except Exception:
        return False


def _send_notification(user_id: int, text: str) -> None:
    if int(user_id or 0) <= 0:
        return
    send_scheduler_notification(chat_id=user_id, text=text, parse_mode="HTML", timeout=15)


def _notify_user_pending_purchase_canceled(order: dict) -> None:
    plan_name = get_plan_name(order.get("plan_id"))
    text = (
        f"⌛️ سفارش خرید شما برای پلن {plan_name} با نام کاربری <code>{order['username']}</code> "
        f"به دلیل عدم پرداخت در 24 ساعت گذشته لغو شد.\n\n"
        f"اکانت رزروشده دوباره آزاد شد و در صورت نیاز می‌توانید دوباره خرید را ثبت کنید."
    )
    _send_notification(order["user_id"], text)


def _notify_user_pending_renewal_canceled(order: dict) -> None:
    plan_name = get_plan_name(order.get("plan_id"))
    text = (
        f"⌛️ درخواست تمدید شما برای سرویس <code>{order['username']}</code> "
        f"و پلن {plan_name} به دلیل عدم پرداخت در 24 ساعت گذشته لغو شد.\n\n"
        f"در صورت نیاز می‌توانید دوباره از بخش تمدید سرویس اقدام کنید."
    )
    _send_notification(order["user_id"], text)
