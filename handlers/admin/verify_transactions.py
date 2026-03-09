import sqlite3

from aiogram import Router, F, Bot
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import Message, CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup

from config import DB_PATH, ADMINS
from keyboards.main_menu import admin_main_menu_keyboard
from services.db import get_user_balance, get_user_telegram_id_by_txn_id

from typing import Optional

router = Router()

MIN_TOPUP = 1000
MAX_TOPUP = 50000000


class VerifyTxn(StatesGroup):
    waiting_for_amount = State()
    waiting_for_reject_reason = State()


def parse_amount(text: str) -> Optional[int]:
    digits = ''.join(ch for ch in (text or '') if ch.isdigit())
    if not digits:
        return None

    value = int(digits)

    if value < MIN_TOPUP or value > MAX_TOPUP:
        return None

    return value


def get_pending_transactions():
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()

    cur.execute(
        "SELECT id FROM transactions WHERE status = 'pending' ORDER BY created_at ASC"
    )

    rows = cur.fetchall()

    conn.close()

    return rows


def amount_keyboard(txn_id):

    return InlineKeyboardMarkup(
        inline_keyboard=[

            [
                InlineKeyboardButton(
                    text="100K",
                    callback_data=f"amount_100000_{txn_id}"
                ),
                InlineKeyboardButton(
                    text="200K",
                    callback_data=f"amount_200000_{txn_id}"
                ),
                InlineKeyboardButton(
                    text="300K",
                    callback_data=f"amount_300000_{txn_id}"
                ),
                InlineKeyboardButton(
                    text="400K",
                    callback_data=f"amount_400000_{txn_id}"
                ),
            ],
            [
                InlineKeyboardButton(
                    text="500K",
                    callback_data=f"amount_500000_{txn_id}"
                ),
                InlineKeyboardButton(
                    text="600K",
                    callback_data=f"amount_600000_{txn_id}"
                ),
                InlineKeyboardButton(
                    text="700K",
                    callback_data=f"amount_700000_{txn_id}"
                ),
                InlineKeyboardButton(
                    text="800K",
                    callback_data=f"amount_800000_{txn_id}"
                ),
            ],
            [
                InlineKeyboardButton(
                    text="900K",
                    callback_data=f"amount_900000_{txn_id}"
                ),
                InlineKeyboardButton(
                    text="1M",
                    callback_data=f"amount_1000000_{txn_id}"
                ),
                InlineKeyboardButton(
                    text="1.2M",
                    callback_data=f"amount_1200000_{txn_id}"
                ),
                InlineKeyboardButton(
                    text="1.5M",
                    callback_data=f"amount_1500000_{txn_id}"
                ),
            ],
            [
                InlineKeyboardButton(
                    text="❌ رد تراکنش",
                    callback_data=f"reject_{txn_id}"
                )
            ],

            [
                InlineKeyboardButton(
                    text="🔙 بازگشت",
                    callback_data="cancel"
                )
            ]

        ]
    )


@router.message(F.text == "💳 تایید پرداخت ها")
async def start_verification(msg: Message):

    if str(msg.from_user.id) not in [str(admin) for admin in ADMINS]:
        return await msg.reply("دسترسی نداری عزیز 😅")

    txns = get_pending_transactions()

    if not txns:
        return await msg.answer("تراکنش در حال بررسی وجود ندارد.")

    buttons = [
        InlineKeyboardButton(
            text=f"تراکنش شماره {txn[0]}",
            callback_data=f"select_{txn[0]}"
        )
        for txn in txns
    ]

    keyboard = InlineKeyboardMarkup(
        inline_keyboard=[[btn] for btn in buttons]
    )

    await msg.answer(
        "یکی از تراکنش‌های در انتظار را انتخاب کنید:",
        reply_markup=keyboard
    )


@router.callback_query(F.data.startswith("select_"))
async def txn_selected(callback: CallbackQuery, state: FSMContext):

    txn_id = int(callback.data.split("_")[1])

    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()

    cur.execute(
        "SELECT photo_id FROM transactions WHERE id = ? AND status = 'pending'",
        (txn_id,)
    )

    row = cur.fetchone()

    conn.close()

    if not row:
        return await callback.answer(
            "این تراکنش قبلاً بررسی شده.",
            show_alert=True
        )

    photo_id = row[0]

    await state.update_data(txn_id=txn_id)

    await callback.message.answer_photo(
        photo=photo_id,
        caption=f"تراکنش #{txn_id}\n\nمبلغ را انتخاب کنید یا دستی وارد کنید:",
        reply_markup=amount_keyboard(txn_id)
    )

    await state.set_state(VerifyTxn.waiting_for_amount)

    await callback.answer()


@router.callback_query(F.data.startswith("reject_"))
async def reject_transaction(callback: CallbackQuery, state: FSMContext):

    txn_id = int(callback.data.split("_")[1])

    await state.update_data(txn_id=txn_id)

    await callback.message.answer("لطفاً دلیل رد تراکنش را وارد کنید:")

    await state.set_state(VerifyTxn.waiting_for_reject_reason)

    await callback.answer()


