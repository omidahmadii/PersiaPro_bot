import sqlite3
from html import escape
from typing import Iterable, Optional, Tuple, Union

import jdatetime
from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message

from config import (
    ADMINS,
    APP_ENV,
    DB_PATH,
    ENABLE_SCHEDULER,
    SCHEDULER_ACTIVATE_RESERVED,
    SCHEDULER_ACTIVATE_WAITING_FOR_PAYMENT,
    SCHEDULER_AUTO_RENEW,
    SCHEDULER_CANCEL_NOT_PAID,
    SCHEDULER_EXPIRE_ORDERS,
    SCHEDULER_LIMIT_SPEED,
    SCHEDULER_MEMBERSHIP,
    SCHEDULER_NOTIFIER,
    SCHEDULER_UPDATE_ORDER_TIMES,
    SCHEDULER_USAGE_LOGGER,
)
from services.payment_workflow import (
    STATUS_ACCOUNTING_APPROVED,
    STATUS_ACCOUNTING_REJECTED,
    STATUS_APPROVED_PENDING_ACCOUNTING,
    STATUS_LEGACY_APPROVED,
    STATUS_LEGACY_PENDING,
    STATUS_PENDING_ADMIN,
    get_transaction_status_label,
)

router = Router()


class ReportUserTx(StatesGroup):
    waiting_for_userid = State()


def is_admin(user_id: int) -> bool:
    return user_id in ADMINS


def _connect() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def _fmt_num(value) -> str:
    try:
        return f"{int(value or 0):,}"
    except Exception:
        return str(value or 0)


def _compact_text(value: Optional[str], limit: int = 70) -> str:
    text = (value or "").replace("\n", " ").strip()
    if len(text) <= limit:
        return escape(text or "-")
    return escape(text[: limit - 1] + "…")


def _build_user_label(row: Optional[Union[sqlite3.Row, Tuple]]) -> str:
    if not row:
        return "-"

    if isinstance(row, sqlite3.Row):
        first_name = row["first_name"] if "first_name" in row.keys() else None
        last_name = row["last_name"] if "last_name" in row.keys() else None
        username = row["username"] if "username" in row.keys() else None
        user_id = row["id"] if "id" in row.keys() else None
    else:
        first_name = row[0] if len(row) > 0 else None
        last_name = row[1] if len(row) > 1 else None
        username = row[2] if len(row) > 2 else None
        user_id = row[3] if len(row) > 3 else None

    name = " ".join(part for part in [first_name or "", last_name or ""] if part).strip()
    if name and username:
        return escape(f"{name} (@{username})")
    if name:
        return escape(name)
    if username:
        return escape(f"@{username}")
    if user_id is not None:
        return escape(f"کاربر {user_id}")
    return "-"


def _render_ranked_rows(rows: Iterable[sqlite3.Row], value_formatter=None, empty_text: str = "اطلاعاتی ثبت نشده.") -> str:
    rows = list(rows)
    if not rows:
        return empty_text

    lines = []
    for index, row in enumerate(rows, start=1):
        label = _build_user_label(row)
        value = row["total"]
        rendered_value = value_formatter(value) if value_formatter else str(value)
        lines.append(f"{index}. {label} — {rendered_value}")
    return "\n".join(lines)


def _current_jalali_month_bounds():
    now_j = jdatetime.datetime.now()
    month_start_j = jdatetime.datetime(now_j.year, now_j.month, 1)
    if now_j.month == 12:
        next_month_start_j = jdatetime.datetime(now_j.year + 1, 1, 1)
    else:
        next_month_start_j = jdatetime.datetime(now_j.year, now_j.month + 1, 1)
    return now_j, month_start_j, next_month_start_j


def _current_month_filters():
    now_j, month_start_j, next_month_start_j = _current_jalali_month_bounds()
    greg_start = month_start_j.togregorian().strftime("%Y-%m-%d")
    greg_end = next_month_start_j.togregorian().strftime("%Y-%m-%d")
    jalali_start = month_start_j.strftime("%Y-%m-%d %H:%M")
    jalali_end = next_month_start_j.strftime("%Y-%m-%d %H:%M")
    period_label = f"{month_start_j.year}/{month_start_j.month:02d}"
    return {
        "now_j": now_j,
        "period_label": period_label,
        "greg_start": greg_start,
        "greg_end": greg_end,
        "jalali_start": jalali_start,
        "jalali_end": jalali_end,
    }


