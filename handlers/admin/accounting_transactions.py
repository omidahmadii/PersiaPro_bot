import jdatetime
from typing import Optional, Tuple

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message

from config import ADMINS
from keyboards.main_menu import admin_main_menu_keyboard
from services.db import get_user_balance
from services.payment_workflow import (
    STATUS_ACCOUNTING_APPROVED,
    STATUS_APPROVED_PENDING_ACCOUNTING,
    confirm_transaction_accounting,
    duplicate_reason_label as payment_duplicate_reason_label,
    format_card_number_for_display,
    get_receipt_bank_cards,
    get_duplicate_candidates,
    get_transaction_status_label,
    get_transaction_with_user,
    list_reversible_transactions,
    list_transactions_by_status,
    normalize_card_number,
    normalize_digits,
    normalize_last4,
    reject_transaction_accounting,
    reverse_transaction_balance,
    set_accounting_destination_card_from_card_id,
    set_accounting_destination_card_manual,
    set_accounting_source_card_last4,
    set_accounting_transfer_datetime,
)
from services.telegram_message_utils import send_photo_with_details

router = Router()
UNKNOWN_DESTINATION_CARD_KEY = "unknown"


class AccountingTxn(StatesGroup):
    waiting_for_reject_reason = State()
    waiting_for_source_last4 = State()
    waiting_for_destination_card_manual = State()
    waiting_for_transfer_datetime = State()
    waiting_for_revert_reason = State()


def is_admin(user_id: int) -> bool:
    return str(user_id) in {str(admin_id) for admin_id in ADMINS}


def format_price(amount: int) -> str:
    try:
        return f"{int(amount):,}"
    except Exception:
        return str(amount)


def mask_card(card_number: Optional[str]) -> str:
    return format_card_number_for_display(card_number)


def duplicate_reason_label(reason: str) -> str:
    return payment_duplicate_reason_label(reason)


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


def parse_transfer_datetime_input(
    text: str,
    current_date: Optional[str],
    current_time: Optional[str],
) -> Optional[Tuple[str, str]]:
    cleaned = normalize_digits(text).strip()
    if not cleaned:
        return None

    parts = [part for part in cleaned.split() if part]
    date_value = current_date
    time_value = current_time

    if len(parts) == 1:
        if "/" in parts[0] or "-" in parts[0]:
            date_value = parse_manual_date(parts[0])
        else:
            time_value = parse_time_value(parts[0])
    elif len(parts) == 2:
        date_value = parse_manual_date(parts[0])
        time_value = parse_time_value(parts[1])
    else:
        return None

    if not date_value or not time_value:
        return None
    return date_value, time_value


def transaction_destination_card_key(txn: dict) -> str:
    return normalize_card_number(txn.get("destination_card_number")) or UNKNOWN_DESTINATION_CARD_KEY


def transaction_display_name(txn: dict) -> str:
    full_name = " ".join(part for part in [txn.get("first_name") or "", txn.get("last_name") or ""] if part).strip()
    username = (txn.get("username") or "").strip()
    label = full_name or (f"@{username}" if username else "")
    if label:
        return label[:12].strip()
    return ""


def transaction_display_datetime(txn: dict) -> str:
    transfer_date = (txn.get("transfer_date") or "").strip()
    transfer_time = (txn.get("transfer_time") or "").strip()
    if transfer_date and transfer_time:
        return f"{transfer_date} {transfer_time}"
    return transfer_date or transfer_time or "نامشخص"


def transaction_duplicate_mark(txn: dict) -> str:
    return " !" if int(txn.get("is_duplicate_suspect") or 0) == 1 else ""


def transaction_transfer_sort_key(txn: dict) -> tuple[int, tuple[int, int, int], tuple[int, int], int]:
    raw_date = normalize_digits((txn.get("transfer_date") or "").strip())
    raw_time = normalize_digits((txn.get("transfer_time") or "").strip())

    date_parts = [part for part in raw_date.replace("-", "/").split("/") if part]
    time_parts = [part for part in raw_time.split(":") if part]

    date_tuple = (9999, 99, 99)
    time_tuple = (99, 99)
    has_complete_datetime = len(date_parts) == 3 and len(time_parts) == 2

    if len(date_parts) == 3:
        try:
            date_tuple = tuple(int(part) for part in date_parts[:3])
        except Exception:
            date_tuple = (9999, 99, 99)

    if len(time_parts) == 2:
        try:
            time_tuple = tuple(int(part) for part in time_parts[:2])
        except Exception:
            time_tuple = (99, 99)

    return (0 if has_complete_datetime else 1, date_tuple, time_tuple, int(txn.get("id") or 0))


