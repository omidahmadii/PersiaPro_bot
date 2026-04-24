from __future__ import annotations

import re
import sqlite3
from typing import Any, Iterable, Optional, Union

from config import DB_PATH

ACCESS_MODE_LABELS = {
    "all": "همه کاربران",
    "funded_only": "فقط کاربران با موجودی کافی",
}

USAGE_LIMIT_SPEED_LABELS = {
    "32k": "32 کیلوبیت",
    "64k": "64 کیلوبیت",
    "128k": "128 کیلوبیت",
    "256k": "256 کیلوبیت",
    "512k": "512 کیلوبیت",
}

PAYMENT_COMMON_AMOUNT_SETTING_KEY = "payment_common_amounts"
DEFAULT_PAYMENT_COMMON_AMOUNTS = [
    250_000,
    500_000,
    750_000,
    1_000_000,
    1_250_000,
    1_500_000,
]
PAYMENT_AMOUNT_MIN = 1_000
PAYMENT_AMOUNT_MAX = 50_000_000

LEGACY_TEXT_DEFAULT_UPDATES: dict[str, dict[str, str]] = {
    "message_conversion_list": {
        "🔁 سرویس‌های واجد شرایط طرح تبدیل\nسرویس موردنظر را انتخاب کنید.": "سرویس مورد نظر را انتخاب کنید.",
    },
    "message_conversion_confirm": {
        (
            "❓ آیا این تبدیل برای این سرویس انجام شود؟\n\n"
            "پس از تایید، سرویس قبلی پایان می‌یابد و سرویس جدید فعال می‌شود.\n"
            "این تغییر غیرقابل بازگشت است."
        ): (
            "⚠️ با تایید این کار، به هیچ عنوان امکان بازگشت به سرویس قبلی وجود ندارد.\n\n"
            "مطمئن هستید؟"
        ),
    },
}


