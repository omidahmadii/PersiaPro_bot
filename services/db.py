import sqlite3
from datetime import datetime
from typing import Optional, List, Dict

import jdatetime

from config import DB_PATH


def create_tables():
    with sqlite3.connect(DB_PATH) as conn:
        cursor = conn.cursor()
        cursor.execute("""
                CREATE TABLE IF NOT EXISTS accounts (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    username TEXT NOT NULL UNIQUE,
                    password TEXT NOT NULL,
                    status TEXT DEFAULT 'free',
                    plan_id INTEGER,
                    order_id INTEGER,
                    start_date INTEGER,
                    expire_date TIMESTAMP,
                    comment TEXT,
                    FOREIGN KEY(order_id) REFERENCES orders(id),
                    FOREIGN KEY(plan_id) REFERENCES plans(id)
                )
                """)

        cursor.execute("""
                CREATE TABLE IF NOT EXISTS bank_cards (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    card_number TEXT NOT NULL,
                    owner_name TEXT,
                    bank_name TEXT,
                    priority INTEGER NOT NULL DEFAULT 0,
                    is_active INTEGER NOT NULL DEFAULT 1
                )
                """)

        cursor.execute("""
                CREATE TABLE IF NOT EXISTS feedbacks (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER,
                    type TEXT,
                    message TEXT,
                    created_at TEXT
                )
                """)

        cursor.execute("""
                CREATE TABLE IF NOT EXISTS order_usages (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    order_id INTEGER,
                    username TEXT,
                    plan_id INTEGER,
                    starts_at TEXT,
                    expires_at TEXT,
                    last_update NUMERIC,
                    sent_mb INTEGER,
                    received_mb INTEGER,
                    total_mb INTEGER,
                    applied_speed TEXT,
                    FOREIGN KEY(order_id) REFERENCES orders(id)
                )
                """)

        cursor.execute("""
                CREATE TABLE IF NOT EXISTS orders (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER,
                    plan_id INTEGER,
                    username INTEGER,
                    status TEXT NOT NULL,
                    price INTEGER NOT NULL,
                    created_at TEXT,
                    starts_at BLOB,
                    expires_at TEXT,
                    last_notif_level INTEGER,
                    is_renewal_of_order INTEGER,
                    volume_bytes INTEGER,
                    FOREIGN KEY(plan_id) REFERENCES plans(id),
                    FOREIGN KEY(user_id) REFERENCES users(id)
                )
                """)

        cursor.execute("""
                CREATE TABLE IF NOT EXISTS plans (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    name TEXT NOT NULL,
                    volume_gb INTEGER,
                    duration_months INTEGER,
                    max_users INTEGER,
                    price INTEGER NOT NULL,
                    order_priority INTEGER DEFAULT 0,
                    visible INTEGER DEFAULT 1,
                    location TEXT,
                    is_unlimited INTEGER DEFAULT 0,
                    group_name TEXT,
                    duration_days INTEGER
                )
                """)

        cursor.execute("""
                CREATE TABLE IF NOT EXISTS servers (
                    server_id INTEGER PRIMARY KEY AUTOINCREMENT,
                    location TEXT NOT NULL,
                    ip TEXT NOT NULL,
                    port INTEGER NOT NULL,
                    panel_path TEXT NOT NULL,
                    api_base_url TEXT NOT NULL,
                    v2ray_username TEXT NOT NULL,
                    v2ray_password TEXT NOT NULL,
                    inbound_id INTEGER,
                    subscription_path TEXT
                )
                """)

        cursor.execute("""
                CREATE TABLE IF NOT EXISTS speed_limits (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    threshold_gb INTEGER,
                    speed TEXT
                )
                """)

        cursor.execute("""
                CREATE TABLE IF NOT EXISTS transactions (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER NOT NULL,
                    amount INTEGER NOT NULL DEFAULT 0,
                    status TEXT NOT NULL DEFAULT 'pending',
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    photo_id TEXT NOT NULL,
                    photo_path TEXT NOT NULL,
                    photo_hash TEXT
                )
                """)

        cursor.execute("""
                CREATE TABLE IF NOT EXISTS users (
                    id INTEGER PRIMARY KEY,
                    first_name TEXT,
                    username TEXT,
                    role TEXT,
                    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                    balance INTEGER DEFAULT 0,
                    membership_status TEXT DEFAULT 'not_member'
                )
                """)
        conn.commit()