def build_accounting_card_groups(transactions: list[dict]) -> list[dict]:
    groups_by_key: dict[str, dict] = {}

    for txn in transactions:
        card_key = transaction_destination_card_key(txn)
        group = groups_by_key.setdefault(
            card_key,
            {
                "key": card_key,
                "card_number": txn.get("destination_card_number"),
                "bank_name": (txn.get("destination_bank_name") or "").strip() or None,
                "owner_name": (txn.get("destination_card_owner") or "").strip() or None,
                "transactions": [],
                "total_amount": 0,
            },
        )
        if not group.get("card_number") and txn.get("destination_card_number"):
            group["card_number"] = txn.get("destination_card_number")
        if not group.get("bank_name") and (txn.get("destination_bank_name") or "").strip():
            group["bank_name"] = (txn.get("destination_bank_name") or "").strip()
        if not group.get("owner_name") and (txn.get("destination_card_owner") or "").strip():
            group["owner_name"] = (txn.get("destination_card_owner") or "").strip()

        group["transactions"].append(txn)
        group["total_amount"] += int(txn.get("amount") or 0)

    groups = []
    for group in groups_by_key.values():
        sorted_transactions = sorted(group["transactions"], key=transaction_transfer_sort_key)
        groups.append(
            {
                **group,
                "transactions": sorted_transactions,
                "count": len(sorted_transactions),
            }
        )

    return sorted(
        groups,
        key=lambda group: (
            transaction_transfer_sort_key(group["transactions"][0]) if group["transactions"] else (1, (9999, 99, 99), (99, 99), 0),
            group["key"],
        ),
    )


def find_accounting_card_group(transactions: list[dict], card_key: str) -> Optional[dict]:
    for group in build_accounting_card_groups(transactions):
        if group["key"] == card_key:
            return group
    return None


def build_accounting_group_button_text(group: dict) -> str:
    parts = [
        f"🏦 {mask_card(group.get('card_number'))}",
        f"{group['count']} تراکنش",
        format_price(group.get("total_amount") or 0),
    ]
    bank_name = (group.get("bank_name") or "").strip()
    if bank_name:
        parts.append(bank_name)
    return " | ".join(parts)


def build_accounting_transaction_button_text(txn: dict) -> str:
    parts = [
        transaction_display_datetime(txn),
        format_price(txn.get("amount") or 0),
    ]
    button_text = " ".join(parts)
    return f"{button_text}{transaction_duplicate_mark(txn)}"


def build_accounting_txn_callback(action: str, txn_id: int, card_key: Optional[str] = None) -> str:
    if card_key:
        return f"acct|{action}|{txn_id}|{card_key}"
    return f"acct|{action}|{txn_id}"


def parse_accounting_txn_callback(data: str) -> tuple[int, Optional[str]]:
    parts = data.split("|", 3)
    txn_id = int(parts[2])
    card_key = parts[3] if len(parts) > 3 else None
    return txn_id, card_key


