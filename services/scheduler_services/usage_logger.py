import sqlite3
from datetime import datetime, timedelta
import jdatetime

from config import DB_PATH
from services.IBSng import get_usage_from_ibs


def sync_orders_to_usages():
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()

    # تمام سفارش‌ها
    cur.execute("SELECT id, username, plan_id, starts_at, expires_at, volume_gb, extra_volume_gb  FROM orders")
    orders = cur.fetchall()

    for order_id, username, plan_id, starts_at, expires_at, volume_gb, extra_volume_gb in orders:

        # چک کن آیا رکورد در order_usages وجود دارد
        cur.execute("SELECT id, starts_at, expires_at FROM order_usages WHERE order_id = ?", (order_id,))
        usage = cur.fetchone()
        if not usage:
            limit_mb = ((volume_gb or 0) + (extra_volume_gb or 0)) * 1024
            # اگه نیست → ایجادش کن
            cur.execute("""
                INSERT INTO order_usages (order_id, username, plan_id, starts_at, expires_at, last_update, sent_mb, received_mb, total_mb, applied_speed, limit_mb)
                VALUES (?, ?, ?, ?, ?, NULL, 0, 0, 0, NULL, ?)
            """, (
                order_id,
                username,
                plan_id,
                starts_at,
                expires_at,
                limit_mb
            ))
            print(f"[+] Usage record created for order_id={order_id}")

        else:
            usage_id, u_starts_at, u_expires_at = usage

            # اگر starts_at یا expires_at توی order_usages خالیه و توی orders مقدار داره → آپدیت کن
            if (not u_starts_at and starts_at) or (not u_expires_at and expires_at):
                cur.execute("""
                    UPDATE order_usages
                    SET starts_at = ?, expires_at = ?
                    WHERE id = ?
                """, (starts_at, expires_at, usage_id))
                print(f"[~] Usage record updated with new dates for order_id={order_id}")

        conn.commit()
    conn.close()


def update_usages():
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()

    cur.execute("SELECT id, order_id, username, plan_id, starts_at, expires_at, last_update FROM order_usages order by last_update , expires_at desc")
    usages = cur.fetchall()

    now = datetime.now()

    for usage_id, order_id, username, plan_id, starts_at, expires_at, last_update in usages:
        # تاریخ پایان (تبدیل از شمسی به میلادی)
        try:
            exp_dt = jdatetime.datetime.strptime(expires_at, "%Y-%m-%d %H:%M").togregorian()
        except Exception as e:
            continue

        # اگر سرویس منقضی شده و حداقل یکبار آپدیت شده → دیگه لازم نیست
        if exp_dt < now and last_update is not None:
            continue

        # بررسی فاصله ۱۲ ساعته برای سرویس‌های فعال
        if last_update:
            last_update_dt = datetime.fromisoformat(last_update)
            if now - last_update_dt < timedelta(hours=12):
                continue

        # گرفتن مصرف از IBSng
        sent_mb, recv_mb = get_usage_from_ibs(username, starts_at, expires_at)
        total_mb = sent_mb + recv_mb

        cur.execute("""
            UPDATE order_usages
            SET sent_mb = ?, received_mb = ?, total_mb = ?, last_update = ?
            WHERE id = ?
        """, (
            sent_mb,
            recv_mb,
            total_mb,
            datetime.utcnow().isoformat(),
            usage_id
        ))
        # print(f"[+] Usage updated for order_id={order_id}")
        conn.commit()
    conn.close()


def log_usage():
    sync_orders_to_usages()
    update_usages()