SETTING_DEFINITIONS: dict[str, dict[str, Any]] = {
    "feature_buy_enabled": {
        "type": "bool",
        "default": "0",
        "label": "فروش سرویس",
    },
    "feature_buy_access_mode": {
        "type": "choice",
        "default": "funded_only",
        "label": "دسترسی خرید",
        "choices": ACCESS_MODE_LABELS,
    },
    "feature_renew_enabled": {
        "type": "bool",
        "default": "0",
        "label": "تمدید سرویس",
    },
    "feature_extra_volume_enabled": {
        "type": "bool",
        "default": "1",
        "label": "خرید حجم اضافه",
    },
    "renewal_offer_notification_enabled": {
        "type": "bool",
        "default": "0",
        "label": "اعلان پلن پیشنهادی نزدیک اتمام",
    },
    "renewal_offer_target_plan_id": {
        "type": "integer",
        "default": "27",
        "label": "شناسه پلن پیشنهادی نزدیک اتمام",
    },
    "renewal_offer_days_threshold": {
        "type": "integer",
        "default": "10",
        "label": "حداکثر روز باقی‌مانده اعلان پیشنهادی",
    },
    "feature_conversion_enabled": {
        "type": "bool",
        "default": "0",
        "label": "طرح تبدیل سرویس",
    },
    "conversion_notification_enabled": {
        "type": "bool",
        "default": "0",
        "label": "اعلان طرح تبدیل",
    },
    "conversion_show_only_marked_services": {
        "type": "bool",
        "default": "1",
        "label": "نمایش فقط سرویس‌های نشان‌دار",
    },
    "feature_renew_access_mode": {
        "type": "choice",
        "default": "funded_only",
        "label": "دسترسی تمدید",
        "choices": ACCESS_MODE_LABELS,
    },
    "usage_limit_speed": {
        "type": "choice",
        "default": "64k",
        "label": "سرعت محدودسازی حجم",
        "choices": USAGE_LIMIT_SPEED_LABELS,
    },
    PAYMENT_COMMON_AMOUNT_SETTING_KEY: {
        "type": "text",
        "default": ",".join(str(amount) for amount in DEFAULT_PAYMENT_COMMON_AMOUNTS),
        "label": "مبلغ‌های سریع ثبت فیش",
    },
    "message_welcome_text": {
        "type": "text",
        "default": (
            "👋 خوش اومدی!\n\n"
            "به ربات فروش VPN PersiaPro خوش آمدی 🌐\n\n"
            "از منوی زیر می‌تونی:\n"
            "▫️ حساب شارژ کنی\n"
            "▫️ سرویس بخری\n"
            "▫️ فیش ارسال کنی\n"
            "▫️ با پشتیبانی در ارتباط باشی\n\n"
            "👇 یکی از گزینه‌ها رو انتخاب کن:"
        ),
        "label": "پیام خوش‌آمد",
    },
    "message_start_membership_required": {
        "type": "text",
        "default": (
            "🔒 دسترسی محدود\n\n"
            "برای استفاده از ربات PersiaPro، ابتدا باید عضو کانال رسمی ما بشید.\n\n"
            "بعد از عضویت، روی دکمه «عضو شدم» بزنید 👇"
        ),
        "label": "پیام عضویت /start",
    },
    "message_membership_required": {
        "type": "text",
        "default": "🔒 برای استفاده از این بخش باید عضو کانال PersiaPro باشید.",
        "label": "پیام الزام عضویت",
    },
    "message_buy_disabled": {
        "type": "text",
        "default": "در حال حاضر فروش سرویس جدید غیر فعال می باشد.",
        "label": "پیام توقف فروش",
    },
    "message_buy_no_active_plans": {
        "type": "text",
        "default": "در حال حاضر پلن فعالی برای فروش موجود نیست.",
        "label": "پیام نبود پلن فروش",
    },
    "message_renew_disabled": {
        "type": "text",
        "default": "در حال حاضر تمدید سرویس غیر فعال می باشد.",
        "label": "پیام توقف تمدید",
    },
    "message_renew_no_services": {
        "type": "text",
        "default": "⚠️ هیچ سرویسی برای تمدید پیدا نشد.",
        "label": "پیام نبود سرویس تمدید",
    },
    "message_extra_volume_disabled": {
        "type": "text",
        "default": "در حال حاضر خرید حجم اضافه غیر فعال می باشد.",
        "label": "پیام توقف خرید حجم اضافه",
    },
    "conversion_menu_title": {
        "type": "text",
        "default": "طرح تبدیل سرویس",
        "label": "عنوان منوی طرح تبدیل",
    },
    "conversion_target_plan_id": {
        "type": "integer",
        "default": "0",
        "label": "شناسه پلن مقصد طرح تبدیل",
    },
    "conversion_min_days_remaining": {
        "type": "integer",
        "default": "30",
        "label": "حداقل روز باقی‌مانده طرح تبدیل",
    },
    "conversion_min_remaining_volume_gb": {
        "type": "integer",
        "default": "2",
        "label": "حداقل حجم باقی‌مانده طرح تبدیل",
    },
    "conversion_new_duration_days": {
        "type": "integer",
        "default": "30",
        "label": "مدت سرویس جدید طرح تبدیل",
    },
    "conversion_new_volume_gb": {
        "type": "integer",
        "default": "2",
        "label": "حجم سرویس جدید طرح تبدیل",
    },
    "conversion_price": {
        "type": "integer",
        "default": "0",
        "label": "قیمت طرح تبدیل",
    },
    "conversion_notification_cooldown_days": {
        "type": "integer",
        "default": "7",
        "label": "فاصله اعلان طرح تبدیل",
    },
    "conversion_topup_package_title": {
        "type": "text",
        "default": "2 گیگ",
        "label": "عنوان بسته حجمی طرح تبدیل",
    },
    "conversion_source_plan_ids": {
        "type": "text",
        "default": "",
        "label": "شناسه پلن‌های مبدأ طرح تبدیل",
    },
    "conversion_source_group_names": {
        "type": "text",
        "default": "",
        "label": "گروه‌های مبدأ طرح تبدیل",
    },
    "conversion_topup_package_volume_gb": {
        "type": "integer",
        "default": "2",
        "label": "حجم بسته حجمی طرح تبدیل",
    },
    "conversion_topup_package_price": {
        "type": "integer",
        "default": "750",
        "label": "قیمت بسته حجمی طرح تبدیل",
    },
    "message_conversion_disabled": {
        "type": "text",
        "default": "🔁 در حال حاضر طرح تبدیل سرویس فعال نیست.",
        "label": "پیام توقف طرح تبدیل",
    },
    "message_conversion_notification": {
        "type": "text",
        "default": (
            "✨ یه خبر خوب برای بعضی از سرویس‌هات!\n\n"
            "اگر یکی از سرویس‌هات شرایط لازم رو داشته باشه، می‌تونی خیلی راحت و کاملاً رایگان 🎁 "
            "اون رو تبدیل کنی به یک سرویس:\n\n"
            "🚀 {new_volume_gb} گیگ | {new_duration_days} روزه\n\n"
            "این سرویس جدید بدون محدودیت طراحی شده تا تجربه بهتری داشته باشی و مخصوص استفاده راحت‌تر در اپ‌هایی مثل:\n"
            "📱 واتساپ | 📸 اینستاگرام\n\n"
            "بعد از تموم شدن حجم، می‌تونی دوباره خیلی سریع بسته زیر رو تهیه کنی:\n\n"
            "🔄 {topup_package_title}\n"
            "💰 {topup_package_price} هزار تومان\n\n"
            "🔍 برای دیدن اینکه کدوم سرویس‌هات شامل این طرح میشن:\n"
            "از منوی ربات برو به بخش «{menu_title}»"
        ),
        "label": "پیام اطلاع‌رسانی طرح تبدیل",
    },
    "message_conversion_list": {
        "type": "text",
        "default": "سرویس مورد نظر را انتخاب کنید.",
        "label": "متن لیست طرح تبدیل",
    },
    "message_conversion_detail": {
        "type": "text",
        "default": (
            "⚠️ با تایید شما:\n"
            "• سرویس فعلی همان لحظه پایان می‌یابد\n"
            "• سرویس جدید {new_volume_gb} گیگ {new_duration_days} روزه فعال می‌شود\n"
            "• این تغییر نهایی است و بازگشت خودکار ندارد"
        ),
        "label": "متن توضیح طرح تبدیل",
    },
    "message_conversion_confirm": {
        "type": "text",
        "default": (
            "⚠️ با تایید این کار، به هیچ عنوان امکان بازگشت به سرویس قبلی وجود ندارد.\n\n"
            "مطمئن هستید؟"
        ),
        "label": "متن تایید طرح تبدیل",
    },
    "message_conversion_success": {
        "type": "text",
        "default": (
            "✅ تبدیل انجام شد.\n"
            "سرویس جدید {new_volume_gb} گیگ {new_duration_days} روزه شما فعال شد.\n"
            "📦 بعد از اتمام حجم، می‌توانید بسته {topup_package_title} با مبلغ {topup_package_price} هزار تومان تهیه کنید."
        ),
        "label": "پیام موفقیت طرح تبدیل",
    },
    "message_conversion_no_services": {
        "type": "text",
        "default": "ℹ️ در حال حاضر سرویس واجد شرایطی برای طرح تبدیل ندارید.",
        "label": "پیام نبود سرویس واجد شرایط طرح تبدیل",
    },
    "message_conversion_no_longer_eligible": {
        "type": "text",
        "default": "⚠️ این سرویس در حال حاضر دیگر شرایط طرح تبدیل را ندارد.",
        "label": "پیام از دست رفتن شرایط طرح تبدیل",
    },
    "message_conversion_cancelled": {
        "type": "text",
        "default": "⛔ درخواست طرح تبدیل برای این سرویس لغو شد.",
        "label": "پیام انصراف طرح تبدیل",
    },
    "message_conversion_failed": {
        "type": "text",
        "default": "❌ انجام طرح تبدیل ممکن نشد. لطفاً دوباره تلاش کنید.",
        "label": "پیام خطای طرح تبدیل",
    },
}

