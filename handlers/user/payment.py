import hashlib
from pathlib import Path
from typing import Optional

import jdatetime
from aiogram import Bot, F, Router
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message

from config import ADMINS
from keyboards.main_menu import main_menu_keyboard_for_user
from services.db import add_user, ensure_user_exists, update_last_name
from services.payment_workflow import (
    STATUS_DRAFT,
    create_transaction_draft,
    get_active_bank_cards,
    get_duplicate_candidates,
    get_transaction,
    normalize_card_number,
    normalize_digits,
    normalize_last4,
    set_claimed_amount,
    set_destination_card_from_card_id,
    set_destination_card_manual,
    set_source_card_last4,
    set_transfer_date,
    set_transfer_time,
    submit_transaction_for_review,
)

router = Router()

MIN_TOPUP = 1_000
MAX_TOPUP = 50_000_000
COMMON_AMOUNTS = [
    200_000,
    400_000,
    500_000,
    600_000,
    1_000_000,
    1_500_000,
]


class PaymentStates(StatesGroup):
    waiting_for_receipt = State()
    choosing_amount = State()
    typing_amount = State()
    choosing_destination_card = State()
    typing_destination_card = State()
    choosing_transfer_date = State()
    typing_transfer_date = State()
    typing_transfer_time = State()
    typing_source_card_last4 = State()
    confirming = State()


def calculate_photo_hash(file_path: str) -> str:
    with open(file_path, "rb") as f:
        return hashlib.sha256(f.read()).hexdigest()


def _get_receipt_file_info(message: Message) -> tuple[Optional[str], str]:
    if message.photo:
        return message.photo[-1].file_id, ".jpg"

    return None, ".jpg"


def format_price(amount: int) -> str:
    try:
        return f"{int(amount):,}"
    except Exception:
        return str(amount)


def mask_card_number(card_number: Optional[str]) -> str:
    digits = normalize_card_number(card_number)
    if len(digits) < 8:
        return digits or "نامشخص"
    groups = [digits[i:i + 4] for i in range(0, len(digits), 4)]
    return "-".join(groups)


def optional_keyboard(skip_text: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text=skip_text, callback_data="pay|skip")],
            [InlineKeyboardButton(text="❌ انصراف", callback_data="pay|cancel")],
        ]
    )


def cancel_only_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="❌ انصراف", callback_data="pay|cancel")],
        ]
    )


def amount_keyboard() -> InlineKeyboardMarkup:
    rows = []
    for index in range(0, len(COMMON_AMOUNTS), 2):
        chunk = COMMON_AMOUNTS[index:index + 2]
        rows.append(
            [
                InlineKeyboardButton(
                    text=f"{format_price(amount)} تومان",
                    callback_data=f"pay|amount|{amount}",
                )
                for amount in chunk
            ]
        )
    rows.append([InlineKeyboardButton(text="✏️ مبلغ دیگر", callback_data="pay|amount|other")])
    rows.append([InlineKeyboardButton(text="❌ انصراف", callback_data="pay|cancel")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def destination_card_keyboard() -> InlineKeyboardMarkup:
    rows = []
    for card in get_active_bank_cards():
        label = f"{mask_card_number(card['card_number'])} | {card.get('bank_name') or '-'}"
        rows.append(
            [
                InlineKeyboardButton(
                    text=label[:64],
                    callback_data=f"pay|dest_card|{card['id']}",
                )
            ]
        )
    rows.append([InlineKeyboardButton(text="✏️ کارت در لیست نیست", callback_data="pay|dest_card|manual")])
    rows.append([InlineKeyboardButton(text="❌ انصراف", callback_data="pay|cancel")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def transfer_date_keyboard() -> InlineKeyboardMarkup:
    today = jdatetime.datetime.now()
    yesterday = today - jdatetime.timedelta(days=1)
    two_days_ago = today - jdatetime.timedelta(days=2)
    choices = [
        ("today", f"امروز ({today.strftime('%Y/%m/%d')})"),
        ("yesterday", f"دیروز ({yesterday.strftime('%Y/%m/%d')})"),
        ("two_days_ago", f"۲ روز قبل ({two_days_ago.strftime('%Y/%m/%d')})"),
        ("manual", "✏️ ورود دستی تاریخ"),
    ]
    rows = [[InlineKeyboardButton(text=label, callback_data=f"pay|date|{key}")] for key, label in choices]
    rows.append([InlineKeyboardButton(text="❌ انصراف", callback_data="pay|cancel")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def confirmation_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="✅ ثبت نهایی", callback_data="pay|confirm")],
            [InlineKeyboardButton(text="❌ انصراف", callback_data="pay|cancel")],
        ]
    )


def review_notification_keyboard(txn_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text=f"🔎 بررسی تراکنش #{txn_id}", callback_data=f"verify|open|{txn_id}")],
        ]
    )


