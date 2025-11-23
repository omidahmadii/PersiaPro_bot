from aiogram import Router, F
from aiogram.types import Message
from config import ADMINS
from keyboards.main_menu import admin_main_menu_keyboard, user_main_menu_keyboard

router = Router()


@router.message(F.text == "💷 تعرفه ها")
async def support_handler(message: Message):
    user_id = message.from_user.id
    role = "admin" if user_id in ADMINS else "user"
    keyboard = admin_main_menu_keyboard() if role == "admin" else user_main_menu_keyboard()
    text = (
        "<b>💷 لیست تعرفه‌ها</b>\n\n"
        "📦 <b>دسته‌بندی: معمولی</b>\n"
        "30 روز 40 گیگ <b>125,000 تومان</b>\n"
        "60 روز 3 روز هدیه 80 گیگ <b>250,000 تومان</b>\n"
        "90 روز 7 روز هدیه 120 گیگ <b>375,000 تومان</b>\n"
        "180 روز 14 روز هدیه 240 گیگ <b>750,000 تومان</b>\n\n"

        "🌐 <b>دسته‌بندی: IP ثابت</b>\n"
        "30 روز 40 گیگ <b>150,000 تومان</b>\n"
        "60 روز 3 روز هدیه 80 گیگ <b>300,000 تومان</b>\n"
        "90 روز 7 روز هدیه 120 گیگ <b>450,000 تومان</b>\n"
        "180 روز 14 روز هدیه 240 گیگ <b>900,000 تومان</b>\n\n"

        "📶 <b>دسته‌بندی: مودم، روتر، تلویزیون</b>\n"
        "30 روز مودم 100 گیگ <b>350,000 تومان</b>\n"
        "30 روز مودم 150 گیگ <b>500,000 تومان</b>\n"
        "30 روز مودم 200 گیگ <b>650,000 تومان</b>\n\n"

        "🌟 <b>دسته‌بندی: ایران (اتصال از خارج به داخل)</b>\n"
        "30 روز 40 گیگ <b>150,000 تومان</b>\n\n"

        "🤖 خرید و تمدید سرویس از طریق ربات انجام می‌شود.\n"
        "📞 برای اطلاعات بیشتر با پشتیبانی در تماس باشید."
    )

    await message.answer(
        text, parse_mode="HTML", reply_markup=keyboard
    )