def add_user(user_id, first_name, username, role):
    with sqlite3.connect(DB_PATH) as conn:
        cursor = conn.cursor()
        cursor.execute("""
                       INSERT
                       OR IGNORE INTO users (id, first_name, username, role)
            VALUES (?, ?, ?, ?)
                       """, (user_id, first_name, username, role))
        conn.commit()


def get_user_info(user_id):
    with sqlite3.connect(DB_PATH) as conn:
        cursor = conn.cursor()
        cursor.execute("""
                       SELECT first_name, username, created_at, balance, role
                       FROM users
                       WHERE id = ?
                       """, (user_id,))
        return cursor.fetchone()


# Plan management

def add_plan(name, volume_gb, duration_days, max_users, price):
    with sqlite3.connect(DB_PATH) as conn:
        cursor = conn.cursor()
        cursor.execute("""
                       INSERT INTO plans (name, volume_gb, duration_days, max_users, price)
                       VALUES (?, ?, ?, ?, ?)
                       """, (name, volume_gb, duration_days, max_users, price))
        conn.commit()


def get_all_plans():
    with sqlite3.connect(DB_PATH) as conn:
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        cursor.execute("""
            SELECT 
                id,
                name,
                volume_gb,
                duration_months,
                duration_days,
                max_users,
                price,
                group_name
            FROM plans
            ORDER BY order_priority DESC
        """)
        return [dict(row) for row in cursor.fetchall()]


# Server management

def add_server(location, ip, port, panel_path, api_base_url, v2ray_username, v2ray_password, inbound_id=None,
               subscription_path=None):
    with sqlite3.connect(DB_PATH) as conn:
        cursor = conn.cursor()
        cursor.execute("""
                       INSERT INTO servers (location, ip, port, panel_path, api_base_url, v2ray_username,
                                            v2ray_password, inbound_id, subscription_path)
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                       """, (
            location, ip, port, panel_path, api_base_url, v2ray_username, v2ray_password, inbound_id,
            subscription_path))
        conn.commit()


def get_all_servers():
    with sqlite3.connect(DB_PATH) as conn:
        cursor = conn.cursor()
        cursor.execute(
            "SELECT server_id, location, ip, port, panel_path, api_base_url, v2ray_username, v2ray_password, inbound_id, subscription_path FROM servers"
        )
        return cursor.fetchall()


def get_next_account_number():
    with sqlite3.connect(DB_PATH) as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT MAX(account_number) FROM orders")
        result = cursor.fetchone()
        max_account = result[0] if result[0] is not None else 100000
        return max_account + 1


def insert_order(user_id, plan_id, username, price, status):
    created_at = datetime.now().isoformat()
    with sqlite3.connect(DB_PATH) as conn:
        cursor = conn.cursor()
        cursor.execute('''
                       INSERT INTO orders (user_id, plan_id, username, price, created_at, status)
                       VALUES (?, ?, ?, ?, ?, ?)
                       ''', (user_id, plan_id, username, price, created_at, status))
        order_id = cursor.lastrowid  # گرفتن آیدی آخرین ردیف واردشده
        conn.commit()
        return order_id


def insert_renewed_order(user_id, plan_id, username, price, status, is_renewal_of_order):
    created_at = datetime.now().isoformat()
    with sqlite3.connect(DB_PATH) as conn:
        cursor = conn.cursor()
        cursor.execute('''
                       INSERT INTO orders (user_id, plan_id, username, price, created_at, status, is_renewal_of_order)
                       VALUES (?, ?, ?, ?, ?, ?, ?)
                       ''', (user_id, plan_id, username, price, created_at, status, is_renewal_of_order))
        order_id = cursor.lastrowid  # گرفتن آیدی آخرین ردیف واردشده
        conn.commit()
        return order_id


