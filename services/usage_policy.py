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
    return (
        "ℹ️ پس از اتمام حجم، سرعت این سرویس محدود می‌شود و در صورت عبور مصرف از سقف حجم به اندازه 200 مگابایت، سرویس قفل خواهد شد."
    )


def get_volume_policy_alert(speed: Optional[str] = None) -> str:
    return (
        "⚠️ با اتمام حجم، سرعت این سرویس محدود می‌شود و اگر 200 مگابایت از سقف حجم عبور کنید، سرویس قفل خواهد شد."
    )


def get_post_limit_actions_text(speed: Optional[str] = None) -> str:
    return (
        "برای برگشت به سرعت عادی بعد از محدود شدن سرویس یا باز شدن سرویس قفل‌شده، "
        "می‌توانید خرید حجم اضافه انجام دهید، یا یک سرویس جدید بخرید و بعد گزینه "
        "«فعال‌سازی سرویس ذخیره» را بزنید."
    )
