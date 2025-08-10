from aiogram import Router, F
from aiogram.types import Message

from config import ADMINS
from keyboards.admin_main_menu import admin_main_menu_keyboard
from services.db import get_user_info
from keyboards.user_main_menu import user_main_menu_keyboard

router = Router()


@router.message(F.text == "👤 حساب کاربری")
async def show_user_profile(message: Message):
    user_id = message.from_user.id
    # logger.info(f"{user_id} | 👤 حساب کاربری ")
    user = get_user_info(user_id)
    role = "admin" if user_id in ADMINS else "user"
    if user:
        first_name, username, created_at, balance, role = user
        username = f"@{username}" if username else "ندارد"

        text = (
            f"👤 نام: {first_name}\n"
            f"🔰 یوزرنیم: {username}\n"
            f"\u200F 🆔 آیدی تلگرام: <code>{user_id}</code>\n"
            f"🎚 نقش: {'ادمین' if role == 'admin' else 'کاربر'}\n"
            f"💰 موجودی: {balance} تومان\n"
            f"📅 عضویت: {created_at.split('T')[0]}"
        )


    else:
        text = "❌ اطلاعاتی برای شما یافت نشد!"

    keyboard = admin_main_menu_keyboard() if role == "admin" else user_main_menu_keyboard()
    # logger.info(f"{user_id} | {text}")
    await message.answer(text, reply_markup=keyboard)
