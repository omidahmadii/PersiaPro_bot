import sqlite3
import time
from datetime import datetime, timedelta

import jdatetime

from config import DB_PATH
from services.IBSng import get_usage_from_ibs

REQUEST_DELAY_SECONDS = 0.4
PRIORITY_BATCH_SIZE = 160
FAIRNESS_BATCH_SIZE = 90
MAX_STALENESS_MINUTES = 6 * 60
FAST_UPDATE_INTERVAL_MINUTES = 10
MEDIUM_UPDATE_INTERVAL_MINUTES = 60
SLOW_UPDATE_INTERVAL_MINUTES = 120
NEAR_LIMIT_RATIO = 0.90
MID_LIMIT_RATIO = 0.75
DATETIME_FORMAT = "%Y-%m-%d %H:%M:%S"
JALALI_MINUTE_FORMAT = "%Y-%m-%d %H:%M"


def parse_jalali_datetime_flexible(dt_str: str):
    try:
        return jdatetime.datetime.strptime(dt_str, DATETIME_FORMAT).togregorian()
    except ValueError:
        return jdatetime.datetime.strptime(dt_str, JALALI_MINUTE_FORMAT).togregorian()


def get_now_local_jalali_str():
    now_local = datetime.now()
    jalali_now = jdatetime.datetime.fromgregorian(datetime=now_local)
    return jalali_now.strftime(DATETIME_FORMAT)


def _get_limit_mb(volume_gb: int, extra_volume_gb: int, overused_volume_gb: float = 0.0) -> int:
    total_gb = max(float(volume_gb or 0) + float(extra_volume_gb or 0) + float(overused_volume_gb or 0), 0.0)
    return int(round(total_gb * 1024))


def _effective_usage_mb(usage_total_mb: int) -> int:
    return max(int(usage_total_mb or 0), 0)


def _pick_update_interval_minutes(limit_mb: int, usage_effective_mb: int) -> int:
    if limit_mb <= 0:
        return SLOW_UPDATE_INTERVAL_MINUTES

    ratio = float(max(usage_effective_mb, 0)) / float(limit_mb)
    if ratio >= NEAR_LIMIT_RATIO:
        return FAST_UPDATE_INTERVAL_MINUTES
    if ratio >= MID_LIMIT_RATIO:
        return MEDIUM_UPDATE_INTERVAL_MINUTES
    return SLOW_UPDATE_INTERVAL_MINUTES


def _fetch_priority_orders_for_usage_update(cur: sqlite3.Cursor):
    cur.execute(
        f"""
        SELECT
            id,
            username,
            starts_at,
            expires_at,
            usage_last_update,
            volume_gb,
            extra_volume_gb,
            overused_volume_gb,
            usage_total_mb,
            usage_applied_speed
        FROM orders
        WHERE status IN ('active', 'waiting_for_renewal', 'waiting_for_renewal_not_paid')
          AND starts_at IS NOT NULL
          AND username IS NOT NULL
        ORDER BY
            CASE
                WHEN (COALESCE(volume_gb, 0) + COALESCE(extra_volume_gb, 0) + COALESCE(overused_volume_gb, 0)) > 0
                     AND COALESCE(usage_total_mb, 0) >= ((COALESCE(volume_gb, 0) + COALESCE(extra_volume_gb, 0) + COALESCE(overused_volume_gb, 0)) * 1024 * {NEAR_LIMIT_RATIO})
                THEN 0
                WHEN (COALESCE(volume_gb, 0) + COALESCE(extra_volume_gb, 0) + COALESCE(overused_volume_gb, 0)) > 0
                     AND COALESCE(usage_total_mb, 0) >= ((COALESCE(volume_gb, 0) + COALESCE(extra_volume_gb, 0) + COALESCE(overused_volume_gb, 0)) * 1024 * {MID_LIMIT_RATIO})
                THEN 1
                ELSE 2
            END,
            CASE WHEN usage_last_update IS NULL THEN 0 ELSE 1 END,
            usage_last_update ASC
        LIMIT {PRIORITY_BATCH_SIZE}
        """
    )
    return cur.fetchall()


