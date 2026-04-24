import sqlite3
from datetime import datetime
from typing import Optional, List, Dict

import jdatetime

from config import DB_PATH


def _now_text(timespec: str = "minutes") -> str:
    return datetime.now().isoformat(sep=" ", timespec=timespec)


def create_tables():
    with sqlite3.connect(DB_PATH) as conn:
        cursor = conn.cursor()
        from services.runtime_settings import initialize_runtime_settings_schema

        def ensure_column(table: str, column: str, definition: str):
            existing_columns = [row[1] for row in cursor.execute(f"PRAGMA table_info({table})").fetchall()]
            if column not in existing_columns:
                cursor.execute(f"ALTER TABLE {table} ADD COLUMN {column} {definition}")

        def normalize_datetime_column(table: str, column: str):
            existing_columns = [row[1] for row in cursor.execute(f"PRAGMA table_info({table})").fetchall()]
            if column not in existing_columns:
                return
            cursor.execute(
                f"""
                UPDATE {table}
                SET {column} = substr(replace({column}, 'T', ' '), 1, 16)
                WHERE {column} IS NOT NULL
                  AND TRIM({column}) != ''
                """
            )

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
                    is_active INTEGER NOT NULL DEFAULT 1,
                    show_in_receipt INTEGER NOT NULL DEFAULT 1
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

        cursor.execute("""
                CREATE TABLE IF NOT EXISTS ownership_transfers (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    from_user_id INTEGER NOT NULL,
                    to_user_id INTEGER NOT NULL,
                    username TEXT,
                    transferred_by INTEGER,
                    transferred_at TEXT DEFAULT CURRENT_TIMESTAMP,
                    total_orders INTEGER DEFAULT 0
                )
                """)

        cursor.execute("""
                CREATE TABLE IF NOT EXISTS segments (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    slug TEXT NOT NULL UNIQUE,
                    title TEXT NOT NULL,
                    description TEXT,
                    is_active INTEGER NOT NULL DEFAULT 1,
                    created_at TEXT DEFAULT CURRENT_TIMESTAMP
                )
                """)

        cursor.execute("""
                CREATE TABLE IF NOT EXISTS segment_users (
                    segment_id INTEGER NOT NULL,
                    user_id INTEGER NOT NULL,
                    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                    PRIMARY KEY (segment_id, user_id)
                )
                """)

        cursor.execute("""
                CREATE TABLE IF NOT EXISTS plan_segments (
                    plan_id INTEGER NOT NULL,
                    segment_id INTEGER NOT NULL,
                    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                    PRIMARY KEY (plan_id, segment_id)
                )
                """)

        cursor.execute("""
                CREATE TABLE IF NOT EXISTS volume_packages (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    name TEXT NOT NULL,
                    volume_gb INTEGER NOT NULL,
                    price INTEGER NOT NULL,
                    sort_order INTEGER NOT NULL DEFAULT 0,
                    is_active INTEGER NOT NULL DEFAULT 1,
                    is_archived INTEGER NOT NULL DEFAULT 0,
                    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                    updated_at TEXT DEFAULT CURRENT_TIMESTAMP
                )
                """)

        cursor.execute("""
                CREATE TABLE IF NOT EXISTS volume_package_segments (
                    package_id INTEGER NOT NULL,
                    segment_id INTEGER NOT NULL,
                    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                    PRIMARY KEY (package_id, segment_id),
                    FOREIGN KEY(package_id) REFERENCES volume_packages(id),
                    FOREIGN KEY(segment_id) REFERENCES segments(id)
                )
                """)

        cursor.execute("""
                CREATE TABLE IF NOT EXISTS volume_package_categories (
                    package_id INTEGER NOT NULL,
                    category TEXT NOT NULL,
                    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                    PRIMARY KEY (package_id, category),
                    FOREIGN KEY(package_id) REFERENCES volume_packages(id)
                )
                """)

        cursor.execute("""
                CREATE TABLE IF NOT EXISTS order_volume_allocations (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    order_id INTEGER NOT NULL,
                    user_id INTEGER NOT NULL,
                    package_id INTEGER,
                    package_name TEXT,
                    source_type TEXT NOT NULL DEFAULT 'user_package',
                    status TEXT NOT NULL DEFAULT 'applied',
                    volume_gb INTEGER NOT NULL DEFAULT 0,
                    price INTEGER NOT NULL DEFAULT 0,
                    note TEXT,
                    admin_id INTEGER,
                    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                    applied_at TEXT,
                    FOREIGN KEY(order_id) REFERENCES orders(id),
                    FOREIGN KEY(package_id) REFERENCES volume_packages(id),
                    FOREIGN KEY(user_id) REFERENCES users(id)
                )
                """)

        cursor.execute("""
                CREATE TABLE IF NOT EXISTS conversion_offer_logs (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    user_id INTEGER NOT NULL,
                    service_id INTEGER NOT NULL,
                    previous_plan_id INTEGER,
                    previous_expire_at TEXT,
                    previous_remaining_volume REAL,
                    target_plan_id INTEGER,
                    new_service_id INTEGER,
                    status TEXT NOT NULL,
                    notification_sent_at TEXT,
                    viewed_at TEXT,
                    selected_at TEXT,
                    confirmed_at TEXT,
                    converted_at TEXT,
                    failure_reason TEXT,
                    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
                    updated_at TEXT DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY(user_id) REFERENCES users(id),
                    FOREIGN KEY(service_id) REFERENCES orders(id),
                    FOREIGN KEY(new_service_id) REFERENCES orders(id)
                )
                """)

        ensure_column("plans", "duration_days", "INTEGER")
        ensure_column("plans", "category", "TEXT DEFAULT 'standard'")
        ensure_column("plans", "access_level", "TEXT DEFAULT 'all'")
        ensure_column("plans", "display_context", "TEXT DEFAULT 'all'")
        ensure_column("plans", "is_archived", "INTEGER DEFAULT 0")
        ensure_column("plans", "archived_at", "TEXT")

        ensure_column("bank_cards", "show_in_receipt", "INTEGER")
        cursor.execute("""
            UPDATE bank_cards
            SET show_in_receipt = COALESCE(is_active, 0)
            WHERE show_in_receipt IS NULL
        """)

        ensure_column("users", "last_name", "TEXT")
        ensure_column("users", "message_name", "TEXT")
        ensure_column("users", "referred_by", "INTEGER")
        ensure_column("users", "max_active_accounts", "INTEGER DEFAULT 3")

        ensure_column("orders", "volume_gb", "INTEGER DEFAULT 0")
        ensure_column("orders", "extra_volume_gb", "INTEGER DEFAULT 0")
        ensure_column("orders", "auto_renew", "INTEGER DEFAULT 0")
        ensure_column("orders", "usage_sent_mb", "INTEGER DEFAULT 0")
        ensure_column("orders", "usage_received_mb", "INTEGER DEFAULT 0")
        ensure_column("orders", "usage_total_mb", "INTEGER DEFAULT 0")
        ensure_column("orders", "usage_last_update", "TEXT")
        ensure_column("orders", "usage_applied_speed", "TEXT")
        ensure_column("orders", "usage_notif_level", "INTEGER DEFAULT 0")
        ensure_column("orders", "usage_lock_applied", "INTEGER DEFAULT 0")
        ensure_column("orders", "eligible_for_conversion", "INTEGER DEFAULT 0")
        ensure_column("orders", "old_limited_service", "INTEGER DEFAULT 0")
        ensure_column("orders", "converted_by_offer", "INTEGER DEFAULT 0")
        ensure_column("orders", "converted_to_service_id", "INTEGER")
        ensure_column("orders", "replaced_from_service_id", "INTEGER")
        ensure_column("orders", "service_source", "TEXT")
        ensure_column("orders", "closed_by_conversion_at", "TEXT")
        ensure_column("orders", "last_conversion_notification_at", "TEXT")
        ensure_column("orders", "last_renewal_offer_notification_at", "TEXT")

        ensure_column("transactions", "amount_claimed", "INTEGER DEFAULT 0")
        ensure_column("transactions", "destination_card_id", "INTEGER")
        ensure_column("transactions", "destination_card_number", "TEXT")
        ensure_column("transactions", "destination_card_owner", "TEXT")
        ensure_column("transactions", "destination_bank_name", "TEXT")
        ensure_column("transactions", "transfer_date", "TEXT")
        ensure_column("transactions", "transfer_time", "TEXT")
        ensure_column("transactions", "source_card_last4", "TEXT")
        ensure_column("transactions", "submitted_at", "TEXT")
        ensure_column("transactions", "duplicate_flags", "TEXT")
        ensure_column("transactions", "duplicate_candidate_ids", "TEXT")
        ensure_column("transactions", "is_duplicate_suspect", "INTEGER DEFAULT 0")
        ensure_column("transactions", "admin_reviewed_at", "TEXT")
        ensure_column("transactions", "admin_reviewed_by", "INTEGER")
        ensure_column("transactions", "admin_note", "TEXT")
        ensure_column("transactions", "accounting_reviewed_at", "TEXT")
        ensure_column("transactions", "accounting_reviewed_by", "INTEGER")
        ensure_column("transactions", "accounting_note", "TEXT")
        ensure_column("transactions", "balance_reverted", "INTEGER DEFAULT 0")
        ensure_column("transactions", "balance_reverted_at", "TEXT")
        ensure_column("transactions", "balance_reverted_by", "INTEGER")
        ensure_column("transactions", "balance_reverted_reason", "TEXT")

        ensure_column("ownership_transfers", "username", "TEXT")
        cursor.execute("""
            UPDATE plans
            SET access_level = 'all'
            WHERE access_level IS NULL OR TRIM(access_level) = ''
        """)
        cursor.execute("""
            UPDATE plans
            SET display_context = 'all'
            WHERE display_context IS NULL OR TRIM(display_context) = ''
        """)
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_segment_users_user_id ON segment_users(user_id)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_plan_segments_plan_id ON plan_segments(plan_id)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_plan_segments_segment_id ON plan_segments(segment_id)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_volume_package_segments_package_id ON volume_package_segments(package_id)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_volume_package_segments_segment_id ON volume_package_segments(segment_id)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_volume_package_categories_package_id ON volume_package_categories(package_id)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_volume_package_categories_category ON volume_package_categories(category)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_transactions_status_created_at ON transactions(status, created_at)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_transactions_photo_hash ON transactions(photo_hash)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_orders_username_status ON orders(username, status)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_orders_conversion_eligibility ON orders(user_id, status, eligible_for_conversion)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_orders_old_limited_service ON orders(old_limited_service)")
        # A plain UNIQUE index is enough here: SQLite allows multiple NULL values,
        # and this form is compatible with older SQLite builds that do not support partial indexes.
        cursor.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_orders_replaced_from_service_id ON orders(replaced_from_service_id)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_order_volume_allocations_order_id ON order_volume_allocations(order_id)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_order_volume_allocations_user_id ON order_volume_allocations(user_id)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_volume_packages_archive_active ON volume_packages(is_archived, is_active)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_conversion_offer_logs_service_status ON conversion_offer_logs(service_id, status)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_conversion_offer_logs_user_status ON conversion_offer_logs(user_id, status)")
        cursor.execute("DROP TABLE IF EXISTS speed_limits")

        normalize_datetime_column("feedbacks", "created_at")
        normalize_datetime_column("orders", "created_at")
        normalize_datetime_column("transactions", "created_at")
        normalize_datetime_column("transactions", "submitted_at")
        normalize_datetime_column("transactions", "admin_reviewed_at")
        normalize_datetime_column("transactions", "accounting_reviewed_at")
        normalize_datetime_column("transactions", "balance_reverted_at")
        normalize_datetime_column("users", "created_at")
        normalize_datetime_column("ownership_transfers", "transferred_at")
        normalize_datetime_column("orders", "closed_by_conversion_at")
        normalize_datetime_column("orders", "last_conversion_notification_at")
        normalize_datetime_column("orders", "last_renewal_offer_notification_at")
        normalize_datetime_column("segments", "created_at")
        normalize_datetime_column("segment_users", "created_at")
        normalize_datetime_column("plan_segments", "created_at")
        normalize_datetime_column("volume_package_segments", "created_at")
        normalize_datetime_column("volume_package_categories", "created_at")
        normalize_datetime_column("volume_packages", "created_at")
        normalize_datetime_column("volume_packages", "updated_at")
        normalize_datetime_column("order_volume_allocations", "created_at")
        normalize_datetime_column("order_volume_allocations", "applied_at")
        normalize_datetime_column("conversion_offer_logs", "notification_sent_at")
        normalize_datetime_column("conversion_offer_logs", "viewed_at")
        normalize_datetime_column("conversion_offer_logs", "selected_at")
        normalize_datetime_column("conversion_offer_logs", "confirmed_at")
        normalize_datetime_column("conversion_offer_logs", "converted_at")
        normalize_datetime_column("conversion_offer_logs", "created_at")
        normalize_datetime_column("conversion_offer_logs", "updated_at")
        initialize_runtime_settings_schema(cursor)
        conn.commit()