def parse_amount(text: str) -> Optional[int]:
    digits = "".join(ch for ch in normalize_digits(text) if ch.isdigit())
    if not digits:
        return None
    amount = int(digits)
    if amount < MIN_TOPUP or amount > MAX_TOPUP:
        return None
    return amount


def parse_manual_date(text: str) -> Optional[str]:
    cleaned = normalize_digits(text).strip().replace("-", "/")
    parts = [part for part in cleaned.split("/") if part]
    if len(parts) != 3:
        return None
    try:
        year, month, day = [int(part) for part in parts]
        jdatetime.date(year, month, day)
    except Exception:
        return None
    return f"{year:04d}/{month:02d}/{day:02d}"


def parse_time_value(text: str) -> Optional[str]:
    cleaned = normalize_digits(text).strip().replace(".", ":")
    parts = cleaned.split(":")
    if len(parts) != 2:
        return None
    try:
        hour = int(parts[0])
        minute = int(parts[1])
    except Exception:
        return None
    if not (0 <= hour <= 23 and 0 <= minute <= 59):
        return None
    return f"{hour:02d}:{minute:02d}"


def _selected_relative_date(choice: str) -> Optional[str]:
    now = jdatetime.datetime.now()
    if choice == "today":
        return now.strftime("%Y/%m/%d")
    if choice == "yesterday":
        return (now - jdatetime.timedelta(days=1)).strftime("%Y/%m/%d")
    if choice == "two_days_ago":
        return (now - jdatetime.timedelta(days=2)).strftime("%Y/%m/%d")
    return None


def _format_duplicate_flags(flags: Optional[str]) -> str:
    mapping = {
        "same_photo": "عکس مشابه",
        "same_amount_card_datetime": "مبلغ/کارت/تاریخ‌وساعت مشابه",
        "same_amount_date_source_last4": "مبلغ/تاریخ/۴ رقم کارت مبدا مشابه",
    }
    items = []
    for raw in (flags or "").split(","):
        key = raw.strip()
        if not key:
            continue
        items.append(mapping.get(key, key))
    return "، ".join(items)


def build_cards_text() -> str:
    active_cards = get_active_bank_cards()
    if not active_cards:
        return "در حال حاضر هیچ کارت فعالی برای شارژ حساب ثبت نشده است."

    lines = ["💳 برای شارژ حساب، مبلغ را به یکی از کارت‌های زیر واریز کنید:", ""]
    for card in active_cards:
        lines.append(f"🏦 {card.get('bank_name') or '-'} به نام {card.get('owner_name') or '-'}")
        lines.append(f"<code>{mask_card_number(card.get('card_number'))}</code>")
        lines.append("")
    lines.append("📸 بعد از واریز، عکس فیش را بفرست تا ثبت اطلاعات را شروع کنیم.")
    return "\n".join(lines)


def build_payment_summary(txn: dict) -> str:
    destination_card = mask_card_number(txn.get("destination_card_number"))
    destination_bank = txn.get("destination_bank_name") or "کارت خارج از لیست"
    source_last4 = txn.get("source_card_last4") or "وارد نشده"
    return (
        "🧾 <b>خلاصه ثبت فیش</b>\n\n"
        f"💰 مبلغ: <b>{format_price(txn.get('amount_claimed') or 0)} تومان</b>\n"
        f"🏦 کارت مقصد: <b>{destination_card}</b>\n"
        f"🏷 بانک/عنوان کارت: <b>{destination_bank}</b>\n"
        f"📅 تاریخ واریز: <b>{txn.get('transfer_date') or '-'}</b>\n"
        f"🕒 ساعت واریز: <b>{txn.get('transfer_time') or '-'}</b>\n"
        f"💳 ۴ رقم آخر کارت مبدا: <b>{source_last4}</b>"
    )


