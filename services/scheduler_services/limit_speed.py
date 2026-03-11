import sqlite3
from datetime import datetime
from typing import Optional

import jdatetime
import requests

import config
from config import DB_PATH, ADMINS
from services.IBSng import (
    get_user_radius_attribute,
    apply_user_radius_attrs,
    get_group_radius_attribute,
)

TOKEN = config.BOT_TOKEN
LIMIT_SPEED = "64k"


def format_limit_notification(username: str, total_mb: int, limit_mb: int) -> str:
    total_gb = round((total_mb or 0) / 1024, 2)
    limit_gb = round((limit_mb or 0) / 1024, 2)

    return (
        f"🔔 کاربر گرامی\n"
        f"⚠️ به دلیل عبور از آستانه مصرف منصفانه، "
        f"سرعت سرویس <b>{username}</b> شما به <b>64K</b> محدود شده است.\n\n"
        f"📊 آستانه مصرف منصفانه: <b>{limit_gb} GB</b>\n"
        f"📈 میزان مصرف شما: <b>{total_gb} GB</b>\n\n"
        f"برای بازگشت به سرعت عادی، سرویس خود را تمدید کرده و سپس گزینه "
        f"<b>فعال‌سازی سرویس ذخیره</b> را از پنل کاربری انتخاب کنید."
    )


def format_admin_limit_notification(user_id: int, username: str, total_mb: int, limit_mb: int, speed: str) -> str:
    total_gb = round((total_mb or 0) / 1024, 2)
    limit_gb = round((limit_mb or 0) / 1024, 2)

    return (
        f"🚨 کاربر <a href='tg://user?id={user_id}'>{user_id}</a>\n"
        f"به دلیل عبور از آستانه مصرف منصفانه محدود شد.\n\n"
        f"👤 یوزرنیم سرویس: <b>{username}</b>\n"
        f"⚡ سرعت اعمال‌شده: <b>{speed}</b>\n"
        f"📊 آستانه مصرف: <b>{limit_gb} GB</b>\n"
        f"📈 مصرف کاربر: <b>{total_gb} GB</b>"
    )


def send_notification(user_id: int, text: str):
    url = f"https://api.telegram.org/bot{TOKEN}/sendMessage"
    data = {
        "chat_id": user_id,
        "text": text,
        "parse_mode": "HTML",
    }
    response = requests.post(url, data=data, timeout=15)
    if not response.ok:
        raise Exception(f"Telegram API error: {response.text}")


def get_rate_limit(speed: str) -> str:
    rate_limit_map = {
        "8m": 'Rate-Limit="8m/8m"',
        "6m": 'Rate-Limit="6m/6m"',
        "4m": 'Rate-Limit="4m/4m"',
        "2m": 'Rate-Limit="2m/2m"',
        "1m": 'Rate-Limit="1m/1m"',
        "512k": 'Rate-Limit="512k/512k"',
        "256k": 'Rate-Limit="256k/256k"',
        "128k": 'Rate-Limit="128k/128k"',
        "64k": 'Rate-Limit="64k/64k"',
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
        cur.execute("""
            UPDATE orders
            SET usage_applied_speed = ?
            WHERE id = ?
        """, (applied_speed, order_id))
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
        cur.execute("""
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
                status
            FROM orders
            WHERE status = 'active'
        """)
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
            status,
        ) = row

        if not username or not user_id:
            continue

        try:
            start_dt = shamsi_to_gregorian(starts_at)
            expire_dt = shamsi_to_gregorian(expires_at)
        except Exception as e:
            print(f"[!] invalid date for order_id={order_id}: {e}")
            continue

        if start_dt and start_dt > now:
            continue

        if expire_dt and expire_dt < now:
            continue

        limit_mb = ((volume_gb or 0) + (extra_volume_gb or 0)) * 1024
        total_mb = usage_total_mb or 0

        valid_rows.append({
            "order_id": order_id,
            "user_id": user_id,
            "username": str(username),
            "total_mb": total_mb,
            "applied_speed": normalize_speed(usage_applied_speed),
            "limit_mb": limit_mb,
        })

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

    for row in rows:
        order_id = row["order_id"]
        user_id = row["user_id"]
        username = row["username"]
        total_mb = row["total_mb"]
        applied_speed = row["applied_speed"]
        limit_mb = row["limit_mb"]

        if limit_mb <= 0:
            continue

        if total_mb < limit_mb:
            continue

        # قبلا لیمیت شده
        if applied_speed == LIMIT_SPEED:
            continue

        try:

            # اعمال محدودیت سرعت
            apply_limit(username=username, order_id=order_id, speed=LIMIT_SPEED)

            # پیام کاربر
            user_text = format_limit_notification(
                username=username,
                total_mb=total_mb,
                limit_mb=limit_mb,
            )

            # پیام ادمین
            admin_text = format_admin_limit_notification(
                user_id=user_id,
                username=username,
                total_mb=total_mb,
                limit_mb=limit_mb,
                speed=LIMIT_SPEED,
            )

            # ارسال به کاربر
            try:
                send_notification(user_id=user_id, text=user_text)
            except Exception as e:
                print(f"[!] failed to notify user {user_id}: {e}")

            # ارسال به ادمین ها
            for admin in ADMINS:
                try:
                    send_notification(user_id=admin, text=admin_text)
                except Exception as e:
                    print(f"[!] failed to notify admin {admin}: {e}")

        except Exception as e:
            print(f"[!] failed to apply limit for order_id={order_id}, username={username}: {e}")
