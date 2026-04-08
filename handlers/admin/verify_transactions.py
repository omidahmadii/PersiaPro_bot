from typing import Optional

from aiogram import F, Router, Bot
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message

from config import ADMINS
from keyboards.main_menu import admin_main_menu_keyboard
from services.db import get_user_balance
from services.payment_workflow import (
    STATUS_LEGACY_PENDING,
    STATUS_PENDING_ADMIN,
    approve_transaction_initial,
    get_duplicate_candidates,
    get_transaction_status_label,
    get_transaction_with_user,
    list_transactions_by_status,
    reject_transaction_initial,
)

router = Router()

MIN_TOPUP = 1_000
MAX_TOPUP = 50_000_000
INITIAL_REVIEW_STATUSES = {STATUS_PENDING_ADMIN, STATUS_LEGACY_PENDING}


class VerifyTxn(StatesGroup):
    waiting_for_amount = State()
    waiting_for_reject_reason = State()


def is_admin(user_id: int) -> bool:
    return str(user_id) in {str(admin_id) for admin_id in ADMINS}


def format_price(amount: int) -> str:
    try:
        return f"{int(amount):,}"
    except Exception:
        return str(amount)


def parse_amount(text: str) -> Optional[int]:
    digits = "".join(ch for ch in (text or "") if ch.isdigit())
    if not digits:
        return None
    amount = int(digits)
    if amount < MIN_TOPUP or amount > MAX_TOPUP:
        return None
    return amount


def mask_card(card_number: Optional[str]) -> str:
    digits = "".join(ch for ch in str(card_number or "") if ch.isdigit())
    if len(digits) < 8:
        return digits or "نامشخص"
    return "-".join(digits[i:i + 4] for i in range(0, len(digits), 4))


def duplicate_reason_label(reason: str) -> str:
    mapping = {
        "same_photo": "عکس مشابه",
        "same_amount_card_datetime": "مبلغ/کارت/تاریخ‌وساعت مشابه",
        "same_amount_date_source_last4": "مبلغ/تاریخ/۴ رقم کارت مبدا مشابه",
    }
    return mapping.get(reason, reason)


def pending_transactions_keyboard(transactions: list[dict]) -> InlineKeyboardMarkup:
    rows = []
    for txn in transactions:
        duplicate_mark = " ⚠️" if int(txn.get("is_duplicate_suspect") or 0) == 1 else ""
        amount_text = format_price(txn.get("amount_claimed") or 0)
        user_label = str(txn.get("username") or txn.get("first_name") or txn["user_id"])
        button_text = f"#{txn['id']} | {amount_text} | {user_label}{duplicate_mark}"
        rows.append(
            [InlineKeyboardButton(text=button_text[:64], callback_data=f"verify|open|{txn['id']}")]
        )
    rows.append([InlineKeyboardButton(text="🔙 منوی اصلی", callback_data="verify|main_menu")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def review_keyboard(txn_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="✅ تایید با مبلغ اعلامی", callback_data=f"verify|approve_claimed|{txn_id}")],
            [InlineKeyboardButton(text="✏️ تایید با مبلغ دیگر", callback_data=f"verify|approve_other|{txn_id}")],
            [InlineKeyboardButton(text="❌ رد تراکنش", callback_data=f"verify|reject|{txn_id}")],
            [InlineKeyboardButton(text="🔙 لیست پرداخت‌ها", callback_data="verify|list")],
        ]
    )


def build_duplicate_lines(txn_id: int) -> str:
    candidates = get_duplicate_candidates(txn_id, limit=5)
    if not candidates:
        return "مورد مشابهی پیدا نشد."

    lines = []
    for item in candidates:
        reasons = "، ".join(duplicate_reason_label(reason) for reason in (item.get("reasons") or [])) or "-"
        lines.append(
            f"• #{item['id']} | user={item['user_id']} | {get_transaction_status_label(item.get('status'))} | "
            f"{format_price(item.get('amount') or item.get('amount_claimed') or 0)} تومان | {reasons}"
        )
    return "\n".join(lines)


