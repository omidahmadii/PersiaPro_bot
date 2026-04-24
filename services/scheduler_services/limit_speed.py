import sqlite3
from datetime import datetime
from typing import Optional

import jdatetime

from config import ADMINS, DB_PATH
from services.IBSng import (
    apply_user_radius_attrs,
    get_group_radius_attribute,
    get_user_radius_attribute,
    lock_user,
    unlock_user,
)
from services.scheduler_services.telegram_safe import send_scheduler_notification
from services.usage_policy import (
    get_limit_speed_display,
    get_limit_speed_value,
    get_post_limit_actions_text,
)

OVERAGE_LOCK_THRESHOLD_MB = 200


def current_limit_speed() -> str:
    return normalize_speed(get_limit_speed_value()) or "64k"


def format_limit_notification(username: str, total_mb: int, limit_mb: int) -> str:
    total_gb = round((total_mb or 0) / 1024, 2)
    limit_gb = round((limit_mb or 0) / 1024, 2)

    return (
        f"🔔 کاربر گرامی\n"
        f"⚠️ چون حجم سرویس <b>{username}</b> شما به پایان رسیده، سرعت آن محدود شد.\n\n"
        f"📊 حجم کل این دوره: <b>{limit_gb} GB</b>\n"
        f"📈 مصرف شما: <b>{total_gb} GB</b>\n\n"
        f"{get_post_limit_actions_text()}"
    )


def format_admin_limit_notification(
    user_id: int,
    username: str,
    total_mb: int,
    limit_mb: int,
    speed: str,
    starts_at: str,
    expires_at: str,
) -> str:
    total_gb = round((total_mb or 0) / 1024, 2)
    limit_gb = round((limit_mb or 0) / 1024, 2)

    return (
        f"🚨 کاربر <a href='tg://user?id={user_id}'>{user_id}</a>\n"
        f"به دلیل اتمام حجم، محدود شد.\n\n"
        f"👤 یوزرنیم سرویس: <b>{username}</b>\n"
        f"⚡ سرعت اعمال‌شده: <b>{speed}</b>\n"
        f"📅 شروع سرویس: <b>{starts_at or '-'}</b>\n"
        f"⏳ پایان سرویس: <b>{expires_at or '-'}</b>\n"
        f"📊 حجم کل: <b>{limit_gb} GB</b>\n"
        f"📈 مصرف کاربر: <b>{total_gb} GB</b>"
    )


def format_lock_notification(username: str, total_mb: int, limit_mb: int, overage_mb: int) -> str:
    total_gb = round((total_mb or 0) / 1024, 2)
    limit_gb = round((limit_mb or 0) / 1024, 2)
    overage_gb = round((overage_mb or 0) / 1024, 2)
    return (
        f"🚫 کاربر گرامی\n"
        f"⚠️ سرویس <b>{username}</b> به دلیل عبور از حجم مجاز قفل شد.\n\n"
        f"📊 حجم کل این دوره: <b>{limit_gb} GB</b>\n"
        f"📈 مصرف شما: <b>{total_gb} GB</b>\n"
        f"➕ اضافه‌مصرف: <b>{overage_gb} GB</b>\n\n"
        f"برای فعال‌سازی مجدد، خرید حجم اضافه انجام دهید یا سرویس را مجددا تمدید کنید."
    )


def format_admin_lock_notification(
    user_id: int,
    username: str,
    total_mb: int,
    limit_mb: int,
    overage_mb: int,
    starts_at: str,
    expires_at: str,
) -> str:
    total_gb = round((total_mb or 0) / 1024, 2)
    limit_gb = round((limit_mb or 0) / 1024, 2)
    overage_gb = round((overage_mb or 0) / 1024, 2)
    threshold_gb = round(OVERAGE_LOCK_THRESHOLD_MB / 1024, 2)
    return (
        f"⛔ کاربر <a href='tg://user?id={user_id}'>{user_id}</a>\n"
        f"به دلیل اضافه‌مصرف، قفل شد.\n\n"
        f"👤 یوزرنیم سرویس: <b>{username}</b>\n"
        f"📅 شروع سرویس: <b>{starts_at or '-'}</b>\n"
        f"⏳ پایان سرویس: <b>{expires_at or '-'}</b>\n"
        f"📊 حجم کل: <b>{limit_gb} GB</b>\n"
        f"📈 مصرف کاربر: <b>{total_gb} GB</b>\n"
        f"➕ اضافه‌مصرف: <b>{overage_gb} GB</b> (بیشتر از {threshold_gb} GB)"
    )