GENERAL_FEATURE_SETTING_KEYS = (
    "feature_buy_enabled",
    "feature_renew_enabled",
    "feature_extra_volume_enabled",
    "renewal_offer_notification_enabled",
)

CONVERSION_FEATURE_SETTING_KEYS = (
    "feature_conversion_enabled",
    "conversion_notification_enabled",
    "conversion_show_only_marked_services",
)

ACCESS_MODE_SETTING_KEYS = (
    "feature_buy_access_mode",
    "feature_renew_access_mode",
)

GENERAL_CHOICE_SETTING_KEYS = ACCESS_MODE_SETTING_KEYS + (
    "usage_limit_speed",
)

GENERAL_INTEGER_SETTING_KEYS = (
    "renewal_offer_target_plan_id",
    "renewal_offer_days_threshold",
)

FEATURE_SETTING_KEYS = GENERAL_FEATURE_SETTING_KEYS + CONVERSION_FEATURE_SETTING_KEYS
CHOICE_SETTING_KEYS = GENERAL_CHOICE_SETTING_KEYS

CONVERSION_INTEGER_SETTING_KEYS = (
    "conversion_target_plan_id",
    "conversion_min_days_remaining",
    "conversion_min_remaining_volume_gb",
    "conversion_new_duration_days",
    "conversion_new_volume_gb",
    "conversion_price",
    "conversion_notification_cooldown_days",
    "conversion_topup_package_volume_gb",
    "conversion_topup_package_price",
)

