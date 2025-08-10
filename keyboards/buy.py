from aiogram.types import ReplyKeyboardMarkup, KeyboardButton

confirm_service_keyboard = ReplyKeyboardMarkup(
    keyboard=[
        [KeyboardButton(text="✅ تایید و ساخت سرویس")],
        [KeyboardButton(text="🔙 بازگشت به منو")]
    ],
    resize_keyboard=True
)
