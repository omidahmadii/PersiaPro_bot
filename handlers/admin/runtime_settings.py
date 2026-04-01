from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message

from config import ADMINS
from keyboards.main_menu import admin_main_menu_keyboard
from services.runtime_settings import (
    FEATURE_SETTING_KEYS,
    TEXT_SETTING_KEYS,
    SETTING_DEFINITIONS,
    get_bool_setting,
    get_default_setting_value,
    get_text_setting,
    reset_text_settings,
    set_bool_setting,
    set_setting,
)

router = Router()


class RuntimeSettingsState(StatesGroup):
    waiting_for_text = State()


def is_admin(user_id: int) -> bool:
    return user_id in ADMINS


def _preview_text(value: str, limit: int = 64) -> str:
    compact = " ".join((value or "").split())
    if not compact:
        return "خالی"
    if len(compact) <= limit:
        return compact
    return compact[: limit - 1] + "…"


def settings_keyboard() -> InlineKeyboardMarkup:
    rows: list[list[InlineKeyboardButton]] = []

    for key in FEATURE_SETTING_KEYS:
        label = SETTING_DEFINITIONS[key]["label"]
        enabled = get_bool_setting(key, default=get_default_setting_value(key) == "1")
        icon = "✅" if enabled else "🚫"
        rows.append(
            [InlineKeyboardButton(text=f"{icon} {label}", callback_data=f"settings|toggle|{key}")]
        )

    for key in TEXT_SETTING_KEYS:
        label = SETTING_DEFINITIONS[key]["label"]
        rows.append(
            [InlineKeyboardButton(text=f"✏️ {label}", callback_data=f"settings|edit|{key}")]
        )

    rows.append([InlineKeyboardButton(text="♻️ بازنشانی همه پیام‌ها", callback_data="settings|reset_messages")])
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
        "کلیدهای عملیاتی:",
    ]

    for key in FEATURE_SETTING_KEYS:
        label = SETTING_DEFINITIONS[key]["label"]
        enabled = get_bool_setting(key, default=get_default_setting_value(key) == "1")
        lines.append(f"• {label}: {'✅ فعال' if enabled else '🚫 غیرفعال'}")

    lines.extend(["", "پیام‌های قابل ویرایش:"])

    for key in TEXT_SETTING_KEYS:
        label = SETTING_DEFINITIONS[key]["label"]
        preview = _preview_text(get_text_setting(key, ""))
        lines.append(f"• {label}: {preview}")

    lines.extend(["", "برای تغییر هر مورد، دکمه‌ی مربوط به آن را بزنید."])
    return "\n".join(lines)


async def _show_settings_panel_message(message: Message) -> None:
    await message.answer(build_settings_text(), reply_markup=settings_keyboard())


async def _show_settings_panel_callback(callback: CallbackQuery) -> None:
    await callback.message.edit_text(build_settings_text(), reply_markup=settings_keyboard())


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


@router.callback_query(F.data.startswith("settings|toggle|"))
async def runtime_settings_toggle(callback: CallbackQuery):
    if not is_admin(callback.from_user.id):
        return await callback.answer("دسترسی ندارید.", show_alert=True)

    _, _, key = callback.data.split("|", 2)
    if key not in FEATURE_SETTING_KEYS:
        return await callback.answer("تنظیمات نامعتبر است.", show_alert=True)

    new_value = not get_bool_setting(key, default=get_default_setting_value(key) == "1")
    set_bool_setting(key, new_value)

    label = SETTING_DEFINITIONS[key]["label"]
    await callback.answer(f"{label} {'فعال' if new_value else 'غیرفعال'} شد.")
    await _show_settings_panel_callback(callback)


@router.callback_query(F.data.startswith("settings|edit|"))
async def runtime_settings_edit(callback: CallbackQuery, state: FSMContext):
    if not is_admin(callback.from_user.id):
        return await callback.answer("دسترسی ندارید.", show_alert=True)

    _, _, key = callback.data.split("|", 2)
    if key not in TEXT_SETTING_KEYS:
        return await callback.answer("پیام نامعتبر است.", show_alert=True)

    label = SETTING_DEFINITIONS[key]["label"]
    current_value = get_text_setting(key, "")
    await state.set_state(RuntimeSettingsState.waiting_for_text)
    await state.update_data(setting_key=key)
    await callback.message.edit_text(
        f"متن جدید برای «{label}» را ارسال کنید.\n\n"
        f"متن فعلی:\n{current_value}\n\n"
        "برای لغو، عبارت «لغو» را ارسال کنید."
    )


@router.callback_query(F.data == "settings|reset_messages")
async def runtime_settings_reset_messages(callback: CallbackQuery, state: FSMContext):
    if not is_admin(callback.from_user.id):
        return await callback.answer("دسترسی ندارید.", show_alert=True)

    await state.clear()
    reset_text_settings()
    await callback.answer("همه پیام‌ها به مقدار پیش‌فرض برگشتند.")
    await _show_settings_panel_callback(callback)


@router.callback_query(F.data == "settings|close")
async def runtime_settings_close(callback: CallbackQuery, state: FSMContext):
    if not is_admin(callback.from_user.id):
        return await callback.answer("دسترسی ندارید.", show_alert=True)

    await state.clear()
    await callback.message.edit_text("پنل تنظیمات بسته شد.")
    await callback.message.answer("بازگشت به منوی ادمین.", reply_markup=admin_main_menu_keyboard())


@router.message(RuntimeSettingsState.waiting_for_text)
async def runtime_settings_receive_text(message: Message, state: FSMContext):
    if not is_admin(message.from_user.id):
        await state.clear()
        return

    text = (message.text or "").strip()
    if not text:
        return await message.answer("متن خالی قابل ذخیره نیست. لطفاً متن جدید را ارسال کنید.")

    if text in {"لغو", "انصراف"}:
        await state.clear()
        return await _show_settings_panel_message(message)

    data = await state.get_data()
    key = data.get("setting_key")

    if key not in TEXT_SETTING_KEYS:
        await state.clear()
        return await message.answer("کلید تنظیمات پیدا نشد.", reply_markup=admin_main_menu_keyboard())

    set_setting(key, text, value_type="text")
    label = SETTING_DEFINITIONS[key]["label"]
    await state.clear()
    await message.answer(
        f"✅ «{label}» با موفقیت ذخیره شد.\n\n{build_settings_text()}",
        reply_markup=settings_keyboard(),
    )
