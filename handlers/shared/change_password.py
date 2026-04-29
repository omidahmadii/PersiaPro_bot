import re
from typing import Dict, List, Optional

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message

from config import ADMINS
from keyboards.main_menu import main_menu_keyboard_for_user
from services.IBSng import change_password as ibs_change_password
from services.db import (
    get_accounts_id_by_username,
    get_user_services_for_password_change,
    update_account_password_by_username,
)

router = Router()

PASSWORD_RULES_TEXT = (
    "رمز جدید را بفرست.\n"
    "شرایط رمز:\n"
    "• حداقل 4 رقم باشد\n"
    "• رقم اول 0 نباشد"
)


class AdminChangePasswordState(StatesGroup):
    waiting_for_username = State()
    waiting_for_new_password = State()


class ServicePasswordState(StatesGroup):
    waiting_for_service_selection = State()
    waiting_for_new_password = State()


def is_admin(user_id: int) -> bool:
    return str(user_id) in {str(admin_id) for admin_id in ADMINS}


def validate_new_password(password: str) -> Optional[str]:
    password = (password or "").strip()
    if not re.fullmatch(r"\d{4,}", password):
        return "رمز باید حداقل 4 رقم باشد."
    if password.startswith("0"):
        return "رقم اول رمز نباید 0 باشد."
    return None


def service_status_label(status: Optional[str]) -> str:
    mapping = {
        "active": "فعال",
        "expired": "منقضی",
        "waiting_for_renewal": "در انتظار تمدید",
        "waiting_for_renewal_not_paid": "تمدید در انتظار پرداخت",
        "reserved": "ذخیره",
    }
    return mapping.get(status or "", "سرویس")


