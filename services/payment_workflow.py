import sqlite3
from datetime import datetime
from typing import Dict, List, Optional

from config import DB_PATH

STATUS_DRAFT = "draft"
STATUS_PENDING_ADMIN = "pending_admin"
STATUS_APPROVED_PENDING_ACCOUNTING = "approved_pending_accounting"
STATUS_ACCOUNTING_APPROVED = "accounting_approved"
STATUS_REJECTED = "rejected"
STATUS_ACCOUNTING_REJECTED = "accounting_rejected"
STATUS_BALANCE_REVERSED = "balance_reversed"
STATUS_LEGACY_PENDING = "pending"
STATUS_LEGACY_APPROVED = "approved"

ACTIVE_REVIEWABLE_STATUSES = {
    STATUS_PENDING_ADMIN,
    STATUS_APPROVED_PENDING_ACCOUNTING,
}

PERSIAN_DIGITS = str.maketrans("\u06f0\u06f1\u06f2\u06f3\u06f4\u06f5\u06f6\u06f7\u06f8\u06f9", "0123456789")
LTR_EMBED_START = "\u202A"
LTR_EMBED_END = "\u202C"
LRM = "\u200E"

DUPLICATE_REASON_LABELS = {
    "same_photo": "هش عکس یکسان",
    "same_amount_transfer_datetime": "مبلغ و تاریخ/ساعت واریز یکسان",
    "same_user_source_last4_within_one_minute": "همان کاربر با همان ۴ رقم آخر در کمتر از ۱ دقیقه دوباره واریز کرده",
    "exact_amount_datetime_source_last4": "بسیار مشکوک: مبلغ و تاریخ/ساعت و ۴ رقم آخر یکی است",
    # Legacy labels for older rows
    "same_user_day_source_last4": "کاربر در همان روز با همان ۴ رقم آخر دوباره واریز کرده",
    "same_amount_card_datetime": "مبلغ/کارت/تاریخ‌وساعت مشابه",
    "same_amount_date_source_last4": "مبلغ/تاریخ/۴ رقم کارت مبدا مشابه",
}

DUPLICATE_REASON_PRIORITY = {
    "exact_amount_datetime_source_last4": 0,
    "same_photo": 1,
    "same_amount_transfer_datetime": 2,
    "same_user_source_last4_within_one_minute": 3,
    "same_user_day_source_last4": 4,
    "same_amount_card_datetime": 5,
    "same_amount_date_source_last4": 6,
}


def _connect() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def _now_text() -> str:
    return datetime.now().isoformat(sep=" ", timespec="minutes")


def normalize_digits(value: Optional[str]) -> str:
    if value is None:
        return ""
    return str(value).translate(PERSIAN_DIGITS)


def normalize_card_number(value: Optional[str]) -> str:
    return "".join(ch for ch in normalize_digits(value) if ch.isdigit())


def normalize_last4(value: Optional[str]) -> str:
    digits = "".join(ch for ch in normalize_digits(value) if ch.isdigit())
    return digits[-4:] if digits else ""


def format_card_number_for_display(card_number: Optional[str], missing: str = "نامشخص") -> str:
    digits = normalize_card_number(card_number)
    if not digits:
        return missing
    grouped = "-".join(digits[i:i + 4] for i in range(0, len(digits), 4))
    safe_grouped = grouped.replace("-", f"{LRM}-{LRM}")
    return f"{LTR_EMBED_START}{LRM}{safe_grouped}{LRM}{LTR_EMBED_END}"


def duplicate_reason_label(reason: str) -> str:
    return DUPLICATE_REASON_LABELS.get(reason, reason)


def _parse_hhmm_to_minutes(value: Optional[str]) -> Optional[int]:
    raw = (normalize_digits(value) or "").strip()
    if not raw:
        return None
    parts = raw.split(":")
    if len(parts) != 2:
        return None
    try:
        hour = int(parts[0])
        minute = int(parts[1])
    except Exception:
        return None
    if not (0 <= hour <= 23 and 0 <= minute <= 59):
        return None
    return (hour * 60) + minute


