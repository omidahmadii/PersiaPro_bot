from __future__ import annotations

import sqlite3
from datetime import datetime
from typing import Optional

import jdatetime

from config import DB_PATH
from services.IBSng import (
    change_group,
    get_user_exp_date,
    get_user_start_date,
    reset_radius_attrs,
    reset_account_client,
    unlock_user,
)

FINAL_ORDER_STATUSES = {"canceled", "renewed", "archived", "converted"}
LIVE_ORDER_STATUSES = {"active", "waiting_for_renewal", "waiting_for_renewal_not_paid", "expired"}
PAID_ORDER_STATUSES = LIVE_ORDER_STATUSES | {"reserved"}


def _connect() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def _now_text() -> str:
    return datetime.now().isoformat(sep=" ", timespec="minutes")


def _status_after_restore(order: Optional[sqlite3.Row]) -> str:
    if not order:
        return "active"
    expires_at = order["expires_at"] if "expires_at" in order.keys() else None
    if not expires_at:
        return "active"
    try:
        exp_jdt = jdatetime.datetime.strptime(str(expires_at), "%Y-%m-%d %H:%M")
        return "expired" if exp_jdt.togregorian() < datetime.now() else "active"
    except Exception:
        return "active"


def _restore_speed_profile(username: Optional[str], group_name: Optional[str], unlock: bool = False) -> Optional[str]:
    if not username:
        return None
    try:
        if unlock:
            unlock_user(username)
        reset_radius_attrs(username)
        if group_name:
            change_group(username, group_name)
        return None
    except Exception as exc:
        return f"{type(exc).__name__}: {exc}"


def _fetch_ibs_times(username: Optional[str]) -> tuple[Optional[str], Optional[str], Optional[str]]:
    if not username:
        return None, None, None
    try:
        starts_at = get_user_start_date(username)
        expires_at = get_user_exp_date(username)
        return starts_at, expires_at, None
    except Exception as exc:
        return None, None, f"{type(exc).__name__}: {exc}"


def _update_order_times(order_id: int, starts_at: Optional[str], expires_at: Optional[str]) -> None:
    if starts_at is None and expires_at is None:
        return

    with _connect() as conn:
        cur = conn.cursor()
        if starts_at is not None and expires_at is not None:
            cur.execute(
                """
                UPDATE orders
                SET starts_at = ?,
                    expires_at = ?
                WHERE id = ?
                """,
                (starts_at, expires_at, order_id),
            )
        elif starts_at is not None:
            cur.execute(
                """
                UPDATE orders
                SET starts_at = ?
                WHERE id = ?
                """,
                (starts_at, order_id),
            )
        else:
            cur.execute(
                """
                UPDATE orders
                SET expires_at = ?
                WHERE id = ?
                """,
                (expires_at, order_id),
            )
        conn.commit()


def _append_warning(current_warning: Optional[str], new_warning: Optional[str]) -> Optional[str]:
    if not new_warning:
        return current_warning
    if not current_warning:
        return new_warning
    return f"{current_warning}\n{new_warning}"


def _apply_live_plan_change(
    username: Optional[str],
    group_name: Optional[str],
    order_id: int,
    usage_total_mb: int,
    total_limit_mb: int,
    unlock: bool = False,
) -> tuple[Optional[str], Optional[str], Optional[str], bool]:
    if not username:
        return None, None, None, False

    warning = _restore_speed_profile(username, group_name, unlock=unlock)
    starts_at, expires_at, time_warning = _fetch_ibs_times(username)
    warning = _append_warning(warning, time_warning)

    limit_applied = False
    if total_limit_mb > 0 and int(usage_total_mb or 0) >= int(total_limit_mb or 0):
        try:
            from services.scheduler_services.limit_speed import apply_limit, current_limit_speed

            if unlock:
                unlock_user(username)
            apply_limit(username=username, order_id=order_id, speed=current_limit_speed())
            limit_applied = True
        except Exception as exc:
            warning = _append_warning(warning, f"{type(exc).__name__}: {exc}")

    return starts_at, expires_at, warning, limit_applied