def update_user_balance(user_id, new_balance):
    with sqlite3.connect(DB_PATH) as conn:
        cursor = conn.cursor()
        cursor.execute("UPDATE users SET balance = ? WHERE id = ?", (new_balance, user_id))
        conn.commit()


def insert_payment(user_id, order_id, amount, status):
    with sqlite3.connect(DB_PATH) as conn:
        cursor = conn.cursor()
        cursor.execute("""
                       INSERT INTO order_payments (user_id, order_id, amount, status, created_at)
                       VALUES (?, ?, ?, ?, ?)
                       """, (user_id, order_id, amount, status, datetime.now().isoformat()))
        conn.commit()


def update_latest_payment_order_id(user_id, order_id):
    with sqlite3.connect(DB_PATH) as conn:
        cursor = conn.cursor()
        cursor.execute("""
                       UPDATE order_payments
                       SET order_id = ?
                       WHERE user_id = ?
                         AND order_id IS NULL
                       """, (order_id, user_id))
        conn.commit()


def get_unpaid_orders(user_id):
    with sqlite3.connect(DB_PATH) as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM orders WHERE user_id = ? AND status = 'pending_payment'", (user_id,))
        orders = cursor.fetchall()
        return orders


def get_all_photo_hashes():
    with sqlite3.connect(DB_PATH) as conn:
        cursor = conn.execute("SELECT photo_hash FROM transactions")
        return {row[0] for row in cursor.fetchall() if row[0] is not None}


def insert_transaction(user_id, photo_id, photo_path, photo_hash):
    created_at = datetime.now().isoformat()
    with sqlite3.connect(DB_PATH) as conn:
        cursor = conn.cursor()
        cursor.execute('''
                       INSERT INTO transactions (user_id, photo_id, photo_path, created_at, photo_hash)
                       VALUES (?, ?, ?, ?, ?)
                       ''', (user_id, photo_id, photo_path, created_at, photo_hash))
        conn.commit()


def get_user_telegram_id_by_txn_id(txn_id: int) -> Optional[int]:
    try:
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()

        query = """
        SELECT users.id
        FROM transactions
        JOIN users ON transactions.user_id = users.id
        WHERE transactions.id = ?
        LIMIT 1
        """
        cursor.execute(query, (txn_id,))
        row = cursor.fetchone()

        conn.close()

        if row:
            return row[0]  # telegram_id
        else:
            return None

    except Exception as e:
        print(f"Database error in get_user_telegram_id_by_txn_id: {e}")
        return None


def get_user_balance(user_id: int) -> Optional[int]:
    with sqlite3.connect(DB_PATH) as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT balance FROM users WHERE id = ?", (user_id,))
        result = cursor.fetchone()
        balance = result[0]
        return balance


# پیدا کردن اولین اکانت آزاد
def find_free_account():
    with sqlite3.connect(DB_PATH) as conn:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT * FROM accounts
            WHERE status = 'free'
            LIMIT 1
        """)
        return cursor.fetchone()  # اگر None برگرده یعنی اکانت آزاد نیست


# رزرو اکانت برای یک سفارش خاص
def assign_account_to_order(account_id: int, order_id: int, plan_id: int, status: str):
    with sqlite3.connect(DB_PATH) as conn:
        cursor = conn.cursor()
        cursor.execute("""
            UPDATE accounts
            SET status = 'assigned',
                order_id = ?,
                plan_id = ?,
                status = ?
            WHERE id = ?
        """, (order_id, plan_id, status, account_id))
        conn.commit()


# اضافه کردن یک اکانت جدید (برای موقع ساخت دستی یا اولیه اکانت‌ها)
def add_account(username: str, password: str, comment: str = ""):
    with sqlite3.connect(DB_PATH) as conn:
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO accounts (username, password, comment)
            VALUES (?, ?, ?)
        """, (username, password, comment))
        conn.commit()


# تغییر وضعیت اکانت (مثلاً آزاد کردن بعد از انقضا)
def update_account_status(account_id: int, new_status: str):
    with sqlite3.connect(DB_PATH) as conn:
        cursor = conn.cursor()
        cursor.execute("""
            UPDATE accounts
            SET status = ?
            WHERE id = ?
        """, (new_status, account_id))
        conn.commit()