def send_notification(user_id: int, text: str):
    return send_scheduler_notification(chat_id=user_id, text=text, parse_mode="HTML", timeout=15)


def get_rate_limit(speed: str) -> str:
    rate_limit_map = {
        "32k": 'Rate-Limit="32k/32k"',
        "64k": 'Rate-Limit="64k/64k"',
        "128k": 'Rate-Limit="128k/128k"',
        "256k": 'Rate-Limit="256k/256k"',
        "512k": 'Rate-Limit="512k/512k"',
    }

    speed = (speed or "").strip().lower()
    if speed not in rate_limit_map:
        raise ValueError(f"Unsupported speed: {speed}")

    return rate_limit_map[speed]


def normalize_speed(speed: Optional[str]) -> Optional[str]:
    if not speed:
        return None
    return speed.strip().lower()


def save_applied_speed_to_db(order_id: int, applied_speed: Optional[str]):
    with sqlite3.connect(DB_PATH) as conn:
        cur = conn.cursor()
        cur.execute(
            """
            UPDATE orders
            SET usage_applied_speed = ?
            WHERE id = ?
            """,
            (applied_speed, order_id),
        )
        conn.commit()


def save_usage_lock_state(order_id: int, locked: bool):
    with sqlite3.connect(DB_PATH) as conn:
        cur = conn.cursor()
        cur.execute(
            """
            UPDATE orders
            SET usage_lock_applied = ?
            WHERE id = ?
            """,
            (1 if locked else 0, order_id),
        )
        conn.commit()


def shamsi_to_gregorian(shamsi_value) -> Optional[datetime]:
    if not shamsi_value:
        return None

    if isinstance(shamsi_value, bytes):
        shamsi_value = shamsi_value.decode("utf-8", errors="ignore")

    shamsi_str = str(shamsi_value).strip()
    if not shamsi_str:
        return None

    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M"):
        try:
            return jdatetime.datetime.strptime(shamsi_str, fmt).togregorian()
        except ValueError:
            pass

    raise ValueError(f"Invalid Jalali datetime format: {shamsi_str}")


def get_orders_for_limitation():
    with sqlite3.connect(DB_PATH) as conn:
        cur = conn.cursor()
        cur.execute(
            """
            SELECT
                id,
                user_id,
                username,
                starts_at,
                expires_at,
                volume_gb,
                extra_volume_gb,
                usage_total_mb,
                usage_applied_speed,
                usage_lock_applied
            FROM orders
            WHERE status IN ('active', 'waiting_for_renewal', 'waiting_for_renewal_not_paid')
            """
        )
        rows = cur.fetchall()

    valid_rows = []
    now = datetime.now()

    for row in rows:
        (
            order_id,
            user_id,
            username,
            starts_at,
            expires_at,
            volume_gb,
            extra_volume_gb,
            usage_total_mb,
            usage_applied_speed,
            usage_lock_applied,
        ) = row
        if not username or not user_id:
            continue

        try:
            start_dt = shamsi_to_gregorian(starts_at)
            expire_dt = shamsi_to_gregorian(expires_at)
        except Exception as exc:
            print(f"[!] invalid date for order_id={order_id}: {exc}")
            continue

        if start_dt and start_dt > now:
            continue
        if expire_dt and expire_dt < now:
            continue

        if isinstance(starts_at, bytes):
            starts_at = starts_at.decode("utf-8", errors="ignore")
        if isinstance(expires_at, bytes):
            expires_at = expires_at.decode("utf-8", errors="ignore")

        limit_mb = ((volume_gb or 0) + (extra_volume_gb or 0)) * 1024
        valid_rows.append(
            {
                "order_id": order_id,
                "user_id": user_id,
                "username": str(username),
                "total_mb": int(usage_total_mb or 0),
                "applied_speed": normalize_speed(usage_applied_speed),
                "usage_lock_applied": int(usage_lock_applied or 0),
                "limit_mb": limit_mb,
                "starts_at": starts_at,
                "expires_at": expires_at,
            }
        )

    return valid_rows