def reports_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="🧪 وضعیت محیط", callback_data="report:env_status"),
                InlineKeyboardButton(text="📊 داشبورد ماه", callback_data="report:dashboard_month"),
            ],
            [
                InlineKeyboardButton(text="📦 سفارش‌ها", callback_data="report:orders_overview"),
                InlineKeyboardButton(text="💰 مالی و کیف پول", callback_data="report:wallet_overview"),
            ],
            [
                InlineKeyboardButton(text="📈 پلن‌های پرفروش", callback_data="report:top_plans"),
                InlineKeyboardButton(text="👥 کاربران", callback_data="report:users_overview"),
            ],
            [
                InlineKeyboardButton(text="⏳ انقضا و تمدید", callback_data="report:expiring_overview"),
                InlineKeyboardButton(text="📬 بازخوردها", callback_data="report:feedback_overview"),
            ],
            [
                InlineKeyboardButton(text="🔎 گزارش کاربر", callback_data="report:user_transactions"),
                InlineKeyboardButton(text="💳 موجودی کاربران", callback_data="report:user_balances"),
            ],
        ]
    )


def build_env_status_report() -> str:
    flags = [
        ("Scheduler", ENABLE_SCHEDULER),
        ("Update order times", SCHEDULER_UPDATE_ORDER_TIMES),
        ("Expire orders", SCHEDULER_EXPIRE_ORDERS),
        ("Activate reserved", SCHEDULER_ACTIVATE_RESERVED),
        ("Notifier", SCHEDULER_NOTIFIER),
        ("Usage logger", SCHEDULER_USAGE_LOGGER),
        ("Membership", SCHEDULER_MEMBERSHIP),
        ("Limit speed", SCHEDULER_LIMIT_SPEED),
        ("Activate waiting payment", SCHEDULER_ACTIVATE_WAITING_FOR_PAYMENT),
        ("Cancel not paid", SCHEDULER_CANCEL_NOT_PAID),
        ("Auto renew", SCHEDULER_AUTO_RENEW),
    ]
    lines = [
        "🧪 وضعیت محیط اجرا",
        "",
        f"محیط فعلی: <b>{APP_ENV}</b>",
        "",
        "فلگ‌های زمان‌بندی:",
    ]
    for label, enabled in flags:
        lines.append(f"• {label}: {'✅ فعال' if enabled else '🚫 غیرفعال'}")
    lines.append("")
    lines.append("در محیط غیرپروداکشن، پیشنهاد امن این است که خود Scheduler یا jobهای حساس خاموش بمانند.")
    return "\n".join(lines)