def _sync_volume_speed_state(
    username: Optional[str],
    group_name: Optional[str],
    order_id: int,
    usage_total_mb: int,
    total_limit_mb: int,
    unlock: bool = False,
) -> tuple[Optional[str], bool]:
    if not username:
        return None, False

    if total_limit_mb > 0 and int(usage_total_mb or 0) >= int(total_limit_mb or 0):
        try:
            from services.scheduler_services.limit_speed import apply_limit, current_limit_speed

            if unlock:
                unlock_user(username)
            apply_limit(username=username, order_id=order_id, speed=current_limit_speed())
            return None, True
        except Exception as exc:
            return f"{type(exc).__name__}: {exc}", False

    return _restore_speed_profile(username, group_name, unlock=unlock), False


def cancel_order(order_id: int, admin_id: Optional[int] = None, note: Optional[str] = None) -> Optional[dict]:
    username = None
    should_release_account = False
    should_reset_account = False
    ibs_warning = None

    with _connect() as conn:
        cur = conn.cursor()
        order = cur.execute("SELECT * FROM orders WHERE id = ? LIMIT 1", (order_id,)).fetchone()
        if not order:
            return None
        if order["status"] in FINAL_ORDER_STATUSES:
            return None

        username = order["username"]
        affected_order_ids = {int(order["id"])}
        canceled_children = 0
        restored_parent_status = None

        children = cur.execute(
            """
            SELECT *
            FROM orders
            WHERE is_renewal_of_order = ?
              AND status NOT IN ('canceled', 'renewed', 'archived', 'converted')
            ORDER BY id DESC
            """,
            (order_id,),
        ).fetchall()

        parent = None
        if order["is_renewal_of_order"]:
            parent = cur.execute(
                "SELECT * FROM orders WHERE id = ? LIMIT 1",
                (order["is_renewal_of_order"],),
            ).fetchone()

        if parent and order["status"] in {"waiting_for_payment", "reserved"}:
            restored_parent_status = _status_after_restore(parent)
            cur.execute(
                "UPDATE orders SET status = ? WHERE id = ?",
                (restored_parent_status, parent["id"]),
            )

        for child in children:
            cur.execute("UPDATE orders SET status = 'canceled' WHERE id = ?", (child["id"],))
            affected_order_ids.add(int(child["id"]))
            canceled_children += 1

        cur.execute("UPDATE orders SET status = 'canceled' WHERE id = ?", (order_id,))

        if order["status"] in LIVE_ORDER_STATUSES:
            should_release_account = True
            should_reset_account = True
        elif order["status"] == "waiting_for_payment" and not order["is_renewal_of_order"]:
            should_release_account = True

        open_rows = []
        if username and should_release_account:
            placeholders = ", ".join("?" for _ in affected_order_ids)
            params = [username, *sorted(affected_order_ids)]
            open_rows = cur.execute(
                f"""
                SELECT id
                FROM orders
                WHERE username = ?
                  AND status NOT IN ('canceled', 'renewed', 'archived', 'converted')
                  AND id NOT IN ({placeholders})
                """,
                params,
            ).fetchall()

            if not open_rows:
                cur.execute(
                    """
                    UPDATE accounts
                    SET status = 'free',
                        order_id = NULL
                    WHERE username = ?
                    """,
                    (username,),
                )

        conn.commit()

    if username and should_reset_account and not open_rows:
        ibs_warning = _reset_or_release_account(username)

    return {
        "order_id": order_id,
        "username": username,
        "canceled_children": canceled_children,
        "restored_parent_status": restored_parent_status,
        "note": note,
        "admin_id": admin_id,
        "ibs_warning": ibs_warning,
    }


