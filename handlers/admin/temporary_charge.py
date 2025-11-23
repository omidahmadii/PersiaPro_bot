# handlers/admin/temporary_charge.py
import re
from aiogram import Router, F, Bot
from aiogram.types import Message, CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import StatesGroup, State

from config import ADMINS
from keyboards.main_menu import admin_main_menu_keyboard
from services.IBSng import temporary_charge  # ← همون فانکشنی که گفتی

router = Router()


class TempCharge(StatesGroup):
    waiting_for_username = State()


def _normalize_username(raw: str) -> str:
    if not raw:
        return ""
    u = raw.strip()
    if u.startswith("@"):
        u = u[1:]
    # فقط حروف/عدد/._- مجاز
    return re.sub(r"[^A-Za-z0-9._-]", "", u)


@router.message(F.text == "⚡️ شارژ موقت")
async def start_temp_charge(msg: Message, state: FSMContext):
    # فقط ادمین
    if str(msg.from_user.id) not in [str(a) for a in ADMINS]:
        return await msg.reply("⛔️ دسترسی نداری عزیز 😅")

    kb = InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="🔙 انصراف", callback_data="temp_cancel")]
        ]
    )
    await state.set_state(TempCharge.waiting_for_username)
    return await msg.answer(
        "👤 یوزرنیم کاربر را بفرست (مثل: omid یا @omid)\n"
        "یا روی «انصراف» بزن.",
        reply_markup=kb
    )


@router.callback_query(TempCharge.waiting_for_username, F.data == "temp_cancel")
async def temp_cancel_cb(cb: CallbackQuery, state: FSMContext):
    await state.clear()
    await cb.message.answer("عملیات لغو شد.", reply_markup=admin_main_menu_keyboard())
    await cb.answer()


@router.message(TempCharge.waiting_for_username, F.text.casefold() == "انصراف")
async def temp_cancel_msg(msg: Message, state: FSMContext):
    await state.clear()
    await msg.answer("عملیات لغو شد.", reply_markup=admin_main_menu_keyboard())


@router.message(TempCharge.waiting_for_username)
async def receive_username_and_charge(msg: Message, state: FSMContext, bot: Bot):
    username = _normalize_username(msg.text or "")
    if not username:
        await msg.answer("❌ یوزرنیم معتبر نیست.")
        return await state.clear()

    await msg.answer(f"⏳ در حال اعمال شارژ موقت برای «{username}»…")

    try:
        # اجرای عملیات IBS
        temporary_charge(username)
    except Exception as e:
        await state.clear()
        return await msg.answer(
            f"❌ خطا در شارژ موقت برای «{username}»\n"
            f"{type(e).__name__}: {e}",
            reply_markup=admin_main_menu_keyboard()
        )

    await state.clear()
    return await msg.answer(
        f"✅ شارژ موقت انجام شد.\n"
        f"کاربر «{username}» به گروه 1-Hour منتقل شد و زمان/اتریبیوت‌ها ریست و اکانت آزاد شد.",
        reply_markup=admin_main_menu_keyboard()
    )