def build_dashboard_month_report(conn: sqlite3.Connection) -> str:
    cur = conn.cursor()
    filters = _current_month_filters()

    cur.execute(
        """
        SELECT COUNT(*) AS cnt, COALESCE(SUM(price), 0) AS total
        FROM orders
        WHERE substr(created_at, 1, 10) >= ? AND substr(created_at, 1, 10) < ?
        """,
        (filters["greg_start"], filters["greg_end"]),
    )
    orders_row = cur.fetchone()

    cur.execute(
        """
        SELECT COUNT(*) AS cnt, COALESCE(SUM(amount), 0) AS total
        FROM transactions
        WHERE status IN (?, ?, ?, ?)
          AND substr(COALESCE(submitted_at, created_at), 1, 10) >= ?
          AND substr(COALESCE(submitted_at, created_at), 1, 10) < ?
        """,
        (
            STATUS_APPROVED_PENDING_ACCOUNTING,
            STATUS_ACCOUNTING_APPROVED,
            STATUS_ACCOUNTING_REJECTED,
            STATUS_LEGACY_APPROVED,
            filters["greg_start"],
            filters["greg_end"],
        ),
    )
    initially_approved_tx_row = cur.fetchone()

    cur.execute(
        """
        SELECT COUNT(*) AS cnt, COALESCE(SUM(amount), 0) AS total
        FROM transactions
        WHERE status IN (?, ?)
          AND substr(COALESCE(submitted_at, created_at), 1, 10) >= ?
          AND substr(COALESCE(submitted_at, created_at), 1, 10) < ?
        """,
        (
            STATUS_ACCOUNTING_APPROVED,
            STATUS_LEGACY_APPROVED,
            filters["greg_start"],
            filters["greg_end"],
        ),
    )
    accounting_approved_tx_row = cur.fetchone()

    cur.execute(
        """
        SELECT COUNT(*) AS cnt, COALESCE(SUM(amount), 0) AS total
        FROM transactions
        WHERE status = ?
          AND substr(COALESCE(submitted_at, created_at), 1, 10) >= ?
          AND substr(COALESCE(submitted_at, created_at), 1, 10) < ?
        """,
        (STATUS_APPROVED_PENDING_ACCOUNTING, filters["greg_start"], filters["greg_end"]),
    )
    pending_accounting_tx_row = cur.fetchone()

    cur.execute(
        """
        SELECT COUNT(*) AS cnt
        FROM users
        WHERE substr(created_at, 1, 10) >= ? AND substr(created_at, 1, 10) < ?
        """,
        (filters["greg_start"], filters["greg_end"]),
    )
    new_users = cur.fetchone()["cnt"]

    cur.execute(
        """
        SELECT COUNT(*) AS cnt
        FROM orders
        WHERE starts_at >= ? AND starts_at < ?
        """,
        (filters["jalali_start"], filters["jalali_end"]),
    )
    month_starts = cur.fetchone()["cnt"]

    cur.execute(
        """
        SELECT COUNT(*) AS cnt
        FROM orders
        WHERE expires_at >= ? AND expires_at < ?
        """,
        (filters["jalali_start"], filters["jalali_end"]),
    )
    month_expires = cur.fetchone()["cnt"]

    cur.execute("SELECT COUNT(*) AS cnt FROM orders WHERE status = 'active'")
    active_orders = cur.fetchone()["cnt"]

    cur.execute("SELECT COUNT(*) AS cnt FROM orders WHERE status = 'waiting_for_renewal'")
    waiting_for_renewal = cur.fetchone()["cnt"]

    cur.execute("SELECT COUNT(*) AS cnt FROM orders WHERE status = 'waiting_for_payment'")
    waiting_for_payment = cur.fetchone()["cnt"]

    cur.execute(
        "SELECT COUNT(*) AS cnt FROM transactions WHERE status IN (?, ?)",
        (STATUS_PENDING_ADMIN, STATUS_LEGACY_PENDING),
    )
    pending_transactions = cur.fetchone()["cnt"]

    cur.execute("SELECT COUNT(*) AS cnt, COALESCE(SUM(balance), 0) AS total FROM users WHERE balance > 0")
    wallet_row = cur.fetchone()

    return "\n".join(
        [
            f"📊 داشبورد ماه {filters['period_label']}",
            "",
            f"سفارش‌های ثبت‌شده: <b>{_fmt_num(orders_row['cnt'])}</b>",
            f"مجموع مبلغ سفارش‌ها: <b>{_fmt_num(orders_row['total'])}</b> تومان",
            f"شارژ اولیه این ماه: <b>{_fmt_num(initially_approved_tx_row['cnt'])}</b>",
            f"جمع شارژ اولیه این ماه: <b>{_fmt_num(initially_approved_tx_row['total'])}</b> تومان",
            f"تایید نهایی حسابداری این ماه: <b>{_fmt_num(accounting_approved_tx_row['cnt'])}</b>",
            f"جمع تایید نهایی حسابداری این ماه: <b>{_fmt_num(accounting_approved_tx_row['total'])}</b> تومان",
            f"در انتظار تایید حسابداری این ماه: <b>{_fmt_num(pending_accounting_tx_row['cnt'])}</b>",
            f"جمع مبالغ در انتظار حسابداری: <b>{_fmt_num(pending_accounting_tx_row['total'])}</b> تومان",
            f"کاربران جدید این ماه: <b>{_fmt_num(new_users)}</b>",
            "",
            f"شروع سرویس در این ماه: <b>{_fmt_num(month_starts)}</b>",
            f"اتمام سرویس در این ماه: <b>{_fmt_num(month_expires)}</b>",
            "",
            f"سرویس فعال فعلی: <b>{_fmt_num(active_orders)}</b>",
            f"در انتظار تمدید: <b>{_fmt_num(waiting_for_renewal)}</b>",
            f"در انتظار پرداخت: <b>{_fmt_num(waiting_for_payment)}</b>",
            f"تراکنش در انتظار بررسی اولیه: <b>{_fmt_num(pending_transactions)}</b>",
            "",
            f"کاربران دارای موجودی: <b>{_fmt_num(wallet_row['cnt'])}</b>",
            f"جمع موجودی کیف پول کاربران: <b>{_fmt_num(wallet_row['total'])}</b> تومان",
        ]
    )