def add_user(user_id, first_name, username, role):
    with sqlite3.connect(DB_PATH) as conn:
        cursor = conn.cursor()
        cursor.execute("""
                       INSERT
                       OR IGNORE INTO users (id, first_name, username, role, created_at)
            VALUES (?, ?, ?, ?, ?)
                       """, (user_id, first_name, username, role, _now_text()))
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

VALID_PLAN_DISPLAY_CONTEXTS = {"all", "purchase", "renew", "agent"}
VALID_PLAN_ACCESS_LEVELS = {"all", "user", "agent", "admin"}


def _normalize_plan_display_context(value: Optional[str]) -> str:
    normalized = (value or "all").strip().lower()
    return normalized if normalized in VALID_PLAN_DISPLAY_CONTEXTS else "all"


def _normalize_plan_access_level(value: Optional[str]) -> str:
    normalized = (value or "all").strip().lower()
    return normalized if normalized in VALID_PLAN_ACCESS_LEVELS else "all"


def _normalize_segment_slug(value: str) -> str:
    slug = (value or "").strip().lower().replace(" ", "_").replace("-", "_")
    while "__" in slug:
        slug = slug.replace("__", "_")
    return slug.strip("_")


def _normalize_volume_package_category(value: str) -> str:
    category = (value or "").strip().lower().replace("-", "_").replace(" ", "_")
    while "__" in category:
        category = category.replace("__", "_")
    return category.strip("_")


def _get_user_role_for_plans(conn: sqlite3.Connection, user_id: Optional[int]) -> Optional[str]:
    if user_id is None:
        return None

    cur = conn.cursor()
    cur.execute("SELECT role FROM users WHERE id = ?", (user_id,))
    row = cur.fetchone()
    role = row[0] if row else None
    role = (role or "user").strip().lower()
    return role if role in VALID_PLAN_ACCESS_LEVELS else "user"


def _apply_plan_audience_filters(base_query: str, params: List, user_id: Optional[int], role: Optional[str],
                                 display_context: Optional[str]):
    clauses = [base_query]

    if display_context:
        clauses.append("""
            AND (
                COALESCE(NULLIF(display_context, ''), 'all') = 'all'
                OR COALESCE(NULLIF(display_context, ''), 'all') = ?
            )
        """)
        params.append(_normalize_plan_display_context(display_context))

    if role and role != "admin":
        clauses.append("""
            AND COALESCE(NULLIF(access_level, ''), 'all') IN ('all', ?)
        """)
        params.append(_normalize_plan_access_level(role))

        clauses.append("""
            AND (
                NOT EXISTS (
                    SELECT 1
                    FROM plan_segments ps
                    JOIN segments s ON s.id = ps.segment_id
                    WHERE ps.plan_id = plans.id
                      AND COALESCE(s.is_active, 1) = 1
                )
                OR EXISTS (
                    SELECT 1
                    FROM plan_segments ps
                    JOIN segments s ON s.id = ps.segment_id
                    JOIN segment_users su ON su.segment_id = ps.segment_id
                    WHERE ps.plan_id = plans.id
                      AND COALESCE(s.is_active, 1) = 1
                      AND su.user_id = ?
                )
            )
        """)
        params.append(user_id)

    return "\n".join(clauses), params


def _get_context_plans(display_context: Optional[str] = None, user_id: Optional[int] = None):
    with sqlite3.connect(DB_PATH) as conn:
        conn.row_factory = sqlite3.Row
        role = _get_user_role_for_plans(conn, user_id)
        query, params = _apply_plan_audience_filters(
            """
            SELECT
                id,
                name,
                volume_gb,
                duration_months,
                duration_days,
                max_users,
                price,
                group_name,
                category,
                location,
                is_unlimited,
                COALESCE(NULLIF(access_level, ''), 'all') AS access_level,
                COALESCE(NULLIF(display_context, ''), 'all') AS display_context
            FROM plans
            WHERE visible = 1
              AND COALESCE(is_archived, 0) = 0
            """,
            [],
            user_id=user_id,
            role=role,
            display_context=display_context,
        )
        query = f"{query}\nORDER BY order_priority DESC, id ASC"
        cursor = conn.cursor()
        cursor.execute(query, params)
        return [dict(row) for row in cursor.fetchall()]

def add_plan(name, volume_gb, duration_days, max_users, price):
    with sqlite3.connect(DB_PATH) as conn:
        cursor = conn.cursor()
        cursor.execute("""
                       INSERT INTO plans (name, volume_gb, duration_days, max_users, price, access_level, display_context)
                       VALUES (?, ?, ?, ?, ?, 'all', 'all')
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
                group_name,
                category,
                location,
                COALESCE(NULLIF(access_level, ''), 'all') AS access_level,
                COALESCE(NULLIF(display_context, ''), 'all') AS display_context
            FROM plans
            WHERE visible = 1
              AND COALESCE(is_archived, 0) = 0
            ORDER BY order_priority DESC, id ASC
        """)
        return [dict(row) for row in cursor.fetchall()]


