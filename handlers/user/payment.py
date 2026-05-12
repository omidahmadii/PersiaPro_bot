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
    create_transaction_draft,
    duplicate_reason_label,
    format_card_number_for_display,
    get_active_bank_cards,
    get_photo_hash_submission_state,
    get_receipt_bank_cards,
    get_duplicate_candidates,
    normalize_card_number,
    normalize_digits,
    set_claimed_amount,
    set_destination_card_from_card_id,
    set_destination_card_manual,
    set_transfer_date,
    set_transfer_time,
    submit_transaction_for_review,
)
from services.runtime_settings import get_payment_common_amounts

router = Router()

MIN_TOPUP = 1_000
MAX_TOPUP = 50_000_000


class PaymentStates(StatesGroup):
    choosing_amount = State()
    typing_amount = State()
    choosing_destination_card = State()
    typing_destination_card = State()
    choosing_transfer_date = State()
    typing_transfer_date = State()
    typing_transfer_time = State()


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


def ltr_card_text(card_number: Optional[str]) -> str:
    return format_card_number_for_display(card_number)


def cancel_only_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="❌ انصراف", callback_data="pay|cancel")],
        ]
    )


def amount_keyboard() -> InlineKeyboardMarkup:
    rows = []
    common_amounts = get_payment_common_amounts()
    for index in range(0, len(common_amounts), 2):
        chunk = common_amounts[index:index + 2]
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
    for card in get_receipt_bank_cards():
        label = f"{ltr_card_text(card['card_number'])} | {card.get('bank_name') or '-'}"
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
    items = []
    for raw in (flags or "").split(","):
        key = raw.strip()
        if not key:
            continue
        items.append(duplicate_reason_label(key))
    return "، ".join(items)


def build_cards_text() -> str:
    active_cards = get_active_bank_cards()
    if not active_cards:
        return "در حال حاضر هیچ کارت فعالی برای شارژ حساب ثبت نشده است."

    lines = ["💳 برای شارژ حساب، مبلغ را به یکی از کارت‌های زیر واریز کنید:", ""]
    for card in active_cards:
        lines.append(f"🏦 {card.get('bank_name') or '-'} به نام {card.get('owner_name') or '-'}")
        lines.append(f"<code>{ltr_card_text(card.get('card_number'))}</code>")
        lines.append("")
    lines.append("📸 پس از واریز، لطفاً تصویر فیش را همین‌جا ارسال کنید تا فرایند ثبت پرداخت آغاز شود.")
    return "\n".join(lines)


def build_admin_submission_caption(txn: dict) -> str:
    name_parts = [txn.get("first_name") or "", txn.get("last_name") or ""]
    full_name = " ".join(part for part in name_parts if part).strip() or "-"
    destination_card = ltr_card_text(txn.get("destination_card_number"))
    destination_bank = txn.get("destination_bank_name") or "کارت خارج از لیست"
    duplicate_note = ""
    if int(txn.get("is_duplicate_suspect") or 0) == 1:
        duplicate_note = f"\n⚠️ مشکوک به تکرار: {_format_duplicate_flags(txn.get('duplicate_flags'))}"
    return (
        f"📥 تراکنش جدید #{txn['id']}\n"
        f"👤 کاربر: <a href='tg://user?id={txn['user_id']}'>{txn['user_id']} {full_name}</a>\n"
        f"💰 مبلغ اعلامی: {format_price(txn.get('amount_claimed') or 0)} تومان\n"
        f"🏦 کارت مقصد: <code>{destination_card}</code> | {destination_bank}\n"
        f"📅 زمان واریز: {txn.get('transfer_date') or '-'} {txn.get('transfer_time') or '-'}\n"
        f"💳 ۴ رقم آخر کارت مبدا: {txn.get('source_card_last4') or 'ندارد'}\n"
        f"{duplicate_note}"
    )