def _fetch_fairness_orders_for_usage_update(cur: sqlite3.Cursor):
    cur.execute(
        f"""
        SELECT
            id,
            username,
            starts_at,
            expires_at,
            usage_last_update,
            volume_gb,
            extra_volume_gb,
            overused_volume_gb,
            usage_total_mb,
            usage_applied_speed
        FROM orders
        WHERE status IN ('active', 'waiting_for_renewal', 'waiting_for_renewal_not_paid')
          AND starts_at IS NOT NULL
          AND username IS NOT NULL
        ORDER BY
            CASE WHEN usage_last_update IS NULL THEN 0 ELSE 1 END,
            usage_last_update ASC
        LIMIT {FAIRNESS_BATCH_SIZE}
        """
    )
    return cur.fetchall()


def update_usages_by_volume():
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()

    priority_orders = _fetch_priority_orders_for_usage_update(cur)
    fairness_orders = _fetch_fairness_orders_for_usage_update(cur)
    orders = []
    seen_order_ids = set()
    for row in priority_orders + fairness_orders:
        order_id = int(row[0] or 0)
        if order_id <= 0 or order_id in seen_order_ids:
            continue
        seen_order_ids.add(order_id)
        orders.append(row)
    now = datetime.now()

    for row in orders:
        (
            order_id,
            username,
            starts_at,
            expires_at,
            usage_last_update,
            volume_gb,
            extra_volume_gb,
            overused_volume_gb,
            usage_total_mb,
            usage_applied_speed,
        ) = row

        if not username:
            continue
        if not starts_at or not expires_at:
            continue

        try:
            exp_dt = parse_jalali_datetime_flexible(expires_at)
        except Exception as exc:
            print(f"[!] invalid expires_at for order_id={order_id}: {expires_at} | {exc}")
            continue

        if exp_dt < now and usage_last_update is not None:
            continue

        limit_mb = _get_limit_mb(
            volume_gb=volume_gb,
            extra_volume_gb=extra_volume_gb,
            overused_volume_gb=float(overused_volume_gb or 0),
        )
        usage_effective_mb = _effective_usage_mb(usage_total_mb=int(usage_total_mb or 0))
        refresh_interval = _pick_update_interval_minutes(limit_mb=limit_mb, usage_effective_mb=usage_effective_mb)

        if usage_last_update:
            try:
                last_update_dt = parse_jalali_datetime_flexible(usage_last_update)
                elapsed_minutes = (now - last_update_dt).total_seconds() / 60
                if elapsed_minutes < refresh_interval and elapsed_minutes < MAX_STALENESS_MINUTES:
                    continue
            except Exception as exc:
                print(f"[!] invalid usage_last_update for order_id={order_id}: {usage_last_update} | {exc}")

        try:
            usage = get_usage_from_ibs(username, starts_at, expires_at)
            if not usage or len(usage) != 2:
                raise ValueError("usage payload is empty")

            sent_mb, recv_mb = usage
            sent_mb = int(sent_mb or 0)
            recv_mb = int(recv_mb or 0)
            total_mb = sent_mb + recv_mb
        except Exception as exc:
            print(f"[!] IBS error for order_id={order_id}, username={username}: {exc}")
            continue

        cur.execute(
            """
            UPDATE orders
            SET
                usage_sent_mb = ?,
                usage_received_mb = ?,
                usage_total_mb = ?,
                remaining_volume_mb = ?,
                usage_last_update = ?
            WHERE id = ?
            """,
            (
                sent_mb,
                recv_mb,
                total_mb,
                max(limit_mb - total_mb, 0),
                get_now_local_jalali_str(),
                order_id,
            ),
        )

        conn.commit()
        print(f"[+] usage updated for order_id={order_id}, username={username}, total_mb={total_mb}")

        time.sleep(REQUEST_DELAY_SECONDS)

    conn.close()


def update_usages():
    # Backward compatible alias
    update_usages_by_volume()


def log_usage():
    update_usages_by_volume()
