from aiogram import Router, F
from aiogram.types import Message

from config import ADMINS
from keyboards.admin_main_menu import admin_main_menu_keyboard
from keyboards.user_main_menu import user_main_menu_keyboard
from services.db import add_user
from aiogram.exceptions import TelegramBadRequest
from services.bot_instance import bot
from config import CHANNEL_ID


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
    user_id = message.from_user.id
    first_name = message.from_user.first_name
    username = message.from_user.username
    role = "admin" if user_id in ADMINS else "user"

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
            f"❗️برای تجربه ای بهتر لطفا ابتدا در کانال ما عضو شوید.\n\n"
            f"📢 [عضویت در کانال]({join_link})",
            parse_mode="Markdown",
            disable_web_page_preview=True
        )

