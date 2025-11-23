from aiogram import Router, F
from aiogram.types import Message
from config import ADMINS
from keyboards.main_menu import user_main_menu_keyboard, admin_main_menu_keyboard

router = Router()


@router.message(F.text == "🎫 پشتیبانی")
async def support_handler(message: Message):
    user_id = message.from_user.id
    role = "admin" if user_id in ADMINS else "user"
    keyboard = admin_main_menu_keyboard() if role == "admin" else user_main_menu_keyboard()
    await message.answer(
        "<a href='https://t.me/persiapro_support'>‌</a>"  # لینک مخفی، فقط برای اینکه آواتار نمایش داده بشه
        "\n📞 برای پشتیبانی روی دکمه زیر بزنید:\n"
        "\u200F<a href='https://t.me/persiapro_support'>🆘\u200E ارتباط با پشتیبانی</a>\n"
        "🕘 پاسخگویی معمولاً کمتر از ۲ ساعت انجام میشه.",
        parse_mode="HTML", reply_markup=keyboard
    )
