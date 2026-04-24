from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message

from config import ADMINS
from keyboards.main_menu import admin_main_menu_keyboard
from services.db import get_plan_info, get_plans_for_admin
from services.runtime_settings import (
    CHOICE_SETTING_KEYS,
    CONVERSION_CONFIG_TEXT_SETTING_KEYS,
    CONVERSION_FEATURE_SETTING_KEYS,
    CONVERSION_INTEGER_SETTING_KEYS,
    CONVERSION_MESSAGE_SETTING_KEYS,
    FEATURE_SETTING_KEYS,
    GENERAL_FEATURE_SETTING_KEYS,
    GENERAL_INTEGER_SETTING_KEYS,
    GENERAL_TEXT_SETTING_KEYS,
    PAYMENT_COMMON_AMOUNT_SETTING_KEY,
    SETTING_DEFINITIONS,
    format_payment_common_amounts,
    get_bool_setting,
    get_choice_label,
    get_choice_options,
    get_choice_setting,
    get_default_setting_value,
    get_int_setting,
    get_payment_common_amounts,
    get_text_setting,
    parse_payment_common_amounts,
    reset_text_settings,
    set_bool_setting,
    set_payment_common_amounts,
    set_setting,
)

router = Router()

ROUTE_MAIN = "menu"
ROUTE_GENERAL_MESSAGES = "messages"
ROUTE_CONVERSION = "conversion"
ROUTE_CONVERSION_MESSAGES = "conversion_messages"
ROUTE_RENEWAL_OFFER = "renewal_offer"

CONVERSION_TEXT_RESET_KEYS = CONVERSION_MESSAGE_SETTING_KEYS + (
    "conversion_menu_title",
    "conversion_topup_package_title",
)

RENEWAL_OFFER_FEATURE_KEYS = ("renewal_offer_notification_enabled",)
RENEWAL_OFFER_INTEGER_KEYS = (
    "renewal_offer_target_plan_id",
    "renewal_offer_days_threshold",
)


class RuntimeSettingsState(StatesGroup):
    waiting_for_value = State()


def is_admin(user_id: int) -> bool:
    return user_id in ADMINS


def _preview_text(value: str, limit: int = 64) -> str:
    compact = " ".join((value or "").split())
    if not compact:
        return "خالی"
    if len(compact) <= limit:
        return compact
    return compact[: limit - 1] + "…"


def _choice_icon(key: str) -> str:
    if key == "usage_limit_speed":
        return "⚡"
    return "👥"


def _parse_list_input(raw_value: str, *, integer: bool) -> str:
    normalized = (raw_value or "").replace("،", ",").replace("\n", ",")
    items: list[str] = []
    seen: set[str] = set()
    for part in normalized.split(","):
        token = part.strip()
        if not token:
            continue
        if integer:
            try:
                number = int(token)
            except Exception:
                continue
            if number <= 0:
                continue
            token = str(number)
        if token.lower() in seen:
            continue
        seen.add(token.lower())
        items.append(token)
    separator = "," if integer else ", "
    return separator.join(items)


def _format_plan_short(plan: dict) -> str:
    return f"#{plan['id']} | {plan.get('name') or '-'}"


def _build_active_plan_reference_lines(limit: int = 10) -> list[str]:
    plans = get_plans_for_admin(include_archived=False)
    lines: list[str] = []
    for plan in plans[:limit]:
        lines.append(f"• {_format_plan_short(plan)}")
    if len(plans) > limit:
        lines.append("• ...")
    return lines


def _build_target_plan_summary() -> str:
    target_plan_id = get_int_setting("conversion_target_plan_id", 0)
    if target_plan_id <= 0:
        return "تنظیم نشده"

    plan = get_plan_info(target_plan_id)
    if not plan:
        return f"#{target_plan_id} (نامعتبر یا آرشیوشده)"

    return (
        f"#{target_plan_id} | {plan.get('name') or '-'}"
        f" | گروه: {plan.get('group_name') or '-'}"
    )


def _build_renewal_offer_target_plan_summary() -> str:
    target_plan_id = get_int_setting("renewal_offer_target_plan_id", 27)
    if target_plan_id <= 0:
        return "تنظیم نشده"

    plan = get_plan_info(target_plan_id)
    if not plan:
        return f"#{target_plan_id} (نامعتبر یا آرشیوشده)"

    return (
        f"#{target_plan_id} | {plan.get('name') or '-'}"
        f" | گروه: {plan.get('group_name') or '-'}"
    )


def _build_source_plan_summary() -> str:
    raw_value = get_text_setting("conversion_source_plan_ids", "")
    plan_ids = [token for token in _parse_list_input(raw_value, integer=True).split(",") if token]
    if not plan_ids:
        return "تعریف نشده"

    labels: list[str] = []
    for token in plan_ids[:5]:
        plan = get_plan_info(int(token))
        if plan:
            labels.append(f"#{token} {plan.get('name') or '-'}")
        else:
            labels.append(f"#{token}")
    if len(plan_ids) > 5:
        labels.append(f"+{len(plan_ids) - 5} مورد دیگر")
    return "، ".join(labels)


def _build_source_group_summary() -> str:
    raw_value = get_text_setting("conversion_source_group_names", "")
    value = _parse_list_input(raw_value, integer=False)
    return value or "تعریف نشده"


