# handlers/admin/manage_users.py
from html import escape
import sqlite3
from typing import Optional, List, Tuple, Dict

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
USER_TXN_PAGE_SIZE = 10
USER_ORDER_PAGE_SIZE = 10
USER_ACCOUNT_PAGE_SIZE = 10

EDITABLE_USER_FIELDS = {
    "first_name": "نام",
    "last_name": "نام خانوادگی",
    "username": "یوزرنیم",
    "role": "نقش",
    "balance": "بالانس",
    "max_active_accounts": "سقف اکانت فعال",
    "membership_status": "وضعیت عضویت",
}

ORDER_STATUS_LABELS = {
    "active": "فعال",
    "waiting_for_payment": "در انتظار پرداخت",
    "reserved": "ذخیره",
    "waiting_for_renewal": "در انتظار فعال‌سازی ذخیره",
    "waiting_for_renewal_not_paid": "تمدید در انتظار پرداخت",
    "expired": "منقضی",
    "canceled": "لغوشده",
    "renewed": "تمدیدشده",
    "converted": "تبدیل‌شده",
    "archived": "آرشیوشده",
}

TRANSACTION_STATUS_LABELS = {
    "draft": "پیش‌نویس",
    "pending_admin": "در انتظار تایید ادمین",
    "approved_pending_accounting": "شارژ شد؛ در انتظار حسابداری",
    "accounting_approved": "تایید نهایی",
    "rejected": "رد توسط ادمین",
    "accounting_rejected": "رد توسط حسابداری",
    "balance_reversed": "برگشت وجه",
    "pending": "در انتظار بررسی",
    "approved": "تایید شده",
}


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


def get_user_dict(user_id: int) -> Optional[Dict]:
    conn = _connect()
    conn.row_factory = sqlite3.Row
    has_last = column_exists(conn, "users", "last_name")
    has_max_accounts = column_exists(conn, "users", "max_active_accounts")
    has_membership = column_exists(conn, "users", "membership_status")
    select_parts = [
        "id",
        "first_name",
        "last_name" if has_last else "'' AS last_name",
        "username",
        "role",
        "COALESCE(balance, 0) AS balance",
        "max_active_accounts" if has_max_accounts else "3 AS max_active_accounts",
        "membership_status" if has_membership else "'' AS membership_status",
        "created_at",
    ]
    cur = conn.cursor()
    cur.execute(f"""
        SELECT {", ".join(select_parts)}
        FROM users
        WHERE id = ?
        LIMIT 1
    """, (user_id,))
    row = cur.fetchone()
    conn.close()
    return dict(row) if row else None


def update_user_field(user_id: int, field: str, value) -> bool:
    allowed = ("first_name", "last_name", "username", "role", "balance", "membership_status")
    if field not in allowed:
        return False
    conn = _connect()
    if not column_exists(conn, "users", field):
        conn.close()
        return False
    cur = conn.cursor()
    try:
        cur.execute(f"UPDATE users SET {field} = ? WHERE id = ?", (value, user_id))
        conn.commit()
    except Exception:
        conn.close()
        return False
    conn.close()
    return True


def update_any_user_field(user_id: int, field: str, value: str) -> bool:
    if field == "balance":
        return update_user_balance(user_id, int(value))
    if field == "max_active_accounts":
        return update_user_max_active_accounts(user_id, int(value))
    if field == "role":
        return update_user_role(user_id, value.strip().lower())
    if field == "username":
        value = value.strip().lstrip("@")
    elif field in ("first_name", "last_name", "membership_status"):
        value = value.strip()
    return update_user_field(user_id, field, value)


def count_user_transactions(user_id: int) -> int:
    conn = _connect()
    cur = conn.cursor()
    cur.execute("SELECT COUNT(*) FROM transactions WHERE user_id = ?", (user_id,))
    row = cur.fetchone()
    conn.close()
    return int(row[0] or 0) if row else 0