def build_admin_submission_caption(txn: dict) -> str:
    name_parts = [txn.get("first_name") or "", txn.get("last_name") or ""]
    full_name = " ".join(part for part in name_parts if part).strip() or "-"
    destination_card = mask_card_number(txn.get("destination_card_number"))
    destination_bank = txn.get("destination_bank_name") or "کارت خارج از لیست"
    duplicate_note = ""
    if int(txn.get("is_duplicate_suspect") or 0) == 1:
        duplicate_note = f"\n⚠️ مشکوک به تکرار: {_format_duplicate_flags(txn.get('duplicate_flags'))}"
    return (
        f"📥 تراکنش جدید #{txn['id']}\n"
        f"👤 کاربر: <a href='tg://user?id={txn['user_id']}'>{txn['user_id']} {full_name}</a>\n"
        f"💰 مبلغ اعلامی: {format_price(txn.get('amount_claimed') or 0)} تومان\n"
        f"🏦 کارت مقصد: {destination_card} | {destination_bank}\n"
        f"📅 زمان واریز: {txn.get('transfer_date') or '-'} {txn.get('transfer_time') or '-'}\n"
        f"💳 ۴ رقم آخر کارت مبدا: {txn.get('source_card_last4') or 'ندارد'}\n"
        f"{duplicate_note}"
    )


async def register_receipt_upload(message: Message, state: FSMContext, bot: Bot) -> bool:
    ensure_user_record(message)

    active_cards = get_active_bank_cards()
    if not active_cards:
        await state.clear()
        await message.answer(
            "❌ در حال حاضر هیچ کارت فعالی برای شارژ حساب ثبت نشده است.",
            reply_markup=main_menu_keyboard_for_user(message.from_user.id),
        )
        return False

    file_id, suffix = _get_receipt_file_info(message)
    if not file_id:
        return False

    user_id = message.from_user.id
    folder_date = jdatetime.datetime.now().togregorian().strftime("%Y-%m-%d")
    user_folder = Path("transactions") / folder_date / str(user_id)
    user_folder.mkdir(parents=True, exist_ok=True)

    photo_path = user_folder / f"{file_id}{suffix}"
    telegram_file = await bot.get_file(file_id)
    await bot.download_file(telegram_file.file_path, destination=photo_path)
    photo_hash = calculate_photo_hash(str(photo_path))

    txn_id = create_transaction_draft(
        user_id=user_id,
        photo_id=file_id,
        photo_path=str(photo_path),
        photo_hash=photo_hash,
    )

    await state.clear()
    await state.update_data(payment_txn_id=txn_id)
    await message.answer(
        "✅ رسید پرداخت دریافت شد. حالا چند مورد کوتاه را ثبت می‌کنیم تا بررسی سریع‌تر و دقیق‌تر انجام شود.",
        reply_markup=main_menu_keyboard_for_user(message.from_user.id),
    )
    await prompt_amount(message, state)
    return True


def ensure_user_record(message: Message) -> None:
    user_id = message.from_user.id
    first_name = message.from_user.first_name
    username = message.from_user.username
    last_name = message.from_user.last_name
    role = "admin" if user_id in ADMINS else "user"
    if not ensure_user_exists(user_id=user_id):
        add_user(user_id, first_name, username, role)
    if last_name:
        update_last_name(user_id=user_id, last_name=last_name)


async def prompt_amount(message: Message, state: FSMContext) -> None:
    await state.set_state(PaymentStates.choosing_amount)
    await message.answer(
        "💰 مبلغ واریزی را انتخاب کنید یا اگر بین گزینه‌ها نبود، «مبلغ دیگر» را بزنید:",
        reply_markup=amount_keyboard(),
    )


async def prompt_destination_card(message: Message, state: FSMContext) -> None:
    await state.set_state(PaymentStates.choosing_destination_card)
    await message.answer(
        "🏦 کارت مقصدی که مبلغ را به آن واریز کرده‌اید انتخاب کنید:",
        reply_markup=destination_card_keyboard(),
    )


async def prompt_transfer_date(message: Message, state: FSMContext) -> None:
    await state.set_state(PaymentStates.choosing_transfer_date)
    await message.answer(
        "📅 تاریخ واریز را انتخاب کنید. اگر در گزینه‌ها نبود، ورود دستی را بزنید:",
        reply_markup=transfer_date_keyboard(),
    )


async def prompt_transfer_time(message: Message, state: FSMContext) -> None:
    await state.set_state(PaymentStates.typing_transfer_time)
    await message.answer(
        "🕒 ساعت دقیق واریز را با فرمت <code>HH:MM</code> بفرست.\nمثال: <code>14:37</code>",
        parse_mode="HTML",
        reply_markup=cancel_only_keyboard(),
    )