def get_plans_for_admin(include_archived: bool = False):
    with sqlite3.connect(DB_PATH) as conn:
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        query = """
            SELECT
                id,
                name,
                volume_gb,
                duration_months,
                duration_days,
                max_users,
                price,
                order_priority,
                visible,
                location,
                is_unlimited,
                group_name,
                COALESCE(is_archived, 0) AS is_archived,
                archived_at,
                COALESCE(NULLIF(access_level, ''), 'all') AS access_level,
                COALESCE(NULLIF(display_context, ''), 'all') AS display_context
            FROM plans
        """
        params: list = []
        if include_archived:
            query += "\nWHERE COALESCE(is_archived, 0) = 1"
        else:
            query += "\nWHERE COALESCE(is_archived, 0) = 0"
        query += "\nORDER BY id ASC"
        cursor.execute(query, params)
        return [dict(row) for row in cursor.fetchall()]


def set_plan_archived(plan_id: int, archived: bool):
    archived_value = 1 if archived else 0
    archived_at = _now_text() if archived else None
    with sqlite3.connect(DB_PATH) as conn:
        cursor = conn.cursor()
        cursor.execute("""
            UPDATE plans
            SET is_archived = ?,
                archived_at = ?,
                visible = CASE WHEN ? = 1 THEN 0 ELSE visible END
            WHERE id = ?
        """, (archived_value, archived_at, archived_value, plan_id))
        conn.commit()
        return cursor.rowcount > 0


def get_buy_plans(user_id: Optional[int] = None):
    return _get_context_plans(display_context="purchase", user_id=user_id)


def get_renew_plans(user_id: Optional[int] = None):
    """Ù¾Ù„Ù†â€ŒÙ‡Ø§ÛŒÛŒ Ú©Ù‡ Ø¨Ø±Ø§ÛŒ ØªÙ…Ø¯ÛŒØ¯ Ù†Ù…Ø§ÛŒØ´ Ø¯Ø§Ø¯Ù‡ Ù…ÛŒâ€ŒØ´ÙˆÙ†Ø¯"""
    return _get_context_plans(display_context="renew", user_id=user_id)


def get_agent_plans(user_id: Optional[int] = None):
    """Ù¾Ù„Ù†â€ŒÙ‡Ø§ÛŒÛŒ Ú©Ù‡ Ø¨Ø±Ø§ÛŒ Ù†Ù…Ø§ÛŒÙ†Ø¯Ù‡â€ŒÙ‡Ø§ Ù†Ù…Ø§ÛŒØ´ Ø¯Ø§Ø¯Ù‡ Ù…ÛŒâ€ŒØ´ÙˆÙ†Ø¯"""
    return _get_context_plans(display_context="agent", user_id=user_id)


def get_all_segments():
    with sqlite3.connect(DB_PATH) as conn:
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        cursor.execute("""
            SELECT
                s.id,
                s.slug,
                s.title,
                s.description,
                s.is_active,
                s.created_at,
                COALESCE(u.user_count, 0) AS user_count,
                COALESCE(p.plan_count, 0) AS plan_count
            FROM segments s
            LEFT JOIN (
                SELECT segment_id, COUNT(*) AS user_count
                FROM segment_users
                GROUP BY segment_id
            ) u ON u.segment_id = s.id
            LEFT JOIN (
                SELECT segment_id, COUNT(*) AS plan_count
                FROM plan_segments
                GROUP BY segment_id
            ) p ON p.segment_id = s.id
            ORDER BY COALESCE(s.is_active, 1) DESC, s.title COLLATE NOCASE ASC, s.id ASC
        """)
        return [dict(row) for row in cursor.fetchall()]


def get_segment(segment_id: int):
    with sqlite3.connect(DB_PATH) as conn:
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        cursor.execute("""
            SELECT
                s.id,
                s.slug,
                s.title,
                s.description,
                s.is_active,
                s.created_at,
                COALESCE(u.user_count, 0) AS user_count,
                COALESCE(p.plan_count, 0) AS plan_count
            FROM segments s
            LEFT JOIN (
                SELECT segment_id, COUNT(*) AS user_count
                FROM segment_users
                GROUP BY segment_id
            ) u ON u.segment_id = s.id
            LEFT JOIN (
                SELECT segment_id, COUNT(*) AS plan_count
                FROM plan_segments
                GROUP BY segment_id
            ) p ON p.segment_id = s.id
            WHERE s.id = ?
            LIMIT 1
        """, (segment_id,))
        row = cursor.fetchone()
        return dict(row) if row else None


def get_segment_by_slug(slug: str):
    normalized = _normalize_segment_slug(slug)
    if not normalized:
        return None
    with sqlite3.connect(DB_PATH) as conn:
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM segments WHERE slug = ? LIMIT 1", (normalized,))
        row = cursor.fetchone()
        return dict(row) if row else None


def create_segment(slug: str, title: str, description: Optional[str] = None):
    normalized = _normalize_segment_slug(slug)
    clean_title = (title or "").strip()
    if not normalized or not clean_title:
        raise ValueError("segment slug and title are required")

    with sqlite3.connect(DB_PATH) as conn:
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO segments (slug, title, description)
            VALUES (?, ?, ?)
        """, (normalized, clean_title, (description or "").strip() or None))
        conn.commit()
        return cursor.lastrowid


def update_segment_info(segment_id: int, title: str, description: Optional[str] = None):
    with sqlite3.connect(DB_PATH) as conn:
        cursor = conn.cursor()
        cursor.execute("""
            UPDATE segments
            SET title = ?,
                description = ?
            WHERE id = ?
        """, ((title or "").strip(), (description or "").strip() or None, segment_id))
        conn.commit()


def set_segment_active(segment_id: int, is_active: int):
    with sqlite3.connect(DB_PATH) as conn:
        cursor = conn.cursor()
        cursor.execute("""
            UPDATE segments
            SET is_active = ?
            WHERE id = ?
        """, (1 if is_active else 0, segment_id))
        conn.commit()


def delete_segment(segment_id: int):
    with sqlite3.connect(DB_PATH) as conn:
        cursor = conn.cursor()
        cursor.execute("DELETE FROM segment_users WHERE segment_id = ?", (segment_id,))
        cursor.execute("DELETE FROM plan_segments WHERE segment_id = ?", (segment_id,))
        cursor.execute("DELETE FROM volume_package_segments WHERE segment_id = ?", (segment_id,))
        cursor.execute("DELETE FROM segments WHERE id = ?", (segment_id,))
        conn.commit()


def delete_volume_package_audience(package_id: int):
    with sqlite3.connect(DB_PATH) as conn:
        cursor = conn.cursor()
        cursor.execute("DELETE FROM volume_package_segments WHERE package_id = ?", (package_id,))
        cursor.execute("DELETE FROM volume_package_categories WHERE package_id = ?", (package_id,))
        conn.commit()


def get_segment_users(segment_id: int, limit: int = 30):
    with sqlite3.connect(DB_PATH) as conn:
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        cursor.execute("""
            SELECT
                u.id,
                u.first_name,
                u.last_name,
                u.username,
                u.role,
                su.created_at
            FROM segment_users su
            JOIN users u ON u.id = su.user_id
            WHERE su.segment_id = ?
            ORDER BY su.created_at DESC, u.id ASC
            LIMIT ?
        """, (segment_id, limit))
        return [dict(row) for row in cursor.fetchall()]


def get_segment_plans(segment_id: int, limit: int = 30):
    with sqlite3.connect(DB_PATH) as conn:
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        cursor.execute("""
            SELECT
                p.id,
                p.name,
                p.price,
                COALESCE(NULLIF(p.access_level, ''), 'all') AS access_level,
                COALESCE(NULLIF(p.display_context, ''), 'all') AS display_context,
                ps.created_at
            FROM plan_segments ps
            JOIN plans p ON p.id = ps.plan_id
            WHERE ps.segment_id = ?
            ORDER BY p.order_priority DESC, p.id ASC
            LIMIT ?
        """, (segment_id, limit))
        return [dict(row) for row in cursor.fetchall()]


def get_plan_segments(plan_id: int):
    with sqlite3.connect(DB_PATH) as conn:
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        cursor.execute("""
            SELECT
                s.id,
                s.slug,
                s.title,
                s.description,
                s.is_active
            FROM plan_segments ps
            JOIN segments s ON s.id = ps.segment_id
            WHERE ps.plan_id = ?
            ORDER BY s.title COLLATE NOCASE ASC, s.id ASC
        """, (plan_id,))
        return [dict(row) for row in cursor.fetchall()]


def add_users_to_segment(segment_id: int, user_ids: List[int]) -> int:
    cleaned_ids = sorted({int(user_id) for user_id in user_ids})
    if not cleaned_ids:
        return 0

    with sqlite3.connect(DB_PATH) as conn:
        cursor = conn.cursor()
        total_added = 0
        for user_id in cleaned_ids:
            cursor.execute("""
                INSERT OR IGNORE INTO segment_users (segment_id, user_id)
                VALUES (?, ?)
            """, (segment_id, user_id))
            total_added += cursor.rowcount
        conn.commit()
        return total_added


def remove_users_from_segment(segment_id: int, user_ids: List[int]) -> int:
    cleaned_ids = sorted({int(user_id) for user_id in user_ids})
    if not cleaned_ids:
        return 0

    with sqlite3.connect(DB_PATH) as conn:
        cursor = conn.cursor()
        cursor.executemany("""
            DELETE FROM segment_users
            WHERE segment_id = ? AND user_id = ?
        """, [(segment_id, user_id) for user_id in cleaned_ids])
        conn.commit()
        return cursor.rowcount


def attach_segments_to_plan(plan_id: int, segment_ids: List[int]) -> int:
    cleaned_ids = sorted({int(segment_id) for segment_id in segment_ids})
    if not cleaned_ids:
        return 0

    with sqlite3.connect(DB_PATH) as conn:
        cursor = conn.cursor()
        total_added = 0
        for segment_id in cleaned_ids:
            cursor.execute("""
                INSERT OR IGNORE INTO plan_segments (plan_id, segment_id)
                VALUES (?, ?)
            """, (plan_id, segment_id))
            total_added += cursor.rowcount
        conn.commit()
        return total_added


def detach_segments_from_plan(plan_id: int, segment_ids: List[int]) -> int:
    cleaned_ids = sorted({int(segment_id) for segment_id in segment_ids})
    if not cleaned_ids:
        return 0

    with sqlite3.connect(DB_PATH) as conn:
        cursor = conn.cursor()
        cursor.executemany("""
            DELETE FROM plan_segments
            WHERE plan_id = ? AND segment_id = ?
        """, [(plan_id, segment_id) for segment_id in cleaned_ids])
        conn.commit()
        return cursor.rowcount


def update_plan_access_level(plan_id: int, access_level: str):
    normalized = _normalize_plan_access_level(access_level)
    with sqlite3.connect(DB_PATH) as conn:
        cursor = conn.cursor()
        cursor.execute("""
            UPDATE plans
            SET access_level = ?
            WHERE id = ?
        """, (normalized, plan_id))
        conn.commit()


def update_plan_display_context(plan_id: int, display_context: str):
    normalized = _normalize_plan_display_context(display_context)
    with sqlite3.connect(DB_PATH) as conn:
        cursor = conn.cursor()
        cursor.execute("""
            UPDATE plans
            SET display_context = ?
            WHERE id = ?
        """, (normalized, plan_id))
        conn.commit()


def resolve_user_identifiers(identifiers: List[str]):
    resolved: List[Dict] = []
    missing: List[str] = []
    seen_user_ids = set()

    with sqlite3.connect(DB_PATH) as conn:
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()

        for raw_identifier in identifiers:
            token = (raw_identifier or "").strip()
            if not token:
                continue

            row = None
            if token.lstrip("-").isdigit():
                cursor.execute("""
                    SELECT id, first_name, last_name, username, role
                    FROM users
                    WHERE id = ?
                    LIMIT 1
                """, (int(token),))
                row = cursor.fetchone()
            else:
                username = token.lstrip("@")
                cursor.execute("""
                    SELECT id, first_name, last_name, username, role
                    FROM users
                    WHERE LOWER(username) = LOWER(?)
                    LIMIT 1
                """, (username,))
                row = cursor.fetchone()

            if row is None:
                missing.append(token)
                continue

            row_dict = dict(row)
            if row_dict["id"] in seen_user_ids:
                continue

            seen_user_ids.add(row_dict["id"])
            resolved.append(row_dict)

    return resolved, missing


def get_all_user_ids_for_messaging() -> List[int]:
    with sqlite3.connect(DB_PATH) as conn:
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT id
            FROM users
            ORDER BY id ASC
            """
        )
        return [int(row[0]) for row in cursor.fetchall()]


