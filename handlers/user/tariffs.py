from aiogram import Router, F
from aiogram.types import Message
from config import ADMINS
from keyboards.main_menu import admin_main_menu_keyboard, user_main_menu_keyboard

router = Router()

@router.message(F.text == "💷 ﺖﻋﺮﻔﻫ ﻩﺍ")
async def support_handler(message: Message):
    user_id = message.from_user.id
    role = "admin" if user_id in ADMINS else "user"
    keyboard = admin_main_menu_keyboard() if role == "admin" else user_main_menu_keyboard()
    text = (
        "<b>💷 ﻝیﺲﺗ ﺖﻋﺮﻔﻫ<200c>ﻫﺍ</b>\n\n"

        "📦 <b>ﺪﺴﺘﻫ<200c>ﺒﻧﺩی: ﻢﻌﻣﻮﻟی</b>\n"
        "60 ﺭﻭﺯ 3 ﺭﻭﺯ ﻩﺩیﻩ 80 گیگ <b>500,000 ﺕﻮﻣﺎﻧ</b>\n"
        "90 ﺭﻭﺯ 7 ﺭﻭﺯ ﻩﺩیﻩ 120 گیگ <b>600,000 ﺕﻮﻣﺎﻧ</b>\n\n"

        "🌐 <b>ﺪﺴﺘﻫ<200c>ﺒﻧﺩی: IP ﺙﺎﺒﺗ</b>\n"
        "60 ﺭﻭﺯ 3 ﺭﻭﺯ ﻩﺩیﻩ 80 گیگ <b>600,000 ﺕﻮﻣﺎﻧ</b>\n"
        "90 ﺭﻭﺯ 7 ﺭﻭﺯ ﻩﺩیﻩ 120 گیگ <b>700,000 ﺕﻮﻣﺎﻧ</b>\n\n"

        "🤖 ﺥﺭیﺩ ﻭ ﺖﻣﺩیﺩ ﺱﺭﻭیﺱ ﺍﺯ ﻁﺭیﻕ ﺮﺑﺎﺗ ﺎﻨﺟﺎﻣ ﻡی<200c>ﺵﻭﺩ.\n"
        "📞 ﺏﺭﺍی ﺎﻃﻼﻋﺎﺗ ﺏیﺶﺗﺭ ﺏﺍ پﺶﺗیﺏﺎﻧی ﺩﺭ ﺖﻣﺎﺳ ﺏﺎﺷیﺩ."
    )

    await message.answer(
        text, parse_mode="HTML", reply_markup=keyboard
    )
