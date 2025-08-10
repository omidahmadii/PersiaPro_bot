import sqlite3

from aiogram import Router, F, Bot
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import Message, CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup

from config import DB_PATH, ADMINS
from keyboards.admin_main_menu import admin_main_menu_keyboard
from services.db import get_user_telegram_id_by_txn_id, get_user_balance

router = Router()

MIN_TOPUP = 1000  # 1,000 تومان
MAX_TOPUP = 50000000  # 50,000,000 تومان (دلخواه)


def parse_amount(text: str) -> int | None:
    # فقط رقم‌ها را نگه می‌داریم (تا اگر کسی با کاما/فاصله نوشت هم اوکی باشد)
    digits = ''.join(ch for ch in (text or '') if ch.isdigit())
    if not digits:
        return None
    value = int(digits)
    if value < MIN_TOPUP or value > MAX_TOPUP:
        return None
    return value


class VerifyTxn(StatesGroup):
    waiting_for_action = State()
    waiting_for_reject_reason = State()
    waiting_for_amount = State()


def get_pending_transactions():
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute("SELECT id FROM transactions WHERE status = 'pending' ORDER BY created_at ASC")
    rows = cur.fetchall()
    conn.close()
    return rows


@router.message(F.text == "💳 تایید پرداخت ها")
async def start_verification(msg: Message):
    if str(msg.from_user.id) not in [str(admin) for admin in ADMINS]:
        return await msg.reply("دسترسی نداری عزیز 😅")

    txns = get_pending_transactions()
    if not txns:
        return await msg.answer("تراکنش در حال بررسی وجود ندارد.")

    buttons = [
        InlineKeyboardButton(text=f"تراکنش شماره {txn[0]}", callback_data=f"select_{txn[0]}")
        for txn in txns
    ]
    keyboard = InlineKeyboardMarkup(inline_keyboard=[buttons[i:i + 1] for i in range(len(buttons))])
    await msg.answer("یکی از تراکنش‌های در انتظار را انتخاب کنید:", reply_markup=keyboard)


@router.callback_query(F.data.startswith("select_"))
async def txn_selected(callback: CallbackQuery, state: FSMContext):
    txn_id = int(callback.data.split("_")[1])
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute("SELECT photo_id FROM transactions WHERE id = ? AND status = 'pending'", (txn_id,))
    row = cur.fetchone()
    conn.close()

    if not row:
        await callback.answer("تراکنش نامعتبر یا قبلا بررسی شده.", show_alert=True)
        return

    photo_id = row[0]
    await state.update_data(txn_id=txn_id)

    await callback.message.answer_photo(photo=photo_id, caption="تصویر فیش تراکنش:")

    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✅ تایید", callback_data="approve")],
        [InlineKeyboardButton(text="❌ رد", callback_data="reject")],
        [InlineKeyboardButton(text="🔙 بازگشت به منوی اصلی", callback_data="cancel")]
    ])
    await callback.message.answer("برای ادامه انتخاب کنید:", reply_markup=keyboard)
    await state.set_state(VerifyTxn.waiting_for_action)
    await callback.answer()


@router.callback_query(VerifyTxn.waiting_for_action, F.data == "approve")
async def approve_handler(callback: CallbackQuery, state: FSMContext):
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="125000", callback_data="amount_125000"),
         InlineKeyboardButton(text="250000", callback_data="amount_250000"),
         InlineKeyboardButton(text="350000", callback_data="amount_350000")],
        [InlineKeyboardButton(text="375000", callback_data="amount_375000"),
         InlineKeyboardButton(text="450000", callback_data="amount_450000"),
         InlineKeyboardButton(text="500000", callback_data="amount_500000")],
        [InlineKeyboardButton(text="🔙 بازگشت به منوی اصلی", callback_data="cancel")]
    ])
    await callback.message.answer("مبلغ تایید شده را انتخاب کنید یا وارد کنید:", reply_markup=keyboard)
    await state.set_state(VerifyTxn.waiting_for_amount)
    await callback.answer()


@router.callback_query(VerifyTxn.waiting_for_action, F.data == "reject")
async def reject_handler(callback: CallbackQuery, state: FSMContext):
    await callback.message.answer("لطفاً دلیل رد تراکنش را وارد کنید:", reply_markup=None)
    await state.set_state(VerifyTxn.waiting_for_reject_reason)
    await callback.answer()


@router.message(VerifyTxn.waiting_for_reject_reason)
async def receive_reject_reason(msg: Message, state: FSMContext, bot: Bot):
    data = await state.get_data()
    txn_id = data.get("txn_id")
    reason = msg.text.strip()

    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute("UPDATE transactions SET status = 'rejected' WHERE id = ?", (txn_id,))
    conn.commit()
    conn.close()

    tg_user_id = get_user_telegram_id_by_txn_id(txn_id)
    if tg_user_id:
        await bot.send_message(tg_user_id, f"❌ پرداخت شما رد شد.\nدلیل: {reason}")

    await msg.answer(f"تراکنش شماره {txn_id} رد شد.\nدلیل: {reason}")
    await state.clear()