def get_user_ids_by_min_balance(min_balance: int) -> List[int]:
    with sqlite3.connect(DB_PATH) as conn:
        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT id
            FROM users
            WHERE COALESCE(balance, 0) >= ?
            ORDER BY COALESCE(balance, 0) DESC, id ASC
            """,
            (int(min_balance),),
        )
        return [int(row[0]) for row in cursor.fetchall()]


def get_user_ids_by_segment_ids(segment_ids: List[int], only_active_segments: bool = True) -> List[int]:
    cleaned_ids = sorted({int(segment_id) for segment_id in segment_ids})
    if not cleaned_ids:
        return []

    placeholders = ", ".join("?" for _ in cleaned_ids)
    with sqlite3.connect(DB_PATH) as conn:
        cursor = conn.cursor()
        if only_active_segments:
            cursor.execute(
                f"""
                SELECT DISTINCT su.user_id
                FROM segment_users su
                JOIN segments s ON s.id = su.segment_id
                WHERE su.segment_id IN ({placeholders})
                  AND COALESCE(s.is_active, 1) = 1
                ORDER BY su.user_id ASC
                """,
                cleaned_ids,
            )
        else:
            cursor.execute(
                f"""
                SELECT DISTINCT su.user_id
                FROM segment_users su
                WHERE su.segment_id IN ({placeholders})
                ORDER BY su.user_id ASC
                """,
                cleaned_ids,
            )
        return [int(row[0]) for row in cursor.fetchall()]


def get_all_plans_for_admin_audience():
    with sqlite3.connect(DB_PATH) as conn:
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        cursor.execute("""
            SELECT
                p.id,
                p.name,
                p.price,
                p.visible,
                p.category,
                p.location,
                COALESCE(NULLIF(p.access_level, ''), 'all') AS access_level,
                COALESCE(NULLIF(p.display_context, ''), 'all') AS display_context,
                COALESCE(ps.segment_count, 0) AS segment_count
            FROM plans p
            LEFT JOIN (
                SELECT plan_id, COUNT(*) AS segment_count
                FROM plan_segments
                GROUP BY plan_id
            ) ps ON ps.plan_id = p.id
            ORDER BY p.order_priority DESC, p.id ASC
        """)
        return [dict(row) for row in cursor.fetchall()]


def get_plan_for_admin_audience(plan_id: int):
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
                visible,
                category,
                location,
                group_name,
                COALESCE(NULLIF(access_level, ''), 'all') AS access_level,
                COALESCE(NULLIF(display_context, ''), 'all') AS display_context
            FROM plans
            WHERE id = ?
            LIMIT 1
        """, (plan_id,))
        row = cursor.fetchone()
        return dict(row) if row else None


def get_next_account_number():
    with sqlite3.connect(DB_PATH) as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT MAX(account_number) FROM orders")
        result = cursor.fetchone()
        max_account = result[0] if result[0] is not None else 100000
        return max_account + 1


def insert_order(user_id, plan_id, username, price, status, volume_gb):
    created_at = _now_text()
    with sqlite3.connect(DB_PATH) as conn:
        cursor = conn.cursor()
        cursor.execute('''
                       INSERT INTO orders (user_id, plan_id, username, price, created_at, status, volume_gb)
                       VALUES (?, ?, ?, ?, ?, ?, ?)
                       ''', (user_id, plan_id, username, price, created_at, status, volume_gb))
        order_id = cursor.lastrowid  # Ú¯Ø±ÙØªÙ† Ø¢ÛŒØ¯ÛŒ Ø¢Ø®Ø±ÛŒÙ† Ø±Ø¯ÛŒÙ ÙˆØ§Ø±Ø¯Ø´Ø¯Ù‡
        conn.commit()
        return order_id


def insert_renewed_order(user_id, plan_id, username, price, status, is_renewal_of_order, volume_gb):
    created_at = _now_text()
    with sqlite3.connect(DB_PATH) as conn:
        cursor = conn.cursor()
        cursor.execute('''
                       INSERT INTO orders (user_id, plan_id, username, price, created_at, status, is_renewal_of_order, volume_gb)
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                       ''', (user_id, plan_id, username, price, created_at, status, is_renewal_of_order, volume_gb))
        order_id = cursor.lastrowid  # Ú¯Ø±ÙØªÙ† Ø¢ÛŒØ¯ÛŒ Ø¢Ø®Ø±ÛŒÙ† Ø±Ø¯ÛŒÙ ÙˆØ§Ø±Ø¯Ø´Ø¯Ù‡
        conn.commit()
        return order_id


def insert_renewed_order_with_auto_renew(user_id, plan_id, username, price, status, is_renewal_of_order, volume_gb,
                                         auto_renew):
    created_at = _now_text()
    with sqlite3.connect(DB_PATH) as conn:
        cursor = conn.cursor()
        cursor.execute('''
                       INSERT INTO orders (user_id, plan_id, username, price, created_at, status, is_renewal_of_order, volume_gb, auto_renew)
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?,?)
                       ''', (
            user_id, plan_id, username, price, created_at, status, is_renewal_of_order, volume_gb, auto_renew))
        order_id = cursor.lastrowid  # Ú¯Ø±ÙØªÙ† Ø¢ÛŒØ¯ÛŒ Ø¢Ø®Ø±ÛŒÙ† Ø±Ø¯ÛŒÙ ÙˆØ§Ø±Ø¯Ø´Ø¯Ù‡
        conn.commit()
        return order_id