def get_user_transactions(user_id: int, page: int = 0, limit: int = USER_TXN_PAGE_SIZE) -> List[Dict]:
    conn = _connect()
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()
    cur.execute("""
        SELECT
            id,
            user_id,
            COALESCE(NULLIF(amount_claimed, 0), amount, 0) AS display_amount,
            amount,
            amount_claimed,
            status,
            created_at,
            submitted_at,
            transfer_date,
            transfer_time
        FROM transactions
        WHERE user_id = ?
        ORDER BY COALESCE(submitted_at, created_at) DESC, id DESC
        LIMIT ? OFFSET ?
    """, (user_id, int(limit), int(page) * int(limit)))
    rows = [dict(row) for row in cur.fetchall()]
    conn.close()
    return rows


def get_user_transaction_detail(user_id: int, txn_id: int) -> Optional[Dict]:
    conn = _connect()
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()
    cur.execute("""
        SELECT *
        FROM transactions
        WHERE id = ? AND user_id = ?
        LIMIT 1
    """, (txn_id, user_id))
    row = cur.fetchone()
    conn.close()
    return dict(row) if row else None


def count_user_orders(user_id: int) -> int:
    conn = _connect()
    cur = conn.cursor()
    cur.execute("SELECT COUNT(*) FROM orders WHERE user_id = ?", (user_id,))
    row = cur.fetchone()
    conn.close()
    return int(row[0] or 0) if row else 0


def get_user_orders(user_id: int, page: int = 0, limit: int = USER_ORDER_PAGE_SIZE) -> List[Dict]:
    conn = _connect()
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()
    cur.execute("""
        SELECT
            o.id,
            o.user_id,
            o.username,
            o.status,
            o.price,
            o.created_at,
            o.starts_at,
            o.expires_at,
            o.volume_gb,
            o.extra_volume_gb,
            p.name AS plan_name
        FROM orders o
        LEFT JOIN plans p ON p.id = o.plan_id
        WHERE o.user_id = ?
        ORDER BY o.id DESC
        LIMIT ? OFFSET ?
    """, (user_id, int(limit), int(page) * int(limit)))
    rows = [dict(row) for row in cur.fetchall()]
    conn.close()
    return rows


def get_user_order_detail(user_id: int, order_id: int) -> Optional[Dict]:
    conn = _connect()
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()
    cur.execute("""
        SELECT
            o.*,
            p.name AS plan_name,
            p.group_name,
            p.duration_days,
            p.duration_months,
            p.is_unlimited
        FROM orders o
        LEFT JOIN plans p ON p.id = o.plan_id
        WHERE o.id = ? AND o.user_id = ?
        LIMIT 1
    """, (order_id, user_id))
    row = cur.fetchone()
    conn.close()
    return dict(row) if row else None


def get_user_accounts(user_id: int, page: int = 0, limit: int = USER_ACCOUNT_PAGE_SIZE) -> List[Dict]:
    conn = _connect()
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()
    cur.execute("""
        SELECT
            username,
            COUNT(*) AS total_orders,
            MAX(id) AS latest_order_id,
            MAX(COALESCE(expires_at, '')) AS latest_expires_at,
            (
                SELECT status
                FROM orders os
                WHERE os.user_id = o.user_id AND os.username = o.username
                ORDER BY os.id DESC
                LIMIT 1
            ) AS latest_status
        FROM orders o
        WHERE user_id = ?
          AND username IS NOT NULL
          AND TRIM(CAST(username AS TEXT)) != ''
        GROUP BY username
        ORDER BY MAX(id) DESC
        LIMIT ? OFFSET ?
    """, (user_id, int(limit), int(page) * int(limit)))
    rows = [dict(row) for row in cur.fetchall()]
    conn.close()
    return rows


def count_user_accounts(user_id: int) -> int:
    conn = _connect()
    cur = conn.cursor()
    cur.execute("""
        SELECT COUNT(*)
        FROM (
            SELECT username
            FROM orders
            WHERE user_id = ?
              AND username IS NOT NULL
              AND TRIM(CAST(username AS TEXT)) != ''
            GROUP BY username
        )
    """, (user_id,))
    row = cur.fetchone()
    conn.close()
    return int(row[0] or 0) if row else 0


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
    waiting_for_field_value = State()


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


def format_price(amount) -> str:
    try:
        return f"{int(amount or 0):,}"
    except Exception:
        return str(amount or 0)


def order_status_label(status: Optional[str]) -> str:
    return ORDER_STATUS_LABELS.get(str(status or "").strip(), str(status or "-"))