def accounting_queue_keyboard(transactions: list[dict]) -> InlineKeyboardMarkup:
    rows = []
    for group in build_accounting_card_groups(transactions):
        rows.append(
            [
                InlineKeyboardButton(
                    text=build_accounting_group_button_text(group)[:64],
                    callback_data=f"acct|card|{group['key']}",
                )
            ]
        )
    rows.append([InlineKeyboardButton(text="↩️ کسر از حساب / برگشت وجه", callback_data="acct|approved_list")])
    rows.append([InlineKeyboardButton(text="🔙 منوی اصلی", callback_data="acct|main_menu")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def accounting_card_transactions_keyboard(card_key: str, transactions: list[dict]) -> InlineKeyboardMarkup:
    rows = []
    for txn in transactions:
        rows.append(
            [
                InlineKeyboardButton(
                    text=build_accounting_transaction_button_text(txn)[:64],
                    callback_data=build_accounting_txn_callback("open", int(txn["id"]), card_key),
                ),
                InlineKeyboardButton(
                    text="✅",
                    callback_data=build_accounting_txn_callback("approve", int(txn["id"]), card_key),
                ),
            ]
        )
    rows.append([InlineKeyboardButton(text="🔙 لیست کارت‌ها", callback_data="acct|list")])
    rows.append([InlineKeyboardButton(text="↩️ کسر از حساب / برگشت وجه", callback_data="acct|approved_list")])
    rows.append([InlineKeyboardButton(text="🔙 منوی اصلی", callback_data="acct|main_menu")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def approved_transactions_keyboard(transactions: list[dict]) -> InlineKeyboardMarkup:
    rows = []
    for txn in transactions:
        button_text = (
            f"#{txn['id']} | {format_price(txn.get('amount') or 0)} | "
            f"{txn.get('username') or txn.get('first_name') or txn['user_id']}"
        )
        rows.append([InlineKeyboardButton(text=button_text[:64], callback_data=f"acct|approved_open|{txn['id']}")])
    rows.append([InlineKeyboardButton(text="🔙 صف حسابداری", callback_data="acct|list")])
    rows.append([InlineKeyboardButton(text="🔙 منوی اصلی", callback_data="acct|main_menu")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def accounting_review_keyboard(txn_id: int, card_key: Optional[str] = None) -> InlineKeyboardMarkup:
    back_callback = f"acct|card|{card_key}" if card_key else "acct|list"
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="✅ تایید حسابداری", callback_data=build_accounting_txn_callback("approve", txn_id, card_key))],
            [InlineKeyboardButton(text="✏️ ویرایش اطلاعات", callback_data=build_accounting_txn_callback("edit", txn_id, card_key))],
            [InlineKeyboardButton(text="❌ عدم تطبیق / رد", callback_data=build_accounting_txn_callback("reject", txn_id, card_key))],
            [InlineKeyboardButton(text="🔙 لیست حسابداری", callback_data=back_callback)],
        ]
    )


def accounting_edit_keyboard(txn_id: int, card_key: Optional[str] = None) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="💳 ویرایش ۴ رقم آخر", callback_data=build_accounting_txn_callback("edit_last4", txn_id, card_key))],
            [InlineKeyboardButton(text="🏦 تغییر کارت مقصد", callback_data=build_accounting_txn_callback("edit_dest", txn_id, card_key))],
            [InlineKeyboardButton(text="⏱ تغییر زمان واریز", callback_data=build_accounting_txn_callback("edit_time", txn_id, card_key))],
            [InlineKeyboardButton(text="🔙 بازگشت به تراکنش", callback_data=build_accounting_txn_callback("open", txn_id, card_key))],
        ]
    )


def accounting_destination_card_keyboard(txn_id: int, card_key: Optional[str] = None) -> InlineKeyboardMarkup:
    rows = []
    for card in get_receipt_bank_cards():
        label = f"{mask_card(card['card_number'])} | {card.get('bank_name') or '-'}"
        rows.append(
            [
                InlineKeyboardButton(
                    text=label[:64],
                    callback_data=f"acct|dest_card|{txn_id}|{card['id']}",
                )
            ]
        )
    rows.append([InlineKeyboardButton(text="✏️ کارت در لیست نیست", callback_data=f"acct|dest_card|{txn_id}|manual")])
    rows.append([InlineKeyboardButton(text="🔙 بازگشت", callback_data=build_accounting_txn_callback("edit", txn_id, card_key))])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def approved_review_keyboard(txn_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="↩️ کسر از حساب کاربر", callback_data=f"acct|revert|{txn_id}")],
            [InlineKeyboardButton(text="🔙 لیست تراکنش‌های تاییدشده", callback_data="acct|approved_list")],
        ]
    )


def duplicate_lines(txn_id: int) -> str:
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


def build_accounting_photo_caption(txn: dict, title: str) -> str:
    name = " ".join(part for part in [txn.get("first_name") or "", txn.get("last_name") or ""] if part).strip() or "-"
    return (
        f"🏦 <b>{title} #{txn['id']}</b>\n"
        f"👤 کاربر: <a href='tg://user?id={txn['user_id']}'>{txn['user_id']} {name}</a>\n"
        f"📌 وضعیت: <b>{get_transaction_status_label(txn.get('status'))}</b>\n"
        f"💰 مبلغ شارژشده: <b>{format_price(txn.get('amount') or 0)} تومان</b>"
    )


