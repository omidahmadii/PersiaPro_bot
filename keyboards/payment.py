from aiogram.types import ReplyKeyboardMarkup, KeyboardButton
from aiogram.types import ReplyKeyboardMarkup, KeyboardButton


def payment_keyboard():
    return ReplyKeyboardMarkup(
        keyboard=[
            #[KeyboardButton(text="📸 ارسال رسید پرداخت")],
            [KeyboardButton(text="🔙 بازگشت به منوی اصلی")]
        ],
        resize_keyboard=True,
        input_field_placeholder="لطفاً یک گزینه را انتخاب کنید:"
    )