def build_orders_overview_report(conn: sqlite3.Connection) -> str:
    cur = conn.cursor()
    filters = _current_month_filters()

    cur.execute(
        """
        SELECT COALESCE(status, 'unknown') AS status, COUNT(*) AS cnt, COALESCE(SUM(price), 0) AS total
        FROM orders
        GROUP BY COALESCE(status, 'unknown')
        ORDER BY cnt DESC, total DESC
        """
    )
    all_time_rows = cur.fetchall()

    cur.execute(
        """
        SELECT COALESCE(status, 'unknown') AS status, COUNT(*) AS cnt, COALESCE(SUM(price), 0) AS total
        FROM orders
        WHERE substr(created_at, 1, 10) >= ? AND substr(created_at, 1, 10) < ?
        GROUP BY COALESCE(status, 'unknown')
        ORDER BY cnt DESC, total DESC
        """,
        (filters["greg_start"], filters["greg_end"]),
    )
    month_rows = cur.fetchall()

    lines = [
        "📦 نمای کلی سفارش‌ها",
        "",
        "وضعیت کل سفارش‌ها:",
    ]
    if all_time_rows:
        for row in all_time_rows:
            lines.append(f"• {row['status']}: {row['cnt']} سفارش | {_fmt_num(row['total'])} تومان")
    else:
        lines.append("• داده‌ای ثبت نشده.")

    lines.extend(["", f"وضعیت سفارش‌های ساخته‌شده در ماه {filters['period_label']}:"])
    if month_rows:
        for row in month_rows:
            lines.append(f"• {row['status']}: {row['cnt']} سفارش | {_fmt_num(row['total'])} تومان")
    else:
        lines.append("• در این ماه سفارشی ثبت نشده.")

    return "\n".join(lines)


def build_wallet_overview_report(conn: sqlite3.Connection) -> str:
    cur = conn.cursor()
    filters = _current_month_filters()

    cur.execute(
        """
        SELECT status, COUNT(*) AS cnt, COALESCE(SUM(amount), 0) AS total
        FROM transactions
        WHERE status != 'draft'
        GROUP BY status
        ORDER BY cnt DESC, total DESC
        """
    )
    raw_status_rows = cur.fetchall()

    merged_status = {}
    for row in raw_status_rows:
        status = row["status"] or "unknown"
        current = merged_status.setdefault(status, {"cnt": 0, "total": 0})
        current["cnt"] += row["cnt"]
        current["total"] += row["total"]

    cur.execute(
        """
        SELECT u.id, u.first_name, u.last_name, u.username, COALESCE(SUM(t.amount), 0) AS total
        FROM transactions t
        JOIN users u ON u.id = t.user_id
        WHERE t.status IN (?, ?)
          AND substr(COALESCE(t.submitted_at, t.created_at), 1, 10) >= ?
          AND substr(COALESCE(t.submitted_at, t.created_at), 1, 10) < ?
        GROUP BY u.id, u.first_name, u.last_name, u.username
        ORDER BY total DESC
        LIMIT 10
        """,
        (STATUS_ACCOUNTING_APPROVED, STATUS_LEGACY_APPROVED, filters["greg_start"], filters["greg_end"]),
    )
    month_depositors = cur.fetchall()

    cur.execute(
        """
        SELECT u.id, u.first_name, u.last_name, u.username, COALESCE(SUM(t.amount), 0) AS total
        FROM transactions t
        JOIN users u ON u.id = t.user_id
        WHERE t.status IN (?, ?)
        GROUP BY u.id, u.first_name, u.last_name, u.username
        ORDER BY total DESC
        LIMIT 10
        """,
        (STATUS_ACCOUNTING_APPROVED, STATUS_LEGACY_APPROVED),
    )
    all_time_depositors = cur.fetchall()

    lines = [
        "💰 گزارش مالی و کیف پول",
        "",
        "وضعیت تراکنش‌ها:",
    ]
    if merged_status:
        for status, values in sorted(merged_status.items(), key=lambda item: item[1]["cnt"], reverse=True):
            lines.append(
                f"• {get_transaction_status_label(status)}: {values['cnt']} تراکنش | {_fmt_num(values['total'])} تومان"
            )
    else:
        lines.append("• داده‌ای ثبت نشده.")

    lines.extend(
        [
            "",
            f"بیشترین واریزی با تایید نهایی حسابداری در ماه {filters['period_label']}:",
            _render_ranked_rows(month_depositors, value_formatter=lambda value: f"{_fmt_num(value)} تومان"),
            "",
            "بیشترین واریزی با تایید نهایی حسابداری در کل:",
            _render_ranked_rows(all_time_depositors, value_formatter=lambda value: f"{_fmt_num(value)} تومان"),
        ]
    )
    return "\n".join(lines)