def build_accounting_details(txn: dict, title: str) -> str:
    name = " ".join(part for part in [txn.get("first_name") or "", txn.get("last_name") or ""] if part).strip() or "-"
    admin_name = txn.get("admin_reviewed_by") or "-"
    lines = [
        f"🏦 <b>{title} #{txn['id']}</b>",
        "",
        f"👤 کاربر: <a href='tg://user?id={txn['user_id']}'>{txn['user_id']} {name}</a>",
        f"📌 وضعیت: <b>{get_transaction_status_label(txn.get('status'))}</b>",
        f"💰 مبلغ شارژشده: <b>{format_price(txn.get('amount') or 0)} تومان</b>",
        f"💰 مبلغ اعلامی: <b>{format_price(txn.get('amount_claimed') or 0)} تومان</b>",
        f"🏦 کارت مقصد: <b>{mask_card(txn.get('destination_card_number'))}</b>",
        f"🏷 بانک/عنوان: <b>{txn.get('destination_bank_name') or 'کارت خارج از لیست'}</b>",
        f"📅 زمان واریز: <b>{txn.get('transfer_date') or '-'} {txn.get('transfer_time') or '-'}</b>",
        f"💳 ۴ رقم آخر کارت مبدا: <b>{txn.get('source_card_last4') or 'ندارد'}</b>",
        f"👮 تایید اولیه توسط: <b>{admin_name}</b>",
        f"⏱ زمان تایید اولیه: <b>{txn.get('admin_reviewed_at') or '-'}</b>",
    ]

    if int(txn.get("balance_reverted") or 0) == 1:
        lines.extend(
            [
                f"↩️ کسر از حساب: <b>انجام شده</b>",
                f"⏱ زمان کسر: <b>{txn.get('balance_reverted_at') or '-'}</b>",
                f"📝 دلیل کسر: <b>{txn.get('balance_reverted_reason') or '-'}</b>",
            ]
        )

    lines.extend(["", f"<b>موارد مشابه:</b>\n{duplicate_lines(int(txn['id']))}"])
    return "\n".join(lines)


async def show_accounting_queue(message: Message, state: FSMContext) -> None:
    await state.clear()
    txns = list_transactions_by_status(STATUS_APPROVED_PENDING_ACCOUNTING)
    if not txns:
        await message.answer(
            "موردی در صف تایید حسابداری وجود ندارد.",
            reply_markup=accounting_queue_keyboard([]),
        )
        return

    await message.answer(
        "کارت‌هایی که تراکنش در انتظار تایید حسابداری دارند:",
        reply_markup=accounting_queue_keyboard(txns),
    )


async def show_accounting_card_transactions(message: Message, state: FSMContext, card_key: str) -> None:
    await state.clear()
    txns = list_transactions_by_status(STATUS_APPROVED_PENDING_ACCOUNTING)
    group = find_accounting_card_group(txns, card_key)
    if not group:
        await message.answer("برای این کارت دیگر تراکنش تاییدنشده‌ای باقی نمانده است.")
        await show_accounting_queue(message, state)
        return

    lines = [
        "تراکنش‌های در انتظار این کارت:",
        f"🏦 کارت مقصد: <b>{mask_card(group.get('card_number'))}</b>",
        f"📦 تعداد تراکنش: <b>{group['count']}</b>",
        f"💰 جمع مبالغ: <b>{format_price(group.get('total_amount') or 0)} تومان</b>",
    ]
    bank_name = (group.get("bank_name") or "").strip()
    owner_name = (group.get("owner_name") or "").strip()
    if bank_name or owner_name:
        lines.append(f"🏷 کارت/بانک: <b>{bank_name or '-'}</b> | <b>{owner_name or '-'}</b>")

    await message.answer(
        "\n".join(lines),
        parse_mode="HTML",
        reply_markup=accounting_card_transactions_keyboard(card_key, group["transactions"]),
    )


async def show_approved_transactions(message: Message, state: FSMContext) -> None:
    await state.clear()
    txns = list_reversible_transactions(limit=25)
    if not txns:
        await message.answer(
            "فعلاً تراکنش تاییدشده‌ای برای کسر از حساب پیدا نشد.",
            reply_markup=approved_transactions_keyboard([]),
        )
        return

    await message.answer(
        "تراکنش‌های تاییدشده‌ای که هنوز قابل کسر از حساب هستند:",
        reply_markup=approved_transactions_keyboard(txns),
    )


