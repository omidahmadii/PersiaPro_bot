from datetime import timedelta

import jdatetime
import requests

import config
from services.db import get_orders_for_notifications, update_order_last_notif_level, get_user_message_name

TOKEN = config.BOT_TOKEN
# ثابت جدید: بازهٔ سکوت
QUIET_HOURS = range(0, 9)


def get_current_jdatetime():
    """برگرداندن زمان جاری شمسی"""
    return jdatetime.datetime.now()


def get_notification_level(remaining_seconds):
    """تعیین سطح اخطار بر اساس زمان باقی‌مانده"""
    if remaining_seconds <= 0:
        return 4
    elif remaining_seconds <= 2 * 3600:
        return 3
    elif remaining_seconds <= 24 * 3600:
        return 2
    elif remaining_seconds <= 72 * 3600:
        return 1
    return 0  # نیازی به اخطار نیست


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


def notifier():
    now_jdt = get_current_jdatetime()
    # اگر در بازهٔ سکوت هستیم، هیچ پیامی ارسال نشود
    if now_jdt.hour in QUIET_HOURS:
        return  # به سادگی خروج؛ دفعهٔ بعدی چک می‌شود

    threshold_time = now_jdt + timedelta(hours=48)
    orders = get_orders_for_notifications(threshold_time.strftime("%Y-%m-%d %H:%M:%S"))

    for order in orders:
        try:
            expires_at_jdt = jdatetime.datetime.strptime(order['expires_at'], "%Y-%m-%d %H:%M")
            remaining_seconds = int((expires_at_jdt - now_jdt).total_seconds())
            level_needed = get_notification_level(remaining_seconds)

            if level_needed == 0:
                continue  # هیچ پیامی لازم نیست

            if order['status'] == 'waiting_for_renewal':
                if level_needed < 3:
                    continue

            last_level = order.get('last_notif_level') or 0
            if level_needed > last_level:
                text = build_message(level_needed, order['status'], order)
                send_notification(order['user_id'], text)
                update_order_last_notif_level(level_needed, order['id'])

        except Exception as e:
            print(f"⚠️ Failed to notify user {order.get('user_id')}: {e}")


def format_jdatetime(dt: jdatetime.datetime) -> str:
    """تبدیل تاریخ شمسی به رشته‌ای خوانا: 1404/04/25 ساعت 16:30"""
    return dt.strftime("%Y/%m/%d ساعت %H:%M")


def build_message(level: int, status: str, order: dict) -> str:
    username = order["username"]
    user_id = order["user_id"]

    user_message_name = get_user_message_name(user_id)
    expires_at_jdt = jdatetime.datetime.strptime(order["expires_at"], "%Y-%m-%d %H:%M")
    exact_time = format_jdatetime(expires_at_jdt)

    # پیام مخصوص زمانی که سفارش جدید در صفِ فعال‌سازی است
    if status == "waiting_for_renewal" and level == 3:
        return (
            f"⏳ اکانت <b><code>{username}</code></b> کمتر از دو ساعت دیگر منقضی می‌شود.\n"
            f"پرداخت شما تأیید شده است و سرویس جدید بلافاصله پس از تاریخ {exact_time} فعال خواهد شد.\n"
            f"سپاس از شکیبایی شما."
        )

    templates = {
        1: (
            "یادآوری ۴۸ ساعته",
            f"اکانت <b><code>{username}</code></b> تا ۴۸ ساعت دیگر (در تاریخ {exact_time}) به پایان می‌رسد.",
        ),
        2: (
            "یادآوری ۲۴ ساعته",
            f"اکانت <b><code>{username}</code></b> تا ۲۴ ساعت دیگر (در تاریخ {exact_time}) منقضی می‌شود.",
        ),
        3: (
            "هشدار ۲ ساعته",
            f"کمتر از دو ساعت به پایان اکانت <b><code>{username}</code></b> باقی مانده است (زمان دقیق: {exact_time}).",
        ),
        4: (
            "اتمام سرویس",
            f"اکانت <b><code>{username}</code></b> در تاریخ {exact_time} به پایان رسیده است.",
        ),
    }

    title, body = templates[level]
    action_line = "برای جلوگیری از قطع اتصال، همین حالا از منوی ربات گزینهٔ «تمدید سرویس» را انتخاب کنید."
    if level == 4:
        action_line = "برای فعال‌سازی مجدد، از منوی ربات «تمدید سرویس» را انتخاب کنید."
    name = user_message_name.strip() if user_message_name else ""

    if name:
        name_text = f"{name} جان"
    else:
        name_text = "مشترک گرامی"

    text = (f"📢 <b>{name_text}</b>\n\n"
            f"{body}\n\n{action_line}")

    return text
