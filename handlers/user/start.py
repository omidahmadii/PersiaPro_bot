from aiogram import Router, F
from aiogram.types import Message
from aiogram.exceptions import TelegramBadRequest

from config import ADMINS, CHANNEL_ID
from keyboards.admin_main_menu import admin_main_menu_keyboard
from keyboards.user_main_menu import user_main_menu_keyboard
from services.db import add_user
from services.bot_instance import bot

router = Router()


async def is_user_member(user_id: int) -> bool:
    try:
        member = await bot.get_chat_member(CHANNEL_ID, user_id)
        return member.status in ['member', 'administrator', 'creator']
    except TelegramBadRequest:
        return False
    except Exception as e:
        print(f"عضویت چک نشد: {e}")
        return False


@router.message(F.text == "/start")
async def cmd_start(message: Message):
    user = message.from_user
    user_id = user.id
    first_name = user.first_name
    username = user.username
    role = "admin" if user_id in ADMINS else "user"

    # --- بخش پرینت اطلاعات کاربر (ایمن و بدون خطا) --------------------------
    # نکته: bio از get_chat می‌آید؛ تاریخ تولد/شماره‌تلفن در تلگرام موجود نیست
    # مگر کاربر contact بدهد. اگر قبلاً ذخیره کرده‌اید، از دیتابیس بخوانید.
    try:
        chat = await bot.get_chat(user_id)  # برای دریافت bio در چت خصوصی
        bio = getattr(chat, "bio", None)
    except Exception as e:
        bio = None
        print(f"خطا در دریافت bio: {e}")

    user_info_to_print = {
        "id": user_id,
        "first_name": user.first_name,
        "last_name": getattr(user, "last_name", None),
        "username": username,
        "language_code": getattr(user, "language_code", None),
        "is_premium": getattr(user, "is_premium", None),
        "bio": bio,
        # تاریخ تولد در Bot API وجود ندارد؛ در آینده اگر از کاربر بگیرید اینجا اضافه کنید
        "birth_date": None,
        # شماره‌تلفن هم فقط وقتی هست که کاربر contact بدهد:
        "phone_number": None,
    }

    print("🔎 User info on /start:", user_info_to_print)
    # ----------------------------------------------------------------------

    # ذخیره کاربر در دیتابیس
    add_user(user_id, first_name, username, role)

    # انتخاب منو بر اساس نقش
    keyboard = admin_main_menu_keyboard() if role == "admin" else user_main_menu_keyboard()

    # ارسال پیام خوش‌آمدگویی و منوی اصلی
    await message.answer(
        "🌐 به ربات فروش VPN خوش آمدید!\n\n"
        "✅ آموزش استفاده از ربات:\n\n"
        "1️⃣ *شارژ حساب*\n"
        "گزینه «شارژ حساب» رو بزن، مبلغ رو واریز کن.\n\n"
        "2️⃣ *ارسال فیش*\n"
        "عکس رسید رو تو ربات بفرست و منتظر تایید باش.\n\n"
        "3️⃣ *خرید سرویس*\n"
        "بعد از تایید، «خرید سرویس» رو بزن، پلن رو انتخاب کن.\n"
        "یوزرنیم و پسورد برات ارسال میشه.\n\n"
        "4️⃣ *اتصال*\n"
        "با اطلاعات داده‌شده توی بخش آموزش وصل شو.\n\n"
        "5️⃣ *پشتیبانی*\n"
        "هرجا مشکل داشتی می‌تونی با پشتیبانی ارتباط بگیری.\n\n"
        "👇 حالا یکی از گزینه‌های زیر رو انتخاب کن:",
        reply_markup=keyboard,
        parse_mode="Markdown"
    )

    # بررسی عضویت در کانال
    if not await is_user_member(user_id):
        join_link = "https://t.me/persiapro"  # لینک جوین به کانال
        await message.answer(
            f"❗️برای تجربه‌ای بهتر لطفا ابتدا در کانال ما عضو شوید.\n\n"
            f"📢 [عضویت در کانال]({join_link})",
            parse_mode="Markdown",
            disable_web_page_preview=True
        )
