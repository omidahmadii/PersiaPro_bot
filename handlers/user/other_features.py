from aiogram import Router, F
from aiogram.types import Message


from keyboards.main_menu import user_main_menu_keyboard, admin_main_menu_keyboard, admin_other_features_keyboard,user_other_features_keyboard
from config import ADMINS, CHANNEL_ID

router = Router()


@router.message(F.text == "📂 سایر امکانات")
async def show_other_features(message: Message):
    user = message.from_user
    user_id = user.id
    role = "admin" if user_id in ADMINS else "user"
    if role=="admin":
        await message.answer(
            "🔧 سایر امکانات:",
            reply_markup=admin_other_features_keyboard()
        )
    else:
        await message.answer(
            "🔧 سایر امکانات:",
            reply_markup=user_other_features_keyboard()
        )


@router.message(F.text == "⬅️ بازگشت به منوی اصلی")
async def back_to_main_menu(message: Message):
    user = message.from_user
    user_id = user.id
    role = "admin" if user_id in ADMINS else "user"
    if role=="admin":
        await message.answer(
            "🏠 بازگشت به منوی اصلی:",
            reply_markup=admin_main_menu_keyboard()
        )
    else:
        await message.answer(
            "🏠 بازگشت به منوی اصلی:",
            reply_markup=user_main_menu_keyboard()
        )



