import asyncio
import re
from typing import Dict, List, Optional, Tuple

from aiogram import Bot, F, Router
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message

from config import ADMINS
from keyboards.main_menu import admin_main_menu_keyboard
from services.db import (
    get_all_segments,
    get_all_user_ids_for_messaging,
    get_user_ids_by_min_balance,
    get_user_ids_by_segment_ids,
    resolve_user_identifiers,
)

router = Router()


class MessagingStates(StatesGroup):
    waiting_for_single_user = State()
    waiting_for_segment_selection = State()
    waiting_for_min_balance = State()
    waiting_for_message = State()


def is_admin(user_id: int) -> bool:
    return str(user_id) in {str(admin_id) for admin_id in ADMINS}


def normalize_digits(value: str) -> str:
    return str(value or "").translate(str.maketrans("۰۱۲۳۴۵۶۷۸۹", "0123456789"))


def split_tokens(value: str) -> List[str]:
    return [token.strip() for token in re.split(r"[\s,\n،]+", value or "") if token.strip()]


def parse_amount(value: str) -> Optional[int]:
    digits = "".join(ch for ch in normalize_digits(value) if ch.isdigit())
    if not digits:
        return None
    return int(digits)


def format_price(value: int) -> str:
    try:
        return f"{int(value):,}"
    except Exception:
        return str(value)


def messaging_home_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="👥 پیام به همه کاربران", callback_data="msg|all")],
            [InlineKeyboardButton(text="👤 پیام به کاربر خاص", callback_data="msg|single")],
            [InlineKeyboardButton(text="🧩 پیام به سگمنت/گروه", callback_data="msg|segment")],
            [InlineKeyboardButton(text="💰 پیام به کاربران با حداقل موجودی", callback_data="msg|min_balance")],
            [InlineKeyboardButton(text="🔙 منوی اصلی", callback_data="msg|main_menu")],
        ]
    )


def cancel_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="❌ لغو", callback_data="msg|cancel")],
        ]
    )


def resolve_segment_identifiers(tokens: List[str]) -> Tuple[List[Dict], List[str]]:
    segments = get_all_segments()
    by_id = {str(segment["id"]): segment for segment in segments}
    by_slug = {str(segment["slug"]).lower(): segment for segment in segments}

    resolved = []
    missing = []
    seen_ids = set()
    for token in tokens:
        key = token.strip()
        if not key:
            continue
        segment = by_id.get(key) or by_slug.get(key.lower())
        if not segment:
            missing.append(key)
            continue
        segment_id = int(segment["id"])
        if segment_id in seen_ids:
            continue
        seen_ids.add(segment_id)
        resolved.append(segment)
    return resolved, missing


async def show_messaging_home(target: Message, state: FSMContext) -> None:
    await state.clear()
    await target.answer(
        "📢 ارسال پیام هدفمند\n\n"
        "نوع گیرنده را انتخاب کن:",
        reply_markup=messaging_home_keyboard(),
    )


async def begin_message_input(message: Message, state: FSMContext, title: str, user_ids: List[int]) -> None:
    await state.set_state(MessagingStates.waiting_for_message)
    await state.update_data(recipient_title=title, recipient_user_ids=user_ids)
    await message.answer(
        f"گیرنده: {title}\n"
        f"تعداد گیرنده: {len(user_ids)}\n\n"
        "متن پیام را ارسال کن.\n"
        "برای لغو، «لغو» را بفرست.",
        reply_markup=cancel_keyboard(),
    )


@router.message(F.text == "📢 ارسال پیام")
async def messaging_entry(message: Message, state: FSMContext):
    if not is_admin(message.from_user.id):
        return
    await show_messaging_home(message, state)


@router.callback_query(F.data == "msg|main_menu")
async def messaging_main_menu(callback: CallbackQuery, state: FSMContext):
    if not is_admin(callback.from_user.id):
        return await callback.answer("دسترسی نداری.", show_alert=True)
    await state.clear()
    await callback.message.answer("بازگشت به منوی اصلی.", reply_markup=admin_main_menu_keyboard())
    await callback.answer()


