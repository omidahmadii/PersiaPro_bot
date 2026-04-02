from aiogram import Router, F
from aiogram.enums import ChatMemberStatus
from aiogram.exceptions import TelegramBadRequest
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.types import Message, CallbackQuery
from aiogram.types import ReplyKeyboardRemove
from aiogram.types import User
from typing import Optional

from config import ADMINS, CHANNEL_ID
from keyboards.main_menu import user_main_menu_keyboard, admin_main_menu_keyboard
from services.bot_instance import bot
from services.db import add_user, update_last_name
from services.runtime_settings import get_text_setting

router = Router()

# =======================
#  عضویت در کانال
# =======================

VALID_STATUSES = {
    ChatMemberStatus.MEMBER,
    ChatMemberStatus.ADMINISTRATOR,
    ChatMemberStatus.CREATOR,
}

DEFAULT_WELCOME_TEXT = (
    "👋 خوش اومدی!\n\n"
    "به ربات فروش VPN PersiaPro خوش آمدی 🌐\n\n"
    "از منوی زیر می‌تونی:\n"
    "▫️ حساب شارژ کنی\n"
    "▫️ سرویس بخری\n"
    "▫️ فیش ارسال کنی\n"
    "▫️ با پشتیبانی در ارتباط باشی\n\n"
    "👇 یکی از گزینه‌ها رو انتخاب کن:"
)

DEFAULT_START_MEMBERSHIP_TEXT = (
    "🔒 دسترسی محدود\n\n"
    "برای استفاده از ربات PersiaPro، ابتدا باید عضو کانال رسمی ما بشید.\n\n"
    "بعد از عضویت، روی دکمه «عضو شدم» بزنید 👇"
)


async def is_user_member(user_id: int) -> bool:
    try:
        member = await bot.get_chat_member(CHANNEL_ID, user_id)
        return member.status in VALID_STATUSES
    except TelegramBadRequest:
        return False
    except Exception as e:
        print(f"خطا در بررسی عضویت {user_id}: {e}")
        return False


def join_channel_keyboard():
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="📢 عضویت در کانال",
                    url="https://t.me/persiapro"
                )
            ],
            [
                InlineKeyboardButton(
                    text="✅ عضو شدم",
                    callback_data="check_membership"
                )
            ]
        ]
    )


# =======================
#  نمایش منوی اصلی
# =======================

async def show_main_menu(message: Message, actor: Optional[User] = None):
    user = actor or message.from_user
    user_id = user.id

    first_name = user.first_name
    last_name = user.last_name
    username = user.username
    role = "admin" if user_id in ADMINS else "user"

    add_user(user_id, first_name, username, role)

    if last_name:
        update_last_name(user_id=user_id, last_name=last_name)

    keyboard = admin_main_menu_keyboard() if role == "admin" else user_main_menu_keyboard()

    await message.answer(
        get_text_setting("message_welcome_text", DEFAULT_WELCOME_TEXT),
        reply_markup=keyboard,
    )


# =======================
#  /start
# =======================

@router.message(F.text == "/start")
async def cmd_start(message: Message):
    user_id = message.from_user.id

    if not await is_user_member(user_id):
        await message.answer(
            get_text_setting("message_start_membership_required", DEFAULT_START_MEMBERSHIP_TEXT),
            reply_markup=join_channel_keyboard(),
            disable_web_page_preview=True
        )

        # 🔥 این خط خیلی مهمه
        await message.answer(
            "⬆️ لطفا عضو کانال شوید.",
            reply_markup=ReplyKeyboardRemove()
        )
        return

    await show_main_menu(message, actor=message.from_user)


# =======================
#  دکمه «عضو شدم»
# =======================


@router.callback_query(F.data == "check_membership")
async def check_membership_callback(call: CallbackQuery):
    user_id = call.from_user.id

    if await is_user_member(user_id):
        await call.message.edit_text(
            "✅ **عضویت شما تایید شد!**\n\n"
            "در حال ورود به منوی اصلی ⏳",
            parse_mode="Markdown"
        )
        await show_main_menu(call.message, actor=call.from_user)
    else:
        await call.answer(
            "❌ هنوز عضو کانال نشدید",
            show_alert=True
        )
