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
    greeting = f"{message_name} Ø¬Ø§Ù†" if message_name else "Ù…Ø´ØªØ±Ú© Ú¯Ø±Ø§Ù…ÛŒ"
    display_percent = format_percent(current_percent)

    if level >= 95:
        headline = (
            f"Ù…ØµØ±Ù Ø³Ø±ÙˆÛŒØ³ <code>{username}</code> Ø§Ù„Ø§Ù† Ø¨Ù‡ <b>{display_percent}%</b> Ø±Ø³ÛŒØ¯Ù‡ "
            "Ùˆ Ø¨Ù‡ Ø§Ù†ØªÙ‡Ø§ÛŒ Ø­Ø¬Ù… Ø®ÛŒÙ„ÛŒ Ù†Ø²Ø¯ÛŒÚ© Ø´Ø¯Ù‡ Ø§Ø³Øª."
        )
        warning_text = (
            "⏳ مصرف این سرویس به آستانه اتمام حجم رسیده است.\n"
        )
    else:
        headline = (
            f"Ù…ØµØ±Ù Ø³Ø±ÙˆÛŒØ³ <code>{username}</code> Ø§Ù„Ø§Ù† Ø¨Ù‡ <b>{display_percent}%</b> Ø±Ø³ÛŒØ¯Ù‡ "
            f"Ùˆ Ø§Ø² Ù…Ø±Ø² Ù‡Ø´Ø¯Ø§Ø± <b>{level}%</b> Ø¹Ø¨ÙˆØ± Ú©Ø±Ø¯Ù‡ Ø§Ø³Øª."
        )
        warning_text = (
            "âš ï¸ Ø¨Ø¹Ø¯ Ø§Ø² Ø§ØªÙ…Ø§Ù… Ø­Ø¬Ù…ØŒ Ø³Ø±Ø¹Øª Ø§ÛŒÙ† Ø³Ø±ÙˆÛŒØ³ Ù…Ø­Ø¯ÙˆØ¯ Ù…ÛŒâ€ŒØ´ÙˆØ¯.\n"
        )

    return (
        f"ðŸ“Š <b>{greeting}</b>\n\n"
        f"{headline}\n"
        f"ðŸ“ˆ Ù…ØµØ±Ù ÙØ¹Ù„ÛŒ: <b>{format_gb_from_mb(used_mb)} Ú¯ÛŒÚ¯</b>\n"
        f"ðŸ“¦ Ø­Ø¬Ù… Ú©Ù„: <b>{format_gb_from_mb(limit_mb)} Ú¯ÛŒÚ¯</b>\n"
        f"ðŸ“‰ Ø­Ø¬Ù… Ø¨Ø§Ù‚ÛŒâ€ŒÙ…Ø§Ù†Ø¯Ù‡: <b>{format_gb_from_mb(remaining_mb)} Ú¯ÛŒÚ¯</b>\n"
        f"ðŸ”¢ Ø¯Ø±ØµØ¯ ÙØ¹Ù„ÛŒ Ù…ØµØ±Ù: <b>{display_percent}%</b>\n\n"
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
            print(f"âš ï¸ Failed to send usage notification for order {order.get('id')}: {exc}")