def get_transaction_status_label(status: Optional[str]) -> str:
    mapping = {
        STATUS_DRAFT: "پیش‌نویس",
        STATUS_PENDING_ADMIN: "در انتظار تایید ادمین",
        STATUS_APPROVED_PENDING_ACCOUNTING: "شارژ شد؛ در انتظار تایید حسابداری",
        STATUS_ACCOUNTING_APPROVED: "تایید نهایی حسابداری",
        STATUS_REJECTED: "رد توسط ادمین",
        STATUS_ACCOUNTING_REJECTED: "رد توسط حسابداری",
        STATUS_BALANCE_REVERSED: "برگشت وجه / کسر از حساب",
        "pending": "در انتظار بررسی",
        "approved": "تایید شده",
    }
    return mapping.get((status or "").strip().lower(), status or "نامشخص")


def create_transaction_draft(user_id: int, photo_id: str, photo_path: str, photo_hash: str) -> int:
    created_at = _now_text()
    with _connect() as conn:
        cur = conn.cursor()
        cur.execute(
            """
            INSERT INTO transactions (
                user_id,
                status,
                created_at,
                photo_id,
                photo_path,
                photo_hash,
                amount,
                amount_claimed,
                is_duplicate_suspect,
                balance_reverted
            )
            VALUES (?, ?, ?, ?, ?, ?, 0, 0, 0, 0)
            """,
            (user_id, STATUS_DRAFT, created_at, photo_id, photo_path, photo_hash),
        )
        conn.commit()
        return int(cur.lastrowid)


def get_active_bank_cards() -> List[Dict]:
    with _connect() as conn:
        cur = conn.cursor()
        cur.execute(
            """
            SELECT id, card_number, owner_name, bank_name
            FROM bank_cards
            WHERE is_active = 1
            ORDER BY priority DESC, id ASC
            """
        )
        return [dict(row) for row in cur.fetchall()]


def get_receipt_bank_cards() -> List[Dict]:
    with _connect() as conn:
        cur = conn.cursor()
        cur.execute(
            """
            SELECT id, card_number, owner_name, bank_name
            FROM bank_cards
            WHERE COALESCE(show_in_receipt, is_active, 0) = 1
            ORDER BY priority DESC, id ASC
            """
        )
        return [dict(row) for row in cur.fetchall()]


def get_transaction(txn_id: int) -> Optional[Dict]:
    with _connect() as conn:
        cur = conn.cursor()
        cur.execute("SELECT * FROM transactions WHERE id = ? LIMIT 1", (txn_id,))
        row = cur.fetchone()
        return dict(row) if row else None


def get_user_transaction(txn_id: int, user_id: int) -> Optional[Dict]:
    with _connect() as conn:
        cur = conn.cursor()
        cur.execute(
            "SELECT * FROM transactions WHERE id = ? AND user_id = ? LIMIT 1",
            (txn_id, user_id),
        )
        row = cur.fetchone()
        return dict(row) if row else None


def _update_draft_field(txn_id: int, user_id: int, field: str, value) -> bool:
    allowed_fields = {
        "amount_claimed",
        "destination_card_id",
        "destination_card_number",
        "destination_card_owner",
        "destination_bank_name",
        "transfer_date",
        "transfer_time",
        "source_card_last4",
    }
    if field not in allowed_fields:
        return False

    with _connect() as conn:
        cur = conn.cursor()
        cur.execute(
            f"""
            UPDATE transactions
            SET {field} = ?
            WHERE id = ? AND user_id = ? AND status = ?
            """,
            (value, txn_id, user_id, STATUS_DRAFT),
        )
        conn.commit()
        return cur.rowcount > 0


def set_claimed_amount(txn_id: int, user_id: int, amount: int) -> bool:
    return _update_draft_field(txn_id, user_id, "amount_claimed", int(amount))


