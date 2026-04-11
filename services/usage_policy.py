from typing import Optional

from services.runtime_settings import (
    get_usage_limit_speed_label,
    get_usage_limit_speed_setting,
)


def get_limit_speed_value() -> str:
    return get_usage_limit_speed_setting(default="64k")


def get_limit_speed_display(speed: Optional[str] = None) -> str:
    return get_usage_limit_speed_label(speed or get_limit_speed_value())


def get_volume_policy_text(speed: Optional[str] = None) -> str:
    speed_label = get_limit_speed_display(speed)
    return (
        f"ℹ️ پس از اتمام حجم، سرعت این سرویس به {speed_label} محدود می‌شود."
    )


def get_volume_policy_alert(speed: Optional[str] = None) -> str:
    speed_label = get_limit_speed_display(speed)
    return (
        f"⚠️ با اتمام حجم، سرعت این سرویس به {speed_label} محدود می‌شود."
    )


def get_post_limit_actions_text(speed: Optional[str] = None) -> str:
    speed_label = get_limit_speed_display(speed)
    return (
        f"برای برگشت به سرعت عادی از حالت محدود {speed_label}، "
        "می‌توانید خرید حجم اضافه انجام دهید، یا یک سرویس جدید بخرید و بعد گزینه "
        "«فعال‌سازی سرویس ذخیره» را بزنید."
    )
