from services.db import get_orders_for_usage_notifications, update_order_usage_notif_level
from services.scheduler_services.telegram_safe import send_scheduler_notification
from services.usage_policy import get_post_limit_actions_text


def get_usage_notification_level(percent: float) -> int:
    if percent >= 95:
        return 95
    if percent >= 75:
        return 75
    if percent >= 50:
        return 50
    return 0


def format_gb_from_mb(value_mb: int) -> str:
    return f"{round((value_mb or 0) / 1024, 2)}"


def format_percent(percent: float) -> int:
    bounded = max(0.0, min(percent, 100.0))
    return int(round(bounded))


def send_notification(user_id: int, text: str):
    return send_scheduler_notification(chat_id=user_id, text=text, parse_mode="HTML", timeout=15)


def build_message(order: dict, level: int, current_percent: float, limit_mb: int) -> str:
    username = order["username"]
    message_name = (order.get("message_name") or "").strip()
    used_mb = int(order.get("usage_total_mb") or order.get("usage_effective_mb") or 0)
    remaining_mb = max(limit_mb - used_mb, 0)
    greeting = f"{message_name} جان" if message_name else "مشترک گرامی"
    display_percent = format_percent(current_percent)

    if level >= 95:
        headline = (
            f"مصرف سرویس <code>{username}</code> الان به <b>{display_percent}%</b> رسیده "
            "و به انتهای حجم خیلی نزدیک شده است."
        )
        warning_text = (
            "⏳ مصرف این سرویس به آستانه اتمام حجم رسیده است.\n"
        )
    else:
        headline = (
            f"مصرف سرویس <code>{username}</code> الان به <b>{display_percent}%</b> رسیده "
            f"و از مرز هشدار <b>{level}%</b> عبور کرده است."
        )
        warning_text = (
            "⚠️ بعد از اتمام حجم، سرعت این سرویس محدود می‌شود.\n"
        )

    return (
        f"📊 <b>{greeting}</b>\n\n"
        f"{headline}\n"
        f"📈 مصرف فعلی: <b>{format_gb_from_mb(used_mb)} گیگ</b>\n"
        f"📦 حجم کل: <b>{format_gb_from_mb(limit_mb)} گیگ</b>\n"
        f"📉 حجم باقی‌مانده: <b>{format_gb_from_mb(remaining_mb)} گیگ</b>\n"
        f"🔢 درصد فعلی مصرف: <b>{display_percent}%</b>\n\n"
        f"{warning_text}"
        f"{get_post_limit_actions_text()}"
    )


def notify_usage_thresholds():
    orders = get_orders_for_usage_notifications()

    for order in orders:
        try:
            user_id = order.get("user_id")
            if not user_id:
                continue

            limit_mb = int(
                round(
                    (
                        float(order.get("volume_gb") or 0)
                        + float(order.get("extra_volume_gb") or 0)
                        + float(order.get("overused_volume_gb") or 0)
                    )
                    * 1024
                )
            )
            if limit_mb <= 0:
                continue

            usage_effective_mb = int(order.get("usage_total_mb") or order.get("usage_effective_mb") or 0)
            usage_percent = (usage_effective_mb * 100) / limit_mb
            level_needed = get_usage_notification_level(usage_percent)
            last_level = int(order.get("usage_notif_level") or 0)

            if level_needed == 0 or level_needed <= last_level:
                continue

            text = build_message(order=order, level=level_needed, current_percent=usage_percent, limit_mb=limit_mb)
            sent = send_notification(user_id=user_id, text=text)
            if not sent:
                continue
            update_order_usage_notif_level(level_needed=level_needed, order_id=order["id"])
        except Exception as exc:
            print(f"⚠️ Failed to send usage notification for order {order.get('id')}: {exc}")