def set_destination_card_from_card_id(txn_id: int, user_id: int, card_id: int) -> bool:
    with _connect() as conn:
        cur = conn.cursor()
        cur.execute(
            """
            SELECT id, card_number, owner_name, bank_name
            FROM bank_cards
            WHERE id = ?
              AND COALESCE(show_in_receipt, is_active, 0) = 1
            LIMIT 1
            """,
            (card_id,),
        )
        card = cur.fetchone()
        if not card:
            return False

        normalized_card = normalize_card_number(card["card_number"])
        cur.execute(
            """
            UPDATE transactions
            SET destination_card_id = ?,
                destination_card_number = ?,
                destination_card_owner = ?,
                destination_bank_name = ?
            WHERE id = ? AND user_id = ? AND status = ?
            """,
            (
                int(card["id"]),
                normalized_card,
                (card["owner_name"] or "").strip() or None,
                (card["bank_name"] or "").strip() or None,
                txn_id,
                user_id,
                STATUS_DRAFT,
            ),
        )
        conn.commit()
        return cur.rowcount > 0


def set_destination_card_manual(txn_id: int, user_id: int, card_number: str) -> bool:
    normalized_card = normalize_card_number(card_number)
    if len(normalized_card) < 12:
        return False
    with _connect() as conn:
        cur = conn.cursor()
        cur.execute(
            """
            UPDATE transactions
            SET destination_card_id = NULL,
                destination_card_number = ?,
                destination_card_owner = NULL,
                destination_bank_name = NULL
            WHERE id = ? AND user_id = ? AND status = ?
            """,
            (normalized_card, txn_id, user_id, STATUS_DRAFT),
        )
        conn.commit()
        return cur.rowcount > 0


def set_transfer_date(txn_id: int, user_id: int, transfer_date: str) -> bool:
    return _update_draft_field(txn_id, user_id, "transfer_date", transfer_date.strip())


def set_transfer_time(txn_id: int, user_id: int, transfer_time: str) -> bool:
    return _update_draft_field(txn_id, user_id, "transfer_time", transfer_time.strip())


def set_source_card_last4(txn_id: int, user_id: int, last4: Optional[str]) -> bool:
    normalized = normalize_last4(last4)
    return _update_draft_field(txn_id, user_id, "source_card_last4", normalized or None)


def _update_transaction_field_by_status(txn_id: int, field: str, value, allowed_statuses: tuple[str, ...]) -> bool:
    allowed_fields = {
        "source_card_last4",
        "transfer_date",
        "transfer_time",
    }
    if field not in allowed_fields or not allowed_statuses:
        return False

    placeholders = ", ".join("?" for _ in allowed_statuses)
    with _connect() as conn:
        cur = conn.cursor()
        cur.execute(
            f"""
            UPDATE transactions
            SET {field} = ?
            WHERE id = ? AND status IN ({placeholders})
            """,
            (value, txn_id, *allowed_statuses),
        )
        conn.commit()
        return cur.rowcount > 0


def set_accounting_source_card_last4(txn_id: int, last4: Optional[str]) -> bool:
    normalized = normalize_last4(last4)
    with _connect() as conn:
        cur = conn.cursor()
        cur.execute(
            """
            UPDATE transactions
            SET source_card_last4 = ?
            WHERE id = ? AND status = ?
            """,
            (normalized or None, txn_id, STATUS_APPROVED_PENDING_ACCOUNTING),
        )
        updated = cur.rowcount > 0
        if updated:
            _refresh_duplicate_markers(conn, txn_id)
        conn.commit()
        return updated


def set_accounting_transfer_datetime(txn_id: int, transfer_date: str, transfer_time: str) -> bool:
    clean_date = (transfer_date or "").strip()
    clean_time = (transfer_time or "").strip()
    if not clean_date or not clean_time:
        return False

    with _connect() as conn:
        cur = conn.cursor()
        cur.execute(
            """
            UPDATE transactions
            SET transfer_date = ?,
                transfer_time = ?
            WHERE id = ? AND status = ?
            """,
            (clean_date, clean_time, txn_id, STATUS_APPROVED_PENDING_ACCOUNTING),
        )
        updated = cur.rowcount > 0
        if updated:
            _refresh_duplicate_markers(conn, txn_id)
        conn.commit()
        return updated


