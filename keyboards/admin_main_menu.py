from aiogram.types import ReplyKeyboardMarkup, KeyboardButton


def admin_main_menu_keyboard():
    return ReplyKeyboardMarkup(
        keyboard=[

            [KeyboardButton(text="💳 تایید پرداخت ها"), KeyboardButton(text="⚡️ شارژ موقت")],
            [KeyboardButton(text="👥 مدیریت کاربران"), KeyboardButton(text="💳 مدیریت کارت‌ها")],
            [KeyboardButton(text="تغییر رمز عبور"), KeyboardButton(text="📦 مدیریت پلن‌ها")],
            [KeyboardButton(text="📑 گزارشات"), KeyboardButton(text="🚀 فعال‌سازی سرویس ذخیره")],
            [KeyboardButton(text="🌐 مدیریت رکوردها") ],

            [KeyboardButton(text="📄 تمدید سرویس"), KeyboardButton(text="🛒 خرید سرویس")],
            [KeyboardButton(text="👤 حساب کاربری"), KeyboardButton(text="📦 سرویس‌های من")],
            [KeyboardButton(text="💳 دریافت شماره کارت"), KeyboardButton(text="💷 تعرفه ها"), ],
            [KeyboardButton(text="🚀 فعال‌سازی سرویس ذخیره"), ],
            [KeyboardButton(text="🎫 پشتیبانی"), KeyboardButton(text="📚 آموزش")],
            [KeyboardButton(text="❓ سوالات متداول"), KeyboardButton(text="📬 انتقادات و پیشنهادات"), ],
        ],
        resize_keyboard=True
    )