@router.callback_query(VerifyTxn.waiting_for_amount, F.data.startswith("amount_"))
async def amount_chosen(callback: CallbackQuery, state: FSMContext, bot: Bot):
    raw = callback.data.split("_")[1]
    amount = parse_amount(raw)
    if amount is None:
        await callback.message.answer(f"❌ مبلغ نامعتبر. بازه مجاز: {MIN_TOPUP:,} تا {MAX_TOPUP:,} تومان.")
        await callback.answer()
        return

    data = await state.get_data()
    txn_id = data.get("txn_id")

    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()

    # گرفتن user_id (که گفتی همون Telegram ID است)
    cur.execute("SELECT user_id FROM transactions WHERE id = ?", (txn_id,))
    row = cur.fetchone()
    if not row:
        await callback.message.answer("⛔️ تراکنش پیدا نشد.")
        await state.clear()
        await callback.answer()
        return
    user_id = row[0]

    # ✅ قفل خوش‌بینانه: فقط اگر هنوز pending است، تأیید کن
    cur.execute(
        "UPDATE transactions SET amount = ?, status = 'approved' WHERE id = ? AND status = 'pending'",
        (amount, txn_id)
    )
    if cur.rowcount == 0:
        # یعنی یکی دیگه یا خود ادمین، همین رو قبلاً تأیید/رد کرده
        conn.rollback()
        conn.close()
        await callback.message.answer("⛔️ این تراکنش قبلاً بررسی شده.")
        await state.clear()
        await callback.answer()
        return

    # افزایش موجودی (COALESCE برای اطمینان از نال نبودن)
    cur.execute("UPDATE users SET balance = COALESCE(balance, 0) + ? WHERE id = ?", (amount, user_id))
    conn.commit()
    conn.close()

    from services.db import get_user_balance  # اگر بالا ایمپورتش کردی، این خط لازم نیست
    user_balance = get_user_balance(user_id)

    await callback.message.answer(
        f"✅ تراکنش #{txn_id} تایید شد و {amount:,} تومان اضافه شد.\n"
        f"💳 مانده فعلی کاربر: {user_balance:,} تومان"
    )
    await bot.send_message(
        user_id,
        f"✅ تراکنش شما تایید شد.\n💰 {amount:,} تومان به کیف‌پول شما افزوده شد.\n"
        f"💳 مانده فعلی: {user_balance:,} تومان"
    )

    await state.clear()
    await callback.answer()


@router.message(VerifyTxn.waiting_for_amount)
async def amount_typed(message: Message, state: FSMContext, bot: Bot):
    amount = parse_amount(message.text)
    if amount is None:
        await message.answer(f"❌ لطفاً یک عدد معتبر بین {MIN_TOPUP:,} و {MAX_TOPUP:,} تومان وارد کنید.")
        return

    data = await state.get_data()
    txn_id = data.get("txn_id")

    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()

    cur.execute("SELECT user_id FROM transactions WHERE id = ?", (txn_id,))
    row = cur.fetchone()
    if not row:
        await message.answer("⛔️ تراکنش پیدا نشد.")
        await state.clear()
        return
    user_id = row[0]

    # ✅ همون قفل خوش‌بینانه اینجا هم
    cur.execute(
        "UPDATE transactions SET amount = ?, status = 'approved' WHERE id = ? AND status = 'pending'",
        (amount, txn_id)
    )
    if cur.rowcount == 0:
        conn.rollback()
        conn.close()
        await message.answer("⛔️ این تراکنش قبلاً بررسی شده.")
        await state.clear()
        return

    cur.execute("UPDATE users SET balance = COALESCE(balance, 0) + ? WHERE id = ?", (amount, user_id))
    conn.commit()
    conn.close()

    from services.db import get_user_balance  # اگر بالا ایمپورتش کردی، این خط لازم نیست
    user_balance = get_user_balance(user_id)

    await message.answer(
        f"✅ تراکنش #{txn_id} تایید شد و {amount:,} تومان اضافه شد.\n"
        f"💳 مانده فعلی کاربر: {user_balance:,} تومان"
    )
    await bot.send_message(
        user_id,
        f"✅ تراکنش شما تایید شد.\n💰 {amount:,} تومان به کیف‌پول شما افزوده شد.\n"
        f"💳 مانده فعلی: {user_balance:,} تومان"
    )

    await state.clear()


@router.callback_query(VerifyTxn.waiting_for_action, F.data == "cancel")
async def cancel_handler(callback: CallbackQuery, state: FSMContext):
    keyboard = admin_main_menu_keyboard()
    await callback.message.answer("بازگشت به منوی اصلی.", reply_markup=keyboard)
    await state.clear()
    await callback.answer()