async def show_accounting_review(message: Message, txn_id: int, card_key: Optional[str] = None) -> None:
    txn = get_transaction_with_user(txn_id)
    if not txn or txn.get("status") != STATUS_APPROVED_PENDING_ACCOUNTING:
        await message.answer("این تراکنش دیگر در صف حسابداری نیست.")
        return

    resolved_card_key = card_key or transaction_destination_card_key(txn)
    await send_photo_with_details(
        message,
        photo=txn["photo_id"],
        caption=build_accounting_photo_caption(txn, "بررسی حسابداری تراکنش"),
        details=build_accounting_details(txn, "بررسی حسابداری تراکنش"),
        reply_markup=accounting_review_keyboard(txn_id, resolved_card_key),
    )


async def show_approved_review(message: Message, txn_id: int) -> None:
    txn = get_transaction_with_user(txn_id)
    if not txn or txn.get("status") != STATUS_ACCOUNTING_APPROVED or int(txn.get("balance_reverted") or 0) == 1:
        await message.answer("این تراکنش دیگر برای کسر از حساب در دسترس نیست.")
        return

    await send_photo_with_details(
        message,
        photo=txn["photo_id"],
        caption=build_accounting_photo_caption(txn, "تراکنش تاییدشده"),
        details=build_accounting_details(txn, "تراکنش تاییدشده"),
        reply_markup=approved_review_keyboard(txn_id),
    )


async def show_pending_review_after_edit(message: Message, state: FSMContext, txn_id: int) -> None:
    await state.clear()
    txn = get_transaction_with_user(txn_id)
    await show_accounting_review(
        message,
        txn_id,
        transaction_destination_card_key(txn) if txn else None,
    )


@router.message(F.text == "🏦 تایید حسابداری")
async def accounting_entry(message: Message, state: FSMContext):
    if not is_admin(message.from_user.id):
        return await message.reply("دسترسی نداری.")
    await show_accounting_queue(message, state)


@router.callback_query(F.data == "acct|list")
async def accounting_list_callback(callback: CallbackQuery, state: FSMContext):
    if not is_admin(callback.from_user.id):
        return await callback.answer("دسترسی نداری.", show_alert=True)
    await show_accounting_queue(callback.message, state)
    await callback.answer()


@router.callback_query(F.data.startswith("acct|card|"))
async def accounting_card_callback(callback: CallbackQuery, state: FSMContext):
    if not is_admin(callback.from_user.id):
        return await callback.answer("دسترسی نداری.", show_alert=True)
    card_key = callback.data.split("|", 2)[2]
    await show_accounting_card_transactions(callback.message, state, card_key)
    await callback.answer()


@router.callback_query(F.data == "acct|approved_list")
async def accounting_approved_list_callback(callback: CallbackQuery, state: FSMContext):
    if not is_admin(callback.from_user.id):
        return await callback.answer("دسترسی نداری.", show_alert=True)
    await show_approved_transactions(callback.message, state)
    await callback.answer()


@router.callback_query(F.data == "acct|main_menu")
async def accounting_main_menu(callback: CallbackQuery, state: FSMContext):
    if not is_admin(callback.from_user.id):
        return await callback.answer("دسترسی نداری.", show_alert=True)
    await state.clear()
    await callback.message.answer("بازگشت به منوی اصلی.", reply_markup=admin_main_menu_keyboard())
    await callback.answer()


@router.callback_query(F.data.startswith("acct|open|"))
async def accounting_open(callback: CallbackQuery, state: FSMContext):
    if not is_admin(callback.from_user.id):
        return await callback.answer("دسترسی نداری.", show_alert=True)
    txn_id, card_key = parse_accounting_txn_callback(callback.data)
    await state.clear()
    await show_accounting_review(callback.message, txn_id, card_key)
    await callback.answer()


@router.callback_query(F.data.startswith("acct|approved_open|"))
async def accounting_approved_open(callback: CallbackQuery, state: FSMContext):
    if not is_admin(callback.from_user.id):
        return await callback.answer("دسترسی نداری.", show_alert=True)
    txn_id = int(callback.data.split("|")[2])
    await state.clear()
    await show_approved_review(callback.message, txn_id)
    await callback.answer()


@router.callback_query(F.data.startswith("acct|edit|"))
async def accounting_edit_menu(callback: CallbackQuery, state: FSMContext):
    if not is_admin(callback.from_user.id):
        return await callback.answer("دسترسی نداری.", show_alert=True)

    txn_id, card_key = parse_accounting_txn_callback(callback.data)
    txn = get_transaction_with_user(txn_id)
    if not txn or txn.get("status") != STATUS_APPROVED_PENDING_ACCOUNTING:
        return await callback.answer("این تراکنش دیگر در صف حسابداری نیست.", show_alert=True)

    resolved_card_key = card_key or transaction_destination_card_key(txn)
    await state.clear()
    await callback.message.answer(
        f"ویرایش اطلاعات تراکنش #{txn_id}:",
        reply_markup=accounting_edit_keyboard(txn_id, resolved_card_key),
    )
    await callback.answer()


