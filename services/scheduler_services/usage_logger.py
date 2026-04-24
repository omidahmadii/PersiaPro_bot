import sqlite3
import time
from datetime import datetime, timedelta

import jdatetime

from config import DB_PATH
from services.IBSng import get_usage_from_ibs

UPDATE_INTERVAL_HOURS = 1
REQUEST_DELAY_SECONDS = 1
DATETIME_FORMAT = "%Y-%m-%d %H:%M:%S"
JALALI_MINUTE_FORMAT = "%Y-%m-%d %H:%M"


def parse_jalali_datetime(dt_str: str):
    return jdatetime.datetime.strptime(dt_str, DATETIME_FORMAT).togregorian()


def parse_jalali_datetime_flexible(dt_str: str):
    """
    برای اینکه هم فرمت ثانیه‌دار را بخواند هم فرمت قدیمی بدون ثانیه را
    """
    try:
        return jdatetime.datetime.strptime(dt_str, DATETIME_FORMAT).togregorian()
    except ValueError:
        return jdatetime.datetime.strptime(dt_str, JALALI_MINUTE_FORMAT).togregorian()


def get_now_local_jalali_str():
    """
    زمان فعلی سیستم را به جلالی برمی‌گرداند
    مثال: 1404-12-18 03:19:45
    """
    now_local = datetime.now()
    jalali_now = jdatetime.datetime.fromgregorian(datetime=now_local)
    return jalali_now.strftime(DATETIME_FORMAT)


def update_usages():
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()

    cur.execute("""
        SELECT
            id,
            username,
            starts_at,
            expires_at,
            usage_last_update
        FROM orders
        WHERE status in ( 'active','waiting_for_renewal' ) and starts_at is not NULL
        ORDER BY
            CASE WHEN usage_last_update IS NULL THEN 0 ELSE 1 END,
            usage_last_update ASC
            limit 7
    """)
    orders = cur.fetchall()

    now = datetime.now()

    for order_id, username, starts_at, expires_at, usage_last_update in orders:
        if not username:
            print(f"[!] order_id={order_id} has no username")
            continue

        if not starts_at or not expires_at:
            print(f"[!] order_id={order_id} missing starts_at/expires_at")
            continue

        try:
            exp_dt = parse_jalali_datetime_flexible(expires_at)
        except Exception as e:
            print(f"[!] invalid expires_at for order_id={order_id}: {expires_at} | {e}")
            continue

        # اگر سرویس منقضی شده و قبلا یکبار آپدیت شده، دیگر سراغش نرو
        if exp_dt < now and usage_last_update is not None:
            continue

        if usage_last_update:
            try:
                last_update_dt = parse_jalali_datetime_flexible(usage_last_update)
                if now - last_update_dt < timedelta(hours=UPDATE_INTERVAL_HOURS):
                    continue
            except Exception as e:
                print(f"[!] invalid usage_last_update for order_id={order_id}: {usage_last_update} | {e}")
                # اگر فرمت خراب بود، می‌گذاریم دوباره آپدیت شود

        try:
            sent_mb, recv_mb = get_usage_from_ibs(username, starts_at, expires_at)
            sent_mb = sent_mb or 0
            recv_mb = recv_mb or 0
            total_mb = sent_mb + recv_mb
        except Exception as e:
            print(f"[!] IBS error for order_id={order_id}, username={username}: {e}")
            continue

        cur.execute("""
            UPDATE orders
            SET
                usage_sent_mb = ?,
                usage_received_mb = ?,
                usage_total_mb = ?,
                usage_last_update = ?
            WHERE id = ?
        """, (
            sent_mb,
            recv_mb,
            total_mb,
            get_now_local_jalali_str(),
            order_id
        ))

        conn.commit()
        print(f"[+] usage updated for order_id={order_id}, username={username}")
        time.sleep(REQUEST_DELAY_SECONDS)

    conn.close()