def build_top_plans_report(conn: sqlite3.Connection) -> str:
    cur = conn.cursor()
    filters = _current_month_filters()

    cur.execute(
        """
        SELECT COALESCE(p.name, 'بدون پلن') AS label, COUNT(*) AS cnt, COALESCE(SUM(o.price), 0) AS total
        FROM orders o
        LEFT JOIN plans p ON p.id = o.plan_id
        GROUP BY COALESCE(p.name, 'بدون پلن')
        ORDER BY cnt DESC, total DESC
        LIMIT 10
        """
    )
    all_time_plans = cur.fetchall()

    cur.execute(
        """
        SELECT COALESCE(p.name, 'بدون پلن') AS label, COUNT(*) AS cnt, COALESCE(SUM(o.price), 0) AS total
        FROM orders o
        LEFT JOIN plans p ON p.id = o.plan_id
        WHERE substr(o.created_at, 1, 10) >= ? AND substr(o.created_at, 1, 10) < ?
        GROUP BY COALESCE(p.name, 'بدون پلن')
        ORDER BY cnt DESC, total DESC
        LIMIT 10
        """,
        (filters["greg_start"], filters["greg_end"]),
    )
    month_plans = cur.fetchall()

    cur.execute(
        """
        SELECT COALESCE(p.category, 'standard') AS label, COUNT(*) AS cnt
        FROM orders o
        LEFT JOIN plans p ON p.id = o.plan_id
        GROUP BY COALESCE(p.category, 'standard')
        ORDER BY cnt DESC
        LIMIT 10
        """
    )
    categories = cur.fetchall()

    lines = ["📈 پلن‌های پرفروش", "", "پرفروش‌ترین پلن‌ها در کل:"]
    if all_time_plans:
        for index, row in enumerate(all_time_plans, start=1):
            lines.append(f"{index}. {escape(str(row['label']))} — {row['cnt']} سفارش | {_fmt_num(row['total'])} تومان")
    else:
        lines.append("داده‌ای ثبت نشده.")

    lines.extend(["", f"پرفروش‌ترین پلن‌ها در ماه {filters['period_label']}:"])
    if month_plans:
        for index, row in enumerate(month_plans, start=1):
            lines.append(f"{index}. {escape(str(row['label']))} — {row['cnt']} سفارش | {_fmt_num(row['total'])} تومان")
    else:
        lines.append("در این ماه پلنی فروخته نشده.")

    lines.extend(["", "توزیع سفارش‌ها بر اساس category:"])
    if categories:
        for row in categories:
            lines.append(f"• {escape(str(row['label']))}: {row['cnt']} سفارش")
    else:
        lines.append("داده‌ای ثبت نشده.")

    return "\n".join(lines)


def build_users_overview_report(conn: sqlite3.Connection) -> str:
    cur = conn.cursor()
    filters = _current_month_filters()

    cur.execute("SELECT COUNT(*) AS cnt FROM users")
    total_users = cur.fetchone()["cnt"]

    cur.execute(
        """
        SELECT COALESCE(role, 'unknown') AS role, COUNT(*) AS cnt
        FROM users
        GROUP BY COALESCE(role, 'unknown')
        ORDER BY cnt DESC
        """
    )
    role_rows = cur.fetchall()

    cur.execute(
        """
        SELECT COUNT(*) AS cnt
        FROM users
        WHERE substr(created_at, 1, 10) >= ? AND substr(created_at, 1, 10) < ?
        """,
        (filters["greg_start"], filters["greg_end"]),
    )
    month_new_users = cur.fetchone()["cnt"]

    cur.execute(
        """
        SELECT COUNT(*) AS cnt, COALESCE(SUM(balance), 0) AS total
        FROM users
        WHERE balance > 0
        """
    )
    wallet_row = cur.fetchone()

    cur.execute(
        """
        SELECT u.id, u.first_name, u.last_name, u.username, COUNT(o.id) AS total
        FROM users u
        JOIN orders o ON o.user_id = u.id
        WHERE o.status = 'active'
        GROUP BY u.id, u.first_name, u.last_name, u.username
        ORDER BY total DESC, u.id ASC
        LIMIT 10
        """
    )
    top_active_users = cur.fetchall()

    lines = [
        "👥 نمای کلی کاربران",
        "",
        f"کل کاربران: <b>{_fmt_num(total_users)}</b>",
        f"کاربران جدید این ماه: <b>{_fmt_num(month_new_users)}</b>",
        f"کاربران دارای موجودی: <b>{_fmt_num(wallet_row['cnt'])}</b>",
        f"جمع موجودی مثبت: <b>{_fmt_num(wallet_row['total'])}</b> تومان",
        "",
        "نقش‌های کاربری:",
    ]

    if role_rows:
        for row in role_rows:
            lines.append(f"• {row['role']}: {row['cnt']}")
    else:
        lines.append("• داده‌ای ثبت نشده.")

    lines.extend(["", "بیشترین تعداد سرویس فعال:"])
    lines.append(_render_ranked_rows(top_active_users, value_formatter=lambda value: f"{value} سرویس"))
    return "\n".join(lines)


