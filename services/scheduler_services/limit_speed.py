import sqlite3
from datetime import datetime

import jdatetime
import requests

import config
from config import DB_PATH
from services.IBSng import get_user_radius_attribute, apply_user_radius_attrs, get_group_radius_attribute
from typing import Optional
from aiogram import Bot
from config import ADMINS  # اطمینان حاصل کن ADMIN_IDS در config لیست آیدی ادمین‌هاست

TOKEN = config.BOT_TOKEN


def format_limit_notification(username: str, total_mb: int, limit_mb: int) -> str:
    total_gb = round(total_mb / 1024, 2)  # تبدیل به گیگ
    limit_gb = round(limit_mb / 1024, 2)

    text = (
        f"🔔 کاربر گرامی\n"
        f"⚠️ به دلیل عبور از آستانه مصرف منصفانه\n"
        f" سرعت سرویس "
        f"<b>{username}</b>"
        f" شما محدود شده است."
        f"\n\n"
        f"📊 آستانه مصرف منصفانه: <b>{limit_gb} GB</b>\n"
        f"📈 میزان مصرف شما: <b>{total_gb} GB</b>\n\n"

    )
    return text


def send_notification(user_id, text):
    """ارسال پیام به کاربر در تلگرام"""
    url = f"https://api.telegram.org/bot{TOKEN}/sendMessage"
    data = {
        "chat_id": user_id,
        "text": text,
        "parse_mode": "HTML"
    }
    response = requests.post(url, data=data)
    if not response.ok:
        raise Exception(f"Telegram API error: {response.text}")


def get_rate_limit(speed):
    rate_limit = {
        '8m': "Rate-Limit=\"8m/8m\"",
        '6m': "Rate-Limit=\"6m/6m\"",
        '4m': "Rate-Limit=\"4m/4m\"",
        '2m': "Rate-Limit=\"2m/2m\"",
        '1m': "Rate-Limit=\"1m/1m\"",
        '512k': "Rate-Limit=\"512k/512k\"",
        '256k': "Rate-Limit=\"256k/256k\"",
        '128k': "Rate-Limit=\"128k/128k\"",
    }
    return rate_limit[speed]


def save_applied_speed_to_db(applied_speed: Optional[str], order_id: int):
    with sqlite3.connect(DB_PATH) as conn:
        curses = conn.cursor()
        if applied_speed:
            curses.execute("""UPDATE order_usages SET applied_speed = ? where order_id=?""", (applied_speed, order_id))
        else:
            curses.execute("""UPDATE order_usages SET applied_speed = NULL where order_id=?""",
                           (applied_speed, order_id))
        conn.commit()


def shamsi_to_gregorian(shamsi_str: str) -> datetime:
    """تبدیل تاریخ شمسی '1404-05-03 15:33' به datetime میلادی"""
    if not shamsi_str:
        return None
    date_part, time_part = shamsi_str.split(" ")
    y, m, d = map(int, date_part.split("-"))
    hh, mm = map(int, time_part.split(":"))
    jd = jdatetime.datetime(y, m, d, hh, mm)
    return jd.togregorian()


def get_orders_usage_for_limitation():
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()

    # گرفتن همه رکوردها
    cur.execute("""
        SELECT 
            ou.id,
            ou.order_id,
            ou.username,
            ou.total_mb,
            ou.applied_speed,
            ou.limit_mb,
            o.starts_at,
            o.expires_at,
            o.user_id
        FROM order_usages ou
        JOIN orders o ON o.id = ou.order_id
        WHERE o.status = 'active'
    """)
    rows = cur.fetchall()
    conn.close()

    valid_rows = []
    now = datetime.now()

    for row in rows:
        usage_id, order_id, username, total_mb, applied_speed, limit_mb, starts_at, expires_at, user_id = row

        # تبدیل تاریخ‌ها از شمسی به میلادی
        start_dt = shamsi_to_gregorian(starts_at) if starts_at else None
        expire_dt = shamsi_to_gregorian(expires_at) if expires_at else None

        # شرط شروع و پایان
        if start_dt and start_dt > now:
            print("Check This !!!")
            continue
        if expire_dt and expire_dt < now:
            continue

        valid_rows.append((usage_id, order_id, username, total_mb, applied_speed, limit_mb, user_id))

    return valid_rows


def apply_limit(username, order_id, speed):
    # دریافت اتربیوت فعلی از IBS
    user_radius_attr = get_user_radius_attribute(username)
    group_radius_attr = get_group_radius_attribute(username)
    if not group_radius_attr:
        # هیچ اتربیوتی نداره → فقط سرعت جدید رو ست کن
        radius_attrs = get_rate_limit(speed)
        apply_user_radius_attrs(username, radius_attrs)
        print(username, order_id, radius_attrs)
    else:
        group = group_radius_attr.get("Group")
        if group:
            rate_limit = get_rate_limit(speed=speed)
            radius_attrs = f"Group=\"{group}\"" + "\n" + rate_limit
            # باید گروه رو هم با سرعت جدید ست کنیم
            apply_user_radius_attrs(username, radius_attrs)
            print(username, order_id, radius_attrs)
        else:
            radius_attrs = get_rate_limit(speed=speed)
            # گروه نداره → فقط سرعت رو ست کن
            apply_user_radius_attrs(username, radius_attrs)
            print(username, order_id, radius_attrs)

    # حالا دوباره اتربیوت جدید رو بخون و در دیتابیس ذخیره کن
    updated_attr = get_user_radius_attribute(username)
    if updated_attr:
        actual_rate_limit = updated_attr.get("Rate-Limit").split("/")[0]
        save_applied_speed_to_db(order_id=order_id,
                                 applied_speed=actual_rate_limit)  # باید این تابع رو خودت ساخته باشی
    else:
        print(f"[!] Failed to fetch updated attributes for {username}")


def limit_speed():
    rows = get_orders_usage_for_limitation()
    for usage_id, order_id, username, total_mb, applied_speed, limit_mb, user_id in rows:
        if not limit_mb:
            continue  # یعنی هنوز حجمش ست نشده

        if total_mb < limit_mb:
            # هنوز زیر سقفه
            if applied_speed == "1m" or applied_speed == "128k":
                print("Ino Che Konim!!!")
                # reset_user_speed(username, order_id)
            continue

            # رد کرده
        if applied_speed == "128k" or applied_speed == "256":
            continue  # قبلاً لیمیت شده
            # رد کرده

        if applied_speed == "1m" and total_mb > (limit_mb + 20480):
            apply_limit(username, order_id, speed='256k')
            continue

        if applied_speed == "4m" and total_mb > (limit_mb + 10240):
            apply_limit(username, order_id, speed='1m')
            continue

        if not applied_speed:
            # لیمیت کن
            # print(usage_id, username, total_mb, limit_mb, total_mb - limit_mb)
            apply_limit(username, order_id, speed='4m')
            text = format_limit_notification(username, total_mb, limit_mb)
            send_notification(user_id=user_id, text=text)
            for admin in ADMINS:
                send_notification(user_id=admin, text=text)


def reset_user_speed(username, order_id):
    """برگردوندن سرعت کاربر به حالت اولیه بعد از خرید حجم"""
    radius_attr = get_user_radius_attribute(username)
    if radius_attr and "Group" in radius_attr:
        group = radius_attr["Group"]
        radius_attrs = f"Group=\"{group}\""
        apply_user_radius_attrs(username, radius_attrs)
    else:
        apply_user_radius_attrs(username, "")  # یعنی بدون محدودیت خاص

    save_applied_speed_to_db(order_id=order_id, applied_speed=None)