def update_usages_by_volume():
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()

    cur.execute("""
            SELECT
                id,
                username,
                starts_at,
                expires_at,
                usage_last_update,
                volume_gb
            FROM orders
            WHERE status in ( 'active','waiting_for_renewal' ) and starts_at is not NULL
            ORDER BY
                CASE WHEN usage_last_update IS NULL THEN 0 ELSE 1 END,
                volume_gb, usage_last_update ASC 
                limit 3
        """)
    orders = cur.fetchall()

    now = datetime.now()

    for order_id, username, starts_at, expires_at, usage_last_update, volume_gb in orders:
        if not username:
            print(f"[!] order_id={order_id} has no username")
            continue

        if not starts_at or not expires_at:
            print(f"[!] order_id={order_id} missing starts_at/expires_at")
            continue

        try:
            exp_dt = parse_jalali_datetime_flexible(expires_at)
        except Exception as e:
            print(f"[!] invalid expires_at for order_id={order_id}: {expires_at} | {e}")
            continue

        # اگر سرویس منقضی شده و قبلا یکبار آپدیت شده، دیگر سراغش نرو
        if exp_dt < now and usage_last_update is not None:
            continue

        if usage_last_update:
            try:
                last_update_dt = parse_jalali_datetime_flexible(usage_last_update)
                if now - last_update_dt < timedelta(hours=UPDATE_INTERVAL_HOURS):
                    continue
            except Exception as e:
                print(f"[!] invalid usage_last_update for order_id={order_id}: {usage_last_update} | {e}")
                # اگر فرمت خراب بود، می‌گذاریم دوباره آپدیت شود

        try:
            sent_mb, recv_mb = get_usage_from_ibs(username, starts_at, expires_at)
            sent_mb = sent_mb or 0
            recv_mb = recv_mb or 0
            total_mb = sent_mb + recv_mb
        except Exception as e:
            print(f"[!] IBS error for order_id={order_id}, username={username}: {e}")
            continue

        cur.execute("""
                UPDATE orders
                SET
                    usage_sent_mb = ?,
                    usage_received_mb = ?,
                    usage_total_mb = ?,
                    usage_last_update = ?
                WHERE id = ?
            """, (
            sent_mb,
            recv_mb,
            total_mb,
            get_now_local_jalali_str(),
            order_id
        ))

        conn.commit()
        print(f"[+] usage updated for order_id={order_id}, username={username}")
        time.sleep(REQUEST_DELAY_SECONDS)

    conn.close()


def update_usages_by_expires_at():
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()

    cur.execute("""
            SELECT
                id,
                username,
                starts_at,
                expires_at,
                usage_last_update
            FROM orders
            WHERE status in ( 'active','waiting_for_renewal' ) and starts_at is not NULL
            ORDER BY
                CASE WHEN usage_last_update IS NULL THEN 0 ELSE 1 END,
                expires_at, usage_last_update ASC 
                limit 1
        """)
    orders = cur.fetchall()

    now = datetime.now()

    for order_id, username, starts_at, expires_at, usage_last_update in orders:
        if not username:
            print(f"[!] order_id={order_id} has no username")
            continue

        if not starts_at or not expires_at:
            print(f"[!] order_id={order_id} missing starts_at/expires_at")
            continue

        try:
            exp_dt = parse_jalali_datetime_flexible(expires_at)
        except Exception as e:
            print(f"[!] invalid expires_at for order_id={order_id}: {expires_at} | {e}")
            continue

        # اگر سرویس منقضی شده و قبلا یکبار آپدیت شده، دیگر سراغش نرو
        if exp_dt < now and usage_last_update is not None:
            continue

        if usage_last_update:
            try:
                last_update_dt = parse_jalali_datetime_flexible(usage_last_update)
                if now - last_update_dt < timedelta(hours=UPDATE_INTERVAL_HOURS):
                    continue
            except Exception as e:
                print(f"[!] invalid usage_last_update for order_id={order_id}: {usage_last_update} | {e}")
                # اگر فرمت خراب بود، می‌گذاریم دوباره آپدیت شود

        try:
            sent_mb, recv_mb = get_usage_from_ibs(username, starts_at, expires_at)
            sent_mb = sent_mb or 0
            recv_mb = recv_mb or 0
            total_mb = sent_mb + recv_mb
        except Exception as e:
            print(f"[!] IBS error for order_id={order_id}, username={username}: {e}")
            continue

        cur.execute("""
                UPDATE orders
                SET
                    usage_sent_mb = ?,
                    usage_received_mb = ?,
                    usage_total_mb = ?,
                    usage_last_update = ?
                WHERE id = ?
            """, (
            sent_mb,
            recv_mb,
            total_mb,
            get_now_local_jalali_str(),
            order_id
        ))

        conn.commit()
        print(f"[+] usage updated for order_id={order_id}, username={username}")
        time.sleep(REQUEST_DELAY_SECONDS)

    conn.close()


def log_usage():
    update_usages()
    update_usages_by_volume()
    update_usages_by_expires_at()

