# handlers/admin/manage_users.py
import sqlite3
from typing import Optional, List, Tuple

from aiogram import Router, F
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import Message, CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup

from config import DB_PATH, ADMINS
from keyboards.main_menu import admin_main_menu_keyboard

router = Router()

# ----------------------
# تنظیمات نمایش (قابل تنظیم)
NAME_COL_WIDTH = 20
USERNAME_COL_WIDTH = 20
ID_COL_WIDTH = 0
BAL_COL_WIDTH = 8
PAGE_SIZE = 10


# ----------------------

# --- بررسی وجود ستون در جدول users ---
def column_exists(conn: sqlite3.Connection, table: str, column: str) -> bool:
    cur = conn.cursor()
    cur.execute("PRAGMA table_info(%s)" % table)
    cols = [r[1] for r in cur.fetchall()]
    return column in cols


# --- helper DB functions ---
def _connect():
    return sqlite3.connect(DB_PATH)


def get_users(offset: int = 0, limit: int = PAGE_SIZE) -> List[Tuple]:
    """
    بازمی‌گرداند لیست کاربران:
    id, first_name, [last_name?], username, role, balance
    """
    conn = _connect()
    has_last = column_exists(conn, "users", "last_name")
    cur = conn.cursor()
    if has_last:
        cur.execute("""
            SELECT id, first_name, last_name, username, role, balance
            FROM users
            ORDER BY CASE WHEN id > 0 THEN 0 ELSE 1 END, id ASC
            LIMIT ? OFFSET ?
        """, (limit, offset))
    else:
        cur.execute("""
            SELECT id, first_name, '' as last_name, username, role, balance
            FROM users
            ORDER BY CASE WHEN id > 0 THEN 0 ELSE 1 END, id ASC
            LIMIT ? OFFSET ?
        """, (limit, offset))
    rows = cur.fetchall()
    conn.close()
    return rows


def search_users(keyword: str, limit: int = 20) -> List[Tuple]:
    conn = _connect()
    has_last = column_exists(conn, "users", "last_name")
    cur = conn.cursor()
    like_kw = f"%{keyword}%"
    if has_last:
        cur.execute("""
            SELECT id, first_name, last_name, username, role, balance
            FROM users
            WHERE CAST(id AS TEXT) LIKE ?
               OR LOWER(first_name) LIKE LOWER(?)
               OR LOWER(last_name) LIKE LOWER(?)
               OR LOWER(username) LIKE LOWER(?)
            ORDER BY id ASC
            LIMIT ?
        """, (like_kw, like_kw, like_kw, like_kw, limit))
    else:
        cur.execute("""
            SELECT id, first_name, '' as last_name, username, role, balance
            FROM users
            WHERE CAST(id AS TEXT) LIKE ?
               OR LOWER(first_name) LIKE LOWER(?)
               OR LOWER(username) LIKE LOWER(?)
            ORDER BY id ASC
            LIMIT ?
        """, (like_kw, like_kw, like_kw, limit))
    rows = cur.fetchall()
    conn.close()
    return rows


def get_user(user_id: int) -> Optional[Tuple]:
    conn = _connect()
    has_last = column_exists(conn, "users", "last_name")
    has_max_accounts = column_exists(conn, "users", "max_active_accounts")
    cur = conn.cursor()

    max_col = "max_active_accounts" if has_max_accounts else "3 as max_active_accounts"

    if has_last:
        cur.execute(f"""
            SELECT id, first_name, last_name, username, role, balance, {max_col}
            FROM users
            WHERE id = ?
        """, (user_id,))
    else:
        cur.execute(f"""
            SELECT id, first_name, '' as last_name, username, role, balance, {max_col}
            FROM users
            WHERE id = ?
        """, (user_id,))

    row = cur.fetchone()
    conn.close()
    return row