def set_accounting_destination_card_from_card_id(txn_id: int, card_id: int) -> bool:
    with _connect() as conn:
        cur = conn.cursor()
        cur.execute(
            """
            SELECT id, card_number, owner_name, bank_name
            FROM bank_cards
            WHERE id = ?
            LIMIT 1
            """,
            (card_id,),
        )
        card = cur.fetchone()
        if not card:
            return False

        normalized_card = normalize_card_number(card["card_number"])
        cur.execute(
            """
            UPDATE transactions
            SET destination_card_id = ?,
                destination_card_number = ?,
                destination_card_owner = ?,
                destination_bank_name = ?
            WHERE id = ? AND status = ?
            """,
            (
                int(card["id"]),
                normalized_card,
                (card["owner_name"] or "").strip() or None,
                (card["bank_name"] or "").strip() or None,
                txn_id,
                STATUS_APPROVED_PENDING_ACCOUNTING,
            ),
        )
        conn.commit()
        return cur.rowcount > 0


def set_accounting_destination_card_manual(txn_id: int, card_number: str) -> bool:
    normalized_card = normalize_card_number(card_number)
    if len(normalized_card) < 12:
        return False

    with _connect() as conn:
        cur = conn.cursor()
        cur.execute(
            """
            UPDATE transactions
            SET destination_card_id = NULL,
                destination_card_number = ?,
                destination_card_owner = NULL,
                destination_bank_name = NULL
            WHERE id = ? AND status = ?
            """,
            (normalized_card, txn_id, STATUS_APPROVED_PENDING_ACCOUNTING),
        )
        conn.commit()
        return cur.rowcount > 0


def _build_duplicate_candidates(conn: sqlite3.Connection, txn: Dict) -> Dict[int, Dict]:
    candidates: Dict[int, Dict] = {}
    cur = conn.cursor()

    def add_reason(rows, reason: str):
        for row in rows:
            tx_id = int(row["id"])
            item = candidates.setdefault(
                tx_id,
                {
                    "id": tx_id,
                    "status": row["status"],
                    "user_id": row["user_id"],
                    "created_at": row["created_at"],
                    "amount": row["amount"],
                    "amount_claimed": row["amount_claimed"],
                    "destination_card_number": row["destination_card_number"],
                    "transfer_date": row["transfer_date"],
                    "transfer_time": row["transfer_time"],
                    "source_card_last4": row["source_card_last4"],
                    "reasons": [],
                },
            )
            if reason not in item["reasons"]:
                item["reasons"].append(reason)

    base_fields = """
        SELECT
            id,
            user_id,
            status,
            created_at,
            amount,
            amount_claimed,
            destination_card_number,
            transfer_date,
            transfer_time,
            source_card_last4
        FROM transactions
        WHERE id != ?
          AND status != ?
    """

    if txn.get("photo_hash"):
        cur.execute(
            f"{base_fields} AND photo_hash = ? ORDER BY id DESC LIMIT 10",
            (txn["id"], STATUS_DRAFT, txn["photo_hash"]),
        )
        add_reason(cur.fetchall(), "same_photo")

    if txn.get("amount_claimed") and txn.get("transfer_date") and txn.get("transfer_time"):
        params = [
            txn["id"],
            STATUS_DRAFT,
            txn["amount_claimed"],
            txn["transfer_date"],
            txn["transfer_time"],
        ]
        extra = """
            AND amount_claimed = ?
            AND transfer_date = ?
            AND transfer_time = ?
        """
        cur.execute(f"{base_fields} {extra} ORDER BY id DESC LIMIT 10", params)
        add_reason(cur.fetchall(), "same_amount_transfer_datetime")

    if txn.get("user_id") and txn.get("transfer_date") and txn.get("source_card_last4") and txn.get("transfer_time"):
        cur.execute(
            f"""
            {base_fields}
            AND user_id = ?
            AND transfer_date = ?
            AND source_card_last4 = ?
            ORDER BY id DESC
            LIMIT 10
            """,
            (
                txn["id"],
                STATUS_DRAFT,
                txn["user_id"],
                txn["transfer_date"],
                txn["source_card_last4"],
            ),
        )
        current_minutes = _parse_hhmm_to_minutes(txn.get("transfer_time"))
        if current_minutes is not None:
            close_rows = []
            for row in cur.fetchall():
                other_minutes = _parse_hhmm_to_minutes(row["transfer_time"])
                if other_minutes is None:
                    continue
                if abs(other_minutes - current_minutes) <= 1:
                    close_rows.append(row)
            add_reason(close_rows, "same_user_source_last4_within_one_minute")

    if (
        txn.get("amount_claimed")
        and txn.get("transfer_date")
        and txn.get("transfer_time")
        and txn.get("source_card_last4")
    ):
        cur.execute(
            f"""
            {base_fields}
            AND amount_claimed = ?
            AND transfer_date = ?
            AND transfer_time = ?
            AND source_card_last4 = ?
            ORDER BY id DESC
            LIMIT 10
            """,
            (
                txn["id"],
                STATUS_DRAFT,
                txn["amount_claimed"],
                txn["transfer_date"],
                txn["transfer_time"],
                txn["source_card_last4"],
            ),
        )
        add_reason(cur.fetchall(), "exact_amount_datetime_source_last4")

    for item in candidates.values():
        item["reasons"] = _sorted_duplicate_reasons(item["reasons"])

    return candidates