def update_user_balance(user_id, new_balance):
    with sqlite3.connect(DB_PATH) as conn:
        cursor = conn.cursor()
        cursor.execute("UPDATE users SET balance = ? WHERE id = ?", (new_balance, user_id))
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
    created_at = _now_text()
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
        return result[0] if result else 0


# Ù¾ÛŒØ¯Ø§ Ú©Ø±Ø¯Ù† Ø§ÙˆÙ„ÛŒÙ† Ø§Ú©Ø§Ù†Øª Ø¢Ø²Ø§Ø¯
def find_free_account():
    with sqlite3.connect(DB_PATH) as conn:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT id, username, password FROM accounts
            WHERE status = 'free'
            LIMIT 1
        """)
        return cursor.fetchone()  # Ø§Ú¯Ø± None Ø¨Ø±Ú¯Ø±Ø¯Ù‡ ÛŒØ¹Ù†ÛŒ Ø§Ú©Ø§Ù†Øª Ø¢Ø²Ø§Ø¯ Ù†ÛŒØ³Øª


# Ø±Ø²Ø±Ùˆ Ø§Ú©Ø§Ù†Øª Ø¨Ø±Ø§ÛŒ ÛŒÚ© Ø³ÙØ§Ø±Ø´ Ø®Ø§Øµ
def assign_account_to_order(account_id: int, order_id: Optional[int] = None):
    with sqlite3.connect(DB_PATH) as conn:
        cursor = conn.cursor()
        if order_id is None:
            cursor.execute("""
                UPDATE accounts
                SET status = 'assigned'
                WHERE id = ?
            """, (account_id,))
        else:
            cursor.execute("""
                UPDATE accounts
                SET status = 'assigned',
                    order_id = ?
                WHERE id = ?
            """, (order_id, account_id))
        conn.commit()


# ØªØºÛŒÛŒØ± ÙˆØ¶Ø¹ÛŒØª Ø§Ú©Ø§Ù†Øª (Ù…Ø«Ù„Ø§Ù‹ Ø¢Ø²Ø§Ø¯ Ú©Ø±Ø¯Ù† Ø¨Ø¹Ø¯ Ø§Ø² Ø§Ù†Ù‚Ø¶Ø§)
def update_account_status(account_id: int, new_status: str):
    with sqlite3.connect(DB_PATH) as conn:
        cursor = conn.cursor()
        if new_status == "free":
            cursor.execute("""
                UPDATE accounts
                SET status = ?,
                    order_id = NULL
                WHERE id = ?
            """, (new_status, account_id))
        else:
            cursor.execute("""
                UPDATE accounts
                SET status = ?
                WHERE id = ?
            """, (new_status, account_id))
        conn.commit()


def release_account_by_username(username: str):
    with sqlite3.connect(DB_PATH) as conn:
        cursor = conn.cursor()
        cursor.execute("""
            UPDATE accounts
            SET status = 'free',
                order_id = NULL
            WHERE username = ?
        """, (username,))
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


def update_order_conversion_markers(order_id: int, enabled: bool):
    with sqlite3.connect(DB_PATH) as conn:
        cursor = conn.cursor()
        cursor.execute(
            """
            UPDATE orders
            SET eligible_for_conversion = ?,
                old_limited_service = ?,
                last_conversion_notification_at = CASE WHEN ? = 1 THEN last_conversion_notification_at ELSE NULL END
            WHERE id = ?
            """,
            (1 if enabled else 0, 1 if enabled else 0, 1 if enabled else 0, order_id),
        )
        conn.commit()
        return cursor.rowcount > 0


def get_user_services(user_id: int):
    with sqlite3.connect(DB_PATH) as conn:
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        cursor.execute("""
                SELECT
                orders.id,
                orders.username,
                accounts.password,
                plans.name AS plan_name,
                plans.is_unlimited,
                orders.starts_at,
                orders.expires_at,
                orders.status,
                orders.created_at,
                orders.volume_gb,
                orders.extra_volume_gb,
                orders.usage_total_mb,
                orders.usage_last_update
                FROM orders
                JOIN plans ON orders.plan_id = plans.id
                JOIN users ON orders.user_id = users.id
                JOIN accounts ON orders.username = accounts.username
                WHERE users.id = ? and orders.status not in ("renewed", "archived", "canceled", "converted")
                ORDER by orders.username,orders.created_at
            """, (user_id,))
        return [dict(row) for row in cursor.fetchall()]


def get_user_services_for_password_change(user_id: int):
    with sqlite3.connect(DB_PATH) as conn:
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        cursor.execute("""
            SELECT
                a.id AS account_id,
                a.username,
                a.password,
                (
                    SELECT p.name
                    FROM orders o2
                    LEFT JOIN plans p ON p.id = o2.plan_id
                    WHERE o2.user_id = ?
                      AND o2.username = a.username
                      AND o2.status NOT IN ('archived', 'renewed', 'canceled', 'converted', 'waiting_for_payment')
                    ORDER BY o2.created_at DESC, o2.id DESC
                    LIMIT 1
                ) AS plan_name,
                (
                    SELECT o3.status
                    FROM orders o3
                    WHERE o3.user_id = ?
                      AND o3.username = a.username
                      AND o3.status NOT IN ('archived', 'renewed', 'canceled', 'converted', 'waiting_for_payment')
                    ORDER BY o3.created_at DESC, o3.id DESC
                    LIMIT 1
                ) AS status
            FROM accounts a
            WHERE EXISTS (
                SELECT 1
                FROM orders o
                WHERE o.user_id = ?
                  AND o.username = a.username
                  AND o.status NOT IN ('archived', 'renewed', 'canceled', 'converted', 'waiting_for_payment')
            )
            ORDER BY a.username ASC
        """, (user_id, user_id, user_id))
        return [dict(row) for row in cursor.fetchall()]


def get_active_orders_without_time() -> List[Dict]:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row  # Ø®Ø±ÙˆØ¬ÛŒ Ø¨Ù‡ Ø´Ú©Ù„ dict
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
            expires_at_str = row['expires_at']  # Ù…Ø«Ù„Ø§Ù‹: "1403-04-16 09:05"
            expires_at = jdatetime.datetime.strptime(expires_at_str, "%Y-%m-%d %H:%M")
            now_jdt = jdatetime.datetime.strptime(now, "%Y-%m-%d %H:%M:%S")

            if expires_at < now_jdt:
                cursor.execute("""
                    UPDATE orders
                    SET status = 'expired'
                    WHERE id = ?
                """, (row['id'],))
        except Exception as e:
            print(f"Ø®Ø·Ø§ Ø¯Ø± Ø¨Ø±Ø±Ø³ÛŒ Ø³ÙØ§Ø±Ø´ {row['id']}: {e}")

    conn.commit()
    conn.close()


def archive_old_orders():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    now = jdatetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    cursor.execute("""
        SELECT id, expires_at FROM orders
        WHERE status IN ('expired', 'renewed', 'converted')
    """)
    rows = cursor.fetchall()

    for row in rows:
        try:
            expires_at_str = row['expires_at']  # Ù…Ø«Ù„Ø§Ù‹: "1403-04-16 09:05"
            expires_at = jdatetime.datetime.strptime(expires_at_str, "%Y-%m-%d %H:%M")
            now_jdt = jdatetime.datetime.strptime(now, "%Y-%m-%d %H:%M:%S")
            thirty_days_ago_jdt = now_jdt - jdatetime.timedelta(days=45)
            if expires_at < thirty_days_ago_jdt:
                cursor.execute("""
                UPDATE orders
                SET status = 'archived'
                WHERE id = ?
                """, (row['id'],))

        except Exception as e:
            print(f"Ø®Ø·Ø§ Ø¯Ø± Ø¨Ø±Ø±Ø³ÛŒ Ø³ÙØ§Ø±Ø´ {row['id']}: {e}")

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
            WHERE user_id = ?
              AND status IN ('active', 'expired', 'waiting_for_renewal_not_paid')
              AND expires_at IS NOT NULL
            ORDER BY
                CASE
                    WHEN status = 'waiting_for_renewal_not_paid' THEN 0
                    WHEN status = 'active' THEN 1
                    ELSE 2
                END,
                username ASC
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


def get_waiting_for_payment_orders():
    with sqlite3.connect(DB_PATH) as conn:
        conn.row_factory = sqlite3.Row
        cur = conn.cursor()
        cur.execute("""
                SELECT * FROM orders
                WHERE status = 'waiting_for_payment'
                ORDER BY created_at ASC
            """)
        return [dict(r) for r in cur.fetchall()]


def get_user_pending_purchase_orders(user_id: int):
    with sqlite3.connect(DB_PATH) as conn:
        conn.row_factory = sqlite3.Row
        cur = conn.cursor()
        cur.execute("""
            SELECT
                o.id,
                o.user_id,
                o.plan_id,
                o.username,
                o.price,
                o.status,
                o.created_at,
                p.name AS plan_name
            FROM orders o
            LEFT JOIN plans p ON p.id = o.plan_id
            WHERE o.user_id = ?
              AND o.status = 'waiting_for_payment'
              AND o.is_renewal_of_order IS NULL
            ORDER BY o.created_at DESC
        """, (user_id,))
        return [dict(r) for r in cur.fetchall()]


def get_pending_renewal_order(base_order_id: int):
    with sqlite3.connect(DB_PATH) as conn:
        conn.row_factory = sqlite3.Row
        cur = conn.cursor()
        cur.execute("""
            SELECT
                o.*,
                p.name AS plan_name
            FROM orders o
            LEFT JOIN plans p ON p.id = o.plan_id
            WHERE o.status = 'waiting_for_payment'
              AND o.is_renewal_of_order = ?
            ORDER BY o.created_at DESC
            LIMIT 1
        """, (base_order_id,))
        row = cur.fetchone()
        return dict(row) if row else None


def get_order_data(order_id):
    with sqlite3.connect(DB_PATH) as conn:
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        cursor.execute("""
                SELECT * FROM orders
                WHERE id = ?
            """, (order_id,))
        row = cursor.fetchone()
        return dict(row) if row else None


def get_order_with_plan(order_id: int):
    with sqlite3.connect(DB_PATH) as conn:
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        cursor.execute("""
            SELECT
                o.*,
                p.name AS plan_name,
                p.group_name,
                p.duration_days,
                p.duration_months,
                p.is_unlimited,
                COALESCE(p.is_archived, 0) AS plan_is_archived,
                u.first_name,
                u.last_name,
                u.username AS telegram_username
            FROM orders o
            LEFT JOIN plans p ON p.id = o.plan_id
            LEFT JOIN users u ON u.id = o.user_id
            WHERE o.id = ?
            LIMIT 1
        """, (order_id,))
        row = cursor.fetchone()
        return dict(row) if row else None


def search_orders_for_admin(keyword: str, limit: int = 30, archived_only: bool = False):
    clean = (keyword or "").strip()
    if not clean:
        return []

    like_value = f"%{clean}%"
    status_filter = "COALESCE(o.status, '') = 'archived'" if archived_only else "COALESCE(o.status, '') != 'archived'"
    with sqlite3.connect(DB_PATH) as conn:
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        cursor.execute("""
            SELECT
                o.id,
                o.user_id,
                o.username,
                o.status,
                o.price,
                o.created_at,
                o.plan_id,
                o.extra_volume_gb,
                p.name AS plan_name,
                u.first_name,
                u.last_name
            FROM orders o
            LEFT JOIN plans p ON p.id = o.plan_id
            LEFT JOIN users u ON u.id = o.user_id
            WHERE (
                   CAST(o.id AS TEXT) = ?
                OR CAST(o.user_id AS TEXT) = ?
                OR LOWER(COALESCE(o.username, '')) LIKE LOWER(?)
            )
              AND """ + status_filter + """
            ORDER BY o.id ASC
            LIMIT ?
        """, (clean, clean, like_value, int(limit)))
        return [dict(row) for row in cursor.fetchall()]


def get_order_children(parent_order_id: int):
    with sqlite3.connect(DB_PATH) as conn:
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        cursor.execute("""
            SELECT *
            FROM orders
            WHERE is_renewal_of_order = ?
            ORDER BY id DESC
        """, (parent_order_id,))
        return [dict(row) for row in cursor.fetchall()]


def get_open_orders_by_username(username: str, exclude_order_ids: Optional[List[int]] = None):
    exclude_order_ids = exclude_order_ids or []
    placeholders = ", ".join("?" for _ in exclude_order_ids)
    params: list = [username]
    query = """
        SELECT *
        FROM orders
        WHERE username = ?
          AND status NOT IN ('canceled', 'renewed', 'archived', 'converted')
    """
    if placeholders:
        query += f"\nAND id NOT IN ({placeholders})"
        params.extend(exclude_order_ids)
    with sqlite3.connect(DB_PATH) as conn:
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        cursor.execute(query, params)
        return [dict(row) for row in cursor.fetchall()]


def get_volume_services_for_user(user_id: int):
    with sqlite3.connect(DB_PATH) as conn:
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        cursor.execute("""
            SELECT
                o.id,
                o.user_id,
                o.username,
                o.status,
                o.price,
                o.volume_gb,
                o.extra_volume_gb,
                o.usage_total_mb,
                o.usage_applied_speed,
                o.starts_at,
                o.expires_at,
                p.name AS plan_name,
                p.group_name,
                p.is_unlimited
            FROM orders o
            JOIN plans p ON p.id = o.plan_id
            WHERE o.user_id = ?
              AND o.status IN ('active', 'waiting_for_renewal', 'waiting_for_renewal_not_paid', 'reserved')
              AND COALESCE(p.is_unlimited, 0) = 0
            ORDER BY o.username ASC, o.id DESC
        """, (user_id,))
        return [dict(row) for row in cursor.fetchall()]


def get_order_volume_purchase_history(order_id: int):
    with sqlite3.connect(DB_PATH) as conn:
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        cursor.execute("""
            SELECT
                id,
                order_id,
                user_id,
                package_id,
                package_name,
                source_type,
                status,
                volume_gb,
                price,
                note,
                admin_id,
                created_at,
                applied_at
            FROM order_volume_allocations
            WHERE order_id = ?
            ORDER BY id DESC
        """, (order_id,))
        return [dict(row) for row in cursor.fetchall()]


def get_order_plan_duration(order_id):
    with sqlite3.connect(DB_PATH) as conn:
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        cursor.execute("""
                SELECT duration_months FROM plans
                JOIN orders on orders.plan_id = plans.id
                WHERE orders.id = ?
            """, (order_id,))
        row = cursor.fetchone()
        return dict(row) if row else None


def get_order_plan_group_name(order_id):
    with sqlite3.connect(DB_PATH) as conn:
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        cursor.execute("""
                SELECT group_name FROM plans
                JOIN orders on orders.plan_id = plans.id
                WHERE orders.id = ?
            """, (order_id,))
        row = cursor.fetchone()
        return dict(row) if row else None


def get_orders_for_notifications(expires_at):
    with sqlite3.connect(DB_PATH) as conn:
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        cursor.execute("""
                SELECT
                    id,
                    user_id,
                    plan_id,
                    username,
                    expires_at,
                    status,
                    last_notif_level,
                    last_renewal_offer_notification_at
            FROM orders
            WHERE status IN ('active', 'waiting_for_renewal', 'waiting_for_renewal_not_paid')
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