def update_user_field(user_id: int, field: str, value) -> bool:
    allowed = ("first_name", "username", "role", "balance")
    if field not in allowed:
        return False
    conn = _connect()
    cur = conn.cursor()
    try:
        cur.execute(f"UPDATE users SET {field} = ? WHERE id = ?", (value, user_id))
        conn.commit()
    except Exception:
        conn.close()
        return False
    conn.close()
    return True


def update_user_role(user_id: int, role_value: str) -> bool:
    if role_value not in ("admin", "user", "agent", "offline"):
        return False
    return update_user_field(user_id, "role", role_value)


def update_user_balance(user_id: int, balance_value: int) -> bool:
    try:
        balance_value = int(balance_value)
    except Exception:
        return False
    return update_user_field(user_id, "balance", balance_value)


def update_user_max_active_accounts(user_id: int, max_value: int) -> bool:
    try:
        max_value = int(max_value)
        if max_value < 0:
            return False
    except Exception:
        return False

    conn = _connect()
    cur = conn.cursor()
    try:
        cur.execute(
            "UPDATE users SET max_active_accounts = ? WHERE id = ?",
            (max_value, user_id)
        )
        conn.commit()
    except Exception:
        conn.close()
        return False

    conn.close()
    return True


# --- FSM states ---
class UserStates(StatesGroup):
    waiting_for_action = State()
    waiting_for_balance = State()
    waiting_for_search = State()
    waiting_for_max_active_accounts = State()


# --- admin check ---
def is_admin(user_id: int) -> bool:
    return str(user_id) in [str(a) for a in ADMINS]


# --- فرمت نمایش (ستونی) ---
def format_name(first: str, last: str, width: int = NAME_COL_WIDTH) -> str:
    full = (first or "") + ((" " + last) if last else "")
    if len(full) > width - 1:
        full = full[:width - 1] + "…"
    return full.ljust(width)


def format_username(username: Optional[str], width: int = USERNAME_COL_WIDTH) -> str:
    uname = (username or "-")
    if len(uname) > width - 1:
        uname = uname[:width - 1] + "…"
    return ("@" + uname).ljust(width + 1)


def format_id(idv: int, width: int = ID_COL_WIDTH) -> str:
    return str(idv).rjust(width)


def format_balance(balance: Optional[int], width: int = BAL_COL_WIDTH) -> str:
    b = str(balance or 0)
    return ("💰" + b).rjust(width + 1)


def format_user_button_text(row: Tuple) -> str:
    """
    row = (id, first_name, last_name, username, role, balance)
    خروجی: ستونی و مرتب
    """
    uid, first, last, username, *_ = row[:5]
    balance = row[5] if len(row) > 5 else 0
    parts = [
        format_name(first or "", last or ""),
        format_username(username),
        format_balance(balance),
    ]
    return " ".join(parts)


# --- ساخت کیبورد صفحه‌بندی و جستجو ---
def build_users_list_keyboard(rows: List[Tuple], page: int) -> InlineKeyboardMarkup:
    keyboard_rows = []
    for r in rows:
        uid = r[0]
        text = format_user_button_text(r)
        keyboard_rows.append([InlineKeyboardButton(text=text, callback_data=f"user_select:{uid}")])

    nav_buttons = []
    if page > 0:
        nav_buttons.append(InlineKeyboardButton(text="⬅️ قبلی", callback_data=f"user_page:{page - 1}"))
    if len(rows) == PAGE_SIZE:
        nav_buttons.append(InlineKeyboardButton(text="➡️ بعدی", callback_data=f"user_page:{page + 1}"))
    if nav_buttons:
        keyboard_rows.append(nav_buttons)

    keyboard_rows.append([InlineKeyboardButton(text="🔍 جستجو کاربر", callback_data="user_search")])
    keyboard_rows.append([InlineKeyboardButton(text="🔙 بازگشت به منوی اصلی", callback_data="user_back_main")])
    return InlineKeyboardMarkup(inline_keyboard=keyboard_rows)


