# handlers/user/activate_stored.py

from typing import List, Dict, Any
from config import ADMINS

import jdatetime
from aiogram import Router, F
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import (
    Message,
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
)
from keyboards.main_menu import user_main_menu_keyboard
from services import IBSng
from services.admin_notifier import send_message_to_admins
from services.db import (
    get_services_waiting_for_renew,
    update_order_status, set_order_expiry_to_now, get_services_waiting_for_renew_admin,
    # set_order_expiry_to_now,
)

router = Router()


class ActivateStates(StatesGroup):
    choosing_service = State()
    confirming = State()


def kb_services_inline(services: List[Dict[str, Any]]) -> InlineKeyboardMarkup:
    rows = [[
        InlineKeyboardButton(
            text=f"{s['username']} • انقضا: {s['expires_at']}",
            callback_data=f"activate|service|{s['id']}"
        )
    ] for s in services]
    return InlineKeyboardMarkup(inline_keyboard=rows)


def kb_confirm(prefix: str = "activate") -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✅ تایید فعال‌سازی", callback_data=f"{prefix}|confirm")],
        [InlineKeyboardButton(text="❌ انصراف", callback_data=f"{prefix}|cancel_not_paid_waiting_for_payment_orders.py")],
    ])


@router.message(F.text == "🚀 فعال‌سازی سرویس ذخیره")
async def activate_start(message: Message, state: FSMContext):
    user_id = message.from_user.id

    # شرط ادمین بودن
    if user_id in ADMINS:
        services = get_services_waiting_for_renew_admin()
    else:
        services = get_services_waiting_for_renew(user_id)

    if not services:
        return await message.answer(
            "⚠️ هیچ سرویسی در وضعیت ذخیره یافت نشد.",
            reply_markup=user_main_menu_keyboard()
        )

    await state.clear()
    await state.update_data(services=services)

    if len(services) == 1:
        # فقط یک سرویس → مستقیم برو مرحله تایید
        selected_service = services[0]
        await state.update_data(selected_service=selected_service)
        await state.set_state(ActivateStates.confirming)
        return await message.answer(
            f"🔹 سرویس: `{selected_service['username']}`\n\n"
            "⚠️ توجه:\n"
            "با فعال‌سازی سرویس، زمان و حجم قبلی منتقل نخواهد شد و امکان بازگشت وجود ندارد.\n\n"
            "آیا مطمئن هستید؟",
            reply_markup=kb_confirm(),
            parse_mode="Markdown"
        )

    # چند سرویس → باید یکی رو انتخاب کنه
    await state.set_state(ActivateStates.choosing_service)
    return await message.answer(
        "لطفاً سرویس ذخیره‌ای که می‌خواهید فعال کنید را انتخاب نمایید:",
        reply_markup=kb_services_inline(services)
    )


@router.callback_query(F.data.startswith("activate|service"))
async def activate_choose_service(callback: CallbackQuery, state: FSMContext):
    _, _, service_id = callback.data.split("|")
    data = await state.get_data()
    services = data.get("services", [])
    selected_service = next((s for s in services if str(s["id"]) == service_id), None)

    if not selected_service:
        return await callback.answer("سرویس معتبر نیست.", show_alert=True)

    await state.update_data(selected_service=selected_service)
    await state.set_state(ActivateStates.confirming)

    return await callback.message.edit_text(
        f"🔹 سرویس: `{selected_service['username']}`\n\n"
        "⚠️ توجه:\n"
        "با فعال‌سازی سرویس، زمان و حجم قبلی منتقل نخواهد شد و امکان بازگشت وجود ندارد.\n\n"
        "آیا مطمئن هستید؟",
        reply_markup=kb_confirm(),
        parse_mode="Markdown"
    )


@router.callback_query(F.data == "activate|confirm")
async def activate_confirm(callback: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    selected_service = data.get("selected_service")

    if not selected_service:
        await state.clear()
        return await callback.message.edit_text(
            "❌ خطا در دریافت اطلاعات. لطفاً دوباره تلاش کنید.",
            reply_markup=user_main_menu_keyboard()
        )

    service_id = selected_service["id"]
    username = selected_service["username"]
    now = jdatetime.datetime.now()
    expiry_str = now.strftime("%Y-%m-%d %H:%M")  # مثال: 1404-07-07 23:47

    # تاریخ پایان رو الان بزن
    set_order_expiry_to_now(expiry_str=expiry_str, service_id=service_id)

    # وضعیت رو active کن
    # update_order_status(order_id=service_id, new_status="active")

    # ریست اکانت (که تو سیکل بعدی همه‌چی درست میشه)
    IBSng.reset_account_client(username=username)

    # گزارش به ادمین
    text_admin = (
        "🔔 فعال‌سازی سرویس ذخیره\n"
        f"👤 کاربر: {callback.from_user.id}\n"
        f"🆔 یوزرنیم: {username}\n"
        f"📅 تاریخ پایان → الان ثبت شد\n"
        "🟢 وضعیت: فعال شد"
    )
    await send_message_to_admins(text_admin)

    await callback.message.edit_text(
        f"✅ سرویس `{username}` با موفقیت فعال شد.",
        parse_mode="Markdown"
    )
    await callback.message.answer("بازگشت به منوی اصلی", reply_markup=user_main_menu_keyboard())
    await state.clear()


@router.callback_query(F.data == "activate|cancel_not_paid_waiting_for_payment_orders.py")
async def activate_cancel(callback: CallbackQuery, state: FSMContext):
    await state.clear()
    await callback.message.edit_text(
        "❌ عملیات فعال‌سازی لغو شد.",
        reply_markup=user_main_menu_keyboard()
    )
