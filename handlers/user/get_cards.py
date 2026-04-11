from aiogram import Router, F
from aiogram.fsm.context import FSMContext
from aiogram.types import Message

from config import ADMINS
from keyboards.main_menu import user_main_menu_keyboard, admin_main_menu_keyboard
from services.db import get_active_cards, update_last_name

router = Router()


@router.message(F.text.in_({"💳 شماره کارت", "شماره کارت"}))
async def show_cards(message: Message):
    user_id = message.from_user.id
    last_name = message.from_user.last_name
    if last_name:
        update_last_name(user_id=user_id, last_name=last_name)

    role = "admin" if user_id in ADMINS else "user"
    keyboard = admin_main_menu_keyboard() if role == "admin" else user_main_menu_keyboard()

    active_cards = get_active_cards()

    if not active_cards:
        await message.answer(
            "❌ در حال حاضر هیچ کارت فعالی موجود نیست.",
            parse_mode="HTML"
        )
    else:
        # متن پایه
        text = "💳 برای شارژ حساب لطفاً مبلغ مورد نظر را به یکی از شماره کارت‌های زیر واریز کنید:\n\n"

        # اضافه کردن هر کارت به متن
        for card in active_cards:
            text += (
                f"🏦 {card['bank_name']} "
                f"به نام {card['owner_name']}\n"
                f"<code>\u200F{card['card_number']}</code>\n\n"
            )

        # ادامه متن ثابت
        text += (
            "📸 سپس تصویر فیش پرداخت را ارسال نمایید.\n"
            "<b>\u200Fℹ️ برای کپی کردن شماره کارت روی آن بزنید.</b>"
        )

        # ارسال پیام
        await message.answer(
            text,
            parse_mode="HTML",
            reply_markup=keyboard
        )
