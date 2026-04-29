import sqlite3
from datetime import datetime
from typing import Optional

import jdatetime

from config import ADMINS, DB_PATH
from services.IBSng import (
    apply_user_radius_attrs,
    get_group_radius_attribute,
    get_user_radius_attribute,
    unlock_user,
)
from services.scheduler_services.telegram_safe import send_scheduler_notification
from services.usage_policy import (
    get_limit_speed_display,
    get_limit_speed_value,
    get_post_limit_actions_text,
)

PRE_LIMIT_RATIO = 0.95
PRE_LIMIT_SPEED = "4m"


def current_limit_speed() -> str:
    return normalize_speed(get_limit_speed_value()) or "64k"


def current_pre_limit_speed() -> str:
    return normalize_speed(PRE_LIMIT_SPEED) or PRE_LIMIT_SPEED


def _speed_label(speed: str) -> str:
    normalized = normalize_speed(speed) or str(speed)
    if normalized.endswith("m"):
        return f"{normalized[:-1]} مگابیت"
    if normalized.endswith("k"):
        return f"{normalized[:-1]} کیلوبیت"
    return normalized


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


def format_pre_limit_notification(username: str, total_mb: int, limit_mb: int, speed: str) -> str:
    total_gb = round((total_mb or 0) / 1024, 2)
    limit_gb = round((limit_mb or 0) / 1024, 2)
    _ = speed

    return (
        f"🔔 کاربر گرامی\n"
        f"⚠️ مصرف سرویس <b>{username}</b> شما از 95٪ عبور کرده است.\n"
        f"⏳ مصرف این سرویس به آستانه اتمام حجم رسیده است.\n\n"
        f"📦 حجم کل این دوره: <b>{limit_gb} GB</b>\n"
        f"📈 مصرف شما: <b>{total_gb} GB</b>\n\n"
        f"{get_post_limit_actions_text()}"
    )


def format_admin_pre_limit_notification(
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
        f"🔔 کاربر <a href='tg://user?id={user_id}'>{user_id}</a>\n"
        f"از آستانه 95٪ مصرف عبور کرد و سرعت موقت اعمال شد.\n\n"
        f"👤 یوزرنیم سرویس: <b>{username}</b>\n"
        f"⚡ سرعت اعمال‌شده: <b>{_speed_label(speed)}</b>\n"
        f"📅 شروع سرویس: <b>{starts_at or '-'}</b>\n"
        f"⏳ پایان سرویس: <b>{expires_at or '-'}</b>\n"
        f"📊 حجم کل: <b>{limit_gb} GB</b>\n"
        f"📈 مصرف کاربر: <b>{total_gb} GB</b>"
    )


def send_notification(user_id: int, text: str):
    return send_scheduler_notification(chat_id=user_id, text=text, parse_mode="HTML", timeout=15)


def get_rate_limit(speed: str) -> str:
    rate_limit_map = {
        "16k": 'Rate-Limit="16k/16k"',
        "32k": 'Rate-Limit="32k/32k"',
        "64k": 'Rate-Limit="64k/64k"',
        "128k": 'Rate-Limit="128k/128k"',
        "256k": 'Rate-Limit="256k/256k"',
        "512k": 'Rate-Limit="512k/512k"',
        "4m": 'Rate-Limit="4m/4m"',
        "4096k": 'Rate-Limit="4m/4m"',
    }

    speed = (speed or "").strip().lower()
    if speed not in rate_limit_map:
        raise ValueError(f"Unsupported speed: {speed}")

    return rate_limit_map[speed]


def normalize_speed(speed: Optional[str]) -> Optional[str]:
    if not speed:
        return None
    return speed.strip().lower()


def speed_to_kbps(speed: Optional[str]) -> Optional[int]:
    normalized = normalize_speed(speed)
    if not normalized:
        return None
    if normalized.endswith("k"):
        try:
            return int(float(normalized[:-1]))
        except ValueError:
            return None
    if normalized.endswith("m"):
        try:
            return int(float(normalized[:-1]) * 1024)
        except ValueError:
            return None
    return None


def is_same_speed(left: Optional[str], right: Optional[str]) -> bool:
    left_norm = normalize_speed(left)
    right_norm = normalize_speed(right)
    if left_norm == right_norm:
        return True

    left_kbps = speed_to_kbps(left_norm)
    right_kbps = speed_to_kbps(right_norm)
    if left_kbps is None or right_kbps is None:
        return False
    return left_kbps == right_kbps


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
                overused_volume_gb,
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
            overused_volume_gb,
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

        effective_total_mb = max(int(usage_total_mb or 0), 0)
        limit_mb = int(round((float(volume_gb or 0) + float(extra_volume_gb or 0) + float(overused_volume_gb or 0)) * 1024))
        valid_rows.append(
            {
                "order_id": order_id,
                "user_id": user_id,
                "username": str(username),
                "total_mb": effective_total_mb,
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
    pre_limit_speed_value = current_pre_limit_speed()

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

        # Migrate previously locked users to the new policy: always keep them online.
        if usage_lock_applied:
            try:
                unlock_user(username=username)
                save_usage_lock_state(order_id=order_id, locked=False)
            except Exception as exc:
                print(f"[!] failed to unlock order_id={order_id}, username={username}: {exc}")

        usage_ratio = float(total_mb) / float(limit_mb)
        target_speed = None
        is_hard_limit = False
        if total_mb >= limit_mb:
            target_speed = limit_speed_value
            is_hard_limit = True
        elif usage_ratio >= PRE_LIMIT_RATIO:
            target_speed = pre_limit_speed_value
        else:
            continue

        if is_same_speed(applied_speed, target_speed):
            continue

        try:
            apply_limit(username=username, order_id=order_id, speed=target_speed)

            if is_hard_limit:
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

                if int(user_id or 0) > 0:
                    try:
                        send_notification(user_id=user_id, text=user_text)
                    except Exception as exc:
                        print(f"[!] failed to notify user {user_id}: {exc}")

                for admin in ADMINS:
                    try:
                        send_notification(user_id=admin, text=admin_text)
                    except Exception as exc:
                        print(f"[!] failed to notify admin {admin}: {exc}")
            else:
                admin_text = format_admin_pre_limit_notification(
                    user_id=user_id,
                    username=username,
                    total_mb=total_mb,
                    limit_mb=limit_mb,
                    speed=target_speed,
                    starts_at=starts_at,
                    expires_at=expires_at,
                )

                for admin in ADMINS:
                    try:
                        send_notification(user_id=admin, text=admin_text)
                    except Exception as exc:
                        print(f"[!] failed pre-limit notify admin {admin}: {exc}")

        except Exception as exc:
            print(f"[!] failed to apply limit for order_id={order_id}, username={username}: {exc}")