CONVERSION_CONFIG_TEXT_SETTING_KEYS = (
    "conversion_menu_title",
    "conversion_topup_package_title",
    "conversion_source_plan_ids",
    "conversion_source_group_names",
)

GENERAL_TEXT_SETTING_KEYS = (
    "message_welcome_text",
    "message_start_membership_required",
    "message_membership_required",
    "message_buy_disabled",
    "message_buy_no_active_plans",
    "message_renew_disabled",
    "message_renew_no_services",
    "message_extra_volume_disabled",
)

CONVERSION_MESSAGE_SETTING_KEYS = (
    "message_conversion_disabled",
    "message_conversion_notification",
    "message_conversion_list",
    "message_conversion_detail",
    "message_conversion_confirm",
    "message_conversion_success",
    "message_conversion_no_services",
    "message_conversion_no_longer_eligible",
    "message_conversion_cancelled",
    "message_conversion_failed",
)

TEXT_SETTING_KEYS = GENERAL_TEXT_SETTING_KEYS + CONVERSION_MESSAGE_SETTING_KEYS + (
    "conversion_menu_title",
    "conversion_topup_package_title",
)


def initialize_runtime_settings_schema(cursor: sqlite3.Cursor) -> None:
    cursor.execute(
        """
        CREATE TABLE IF NOT EXISTS app_settings (
            key TEXT PRIMARY KEY,
            value TEXT,
            value_type TEXT NOT NULL DEFAULT 'text',
            updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
        )
        """
    )

    for key, definition in SETTING_DEFINITIONS.items():
        default_value = str(definition["default"])
        setting_type = str(definition.get("type", "text"))
        cursor.execute(
            """
            INSERT OR IGNORE INTO app_settings (key, value, value_type)
            VALUES (?, ?, ?)
            """,
            (key, default_value, setting_type),
        )
        row = cursor.execute(
            "SELECT value FROM app_settings WHERE key = ?",
            (key,),
        ).fetchone()
        current_value = str(row[0]) if row and row[0] is not None else None
        if current_value is None or (not current_value.strip() and default_value.strip()):
            cursor.execute(
                """
                UPDATE app_settings
                SET value = ?, value_type = ?, updated_at = CURRENT_TIMESTAMP
                WHERE key = ?
                """,
                (default_value, setting_type, key),
            )
            current_value = default_value

        if str(definition.get("type")) == "choice":
            allowed_values = {str(option) for option in dict(definition.get("choices") or {}).keys()}
            if not allowed_values:
                continue

            if current_value not in allowed_values:
                cursor.execute(
                    """
                    UPDATE app_settings
                    SET value = ?, value_type = ?, updated_at = CURRENT_TIMESTAMP
                    WHERE key = ?
                    """,
                (default_value, "choice", key),
            )

        legacy_replacements = LEGACY_TEXT_DEFAULT_UPDATES.get(key, {})
        replacement_value = legacy_replacements.get(current_value)
        if replacement_value is not None:
            cursor.execute(
                """
                UPDATE app_settings
                SET value = ?, value_type = ?, updated_at = CURRENT_TIMESTAMP
                WHERE key = ?
                """,
                (replacement_value, setting_type, key),
            )


