from datetime import datetime, timedelta

from services.db import (
    get_waiting_for_payment_orders, update_order_status
)


def cancel_not_paid_waiting_for_payment_orders() -> None:
    for waiting_for_payment in get_waiting_for_payment_orders():
        _maybe_not_payed(waiting_for_payment)


def _maybe_not_payed(waiting_for_payment: dict) -> None:
    created_at = waiting_for_payment['created_at']
    # تبدیل رشته به datetime
    created_time = datetime.fromisoformat(created_at)

    # زمان فعلی
    now = datetime.now()

    # چک کنیم آیا بیشتر از 3 روز گذشته
    if now - created_time > timedelta(days=3):
        order_id = waiting_for_payment['id']
        previous: int | None = waiting_for_payment.get("is_renewal_of_order")
        if not previous:
            return  # No linked order → nothing to do
        update_order_status(order_id=previous, new_status="active")
        update_order_status(order_id=order_id, new_status="canceled")