async def prompt_source_last4(message: Message, state: FSMContext) -> None:
    await state.set_state(PaymentStates.typing_source_card_last4)
    await message.answer(
        "💳 ۴ رقم آخر کارت مبدا را بفرست.\n"
        "وارد کردنش باعث سریع‌تر تایید شدن میشه.\n"
        "اگر نمی‌خواهی، دکمه «ندارم» را بزن.",
        reply_markup=optional_keyboard("ندارم"),
    )


async def prompt_confirmation(message: Message, state: FSMContext) -> None:
    data = await state.get_data()
    txn_id = data.get("payment_txn_id")
    if not txn_id:
        await state.clear()
        await message.answer("❌ وضعیت ثبت فیش پیدا نشد. دوباره از اول اقدام کن.", reply_markup=main_menu_keyboard_for_user(message.from_user.id))
        return

    txn = get_transaction(int(txn_id))
    if not txn or txn.get("status") != STATUS_DRAFT:
        await state.clear()
        await message.answer("❌ این ثبت فیش دیگر قابل ادامه نیست. دوباره شروع کن.", reply_markup=main_menu_keyboard_for_user(message.from_user.id))
        return

    await state.set_state(PaymentStates.confirming)
    await message.answer(
        build_payment_summary(txn),
        parse_mode="HTML",
        reply_markup=confirmation_keyboard(),
    )


@router.message(F.text.in_({"💳 شارژ حساب", "💳 شماره کارت", "💳 دریافت شماره کارت"}))
async def start_topup_flow(message: Message, state: FSMContext):
    ensure_user_record(message)
    await state.clear()
    await state.set_state(PaymentStates.waiting_for_receipt)
    await message.answer(
        build_cards_text(),
        parse_mode="HTML",
        reply_markup=main_menu_keyboard_for_user(message.from_user.id),
    )


@router.message(PaymentStates.waiting_for_receipt)
async def waiting_for_receipt_message(message: Message, state: FSMContext, bot: Bot):
    if message.photo:
        handled = await register_receipt_upload(message, state, bot)
        if handled:
            return

    await message.answer("📸 لطفاً عکس فیش را بفرست تا ثبت اطلاعات را ادامه بدهیم.")


@router.message(F.photo)
async def catch_any_photo_as_receipt(message: Message, state: FSMContext, bot: Bot):
    current_state = await state.get_state()
    allowed_states = {None}
    if current_state not in allowed_states:
        return

    await register_receipt_upload(message, state, bot)


@router.callback_query(F.data.startswith("pay|amount|"))
async def choose_amount(callback: CallbackQuery, state: FSMContext):
    _, _, value = callback.data.split("|", 2)
    data = await state.get_data()
    txn_id = data.get("payment_txn_id")
    if not txn_id:
        await state.clear()
        await callback.message.answer("❌ ثبت فیش پیدا نشد. دوباره از اول اقدام کن.")
        return await callback.answer()

    if value == "other":
        await state.set_state(PaymentStates.typing_amount)
        await callback.message.answer(
            f"💰 مبلغ را به تومان بفرست.\nبازه مجاز: {format_price(MIN_TOPUP)} تا {format_price(MAX_TOPUP)} تومان",
            reply_markup=cancel_only_keyboard(),
        )
        return await callback.answer()

    amount = parse_amount(value)
    if amount is None or not set_claimed_amount(int(txn_id), callback.from_user.id, amount):
        await callback.message.answer("❌ ثبت مبلغ انجام نشد. دوباره تلاش کن.")
        return await callback.answer()

    await callback.answer("مبلغ ثبت شد.")
    await prompt_destination_card(callback.message, state)


@router.message(PaymentStates.typing_amount)
async def type_amount(message: Message, state: FSMContext):
    data = await state.get_data()
    txn_id = data.get("payment_txn_id")
    amount = parse_amount(message.text or "")
    if not txn_id or amount is None:
        await message.answer(
            f"❌ لطفاً مبلغی بین {format_price(MIN_TOPUP)} تا {format_price(MAX_TOPUP)} تومان وارد کن."
        )
        return

    if not set_claimed_amount(int(txn_id), message.from_user.id, amount):
        await state.clear()
        await message.answer("❌ ثبت مبلغ انجام نشد. دوباره از اول اقدام کن.", reply_markup=main_menu_keyboard_for_user(message.from_user.id))
        return

    await prompt_destination_card(message, state)