def _reset_or_release_account(username: str) -> Optional[str]:
    try:
        reset_account_client(username)
        return None
    except Exception as exc:
        return f"{type(exc).__name__}: {exc}"


def change_order_plan(order_id: int, new_plan_id: int, admin_id: Optional[int] = None) -> Optional[dict]:
    username = None
    group_name = None
    live_service = False
    ibs_warning = None
    limit_applied = False

    with _connect() as conn:
        cur = conn.cursor()
        order = cur.execute(
            """
            SELECT o.*, p.name AS plan_name
            FROM orders o
            LEFT JOIN plans p ON p.id = o.plan_id
            WHERE o.id = ?
            LIMIT 1
            """,
            (order_id,),
        ).fetchone()
        if not order:
            return None
        if order["status"] in FINAL_ORDER_STATUSES:
            return None

        new_plan = cur.execute(
            """
            SELECT *
            FROM plans
            WHERE id = ?
              AND COALESCE(is_archived, 0) = 0
            LIMIT 1
            """,
            (new_plan_id,),
        ).fetchone()
        if not new_plan:
            return None

        old_price = int(order["price"] or 0)
        new_price = int(new_plan["price"] or 0)
        price_diff = new_price - old_price
        username = order["username"]
        group_name = new_plan["group_name"]
        live_service = order["status"] in LIVE_ORDER_STATUSES
        was_usage_locked = bool(int(order["usage_lock_applied"] or 0))

        if order["user_id"] and order["status"] in PAID_ORDER_STATUSES and price_diff != 0:
            cur.execute(
                """
                UPDATE users
                SET balance = COALESCE(balance, 0) - ?
                WHERE id = ?
                """,
                (price_diff, order["user_id"]),
            )

        start_text = order["starts_at"]
        expires_text = order["expires_at"]
        usage_sent_mb = order["usage_sent_mb"]
        usage_received_mb = order["usage_received_mb"]
        usage_total_mb = order["usage_total_mb"]
        total_limit_mb = int((int(new_plan["volume_gb"] or 0) + int(order["extra_volume_gb"] or 0)) * 1024)

        cur.execute(
            """
            UPDATE orders
            SET plan_id = ?,
                price = ?,
                volume_gb = ?,
                starts_at = ?,
                expires_at = ?,
                usage_sent_mb = ?,
                usage_received_mb = ?,
                usage_total_mb = ?,
                last_notif_level = 0,
                usage_applied_speed = NULL,
                usage_notif_level = 0,
                usage_lock_applied = 0
            WHERE id = ?
            """,
            (
                new_plan["id"],
                new_price,
                int(new_plan["volume_gb"] or 0),
                start_text,
                expires_text,
                usage_sent_mb,
                usage_received_mb,
                usage_total_mb,
                order_id,
            ),
        )
        conn.commit()

        new_balance = None
        if order["user_id"]:
            balance_row = cur.execute("SELECT balance FROM users WHERE id = ?", (order["user_id"],)).fetchone()
            new_balance = int(balance_row["balance"] or 0) if balance_row else None

    if live_service:
        synced_start, synced_expire, ibs_warning, limit_applied = _apply_live_plan_change(
            username=username,
            group_name=group_name,
            order_id=order_id,
            usage_total_mb=int(usage_total_mb or 0),
            total_limit_mb=total_limit_mb,
            unlock=was_usage_locked,
        )
        start_text = synced_start or start_text
        expires_text = synced_expire or expires_text
        _update_order_times(order_id, synced_start, synced_expire)

    return {
        "order_id": order_id,
        "username": username,
        "old_plan_name": order["plan_name"],
        "new_plan_name": new_plan["name"],
        "old_price": old_price,
        "new_price": new_price,
        "price_diff": price_diff,
        "new_balance": new_balance,
        "admin_id": admin_id,
        "starts_at": start_text,
        "expires_at": expires_text,
        "ibs_warning": ibs_warning,
        "limit_applied": limit_applied,
    }