@router.callback_query(F.data == "msg|cancel")
async def messaging_cancel(callback: CallbackQuery, state: FSMContext):
    if not is_admin(callback.from_user.id):
        return await callback.answer("دسترسی نداری.", show_alert=True)
    await state.clear()
    await callback.message.answer("ارسال پیام لغو شد.", reply_markup=messaging_home_keyboard())
    await callback.answer("لغو شد.")


@router.callback_query(F.data == "msg|all")
async def messaging_select_all(callback: CallbackQuery, state: FSMContext):
    if not is_admin(callback.from_user.id):
        return await callback.answer("دسترسی نداری.", show_alert=True)

    user_ids = get_all_user_ids_for_messaging()
    if not user_ids:
        await callback.message.answer("هیچ کاربری برای ارسال پیام پیدا نشد.", reply_markup=messaging_home_keyboard())
        return await callback.answer()

    await begin_message_input(callback.message, state, "همه کاربران", user_ids)
    await callback.answer()


@router.callback_query(F.data == "msg|single")
async def messaging_select_single(callback: CallbackQuery, state: FSMContext):
    if not is_admin(callback.from_user.id):
        return await callback.answer("دسترسی نداری.", show_alert=True)

    await state.clear()
    await state.set_state(MessagingStates.waiting_for_single_user)
    await callback.message.answer(
        "شناسه عددی کاربر یا یوزرنیم (با @ یا بدون @) را بفرست.\n"
        "مثال: <code>123456789</code> یا <code>@username</code>",
        parse_mode="HTML",
        reply_markup=cancel_keyboard(),
    )
    await callback.answer()


@router.callback_query(F.data == "msg|segment")
async def messaging_select_segment(callback: CallbackQuery, state: FSMContext):
    if not is_admin(callback.from_user.id):
        return await callback.answer("دسترسی نداری.", show_alert=True)

    segments = get_all_segments()
    if not segments:
        await callback.message.answer("هیچ سگمنتی ثبت نشده است.", reply_markup=messaging_home_keyboard())
        return await callback.answer()

    lines = ["سگمنت‌های موجود:", ""]
    for segment in segments[:25]:
        lines.append(
            f"• #{segment['id']} | {segment['title']} | slug={segment['slug']} | users={segment.get('user_count') or 0}"
        )
    lines.append("")
    lines.append("شناسه یا slug سگمنت‌ها را با فاصله یا کاما بفرست.")

    await state.clear()
    await state.set_state(MessagingStates.waiting_for_segment_selection)
    await callback.message.answer("\n".join(lines), reply_markup=cancel_keyboard())
    await callback.answer()


@router.callback_query(F.data == "msg|min_balance")
async def messaging_select_min_balance(callback: CallbackQuery, state: FSMContext):
    if not is_admin(callback.from_user.id):
        return await callback.answer("دسترسی نداری.", show_alert=True)

    await state.clear()
    await state.set_state(MessagingStates.waiting_for_min_balance)
    await callback.message.answer(
        "حداقل موجودی را به تومان بفرست.\n"
        "مثال: <code>300000</code>",
        parse_mode="HTML",
        reply_markup=cancel_keyboard(),
    )
    await callback.answer()


@router.message(MessagingStates.waiting_for_single_user)
async def messaging_receive_single_user(message: Message, state: FSMContext):
    if not is_admin(message.from_user.id):
        await state.clear()
        return

    token = (message.text or "").strip()
    users, missing = resolve_user_identifiers([token], include_offline=False)
    if not users:
        await message.answer(
            f"کاربر پیدا نشد: {token or '-'}\n"
            "دوباره شناسه یا یوزرنیم معتبر بفرست.",
            reply_markup=cancel_keyboard(),
        )
        return

    user = users[0]
    user_id = int(user["id"])
    username = user.get("username") or "-"
    await begin_message_input(
        message,
        state,
        f"کاربر #{user_id} (@{username})",
        [user_id],
    )


