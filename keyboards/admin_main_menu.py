from aiogram.types import ReplyKeyboardMarkup, KeyboardButton


def admin_main_menu_keyboard():
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="💳 تایید پرداخت ها"), KeyboardButton(text="⚡️ شارژ موقت")],
            [KeyboardButton(text="تغییر رمز عبور")],
            [KeyboardButton(text="📦 سرویس‌های من"), KeyboardButton(text="💳 دریافت شماره کارت")],
            [KeyboardButton(text="📄 تمدید سرویس"), KeyboardButton(text="🛒 خرید سرویس")],
            [KeyboardButton(text="🎫 پشتیبانی"), KeyboardButton(text="📚 آموزش")],
            [KeyboardButton(text="👤 حساب کاربری"), KeyboardButton(text="❓ سوالات متداول")],
            [KeyboardButton(text="📬 انتقادات و پیشنهادات")],
        ],
        resize_keyboard=True
    )

