import sqlite3
from datetime import datetime
from typing import Optional, List, Dict

import jdatetime

from config import DB_PATH


def get_orders():
    with sqlite3.connect(DB_PATH) as conn:
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        cursor.execute("""
                SELECT * FROM orders
                WHERE starts_at IS NOT NULL AND expires_at IS NOT NULL
            """)
        return [dict(r) for r in cursor.fetchall()]


def get_last_update(order_id):
    with sqlite3.connect(DB_PATH) as conn:
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        cursor.execute("SELECT last_update FROM order_usages WHERE order_id = ?", (order_id,))
        row = cursor.fetchone()
        last_update = row["last_update"] if row else None
        return last_update


def update_order_usages(now, sent_mb, recv_mb, total_mb, order_id):
    with sqlite3.connect(DB_PATH) as conn:
        cursor = conn.cursor()
        cursor.execute("""
                            UPDATE order_usages
                            SET last_update = ?, sent_mb = ?, received_mb = ?, total_mb = ?
                            WHERE order_id = ?
                        """, (now, sent_mb, recv_mb, total_mb, order_id))
        conn.commit()


def insert_order_usages(order_id, username, plan_id, starts_at, expires_at, now, sent_mb, recv_mb, total_mb):
    with sqlite3.connect(DB_PATH) as conn:
        cursor = conn.cursor()
        cursor.execute("""
                            INSERT INTO order_usages (order_id, username, plan_id, starts_at, expires_at, last_update, sent_mb, received_mb, total_mb)
                            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                        """, (order_id, username, plan_id, starts_at, expires_at, now, sent_mb, recv_mb, total_mb))

        conn.commit()