def transaction_status_label(status: Optional[str]) -> str:
    return TRANSACTION_STATUS_LABELS.get(str(status or "").strip().lower(), str(status or "-"))


def user_caption(user: Dict) -> str:
    display_name = " ".join(
        part for part in [user.get("first_name") or "", user.get("last_name") or ""] if part
    ).strip()
    return (
        f"👤 <b>کاربر #{user['id']}</b>\n"
        f"نام: {escape(display_name or '-')}\n"
        f"یوزرنیم: @{escape(user.get('username') or '-')}\n"
        f"بالانس: {format_price(user.get('balance'))}\n"
        f"نقش: {escape(user.get('role') or '-')}\n"
        f"سقف اکانت فعال: {user.get('max_active_accounts') or 3}\n"
        f"وضعیت عضویت: {escape(user.get('membership_status') or '-')}\n"
        f"تاریخ ثبت: {escape(user.get('created_at') or '-')}"
    )


def user_detail_keyboard(user_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✏️ اصلاح فیلدهای دیتابیس", callback_data=f"user_edit_menu:{user_id}")],
        [
            InlineKeyboardButton(text="🧾 تراکنش‌ها", callback_data=f"user_txns:{user_id}:0"),
            InlineKeyboardButton(text="📦 سفارش‌ها", callback_data=f"user_orders:{user_id}:0"),
        ],
        [InlineKeyboardButton(text="👤 اکانت‌های کاربر", callback_data=f"user_accounts:{user_id}:0")],
        [
            InlineKeyboardButton(text="💰 تغییر بالانس", callback_data=f"user_balance_edit:{user_id}"),
            InlineKeyboardButton(text="🔢 تغییر سقف اکانت", callback_data=f"user_max_accounts_edit:{user_id}"),
        ],
        [InlineKeyboardButton(text="🎭 تغییر نقش", callback_data=f"user_role_menu:{user_id}")],
        [InlineKeyboardButton(text="🔙 بازگشت به لیست", callback_data="user_page:0")],
    ])


