from aiogram.types import KeyboardButton, ReplyKeyboardMarkup

from config import ADMINS


def is_admin_user(user_id: int) -> bool:
    return str(user_id) in {str(admin_id) for admin_id in ADMINS}


def main_menu_keyboard_for_user(user_id: int):
    return admin_main_menu_keyboard() if is_admin_user(user_id) else user_main_menu_keyboard()


def admin_main_menu_keyboard():
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="💳 تایید پرداخت ها"), KeyboardButton(text="🏦 تایید حسابداری")],
            [KeyboardButton(text="⚡️ شارژ موقت"), KeyboardButton(text="👥 مدیریت کاربران")],
            [KeyboardButton(text="📢 ارسال پیام"), KeyboardButton(text="💳 مدیریت کارت‌ها")],
            [KeyboardButton(text="📦 مدیریت پلن‌ها"), KeyboardButton(text="🎯 مخاطب پلن‌ها")],
            [KeyboardButton(text="📑 گزارشات"), KeyboardButton(text="🚀 فعال‌سازی سرویس ذخیره")],
            [KeyboardButton(text="🌐 مدیریت رکوردها"), KeyboardButton(text="⚙️ تنظیمات ربات")],
            [KeyboardButton(text="تغییر رمز عبور")],
            [KeyboardButton(text="📂 سایر امکانات")],
        ],
        resize_keyboard=False,
    )


def admin_other_features_keyboard():
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="📄 تمدید سرویس"), KeyboardButton(text="🛒 خرید سرویس")],
            [KeyboardButton(text="👤 حساب کاربری"), KeyboardButton(text="📦 سرویس‌های من")],
            [KeyboardButton(text="🔐 تغییر رمز سرویس"), KeyboardButton(text="💳 شارژ حساب")],
            [KeyboardButton(text="💷 تعرفه ها")],
            [KeyboardButton(text="🔁 انتقال مالکیت سرویس"), KeyboardButton(text="🚀 فعال‌سازی سرویس ذخیره")],
            [KeyboardButton(text="🎫 پشتیبانی"), KeyboardButton(text="📚 آموزش")],
            [KeyboardButton(text="❓ سوالات متداول"), KeyboardButton(text="📬 انتقادات و پیشنهادات")],
            [KeyboardButton(text="⬅️ بازگشت به منوی اصلی")],
        ],
        resize_keyboard=True,
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
        input_field_placeholder="راه‌اندازی مجدد ربات /start",
    )


def user_other_features_keyboard():
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="🔐 تغییر رمز سرویس"), KeyboardButton(text="💳 شارژ حساب")],
            [KeyboardButton(text="💷 تعرفه ها")],
            [KeyboardButton(text="🚀 فعال‌سازی سرویس ذخیره"), KeyboardButton(text="🎫 پشتیبانی")],
            [KeyboardButton(text="📬 انتقادات و پیشنهادات"), KeyboardButton(text="❓ سوالات متداول")],
            [KeyboardButton(text="⬅️ بازگشت به منوی اصلی")],
        ],
        resize_keyboard=True,
    )