def apply_limit(username: str, order_id: int, speed: str):
    speed = normalize_speed(speed)
    group_radius_attr = get_group_radius_attribute(username)

    if not group_radius_attr:
        radius_attrs = get_rate_limit(speed)
        apply_user_radius_attrs(username, radius_attrs)
        print(f"[+] limit applied to {username}: {radius_attrs}")
    else:
        group = group_radius_attr.get("Group")
        if group:
            rate_limit = get_rate_limit(speed)
            radius_attrs = f'Group="{group}"\n{rate_limit}'
            apply_user_radius_attrs(username, radius_attrs)
            print(f"[+] limit applied to {username}: {radius_attrs}")
        else:
            radius_attrs = get_rate_limit(speed)
            apply_user_radius_attrs(username, radius_attrs)
            print(f"[+] limit applied to {username}: {radius_attrs}")

    updated_attr = get_user_radius_attribute(username)
    if updated_attr and updated_attr.get("Rate-Limit"):
        actual_rate_limit = updated_attr["Rate-Limit"].split("/")[0].strip().lower()
        save_applied_speed_to_db(order_id=order_id, applied_speed=actual_rate_limit)
    else:
        print(f"[!] failed to fetch updated attributes for {username}")


def limit_speed():
    rows = get_orders_for_limitation()
    limit_speed_value = current_limit_speed()

    for row in rows:
        order_id = row["order_id"]
        user_id = row["user_id"]
        username = row["username"]
        total_mb = row["total_mb"]
        applied_speed = row["applied_speed"]
        usage_lock_applied = bool(row.get("usage_lock_applied"))
        limit_mb = row["limit_mb"]
        starts_at = row["starts_at"]
        expires_at = row["expires_at"]

        if limit_mb <= 0:
            continue
        overage_mb = max(total_mb - limit_mb, 0)

        if overage_mb >= OVERAGE_LOCK_THRESHOLD_MB:
            if usage_lock_applied:
                continue

            try:
                lock_user(username=username)
                save_usage_lock_state(order_id=order_id, locked=True)
            except Exception as exc:
                print(f"[!] failed to lock order_id={order_id}, username={username}: {exc}")
                continue

            user_text = format_lock_notification(
                username=username,
                total_mb=total_mb,
                limit_mb=limit_mb,
                overage_mb=overage_mb,
            )
            admin_text = format_admin_lock_notification(
                user_id=user_id,
                username=username,
                total_mb=total_mb,
                limit_mb=limit_mb,
                overage_mb=overage_mb,
                starts_at=starts_at,
                expires_at=expires_at,
            )

            try:
                send_notification(user_id=user_id, text=user_text)
            except Exception as exc:
                print(f"[!] failed to notify user {user_id}: {exc}")

            for admin in ADMINS:
                try:
                    send_notification(user_id=admin, text=admin_text)
                except Exception as exc:
                    print(f"[!] failed to notify admin {admin}: {exc}")

            continue

        if usage_lock_applied:
            try:
                unlock_user(username=username)
                save_usage_lock_state(order_id=order_id, locked=False)
            except Exception as exc:
                print(f"[!] failed to unlock order_id={order_id}, username={username}: {exc}")

        if total_mb < limit_mb:
            continue
        if applied_speed == limit_speed_value:
            continue

        try:
            apply_limit(username=username, order_id=order_id, speed=limit_speed_value)

            user_text = format_limit_notification(
                username=username,
                total_mb=total_mb,
                limit_mb=limit_mb,
            )
            admin_text = format_admin_limit_notification(
                user_id=user_id,
                username=username,
                total_mb=total_mb,
                limit_mb=limit_mb,
                speed=get_limit_speed_display(limit_speed_value),
                starts_at=starts_at,
                expires_at=expires_at,
            )

            try:
                send_notification(user_id=user_id, text=user_text)
            except Exception as exc:
                print(f"[!] failed to notify user {user_id}: {exc}")

            for admin in ADMINS:
                try:
                    send_notification(user_id=admin, text=admin_text)
                except Exception as exc:
                    print(f"[!] failed to notify admin {admin}: {exc}")

        except Exception as exc:
            print(f"[!] failed to apply limit for order_id={order_id}, username={username}: {exc}")