def build_expiring_overview_report(conn: sqlite3.Connection) -> str:
    cur = conn.cursor()
    now_j = jdatetime.datetime.now()
    now_str = now_j.strftime("%Y-%m-%d %H:%M")
    plus_24 = (now_j + jdatetime.timedelta(hours=24)).strftime("%Y-%m-%d %H:%M")
    plus_72 = (now_j + jdatetime.timedelta(hours=72)).strftime("%Y-%m-%d %H:%M")
    plus_7d = (now_j + jdatetime.timedelta(days=7)).strftime("%Y-%m-%d %H:%M")

    windows = [
        ("تا 24 ساعت آینده", plus_24),
        ("تا 72 ساعت آینده", plus_72),
        ("تا 7 روز آینده", plus_7d),
    ]

    lines = ["⏳ گزارش انقضا و تمدید", ""]
    for label, end_value in windows:
        cur.execute(
            """
            SELECT COUNT(*) AS cnt
            FROM orders
            WHERE status = 'active'
              AND expires_at IS NOT NULL
              AND expires_at >= ?
              AND expires_at < ?
            """,
            (now_str, end_value),
        )
        lines.append(f"{label}: <b>{_fmt_num(cur.fetchone()['cnt'])}</b> سرویس")

    cur.execute("SELECT COUNT(*) AS cnt FROM orders WHERE status = 'waiting_for_renewal'")
    waiting_for_renewal = cur.fetchone()["cnt"]
    cur.execute("SELECT COUNT(*) AS cnt FROM orders WHERE status = 'reserved'")
    reserved_orders = cur.fetchone()["cnt"]
    cur.execute("SELECT COUNT(*) AS cnt FROM orders WHERE status = 'waiting_for_payment'")
    waiting_for_payment = cur.fetchone()["cnt"]

    lines.extend(
        [
            "",
            f"در انتظار تمدید: <b>{_fmt_num(waiting_for_renewal)}</b>",
            f"تمدید رزروی: <b>{_fmt_num(reserved_orders)}</b>",
            f"در انتظار پرداخت: <b>{_fmt_num(waiting_for_payment)}</b>",
            "",
            "نزدیک‌ترین سرویس‌های در حال انقضا:",
        ]
    )

    cur.execute(
        """
        SELECT id, user_id, username, expires_at
        FROM orders
        WHERE status = 'active'
          AND expires_at IS NOT NULL
          AND expires_at >= ?
        ORDER BY expires_at ASC
        LIMIT 10
        """,
        (now_str,),
    )
    rows = cur.fetchall()
    if rows:
        for row in rows:
            lines.append(
                f"• سفارش #{row['id']} | user_id={row['user_id']} | "
                f"{escape(str(row['username']))} | انقضا: {escape(str(row['expires_at']))}"
            )
    else:
        lines.append("• موردی پیدا نشد.")

    return "\n".join(lines)


def build_feedback_overview_report(conn: sqlite3.Connection) -> str:
    cur = conn.cursor()

    cur.execute(
        """
        SELECT COALESCE(type, 'unknown') AS type, COUNT(*) AS cnt
        FROM feedbacks
        GROUP BY COALESCE(type, 'unknown')
        ORDER BY cnt DESC
        """
    )
    grouped = cur.fetchall()

    cur.execute(
        """
        SELECT user_id, type, message, created_at
        FROM feedbacks
        ORDER BY created_at DESC
        LIMIT 5
        """
    )
    latest_rows = cur.fetchall()

    lines = ["📬 گزارش بازخوردها", "", "تعداد بازخورد به تفکیک نوع:"]
    if grouped:
        for row in grouped:
            lines.append(f"• {row['type']}: {row['cnt']}")
    else:
        lines.append("• بازخوردی ثبت نشده.")

    lines.extend(["", "آخرین بازخوردها:"])
    if latest_rows:
        for row in latest_rows:
            lines.append(
                f"• user_id={row['user_id']} | {escape(str(row['type'] or '-'))} | "
                f"{_compact_text(row['message'])} | {escape(str(row['created_at'] or '-'))}"
            )
    else:
        lines.append("• موردی پیدا نشد.")
    return "\n".join(lines)


