from aiogram.types import ReplyKeyboardMarkup, KeyboardButton


def admin_main_menu_keyboard():
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="💳 تایید پرداخت ها")],
            [KeyboardButton(text="🛒 خرید سرویس"), KeyboardButton(text="💳 دریافت شماره کارت")],
            [KeyboardButton(text="👤 حساب کاربری"), KeyboardButton(text="📦 سرویس‌های من")],
            [KeyboardButton(text="🎫 پشتیبانی"), KeyboardButton(text="📚 آموزش")],
            [KeyboardButton(text="تغییر رمز عبور"), KeyboardButton(text="📬 انتقادات و پیشنهادات")],

        ],
        resize_keyboard=True
    )


"""
def admin_main_menu_keyboard():
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="🛒 خرید سرویس جدید"), KeyboardButton(text="🔄 تمدید سرویس")],
            [KeyboardButton(text="📦 سرویس‌های من"), KeyboardButton(text="💳 پرداخت")],
            [KeyboardButton(text="🎫 تیکت پشتیبانی"), KeyboardButton(text="📚 آموزش اتصال")],
            [KeyboardButton(text="👤 حساب کاربری"),KeyboardButton(text="💳 تایید پرداخت ها")],
        ],
        resize_keyboard=True
    )
"""