def adjust_manual_extra_volume(order_id: int, volume_gb: int, admin_id: Optional[int] = None,
                               note: Optional[str] = None) -> dict:
    delta_volume = int(volume_gb or 0)
    if delta_volume == 0:
        return {"ok": False, "error": "invalid_delta"}

    username = None
    group_name = None
    live_service = False
    ibs_warning = None
    limit_applied = False

    with _connect() as conn:
        cur = conn.cursor()
        order = cur.execute(
            """
            SELECT o.*, p.name AS plan_name, p.group_name
            FROM orders o
            LEFT JOIN plans p ON p.id = o.plan_id
            WHERE o.id = ?
            LIMIT 1
            """,
            (order_id,),
        ).fetchone()
        if not order or order["status"] in FINAL_ORDER_STATUSES:
            return {"ok": False, "error": "order_not_found"}

        username = order["username"]
        group_name = order["group_name"]
        live_service = order["status"] in LIVE_ORDER_STATUSES
        was_usage_locked = bool(int(order["usage_lock_applied"] or 0))
        current_extra_volume = int(order["extra_volume_gb"] or 0)
        new_extra_volume = current_extra_volume + delta_volume
        if new_extra_volume < 0:
            return {
                "ok": False,
                "error": "insufficient_extra_volume",
                "current_extra_volume_gb": current_extra_volume,
            }

        usage_total_mb = int(order["usage_total_mb"] or 0)
        total_limit_mb = int((int(order["volume_gb"] or 0) + new_extra_volume) * 1024)
        now_text = _now_text()
        source_type = "admin_manual_add" if delta_volume > 0 else "admin_manual_reduce"

        cur.execute(
            """
            UPDATE orders
            SET extra_volume_gb = ?,
                usage_applied_speed = NULL,
                usage_notif_level = 0,
                usage_lock_applied = 0
            WHERE id = ?
            """,
            (new_extra_volume, order_id),
        )
        cur.execute(
            """
            INSERT INTO order_volume_allocations (
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
            )
            VALUES (?, ?, NULL, NULL, ?, 'applied', ?, 0, ?, ?, ?, ?)
            """,
            (
                order_id,
                int(order["user_id"] or 0),
                source_type,
                delta_volume,
                (note or "").strip() or None,
                admin_id,
                now_text,
                now_text,
            ),
        )
        conn.commit()

    if live_service:
        ibs_warning, limit_applied = _sync_volume_speed_state(
            username=username,
            group_name=group_name,
            order_id=order_id,
            usage_total_mb=usage_total_mb,
            total_limit_mb=total_limit_mb,
            unlock=was_usage_locked,
        )

    return {
        "ok": True,
        "order_id": order_id,
        "username": username,
        "plan_name": order["plan_name"],
        "volume_delta_gb": delta_volume,
        "changed_volume_gb": abs(delta_volume),
        "new_extra_volume_gb": new_extra_volume,
        "admin_id": admin_id,
        "note": note,
        "ibs_warning": ibs_warning,
        "limit_applied": limit_applied,
    }


def add_manual_extra_volume(order_id: int, volume_gb: int, admin_id: Optional[int] = None,
                            note: Optional[str] = None) -> Optional[dict]:
    result = adjust_manual_extra_volume(
        order_id=order_id,
        volume_gb=volume_gb,
        admin_id=admin_id,
        note=note,
    )
    return result if result.get("ok") else None