def build_user_balances_report(conn: sqlite3.Connection) -> str:
    cur = conn.cursor()

    cur.execute(
        """
        SELECT id, first_name, last_name, username, COALESCE(balance, 0) AS balance
        FROM users
        WHERE balance > 0
        ORDER BY balance DESC, id ASC
        LIMIT 30
        """
    )
    rows = cur.fetchall()

    cur.execute("SELECT COUNT(*) AS cnt, COALESCE(SUM(balance), 0) AS total FROM users WHERE balance > 0")
    summary = cur.fetchone()

    lines = [
        "💳 موجودی کاربران",
        "",
        f"تعداد کاربران دارای موجودی: <b>{_fmt_num(summary['cnt'])}</b>",
        f"جمع کل موجودی مثبت: <b>{_fmt_num(summary['total'])}</b> تومان",
        "",
        "بیشترین موجودی‌ها:",
    ]

    if rows:
        for index, row in enumerate(rows, start=1):
            lines.append(f"{index}. {_build_user_label(row)} — {_fmt_num(row['balance'])} تومان")
    else:
        lines.append("موردی پیدا نشد.")

    return "\n".join(lines)


def build_user_detail_report(user_id: int) -> Optional[str]:
    with _connect() as conn:
        cur = conn.cursor()

        cur.execute(
            """
            SELECT id, first_name, last_name, username, role, created_at, COALESCE(balance, 0) AS balance
            FROM users
            WHERE id = ?
            """,
            (user_id,),
        )
        user_row = cur.fetchone()
        if not user_row:
            return None

        cur.execute(
            """
            SELECT COALESCE(status, 'unknown') AS status, COUNT(*) AS cnt, COALESCE(SUM(price), 0) AS total
            FROM orders
            WHERE user_id = ?
            GROUP BY COALESCE(status, 'unknown')
            ORDER BY cnt DESC
            """,
            (user_id,),
        )
        order_status_rows = cur.fetchall()

        cur.execute(
            """
            SELECT COUNT(*) AS cnt, COALESCE(SUM(price), 0) AS total
            FROM orders
            WHERE user_id = ?
            """,
            (user_id,),
        )
        orders_summary = cur.fetchone()

        cur.execute(
            """
            SELECT COUNT(*) AS cnt, COALESCE(SUM(amount), 0) AS total
            FROM transactions
            WHERE user_id = ? AND status IN (?, ?)
            """,
            (user_id, STATUS_ACCOUNTING_APPROVED, STATUS_LEGACY_APPROVED),
        )
        accounting_approved_tx_summary = cur.fetchone()

        cur.execute(
            """
            SELECT COUNT(*) AS cnt, COALESCE(SUM(amount), 0) AS total
            FROM transactions
            WHERE user_id = ? AND status = ?
            """,
            (user_id, STATUS_APPROVED_PENDING_ACCOUNTING),
        )
        pending_accounting_tx_summary = cur.fetchone()

        cur.execute(
            """
            SELECT COUNT(*) AS cnt
            FROM transactions
            WHERE user_id = ? AND status IN (?, ?)
            """,
            (user_id, STATUS_PENDING_ADMIN, STATUS_LEGACY_PENDING),
        )
        pending_initial_tx_summary = cur.fetchone()

        cur.execute(
            """
            SELECT o.id, o.username, COALESCE(p.name, 'بدون پلن') AS plan_name, o.status, o.price, o.created_at, o.expires_at
            FROM orders o
            LEFT JOIN plans p ON p.id = o.plan_id
            WHERE o.user_id = ?
            ORDER BY o.id DESC
            LIMIT 8
            """,
            (user_id,),
        )
        recent_orders = cur.fetchall()

        cur.execute(
            """
            SELECT id, amount, status, created_at
            FROM transactions
            WHERE user_id = ?
            ORDER BY id DESC
            LIMIT 8
            """,
            (user_id,),
        )
        recent_transactions = cur.fetchall()

    lines = [
        f"🔎 گزارش کاربر {user_id}",
        "",
        f"نام: <b>{_build_user_label(user_row)}</b>",
        f"نقش: <b>{user_row['role'] or '-'}</b>",
        f"تاریخ عضویت: <b>{user_row['created_at'] or '-'}</b>",
        f"موجودی کیف پول: <b>{_fmt_num(user_row['balance'])}</b> تومان",
        "",
        f"کل سفارش‌ها: <b>{_fmt_num(orders_summary['cnt'])}</b>",
        f"جمع مبلغ سفارش‌ها: <b>{_fmt_num(orders_summary['total'])}</b> تومان",
        f"تراکنش‌های تایید نهایی حسابداری: <b>{_fmt_num(accounting_approved_tx_summary['cnt'])}</b>",
        f"جمع واریزی تایید نهایی: <b>{_fmt_num(accounting_approved_tx_summary['total'])}</b> تومان",
        f"در انتظار بررسی اولیه: <b>{_fmt_num(pending_initial_tx_summary['cnt'])}</b>",
        f"در انتظار تایید حسابداری: <b>{_fmt_num(pending_accounting_tx_summary['cnt'])}</b>",
        f"جمع مبالغ در انتظار حسابداری: <b>{_fmt_num(pending_accounting_tx_summary['total'])}</b> تومان",
        "",
        "وضعیت سفارش‌ها:",
    ]

    if order_status_rows:
        for row in order_status_rows:
            lines.append(f"• {row['status']}: {row['cnt']} سفارش | {_fmt_num(row['total'])} تومان")
    else:
        lines.append("• سفارشی ثبت نشده.")

    lines.extend(["", "آخرین سفارش‌ها:"])
    if recent_orders:
        for row in recent_orders:
            lines.append(
                f"• #{row['id']} | {escape(str(row['plan_name']))} | {escape(str(row['username']))} | "
                f"{escape(str(row['status']))} | {_fmt_num(row['price'])} تومان | {escape(str(row['created_at'] or '-'))}"
            )
    else:
        lines.append("• سفارشی ثبت نشده.")

    lines.extend(["", "آخرین تراکنش‌ها:"])
    if recent_transactions:
        for row in recent_transactions:
            lines.append(
                f"• #{row['id']} | {escape(get_transaction_status_label(row['status']))} | "
                f"{_fmt_num(row['amount'])} تومان | {escape(str(row['created_at'] or '-'))}"
            )
    else:
        lines.append("• تراکنشی ثبت نشده.")

    return "\n".join(lines)