# --- نمایش لیست کاربران (صفحه‌بندی) ---
async def show_users_list_message(msg_or_cb, page: int = 0):
    offset = page * PAGE_SIZE
    users = get_users(offset=offset, limit=PAGE_SIZE)
    if not users:
        text = "🚫 هیچ کاربری یافت نشد."
        if isinstance(msg_or_cb, Message):
            await msg_or_cb.answer(text, reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="🔙 بازگشت به منوی اصلی", callback_data="user_back_main")]
            ]))
        else:
            await msg_or_cb.message.edit_text(text, reply_markup=InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="🔙 بازگشت به منوی اصلی", callback_data="user_back_main")]
            ]))
            await msg_or_cb.answer()
        return

    text = f"📋 لیست کاربران — صفحه {page + 1}:"
    kb = build_users_list_keyboard(users, page)
    if isinstance(msg_or_cb, Message):
        await msg_or_cb.answer(text, reply_markup=kb)
    else:
        try:
            await msg_or_cb.message.edit_text(text, reply_markup=kb)
        except Exception:
            await msg_or_cb.message.answer(text, reply_markup=kb)
        await msg_or_cb.answer()


# --- ورودی منو مدیریت کاربران ---
@router.message(F.text == "👥 مدیریت کاربران")
async def manage_users_entry(msg: Message):
    if not is_admin(msg.from_user.id):
        return await msg.reply("دسترسی نداری 😅")
    await show_users_list_message(msg, page=0)


# --- پیجینگ (callback) ---
@router.callback_query(F.data.startswith("user_page:"))
async def user_page_handler(cb: CallbackQuery):
    if not is_admin(cb.from_user.id):
        return await cb.answer("دسترسی نداری.", show_alert=True)
    page = int(cb.data.split(":")[1])
    await show_users_list_message(cb, page)


# --- بازگشت به منوی اصلی ---
@router.callback_query(F.data == "user_back_main")
async def user_back_main(cb: CallbackQuery, state: FSMContext):
    if not is_admin(cb.from_user.id):
        return await cb.answer("دسترسی نداری.", show_alert=True)
    await state.clear()
    await cb.message.answer("بازگشت به منوی اصلی.", reply_markup=admin_main_menu_keyboard())
    await cb.answer()


# --- شروع جستجو ---
@router.callback_query(F.data == "user_search")
async def user_search_start(cb: CallbackQuery, state: FSMContext):
    if not is_admin(cb.from_user.id):
        return await cb.answer("دسترسی نداری.", show_alert=True)
    await cb.message.answer("🔍 لطفاً آیدی، نام یا یوزرنیم مورد نظر را ارسال کنید:")
    await state.set_state(UserStates.waiting_for_search)
    await cb.answer()


@router.message(UserStates.waiting_for_search)
async def user_search_receive(msg: Message, state: FSMContext):
    if not is_admin(msg.from_user.id):
        await state.clear()
        return await msg.reply("دسترسی نداری 😅")
    keyword = msg.text.strip()
    results = search_users(keyword)
    await state.clear()
    if not results:
        await msg.answer("❌ نتیجه‌ای یافت نشد.")
        return await show_users_list_message(msg, page=0)

    text = f"🔎 نتایج جستجو برای: `{keyword}`"
    kb = build_users_list_keyboard(results, page=0)
    await msg.answer(text, reply_markup=kb)