def cleanup_unused_receipt_file(photo_path: Path) -> None:
    try:
        photo_path.unlink(missing_ok=True)
    except Exception:
        pass

    try:
        parent = photo_path.parent
        if parent.exists() and not any(parent.iterdir()):
            parent.rmdir()
            grandparent = parent.parent
            if grandparent.exists() and not any(grandparent.iterdir()):
                grandparent.rmdir()
    except Exception:
        pass


async def register_receipt_upload(message: Message, state: FSMContext, bot: Bot) -> bool:
    ensure_user_record(message)

    receipt_cards = get_receipt_bank_cards()
    if not receipt_cards:
        await state.clear()
        await message.answer(
            "❌ در حال حاضر هیچ کارتی برای ثبت فیش فعال نشده است.",
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

    existing_photo_state = get_photo_hash_submission_state(photo_hash)
    if existing_photo_state:
        cleanup_unused_receipt_file(photo_path)
        await state.clear()

        if existing_photo_state["result"] == "approved":
            await message.answer(
                "✅ این فیش قبلاً تایید شده است. لطفاً از ارسال مجدد آن خودداری فرمایید.",
                reply_markup=main_menu_keyboard_for_user(message.from_user.id),
            )
            return False

        if existing_photo_state["result"] != "retryable":
            await message.answer(
                "⏳ این فیش قبلاً ثبت شده و همچنان در حال بررسی است. لطفاً منتظر بمانید تا نتیجه بررسی اعلام شود.",
                reply_markup=main_menu_keyboard_for_user(message.from_user.id),
            )
            return False

    txn_id = create_transaction_draft(
        user_id=user_id,
        photo_id=file_id,
        photo_path=str(photo_path),
        photo_hash=photo_hash,
    )

    await state.clear()
    await state.update_data(payment_txn_id=txn_id)
    await message.answer(
        "✅ رسید پرداخت شما دریافت شد. لطفاً در ادامه چند مورد کوتاه را ثبت کنید تا بررسی سریع‌تر و دقیق‌تر انجام شود.",
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
        "💰 مبلغ واریزی را انتخاب کنید. اگر مبلغ موردنظر در گزینه‌ها نبود، «مبلغ دیگر» را انتخاب فرمایید:",
        reply_markup=amount_keyboard(),
    )


async def prompt_destination_card(message: Message, state: FSMContext) -> None:
    await state.set_state(PaymentStates.choosing_destination_card)
    await message.answer(
        "🏦 لطفاً کارت مقصدی را که مبلغ به آن واریز شده است انتخاب کنید:",
        reply_markup=destination_card_keyboard(),
    )


async def prompt_transfer_date(message: Message, state: FSMContext) -> None:
    await state.set_state(PaymentStates.choosing_transfer_date)
    await message.answer(
        "📅 لطفاً تاریخ واریز را انتخاب کنید. اگر در گزینه‌ها موجود نبود، «ورود دستی تاریخ» را انتخاب فرمایید:",
        reply_markup=transfer_date_keyboard(),
    )


async def prompt_transfer_time(message: Message, state: FSMContext) -> None:
    await state.set_state(PaymentStates.typing_transfer_time)
    await message.answer(
        "🕒 لطفاً ساعت دقیق واریز را با فرمت <code>HH:MM</code> ارسال کنید.\nمثال: <code>14:37</code>",
        parse_mode="HTML",
        reply_markup=cancel_only_keyboard(),
    )


async def finalize_payment_submission(message: Message, state: FSMContext, bot: Bot) -> None:
    data = await state.get_data()
    txn_id = data.get("payment_txn_id")
    if not txn_id:
        await state.clear()
        await message.answer(
            "❌ ثبت فیش یافت نشد. لطفاً دوباره از ابتدا اقدام کنید.",
            reply_markup=main_menu_keyboard_for_user(message.from_user.id),
        )
        return

    txn = submit_transaction_for_review(int(txn_id), message.from_user.id)
    if not txn:
        await state.clear()
        await message.answer(
            "❌ ثبت فیش انجام نشد. لطفاً دوباره تلاش کنید یا مجدداً از ابتدا شروع فرمایید.",
            reply_markup=main_menu_keyboard_for_user(message.from_user.id),
        )
        return

    duplicate_candidates = get_duplicate_candidates(int(txn_id), limit=5)
    duplicate_note = ""
    if duplicate_candidates:
        duplicate_note = "\n⚠️ این فیش برای بررسی دقیق‌تر علامت‌گذاری شد."

    await message.answer(
        "✅ فیش شما با موفقیت ثبت شد. لطفاً منتظر بررسی و تایید بمانید."
        f"{duplicate_note}",
        reply_markup=main_menu_keyboard_for_user(message.from_user.id),
    )

    for admin_id in ADMINS:
        try:
            await bot.send_photo(
                admin_id,
                txn["photo_id"],
                caption=build_admin_submission_caption(txn),
                parse_mode="HTML",
                reply_markup=review_notification_keyboard(int(txn_id)),
            )
        except Exception as exc:
            print(f"خطا در ارسال اعلان تراکنش #{txn_id} به ادمین {admin_id}: {exc}")

    await state.clear()


@router.message(F.text.in_({"💳 شارژ حساب", "💳 شماره کارت", "💳 دریافت شماره کارت", "شماره کارت"}))
async def start_topup_flow(message: Message, state: FSMContext):
    ensure_user_record(message)
    await state.clear()
    await message.answer(
        build_cards_text(),
        parse_mode="HTML",
        reply_markup=main_menu_keyboard_for_user(message.from_user.id),
    )

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
        await callback.message.answer("❌ ثبت فیش یافت نشد. لطفاً دوباره از ابتدا اقدام کنید.")
        return await callback.answer()

    if value == "other":
        await state.set_state(PaymentStates.typing_amount)
        await callback.message.answer(
            f"💰 لطفاً مبلغ را به تومان ارسال کنید.\nبازه مجاز: {format_price(MIN_TOPUP)} تا {format_price(MAX_TOPUP)} تومان",
            reply_markup=cancel_only_keyboard(),
        )
        return await callback.answer()

    amount = parse_amount(value)
    if amount is None or not set_claimed_amount(int(txn_id), callback.from_user.id, amount):
        await callback.message.answer("❌ ثبت مبلغ انجام نشد. لطفاً دوباره تلاش کنید.")
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
            f"❌ لطفاً مبلغی بین {format_price(MIN_TOPUP)} تا {format_price(MAX_TOPUP)} تومان وارد کنید."
        )
        return

    if not set_claimed_amount(int(txn_id), message.from_user.id, amount):
        await state.clear()
        await message.answer("❌ ثبت مبلغ انجام نشد. لطفاً دوباره از ابتدا اقدام کنید.", reply_markup=main_menu_keyboard_for_user(message.from_user.id))
        return

    await prompt_destination_card(message, state)


