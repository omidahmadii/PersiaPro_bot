import sqlite3
import io
import datetime
import jdatetime

from aiogram import Router, F
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import Message, CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, FSInputFile, \
    BufferedInputFile

from config import DB_PATH, ADMINS

router = Router()


# --- FSM برای گزارش یوزر خاص ---
class ReportUserTx(StatesGroup):
    waiting_for_userid = State()


# --- کیبورد اصلی گزارشات ---
def reports_keyboard():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📊 سفارشات ماه جاری", callback_data="report:orders_month")],
        [InlineKeyboardButton(text="💰 فروش ماه جاری", callback_data="report:sales_month")],
        [InlineKeyboardButton(text="👤 شروع سرویس‌های این ماه", callback_data="report:users_started")],
        [InlineKeyboardButton(text="⏳ اتمام سرویس‌های این ماه", callback_data="report:users_expired")],
        [InlineKeyboardButton(text="🏦 بیشترین واریزی (ماه)", callback_data="report:top_depositors_month")],
        [InlineKeyboardButton(text="🏦 بیشترین واریزی (کل)", callback_data="report:top_depositors_all")],
        [InlineKeyboardButton(text="📂 تراکنش‌های کاربر خاص", callback_data="report:user_transactions")],
        [InlineKeyboardButton(text="💳 موجودی کاربران", callback_data="report:user_balances")],
    ])


# --- منوی اصلی ---
@router.message(F.text == "📑 گزارشات")
async def show_reports_menu(message: Message):
    if message.from_user.id not in ADMINS:
        return
    await message.answer("📑 یکی از گزارش‌ها رو انتخاب کنید:", reply_markup=reports_keyboard())


# --- هندلر کلی ---
@router.callback_query(F.data.startswith("report:"))
async def report_handler(callback: CallbackQuery, state: FSMContext):
    if callback.from_user.id not in ADMINS:
        return

    action = callback.data.split(":")[1]
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    # تاریخ شروع ماه جاری (میلادی)
    now_jalali = jdatetime.datetime.now()
    month_start_jalali = jdatetime.datetime(now_jalali.year, now_jalali.month, 1)
    month_start_greg = month_start_jalali.togregorian().strftime("%Y-%m-%d")

    if action == "orders_month":
        cursor.execute("SELECT COUNT(*) FROM orders WHERE created_at >= ?", (month_start_greg,))
        count = cursor.fetchone()[0]
        await callback.message.answer(f"📊 تعداد سفارشات در {now_jalali.strftime('%B %Y')} : {count}")

    elif action == "sales_month":
        cursor.execute("SELECT SUM(price) FROM orders WHERE created_at >= ?", (month_start_greg,))
        total = cursor.fetchone()[0] or 0
        await callback.message.answer(f"💰 مجموع فروش {now_jalali.strftime('%B %Y')} : {total:,} تومان")

    elif action == "users_started":
        cursor.execute("SELECT COUNT(*) FROM orders WHERE starts_at >= ?", (month_start_greg,))
        count = cursor.fetchone()[0]
        await callback.message.answer(f"👤 سرویس‌هایی که این ماه شروع شدن: {count}")

    elif action == "users_expired":
        cursor.execute("SELECT COUNT(*) FROM orders WHERE expires_at >= ?", (month_start_greg,))
        count = cursor.fetchone()[0]
        await callback.message.answer(f"⏳ سرویس‌هایی که این ماه تموم میشن: {count}")

    elif action == "top_depositors_month":
        cursor.execute("""
            SELECT u.first_name, u.username, SUM(o.price) as total
            FROM orders o
            JOIN users u ON o.user_id = u.id
            WHERE o.created_at >= ?
            GROUP BY u.id
            ORDER BY total DESC
            LIMIT 10
        """, (month_start_greg,))
        rows = cursor.fetchall()
        text = f"🏦 بیشترین واریزی‌ها در {now_jalali.strftime('%B %Y')}:\n"
        for r in rows:
            text += f"- {r[0]} (@{r[1]}) → {r[2]:,} تومان\n"
        await callback.message.answer(text or "هیچ واریزی در این ماه ثبت نشده.")

    elif action == "top_depositors_all":
        cursor.execute("""
            SELECT u.first_name, u.username, SUM(o.price) as total
            FROM orders o
            JOIN users u ON o.user_id = u.id
            GROUP BY u.id
            ORDER BY total DESC
            LIMIT 25
        """)
        rows = cursor.fetchall()
        text = "🏦 بیشترین واریزی کل:\n"
        for r in rows:
            text += f"- {r[0]} (@{r[1]}) → {r[2]:,} تومان\n"
        await callback.message.answer(text or "هیچ واریزی ثبت نشده.")

    elif action == "user_transactions":
        await state.set_state(ReportUserTx.waiting_for_userid)
        await callback.message.answer("🔍 لطفاً آیدی عددی کاربر رو وارد کنید:")


    elif action == "user_balances":
        cursor.execute("""
            SELECT first_name, username, COALESCE(balance, 0)
            FROM users
            WHERE balance > 0
            ORDER BY balance DESC
        """)
        rows = cursor.fetchall()
        if not rows:
            await callback.message.answer("هیچ کاربری موجودی ندارد.")
        else:
            text = "💳 موجودی کاربران:\n\n"
            text += "نام | یوزرنیم | موجودی\n"
            text += "--- | -------- | --------\n"
            for r in rows:
                name = r[0] or "-"
                username = f"@{r[1]}" if r[1] else "-"
                balance = f"{r[2]:,} تومان"
                text += f"{name} | {username} | {balance}\n"

            await callback.message.answer(f"```\n{text}\n```", parse_mode="Markdown")

    conn.close()
    await callback.answer()


# --- گرفتن تراکنش‌های یک یوزر خاص ---
@router.message(ReportUserTx.waiting_for_userid)
async def process_user_transactions(message: Message, state: FSMContext):
    if message.from_user.id not in ADMINS:
        return

    user_id = message.text.strip()
    if not user_id.isdigit():
        await message.answer("⚠️ لطفاً فقط آیدی عددی وارد کنید.")
        return

    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    cursor.execute("""
        SELECT id, price, status, created_at
        FROM orders
        WHERE user_id = ?
        ORDER BY created_at DESC
        LIMIT 10
    """, (int(user_id),))
    rows = cursor.fetchall()
    conn.close()

    if not rows:
        await message.answer("📂 این کاربر هیچ تراکنشی ندارد.")
    else:
        text = "📂 آخرین تراکنش‌های کاربر:\n"
        for r in rows:
            text += f"#{r[0]} | {r[1]:,} تومان | {r[2]} | {r[3]}\n"
        await message.answer(text)

    await state.clear()