@router.message(F.text == "📑 گزارشات")
async def show_reports_menu(message: Message):
    if not is_admin(message.from_user.id):
        return
    await message.answer(
        f"📑 گزارش‌های مدیریتی\n\nمحیط فعلی: <b>{APP_ENV}</b>",
        reply_markup=reports_keyboard(),
        parse_mode="HTML",
    )


@router.callback_query(F.data.startswith("report:"))
async def report_handler(callback: CallbackQuery, state: FSMContext):
    if not is_admin(callback.from_user.id):
        return await callback.answer("دسترسی نداری.", show_alert=True)

    action = callback.data.split(":", 1)[1]
    if action == "env_status":
        text = build_env_status_report()
    elif action == "dashboard_month":
        with _connect() as conn:
            text = build_dashboard_month_report(conn)
    elif action == "orders_overview":
        with _connect() as conn:
            text = build_orders_overview_report(conn)
    elif action == "wallet_overview":
        with _connect() as conn:
            text = build_wallet_overview_report(conn)
    elif action == "top_plans":
        with _connect() as conn:
            text = build_top_plans_report(conn)
    elif action == "users_overview":
        with _connect() as conn:
            text = build_users_overview_report(conn)
    elif action == "expiring_overview":
        with _connect() as conn:
            text = build_expiring_overview_report(conn)
    elif action == "feedback_overview":
        with _connect() as conn:
            text = build_feedback_overview_report(conn)
    elif action == "user_balances":
        with _connect() as conn:
            text = build_user_balances_report(conn)
    elif action == "user_transactions":
        await state.set_state(ReportUserTx.waiting_for_userid)
        await callback.message.answer("🔎 لطفاً آیدی عددی کاربر را ارسال کنید:")
        await callback.answer()
        return
    else:
        await callback.answer("گزارش نامعتبر است.", show_alert=True)
        return

    await callback.message.answer(text, parse_mode="HTML")
    await callback.answer()


@router.message(ReportUserTx.waiting_for_userid)
async def process_user_transactions(message: Message, state: FSMContext):
    if not is_admin(message.from_user.id):
        await state.clear()
        return

    user_id_text = (message.text or "").strip()
    if not user_id_text.isdigit():
        await message.answer("⚠️ لطفاً فقط آیدی عددی وارد کنید.")
        return

    report = build_user_detail_report(int(user_id_text))
    await state.clear()

    if not report:
        await message.answer("کاربری با این آیدی در سیستم پیدا نشد.")
        return

    await message.answer(report, parse_mode="HTML")
