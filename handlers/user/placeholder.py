from aiogram import Router
from aiogram.types import Message
from aiogram.filters import StateFilter
from aiogram.fsm.context import FSMContext
from keyboards.user_main_menu import user_main_menu_keyboard

router = Router()


@router.message(StateFilter(None))  # فقط وقتی کاربر در هیچ وضعیت فعالی نیست
async def unknown_message_handler(message: Message, state: FSMContext):
    await message.answer(
        "❓ دستور نامعتبر است. لطفاً از دکمه‌های موجود استفاده کنید.",
        reply_markup=user_main_menu_keyboard()
    )