def update_order_last_renewal_offer_notification_at(sent_at: str, order_id: int):
    with sqlite3.connect(DB_PATH) as conn:
        cursor = conn.cursor()
        cursor.execute(
            """
            UPDATE orders
            SET last_renewal_offer_notification_at = ?
            WHERE id = ?
            """,
            (sent_at, order_id),
        )
        conn.commit()


def get_order_usage(order_id: int):
    with sqlite3.connect(DB_PATH) as conn:
        cursor = conn.cursor()
        cursor.execute("""SELECT usage_total_mb FROM orders WHERE id = ?""", (order_id,))
        row = cursor.fetchone()
        return row[0] if row else 0


def get_orders_for_usage_notifications():
    with sqlite3.connect(DB_PATH) as conn:
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        cursor.execute("""
            SELECT
                o.id,
                o.user_id,
                o.username,
                o.volume_gb,
                o.extra_volume_gb,
                o.usage_total_mb,
                o.usage_notif_level,
                o.usage_lock_applied,
                u.message_name
            FROM orders o
            JOIN plans p ON p.id = o.plan_id
            LEFT JOIN users u ON u.id = o.user_id
            WHERE o.status IN ('active', 'waiting_for_renewal', 'waiting_for_renewal_not_paid')
              AND o.user_id IS NOT NULL
              AND o.username IS NOT NULL
              AND COALESCE(p.is_unlimited, 0) = 0
              AND (COALESCE(o.volume_gb, 0) + COALESCE(o.extra_volume_gb, 0)) > 0
        """)
        return [dict(row) for row in cursor.fetchall()]


def update_order_usage_notif_level(level_needed: int, order_id: int):
    with sqlite3.connect(DB_PATH) as conn:
        cursor = conn.cursor()
        cursor.execute("""
            UPDATE orders
            SET usage_notif_level = ?
            WHERE id = ?
        """, (level_needed, order_id))
        conn.commit()


def get_accounts_id_by_username(username: str):
    with sqlite3.connect(DB_PATH) as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT id FROM accounts WHERE username = ?", (username,))
        return cursor.fetchone()


def get_account_credentials_by_username(username: str):
    with sqlite3.connect(DB_PATH) as conn:
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        cursor.execute("""
            SELECT id, username, password, status, order_id
            FROM accounts
            WHERE username = ?
        """, (username,))
        row = cursor.fetchone()
        return dict(row) if row else None


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