# --- انتخاب یک کاربر از لیست یا جستجو ---
@router.callback_query(F.data.startswith("user_select:"))
async def user_selected(cb: CallbackQuery, state: FSMContext):
    if not is_admin(cb.from_user.id):
        return await cb.answer("دسترسی نداری.", show_alert=True)

    uid = int(cb.data.split(":")[1])
    row = get_user(uid)
    if not row:
        return await cb.answer("کاربر پیدا نشد.", show_alert=True)

    uid, first, last, username, role, balance, max_active_accounts = row
    display_name = (first or "") + ((" " + last) if last else "")
    caption = (
        f"👤 کاربر #{uid}\n"
        f"نام: {display_name or '-'}\n"
        f"یوزرنیم: @{username or '-'}\n"
        f"بالانس: {balance or 0}\n"
        f"نقش: {role or '-'}\n"
        f"سقف اکانت فعال: {max_active_accounts or 3}"
    )

    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="💰 تغییر بالانس", callback_data=f"user_balance_edit:{uid}")],
        [InlineKeyboardButton(text="🔢 تغییر سقف اکانت", callback_data=f"user_max_accounts_edit:{uid}")],
        [InlineKeyboardButton(text="🎭 تغییر نقش", callback_data=f"user_role_menu:{uid}")],
        [InlineKeyboardButton(text="🔙 بازگشت به لیست", callback_data="user_page:0")]
    ])

    await state.update_data(user_id=uid)
    await cb.message.answer(caption, reply_markup=keyboard)
    await state.set_state(UserStates.waiting_for_action)
    await cb.answer()


# --- شروع ویرایش بالانس ---
@router.callback_query(F.data.startswith("user_balance_edit:"))
async def user_balance_edit_start(cb: CallbackQuery, state: FSMContext):
    if not is_admin(cb.from_user.id):
        return await cb.answer("دسترسی نداری.", show_alert=True)
    uid = int(cb.data.split(":")[1])
    await state.update_data(edit_user_id=uid)
    await cb.message.answer("💰 لطفاً مقدار جدید بالانس را (عدد کامل) ارسال کنید:")
    await state.set_state(UserStates.waiting_for_balance)
    await cb.answer()


@router.message(UserStates.waiting_for_balance)
async def user_receive_new_balance(msg: Message, state: FSMContext):
    if not is_admin(msg.from_user.id):
        await state.clear()
        return await msg.reply("دسترسی نداری 😅")
    data = await state.get_data()
    uid = data.get("edit_user_id")
    if not uid:
        await state.clear()
        return await msg.reply("خطای وضعیت. لطفاً دوباره تلاش کنید.")
    value_text = msg.text.strip()
    try:
        value = int(value_text)
    except Exception:
        return await msg.answer("بالانس باید یک عدد صحیح باشد. لطفاً دوباره عدد بفرستید.")
    ok = update_user_balance(uid, value)
    if ok:
        await msg.answer("✅ بالانس بروزرسانی شد.")
    else:
        await msg.answer("❌ خطا در بروزرسانی بالانس.")
    await state.clear()
    await show_users_list_message(msg, page=0)


# --- شروع ویرایش سقف اکانت فعال ---
@router.callback_query(F.data.startswith("user_max_accounts_edit:"))
async def user_max_accounts_edit_start(cb: CallbackQuery, state: FSMContext):
    if not is_admin(cb.from_user.id):
        return await cb.answer("دسترسی نداری.", show_alert=True)

    uid = int(cb.data.split(":")[1])
    await state.update_data(edit_user_id=uid)

    await cb.message.answer(
        "🔢 لطفاً سقف جدید اکانت فعال این کاربر را ارسال کنید:\n"
        "مثال: 3 یا 10"
    )
    await state.set_state(UserStates.waiting_for_max_active_accounts)
    await cb.answer()


@router.message(UserStates.waiting_for_max_active_accounts)
async def user_receive_new_max_active_accounts(msg: Message, state: FSMContext):
    if not is_admin(msg.from_user.id):
        await state.clear()
        return await msg.reply("دسترسی نداری 😅")

    data = await state.get_data()
    uid = data.get("edit_user_id")
    if not uid:
        await state.clear()
        return await msg.reply("خطای وضعیت. لطفاً دوباره تلاش کنید.")

    value_text = msg.text.strip()
    try:
        value = int(value_text)
        if value < 0:
            return await msg.answer("❌ مقدار سقف باید صفر یا بیشتر باشد.")
    except Exception:
        return await msg.answer("❌ لطفاً یک عدد صحیح معتبر ارسال کنید.")

    ok = update_user_max_active_accounts(uid, value)
    if ok:
        await msg.answer(f"✅ سقف اکانت فعال کاربر #{uid} به {value} تغییر کرد.")
    else:
        await msg.answer("❌ خطا در بروزرسانی سقف اکانت فعال.")

    await state.clear()
    await show_users_list_message(msg, page=0)