def _sorted_duplicate_reasons(reasons) -> List[str]:
    unique_reasons = {reason for reason in reasons if reason}
    return sorted(unique_reasons, key=lambda reason: (DUPLICATE_REASON_PRIORITY.get(reason, 999), reason))


def _candidate_sort_key(item: Dict) -> tuple[int, int]:
    min_priority = min((DUPLICATE_REASON_PRIORITY.get(reason, 999) for reason in (item.get("reasons") or [])), default=999)
    return min_priority, -int(item["id"])


def _analyze_duplicate_candidates(conn: sqlite3.Connection, txn: Dict) -> tuple[List[Dict], Optional[str], Optional[str], int]:
    candidates = list(_build_duplicate_candidates(conn, txn).values())
    candidates.sort(key=_candidate_sort_key)
    candidate_ids = ",".join(str(item["id"]) for item in candidates[:10]) or None
    flags = _sorted_duplicate_reasons(reason for item in candidates for reason in (item.get("reasons") or []))
    duplicate_flags = ",".join(flags) or None
    is_duplicate = 1 if flags else 0
    return candidates, duplicate_flags, candidate_ids, is_duplicate


def _refresh_duplicate_markers(conn: sqlite3.Connection, txn_id: int) -> bool:
    cur = conn.cursor()
    cur.execute("SELECT * FROM transactions WHERE id = ? LIMIT 1", (txn_id,))
    row = cur.fetchone()
    if not row:
        return False

    _, duplicate_flags, candidate_ids, is_duplicate = _analyze_duplicate_candidates(conn, dict(row))
    cur.execute(
        """
        UPDATE transactions
        SET duplicate_flags = ?,
            duplicate_candidate_ids = ?,
            is_duplicate_suspect = ?
        WHERE id = ?
        """,
        (duplicate_flags, candidate_ids, is_duplicate, txn_id),
    )
    return True


def get_duplicate_candidates(txn_id: int, limit: int = 5) -> List[Dict]:
    with _connect() as conn:
        cur = conn.cursor()
        cur.execute("SELECT * FROM transactions WHERE id = ? LIMIT 1", (txn_id,))
        row = cur.fetchone()
        if not row:
            return []
        candidates = list(_build_duplicate_candidates(conn, dict(row)).values())
        candidates.sort(key=_candidate_sort_key)
        return candidates[:limit]