def build_review_caption(txn: dict) -> str:
    name = " ".join(part for part in [txn.get("first_name") or "", txn.get("last_name") or ""] if part).strip() or "-"
    duplicate_header = "بله" if int(txn.get("is_duplicate_suspect") or 0) == 1 else "خیر"
    return (
        f"🧾 <b>بررسی تراکنش #{txn['id']}</b>\n\n"
        f"👤 کاربر: <a href='tg://user?id={txn['user_id']}'>{txn['user_id']} {name}</a>\n"
        f"🔰 یوزرنیم: <b>@{txn.get('username') or '-'}</b>\n"
        f"💰 مبلغ اعلامی: <b>{format_price(txn.get('amount_claimed') or 0)} تومان</b>\n"
        f"🏦 کارت مقصد: <b>{mask_card(txn.get('destination_card_number'))}</b>\n"
        f"🏷 بانک/عنوان: <b>{txn.get('destination_bank_name') or 'کارت خارج از لیست'}</b>\n"
        f"📅 زمان واریز: <b>{txn.get('transfer_date') or '-'} {txn.get('transfer_time') or '-'}</b>\n"
        f"💳 ۴ رقم آخر کارت مبدا: <b>{txn.get('source_card_last4') or 'ندارد'}</b>\n"
        f"⚠️ مشکوک به تکرار: <b>{duplicate_header}</b>\n\n"
        f"<b>موارد مشابه:</b>\n{build_duplicate_lines(int(txn['id']))}"
    )


async def show_pending_transactions(message: Message, state: FSMContext) -> None:
    await state.clear()
    txns = list_transactions_by_status(STATUS_PENDING_ADMIN)
    if not txns:
        await message.answer("تراکنشی در انتظار بررسی اولیه وجود ندارد.")
        return
    await message.answer(
        "تراکنش‌های در انتظار بررسی اولیه را انتخاب کنید:",
        reply_markup=pending_transactions_keyboard(txns),
    )


async def show_transaction_review(message: Message, txn_id: int) -> None:
    txn = get_transaction_with_user(txn_id)
    if not txn or txn.get("status") not in INITIAL_REVIEW_STATUSES:
        await message.answer("این تراکنش قبلاً بررسی شده یا دیگر در صف اولیه نیست.")
        return

    await message.answer_photo(
        txn["photo_id"],
        caption=build_review_caption(txn),
        parse_mode="HTML",
        reply_markup=review_keyboard(txn_id),
    )


@router.message(F.text == "💳 تایید پرداخت ها")
async def start_verification(message: Message, state: FSMContext):
    if not is_admin(message.from_user.id):
        return await message.reply("دسترسی نداری.")
    await show_pending_transactions(message, state)


@router.callback_query(F.data == "verify|list")
async def list_pending_callback(callback: CallbackQuery, state: FSMContext):
    if not is_admin(callback.from_user.id):
        return await callback.answer("دسترسی نداری.", show_alert=True)
    await show_pending_transactions(callback.message, state)
    await callback.answer()


@router.callback_query(F.data == "verify|main_menu")
async def verify_main_menu(callback: CallbackQuery, state: FSMContext):
    if not is_admin(callback.from_user.id):
        return await callback.answer("دسترسی نداری.", show_alert=True)
    await state.clear()
    await callback.message.answer("بازگشت به منوی اصلی.", reply_markup=admin_main_menu_keyboard())
    await callback.answer()


@router.callback_query(F.data.startswith("verify|open|"))
async def open_transaction(callback: CallbackQuery, state: FSMContext):
    if not is_admin(callback.from_user.id):
        return await callback.answer("دسترسی نداری.", show_alert=True)
    txn_id = int(callback.data.split("|")[2])
    await state.clear()
    await show_transaction_review(callback.message, txn_id)
    await callback.answer()


@router.callback_query(F.data.startswith("verify|approve_claimed|"))
async def approve_with_claimed_amount(callback: CallbackQuery, state: FSMContext, bot: Bot):
    if not is_admin(callback.from_user.id):
        return await callback.answer("دسترسی نداری.", show_alert=True)
    txn_id = int(callback.data.split("|")[2])
    txn = get_transaction_with_user(txn_id)
    if not txn or txn.get("status") not in INITIAL_REVIEW_STATUSES:
        return await callback.answer("این تراکنش دیگر در صف بررسی نیست.", show_alert=True)

    approved = approve_transaction_initial(
        txn_id=txn_id,
        reviewer_id=callback.from_user.id,
        amount=int(txn.get("amount_claimed") or 0),
    )
    if not approved:
        return await callback.answer("تایید انجام نشد.", show_alert=True)

    user_balance = get_user_balance(int(approved["user_id"]))
    await callback.message.answer(
        f"✅ تراکنش #{txn_id} تایید شد و موجودی کاربر شارژ شد.\n"
        f"💰 مبلغ: {format_price(approved.get('amount') or 0)} تومان\n"
        f"💳 موجودی فعلی کاربر: {format_price(user_balance)} تومان\n"
        "🏦 این تراکنش حالا در صف تایید حسابداری قرار گرفت."
    )
    await bot.send_message(
        int(approved["user_id"]),
        f"✅ فیش شما تایید شد و {format_price(approved.get('amount') or 0)} تومان به کیف پول شما اضافه شد.\n"
        f"💳 موجودی فعلی: {format_price(user_balance)} تومان",
    )
    await state.clear()
    await callback.answer("تایید شد.")