def service_password_keyboard(services: List[Dict]) -> InlineKeyboardMarkup:
    rows = []
    for service in services:
        plan_name = service.get("plan_name") or "بدون نام"
        status_text = service_status_label(service.get("status"))
        text = f"{service['username']} • {status_text} • {plan_name}"
        rows.append([
            InlineKeyboardButton(
                text=text[:64],
                callback_data=f"service_pw|select|{service['account_id']}",
            )
        ])

    rows.append([InlineKeyboardButton(text="❌ انصراف", callback_data="service_pw|cancel")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


async def apply_password_change(username: str, new_password: str) -> tuple[bool, str]:
    try:
        success = ibs_change_password(username=username, password=new_password)
    except Exception as exc:
        return False, f"خطا در تغییر رمز در IBS: {exc}"

    if not success:
        return False, "تغییر رمز در IBS ناموفق بود."

    update_account_password_by_username(username=username, new_password=new_password)
    return True, "رمز با موفقیت تغییر کرد."


@router.message(F.text == "تغییر رمز عبور")
async def admin_change_password_start(message: Message, state: FSMContext):
    user_id = message.from_user.id
    if not is_admin(user_id):
        await message.answer(
            "برای تغییر رمز سرویس خودت از دکمه «🔐 تغییر رمز» استفاده کن.",
            reply_markup=main_menu_keyboard_for_user(user_id),
        )
        return

    await state.clear()
    await state.set_state(AdminChangePasswordState.waiting_for_username)
    await message.answer("لطفاً نام کاربری سرویس موردنظر را وارد کنید.")


@router.message(AdminChangePasswordState.waiting_for_username)
async def admin_receive_username(message: Message, state: FSMContext):
    username = (message.text or "").strip()
    accounts_id = get_accounts_id_by_username(username)
    if not accounts_id:
        await message.answer(
            "❌ اکانتی با این نام پیدا نشد. دوباره تلاش کنید یا از منو خارج شوید.",
            reply_markup=main_menu_keyboard_for_user(message.from_user.id),
        )
        await state.clear()
        return

    await state.update_data(username=username)
    await state.set_state(AdminChangePasswordState.waiting_for_new_password)
    await message.answer(f"✅ اکانت <code>{username}</code> پیدا شد.\n\n{PASSWORD_RULES_TEXT}", parse_mode="HTML")


@router.message(AdminChangePasswordState.waiting_for_new_password)
async def admin_set_new_password(message: Message, state: FSMContext):
    new_password = (message.text or "").strip()
    error = validate_new_password(new_password)
    if error:
        await message.answer(f"❌ {error}\n\n{PASSWORD_RULES_TEXT}")
        return

    data = await state.get_data()
    username = data.get("username")
    if not username:
        await state.clear()
        await message.answer(
            "اطلاعات عملیات پیدا نشد. دوباره از اول شروع کنید.",
            reply_markup=main_menu_keyboard_for_user(message.from_user.id),
        )
        return

    success, result_message = await apply_password_change(username, new_password)
    await state.clear()
    await message.answer(
        ("✅ " if success else "❌ ") + result_message,
        reply_markup=main_menu_keyboard_for_user(message.from_user.id),
    )


@router.message(F.text == "🔐 تغییر رمز")
async def service_password_start(message: Message, state: FSMContext):
    user_id = message.from_user.id
    if is_admin(user_id):
        await admin_change_password_start(message, state)
        return

    services = get_user_services_for_password_change(user_id)
    if not services:
        await state.clear()
        await message.answer(
            "هیچ سرویسی برای تغییر رمز پیدا نشد.",
            reply_markup=main_menu_keyboard_for_user(user_id),
        )
        return

    await state.clear()
    await state.update_data(service_password_services=services)
    await state.set_state(ServicePasswordState.waiting_for_service_selection)
    await message.answer(
        "سرویسی که می‌خواهی رمزش تغییر کند را انتخاب کن:",
        reply_markup=service_password_keyboard(services),
    )


@router.callback_query(F.data == "service_pw|cancel")
async def service_password_cancel(callback: CallbackQuery, state: FSMContext):
    await state.clear()
    await callback.message.edit_text("عملیات تغییر رمز سرویس لغو شد.")
    await callback.message.answer(
        "بازگشت به منوی اصلی",
        reply_markup=main_menu_keyboard_for_user(callback.from_user.id),
    )
    await callback.answer()


@router.callback_query(F.data.startswith("service_pw|select|"))
async def service_password_select(callback: CallbackQuery, state: FSMContext):
    account_id = int(callback.data.split("|")[2])
    data = await state.get_data()
    services = data.get("service_password_services") or []
    selected_service = next((service for service in services if int(service["account_id"]) == account_id), None)

    if not selected_service:
        await callback.answer("این سرویس دیگر معتبر نیست. دوباره از ابتدا شروع کن.", show_alert=True)
        await state.clear()
        return

    await state.update_data(selected_service_username=selected_service["username"])
    await state.set_state(ServicePasswordState.waiting_for_new_password)
    await callback.message.edit_text(
        f"برای سرویس <code>{selected_service['username']}</code> رمز جدید را بفرست.\n\n{PASSWORD_RULES_TEXT}",
        parse_mode="HTML",
    )
    await callback.answer()


@router.message(ServicePasswordState.waiting_for_new_password)
async def service_password_set_new_password(message: Message, state: FSMContext):
    new_password = (message.text or "").strip()
    error = validate_new_password(new_password)
    if error:
        await message.answer(f"❌ {error}\n\n{PASSWORD_RULES_TEXT}")
        return

    data = await state.get_data()
    username = data.get("selected_service_username")
    if not username:
        await state.clear()
        await message.answer(
            "اطلاعات عملیات پیدا نشد. دوباره از اول شروع کنید.",
            reply_markup=main_menu_keyboard_for_user(message.from_user.id),
        )
        return

    success, result_message = await apply_password_change(username, new_password)
    await state.clear()
    await message.answer(
        ("✅ " if success else "❌ ") + result_message + f"\n\nاکانت: <code>{username}</code>",
        parse_mode="HTML",
        reply_markup=main_menu_keyboard_for_user(message.from_user.id),
    )