def submit_transaction_for_review(txn_id: int, user_id: int) -> Optional[Dict]:
    with _connect() as conn:
        cur = conn.cursor()
        cur.execute(
            """
            SELECT *
            FROM transactions
            WHERE id = ? AND user_id = ? AND status = ?
            LIMIT 1
            """,
            (txn_id, user_id, STATUS_DRAFT),
        )
        row = cur.fetchone()
        if not row:
            return None

        txn = dict(row)
        required_fields = (
            txn.get("photo_id"),
            txn.get("photo_path"),
            txn.get("amount_claimed"),
            txn.get("destination_card_number"),
            txn.get("transfer_date"),
            txn.get("transfer_time"),
        )
        if not all(required_fields):
            return None

        _, duplicate_flags, candidate_ids, is_duplicate = _analyze_duplicate_candidates(conn, txn)
        submitted_at = _now_text()

        cur.execute(
            """
            UPDATE transactions
            SET status = ?,
                submitted_at = ?,
                duplicate_flags = ?,
                duplicate_candidate_ids = ?,
                is_duplicate_suspect = ?
            WHERE id = ? AND user_id = ? AND status = ?
            """,
            (
                STATUS_PENDING_ADMIN,
                submitted_at,
                duplicate_flags,
                candidate_ids,
                is_duplicate,
                txn_id,
                user_id,
                STATUS_DRAFT,
            ),
        )
        conn.commit()

    return get_transaction_with_user(txn_id)


def _transaction_user_query() -> str:
    return """
        SELECT
            t.*,
            u.first_name,
            u.last_name,
            u.username
        FROM transactions t
        JOIN users u ON u.id = t.user_id
    """


def list_transactions_by_status(status: str) -> List[Dict]:
    with _connect() as conn:
        cur = conn.cursor()
        if status == STATUS_PENDING_ADMIN:
            cur.execute(
                f"""
                {_transaction_user_query()}
                WHERE t.status IN (?, ?)
                ORDER BY COALESCE(t.submitted_at, t.created_at) ASC, t.id ASC
                """,
                (STATUS_PENDING_ADMIN, STATUS_LEGACY_PENDING),
            )
        else:
            cur.execute(
                f"""
                {_transaction_user_query()}
                WHERE t.status = ?
                ORDER BY COALESCE(t.submitted_at, t.created_at) ASC, t.id ASC
                """,
                (status,),
            )
        return [dict(row) for row in cur.fetchall()]


def get_transaction_with_user(txn_id: int) -> Optional[Dict]:
    with _connect() as conn:
        cur = conn.cursor()
        cur.execute(
            f"""
            {_transaction_user_query()}
            WHERE t.id = ?
            LIMIT 1
            """,
            (txn_id,),
        )
        row = cur.fetchone()
        return dict(row) if row else None


def list_reversible_transactions(limit: int = 20) -> List[Dict]:
    with _connect() as conn:
        cur = conn.cursor()
        cur.execute(
            f"""
            {_transaction_user_query()}
            WHERE t.status = ?
              AND COALESCE(t.balance_reverted, 0) = 0
            ORDER BY COALESCE(t.accounting_reviewed_at, t.created_at) DESC, t.id DESC
            LIMIT ?
            """,
            (STATUS_ACCOUNTING_APPROVED, int(limit)),
        )
        return [dict(row) for row in cur.fetchall()]


def approve_transaction_initial(txn_id: int, reviewer_id: int, amount: int, note: Optional[str] = None) -> Optional[Dict]:
    approved_amount = int(amount or 0)
    if approved_amount <= 0:
        return None

    reviewed_at = _now_text()
    with _connect() as conn:
        cur = conn.cursor()
        cur.execute("BEGIN")
        cur.execute(
            """
            SELECT user_id
            FROM transactions
            WHERE id = ? AND status IN (?, ?)
            LIMIT 1
            """,
            (txn_id, STATUS_PENDING_ADMIN, STATUS_LEGACY_PENDING),
        )
        row = cur.fetchone()
        if not row:
            conn.rollback()
            return None

        user_id = int(row["user_id"])
        cur.execute(
            """
            UPDATE transactions
            SET amount = ?,
                status = ?,
                admin_reviewed_at = ?,
                admin_reviewed_by = ?,
                admin_note = ?
            WHERE id = ? AND status IN (?, ?)
            """,
            (
                approved_amount,
                STATUS_APPROVED_PENDING_ACCOUNTING,
                reviewed_at,
                reviewer_id,
                (note or "").strip() or None,
                txn_id,
                STATUS_PENDING_ADMIN,
                STATUS_LEGACY_PENDING,
            ),
        )
        if cur.rowcount == 0:
            conn.rollback()
            return None

        cur.execute(
            "UPDATE users SET balance = COALESCE(balance, 0) + ? WHERE id = ?",
            (approved_amount, user_id),
        )
        conn.commit()

    return get_transaction_with_user(txn_id)