@router.callback_query(F.data.startswith("verify|approve_other|"))
async def approve_with_other_amount(callback: CallbackQuery, state: FSMContext):
    if not is_admin(callback.from_user.id):
        return await callback.answer("دسترسی نداری.", show_alert=True)
    txn_id = int(callback.data.split("|")[2])
    txn = get_transaction_with_user(txn_id)
    if not txn or txn.get("status") not in INITIAL_REVIEW_STATUSES:
        return await callback.answer("این تراکنش دیگر در صف بررسی نیست.", show_alert=True)

    await state.clear()
    await state.update_data(txn_id=txn_id)
    await state.set_state(VerifyTxn.waiting_for_amount)
    await callback.message.answer(
        f"مبلغ نهایی تراکنش #{txn_id} را وارد کن.\n"
        f"مبلغ اعلامی کاربر: {format_price(txn.get('amount_claimed') or 0)} تومان"
    )
    await callback.answer()


@router.message(VerifyTxn.waiting_for_amount)
async def receive_custom_amount(message: Message, state: FSMContext, bot: Bot):
    if not is_admin(message.from_user.id):
        await state.clear()
        return

    amount = parse_amount(message.text or "")
    if amount is None:
        await message.answer(
            f"❌ لطفاً مبلغی بین {format_price(MIN_TOPUP)} تا {format_price(MAX_TOPUP)} تومان وارد کنید."
        )
        return

    data = await state.get_data()
    txn_id = data.get("txn_id")
    if not txn_id:
        await state.clear()
        await message.answer("❌ تراکنش انتخاب‌شده پیدا نشد.")
        return

    approved = approve_transaction_initial(
        txn_id=int(txn_id),
        reviewer_id=message.from_user.id,
        amount=amount,
        note="مبلغ با اصلاح ادمین تایید شد.",
    )
    if not approved:
        await state.clear()
        await message.answer("❌ این تراکنش دیگر در صف بررسی اولیه نیست.")
        return

    user_balance = get_user_balance(int(approved["user_id"]))
    await message.answer(
        f"✅ تراکنش #{txn_id} با مبلغ اصلاح‌شده تایید شد.\n"
        f"💰 مبلغ نهایی: {format_price(approved.get('amount') or 0)} تومان\n"
        f"💳 موجودی فعلی کاربر: {format_price(user_balance)} تومان\n"
        "🏦 این تراکنش حالا در صف تایید حسابداری قرار گرفت."
    )
    await bot.send_message(
        int(approved["user_id"]),
        f"✅ فیش شما تایید شد و {format_price(approved.get('amount') or 0)} تومان به کیف پول شما اضافه شد.\n"
        f"💳 موجودی فعلی: {format_price(user_balance)} تومان",
    )
    await state.clear()


@router.callback_query(F.data.startswith("verify|reject|"))
async def reject_transaction(callback: CallbackQuery, state: FSMContext):
    if not is_admin(callback.from_user.id):
        return await callback.answer("دسترسی نداری.", show_alert=True)
    txn_id = int(callback.data.split("|")[2])
    txn = get_transaction_with_user(txn_id)
    if not txn or txn.get("status") not in INITIAL_REVIEW_STATUSES:
        return await callback.answer("این تراکنش دیگر در صف بررسی نیست.", show_alert=True)

    await state.clear()
    await state.update_data(txn_id=txn_id)
    await state.set_state(VerifyTxn.waiting_for_reject_reason)
    await callback.message.answer(f"دلیل رد تراکنش #{txn_id} را وارد کن:")
    await callback.answer()


@router.message(VerifyTxn.waiting_for_reject_reason)
async def receive_reject_reason(message: Message, state: FSMContext, bot: Bot):
    if not is_admin(message.from_user.id):
        await state.clear()
        return

    data = await state.get_data()
    txn_id = data.get("txn_id")
    reason = (message.text or "").strip()
    if not txn_id or not reason:
        await message.answer("❌ دلیل رد را وارد کن.")
        return

    rejected = reject_transaction_initial(int(txn_id), message.from_user.id, reason)
    if not rejected:
        await state.clear()
        await message.answer("❌ این تراکنش دیگر در صف بررسی اولیه نیست.")
        return

    await message.answer(f"تراکنش #{txn_id} رد شد.")
    await bot.send_message(
        int(rejected["user_id"]),
        f"❌ فیش شما رد شد.\nدلیل: {reason}\n"
        "اگر نیاز به ثبت مجدد دارید می‌توانید دوباره فیش را همراه با اطلاعات کامل ارسال کنید.",
    )
    await state.clear()