@router.callback_query(F.data.startswith("pay|dest_card|"))
async def choose_destination_card(callback: CallbackQuery, state: FSMContext):
    _, _, value = callback.data.split("|", 2)
    data = await state.get_data()
    txn_id = data.get("payment_txn_id")
    if not txn_id:
        await state.clear()
        await callback.message.answer("❌ ثبت فیش یافت نشد. لطفاً دوباره از ابتدا اقدام کنید.")
        return await callback.answer()

    if value == "manual":
        await state.set_state(PaymentStates.typing_destination_card)
        await callback.message.answer(
            "✏️ لطفاً شماره کامل کارت مقصد را ارسال کنید.\nمثال: <code>6037123412341234</code>",
            parse_mode="HTML",
            reply_markup=cancel_only_keyboard(),
        )
        return await callback.answer()

    if not set_destination_card_from_card_id(int(txn_id), callback.from_user.id, int(value)):
        await callback.message.answer("❌ ثبت کارت مقصد انجام نشد. لطفاً دوباره تلاش کنید.")
        return await callback.answer()

    await callback.answer("کارت مقصد ثبت شد.")
    await prompt_transfer_date(callback.message, state)


@router.message(PaymentStates.typing_destination_card)
async def type_destination_card(message: Message, state: FSMContext):
    data = await state.get_data()
    txn_id = data.get("payment_txn_id")
    normalized = normalize_card_number(message.text or "")
    if not txn_id or len(normalized) != 16:
        await message.answer("❌ لطفاً شماره کارت ۱۶ رقمی معتبر وارد کنید.")
        return

    if not set_destination_card_manual(int(txn_id), message.from_user.id, normalized):
        await state.clear()
        await message.answer("❌ ثبت کارت مقصد انجام نشد. لطفاً دوباره از ابتدا اقدام کنید.", reply_markup=main_menu_keyboard_for_user(message.from_user.id))
        return

    await prompt_transfer_date(message, state)