@router.callback_query(F.data.startswith("pay|dest_card|"))
async def choose_destination_card(callback: CallbackQuery, state: FSMContext):
    _, _, value = callback.data.split("|", 2)
    data = await state.get_data()
    txn_id = data.get("payment_txn_id")
    if not txn_id:
        await state.clear()
        await callback.message.answer("❌ ثبت فیش پیدا نشد. دوباره از اول اقدام کن.")
        return await callback.answer()

    if value == "manual":
        await state.set_state(PaymentStates.typing_destination_card)
        await callback.message.answer(
            "✏️ شماره کامل کارت مقصد را بفرست.\nمثال: <code>6037123412341234</code>",
            parse_mode="HTML",
            reply_markup=cancel_only_keyboard(),
        )
        return await callback.answer()

    if not set_destination_card_from_card_id(int(txn_id), callback.from_user.id, int(value)):
        await callback.message.answer("❌ ثبت کارت مقصد انجام نشد. دوباره تلاش کن.")
        return await callback.answer()

    await callback.answer("کارت مقصد ثبت شد.")
    await prompt_transfer_date(callback.message, state)


@router.message(PaymentStates.typing_destination_card)
async def type_destination_card(message: Message, state: FSMContext):
    data = await state.get_data()
    txn_id = data.get("payment_txn_id")
    normalized = normalize_card_number(message.text or "")
    if not txn_id or len(normalized) != 16:
        await message.answer("❌ لطفاً شماره کارت ۱۶ رقمی معتبر وارد کن.")
        return

    if not set_destination_card_manual(int(txn_id), message.from_user.id, normalized):
        await state.clear()
        await message.answer("❌ ثبت کارت مقصد انجام نشد. دوباره از اول اقدام کن.", reply_markup=main_menu_keyboard_for_user(message.from_user.id))
        return

    await prompt_transfer_date(message, state)


@router.callback_query(F.data.startswith("pay|date|"))
async def choose_transfer_date(callback: CallbackQuery, state: FSMContext):
    _, _, value = callback.data.split("|", 2)
    data = await state.get_data()
    txn_id = data.get("payment_txn_id")
    if not txn_id:
        await state.clear()
        await callback.message.answer("❌ ثبت فیش پیدا نشد. دوباره از اول اقدام کن.")
        return await callback.answer()

    if value == "manual":
        await state.set_state(PaymentStates.typing_transfer_date)
        await callback.message.answer(
            "📅 تاریخ واریز را با فرمت <code>1405/01/16</code> بفرست.",
            parse_mode="HTML",
            reply_markup=cancel_only_keyboard(),
        )
        return await callback.answer()

    selected_date = _selected_relative_date(value)
    if not selected_date or not set_transfer_date(int(txn_id), callback.from_user.id, selected_date):
        await callback.message.answer("❌ ثبت تاریخ انجام نشد. دوباره تلاش کن.")
        return await callback.answer()

    await callback.answer("تاریخ ثبت شد.")
    await prompt_transfer_time(callback.message, state)


@router.message(PaymentStates.typing_transfer_date)
async def type_transfer_date(message: Message, state: FSMContext):
    data = await state.get_data()
    txn_id = data.get("payment_txn_id")
    transfer_date = parse_manual_date(message.text or "")
    if not txn_id or not transfer_date:
        await message.answer("❌ تاریخ را با فرمت درست مثل <code>1405/01/16</code> بفرست.", parse_mode="HTML")
        return

    if not set_transfer_date(int(txn_id), message.from_user.id, transfer_date):
        await state.clear()
        await message.answer("❌ ثبت تاریخ انجام نشد. دوباره از اول اقدام کن.", reply_markup=main_menu_keyboard_for_user(message.from_user.id))
        return

    await prompt_transfer_time(message, state)


@router.message(PaymentStates.typing_transfer_time)
async def type_transfer_time(message: Message, state: FSMContext):
    data = await state.get_data()
    txn_id = data.get("payment_txn_id")
    time_value = parse_time_value(message.text or "")
    if not txn_id or not time_value:
        await message.answer("❌ ساعت را با فرمت <code>HH:MM</code> بفرست. مثال: <code>14:37</code>", parse_mode="HTML")
        return

    if not set_transfer_time(int(txn_id), message.from_user.id, time_value):
        await state.clear()
        await message.answer("❌ ثبت ساعت انجام نشد. دوباره از اول اقدام کن.", reply_markup=main_menu_keyboard_for_user(message.from_user.id))
        return

    await prompt_source_last4(message, state)


