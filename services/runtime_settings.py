from __future__ import annotations

import sqlite3
from typing import Any

from config import DB_PATH


SETTING_DEFINITIONS: dict[str, dict[str, Any]] = {
    "feature_buy_enabled": {
        "type": "bool",
        "default": "0",
        "label": "فروش سرویس",
    },
    "feature_renew_enabled": {
        "type": "bool",
        "default": "0",
        "label": "تمدید سرویس",
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
}

FEATURE_SETTING_KEYS = (
    "feature_buy_enabled",
    "feature_renew_enabled",
)

TEXT_SETTING_KEYS = (
    "message_welcome_text",
    "message_start_membership_required",
    "message_membership_required",
    "message_buy_disabled",
    "message_buy_no_active_plans",
    "message_renew_disabled",
    "message_renew_no_services",
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


def _connect() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def get_setting_definition(key: str) -> dict[str, Any]:
    return SETTING_DEFINITIONS.get(key, {})


def get_default_setting_value(key: str, fallback: str | None = None) -> str | None:
    definition = get_setting_definition(key)
    if "default" in definition:
        return str(definition["default"])
    return fallback


def get_setting(key: str, fallback: str | None = None) -> str | None:
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


def _is_truthy(raw: str | None) -> bool:
    return str(raw or "").strip().lower() in {"1", "true", "yes", "on"}


def get_bool_setting(key: str, default: bool = False) -> bool:
    raw = get_setting(key, "1" if default else "0")
    return _is_truthy(raw)


def set_setting(key: str, value: str, value_type: str | None = None) -> None:
    definition = get_setting_definition(key)
    resolved_type = value_type or str(definition.get("type", "text"))

    with _connect() as conn:
        cursor = conn.cursor()
        cursor.execute(
            """
            INSERT INTO app_settings (key, value, value_type, updated_at)
            VALUES (?, ?, ?, CURRENT_TIMESTAMP)
            ON CONFLICT(key) DO UPDATE SET
                value = excluded.value,
                value_type = excluded.value_type,
                updated_at = CURRENT_TIMESTAMP
            """,
            (key, value, resolved_type),
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
