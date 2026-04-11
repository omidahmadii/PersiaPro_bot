from __future__ import annotations

import sqlite3
from typing import Any, Optional

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
}

FEATURE_SETTING_KEYS = (
    "feature_buy_enabled",
    "feature_renew_enabled",
    "feature_extra_volume_enabled",
)

ACCESS_MODE_SETTING_KEYS = (
    "feature_buy_access_mode",
    "feature_renew_access_mode",
)

CHOICE_SETTING_KEYS = ACCESS_MODE_SETTING_KEYS + (
    "usage_limit_speed",
)

TEXT_SETTING_KEYS = (
    "message_welcome_text",
    "message_start_membership_required",
    "message_membership_required",
    "message_buy_disabled",
    "message_buy_no_active_plans",
    "message_renew_disabled",
    "message_renew_no_services",
    "message_extra_volume_disabled",
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
        cursor.execute(
            """
            INSERT OR IGNORE INTO app_settings (key, value, value_type)
            VALUES (?, ?, ?)
            """,
            (key, str(definition["default"]), str(definition["type"])),
        )
        if str(definition.get("type")) == "choice":
            allowed_values = {str(option) for option in dict(definition.get("choices") or {}).keys()}
            if not allowed_values:
                continue

            row = cursor.execute(
                "SELECT value FROM app_settings WHERE key = ?",
                (key,),
            ).fetchone()
            current_value = str(row[0]) if row and row[0] is not None else None
            default_value = str(definition["default"])
            if current_value not in allowed_values:
                cursor.execute(
                    """
                    UPDATE app_settings
                    SET value = ?, value_type = ?, updated_at = CURRENT_TIMESTAMP
                    WHERE key = ?
                    """,
                    (default_value, "choice", key),
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


def reset_text_settings() -> None:
    for key in TEXT_SETTING_KEYS:
        reset_setting(key)