def _connect() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def get_setting_definition(key: str) -> dict[str, Any]:
    return SETTING_DEFINITIONS.get(key, {})


def get_default_setting_value(key: str, fallback: Optional[str] = None) -> Optional[str]:
    definition = get_setting_definition(key)
    if "default" in definition:
        return str(definition["default"])
    return fallback


def get_setting(key: str, fallback: Optional[str] = None) -> Optional[str]:
    with _connect() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT value FROM app_settings WHERE key = ?", (key,))
        row = cursor.fetchone()

    if row and row["value"] is not None:
        return str(row["value"])
    return get_default_setting_value(key, fallback)


def get_text_setting(key: str, fallback: str = "") -> str:
    value = get_setting(key, fallback)
    if value is None:
        return fallback
    return str(value)


def _is_truthy(raw: Optional[str]) -> bool:
    return str(raw or "").strip().lower() in {"1", "true", "yes", "on"}


def get_bool_setting(key: str, default: bool = False) -> bool:
    raw = get_setting(key, "1" if default else "0")
    return _is_truthy(raw)


def get_int_setting(key: str, default: int = 0) -> int:
    raw = get_setting(key, str(default))
    try:
        return int(str(raw).strip())
    except Exception:
        return int(default)


def get_choice_options(key: str) -> dict[str, str]:
    definition = get_setting_definition(key)
    choices = definition.get("choices")
    return dict(choices) if isinstance(choices, dict) else {}


def normalize_choice_value(key: str, value: Optional[str], fallback: Optional[str] = None) -> Optional[str]:
    options = get_choice_options(key)
    if not options:
        return value if value is not None else fallback

    resolved_fallback = fallback or get_default_setting_value(key)
    if resolved_fallback not in options:
        resolved_fallback = next(iter(options))

    if value in options:
        return str(value)
    return resolved_fallback


def get_choice_setting(key: str, default: Optional[str] = None) -> Optional[str]:
    fallback = default or get_default_setting_value(key)
    raw = get_setting(key, fallback)
    return normalize_choice_value(key, raw, fallback)


def get_choice_label(key: str, value: Optional[str]) -> str:
    options = get_choice_options(key)
    if value in options:
        return str(options[str(value)])
    return str(value or "-")


def get_access_mode_setting(key: str, default: str = "funded_only") -> str:
    return str(get_choice_setting(key, default) or default)


def get_access_mode_label(mode: str) -> str:
    return ACCESS_MODE_LABELS.get(mode, ACCESS_MODE_LABELS["funded_only"])


def get_usage_limit_speed_setting(default: str = "64k") -> str:
    return str(get_choice_setting("usage_limit_speed", default) or default)


def get_usage_limit_speed_label(value: Optional[str] = None) -> str:
    resolved = value or get_usage_limit_speed_setting()
    return get_choice_label("usage_limit_speed", resolved)


_DIGIT_TRANSLATION = str.maketrans(
    "۰۱۲۳۴۵۶۷۸۹٠١٢٣٤٥٦٧٨٩",
    "01234567890123456789",
)


def normalize_setting_digits(value: str) -> str:
    return str(value or "").translate(_DIGIT_TRANSLATION)


def parse_payment_common_amounts(raw_value: str) -> list[int]:
    normalized = normalize_setting_digits(raw_value)
    raw_tokens: list[str] = []
    for part in re.split(r"[\s،;؛|/]+", normalized):
        token = part.strip().strip(",")
        if not token:
            continue

        compact = token.replace(",", "")
        if (
            "," in token
            and re.fullmatch(r"\d{1,3}(,\d{3})+", token)
            and token.endswith(",000")
            and PAYMENT_AMOUNT_MIN <= int(compact) <= PAYMENT_AMOUNT_MAX
        ):
            raw_tokens.append(compact)
        else:
            raw_tokens.extend(item for item in token.split(",") if item.strip())

    amounts: list[int] = []
    seen: set[int] = set()

    for token in raw_tokens:
        digits = "".join(ch for ch in token if ch.isdigit())
        if not digits:
            continue

        amount = int(digits)
        if 0 < amount < 10_000:
            amount *= 1_000

        if amount < PAYMENT_AMOUNT_MIN or amount > PAYMENT_AMOUNT_MAX:
            continue
        if amount in seen:
            continue

        seen.add(amount)
        amounts.append(amount)

    return amounts


