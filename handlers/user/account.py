from aiogram import Router, F
from aiogram.types import Message

from config import ADMINS
from keyboards.main_menu import admin_main_menu_keyboard, user_main_menu_keyboard
from services.db import get_user_info

router = Router()


@router.message(F.text == "👤 حساب کاربری")
async def show_user_profile(message: Message):
    user_id = message.from_user.id
    # logger.info(f"{user_id} | 👤 حساب کاربری ")
    user = get_user_info(user_id)
    role = "admin" if user_id in ADMINS else "user"
    if user:
        first_name, username, created_at, balance, role = user
        safe_username = f"@{username}" if username else "ندارد"

        text = (
            f"👤 <b>اطلاعات حساب کاربری</b>\n\n"
            f"🧾 نام: <b>{first_name}</b>\n"
            f"🔰 یوزرنیم: <b>{safe_username}</b>\n"
            f"💰 موجودی: <b>{balance}</b> تومان\n"
            f"📅 تاریخ عضویت: <b>{created_at.split('T')[0]}</b>\n\n"
            f"━━━━━━━━━━━━━━\n"
            f"🔐 <b>شناسه انتقال مالکیت</b>\n\n"
            f"این شناسه را برای شخصی که می‌خواهد سرویس را به شما منتقل کند بفرستید:\n\n"
            f"<code>{user_id}</code>\n"
            f"━━━━━━━━━━━━━━"
        )

    else:
        text = "❌ اطلاعاتی برای شما یافت نشد!"

    keyboard = admin_main_menu_keyboard() if role == "admin" else user_main_menu_keyboard()
    # logger.info(f"{user_id} | {text}")
    await message.answer(text, reply_markup=keyboard)