@router.callback_query(F.data.startswith("acct|edit_last4|"))
async def accounting_edit_last4_start(callback: CallbackQuery, state: FSMContext):
    if not is_admin(callback.from_user.id):
        return await callback.answer("دسترسی نداری.", show_alert=True)

    txn_id, card_key = parse_accounting_txn_callback(callback.data)
    txn = get_transaction_with_user(txn_id)
    if not txn or txn.get("status") != STATUS_APPROVED_PENDING_ACCOUNTING:
        return await callback.answer("این تراکنش دیگر در صف حسابداری نیست.", show_alert=True)

    await state.clear()
    await state.update_data(txn_id=txn_id, card_key=card_key or transaction_destination_card_key(txn))
    await state.set_state(AccountingTxn.waiting_for_source_last4)
    await callback.message.answer(
        "۴ رقم آخر کارت مبدا را بفرست.\nبرای پاک کردن، «ندارم» را بفرست."
    )
    await callback.answer()


@router.callback_query(F.data.startswith("acct|edit_dest|"))
async def accounting_edit_destination_start(callback: CallbackQuery, state: FSMContext):
    if not is_admin(callback.from_user.id):
        return await callback.answer("دسترسی نداری.", show_alert=True)

    txn_id, card_key = parse_accounting_txn_callback(callback.data)
    txn = get_transaction_with_user(txn_id)
    if not txn or txn.get("status") != STATUS_APPROVED_PENDING_ACCOUNTING:
        return await callback.answer("این تراکنش دیگر در صف حسابداری نیست.", show_alert=True)

    resolved_card_key = card_key or transaction_destination_card_key(txn)
    await state.clear()
    await callback.message.answer(
        "کارت مقصد جدید را انتخاب کن:",
        reply_markup=accounting_destination_card_keyboard(txn_id, resolved_card_key),
    )
    await callback.answer()


@router.callback_query(F.data.startswith("acct|dest_card|"))
async def accounting_edit_destination_finish(callback: CallbackQuery, state: FSMContext):
    if not is_admin(callback.from_user.id):
        return await callback.answer("دسترسی نداری.", show_alert=True)

    _, _, txn_id_raw, value = callback.data.split("|", 3)
    txn_id = int(txn_id_raw)
    txn = get_transaction_with_user(txn_id)
    if not txn or txn.get("status") != STATUS_APPROVED_PENDING_ACCOUNTING:
        return await callback.answer("این تراکنش دیگر در صف حسابداری نیست.", show_alert=True)

    if value == "manual":
        await state.clear()
        await state.update_data(txn_id=txn_id, card_key=transaction_destination_card_key(txn))
        await state.set_state(AccountingTxn.waiting_for_destination_card_manual)
        await callback.message.answer(
            "شماره کامل کارت مقصد را بفرست.\nمثال: <code>6037123412341234</code>",
            parse_mode="HTML",
        )
        return await callback.answer()

    if not set_accounting_destination_card_from_card_id(txn_id, int(value)):
        return await callback.answer("تغییر کارت مقصد انجام نشد.", show_alert=True)

    await callback.answer("کارت مقصد ویرایش شد.")
    await show_pending_review_after_edit(callback.message, state, txn_id)


@router.callback_query(F.data.startswith("acct|edit_time|"))
async def accounting_edit_transfer_time_start(callback: CallbackQuery, state: FSMContext):
    if not is_admin(callback.from_user.id):
        return await callback.answer("دسترسی نداری.", show_alert=True)

    txn_id, card_key = parse_accounting_txn_callback(callback.data)
    txn = get_transaction_with_user(txn_id)
    if not txn or txn.get("status") != STATUS_APPROVED_PENDING_ACCOUNTING:
        return await callback.answer("این تراکنش دیگر در صف حسابداری نیست.", show_alert=True)

    await state.clear()
    await state.update_data(txn_id=txn_id, card_key=card_key or transaction_destination_card_key(txn))
    await state.set_state(AccountingTxn.waiting_for_transfer_datetime)
    await callback.message.answer(
        "زمان واریز جدید را بفرست.\n"
        "می‌توانی فقط ساعت، فقط تاریخ، یا هر دو را بفرستی.\n"
        "نمونه‌ها: <code>14:37</code> یا <code>1405/01/16</code> یا <code>1405/01/16 14:37</code>",
        parse_mode="HTML",
    )
    await callback.answer()