def update_order_status(order_id: int, new_status: str):
    with sqlite3.connect(DB_PATH) as conn:
        cursor = conn.cursor()
        cursor.execute("""
            UPDATE orders
            SET status = ?
            WHERE id = ?
        """, (new_status, order_id))
        conn.commit()


# گرفتن اطلاعات اکانت بر اساس آیدی سفارش
def get_account_by_order_id(order_id: int):
    with sqlite3.connect(DB_PATH) as conn:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT * FROM accounts
            WHERE order_id = ?
        """, (order_id,))
        return cursor.fetchone()


def get_user_services(user_id: int):
    with sqlite3.connect(DB_PATH) as conn:
        cursor = conn.cursor()
        cursor.execute("""
                SELECT 
                orders.id,
                orders.username,
                accounts.password,
                plans.name AS plan_name,
                orders.starts_at,
                orders.expires_at,
                orders.status,
                orders.created_at
                FROM orders
                JOIN plans ON orders.plan_id = plans.id
                JOIN users ON orders.user_id = users.id
                JOIN accounts ON orders.username = accounts.username
                WHERE users.id = ? and orders.status is not "renewed" 
                ORDER by orders.username,orders.created_at
            """, (user_id,))
        return cursor.fetchall()


def get_active_orders_without_time() -> List[Dict]:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row  # خروجی به شکل dict
    cur = conn.cursor()

    cur.execute("""
        SELECT * FROM orders
        WHERE status = 'active'
        AND (starts_at IS NULL OR expires_at IS NULL)
    """)

    rows = cur.fetchall()
    conn.close()

    return [dict(row) for row in rows]


def update_order_starts_at(order_id: int, starts_at: str):
    with sqlite3.connect(DB_PATH) as conn:
        cursor = conn.cursor()
        cursor.execute("""
                    UPDATE orders
                    SET starts_at = ?
                    WHERE id = ?
                """, (starts_at, order_id))
        conn.commit()


def update_order_expires_at(order_id: int, expires_at: str):
    with sqlite3.connect(DB_PATH) as conn:
        cursor = conn.cursor()
        cursor.execute("""
                    UPDATE orders
                    SET expires_at = ?
                    WHERE id = ?
                """, (expires_at, order_id))
        conn.commit()


def expire_old_orders():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    now = jdatetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    cursor.execute("""
        SELECT id, expires_at FROM orders
        WHERE status = 'active' AND expires_at IS NOT NULL
    """)
    rows = cursor.fetchall()

    for row in rows:
        try:
            expires_at_str = row['expires_at']  # مثلاً: "1403-04-16 09:05"
            expires_at = jdatetime.datetime.strptime(expires_at_str, "%Y-%m-%d %H:%M")
            now_jdt = jdatetime.datetime.strptime(now, "%Y-%m-%d %H:%M:%S")

            if expires_at < now_jdt:
                cursor.execute("""
                    UPDATE orders
                    SET status = 'expired'
                    WHERE id = ?
                """, (row['id'],))
        except Exception as e:
            print(f"خطا در بررسی سفارش {row['id']}: {e}")

    conn.commit()
    conn.close()


def get_active_orders():
    with sqlite3.connect(DB_PATH) as conn:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT o.id, o.user_id, o.username, o.expires_at, u.first_name
            FROM orders o
            JOIN users u ON o.user_id = u.id
            WHERE o.status = 'active' AND o.expires_at IS NOT NULL
        """)
        return cursor.fetchall()


def get_services_for_renew(user_id):
    with sqlite3.connect(DB_PATH) as conn:
        conn.row_factory = sqlite3.Row
        cur = conn.cursor()
        cur.execute("""
            SELECT id, username, expires_at, status
            FROM orders
            WHERE user_id = ? AND status IN ('active','expired') AND expires_at not NULL
        """, (user_id,))
        return [dict(r) for r in cur.fetchall()]


def get_reserved_orders():
    with sqlite3.connect(DB_PATH) as conn:
        conn.row_factory = sqlite3.Row
        cur = conn.cursor()
        cur.execute("""
                SELECT * FROM orders
                WHERE status = 'reserved'
            """)
        return [dict(r) for r in cur.fetchall()]