def approve_transaction_with_accounting(
    txn_id: int,
    reviewer_id: int,
    amount: int,
    note: Optional[str] = None,
    accounting_note: Optional[str] = None,
) -> Optional[Dict]:
    approved_amount = int(amount or 0)
    if approved_amount <= 0:
        return None

    reviewed_at = _now_text()
    with _connect() as conn:
        cur = conn.cursor()
        cur.execute("BEGIN")
        cur.execute(
            """
            SELECT user_id
            FROM transactions
            WHERE id = ? AND status IN (?, ?)
            LIMIT 1
            """,
            (txn_id, STATUS_PENDING_ADMIN, STATUS_LEGACY_PENDING),
        )
        row = cur.fetchone()
        if not row:
            conn.rollback()
            return None

        user_id = int(row["user_id"])
        cur.execute(
            """
            UPDATE transactions
            SET amount = ?,
                status = ?,
                admin_reviewed_at = ?,
                admin_reviewed_by = ?,
                admin_note = ?,
                accounting_reviewed_at = ?,
                accounting_reviewed_by = ?,
                accounting_note = ?
            WHERE id = ? AND status IN (?, ?)
            """,
            (
                approved_amount,
                STATUS_ACCOUNTING_APPROVED,
                reviewed_at,
                reviewer_id,
                (note or "").strip() or None,
                reviewed_at,
                reviewer_id,
                (accounting_note or "").strip() or None,
                txn_id,
                STATUS_PENDING_ADMIN,
                STATUS_LEGACY_PENDING,
            ),
        )
        if cur.rowcount == 0:
            conn.rollback()
            return None

        cur.execute(
            "UPDATE users SET balance = COALESCE(balance, 0) + ? WHERE id = ?",
            (approved_amount, user_id),
        )
        conn.commit()

    return get_transaction_with_user(txn_id)


def reject_transaction_initial(txn_id: int, reviewer_id: int, reason: str) -> Optional[Dict]:
    reviewed_at = _now_text()
    clean_reason = (reason or "").strip()
    with _connect() as conn:
        cur = conn.cursor()
        cur.execute(
            """
            UPDATE transactions
            SET status = ?,
                admin_reviewed_at = ?,
                admin_reviewed_by = ?,
                admin_note = ?
            WHERE id = ? AND status IN (?, ?)
            """,
            (
                STATUS_REJECTED,
                reviewed_at,
                reviewer_id,
                clean_reason or None,
                txn_id,
                STATUS_PENDING_ADMIN,
                STATUS_LEGACY_PENDING,
            ),
        )
        conn.commit()
        if cur.rowcount == 0:
            return None

    return get_transaction_with_user(txn_id)


def confirm_transaction_accounting(txn_id: int, reviewer_id: int, note: Optional[str] = None) -> Optional[Dict]:
    reviewed_at = _now_text()
    with _connect() as conn:
        cur = conn.cursor()
        cur.execute(
            """
            UPDATE transactions
            SET status = ?,
                accounting_reviewed_at = ?,
                accounting_reviewed_by = ?,
                accounting_note = ?
            WHERE id = ? AND status = ?
            """,
            (
                STATUS_ACCOUNTING_APPROVED,
                reviewed_at,
                reviewer_id,
                (note or "").strip() or None,
                txn_id,
                STATUS_APPROVED_PENDING_ACCOUNTING,
            ),
        )
        conn.commit()
        if cur.rowcount == 0:
            return None

    return get_transaction_with_user(txn_id)


