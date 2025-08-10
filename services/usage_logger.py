import sqlite3
from datetime import datetime, timedelta
import asyncio
from services.database_services.usage_logger_DB import get_orders, get_last_update, update_order_usages, \
    insert_order_usages
from services.IBSng_services.usage_logger_IBS import get_usage_from_ibs


def should_update(last_update: str, hours=2) -> bool:
    if not last_update:
        return True
    try:
        last = datetime.fromisoformat(last_update)
        return datetime.now() - last > timedelta(hours=hours)
    except Exception:
        return True


def log_usage():
    orders = get_orders()
    for order in orders:
        order_id = order["id"]
        username = order["username"]
        plan_id = order["plan_id"]
        starts_at = order["starts_at"]
        expires_at = order["expires_at"]

        last_update = get_last_update(order_id)
        if should_update(last_update, hours=4):
            sent_mb, recv_mb = get_usage_from_ibs(username, starts_at, expires_at)

            total_mb = sent_mb + recv_mb
            print(username, total_mb, sent_mb, recv_mb)

            now = datetime.now().isoformat()
            if last_update:
                update_order_usages(now, sent_mb, recv_mb, total_mb, order_id)
            else:
                insert_order_usages(order_id, username, plan_id, starts_at, expires_at, now, sent_mb, recv_mb, total_mb)