@router.callback_query(F.data.startswith("pay|date|"))
async def choose_transfer_date(callback: CallbackQuery, state: FSMContext):
    _, _, value = callback.data.split("|", 2)
    data = await state.get_data()
    txn_id = data.get("payment_txn_id")
    if not txn_id:
        await state.clear()
        await callback.message.answer("❌ ثبت فیش یافت نشد. لطفاً دوباره از ابتدا اقدام کنید.")
        return await callback.answer()

    if value == "manual":
        await state.set_state(PaymentStates.typing_transfer_date)
        await callback.message.answer(
            "📅 لطفاً تاریخ واریز را با فرمت <code>1405/01/16</code> ارسال کنید.",
            parse_mode="HTML",
            reply_markup=cancel_only_keyboard(),
        )
        return await callback.answer()

    selected_date = _selected_relative_date(value)
    if not selected_date or not set_transfer_date(int(txn_id), callback.from_user.id, selected_date):
        await callback.message.answer("❌ ثبت تاریخ انجام نشد. لطفاً دوباره تلاش کنید.")
        return await callback.answer()

    await callback.answer("تاریخ ثبت شد.")
    await prompt_transfer_time(callback.message, state)


@router.message(PaymentStates.typing_transfer_date)
async def type_transfer_date(message: Message, state: FSMContext):
    data = await state.get_data()
    txn_id = data.get("payment_txn_id")
    transfer_date = parse_manual_date(message.text or "")
    if not txn_id or not transfer_date:
        await message.answer("❌ لطفاً تاریخ را با فرمت صحیح، مانند <code>1405/01/16</code> ارسال کنید.", parse_mode="HTML")
        return

    if not set_transfer_date(int(txn_id), message.from_user.id, transfer_date):
        await state.clear()
        await message.answer("❌ ثبت تاریخ انجام نشد. لطفاً دوباره از ابتدا اقدام کنید.", reply_markup=main_menu_keyboard_for_user(message.from_user.id))
        return

    await prompt_transfer_time(message, state)


@router.message(PaymentStates.typing_transfer_time)
async def type_transfer_time(message: Message, state: FSMContext, bot: Bot):
    data = await state.get_data()
    txn_id = data.get("payment_txn_id")
    time_value = parse_time_value(message.text or "")
    if not txn_id or not time_value:
        await message.answer("❌ لطفاً ساعت را با فرمت <code>HH:MM</code> ارسال کنید. مثال: <code>14:37</code>", parse_mode="HTML")
        return

    if not set_transfer_time(int(txn_id), message.from_user.id, time_value):
        await state.clear()
        await message.answer("❌ ثبت ساعت انجام نشد. لطفاً دوباره از ابتدا اقدام کنید.", reply_markup=main_menu_keyboard_for_user(message.from_user.id))
        return

    await finalize_payment_submission(message, state, bot)


@router.callback_query(F.data == "pay|cancel")
async def cancel_payment_flow(callback: CallbackQuery, state: FSMContext):
    await state.clear()
    await callback.message.answer(
        "فرایند ثبت فیش لغو شد.",
        reply_markup=main_menu_keyboard_for_user(callback.from_user.id),
    )
    await callback.answer("لغو شد.")
