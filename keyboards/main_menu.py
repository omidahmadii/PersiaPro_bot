from aiogram.types import ReplyKeyboardMarkup, KeyboardButton


def admin_main_menu_keyboard():
    return ReplyKeyboardMarkup(
        keyboard=[

            [KeyboardButton(text="💳 تایید پرداخت ها"), KeyboardButton(text="⚡️ شارژ موقت")],
            [KeyboardButton(text="👥 مدیریت کاربران"), KeyboardButton(text="💳 مدیریت کارت‌ها")],
            [KeyboardButton(text="تغییر رمز عبور"), KeyboardButton(text="📦 مدیریت پلن‌ها")],
            [KeyboardButton(text="📑 گزارشات"), KeyboardButton(text="🚀 فعال‌سازی سرویس ذخیره")],
            [KeyboardButton(text="🌐 مدیریت رکوردها")],
            [KeyboardButton(text="📂 سایر امکانات")],

        ],
        resize_keyboard=False
    )


def admin_other_features_keyboard():
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="📄 تمدید سرویس"), KeyboardButton(text="🛒 خرید سرویس")],
            [KeyboardButton(text="👤 حساب کاربری"), KeyboardButton(text="📦 سرویس‌های من")],
            [KeyboardButton(text="💳 دریافت شماره کارت"), KeyboardButton(text="💷 تعرفه ها"), ],
            [KeyboardButton(text="🔁 انتقال مالکیت سرویس"), KeyboardButton(text="🚀 فعال‌سازی سرویس ذخیره")],
            [KeyboardButton(text="🎫 پشتیبانی"), KeyboardButton(text="📚 آموزش")],
            [KeyboardButton(text="❓ سوالات متداول"), KeyboardButton(text="📬 انتقادات و پیشنهادات"), ],
            [KeyboardButton(text="⬅️ بازگشت به منوی اصلی")],
        ],
        resize_keyboard=True
    )


def user_main_menu_keyboard():
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="🛒 خرید سرویس"), KeyboardButton(text="📄 تمدید سرویس")],
            [KeyboardButton(text="👤 حساب کاربری"), KeyboardButton(text="📦 سرویس‌های من")],
            [KeyboardButton(text="🔁 انتقال مالکیت سرویس"), KeyboardButton(text="📚 آموزش")],
            [KeyboardButton(text="📂 سایر امکانات")],
        ],
        resize_keyboard=True,
        input_field_placeholder="راه اندازی مجدد ربات /start"
    )


def user_other_features_keyboard():
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="💳 شماره کارت"), KeyboardButton(text="💷 تعرفه ها")],
            [KeyboardButton(text="🚀 فعال‌سازی سرویس ذخیره"), KeyboardButton(text="🎫 پشتیبانی")],
            [KeyboardButton(text="📬 انتقادات و پیشنهادات"), KeyboardButton(text="❓ سوالات متداول")],
            [KeyboardButton(text="⬅️ بازگشت به منوی اصلی")],
        ],
        resize_keyboard=True
    )