def serialize_payment_common_amounts(amounts: Iterable[int]) -> str:
    cleaned: list[int] = []
    seen: set[int] = set()
    for amount in amounts:
        try:
            normalized = int(amount)
        except Exception:
            continue
        if 0 < normalized < 10_000:
            normalized *= 1_000
        if normalized < PAYMENT_AMOUNT_MIN or normalized > PAYMENT_AMOUNT_MAX:
            continue
        if normalized in seen:
            continue
        seen.add(normalized)
        cleaned.append(normalized)

    if not cleaned:
        cleaned = list(DEFAULT_PAYMENT_COMMON_AMOUNTS)
    return ",".join(str(amount) for amount in cleaned)


def get_payment_common_amounts() -> list[int]:
    default_value = serialize_payment_common_amounts(DEFAULT_PAYMENT_COMMON_AMOUNTS)
    raw_value = get_text_setting(PAYMENT_COMMON_AMOUNT_SETTING_KEY, default_value)
    amounts = parse_payment_common_amounts(raw_value)
    return amounts or list(DEFAULT_PAYMENT_COMMON_AMOUNTS)


def set_payment_common_amounts(amounts: Union[Iterable[int], str]) -> list[int]:
    if isinstance(amounts, str):
        cleaned = parse_payment_common_amounts(amounts)
    else:
        cleaned = parse_payment_common_amounts(serialize_payment_common_amounts(amounts))

    if not cleaned:
        raise ValueError("payment amount list is empty")

    set_setting(PAYMENT_COMMON_AMOUNT_SETTING_KEY, ",".join(str(amount) for amount in cleaned), value_type="text")
    return cleaned


def format_payment_common_amounts(amounts: Optional[Iterable[int]] = None) -> str:
    values = list(amounts if amounts is not None else get_payment_common_amounts())
    return "، ".join(f"{int(amount):,}" for amount in values)


def set_setting(key: str, value: str, value_type: Optional[str] = None) -> None:
    definition = get_setting_definition(key)
    resolved_type = value_type or str(definition.get("type", "text"))
    resolved_value = value

    if resolved_type == "choice":
        resolved_value = str(normalize_choice_value(key, value, get_default_setting_value(key, value)) or value)

    with _connect() as conn:
        cursor = conn.cursor()
        cursor.execute(
            """
            UPDATE app_settings
            SET value = ?, value_type = ?, updated_at = CURRENT_TIMESTAMP
            WHERE key = ?
            """,
            (resolved_value, resolved_type, key),
        )

        if cursor.rowcount == 0:
            cursor.execute(
                """
                INSERT OR IGNORE INTO app_settings (key, value, value_type, updated_at)
                VALUES (?, ?, ?, CURRENT_TIMESTAMP)
                """,
                (key, resolved_value, resolved_type),
            )
            cursor.execute(
                """
                UPDATE app_settings
                SET value = ?, value_type = ?, updated_at = CURRENT_TIMESTAMP
                WHERE key = ?
                """,
                (resolved_value, resolved_type, key),
            )

        conn.commit()


def set_bool_setting(key: str, enabled: bool) -> None:
    set_setting(key, "1" if enabled else "0", value_type="bool")


def reset_setting(key: str) -> None:
    default_value = get_default_setting_value(key)
    if default_value is None:
        return

    definition = get_setting_definition(key)
    set_setting(key, default_value, value_type=str(definition.get("type", "text")))


def reset_text_settings(keys: Optional[Iterable[str]] = None) -> None:
    for key in keys or TEXT_SETTING_KEYS:
        reset_setting(key)