def get_volume_packages(include_archived: bool = False):
    with sqlite3.connect(DB_PATH) as conn:
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        query = """
            SELECT
                vp.id,
                vp.name,
                vp.volume_gb,
                vp.price,
                vp.sort_order,
                vp.is_active,
                COALESCE(vp.is_archived, 0) AS is_archived,
                vp.created_at,
                vp.updated_at,
                COALESCE(vps.segment_count, 0) AS segment_count,
                COALESCE(vpc.category_count, 0) AS category_count
            FROM volume_packages vp
            LEFT JOIN (
                SELECT package_id, COUNT(*) AS segment_count
                FROM volume_package_segments
                GROUP BY package_id
            ) vps ON vps.package_id = vp.id
            LEFT JOIN (
                SELECT package_id, COUNT(*) AS category_count
                FROM volume_package_categories
                GROUP BY package_id
            ) vpc ON vpc.package_id = vp.id
        """
        if include_archived:
            query += "\nWHERE COALESCE(vp.is_archived, 0) = 1"
        else:
            query += "\nWHERE COALESCE(vp.is_archived, 0) = 0"
        query += "\nORDER BY vp.sort_order DESC, vp.id ASC"
        cursor.execute(query)
        return [dict(row) for row in cursor.fetchall()]


def get_active_volume_packages(user_id: Optional[int] = None, service_id: Optional[int] = None):
    with sqlite3.connect(DB_PATH) as conn:
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        params: list = []
        segment_filter = ""
        if user_id is not None:
            segment_filter = """
              AND (
                NOT EXISTS (
                    SELECT 1
                    FROM volume_package_segments vps2
                    JOIN segments s2 ON s2.id = vps2.segment_id
                    WHERE vps2.package_id = vp.id
                      AND COALESCE(s2.is_active, 1) = 1
                )
                OR EXISTS (
                    SELECT 1
                    FROM volume_package_segments vps2
                    JOIN segments s2 ON s2.id = vps2.segment_id
                    JOIN segment_users su2 ON su2.segment_id = vps2.segment_id
                    WHERE vps2.package_id = vp.id
                      AND COALESCE(s2.is_active, 1) = 1
                      AND su2.user_id = ?
                )
              )
            """
            params.append(user_id)
        else:
            segment_filter = """
              AND NOT EXISTS (
                    SELECT 1
                    FROM volume_package_segments vps2
                    JOIN segments s2 ON s2.id = vps2.segment_id
                    WHERE vps2.package_id = vp.id
                      AND COALESCE(s2.is_active, 1) = 1
              )
            """

        category_filter = ""
        if service_id is not None:
            category_filter = """
              AND (
                NOT EXISTS (
                    SELECT 1
                    FROM volume_package_categories vpc2
                    WHERE vpc2.package_id = vp.id
                )
                OR EXISTS (
                    SELECT 1
                    FROM volume_package_categories vpc2
                    JOIN orders service_order ON service_order.id = ?
                    JOIN plans service_plan ON service_plan.id = service_order.plan_id
                    WHERE vpc2.package_id = vp.id
                      AND vpc2.category = COALESCE(NULLIF(service_plan.category, ''), 'standard')
                )
              )
            """
            params.append(service_id)

        cursor.execute(f"""
            SELECT
                vp.id,
                vp.name,
                vp.volume_gb,
                vp.price,
                vp.sort_order,
                vp.is_active,
                COALESCE(vp.is_archived, 0) AS is_archived,
                vp.created_at,
                vp.updated_at,
                COALESCE(vps.segment_count, 0) AS segment_count,
                COALESCE(vpc.category_count, 0) AS category_count
            FROM volume_packages vp
            LEFT JOIN (
                SELECT package_id, COUNT(*) AS segment_count
                FROM volume_package_segments
                GROUP BY package_id
            ) vps ON vps.package_id = vp.id
            LEFT JOIN (
                SELECT package_id, COUNT(*) AS category_count
                FROM volume_package_categories
                GROUP BY package_id
            ) vpc ON vpc.package_id = vp.id
            WHERE COALESCE(vp.is_archived, 0) = 0
              AND COALESCE(vp.is_active, 1) = 1
              {segment_filter}
              {category_filter}
            ORDER BY vp.sort_order DESC, vp.id ASC
        """, params)
        return [dict(row) for row in cursor.fetchall()]


def get_volume_package(package_id: int):
    with sqlite3.connect(DB_PATH) as conn:
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        cursor.execute("""
            SELECT
                vp.id,
                vp.name,
                vp.volume_gb,
                vp.price,
                vp.sort_order,
                vp.is_active,
                COALESCE(vp.is_archived, 0) AS is_archived,
                vp.created_at,
                vp.updated_at,
                COALESCE(vps.segment_count, 0) AS segment_count,
                COALESCE(vpc.category_count, 0) AS category_count
            FROM volume_packages vp
            LEFT JOIN (
                SELECT package_id, COUNT(*) AS segment_count
                FROM volume_package_segments
                GROUP BY package_id
            ) vps ON vps.package_id = vp.id
            LEFT JOIN (
                SELECT package_id, COUNT(*) AS category_count
                FROM volume_package_categories
                GROUP BY package_id
            ) vpc ON vpc.package_id = vp.id
            WHERE vp.id = ?
            LIMIT 1
        """, (package_id,))
        row = cursor.fetchone()
        return dict(row) if row else None


def get_volume_package_segments(package_id: int):
    with sqlite3.connect(DB_PATH) as conn:
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        cursor.execute("""
            SELECT
                s.id,
                s.slug,
                s.title,
                s.description,
                s.is_active
            FROM volume_package_segments vps
            JOIN segments s ON s.id = vps.segment_id
            WHERE vps.package_id = ?
            ORDER BY s.title COLLATE NOCASE ASC, s.id ASC
        """, (package_id,))
        return [dict(row) for row in cursor.fetchall()]


def get_volume_package_categories(package_id: int) -> List[str]:
    with sqlite3.connect(DB_PATH) as conn:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT category
            FROM volume_package_categories
            WHERE package_id = ?
            ORDER BY category ASC
        """, (package_id,))
        return [row[0] for row in cursor.fetchall()]


def attach_segments_to_volume_package(package_id: int, segment_ids: List[int]) -> int:
    cleaned_ids = sorted({int(segment_id) for segment_id in segment_ids})
    if not cleaned_ids:
        return 0

    with sqlite3.connect(DB_PATH) as conn:
        cursor = conn.cursor()
        total_added = 0
        for segment_id in cleaned_ids:
            cursor.execute("""
                INSERT OR IGNORE INTO volume_package_segments (package_id, segment_id)
                VALUES (?, ?)
            """, (package_id, segment_id))
            total_added += cursor.rowcount
        conn.commit()
        return total_added


def detach_segments_from_volume_package(package_id: int, segment_ids: List[int]) -> int:
    cleaned_ids = sorted({int(segment_id) for segment_id in segment_ids})
    if not cleaned_ids:
        return 0

    with sqlite3.connect(DB_PATH) as conn:
        cursor = conn.cursor()
        cursor.executemany("""
            DELETE FROM volume_package_segments
            WHERE package_id = ? AND segment_id = ?
        """, [(package_id, segment_id) for segment_id in cleaned_ids])
        conn.commit()
        return cursor.rowcount


def attach_categories_to_volume_package(package_id: int, categories: List[str]) -> int:
    cleaned_categories = sorted({
        normalized
        for normalized in (_normalize_volume_package_category(category) for category in categories)
        if normalized
    })
    if not cleaned_categories:
        return 0

    with sqlite3.connect(DB_PATH) as conn:
        cursor = conn.cursor()
        total_added = 0
        for category in cleaned_categories:
            cursor.execute("""
                INSERT OR IGNORE INTO volume_package_categories (package_id, category)
                VALUES (?, ?)
            """, (package_id, category))
            total_added += cursor.rowcount
        conn.commit()
        return total_added


def detach_categories_from_volume_package(package_id: int, categories: List[str]) -> int:
    cleaned_categories = sorted({
        normalized
        for normalized in (_normalize_volume_package_category(category) for category in categories)
        if normalized
    })
    if not cleaned_categories:
        return 0

    with sqlite3.connect(DB_PATH) as conn:
        cursor = conn.cursor()
        cursor.executemany("""
            DELETE FROM volume_package_categories
            WHERE package_id = ? AND category = ?
        """, [(package_id, category) for category in cleaned_categories])
        conn.commit()
        return cursor.rowcount


def add_volume_package(name: str, volume_gb: int, price: int, sort_order: int = 0):
    now_text = _now_text()
    with sqlite3.connect(DB_PATH) as conn:
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO volume_packages (
                name,
                volume_gb,
                price,
                sort_order,
                is_active,
                is_archived,
                created_at,
                updated_at
            )
            VALUES (?, ?, ?, ?, 1, 0, ?, ?)
        """, (name, volume_gb, price, sort_order, now_text, now_text))
        conn.commit()
        return cursor.lastrowid