@router.message(MessagingStates.waiting_for_segment_selection)
async def messaging_receive_segments(message: Message, state: FSMContext):
    if not is_admin(message.from_user.id):
        await state.clear()
        return

    tokens = split_tokens(message.text or "")
    if not tokens:
        await message.answer("حداقل یک شناسه یا slug سگمنت بفرست.", reply_markup=cancel_keyboard())
        return

    segments, missing = resolve_segment_identifiers(tokens)
    if not segments:
        await message.answer(
            "هیچ سگمنت معتبری پیدا نشد.\n"
            f"موارد نامعتبر: {', '.join(missing[:10]) if missing else '-'}",
            reply_markup=cancel_keyboard(),
        )
        return

    segment_ids = [int(segment["id"]) for segment in segments]
    user_ids = get_user_ids_by_segment_ids(segment_ids, only_active_segments=True)
    if not user_ids:
        await message.answer("در سگمنت(های) انتخابی کاربری برای ارسال پیام پیدا نشد.", reply_markup=messaging_home_keyboard())
        await state.clear()
        return

    segment_titles = [str(segment["title"]) for segment in segments]
    title = "سگمنت: " + ", ".join(segment_titles[:3])
    if len(segment_titles) > 3:
        title += f" و {len(segment_titles) - 3} مورد دیگر"
    await begin_message_input(message, state, title, user_ids)


@router.message(MessagingStates.waiting_for_min_balance)
async def messaging_receive_min_balance(message: Message, state: FSMContext):
    if not is_admin(message.from_user.id):
        await state.clear()
        return

    amount = parse_amount(message.text or "")
    if amount is None:
        await message.answer("حداقل موجودی معتبر بفرست. مثال: 300000", reply_markup=cancel_keyboard())
        return

    user_ids = get_user_ids_by_min_balance(amount)
    if not user_ids:
        await message.answer(
            f"کاربری با موجودی بالاتر یا مساوی {format_price(amount)} تومان پیدا نشد.",
            reply_markup=messaging_home_keyboard(),
        )
        await state.clear()
        return

    await begin_message_input(
        message,
        state,
        f"کاربران با موجودی >= {format_price(amount)} تومان",
        user_ids,
    )


@router.message(MessagingStates.waiting_for_message)
async def messaging_send(message: Message, state: FSMContext, bot: Bot):
    if not is_admin(message.from_user.id):
        await state.clear()
        return

    text = (message.text or "").strip()
    if not text:
        await message.answer("متن پیام خالی است. پیام را بفرست یا لغو کن.", reply_markup=cancel_keyboard())
        return

    if text in {"لغو", "/cancel", "cancel"}:
        await state.clear()
        await message.answer("ارسال پیام لغو شد.", reply_markup=messaging_home_keyboard())
        return

    data = await state.get_data()
    user_ids = [int(uid) for uid in (data.get("recipient_user_ids") or [])]
    recipient_title = str(data.get("recipient_title") or "نامشخص")
    if not user_ids:
        await state.clear()
        await message.answer("لیست گیرنده‌ها پیدا نشد. دوباره از منوی ارسال پیام شروع کن.", reply_markup=messaging_home_keyboard())
        return

    await message.answer(
        f"ارسال شروع شد...\n"
        f"گیرنده: {recipient_title}\n"
        f"تعداد: {len(user_ids)}"
    )

    success = 0
    failed = 0
    failed_ids: List[int] = []

    for user_id in user_ids:
        try:
            await bot.send_message(user_id, text)
            success += 1
        except Exception:
            failed += 1
            if len(failed_ids) < 20:
                failed_ids.append(user_id)
        await asyncio.sleep(0.02)

    await state.clear()
    failed_preview = ", ".join(str(uid) for uid in failed_ids) if failed_ids else "-"
    await message.answer(
        "✅ ارسال پیام تمام شد.\n"
        f"گیرنده: {recipient_title}\n"
        f"موفق: {success}\n"
        f"ناموفق: {failed}\n"
        f"نمونه آیدی ناموفق: {failed_preview}",
        reply_markup=messaging_home_keyboard(),
    )