@router.callback_query(F.data.startswith("acct|approve|"))
async def accounting_approve(callback: CallbackQuery, state: FSMContext):
    if not is_admin(callback.from_user.id):
        return await callback.answer("دسترسی نداری.", show_alert=True)

    txn_id, card_key = parse_accounting_txn_callback(callback.data)
    approved = confirm_transaction_accounting(txn_id, callback.from_user.id)
    if not approved:
        return await callback.answer("این تراکنش دیگر در صف حسابداری نیست.", show_alert=True)

    await callback.message.answer(
        f"✅ تراکنش #{txn_id} در حسابداری تایید نهایی شد.\n"
        f"💰 مبلغ: {format_price(approved.get('amount') or 0)} تومان"
    )
    await state.clear()
    if card_key:
        await show_accounting_card_transactions(callback.message, state, card_key)
    else:
        await show_accounting_queue(callback.message, state)
    await callback.answer("تایید شد.")


@router.callback_query(F.data.startswith("acct|reject|"))
async def accounting_reject_start(callback: CallbackQuery, state: FSMContext):
    if not is_admin(callback.from_user.id):
        return await callback.answer("دسترسی نداری.", show_alert=True)

    txn_id, card_key = parse_accounting_txn_callback(callback.data)
    txn = get_transaction_with_user(txn_id)
    if not txn or txn.get("status") != STATUS_APPROVED_PENDING_ACCOUNTING:
        return await callback.answer("این تراکنش دیگر در صف حسابداری نیست.", show_alert=True)

    await state.clear()
    await state.update_data(txn_id=txn_id, card_key=card_key or transaction_destination_card_key(txn))
    await state.set_state(AccountingTxn.waiting_for_reject_reason)
    await callback.message.answer(
        f"دلیل عدم تطبیق/رد حسابداری برای تراکنش #{txn_id} را وارد کن:"
    )
    await callback.answer()


@router.callback_query(F.data.startswith("acct|revert|"))
async def accounting_revert_start(callback: CallbackQuery, state: FSMContext):
    if not is_admin(callback.from_user.id):
        return await callback.answer("دسترسی نداری.", show_alert=True)

    txn_id = int(callback.data.split("|")[2])
    txn = get_transaction_with_user(txn_id)
    if not txn or txn.get("status") != STATUS_ACCOUNTING_APPROVED or int(txn.get("balance_reverted") or 0) == 1:
        return await callback.answer("این تراکنش دیگر برای کسر از حساب در دسترس نیست.", show_alert=True)

    await state.clear()
    await state.update_data(txn_id=txn_id)
    await state.set_state(AccountingTxn.waiting_for_revert_reason)
    await callback.message.answer(
        f"دلیل کسر از حساب برای تراکنش #{txn_id} را وارد کن:"
    )
    await callback.answer()


@router.message(AccountingTxn.waiting_for_source_last4)
async def accounting_edit_last4_finish(message: Message, state: FSMContext):
    if not is_admin(message.from_user.id):
        await state.clear()
        return

    data = await state.get_data()
    txn_id = data.get("txn_id")
    raw_text = (message.text or "").strip()
    if not txn_id:
        await state.clear()
        await message.answer("❌ تراکنش انتخاب‌شده پیدا نشد.")
        return

    if raw_text in {"ندارم", "حذف", "پاک"}:
        updated = set_accounting_source_card_last4(int(txn_id), None)
    else:
        last4 = normalize_last4(raw_text)
        if len(last4) != 4:
            await message.answer("❌ فقط ۴ رقم آخر را بفرست یا «ندارم» را وارد کن.")
            return
        updated = set_accounting_source_card_last4(int(txn_id), last4)

    if not updated:
        await state.clear()
        await message.answer("❌ ویرایش ۴ رقم آخر انجام نشد یا تراکنش از صف خارج شده است.")
        return

    await message.answer("✅ ۴ رقم آخر کارت مبدا ویرایش شد.")
    await show_pending_review_after_edit(message, state, int(txn_id))