def _build_payment_amounts_summary() -> str:
    return format_payment_common_amounts(get_payment_common_amounts())


def choice_keyboard(key: str) -> InlineKeyboardMarkup:
    options = list(get_choice_options(key).items())
    current_value = get_choice_setting(key)
    rows: list[list[InlineKeyboardButton]] = []
    current_row: list[InlineKeyboardButton] = []
    columns = 3 if key == "usage_limit_speed" else 1

    for value, label in options:
        prefix = "✅ " if value == current_value else ""
        current_row.append(
            InlineKeyboardButton(
                text=f"{prefix}{label}",
                callback_data=f"settings|choice_set|{key}|{value}",
            )
        )
        if len(current_row) == columns:
            rows.append(current_row)
            current_row = []

    if current_row:
        rows.append(current_row)

    rows.append([InlineKeyboardButton(text="⬅️ بازگشت به تنظیمات", callback_data="settings|menu")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def build_choice_text(key: str) -> str:
    label = SETTING_DEFINITIONS[key]["label"]
    current_value = get_choice_setting(key)
    lines = [
        f"{_choice_icon(key)} تنظیم «{label}»",
        "",
        f"مقدار فعلی: {get_choice_label(key, current_value)}",
        "",
        "یکی از گزینه‌های زیر را انتخاب کنید:",
    ]
    return "\n".join(lines)


def settings_keyboard() -> InlineKeyboardMarkup:
    rows: list[list[InlineKeyboardButton]] = []

    for key in GENERAL_FEATURE_SETTING_KEYS:
        if key in RENEWAL_OFFER_FEATURE_KEYS:
            continue
        label = SETTING_DEFINITIONS[key]["label"]
        enabled = get_bool_setting(key, default=get_default_setting_value(key) == "1")
        icon = "✅" if enabled else "🚫"
        rows.append(
            [InlineKeyboardButton(text=f"{icon} {label}", callback_data=f"settings|toggle|{key}")]
        )

    for key in CHOICE_SETTING_KEYS:
        label = SETTING_DEFINITIONS[key]["label"]
        mode = get_choice_setting(key)
        rows.append(
            [
                InlineKeyboardButton(
                    text=f"{_choice_icon(key)} {label}: {get_choice_label(key, mode)}",
                    callback_data=f"settings|choice|{key}",
                )
            ]
        )

    rows.append(
        [
            InlineKeyboardButton(
                text=f"💳 مبلغ‌های فیش: {_preview_text(_build_payment_amounts_summary(), limit=42)}",
                callback_data="settings|payment_amounts",
            )
        ]
    )
    rows.append([InlineKeyboardButton(text="🔁 طرح تبدیل سرویس", callback_data="settings|conversion")])
    rows.append([InlineKeyboardButton(text="🔔 پیشنهاد تمدید نزدیک اتمام", callback_data="settings|renewal_offer")])
    rows.append([InlineKeyboardButton(text="✏️ پیام‌های عمومی", callback_data="settings|messages")])
    rows.append(
        [
            InlineKeyboardButton(text="↻ بروزرسانی", callback_data="settings|menu"),
            InlineKeyboardButton(text="🏠 منوی ادمین", callback_data="settings|close"),
        ]
    )

    return InlineKeyboardMarkup(inline_keyboard=rows)


def build_settings_text() -> str:
    lines = [
        "⚙️ تنظیمات ربات",
        "",
        "تغییرات این بخش بلافاصله از دیتابیس خوانده می‌شوند و نیازی به ریستارت نیست.",
        "",
        "تنظیمات عمومی:",
    ]

    for key in GENERAL_FEATURE_SETTING_KEYS:
        if key in RENEWAL_OFFER_FEATURE_KEYS:
            continue
        label = SETTING_DEFINITIONS[key]["label"]
        enabled = get_bool_setting(key, default=get_default_setting_value(key) == "1")
        lines.append(f"• {label}: {'✅ فعال' if enabled else '🚫 غیرفعال'}")

    lines.extend(["", "تنظیمات انتخابی:"])
    for key in CHOICE_SETTING_KEYS:
        label = SETTING_DEFINITIONS[key]["label"]
        mode = get_choice_setting(key)
        lines.append(f"• {label}: {get_choice_label(key, mode)}")

    lines.extend(["", "تنظیمات پرداخت:"])
    lines.append(f"• مبلغ‌های سریع ثبت فیش: {_build_payment_amounts_summary()} تومان")

    lines.extend(
        [
            "",
            "سایر بخش‌ها:",
            "• پیام‌های عمومی از منوی «پیام‌های عمومی» قابل ویرایش هستند.",
            "• تنظیمات «طرح تبدیل سرویس» در زیرمنوی جداگانه قرار گرفته‌اند.",
            "• تنظیمات «پیشنهاد تمدید نزدیک اتمام» در زیرمنوی جداگانه قرار گرفته‌اند.",
        ]
    )
    return "\n".join(lines)


def message_settings_keyboard(keys: tuple[str, ...], *, reset_callback: str, back_callback: str) -> InlineKeyboardMarkup:
    rows: list[list[InlineKeyboardButton]] = []

    for key in keys:
        label = SETTING_DEFINITIONS[key]["label"]
        rows.append([InlineKeyboardButton(text=f"✏️ {label}", callback_data=f"settings|edit|{key}")])

    rows.append([InlineKeyboardButton(text="♻️ بازنشانی این بخش", callback_data=reset_callback)])
    rows.append([InlineKeyboardButton(text="⬅️ بازگشت", callback_data=back_callback)])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def build_message_settings_text(title: str, keys: tuple[str, ...]) -> str:
    lines = [
        title,
        "",
        "پیش‌نمایش متن‌های قابل ویرایش:",
    ]

    for key in keys:
        label = SETTING_DEFINITIONS[key]["label"]
        preview = _preview_text(get_text_setting(key, ""))
        lines.append(f"• {label}: {preview}")

    lines.extend(["", "برای ویرایش هر متن، دکمه‌ی همان مورد را بزنید."])
    return "\n".join(lines)


def conversion_settings_keyboard() -> InlineKeyboardMarkup:
    rows: list[list[InlineKeyboardButton]] = []

    for key in CONVERSION_FEATURE_SETTING_KEYS:
        label = SETTING_DEFINITIONS[key]["label"]
        enabled = get_bool_setting(key, default=get_default_setting_value(key) == "1")
        icon = "✅" if enabled else "🚫"
        rows.append([InlineKeyboardButton(text=f"{icon} {label}", callback_data=f"settings|toggle|{key}")])

    rows.append(
        [
            InlineKeyboardButton(text="🎯 انتخاب پلن مقصد", callback_data="settings|conv_target_pick"),
            InlineKeyboardButton(text="#️⃣ شناسه پلن مقصد", callback_data="settings|cfg|conversion_target_plan_id"),
        ]
    )
    rows.append(
        [
            InlineKeyboardButton(text="🧭 پلن‌های مبدأ", callback_data="settings|cfg|conversion_source_plan_ids"),
            InlineKeyboardButton(text="🧩 گروه‌های مبدأ", callback_data="settings|cfg|conversion_source_group_names"),
        ]
    )
    rows.append(
        [
            InlineKeyboardButton(text="📅 حداقل روز", callback_data="settings|cfg|conversion_min_days_remaining"),
            InlineKeyboardButton(text="📦 حداقل حجم", callback_data="settings|cfg|conversion_min_remaining_volume_gb"),
        ]
    )
    rows.append(
        [
            InlineKeyboardButton(text="🗓 مدت سرویس جدید", callback_data="settings|cfg|conversion_new_duration_days"),
            InlineKeyboardButton(text="💾 حجم سرویس جدید", callback_data="settings|cfg|conversion_new_volume_gb"),
        ]
    )
    rows.append(
        [
            InlineKeyboardButton(text="💰 قیمت تبدیل", callback_data="settings|cfg|conversion_price"),
            InlineKeyboardButton(text="⏳ فاصله اعلان", callback_data="settings|cfg|conversion_notification_cooldown_days"),
        ]
    )
    rows.append(
        [
            InlineKeyboardButton(text="🏷 عنوان منو", callback_data="settings|cfg|conversion_menu_title"),
            InlineKeyboardButton(text="🛍 عنوان بسته", callback_data="settings|cfg|conversion_topup_package_title"),
        ]
    )
    rows.append(
        [
            InlineKeyboardButton(text="📦 حجم بسته حجمی", callback_data="settings|cfg|conversion_topup_package_volume_gb"),
            InlineKeyboardButton(text="💵 قیمت بسته حجمی", callback_data="settings|cfg|conversion_topup_package_price"),
        ]
    )
    rows.append([InlineKeyboardButton(text="✏️ پیام‌های طرح تبدیل", callback_data="settings|conversion_messages")])
    rows.append(
        [
            InlineKeyboardButton(text="↻ بروزرسانی", callback_data="settings|conversion"),
            InlineKeyboardButton(text="⬅️ بازگشت به تنظیمات", callback_data="settings|menu"),
        ]
    )
    return InlineKeyboardMarkup(inline_keyboard=rows)


def build_conversion_settings_text() -> str:
    lines = [
        "🔁 تنظیمات طرح تبدیل سرویس",
        "",
        "وضعیت کلی:",
    ]

    for key in CONVERSION_FEATURE_SETTING_KEYS:
        label = SETTING_DEFINITIONS[key]["label"]
        enabled = get_bool_setting(key, default=get_default_setting_value(key) == "1")
        lines.append(f"• {label}: {'✅ فعال' if enabled else '🚫 غیرفعال'}")

    lines.extend(
        [
            "",
            "تعریف پلن‌ها:",
            f"• پلن مقصد: {_build_target_plan_summary()}",
            f"• پلن‌های مبدأ: {_build_source_plan_summary()}",
            f"• گروه‌های مبدأ: {_build_source_group_summary()}",
            "",
            "پارامترهای تبدیل:",
            f"• عنوان منو: {get_text_setting('conversion_menu_title', '') or '-'}",
            f"• حداقل روز باقی‌مانده: {get_int_setting('conversion_min_days_remaining', 30)}",
            f"• حداقل حجم باقی‌مانده: {get_int_setting('conversion_min_remaining_volume_gb', 2)} گیگ",
            f"• مدت سرویس جدید: {get_int_setting('conversion_new_duration_days', 30)} روز",
            f"• حجم سرویس جدید: {get_int_setting('conversion_new_volume_gb', 2)} گیگ",
            f"• قیمت تبدیل: {get_int_setting('conversion_price', 0)}",
            f"• فاصله اعلان: {get_int_setting('conversion_notification_cooldown_days', 7)} روز",
            f"• عنوان بسته حجمی: {get_text_setting('conversion_topup_package_title', '') or '-'}",
            f"• حجم بسته حجمی: {get_int_setting('conversion_topup_package_volume_gb', 2)} گیگ",
            f"• قیمت بسته حجمی: {get_int_setting('conversion_topup_package_price', 750)}",
            "",
            "منطق تشخیص خودکار:",
            "• اگر «نمایش فقط سرویس‌های نشان‌دار» روشن باشد، فقط سفارش‌هایی که eligible_for_conversion=1 دارند نمایش داده می‌شوند.",
            "• اگر این گزینه خاموش باشد، سرویس‌های دارای یکی از این شرط‌ها بررسی می‌شوند: eligible_for_conversion، old_limited_service، تطبیق plan_id با پلن‌های مبدأ، یا تطبیق group_name با گروه‌های مبدأ.",
            "• برای حالت خودکار، معمولاً کافی است پلن‌های مبدأ را ثبت کنید و «نمایش فقط سرویس‌های نشان‌دار» را خاموش بگذارید.",
        ]
    )

    active_plan_lines = _build_active_plan_reference_lines(limit=8)
    if active_plan_lines:
        lines.extend(["", "پلن‌های فعال برای راهنما:"])
        lines.extend(active_plan_lines)

    return "\n".join(lines)


def conversion_target_picker_keyboard() -> InlineKeyboardMarkup:
    rows: list[list[InlineKeyboardButton]] = []
    for plan in get_plans_for_admin(include_archived=False):
        rows.append(
            [
                InlineKeyboardButton(
                    text=_format_plan_short(plan)[:64],
                    callback_data=f"settings|conv_target_set|{plan['id']}",
                )
            ]
        )

    rows.append([InlineKeyboardButton(text="⬅️ بازگشت به طرح تبدیل", callback_data="settings|conversion")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def build_conversion_target_picker_text() -> str:
    lines = [
        "🎯 انتخاب پلن مقصد طرح تبدیل",
        "",
        f"پلن مقصد فعلی: {_build_target_plan_summary()}",
        "",
        "یکی از پلن‌های فعال زیر را انتخاب کنید:",
    ]
    return "\n".join(lines)


def renewal_offer_target_picker_keyboard() -> InlineKeyboardMarkup:
    rows: list[list[InlineKeyboardButton]] = []
    for plan in get_plans_for_admin(include_archived=False):
        rows.append(
            [
                InlineKeyboardButton(
                    text=_format_plan_short(plan)[:64],
                    callback_data=f"settings|renew_offer_target_set|{plan['id']}",
                )
            ]
        )

    rows.append([InlineKeyboardButton(text="⬅️ بازگشت به پیشنهاد تمدید", callback_data="settings|renewal_offer")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def build_renewal_offer_target_picker_text() -> str:
    lines = [
        "🎯 انتخاب پلن پیشنهادی نزدیک اتمام",
        "",
        f"پلن پیشنهادی فعلی: {_build_renewal_offer_target_plan_summary()}",
        "",
        "یکی از پلن‌های فعال زیر را انتخاب کنید:",
    ]
    return "\n".join(lines)


def renewal_offer_settings_keyboard() -> InlineKeyboardMarkup:
    rows: list[list[InlineKeyboardButton]] = []

    for key in RENEWAL_OFFER_FEATURE_KEYS:
        label = SETTING_DEFINITIONS[key]["label"]
        enabled = get_bool_setting(key, default=get_default_setting_value(key) == "1")
        icon = "✅" if enabled else "🚫"
        rows.append([InlineKeyboardButton(text=f"{icon} {label}", callback_data=f"settings|toggle|{key}")])

    rows.append(
        [
            InlineKeyboardButton(text="🎯 انتخاب پلن پیشنهادی", callback_data="settings|renew_offer_target_pick"),
            InlineKeyboardButton(text="#️⃣ شناسه پلن پیشنهادی", callback_data="settings|cfg|renewal_offer_target_plan_id"),
        ]
    )
    rows.append(
        [
            InlineKeyboardButton(
                text=f"📅 بازه اعلان نزدیک اتمام: {get_int_setting('renewal_offer_days_threshold', 10)} روز",
                callback_data="settings|cfg|renewal_offer_days_threshold",
            )
        ]
    )
    rows.append(
        [
            InlineKeyboardButton(text="↻ بروزرسانی", callback_data="settings|renewal_offer"),
            InlineKeyboardButton(text="⬅️ بازگشت به تنظیمات", callback_data="settings|menu"),
        ]
    )
    return InlineKeyboardMarkup(inline_keyboard=rows)


def build_renewal_offer_settings_text() -> str:
    enabled = get_bool_setting("renewal_offer_notification_enabled", default=False)
    days_threshold = get_int_setting("renewal_offer_days_threshold", 10)
    lines = [
        "🔔 تنظیمات پیشنهاد تمدید نزدیک اتمام",
        "",
        "وضعیت کلی:",
        f"• اعلان پلن پیشنهادی: {'✅ فعال' if enabled else '🚫 غیرفعال'}",
        f"• پلن پیشنهادی: {_build_renewal_offer_target_plan_summary()}",
        f"• بازه اعلان: {days_threshold} روز مانده به اتمام",
        "",
        "راهنما:",
        "• اعلان فقط برای سرویس‌های نزدیک اتمام ارسال می‌شود.",
        "• اگر کاربر روی همان پلن پیشنهادی باشد، اعلان ارسال نمی‌شود.",
    ]
    return "\n".join(lines)


async def _show_settings_panel_message(message: Message) -> None:
    await message.answer(build_settings_text(), reply_markup=settings_keyboard())


async def _show_settings_panel_callback(callback: CallbackQuery) -> None:
    await callback.message.edit_text(build_settings_text(), reply_markup=settings_keyboard())


async def _show_general_message_settings_panel_message(message: Message) -> None:
    await message.answer(
        build_message_settings_text("✏️ پیام‌های عمومی", GENERAL_TEXT_SETTING_KEYS),
        reply_markup=message_settings_keyboard(
            GENERAL_TEXT_SETTING_KEYS,
            reset_callback="settings|messages_reset",
            back_callback="settings|menu",
        ),
    )


async def _show_general_message_settings_panel_callback(callback: CallbackQuery) -> None:
    await callback.message.edit_text(
        build_message_settings_text("✏️ پیام‌های عمومی", GENERAL_TEXT_SETTING_KEYS),
        reply_markup=message_settings_keyboard(
            GENERAL_TEXT_SETTING_KEYS,
            reset_callback="settings|messages_reset",
            back_callback="settings|menu",
        ),
    )


async def _show_conversion_settings_panel_message(message: Message) -> None:
    await message.answer(build_conversion_settings_text(), reply_markup=conversion_settings_keyboard())


async def _show_conversion_settings_panel_callback(callback: CallbackQuery) -> None:
    await callback.message.edit_text(build_conversion_settings_text(), reply_markup=conversion_settings_keyboard())


async def _show_conversion_message_settings_panel_message(message: Message) -> None:
    await message.answer(
        build_message_settings_text("✏️ پیام‌های طرح تبدیل", CONVERSION_MESSAGE_SETTING_KEYS),
        reply_markup=message_settings_keyboard(
            CONVERSION_MESSAGE_SETTING_KEYS,
            reset_callback="settings|conv_msgs_reset",
            back_callback="settings|conversion",
        ),
    )


async def _show_conversion_message_settings_panel_callback(callback: CallbackQuery) -> None:
    await callback.message.edit_text(
        build_message_settings_text("✏️ پیام‌های طرح تبدیل", CONVERSION_MESSAGE_SETTING_KEYS),
        reply_markup=message_settings_keyboard(
            CONVERSION_MESSAGE_SETTING_KEYS,
            reset_callback="settings|conv_msgs_reset",
            back_callback="settings|conversion",
        ),
    )


async def _show_renewal_offer_settings_panel_message(message: Message) -> None:
    await message.answer(build_renewal_offer_settings_text(), reply_markup=renewal_offer_settings_keyboard())


async def _show_renewal_offer_settings_panel_callback(callback: CallbackQuery) -> None:
    await callback.message.edit_text(build_renewal_offer_settings_text(), reply_markup=renewal_offer_settings_keyboard())


async def _show_conversion_target_picker(callback: CallbackQuery) -> None:
    await callback.message.edit_text(
        build_conversion_target_picker_text(),
        reply_markup=conversion_target_picker_keyboard(),
    )


async def _show_renewal_offer_target_picker(callback: CallbackQuery) -> None:
    await callback.message.edit_text(
        build_renewal_offer_target_picker_text(),
        reply_markup=renewal_offer_target_picker_keyboard(),
    )


async def _show_route_message(message: Message, route: str) -> None:
    if route == ROUTE_GENERAL_MESSAGES:
        await _show_general_message_settings_panel_message(message)
        return
    if route == ROUTE_CONVERSION:
        await _show_conversion_settings_panel_message(message)
        return
    if route == ROUTE_CONVERSION_MESSAGES:
        await _show_conversion_message_settings_panel_message(message)
        return
    if route == ROUTE_RENEWAL_OFFER:
        await _show_renewal_offer_settings_panel_message(message)
        return
    await _show_settings_panel_message(message)


async def _show_route_callback(callback: CallbackQuery, route: str) -> None:
    if route == ROUTE_GENERAL_MESSAGES:
        await _show_general_message_settings_panel_callback(callback)
        return
    if route == ROUTE_CONVERSION:
        await _show_conversion_settings_panel_callback(callback)
        return
    if route == ROUTE_CONVERSION_MESSAGES:
        await _show_conversion_message_settings_panel_callback(callback)
        return
    if route == ROUTE_RENEWAL_OFFER:
        await _show_renewal_offer_settings_panel_callback(callback)
        return
    await _show_settings_panel_callback(callback)


def _resolve_return_route(key: str) -> str:
    if key in GENERAL_TEXT_SETTING_KEYS:
        return ROUTE_GENERAL_MESSAGES
    if key in RENEWAL_OFFER_FEATURE_KEYS or key in RENEWAL_OFFER_INTEGER_KEYS:
        return ROUTE_RENEWAL_OFFER
    if key in GENERAL_INTEGER_SETTING_KEYS:
        return ROUTE_MAIN
    if key in CONVERSION_MESSAGE_SETTING_KEYS:
        return ROUTE_CONVERSION_MESSAGES
    if key in CONVERSION_CONFIG_TEXT_SETTING_KEYS or key in CONVERSION_INTEGER_SETTING_KEYS or key in CONVERSION_FEATURE_SETTING_KEYS:
        return ROUTE_CONVERSION
    return ROUTE_MAIN


async def _start_setting_edit(callback: CallbackQuery, state: FSMContext, key: str) -> None:
    if key not in SETTING_DEFINITIONS:
        return await callback.answer("تنظیمات نامعتبر است.", show_alert=True)

    definition = SETTING_DEFINITIONS[key]
    setting_type = str(definition.get("type", "text"))
    if setting_type not in {"text", "integer"}:
        return await callback.answer("این تنظیم از این بخش قابل ویرایش نیست.", show_alert=True)

    label = str(definition.get("label") or key)
    return_route = _resolve_return_route(key)
    await state.set_state(RuntimeSettingsState.waiting_for_value)
    await state.update_data(setting_key=key, setting_type=setting_type, return_route=return_route)

    if key == PAYMENT_COMMON_AMOUNT_SETTING_KEY:
        prompt_lines = [
            f"لیست جدید برای «{label}» را ارسال کنید.",
            "",
            f"مقدار فعلی: {_build_payment_amounts_summary()} تومان",
            "",
            "عددها را با فاصله، کاما یا خط جدید جدا کنید.",
            "اگر عدد را کوتاه بنویسید، هزار تومان حساب می‌شود؛ مثلا 250 یعنی 250,000 تومان.",
            "مثال: 250 500 750 1000 1250 1500",
            "",
            "برای لغو، عبارت «لغو» را ارسال کنید.",
        ]
        await callback.message.edit_text("\n".join(prompt_lines))
        await callback.answer()
        return

    if setting_type == "integer":
        current_value = get_int_setting(key, int(get_default_setting_value(key, "0") or 0))
        prompt_lines = [
            f"عدد جدید برای «{label}» را ارسال کنید.",
            "",
            f"مقدار فعلی: {current_value}",
            "",
            "برای لغو، عبارت «لغو» را ارسال کنید.",
        ]
        if key in {"conversion_target_plan_id", "renewal_offer_target_plan_id"}:
            prompt_lines.extend(["", "راهنما برای شناسه پلن‌ها:"])
            prompt_lines.extend(_build_active_plan_reference_lines(limit=10))
        await callback.message.edit_text("\n".join(prompt_lines))
        await callback.answer()
        return

    current_value = get_text_setting(key, "")
    prompt_lines = [
        f"مقدار جدید برای «{label}» را ارسال کنید.",
        "",
        f"مقدار فعلی:\n{current_value or '-'}",
        "",
        "برای لغو، عبارت «لغو» را ارسال کنید.",
    ]
    if key == "conversion_source_plan_ids":
        prompt_lines.extend(
            [
                "",
                "فرمت ورودی: شناسه‌ها را با کاما جدا کنید. مثال: 12,15,18",
                "برای پاک‌کردن این مقدار، «پاک» را ارسال کنید.",
                "",
                "راهنما برای شناسه پلن‌ها:",
            ]
        )
        prompt_lines.extend(_build_active_plan_reference_lines(limit=10))
    elif key == "conversion_source_group_names":
        prompt_lines.extend(
            [
                "",
                "فرمت ورودی: نام group_nameها را با کاما جدا کنید. مثال: OLD-TG, TG-LIMITED",
                "برای پاک‌کردن این مقدار، «پاک» را ارسال کنید.",
            ]
        )
    await callback.message.edit_text("\n".join(prompt_lines))
    await callback.answer()


@router.message(F.text == "⚙️ تنظیمات ربات")
async def runtime_settings_entry(message: Message, state: FSMContext):
    if not is_admin(message.from_user.id):
        return

    await state.clear()
    await _show_settings_panel_message(message)


@router.callback_query(F.data == "settings|menu")
async def runtime_settings_menu(callback: CallbackQuery, state: FSMContext):
    if not is_admin(callback.from_user.id):
        return await callback.answer("دسترسی ندارید.", show_alert=True)

    await state.clear()
    await _show_settings_panel_callback(callback)


@router.callback_query(F.data == "settings|payment_amounts")
async def runtime_settings_payment_amounts(callback: CallbackQuery, state: FSMContext):
    if not is_admin(callback.from_user.id):
        return await callback.answer("دسترسی ندارید.", show_alert=True)

    await _start_setting_edit(callback, state, PAYMENT_COMMON_AMOUNT_SETTING_KEY)


@router.callback_query(F.data.startswith("settings|toggle|"))
async def runtime_settings_toggle(callback: CallbackQuery, state: FSMContext):
    if not is_admin(callback.from_user.id):
        return await callback.answer("دسترسی ندارید.", show_alert=True)

    _, _, key = callback.data.split("|", 2)
    if key not in FEATURE_SETTING_KEYS:
        return await callback.answer("تنظیمات نامعتبر است.", show_alert=True)

    new_value = not get_bool_setting(key, default=get_default_setting_value(key) == "1")
    set_bool_setting(key, new_value)

    label = SETTING_DEFINITIONS[key]["label"]
    await state.clear()
    await callback.answer(f"{label} {'فعال' if new_value else 'غیرفعال'} شد.")
    await _show_route_callback(callback, _resolve_return_route(key))


@router.callback_query(F.data.startswith("settings|choice|"))
async def runtime_settings_change_choice(callback: CallbackQuery):
    if not is_admin(callback.from_user.id):
        return await callback.answer("دسترسی ندارید.", show_alert=True)

    _, _, key = callback.data.split("|", 2)
    if key not in CHOICE_SETTING_KEYS:
        return await callback.answer("تنظیمات نامعتبر است.", show_alert=True)

    if not get_choice_options(key):
        return await callback.answer("گزینه‌ای برای این تنظیم تعریف نشده است.", show_alert=True)

    await callback.message.edit_text(
        build_choice_text(key),
        reply_markup=choice_keyboard(key),
    )
    await callback.answer()


@router.callback_query(F.data.startswith("settings|choice_set|"))
async def runtime_settings_set_choice(callback: CallbackQuery, state: FSMContext):
    if not is_admin(callback.from_user.id):
        return await callback.answer("دسترسی ندارید.", show_alert=True)

    _, _, key, value = callback.data.split("|", 3)
    if key not in CHOICE_SETTING_KEYS:
        return await callback.answer("تنظیمات نامعتبر است.", show_alert=True)

    if value not in get_choice_options(key):
        return await callback.answer("گزینه انتخاب‌شده معتبر نیست.", show_alert=True)

    set_setting(key, value, value_type="choice")

    label = SETTING_DEFINITIONS[key]["label"]
    await state.clear()
    await callback.answer(f"{label} روی «{get_choice_label(key, value)}» قرار گرفت.")
    await _show_settings_panel_callback(callback)


@router.callback_query(F.data.in_({"settings|messages", "settings|general_messages"}))
async def runtime_settings_messages_menu(callback: CallbackQuery, state: FSMContext):
    if not is_admin(callback.from_user.id):
        return await callback.answer("دسترسی ندارید.", show_alert=True)

    await state.clear()
    await _show_general_message_settings_panel_callback(callback)


@router.callback_query(F.data == "settings|conversion")
async def runtime_settings_conversion_menu(callback: CallbackQuery, state: FSMContext):
    if not is_admin(callback.from_user.id):
        return await callback.answer("دسترسی ندارید.", show_alert=True)

    await state.clear()
    await _show_conversion_settings_panel_callback(callback)


@router.callback_query(F.data == "settings|conversion_messages")
async def runtime_settings_conversion_messages_menu(callback: CallbackQuery, state: FSMContext):
    if not is_admin(callback.from_user.id):
        return await callback.answer("دسترسی ندارید.", show_alert=True)

    await state.clear()
    await _show_conversion_message_settings_panel_callback(callback)


@router.callback_query(F.data == "settings|renewal_offer")
async def runtime_settings_renewal_offer_menu(callback: CallbackQuery, state: FSMContext):
    if not is_admin(callback.from_user.id):
        return await callback.answer("دسترسی ندارید.", show_alert=True)

    await state.clear()
    await _show_renewal_offer_settings_panel_callback(callback)


@router.callback_query(F.data == "settings|conv_target_pick")
async def runtime_settings_conversion_target_picker(callback: CallbackQuery, state: FSMContext):
    if not is_admin(callback.from_user.id):
        return await callback.answer("دسترسی ندارید.", show_alert=True)

    await state.clear()
    await _show_conversion_target_picker(callback)
    await callback.answer()


@router.callback_query(F.data.startswith("settings|conv_target_set|"))
async def runtime_settings_conversion_target_set(callback: CallbackQuery, state: FSMContext):
    if not is_admin(callback.from_user.id):
        return await callback.answer("دسترسی ندارید.", show_alert=True)

    plan_id = callback.data.split("|", 2)[2]
    set_setting("conversion_target_plan_id", plan_id, value_type="integer")
    await state.clear()
    await callback.answer("پلن مقصد به‌روزرسانی شد.")
    await _show_conversion_settings_panel_callback(callback)


@router.callback_query(F.data == "settings|renew_offer_target_pick")
async def runtime_settings_renewal_offer_target_picker(callback: CallbackQuery, state: FSMContext):
    if not is_admin(callback.from_user.id):
        return await callback.answer("دسترسی ندارید.", show_alert=True)

    await state.clear()
    await _show_renewal_offer_target_picker(callback)
    await callback.answer()


@router.callback_query(F.data.startswith("settings|renew_offer_target_set|"))
async def runtime_settings_renewal_offer_target_set(callback: CallbackQuery, state: FSMContext):
    if not is_admin(callback.from_user.id):
        return await callback.answer("دسترسی ندارید.", show_alert=True)

    plan_id = callback.data.split("|", 2)[2]
    set_setting("renewal_offer_target_plan_id", plan_id, value_type="integer")
    await state.clear()
    await callback.answer("پلن پیشنهادی به‌روزرسانی شد.")
    await _show_renewal_offer_settings_panel_callback(callback)


@router.callback_query(F.data.startswith("settings|edit|"))
async def runtime_settings_edit_text(callback: CallbackQuery, state: FSMContext):
    if not is_admin(callback.from_user.id):
        return await callback.answer("دسترسی ندارید.", show_alert=True)

    _, _, key = callback.data.split("|", 2)
    if key not in GENERAL_TEXT_SETTING_KEYS + CONVERSION_MESSAGE_SETTING_KEYS:
        if key not in CONVERSION_CONFIG_TEXT_SETTING_KEYS:
            return await callback.answer("پیام نامعتبر است.", show_alert=True)

    await _start_setting_edit(callback, state, key)


@router.callback_query(F.data.startswith("settings|cfg|"))
async def runtime_settings_edit_config(callback: CallbackQuery, state: FSMContext):
    if not is_admin(callback.from_user.id):
        return await callback.answer("دسترسی ندارید.", show_alert=True)

    _, _, key = callback.data.split("|", 2)
    if key not in CONVERSION_INTEGER_SETTING_KEYS + CONVERSION_CONFIG_TEXT_SETTING_KEYS + GENERAL_INTEGER_SETTING_KEYS:
        return await callback.answer("تنظیمات نامعتبر است.", show_alert=True)

    await _start_setting_edit(callback, state, key)


@router.callback_query(F.data.in_({"settings|reset_messages", "settings|messages_reset"}))
async def runtime_settings_reset_general_messages(callback: CallbackQuery, state: FSMContext):
    if not is_admin(callback.from_user.id):
        return await callback.answer("دسترسی ندارید.", show_alert=True)

    await state.clear()
    reset_text_settings(GENERAL_TEXT_SETTING_KEYS)
    await callback.answer("پیام‌های عمومی به مقدار پیش‌فرض برگشتند.")
    await _show_general_message_settings_panel_callback(callback)


@router.callback_query(F.data == "settings|conv_msgs_reset")
async def runtime_settings_reset_conversion_messages(callback: CallbackQuery, state: FSMContext):
    if not is_admin(callback.from_user.id):
        return await callback.answer("دسترسی ندارید.", show_alert=True)

    await state.clear()
    reset_text_settings(CONVERSION_TEXT_RESET_KEYS)
    await callback.answer("متن‌های طرح تبدیل به مقدار پیش‌فرض برگشتند.")
    await _show_conversion_message_settings_panel_callback(callback)


@router.callback_query(F.data == "settings|close")
async def runtime_settings_close(callback: CallbackQuery, state: FSMContext):
    if not is_admin(callback.from_user.id):
        return await callback.answer("دسترسی ندارید.", show_alert=True)

    await state.clear()
    await callback.message.edit_text("پنل تنظیمات بسته شد.")
    await callback.message.answer("بازگشت به منوی ادمین.", reply_markup=admin_main_menu_keyboard())


@router.message(RuntimeSettingsState.waiting_for_value)
async def runtime_settings_receive_value(message: Message, state: FSMContext):
    if not is_admin(message.from_user.id):
        await state.clear()
        return

    raw_text = (message.text or "").strip()
    if not raw_text:
        return await message.answer("مقدار خالی قابل ذخیره نیست. لطفاً مقدار جدید را ارسال کنید.")

    if raw_text in {"لغو", "انصراف"}:
        data = await state.get_data()
        await state.clear()
        return await _show_route_message(message, str(data.get("return_route") or ROUTE_MAIN))

    data = await state.get_data()
    key = str(data.get("setting_key") or "")
    setting_type = str(data.get("setting_type") or "text")
    return_route = str(data.get("return_route") or ROUTE_MAIN)

    if key not in SETTING_DEFINITIONS:
        await state.clear()
        return await message.answer("کلید تنظیمات پیدا نشد.", reply_markup=admin_main_menu_keyboard())

    value_to_store = raw_text
    if key in {"conversion_source_plan_ids", "conversion_source_group_names"} and raw_text in {"پاک", "خالی", "-", "clear"}:
        value_to_store = ""

    if key == PAYMENT_COMMON_AMOUNT_SETTING_KEY:
        amounts = parse_payment_common_amounts(value_to_store)
        if not amounts:
            return await message.answer(
                "هیچ مبلغ معتبری پیدا نشد. مثال درست: 250 500 750 1000 1250 1500"
            )
        set_payment_common_amounts(amounts)
        label = SETTING_DEFINITIONS[key]["label"]
        await state.clear()
        await message.answer(
            f"✅ «{label}» با موفقیت ذخیره شد:\n{format_payment_common_amounts(amounts)} تومان"
        )
        return await _show_route_message(message, return_route)

    if setting_type == "integer":
        try:
            number = int(value_to_store)
        except Exception:
            return await message.answer("فقط عدد صحیح قابل قبول است. لطفاً دوباره ارسال کنید.")

        if number < 0:
            return await message.answer("عدد منفی معتبر نیست. لطفاً دوباره ارسال کنید.")

        value_to_store = str(number)
    else:
        if key == "conversion_source_plan_ids":
            value_to_store = _parse_list_input(value_to_store, integer=True)
        elif key == "conversion_source_group_names":
            value_to_store = _parse_list_input(value_to_store, integer=False)

        if not value_to_store and key not in {"conversion_source_plan_ids", "conversion_source_group_names"}:
            return await message.answer("متن خالی قابل ذخیره نیست. لطفاً مقدار جدید را ارسال کنید.")

    set_setting(key, value_to_store, value_type=setting_type)
    label = SETTING_DEFINITIONS[key]["label"]
    await state.clear()
    await message.answer(f"✅ «{label}» با موفقیت ذخیره شد.")
    await _show_route_message(message, return_route)