def edit_fields_keyboard(user_id: int) -> InlineKeyboardMarkup:
    rows = []
    for field, label in EDITABLE_USER_FIELDS.items():
        rows.append([InlineKeyboardButton(text=f"✏️ {label}", callback_data=f"user_edit_field:{user_id}:{field}")])
    rows.append([InlineKeyboardButton(text="🔙 بازگشت به کاربر", callback_data=f"user_select:{user_id}")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def paged_back_keyboard(prefix: str, user_id: int, page: int, total: int, page_size: int) -> InlineKeyboardMarkup:
    nav = []
    if page > 0:
        nav.append(InlineKeyboardButton(text="⬅️ قبلی", callback_data=f"{prefix}:{user_id}:{page - 1}"))
    if (page + 1) * page_size < total:
        nav.append(InlineKeyboardButton(text="➡️ بعدی", callback_data=f"{prefix}:{user_id}:{page + 1}"))
    rows = []
    if nav:
        rows.append(nav)
    rows.append([InlineKeyboardButton(text="🔙 بازگشت به کاربر", callback_data=f"user_select:{user_id}")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def transactions_keyboard(user_id: int, rows_data: List[Dict], page: int, total: int) -> InlineKeyboardMarkup:
    rows = []
    for txn in rows_data:
        date_text = txn.get("submitted_at") or txn.get("created_at") or "-"
        button_text = f"#{txn['id']} | {format_price(txn.get('display_amount'))} | {date_text}"
        rows.append([InlineKeyboardButton(text=button_text[:64], callback_data=f"user_txn_detail:{user_id}:{txn['id']}:{page}")])
    nav = []
    if page > 0:
        nav.append(InlineKeyboardButton(text="⬅️ قبلی", callback_data=f"user_txns:{user_id}:{page - 1}"))
    if (page + 1) * USER_TXN_PAGE_SIZE < total:
        nav.append(InlineKeyboardButton(text="➡️ بعدی", callback_data=f"user_txns:{user_id}:{page + 1}"))
    if nav:
        rows.append(nav)
    rows.append([InlineKeyboardButton(text="🔙 بازگشت به کاربر", callback_data=f"user_select:{user_id}")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def orders_keyboard(user_id: int, rows_data: List[Dict], page: int, total: int) -> InlineKeyboardMarkup:
    rows = []
    for order in rows_data:
        button_text = (
            f"#{order['id']} | {order.get('username') or '-'} | "
            f"{order_status_label(order.get('status'))} | {order.get('expires_at') or '-'}"
        )
        rows.append([InlineKeyboardButton(text=button_text[:64], callback_data=f"user_order_detail:{user_id}:{order['id']}:{page}")])
    nav = []
    if page > 0:
        nav.append(InlineKeyboardButton(text="⬅️ قبلی", callback_data=f"user_orders:{user_id}:{page - 1}"))
    if (page + 1) * USER_ORDER_PAGE_SIZE < total:
        nav.append(InlineKeyboardButton(text="➡️ بعدی", callback_data=f"user_orders:{user_id}:{page + 1}"))
    if nav:
        rows.append(nav)
    rows.append([InlineKeyboardButton(text="🔙 بازگشت به کاربر", callback_data=f"user_select:{user_id}")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def accounts_keyboard(user_id: int, page: int, total: int) -> InlineKeyboardMarkup:
    return paged_back_keyboard("user_accounts", user_id, page, total, USER_ACCOUNT_PAGE_SIZE)


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
    user = get_user_dict(uid)
    if not user:
        return await cb.answer("کاربر پیدا نشد.", show_alert=True)

    await state.update_data(user_id=uid)
    await cb.message.answer(user_caption(user), parse_mode="HTML", reply_markup=user_detail_keyboard(uid))
    await state.set_state(UserStates.waiting_for_action)
    await cb.answer()


@router.callback_query(F.data.startswith("user_edit_menu:"))
async def user_edit_menu(cb: CallbackQuery):
    if not is_admin(cb.from_user.id):
        return await cb.answer("دسترسی نداری.", show_alert=True)
    uid = int(cb.data.split(":")[1])
    if not get_user_dict(uid):
        return await cb.answer("کاربر پیدا نشد.", show_alert=True)
    await cb.message.answer("کدام فیلد کاربر را می‌خواهی اصلاح کنی؟", reply_markup=edit_fields_keyboard(uid))
    await cb.answer()


@router.callback_query(F.data.startswith("user_edit_field:"))
async def user_edit_field_start(cb: CallbackQuery, state: FSMContext):
    if not is_admin(cb.from_user.id):
        return await cb.answer("دسترسی نداری.", show_alert=True)
    _, uid_text, field = cb.data.split(":", 2)
    uid = int(uid_text)
    if field not in EDITABLE_USER_FIELDS:
        return await cb.answer("فیلد نامعتبر است.", show_alert=True)
    user = get_user_dict(uid)
    if not user:
        return await cb.answer("کاربر پیدا نشد.", show_alert=True)
    current_value = user.get(field)
    await state.update_data(edit_user_id=uid, edit_field=field)
    await state.set_state(UserStates.waiting_for_field_value)
    await cb.message.answer(
        f"مقدار جدید برای «{EDITABLE_USER_FIELDS[field]}» را بفرست.\n"
        f"مقدار فعلی: <code>{escape(str(current_value if current_value is not None else '-'))}</code>\n\n"
        "برای خالی کردن فیلدهای متنی، فقط <code>-</code> بفرست.",
        parse_mode="HTML",
    )
    await cb.answer()


@router.message(UserStates.waiting_for_field_value)
async def user_receive_field_value(msg: Message, state: FSMContext):
    if not is_admin(msg.from_user.id):
        await state.clear()
        return await msg.reply("دسترسی نداری 😅")

    data = await state.get_data()
    uid = data.get("edit_user_id")
    field = data.get("edit_field")
    if not uid or field not in EDITABLE_USER_FIELDS:
        await state.clear()
        return await msg.reply("خطای وضعیت. لطفاً دوباره تلاش کنید.")

    value = (msg.text or "").strip()
    if value == "-" and field in ("first_name", "last_name", "username", "membership_status"):
        value = ""

    try:
        ok = update_any_user_field(int(uid), field, value)
    except Exception:
        ok = False

    await state.clear()
    if not ok:
        return await msg.answer(
            "❌ مقدار واردشده معتبر نبود یا فیلد در دیتابیس وجود ندارد.",
            reply_markup=edit_fields_keyboard(int(uid)),
        )

    user = get_user_dict(int(uid))
    await msg.answer("✅ فیلد کاربر بروزرسانی شد.")
    if user:
        await msg.answer(user_caption(user), parse_mode="HTML", reply_markup=user_detail_keyboard(int(uid)))


@router.callback_query(F.data.startswith("user_txns:"))
async def user_transactions_list(cb: CallbackQuery):
    if not is_admin(cb.from_user.id):
        return await cb.answer("دسترسی نداری.", show_alert=True)
    _, uid_text, page_text = cb.data.split(":")
    uid = int(uid_text)
    page = max(0, int(page_text))
    total = count_user_transactions(uid)
    rows = get_user_transactions(uid, page=page)
    if not rows:
        await cb.message.answer("برای این کاربر تراکنشی ثبت نشده.", reply_markup=paged_back_keyboard("user_txns", uid, page, total, USER_TXN_PAGE_SIZE))
        return await cb.answer()
    await cb.message.answer(
        f"🧾 تراکنش‌های کاربر #{uid} — صفحه {page + 1}\n"
        "شماره | مبلغ | تاریخ",
        reply_markup=transactions_keyboard(uid, rows, page, total),
    )
    await cb.answer()


@router.callback_query(F.data.startswith("user_txn_detail:"))
async def user_transaction_detail(cb: CallbackQuery):
    if not is_admin(cb.from_user.id):
        return await cb.answer("دسترسی نداری.", show_alert=True)
    _, uid_text, txn_text, page_text = cb.data.split(":")
    uid = int(uid_text)
    txn_id = int(txn_text)
    page = int(page_text)
    txn = get_user_transaction_detail(uid, txn_id)
    if not txn:
        return await cb.answer("تراکنش پیدا نشد.", show_alert=True)
    amount_display = txn.get("amount_claimed") or txn.get("amount") or 0
    text = (
        f"🧾 <b>جزئیات تراکنش #{txn['id']}</b>\n\n"
        f"👤 کاربر: <code>{uid}</code>\n"
        f"💰 مبلغ: <b>{format_price(amount_display)} تومان</b>\n"
        f"📍 وضعیت: {escape(transaction_status_label(txn.get('status')))}\n"
        f"🕒 ثبت: <code>{escape(str(txn.get('created_at') or '-'))}</code>\n"
        f"📨 ارسال: <code>{escape(str(txn.get('submitted_at') or '-'))}</code>\n"
        f"📅 زمان واریز: <code>{escape(str(txn.get('transfer_date') or '-'))} {escape(str(txn.get('transfer_time') or '-'))}</code>\n"
        f"🏦 کارت مقصد: <code>{escape(str(txn.get('destination_card_number') or '-'))}</code>\n"
        f"🏷 صاحب/بانک مقصد: {escape(str(txn.get('destination_card_owner') or '-'))} | {escape(str(txn.get('destination_bank_name') or '-'))}\n"
        f"💳 ۴ رقم کارت مبدا: <code>{escape(str(txn.get('source_card_last4') or '-'))}</code>\n"
        f"📝 یادداشت ادمین: {escape(str(txn.get('admin_note') or '-'))}\n"
        f"🧮 یادداشت حسابداری: {escape(str(txn.get('accounting_note') or '-'))}"
    )
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔙 بازگشت به تراکنش‌ها", callback_data=f"user_txns:{uid}:{page}")],
        [InlineKeyboardButton(text="🔙 بازگشت به کاربر", callback_data=f"user_select:{uid}")],
    ])
    await cb.message.answer(text, parse_mode="HTML", reply_markup=kb)
    await cb.answer()


@router.callback_query(F.data.startswith("user_orders:"))
async def user_orders_list(cb: CallbackQuery):
    if not is_admin(cb.from_user.id):
        return await cb.answer("دسترسی نداری.", show_alert=True)
    _, uid_text, page_text = cb.data.split(":")
    uid = int(uid_text)
    page = max(0, int(page_text))
    total = count_user_orders(uid)
    rows = get_user_orders(uid, page=page)
    if not rows:
        await cb.message.answer("برای این کاربر سفارشی ثبت نشده.", reply_markup=paged_back_keyboard("user_orders", uid, page, total, USER_ORDER_PAGE_SIZE))
        return await cb.answer()
    await cb.message.answer(
        f"📦 سفارش‌های کاربر #{uid} — صفحه {page + 1}:",
        reply_markup=orders_keyboard(uid, rows, page, total),
    )
    await cb.answer()


@router.callback_query(F.data.startswith("user_order_detail:"))
async def user_order_detail(cb: CallbackQuery):
    if not is_admin(cb.from_user.id):
        return await cb.answer("دسترسی نداری.", show_alert=True)
    _, uid_text, order_text, page_text = cb.data.split(":")
    uid = int(uid_text)
    order_id = int(order_text)
    page = int(page_text)
    order = get_user_order_detail(uid, order_id)
    if not order:
        return await cb.answer("سفارش پیدا نشد.", show_alert=True)
    text = (
        f"📦 <b>جزئیات سفارش #{order['id']}</b>\n\n"
        f"👤 کاربر: <code>{uid}</code>\n"
        f"🆔 اکانت: <code>{escape(str(order.get('username') or '-'))}</code>\n"
        f"📦 پلن: {escape(str(order.get('plan_name') or '-'))}\n"
        f"💰 مبلغ: {format_price(order.get('price'))} تومان\n"
        f"📊 حجم: {order.get('volume_gb') or 0} گیگ + {order.get('extra_volume_gb') or 0} گیگ اضافه\n"
        f"📍 وضعیت: {order_status_label(order.get('status'))}\n"
        f"🕒 ثبت: <code>{escape(str(order.get('created_at') or '-'))}</code>\n"
        f"🚀 شروع: <code>{escape(str(order.get('starts_at') or '-'))}</code>\n"
        f"⏳ پایان: <code>{escape(str(order.get('expires_at') or '-'))}</code>\n"
        f"🔁 تمدید سفارش: <code>{escape(str(order.get('is_renewal_of_order') or '-'))}</code>"
    )
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🔙 بازگشت به سفارش‌ها", callback_data=f"user_orders:{uid}:{page}")],
        [InlineKeyboardButton(text="🔙 بازگشت به کاربر", callback_data=f"user_select:{uid}")],
    ])
    await cb.message.answer(text, parse_mode="HTML", reply_markup=kb)
    await cb.answer()


@router.callback_query(F.data.startswith("user_accounts:"))
async def user_accounts_list(cb: CallbackQuery):
    if not is_admin(cb.from_user.id):
        return await cb.answer("دسترسی نداری.", show_alert=True)
    _, uid_text, page_text = cb.data.split(":")
    uid = int(uid_text)
    page = max(0, int(page_text))
    total = count_user_accounts(uid)
    rows = get_user_accounts(uid, page=page)
    if not rows:
        await cb.message.answer("برای این کاربر اکانتی در سفارش‌ها پیدا نشد.", reply_markup=accounts_keyboard(uid, page, total))
        return await cb.answer()

    lines = [f"👤 اکانت‌های کاربر #{uid} — صفحه {page + 1}:"]
    for account in rows:
        lines.append(
            f"\n• <code>{escape(str(account.get('username') or '-'))}</code>\n"
            f"  سفارش‌ها: {account.get('total_orders') or 0} | "
            f"آخرین وضعیت: {order_status_label(account.get('latest_status'))} | "
            f"پایان: <code>{escape(str(account.get('latest_expires_at') or '-'))}</code>"
        )
    await cb.message.answer("\n".join(lines), parse_mode="HTML", reply_markup=accounts_keyboard(uid, page, total))
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
    user = get_user_dict(uid)
    if user:
        await msg.answer(user_caption(user), parse_mode="HTML", reply_markup=user_detail_keyboard(uid))
    else:
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
    user = get_user_dict(uid)
    if user:
        await msg.answer(user_caption(user), parse_mode="HTML", reply_markup=user_detail_keyboard(uid))
    else:
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
        [InlineKeyboardButton(text="🔙 بازگشت", callback_data=f"user_select:{uid}")]
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
        user = get_user_dict(uid)
        if user:
            await cb.message.answer(user_caption(user), parse_mode="HTML", reply_markup=user_detail_keyboard(uid))
        else:
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