@router.message(VerifyTxn.waiting_for_reject_reason)
async def receive_reject_reason(msg: Message, state: FSMContext, bot: Bot):

    data = await state.get_data()

    txn_id = data.get("txn_id")

    reason = msg.text.strip()

    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()

    cur.execute(
        "UPDATE transactions SET status = 'rejected' WHERE id = ?",
        (txn_id,)
    )

    conn.commit()

    conn.close()

    tg_user_id = get_user_telegram_id_by_txn_id(txn_id)

    if tg_user_id:

        await bot.send_message(
            tg_user_id,
            f"❌ پرداخت شما رد شد.\nدلیل: {reason}"
        )

    await msg.answer(f"تراکنش #{txn_id} رد شد.")

    await state.clear()


@router.callback_query(F.data.startswith("amount_"))
async def amount_selected(callback: CallbackQuery, state: FSMContext, bot: Bot):

    parts = callback.data.split("_")

    amount = parse_amount(parts[1])

    txn_id = int(parts[2])

    if amount is None:

        await callback.message.answer(
            f"❌ مبلغ نامعتبر.\nبازه مجاز: {MIN_TOPUP:,} تا {MAX_TOPUP:,} تومان"
        )

        return

    conn = sqlite3.connect(DB_PATH)

    cur = conn.cursor()

    cur.execute(
        "SELECT user_id FROM transactions WHERE id = ?",
        (txn_id,)
    )

    row = cur.fetchone()

    if not row:

        conn.close()

        await callback.message.answer("⛔️ تراکنش پیدا نشد.")

        return

    user_id = row[0]

    cur.execute(
        "UPDATE transactions SET amount = ?, status = 'approved' WHERE id = ? AND status = 'pending'",
        (amount, txn_id)
    )

    if cur.rowcount == 0:

        conn.rollback()

        conn.close()

        await callback.message.answer("⛔️ این تراکنش قبلاً بررسی شده.")

        return

    cur.execute(
        "UPDATE users SET balance = COALESCE(balance,0) + ? WHERE id = ?",
        (amount, user_id)
    )

    conn.commit()

    conn.close()

    user_balance = get_user_balance(user_id)

    await callback.message.answer(
        f"✅ تراکنش #{txn_id} تایید شد\n"
        f"💰 مبلغ: {amount:,} تومان\n"
        f"💳 موجودی کاربر: {user_balance:,} تومان"
    )

    await bot.send_message(
        user_id,
        f"✅ پرداخت شما تایید شد\n"
        f"💰 {amount:,} تومان به کیف پول شما افزوده شد\n"
        f"💳 موجودی فعلی: {user_balance:,} تومان"
    )

    await state.clear()

    await callback.answer()


@router.message(VerifyTxn.waiting_for_amount)
async def amount_typed(message: Message, state: FSMContext, bot: Bot):

    amount = parse_amount(message.text)

    if amount is None:

        return await message.answer(
            f"❌ لطفاً عددی بین {MIN_TOPUP:,} تا {MAX_TOPUP:,} وارد کنید."
        )

    data = await state.get_data()

    txn_id = data.get("txn_id")

    conn = sqlite3.connect(DB_PATH)

    cur = conn.cursor()

    cur.execute(
        "SELECT user_id FROM transactions WHERE id = ?",
        (txn_id,)
    )

    row = cur.fetchone()

    if not row:

        conn.close()

        await message.answer("⛔️ تراکنش پیدا نشد.")

        return

    user_id = row[0]

    cur.execute(
        "UPDATE transactions SET amount = ?, status = 'approved' WHERE id = ? AND status = 'pending'",
        (amount, txn_id)
    )

    if cur.rowcount == 0:

        conn.rollback()

        conn.close()

        await message.answer("⛔️ این تراکنش قبلاً بررسی شده.")

        return

    cur.execute(
        "UPDATE users SET balance = COALESCE(balance,0) + ? WHERE id = ?",
        (amount, user_id)
    )

    conn.commit()

    conn.close()

    user_balance = get_user_balance(user_id)

    await message.answer(
        f"✅ تراکنش #{txn_id} تایید شد\n"
        f"💰 مبلغ: {amount:,} تومان\n"
        f"💳 موجودی کاربر: {user_balance:,} تومان"
    )

    await bot.send_message(
        user_id,
        f"✅ پرداخت شما تایید شد\n"
        f"💰 {amount:,} تومان اضافه شد\n"
        f"💳 موجودی: {user_balance:,} تومان"
    )

    await state.clear()


@router.callback_query(F.data == "cancel")
async def cancel_handler(callback: CallbackQuery, state: FSMContext):

    await state.clear()

    keyboard = admin_main_menu_keyboard()

    await callback.message.answer(
        "بازگشت به منوی اصلی.",
        reply_markup=keyboard
    )

    await callback.answer()