@router.message(PaymentStates.typing_source_card_last4)
async def type_source_last4(message: Message, state: FSMContext):
    data = await state.get_data()
    txn_id = data.get("payment_txn_id")
    last4 = normalize_last4(message.text or "")
    if not txn_id or len(last4) != 4:
        await message.answer("❌ فقط ۴ رقم آخر کارت مبدا را بفرست یا از دکمه «ندارم» استفاده کن.")
        return

    if not set_source_card_last4(int(txn_id), message.from_user.id, last4):
        await state.clear()
        await message.answer("❌ ثبت ۴ رقم آخر کارت انجام نشد. دوباره از اول اقدام کن.", reply_markup=main_menu_keyboard_for_user(message.from_user.id))
        return

    await prompt_confirmation(message, state)


@router.callback_query(F.data == "pay|skip")
async def skip_optional_step(callback: CallbackQuery, state: FSMContext):
    current_state = await state.get_state()
    data = await state.get_data()
    txn_id = data.get("payment_txn_id")
    if not txn_id:
        await state.clear()
        await callback.message.answer("❌ ثبت فیش پیدا نشد. دوباره از اول اقدام کن.")
        return await callback.answer()

    if current_state == PaymentStates.typing_transfer_time.state:
        await callback.message.answer("❌ ساعت واریز اجباری است و باید وارد شود.")
        return await callback.answer()

    if current_state == PaymentStates.typing_amount.state:
        await callback.message.answer("❌ مبلغ واریز اجباری است و باید وارد شود.")
        return await callback.answer()

    if current_state == PaymentStates.typing_destination_card.state:
        await callback.message.answer("❌ کارت مقصد اجباری است و باید وارد شود.")
        return await callback.answer()

    if current_state == PaymentStates.typing_transfer_date.state:
        await callback.message.answer("❌ تاریخ واریز اجباری است و باید وارد شود.")
        return await callback.answer()

    if current_state == PaymentStates.typing_source_card_last4.state:
        set_source_card_last4(int(txn_id), callback.from_user.id, None)
        await callback.answer("۴ رقم آخر ثبت نشد.")
        await prompt_confirmation(callback.message, state)
        return

    await callback.answer()


@router.callback_query(F.data == "pay|confirm")
async def confirm_payment_submission(callback: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    txn_id = data.get("payment_txn_id")
    if not txn_id:
        await state.clear()
        await callback.message.answer("❌ ثبت فیش پیدا نشد. دوباره از اول اقدام کن.")
        return await callback.answer()

    txn = submit_transaction_for_review(int(txn_id), callback.from_user.id)
    if not txn:
        await callback.message.answer("❌ ثبت نهایی فیش انجام نشد. دوباره تلاش کن یا از اول شروع کن.")
        return await callback.answer()

    duplicate_candidates = get_duplicate_candidates(int(txn_id), limit=5)
    duplicate_note = ""
    if duplicate_candidates:
        duplicate_note = "\n⚠️ این فیش برای بررسی دقیق‌تر علامت‌گذاری شد."

    await callback.message.answer(
        "✅ فیش شما ثبت شد و برای بررسی ارسال شد."
        f"{duplicate_note}",
        reply_markup=main_menu_keyboard_for_user(callback.from_user.id),
    )

    for admin_id in ADMINS:
        try:
            await callback.bot.send_photo(
                admin_id,
                txn["photo_id"],
                caption=build_admin_submission_caption(txn),
                parse_mode="HTML",
                reply_markup=review_notification_keyboard(int(txn_id)),
            )
        except Exception as exc:
            print(f"خطا در ارسال اعلان تراکنش #{txn_id} به ادمین {admin_id}: {exc}")

    await state.clear()
    await callback.answer("ثبت شد.")


@router.callback_query(F.data == "pay|cancel")
async def cancel_payment_flow(callback: CallbackQuery, state: FSMContext):
    await state.clear()
    await callback.message.answer(
        "ثبت فیش لغو شد.",
        reply_markup=main_menu_keyboard_for_user(callback.from_user.id),
    )
    await callback.answer("لغو شد.")