# --- منوی تغییر نقش ---
@router.callback_query(F.data.startswith("user_role_menu:"))
async def user_role_menu(cb: CallbackQuery):
    if not is_admin(cb.from_user.id):
        return await cb.answer("دسترسی نداری.", show_alert=True)
    uid = int(cb.data.split(":")[1])
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔐 ادمین", callback_data=f"user_role_set:{uid}:admin")],
        [InlineKeyboardButton(text="👤 یوزر", callback_data=f"user_role_set:{uid}:user")],
        [InlineKeyboardButton(text="🤝 نماینده", callback_data=f"user_role_set:{uid}:agent")],
        [InlineKeyboardButton(text="📴 خارج از ربات", callback_data=f"user_role_set:{uid}:offline")],
        [InlineKeyboardButton(text="🔙 بازگشت", callback_data="user_page:0")]
    ])
    await cb.message.answer("🎯 نقش جدید را انتخاب کنید:", reply_markup=kb)
    await cb.answer()


@router.callback_query(F.data.startswith("user_role_set:"))
async def user_role_set(cb: CallbackQuery):
    if not is_admin(cb.from_user.id):
        return await cb.answer("دسترسی نداری.", show_alert=True)
    parts = cb.data.split(":")
    if len(parts) != 3:
        return await cb.answer("دیتای نامعتبر.", show_alert=True)
    uid = int(parts[1])
    new_role = parts[2]
    if new_role not in ("admin", "user", "agent", "offline"):
        return await cb.answer("نقش نامعتبر.", show_alert=True)
    ok = update_user_role(uid, new_role)
    if ok:
        await cb.answer(f"✅ نقش کاربر #{uid} به `{new_role}` تغییر کرد.")
        await cb.message.answer(f"کاربر #{uid} با موفقیت به نقش `{new_role}` تغییر پیدا کرد.")
    else:
        await cb.answer("❌ خطا در تغییر نقش.", show_alert=True)


# --- فرمان سریع ویرایش بالانس ---
@router.message(F.text.startswith("/edit_user_balance"))
async def quick_edit_balance(msg: Message):
    if not is_admin(msg.from_user.id):
        return await msg.reply("دسترسی نداری 😅")
    parts = msg.text.split()
    if len(parts) < 3:
        return await msg.reply("فرمت: /edit_user_balance <id> <balance>")
    try:
        uid = int(parts[1])
        bal = int(parts[2])
    except Exception:
        return await msg.reply("فرمت صحیح نیست. id و balance باید عدد باشند.")
    ok = update_user_balance(uid, bal)
    if ok:
        await msg.reply("✅ بالانس بروزرسانی شد.")
    else:
        await msg.reply("❌ خطا در بروزرسانی.")


# --- فرمان سریع تغییر نقش ---
@router.message(F.text.startswith("/set_user_role"))
async def quick_set_role(msg: Message):
    if not is_admin(msg.from_user.id):
        return await msg.reply("دسترسی نداری 😅")
    parts = msg.text.split()
    if len(parts) < 3:
        return await msg.reply("فرمت: /set_user_role <id> <admin|user|agent|offline>")
    try:
        uid = int(parts[1])
    except Exception:
        return await msg.reply("id نامعتبر.")
    rolev = parts[2].lower()
    if rolev not in ("admin", "user", "agent", "offline"):
        return await msg.reply("نقش نامعتبر. از admin|user|agent|offline استفاده کن.")
    ok = update_user_role(uid, rolev)
    if ok:
        await msg.reply("✅ نقش بروزرسانی شد.")
    else:
        await msg.reply("❌ خطا در بروزرسانی نقش.")