def reject_transaction_accounting(txn_id: int, reviewer_id: int, reason: str) -> Optional[Dict]:
    reviewed_at = _now_text()
    clean_reason = (reason or "").strip()
    with _connect() as conn:
        cur = conn.cursor()
        cur.execute("BEGIN")
        cur.execute(
            """
            SELECT user_id, amount, balance_reverted
            FROM transactions
            WHERE id = ? AND status = ?
            LIMIT 1
            """,
            (txn_id, STATUS_APPROVED_PENDING_ACCOUNTING),
        )
        row = cur.fetchone()
        if not row:
            conn.rollback()
            return None

        user_id = int(row["user_id"])
        amount = int(row["amount"] or 0)
        balance_reverted = int(row["balance_reverted"] or 0)

        if amount > 0 and balance_reverted == 0:
            cur.execute(
                "UPDATE users SET balance = COALESCE(balance, 0) - ? WHERE id = ?",
                (amount, user_id),
            )

        cur.execute(
            """
            UPDATE transactions
            SET status = ?,
                accounting_reviewed_at = ?,
                accounting_reviewed_by = ?,
                accounting_note = ?,
                balance_reverted_at = CASE
                    WHEN COALESCE(balance_reverted, 0) = 1 THEN balance_reverted_at
                    WHEN COALESCE(amount, 0) > 0 THEN ?
                    ELSE balance_reverted_at
                END,
                balance_reverted_by = CASE
                    WHEN COALESCE(balance_reverted, 0) = 1 THEN balance_reverted_by
                    WHEN COALESCE(amount, 0) > 0 THEN ?
                    ELSE balance_reverted_by
                END,
                balance_reverted_reason = CASE
                    WHEN COALESCE(balance_reverted, 0) = 1 THEN balance_reverted_reason
                    WHEN COALESCE(amount, 0) > 0 THEN ?
                    ELSE balance_reverted_reason
                END,
                balance_reverted = CASE
                    WHEN COALESCE(balance_reverted, 0) = 1 THEN 1
                    WHEN COALESCE(amount, 0) > 0 THEN 1
                    ELSE 0
                END
            WHERE id = ? AND status = ?
            """,
            (
                STATUS_ACCOUNTING_REJECTED,
                reviewed_at,
                reviewer_id,
                clean_reason or None,
                reviewed_at,
                reviewer_id,
                clean_reason or None,
                txn_id,
                STATUS_APPROVED_PENDING_ACCOUNTING,
            ),
        )
        if cur.rowcount == 0:
            conn.rollback()
            return None

        conn.commit()

    return get_transaction_with_user(txn_id)


def reverse_transaction_balance(txn_id: int, reviewer_id: int, reason: str) -> Optional[Dict]:
    reviewed_at = _now_text()
    clean_reason = (reason or "").strip()
    if not clean_reason:
        return None

    with _connect() as conn:
        cur = conn.cursor()
        cur.execute("BEGIN")
        cur.execute(
            """
            SELECT user_id, amount, balance_reverted
            FROM transactions
            WHERE id = ? AND status = ?
            LIMIT 1
            """,
            (txn_id, STATUS_ACCOUNTING_APPROVED),
        )
        row = cur.fetchone()
        if not row:
            conn.rollback()
            return None

        user_id = int(row["user_id"])
        amount = int(row["amount"] or 0)
        balance_reverted = int(row["balance_reverted"] or 0)
        if balance_reverted == 1:
            conn.rollback()
            return None

        if amount > 0:
            cur.execute(
                "UPDATE users SET balance = COALESCE(balance, 0) - ? WHERE id = ?",
                (amount, user_id),
            )

        cur.execute(
            """
            UPDATE transactions
            SET status = ?,
                balance_reverted = 1,
                balance_reverted_at = ?,
                balance_reverted_by = ?,
                balance_reverted_reason = ?
            WHERE id = ? AND status = ? AND COALESCE(balance_reverted, 0) = 0
            """,
            (
                STATUS_BALANCE_REVERSED,
                reviewed_at,
                reviewer_id,
                clean_reason,
                txn_id,
                STATUS_ACCOUNTING_APPROVED,
            ),
        )
        if cur.rowcount == 0:
            conn.rollback()
            return None

        conn.commit()

    return get_transaction_with_user(txn_id)