def get_order_data(order_id):
    with sqlite3.connect(DB_PATH) as conn:
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        cursor.execute("""
                SELECT * FROM orders
                WHERE id = ?
            """, (order_id,))
        return dict(cursor.fetchone())


def get_order_plan_duration(order_id):
    with sqlite3.connect(DB_PATH) as conn:
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        cursor.execute("""
                SELECT duration_months FROM plans
                JOIN orders on orders.plan_id = plans.id
                WHERE orders.id = ?
            """, (order_id,))
        return dict(cursor.fetchone())


def get_order_plan_group_name(order_id):
    with sqlite3.connect(DB_PATH) as conn:
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        cursor.execute("""
                SELECT group_name FROM plans
                JOIN orders on orders.plan_id = plans.id
                WHERE orders.id = ?
            """, (order_id,))
        return dict(cursor.fetchone())


def get_orders_for_notifications(expires_at):
    with sqlite3.connect(DB_PATH) as conn:
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        cursor.execute("""
                SELECT id, user_id, username, expires_at, status, last_notif_level
            FROM orders
            WHERE status IN ('active', 'waiting_for_renewal')
            AND expires_at IS NOT NULL
            AND expires_at <= ?
            """, (expires_at,))
        return [dict(r) for r in cursor.fetchall()]


def update_order_last_notif_level(level_needed, order_id):
    with sqlite3.connect(DB_PATH) as conn:
        cursor = conn.cursor()
        cursor.execute("""
                    UPDATE orders
                    SET last_notif_level  = ?
                    WHERE id = ?
                """, (level_needed, order_id))
        conn.commit()


def get_order_usage(order_id: int):
    with sqlite3.connect(DB_PATH) as conn:
        cursor = conn.cursor()
        cursor.execute("""SELECT total_mb from order_usages where order_id = ?""", (order_id,))
        row = cursor.fetchone()
        return row[0] if row else 0


def get_accounts_id_by_username(username: str):
    with sqlite3.connect(DB_PATH) as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT id FROM accounts WHERE username = ?", (username,))
        return cursor.fetchone()


def update_account_password_by_username(username: str, new_password: str):
    with sqlite3.connect(DB_PATH) as conn:
        cursor = conn.cursor()
        cursor.execute("UPDATE accounts SET password = ? WHERE username = ?", (new_password, username))
        conn.commit()


def ensure_user_exists(user_id: int):
    with sqlite3.connect(DB_PATH) as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT 1 FROM users WHERE id = ?", (user_id,))
        return cursor.fetchone()


def insert_feedback(user_id, feedback_type, message, created_at):
    with sqlite3.connect(DB_PATH) as conn:
        cursor = conn.cursor()
        cursor.execute("INSERT INTO feedbacks (user_id, type, message, created_at) VALUES (?, ?, ?, ?)",
                       (user_id, feedback_type, message, created_at))
        conn.commit()


def get_orders_usage_for_limitation():
    with sqlite3.connect(DB_PATH) as conn:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT ou.id, ou.order_id, ou.username, ou.total_mb, ou.applied_speed,
                   p.is_unlimited, p.duration_months
            FROM order_usages ou
            JOIN orders o ON ou.order_id = o.id
            JOIN plans p ON o.plan_id = p.id
        """)
        return cursor.fetchall()


def save_applied_speed_to_db(applied_speed: str, order_id: int):
    with sqlite3.connect(DB_PATH) as conn:
        curses = conn.cursor()
        curses.execute("""UPDATE order_usages SET applied_speed = ? where order_id=?""", (applied_speed, order_id))
        conn.commit()


def get_active_cards():
    with sqlite3.connect(DB_PATH) as conn:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT card_number, owner_name, bank_name
            FROM bank_cards
            WHERE is_active = 1
            ORDER BY priority DESC
        """)

        rows = cursor.fetchall()
        if not rows:
            return []

        return [
            {
                "card_number": card_number,
                "owner_name": owner_name or "",
                "bank_name": bank_name or ""
            }
            for card_number, owner_name, bank_name in rows
        ]