@router.message(AccountingTxn.waiting_for_destination_card_manual)
async def accounting_edit_destination_manual_finish(message: Message, state: FSMContext):
    if not is_admin(message.from_user.id):
        await state.clear()
        return

    data = await state.get_data()
    txn_id = data.get("txn_id")
    normalized = normalize_card_number(message.text or "")
    if not txn_id:
        await state.clear()
        await message.answer("❌ تراکنش انتخاب‌شده پیدا نشد.")
        return

    if len(normalized) != 16:
        await message.answer("❌ لطفاً شماره کارت ۱۶ رقمی معتبر وارد کن.")
        return

    if not set_accounting_destination_card_manual(int(txn_id), normalized):
        await state.clear()
        await message.answer("❌ تغییر کارت مقصد انجام نشد یا تراکنش از صف خارج شده است.")
        return

    await message.answer("✅ کارت مقصد ویرایش شد.")
    await show_pending_review_after_edit(message, state, int(txn_id))


@router.message(AccountingTxn.waiting_for_transfer_datetime)
async def accounting_edit_transfer_time_finish(message: Message, state: FSMContext):
    if not is_admin(message.from_user.id):
        await state.clear()
        return

    data = await state.get_data()
    txn_id = data.get("txn_id")
    if not txn_id:
        await state.clear()
        await message.answer("❌ تراکنش انتخاب‌شده پیدا نشد.")
        return

    txn = get_transaction_with_user(int(txn_id))
    if not txn or txn.get("status") != STATUS_APPROVED_PENDING_ACCOUNTING:
        await state.clear()
        await message.answer("❌ این تراکنش دیگر در صف حسابداری نیست.")
        return

    parsed = parse_transfer_datetime_input(
        message.text or "",
        txn.get("transfer_date"),
        txn.get("transfer_time"),
    )
    if not parsed:
        await message.answer(
            "❌ زمان واریز معتبر بفرست.\n"
            "نمونه‌ها: <code>14:37</code> یا <code>1405/01/16</code> یا <code>1405/01/16 14:37</code>",
            parse_mode="HTML",
        )
        return

    transfer_date, transfer_time = parsed
    if not set_accounting_transfer_datetime(int(txn_id), transfer_date, transfer_time):
        await state.clear()
        await message.answer("❌ تغییر زمان واریز انجام نشد یا تراکنش از صف خارج شده است.")
        return

    await message.answer("✅ زمان واریز ویرایش شد.")
    await show_pending_review_after_edit(message, state, int(txn_id))


@router.message(AccountingTxn.waiting_for_reject_reason)
async def accounting_reject_finish(message: Message, state: FSMContext):
    if not is_admin(message.from_user.id):
        await state.clear()
        return

    data = await state.get_data()
    txn_id = data.get("txn_id")
    card_key = data.get("card_key")
    reason = (message.text or "").strip()
    if not txn_id or not reason:
        await message.answer("❌ دلیل را وارد کن.")
        return

    rejected = reject_transaction_accounting(int(txn_id), message.from_user.id, reason)
    if not rejected:
        await state.clear()
        await message.answer("❌ این تراکنش دیگر در صف حسابداری نیست.")
        return

    user_balance = get_user_balance(int(rejected["user_id"]))
    await message.answer(
        f"❌ تراکنش #{txn_id} در حسابداری رد شد.\n"
        f"💳 موجودی فعلی کاربر بعد از اصلاح: {format_price(user_balance)} تومان"
    )
    await state.clear()
    if card_key:
        await show_accounting_card_transactions(message, state, str(card_key))
    else:
        await show_accounting_queue(message, state)


@router.message(AccountingTxn.waiting_for_revert_reason)
async def accounting_revert_finish(message: Message, state: FSMContext):
    if not is_admin(message.from_user.id):
        await state.clear()
        return

    data = await state.get_data()
    txn_id = data.get("txn_id")
    reason = (message.text or "").strip()
    if not txn_id or not reason:
        await message.answer("❌ دلیل کسر از حساب را وارد کن.")
        return

    reverted = reverse_transaction_balance(int(txn_id), message.from_user.id, reason)
    if not reverted:
        await state.clear()
        await message.answer("❌ کسر از حساب انجام نشد یا این تراکنش دیگر در دسترس نیست.")
        return

    user_balance = get_user_balance(int(reverted["user_id"]))
    await message.answer(
        f"↩️ مبلغ تراکنش #{txn_id} از حساب کاربر کسر شد.\n"
        f"💰 مبلغ کسرشده: {format_price(reverted.get('amount') or 0)} تومان\n"
        f"💳 موجودی فعلی کاربر: {format_price(user_balance)} تومان"
    )
    await state.clear()
