from aiogram.types import KeyboardButton, ReplyKeyboardMarkup

from config import ADMINS
from services.conversion_offer import get_conversion_menu_title, is_conversion_menu_enabled


def is_admin_user(user_id: int) -> bool:
    return str(user_id) in {str(admin_id) for admin_id in ADMINS}


def main_menu_keyboard_for_user(user_id: int):
    return admin_main_menu_keyboard() if is_admin_user(user_id) else user_main_menu_keyboard()


def _activation_and_conversion_row() -> list[KeyboardButton]:
    row = [KeyboardButton(text="🚀 فعال‌سازی سرویس ذخیره")]
    if is_conversion_menu_enabled():
        row.append(KeyboardButton(text=get_conversion_menu_title()))
    return row


def admin_main_menu_keyboard():
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="💳 تایید پرداخت ها"), KeyboardButton(text="🏦 تایید حسابداری")],
            [KeyboardButton(text="⚡️ شارژ موقت"), KeyboardButton(text="👥 مدیریت کاربران")],
            [KeyboardButton(text="📢 ارسال پیام"), KeyboardButton(text="💳 مدیریت کارت‌ها")],
            [KeyboardButton(text="📦 مدیریت پلن‌ها"), KeyboardButton(text="🎯 مخاطب پلن‌ها")],
            [KeyboardButton(text="📑 گزارشات"), KeyboardButton(text="🚀 فعال‌سازی سرویس ذخیره")],
            [KeyboardButton(text="🧾 مدیریت سفارش‌ها"), KeyboardButton(text="📚 مدیریت بسته‌های حجمی")],
            [KeyboardButton(text="🌐 مدیریت رکوردها"), KeyboardButton(text="⚙️ تنظیمات ربات")],
            [KeyboardButton(text="تغییر رمز عبور")],
            [KeyboardButton(text="📂 سایر امکانات")],
        ],
        resize_keyboard=False,
    )


def admin_other_features_keyboard():
    keyboard = [
        [KeyboardButton(text="📄 تمدید سرویس"), KeyboardButton(text="🛒 خرید سرویس")],
        [KeyboardButton(text="👤 حساب کاربری"), KeyboardButton(text="📦 سرویس‌های من")],
        [KeyboardButton(text="📦 خرید حجم اضافه"), KeyboardButton(text="💷 تعرفه ها")],
        [KeyboardButton(text="🔁 انتقال مالکیت سرویس")],
        _activation_and_conversion_row(),
    ]
    keyboard.extend(
        [
            [KeyboardButton(text="🎫 پشتیبانی"), KeyboardButton(text="📚 آموزش")],
            [KeyboardButton(text="❓ سوالات متداول"), KeyboardButton(text="📬 انتقادات و پیشنهادات")],
            [KeyboardButton(text="⬅️ بازگشت به منوی اصلی")],
        ]
    )
    return ReplyKeyboardMarkup(keyboard=keyboard, resize_keyboard=True)


def user_main_menu_keyboard():
    keyboard = [
        [KeyboardButton(text="🛒 خرید سرویس"), KeyboardButton(text="📄 تمدید سرویس")],
        [KeyboardButton(text="💳 شارژ حساب"), KeyboardButton(text="📦 خرید حجم اضافه")],
        [KeyboardButton(text="👤 حساب کاربری"), KeyboardButton(text="📦 سرویس‌های من")],
        _activation_and_conversion_row(),
        [KeyboardButton(text="🔁 انتقال مالکیت سرویس"), KeyboardButton(text="🔐 تغییر رمز سرویس")],
    ]
    keyboard.append([KeyboardButton(text="📂 سایر امکانات")])
    return ReplyKeyboardMarkup(
        keyboard=keyboard,
        resize_keyboard=True,
        input_field_placeholder="راه‌اندازی مجدد ربات /start",
    )


def user_other_features_keyboard():
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="💷 تعرفه ها"), KeyboardButton(text="🎫 پشتیبانی")],
            [KeyboardButton(text="📚 آموزش"), KeyboardButton(text="❓ سوالات متداول")],
            [KeyboardButton(text="📬 انتقادات و پیشنهادات")],
            [KeyboardButton(text="⬅️ بازگشت به منوی اصلی")],
        ],
        resize_keyboard=True,
    )