def update_volume_package_field(package_id: int, field: str, value):
    allowed = {"name", "volume_gb", "price", "sort_order", "is_active"}
    if field not in allowed:
        return False
    with sqlite3.connect(DB_PATH) as conn:
        cursor = conn.cursor()
        cursor.execute(
            f"""
            UPDATE volume_packages
            SET {field} = ?,
                updated_at = ?
            WHERE id = ?
            """,
            (value, _now_text(), package_id),
        )
        conn.commit()
        return cursor.rowcount > 0


def set_volume_package_archived(package_id: int, archived: bool):
    with sqlite3.connect(DB_PATH) as conn:
        cursor = conn.cursor()
        cursor.execute("""
            UPDATE volume_packages
            SET is_archived = ?,
                is_active = CASE WHEN ? = 1 THEN 0 ELSE is_active END,
                updated_at = ?
            WHERE id = ?
        """, (1 if archived else 0, 1 if archived else 0, _now_text(), package_id))
        conn.commit()
        return cursor.rowcount > 0


def get_active_locations_by_category(category: str, user_id: Optional[int] = None,
                                     display_context: Optional[str] = None):
    with sqlite3.connect(DB_PATH) as conn:
        conn.row_factory = sqlite3.Row
        role = _get_user_role_for_plans(conn, user_id)
        query, params = _apply_plan_audience_filters(
            """
            SELECT DISTINCT location
            FROM plans
            WHERE category = ?
              AND visible = 1
              AND COALESCE(is_archived, 0) = 0
              AND location IS NOT NULL
            """,
            [category],
            user_id=user_id,
            role=role,
            display_context=display_context,
        )
        query = f"{query}\nORDER BY location ASC"
        cursor = conn.cursor()
        cursor.execute(query, params)
        return [row["location"] for row in cursor.fetchall()]


def get_services_waiting_for_renew(user_id):
    with sqlite3.connect(DB_PATH) as conn:
        conn.row_factory = sqlite3.Row
        cur = conn.cursor()
        cur.execute("""
            SELECT id, username, expires_at, status
            FROM orders
            WHERE user_id = ? AND status = 'waiting_for_renewal'
        """, (user_id,))
        return [dict(r) for r in cur.fetchall()]


def get_services_waiting_for_renew_admin():
    with sqlite3.connect(DB_PATH) as conn:
        conn.row_factory = sqlite3.Row
        cur = conn.cursor()
        cur.execute("""
            SELECT id, username, expires_at, status
            FROM orders
            WHERE status = 'waiting_for_renewal'
        """, )
        return [dict(r) for r in cur.fetchall()]


def set_order_expiry_to_now(expiry_str: str, service_id: int):
    with sqlite3.connect(DB_PATH) as conn:
        cursor = conn.cursor()
        cursor.execute("""
            UPDATE orders
            SET expires_at = ?
            WHERE id = ?
        """, (expiry_str, service_id))


def get_order_status(order_id: int) -> Optional[str]:
    """Ø¨Ø±Ú¯Ø±Ø¯Ø§Ù†Ø¯Ù† ÙˆØ¶Ø¹ÛŒØª ÙØ¹Ù„ÛŒ Ø³ÙØ§Ø±Ø´ (status) Ø§Ø² Ø¬Ø¯ÙˆÙ„ orders"""
    with sqlite3.connect(DB_PATH) as conn:
        cur = conn.cursor()
        cur.execute("SELECT status FROM orders WHERE id = ?", (order_id,))
        row = cur.fetchone()
        return row[0] if row else None


def get_plan_info(plan_id: int):
    with sqlite3.connect(DB_PATH) as conn:
        conn.row_factory = sqlite3.Row  # Ø®Ø±ÙˆØ¬ÛŒ Ø¨Ù‡ Ø´Ú©Ù„ dict
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM plans WHERE id = ?", (plan_id,))
        row = cursor.fetchone()
        return dict(row) if row else None


def get_plan_name(plan_id: int) -> Optional[str]:
    with sqlite3.connect(DB_PATH) as conn:
        cur = conn.cursor()
        cur.execute("SELECT name FROM plans WHERE id = ?", (plan_id,))
        row = cur.fetchone()
        return row[0] if row else None


def get_plan_price(plan_id: int) -> int:
    with sqlite3.connect(DB_PATH) as conn:
        cur = conn.cursor()
        cur.execute("SELECT price FROM plans WHERE id = ?", (plan_id,))
        row = cur.fetchone()
        return row[0] if row else None


def get_auto_renew_orders():
    with sqlite3.connect(DB_PATH) as conn:
        conn.row_factory = sqlite3.Row  # Ø®Ø±ÙˆØ¬ÛŒ Ø¨Ù‡ Ø´Ú©Ù„ dict
        cursor = conn.cursor()

        now = jdatetime.datetime.now()
        one_day_later = now + jdatetime.timedelta(days=1)
        cursor.execute("""
                SELECT * FROM orders
                WHERE auto_renew = 1
                AND status IN ('active','expired')
                AND expires_at <= ?
            """, (one_day_later.strftime("%Y-%m-%d %H:%M:%S"),))

        rows = cursor.fetchall()
        return [dict(row) for row in rows]


def update_last_name(user_id: int, last_name: str):
    with sqlite3.connect(DB_PATH) as conn:
        cursor = conn.cursor()
        cursor.execute("""
            UPDATE users
            SET last_name = ?
            WHERE id = ?
        """, (last_name, user_id))


def get_user_message_name(user_id: int):
    with sqlite3.connect(DB_PATH) as conn:
        cur = conn.cursor()
        cur.execute("SELECT message_name FROM users WHERE id = ?", (user_id,))
        row = cur.fetchone()
        return row[0] if row else None


def count_user_active_orders(user_id: int) -> int:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()

    cur.execute("""
        SELECT COUNT(*) AS cnt
        FROM orders
        WHERE user_id = ?
          AND status = 'active'
    """, (user_id,))

    row = cur.fetchone()
    conn.close()
    return int(row["cnt"] or 0)


def get_user_max_active_accounts(user_id: int) -> int:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()

    cur.execute("""
        SELECT max_active_accounts
        FROM users
        WHERE id = ?
        LIMIT 1
    """, (user_id,))

    row = cur.fetchone()
    conn.close()

    if not row:
        return 3

    try:
        value = int(row["max_active_accounts"] or 3)
        return value if value > 0 else 3
    except Exception:
        return 3


def get_user_by_id(user_id: int):
    with sqlite3.connect(DB_PATH) as conn:
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        cursor.execute("""
            SELECT *
            FROM users
            WHERE id = ?
        """, (user_id,))
        row = cursor.fetchone()
        return dict(row) if row else None


def get_user_display_name(user_id: int) -> str:
    with sqlite3.connect(DB_PATH) as conn:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT first_name, username
            FROM users
            WHERE id = ?
        """, (user_id,))
        row = cursor.fetchone()

        if not row:
            return f"Ú©Ø§Ø±Ø¨Ø± {user_id}"

        first_name, username = row

        if first_name and username:
            return f"{first_name} (@{username})"
        if first_name:
            return str(first_name)
        if username:
            return f"@{username}"

        return f"Ú©Ø§Ø±Ø¨Ø± {user_id}"


def get_distinct_usernames_by_user_id(user_id: int):
    with sqlite3.connect(DB_PATH) as conn:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT DISTINCT username
            FROM orders
            WHERE user_id = ?
              AND username IS NOT NULL
              AND status NOT IN ('archived', 'renewed', 'converted')
            ORDER BY username
        """, (user_id,))
        rows = cursor.fetchall()
        return [row[0] for row in rows if row[0] is not None]


def count_orders_by_user_id_and_username(user_id: int, username: str) -> int:
    with sqlite3.connect(DB_PATH) as conn:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT COUNT(*)
            FROM orders
            WHERE user_id = ? AND username = ?
        """, (user_id, username))
        row = cursor.fetchone()
        return row[0] if row else 0


def transfer_orders_by_username_to_another_user(from_user_id: int, to_user_id: int, username: str):
    with sqlite3.connect(DB_PATH) as conn:
        cursor = conn.cursor()

        cursor.execute("""
            SELECT COUNT(*)
            FROM orders
            WHERE user_id = ? AND username = ?
        """, (from_user_id, username))
        row = cursor.fetchone()
        total_orders = row[0] if row else 0

        if total_orders == 0:
            return False, "Ø¨Ø±Ø§ÛŒ Ø§ÛŒÙ† Ø§Ú©Ø§Ù†Øª Ø³ÙØ§Ø±Ø´ÛŒ Ù¾ÛŒØ¯Ø§ Ù†Ø´Ø¯.", 0

        cursor.execute("""
            UPDATE orders
            SET user_id = ?
            WHERE user_id = ? AND username = ?
        """, (to_user_id, from_user_id, username))

        cursor.execute("""
            INSERT INTO ownership_transfers (
                from_user_id,
                to_user_id,
                username,
                transferred_by,
                transferred_at,
                total_orders
            )
            VALUES (?, ?, ?, ?, ?, ?)
        """, (from_user_id, to_user_id, username, from_user_id, _now_text(), total_orders))

        conn.commit()
        return True, None, total_orders