def purchase_volume_package(user_id: int, order_id: int, package_id: int) -> dict:
    username = None
    group_name = None
    live_service = False
    ibs_warning = None

    with _connect() as conn:
        cur = conn.cursor()
        order = cur.execute(
            """
            SELECT
                o.*,
                p.name AS plan_name,
                p.group_name,
                p.category,
                p.is_unlimited
            FROM orders o
            JOIN plans p ON p.id = o.plan_id
            WHERE o.id = ?
              AND o.user_id = ?
              AND o.status IN ('active', 'waiting_for_renewal', 'waiting_for_renewal_not_paid', 'reserved')
            LIMIT 1
            """,
            (order_id, user_id),
        ).fetchone()
        if not order:
            return {"ok": False, "error": "order_not_found"}
        if int(order["is_unlimited"] or 0) == 1:
            return {"ok": False, "error": "order_unlimited"}

        package = cur.execute(
            """
            SELECT *
            FROM volume_packages vp
            WHERE vp.id = ?
              AND COALESCE(vp.is_active, 1) = 1
              AND COALESCE(vp.is_archived, 0) = 0
              AND (
                NOT EXISTS (
                    SELECT 1
                    FROM volume_package_segments vps
                    JOIN segments s ON s.id = vps.segment_id
                    WHERE vps.package_id = vp.id
                      AND COALESCE(s.is_active, 1) = 1
                )
                OR EXISTS (
                    SELECT 1
                    FROM volume_package_segments vps
                    JOIN segments s ON s.id = vps.segment_id
                    JOIN segment_users su ON su.segment_id = vps.segment_id
                    WHERE vps.package_id = vp.id
                      AND COALESCE(s.is_active, 1) = 1
                      AND su.user_id = ?
                )
              )
              AND (
                NOT EXISTS (
                    SELECT 1
                    FROM volume_package_categories vpc
                    WHERE vpc.package_id = vp.id
                )
                OR EXISTS (
                    SELECT 1
                    FROM volume_package_categories vpc
                    WHERE vpc.package_id = vp.id
                      AND vpc.category = COALESCE(NULLIF(?, ''), 'standard')
                )
              )
            LIMIT 1
            """,
            (package_id, user_id, order["category"]),
        ).fetchone()
        if not package:
            return {"ok": False, "error": "package_not_found"}

        balance_row = cur.execute("SELECT balance FROM users WHERE id = ? LIMIT 1", (user_id,)).fetchone()
        current_balance = int(balance_row["balance"] or 0) if balance_row else 0
        package_price = int(package["price"] or 0)
        if current_balance < package_price:
            return {
                "ok": False,
                "error": "insufficient_balance",
                "required": package_price - current_balance,
                "current_balance": current_balance,
                "package_price": package_price,
            }

        username = order["username"]
        group_name = order["group_name"]
        live_service = order["status"] in LIVE_ORDER_STATUSES
        was_usage_locked = bool(int(order["usage_lock_applied"] or 0))
        now_text = _now_text()
        new_extra_volume = int(order["extra_volume_gb"] or 0) + int(package["volume_gb"] or 0)
        new_balance = current_balance - package_price

        cur.execute(
            "UPDATE users SET balance = ? WHERE id = ?",
            (new_balance, user_id),
        )
        cur.execute(
            """
            UPDATE orders
            SET extra_volume_gb = ?,
                usage_applied_speed = NULL,
                usage_notif_level = 0,
                usage_lock_applied = 0
            WHERE id = ?
            """,
            (new_extra_volume, order_id),
        )
        cur.execute(
            """
            INSERT INTO order_volume_allocations (
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
            )
            VALUES (?, ?, ?, ?, 'user_package', 'applied', ?, ?, NULL, NULL, ?, ?)
            """,
            (
                order_id,
                user_id,
                package["id"],
                package["name"],
                int(package["volume_gb"] or 0),
                package_price,
                now_text,
                now_text,
            ),
        )
        conn.commit()

    if live_service:
        ibs_warning = _restore_speed_profile(username, group_name, unlock=was_usage_locked)

    return {
        "ok": True,
        "order_id": order_id,
        "username": username,
        "package_id": package_id,
        "package_name": package["name"],
        "volume_gb": int(package["volume_gb"] or 0),
        "price": package_price,
        "new_balance": new_balance,
        "new_extra_volume_gb": new_extra_volume,
        "ibs_warning": ibs_warning,
    }
