from aiogram.types import ReplyKeyboardMarkup, KeyboardButton


def user_main_menu_keyboard():
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="📦 سرویس‌های من"),
             KeyboardButton(text="💳 دریافت شماره کارت")],
            [KeyboardButton(text="📄 تمدید سرویس"),
             KeyboardButton(text="🛒 خرید سرویس")],
            [KeyboardButton(text="👤 حساب کاربری"),
             KeyboardButton(text="🚀 فعال‌سازی سرویس ذخیره")],
            [KeyboardButton(text="🎫 پشتیبانی"),
             KeyboardButton(text="📚 آموزش")],
            [KeyboardButton(text="❓ سوالات متداول"),
             KeyboardButton(text="📬 انتقادات و پیشنهادات"), ],
        ],
        resize_keyboard=True,
        input_field_placeholder="راه اندازی مجدد ربات /start"
    )
