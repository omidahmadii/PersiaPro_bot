from __future__ import annotations

import logging
import sqlite3
from datetime import datetime, timedelta
from typing import Any, Optional

import jdatetime

from config import DB_PATH
from services.IBSng import change_group, reset_account_client
from services.scheduler_services.telegram_safe import send_scheduler_notification
from services.runtime_settings import get_bool_setting, get_int_setting, get_text_setting

logger = logging.getLogger(__name__)

CONVERSION_STATUS_CONVERTED = "converted"
CONVERSION_SERVICE_SOURCE = "conversion_offer"

DEFAULT_MENU_TITLE = "طرح تبدیل سرویس"
DEFAULT_DISABLED_TEXT = "در حال حاضر طرح تبدیل سرویس فعال نیست."

ACTIVE_SERVICE_STATUSES = {"active"}


def _connect() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def _now_text(timespec: str = "minutes") -> str:
    return datetime.now().isoformat(sep=" ", timespec=timespec)


def _now_jalali() -> jdatetime.datetime:
    return jdatetime.datetime.now()


def _format_jalali(dt: jdatetime.datetime) -> str:
    return dt.strftime("%Y-%m-%d %H:%M")


def _parse_jalali(value: Optional[str]) -> Optional[jdatetime.datetime]:
    text = str(value or "").strip()
    if not text:
        return None

    for fmt in ("%Y-%m-%d %H:%M", "%Y-%m-%d %H:%M:%S"):
        try:
            return jdatetime.datetime.strptime(text, fmt)
        except Exception:
            continue
    return None


def _format_price(amount: int) -> str:
    try:
        return f"{int(amount):,}"
    except Exception:
        return str(amount)


def _format_gb(value: Optional[float]) -> str:
    if value is None:
        return "-"

    numeric = float(value)
    if abs(numeric - int(numeric)) < 0.01:
        return str(int(numeric))
    return f"{numeric:.2f}".rstrip("0").rstrip(".")


def _split_config_tokens(raw_value: Optional[str]) -> list[str]:
    normalized = str(raw_value or "").replace("،", ",").replace("\n", ",")
    return [token.strip() for token in normalized.split(",") if token.strip()]


def _parse_config_int_tokens(raw_value: Optional[str]) -> list[int]:
    values: list[int] = []
    seen: set[int] = set()
    for token in _split_config_tokens(raw_value):
        try:
            value = int(token)
        except Exception:
            continue
        if value <= 0 or value in seen:
            continue
        seen.add(value)
        values.append(value)
    return values


def _parse_config_group_tokens(raw_value: Optional[str]) -> list[str]:
    values: list[str] = []
    seen: set[str] = set()
    for token in _split_config_tokens(raw_value):
        normalized = token.lower()
        if normalized in seen:
            continue
        seen.add(normalized)
        values.append(normalized)
    return values


def _render_template(template_key: str, context: dict[str, Any], fallback: str = "") -> str:
    template = get_text_setting(template_key, fallback)
    try:
        return template.format(**context)
    except Exception:
        logger.warning("Failed to render conversion template %s", template_key, exc_info=True)
        return template


def _base_template_context() -> dict[str, Any]:
    config = get_conversion_config()
    return {
        "menu_title": config["menu_title"],
        "new_duration_days": config["new_duration_days"],
        "new_volume_gb": config["new_volume_gb"],
        "conversion_price": config["price"],
        "conversion_price_formatted": _format_price(config["price"]),
        "topup_package_title": config["topup_package_title"],
        "topup_package_volume_gb": config["topup_package_volume_gb"],
        "topup_package_price": config["topup_package_price"],
        "topup_package_price_formatted": _format_price(config["topup_package_price"]),
    }


def get_conversion_config() -> dict[str, Any]:
    source_plan_ids = _parse_config_int_tokens(get_text_setting("conversion_source_plan_ids", ""))
    source_group_names = _parse_config_group_tokens(get_text_setting("conversion_source_group_names", ""))
    return {
        "enabled": get_bool_setting("feature_conversion_enabled", default=False),
        "menu_title": get_text_setting("conversion_menu_title", DEFAULT_MENU_TITLE),
        "min_days_remaining": max(get_int_setting("conversion_min_days_remaining", 30), 0),
        "min_remaining_volume_gb": max(get_int_setting("conversion_min_remaining_volume_gb", 2), 0),
        "target_plan_id": max(get_int_setting("conversion_target_plan_id", 0), 0),
        "new_duration_days": max(get_int_setting("conversion_new_duration_days", 30), 1),
        "new_volume_gb": max(get_int_setting("conversion_new_volume_gb", 2), 0),
        "price": max(get_int_setting("conversion_price", 0), 0),
        "notification_enabled": get_bool_setting("conversion_notification_enabled", default=False),
        "notification_cooldown_days": max(get_int_setting("conversion_notification_cooldown_days", 7), 0),
        "show_only_marked_services": get_bool_setting("conversion_show_only_marked_services", default=True),
        "topup_package_title": get_text_setting("conversion_topup_package_title", "2 گیگ"),
        "topup_package_volume_gb": max(get_int_setting("conversion_topup_package_volume_gb", 2), 0),
        "topup_package_price": max(get_int_setting("conversion_topup_package_price", 750), 0),
        "source_plan_ids": source_plan_ids,
        "source_plan_id_set": set(source_plan_ids),
        "source_group_names": source_group_names,
        "source_group_name_set": set(source_group_names),
    }


def get_conversion_menu_title() -> str:
    return get_conversion_config()["menu_title"]


def get_conversion_disabled_text() -> str:
    return get_text_setting("message_conversion_disabled", DEFAULT_DISABLED_TEXT)


def _get_target_plan_from_conn(conn: sqlite3.Connection, plan_id: int) -> Optional[dict[str, Any]]:
    if plan_id <= 0:
        return None

    cursor = conn.cursor()
    cursor.execute(
        """
        SELECT
            id,
            name,
            volume_gb,
            duration_days,
            duration_months,
            group_name,
            price,
            visible,
            COALESCE(is_archived, 0) AS is_archived
        FROM plans
        WHERE id = ?
          AND COALESCE(is_archived, 0) = 0
        LIMIT 1
        """,
        (plan_id,),
    )
    row = cursor.fetchone()
    if not row:
        return None

    plan = dict(row)
    if not str(plan.get("group_name") or "").strip():
        logger.warning("Conversion target plan %s does not have group_name configured.", plan_id)
        return None
    return plan


def get_conversion_target_plan() -> Optional[dict[str, Any]]:
    config = get_conversion_config()
    with _connect() as conn:
        return _get_target_plan_from_conn(conn, int(config["target_plan_id"]))


def is_conversion_menu_enabled() -> bool:
    config = get_conversion_config()
    if not config["enabled"]:
        return False

    target_plan = get_conversion_target_plan()
    if not target_plan:
        logger.warning(
            "Conversion feature enabled but target plan is unavailable. plan_id=%s",
            config["target_plan_id"],
        )
        return False
    return True


def _fetch_service_from_conn(conn: sqlite3.Connection, service_id: int, user_id: Optional[int] = None) -> Optional[dict[str, Any]]:
    params: list[Any] = [service_id]
    query = """
        SELECT
            o.id,
            o.user_id,
            o.plan_id,
            o.username,
            o.status,
            o.price,
            o.created_at,
            o.volume_gb,
            o.extra_volume_gb,
            o.overused_volume_gb,
            o.usage_total_mb,
            o.remaining_volume_mb,
            o.usage_sent_mb,
            o.usage_received_mb,
            o.usage_last_update,
            o.usage_applied_speed,
            o.starts_at,
            o.expires_at,
            o.last_notif_level,
            o.is_renewal_of_order,
            o.usage_notif_level,
            o.auto_renew,
            o.eligible_for_conversion,
            o.old_limited_service,
            o.converted_by_offer,
            o.converted_to_service_id,
            o.replaced_from_service_id,
            o.service_source,
            o.closed_by_conversion_at,
            o.last_conversion_notification_at,
            p.name AS plan_name,
            p.group_name,
            COALESCE(p.is_unlimited, 0) AS is_unlimited,
            COALESCE(p.is_archived, 0) AS plan_is_archived
        FROM orders o
        JOIN plans p ON p.id = o.plan_id
        WHERE o.id = ?
    """
    if user_id is not None:
        query += "\nAND o.user_id = ?"
        params.append(user_id)

    cursor = conn.cursor()
    cursor.execute(query, params)
    row = cursor.fetchone()
    return dict(row) if row else None


def _fetch_active_services_for_user(conn: sqlite3.Connection, user_id: int) -> list[dict[str, Any]]:
    cursor = conn.cursor()
    cursor.execute(
        """
        SELECT
            o.id,
            o.user_id,
            o.plan_id,
            o.username,
            o.status,
            o.price,
            o.created_at,
            o.volume_gb,
            o.extra_volume_gb,
            o.overused_volume_gb,
            o.usage_total_mb,
            o.remaining_volume_mb,
            o.usage_sent_mb,
            o.usage_received_mb,
            o.usage_last_update,
            o.usage_applied_speed,
            o.starts_at,
            o.expires_at,
            o.last_notif_level,
            o.is_renewal_of_order,
            o.usage_notif_level,
            o.auto_renew,
            o.eligible_for_conversion,
            o.old_limited_service,
            o.converted_by_offer,
            o.converted_to_service_id,
            o.replaced_from_service_id,
            o.service_source,
            o.closed_by_conversion_at,
            o.last_conversion_notification_at,
            p.name AS plan_name,
            p.group_name,
            COALESCE(p.is_unlimited, 0) AS is_unlimited,
            COALESCE(p.is_archived, 0) AS plan_is_archived
        FROM orders o
        JOIN plans p ON p.id = o.plan_id
        WHERE o.user_id = ?
          AND o.status = 'active'
        ORDER BY o.username ASC, o.id DESC
        """,
        (user_id,),
    )
    return [dict(row) for row in cursor.fetchall()]


def _existing_replacement_service(conn: sqlite3.Connection, service_id: int) -> Optional[dict[str, Any]]:
    cursor = conn.cursor()
    cursor.execute(
        """
        SELECT
            o.*,
            p.name AS plan_name,
            p.group_name
        FROM orders o
        LEFT JOIN plans p ON p.id = o.plan_id
        WHERE o.replaced_from_service_id = ?
        LIMIT 1
        """,
        (service_id,),
    )
    row = cursor.fetchone()
    return dict(row) if row else None


def _calculate_remaining_volume_gb(service: dict[str, Any]) -> Optional[float]:
    if int(service.get("is_unlimited") or 0) == 1:
        return None

    remaining_volume_mb = service.get("remaining_volume_mb")
    if remaining_volume_mb is not None:
        return max(float(remaining_volume_mb or 0) / 1024, 0.0)

    total_volume_gb = (
        float(service.get("volume_gb") or 0)
        + float(service.get("extra_volume_gb") or 0)
        + float(service.get("overused_volume_gb") or 0)
    )
    usage_total_mb = int(service.get("usage_total_mb") or 0)
    used_gb = float(usage_total_mb) / 1024
    return max(total_volume_gb - used_gb, 0.0)


def _calculate_days_remaining(service: dict[str, Any], now_jdt: Optional[jdatetime.datetime] = None) -> tuple[int, Optional[jdatetime.timedelta]]:
    now_jdt = now_jdt or _now_jalali()
    expires_at = _parse_jalali(service.get("expires_at"))
    if not expires_at:
        return 0, None

    remaining_delta = expires_at - now_jdt
    total_seconds = int(remaining_delta.total_seconds())
    if total_seconds <= 0:
        return 0, remaining_delta

    return max(total_seconds // 86400, 0), remaining_delta


def _is_notification_on_cooldown(service: dict[str, Any], cooldown_days: int) -> bool:
    if cooldown_days <= 0:
        return False

    raw_value = str(service.get("last_conversion_notification_at") or "").strip()
    if not raw_value:
        return False

    for fmt in ("%Y-%m-%d %H:%M", "%Y-%m-%d %H:%M:%S"):
        try:
            last_sent_at = datetime.strptime(raw_value, fmt)
            return last_sent_at > (datetime.now() - timedelta(days=cooldown_days))
        except Exception:
            continue
    return False


def _get_conversion_scope_flags(service: dict[str, Any], config: dict[str, Any]) -> dict[str, bool]:
    marked_for_conversion = int(service.get("eligible_for_conversion") or 0) == 1
    old_limited_service = int(service.get("old_limited_service") or 0) == 1
    source_plan_match = int(service.get("plan_id") or 0) in config.get("source_plan_id_set", set())
    source_group_match = str(service.get("group_name") or "").strip().lower() in config.get("source_group_name_set", set())
    return {
        "marked_for_conversion": marked_for_conversion,
        "old_limited_service": old_limited_service,
        "source_plan_match": source_plan_match,
        "source_group_match": source_group_match,
        "in_scope": marked_for_conversion or old_limited_service or source_plan_match or source_group_match,
    }


def evaluate_conversion_eligibility(
    service: dict[str, Any],
    *,
    config: Optional[dict[str, Any]] = None,
    target_plan: Optional[dict[str, Any]] = None,
    conn: Optional[sqlite3.Connection] = None,
) -> dict[str, Any]:
    config = config or get_conversion_config()
    target_plan = target_plan or get_conversion_target_plan()
    now_jdt = _now_jalali()
    remaining_volume_gb = _calculate_remaining_volume_gb(service)
    days_remaining, remaining_delta = _calculate_days_remaining(service, now_jdt=now_jdt)
    existing_replacement = None

    if conn is not None:
        existing_replacement = _existing_replacement_service(conn, int(service["id"]))

    reasons: list[str] = []
    scope_flags = _get_conversion_scope_flags(service, config)

    if not config["enabled"]:
        reasons.append("feature_disabled")
    if not target_plan:
        reasons.append("target_plan_unavailable")
    if str(service.get("status") or "").strip() not in ACTIVE_SERVICE_STATUSES:
        reasons.append("service_not_active")

    expires_at = _parse_jalali(service.get("expires_at"))
    if not expires_at:
        reasons.append("missing_expire_at")
    elif expires_at <= now_jdt:
        reasons.append("service_expired")

    min_delta = jdatetime.timedelta(days=int(config["min_days_remaining"]))
    if remaining_delta is None or remaining_delta < min_delta:
        reasons.append("insufficient_days_remaining")

    if remaining_volume_gb is not None and remaining_volume_gb < float(config["min_remaining_volume_gb"]):
        reasons.append("insufficient_remaining_volume")

    if int(service.get("converted_by_offer") or 0) == 1:
        reasons.append("already_converted")
    if service.get("converted_to_service_id"):
        reasons.append("already_converted")
    if existing_replacement:
        reasons.append("already_replaced")
    if str(service.get("status") or "").strip() == CONVERSION_STATUS_CONVERTED:
        reasons.append("already_converted")

    if config["show_only_marked_services"]:
        if not scope_flags["marked_for_conversion"]:
            reasons.append("service_not_marked")
    elif not scope_flags["in_scope"]:
        reasons.append("service_not_in_scope")

    return {
        "is_eligible": len(reasons) == 0,
        "reasons": list(dict.fromkeys(reasons)),
        "days_remaining": days_remaining,
        "remaining_volume_gb": remaining_volume_gb,
        "remaining_volume_display": "نامحدود" if remaining_volume_gb is None else _format_gb(remaining_volume_gb),
        "marked_for_conversion": scope_flags["marked_for_conversion"],
        "old_limited_service": scope_flags["old_limited_service"],
        "source_plan_match": scope_flags["source_plan_match"],
        "source_group_match": scope_flags["source_group_match"],
        "in_conversion_scope": scope_flags["in_scope"],
        "notification_on_cooldown": _is_notification_on_cooldown(
            service,
            int(config["notification_cooldown_days"]),
        ),
    }


def _enrich_service(service: dict[str, Any], eligibility: dict[str, Any]) -> dict[str, Any]:
    enriched = dict(service)
    enriched.update(
        {
            "days_remaining": eligibility["days_remaining"],
            "remaining_volume_gb": eligibility["remaining_volume_gb"],
            "remaining_volume_display": eligibility["remaining_volume_display"],
            "eligibility": eligibility,
        }
    )
    return enriched


def get_eligible_conversion_services(user_id: int) -> list[dict[str, Any]]:
    config = get_conversion_config()
    with _connect() as conn:
        target_plan = _get_target_plan_from_conn(conn, int(config["target_plan_id"]))
        services = _fetch_active_services_for_user(conn, user_id)

        eligible_services: list[dict[str, Any]] = []
        for service in services:
            eligibility = evaluate_conversion_eligibility(
                service,
                config=config,
                target_plan=target_plan,
                conn=conn,
            )
            if eligibility["is_eligible"]:
                eligible_services.append(_enrich_service(service, eligibility))
        return eligible_services


def get_conversion_service_for_user(user_id: int, service_id: int) -> tuple[Optional[dict[str, Any]], dict[str, Any]]:
    config = get_conversion_config()
    default_eligibility = {
        "is_eligible": False,
        "reasons": ["service_not_found"],
        "days_remaining": 0,
        "remaining_volume_gb": 0.0,
        "remaining_volume_display": "0",
        "marked_for_conversion": False,
        "old_limited_service": False,
        "source_plan_match": False,
        "source_group_match": False,
        "in_conversion_scope": False,
        "notification_on_cooldown": False,
    }

    with _connect() as conn:
        target_plan = _get_target_plan_from_conn(conn, int(config["target_plan_id"]))
        service = _fetch_service_from_conn(conn, service_id, user_id=user_id)
        if not service:
            return None, default_eligibility

        eligibility = evaluate_conversion_eligibility(
            service,
            config=config,
            target_plan=target_plan,
            conn=conn,
        )
        return _enrich_service(service, eligibility), eligibility


def _build_log_payload(
    service: dict[str, Any],
    *,
    target_plan_id: Optional[int],
    new_service_id: Optional[int],
    status: str,
    failure_reason: Optional[str] = None,
    notification_sent_at: Optional[str] = None,
    viewed_at: Optional[str] = None,
    selected_at: Optional[str] = None,
    confirmed_at: Optional[str] = None,
    converted_at: Optional[str] = None,
    created_at: Optional[str] = None,
) -> tuple[Any, ...]:
    now_text = created_at or _now_text()
    remaining_volume_gb = _calculate_remaining_volume_gb(service)
    return (
        int(service["user_id"]),
        int(service["id"]),
        int(service.get("plan_id") or 0) if service.get("plan_id") is not None else None,
        service.get("expires_at"),
        round(float(remaining_volume_gb or 0), 2) if remaining_volume_gb is not None else None,
        target_plan_id,
        new_service_id,
        status,
        notification_sent_at,
        viewed_at,
        selected_at,
        confirmed_at,
        converted_at,
        failure_reason,
        now_text,
        now_text,
    )


def _insert_conversion_log(
    cursor: sqlite3.Cursor,
    service: dict[str, Any],
    *,
    target_plan_id: Optional[int],
    new_service_id: Optional[int] = None,
    status: str,
    failure_reason: Optional[str] = None,
    notification_sent_at: Optional[str] = None,
    viewed_at: Optional[str] = None,
    selected_at: Optional[str] = None,
    confirmed_at: Optional[str] = None,
    converted_at: Optional[str] = None,
    created_at: Optional[str] = None,
) -> None:
    cursor.execute(
        """
        INSERT INTO conversion_offer_logs (
            user_id,
            service_id,
            previous_plan_id,
            previous_expire_at,
            previous_remaining_volume,
            target_plan_id,
            new_service_id,
            status,
            notification_sent_at,
            viewed_at,
            selected_at,
            confirmed_at,
            converted_at,
            failure_reason,
            created_at,
            updated_at
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        _build_log_payload(
            service,
            target_plan_id=target_plan_id,
            new_service_id=new_service_id,
            status=status,
            failure_reason=failure_reason,
            notification_sent_at=notification_sent_at,
            viewed_at=viewed_at,
            selected_at=selected_at,
            confirmed_at=confirmed_at,
            converted_at=converted_at,
            created_at=created_at,
        ),
    )


def log_conversion_viewed(user_id: int, services: list[dict[str, Any]]) -> None:
    if not services:
        return

    config = get_conversion_config()
    now_text = _now_text()
    with _connect() as conn:
        cursor = conn.cursor()
        for service in services:
            if int(service.get("user_id") or 0) != int(user_id):
                continue
            _insert_conversion_log(
                cursor,
                service,
                target_plan_id=int(config["target_plan_id"]) or None,
                status="viewed",
                viewed_at=now_text,
                created_at=now_text,
            )
        conn.commit()


def log_conversion_selected(service: dict[str, Any]) -> None:
    config = get_conversion_config()
    now_text = _now_text()
    with _connect() as conn:
        cursor = conn.cursor()
        _insert_conversion_log(
            cursor,
            service,
            target_plan_id=int(config["target_plan_id"]) or None,
            status="selected",
            selected_at=now_text,
            created_at=now_text,
        )
        conn.commit()


def log_conversion_cancelled(service: dict[str, Any]) -> None:
    config = get_conversion_config()
    now_text = _now_text()
    with _connect() as conn:
        cursor = conn.cursor()
        _insert_conversion_log(
            cursor,
            service,
            target_plan_id=int(config["target_plan_id"]) or None,
            status="cancelled",
            created_at=now_text,
        )
        conn.commit()


def _notify_user(user_id: int, text: str) -> bool:
    return send_scheduler_notification(chat_id=user_id, text=text, parse_mode="HTML", timeout=15)


def send_conversion_offer_notifications() -> None:
    config = get_conversion_config()
    if not config["enabled"] or not config["notification_enabled"]:
        return

    with _connect() as conn:
        target_plan = _get_target_plan_from_conn(conn, int(config["target_plan_id"]))
        if not target_plan:
            logger.warning(
                "Conversion notification skipped because target plan is unavailable. plan_id=%s",
                config["target_plan_id"],
            )
            return

        cursor = conn.cursor()
        cursor.execute(
            """
            SELECT
                o.id,
                o.user_id,
                o.plan_id,
                o.username,
                o.status,
                o.price,
                o.created_at,
                o.volume_gb,
                o.extra_volume_gb,
                o.overused_volume_gb,
                o.usage_total_mb,
                o.remaining_volume_mb,
                o.usage_sent_mb,
                o.usage_received_mb,
                o.usage_last_update,
                o.usage_applied_speed,
                o.starts_at,
                o.expires_at,
                o.last_notif_level,
                o.is_renewal_of_order,
                o.usage_notif_level,
                o.auto_renew,
                o.eligible_for_conversion,
                o.old_limited_service,
                o.converted_by_offer,
                o.converted_to_service_id,
                o.replaced_from_service_id,
                o.service_source,
                o.closed_by_conversion_at,
                o.last_conversion_notification_at,
                p.name AS plan_name,
                p.group_name,
                COALESCE(p.is_unlimited, 0) AS is_unlimited,
                COALESCE(p.is_archived, 0) AS plan_is_archived
            FROM orders o
            JOIN plans p ON p.id = o.plan_id
            JOIN users u ON u.id = o.user_id
            WHERE o.status = 'active'
              AND o.user_id > 0
              AND COALESCE(u.role, '') != 'offline'
            ORDER BY o.user_id ASC, o.id ASC
            """
        )
        rows = [dict(row) for row in cursor.fetchall()]

        eligible_by_user: dict[int, list[dict[str, Any]]] = {}
        all_eligible_by_user: dict[int, list[dict[str, Any]]] = {}

        for service in rows:
            eligibility = evaluate_conversion_eligibility(
                service,
                config=config,
                target_plan=target_plan,
                conn=conn,
            )
            if not eligibility["is_eligible"]:
                continue

            user_id = int(service["user_id"])
            all_eligible_by_user.setdefault(user_id, []).append(service)
            if eligibility["notification_on_cooldown"]:
                continue

            eligible_by_user.setdefault(user_id, []).append(service)

        if not eligible_by_user:
            return

        notification_text = _render_template(
            "message_conversion_notification",
            _base_template_context(),
            "",
        )
        now_text = _now_text()

        for user_id, services in eligible_by_user.items():
            sent = _notify_user(user_id, notification_text)
            if not sent:
                continue

            cursor.executemany(
                """
                UPDATE orders
                SET last_conversion_notification_at = ?
                WHERE id = ?
                """,
                [(now_text, int(service["id"])) for service in all_eligible_by_user.get(user_id, [])],
            )
            for service in services:
                _insert_conversion_log(
                    cursor,
                    service,
                    target_plan_id=int(config["target_plan_id"]) or None,
                    status="notified",
                    notification_sent_at=now_text,
                    created_at=now_text,
                )

        conn.commit()


def build_conversion_template_context(service: Optional[dict[str, Any]] = None) -> dict[str, Any]:
    context = _base_template_context()
    if service:
        context.update(
            {
                "service_id": service.get("id"),
                "service_username": service.get("username") or "-",
                "service_name": service.get("username") or f"#{service.get('id')}",
                "plan_name": service.get("plan_name") or "-",
                "expires_at": service.get("expires_at") or "-",
                "days_remaining": service.get("days_remaining") or 0,
                "remaining_volume_gb": _format_gb(service.get("remaining_volume_gb")),
                "remaining_volume_display": service.get("remaining_volume_display") or "-",
            }
        )
    return context


def get_conversion_text(template_key: str, service: Optional[dict[str, Any]] = None, fallback: str = "") -> str:
    return _render_template(template_key, build_conversion_template_context(service), fallback)


def apply_conversion(user_id: int, service_id: int) -> dict[str, Any]:
    config = get_conversion_config()
    if not config["enabled"]:
        return {"ok": False, "error": "feature_disabled"}

    conn = _connect()
    try:
        conn.execute("BEGIN IMMEDIATE")
        target_plan = _get_target_plan_from_conn(conn, int(config["target_plan_id"]))
        if not target_plan:
            conn.rollback()
            logger.warning(
                "Conversion apply skipped because target plan is unavailable. user_id=%s service_id=%s plan_id=%s",
                user_id,
                service_id,
                config["target_plan_id"],
            )
            return {"ok": False, "error": "target_plan_unavailable"}

        service = _fetch_service_from_conn(conn, service_id, user_id=user_id)
        if not service:
            conn.rollback()
            return {"ok": False, "error": "service_not_found"}

        existing_replacement = _existing_replacement_service(conn, service_id)
        if service.get("converted_to_service_id") or existing_replacement:
            new_service = existing_replacement
            if not new_service and service.get("converted_to_service_id"):
                new_service = _fetch_service_from_conn(
                    conn,
                    int(service["converted_to_service_id"]),
                    user_id=user_id,
                )
            conn.commit()
            return {
                "ok": True,
                "already_converted": True,
                "service": service,
                "new_service": new_service,
                "target_plan": target_plan,
            }

        eligibility = evaluate_conversion_eligibility(
            service,
            config=config,
            target_plan=target_plan,
            conn=conn,
        )
        if not eligibility["is_eligible"]:
            now_text = _now_text()
            _insert_conversion_log(
                conn.cursor(),
                service,
                target_plan_id=int(target_plan["id"]),
                status="no_longer_eligible",
                failure_reason=", ".join(eligibility["reasons"]),
                created_at=now_text,
            )
            conn.commit()
            return {
                "ok": False,
                "error": "no_longer_eligible",
                "service": service,
                "eligibility": eligibility,
            }

        now_text = _now_text()

        cursor = conn.cursor()
        _insert_conversion_log(
            cursor,
            service,
            target_plan_id=int(target_plan["id"]),
            status="confirmed",
            confirmed_at=now_text,
            created_at=now_text,
        )
        cursor.execute(
            """
            INSERT INTO orders (
                user_id,
                plan_id,
                username,
                price,
                created_at,
                status,
                volume_gb,
                extra_volume_gb,
                overused_volume_gb,
                usage_sent_mb,
                usage_received_mb,
                usage_total_mb,
                remaining_volume_mb,
                usage_last_update,
                usage_applied_speed,
                usage_notif_level,
                starts_at,
                expires_at,
                last_notif_level,
                is_renewal_of_order,
                auto_renew,
                eligible_for_conversion,
                old_limited_service,
                converted_by_offer,
                converted_to_service_id,
                replaced_from_service_id,
                service_source,
                closed_by_conversion_at,
                last_conversion_notification_at
            )
            VALUES (?, ?, ?, ?, ?, 'active', ?, 0, 0, 0, 0, ?, NULL, NULL, 0, NULL, NULL, NULL, ?, 0, 0, 0, 0, NULL, ?, ?, NULL, NULL)
            """,
            (
                int(service["user_id"]),
                int(target_plan["id"]),
                service["username"],
                int(config["price"]),
                now_text,
                int(config["new_volume_gb"]),
                int(round(float(config["new_volume_gb"] or 0) * 1024)),
                int(service["id"]),
                int(service["id"]),
                CONVERSION_SERVICE_SOURCE,
            ),
        )
        new_service_id = int(cursor.lastrowid)

        cursor.execute(
            """
            UPDATE orders
            SET status = ?,
                remaining_volume_mb = 0,
                converted_by_offer = 1,
                converted_to_service_id = ?,
                eligible_for_conversion = 0,
                auto_renew = 0,
                closed_by_conversion_at = ?
            WHERE id = ?
            """,
            (
                CONVERSION_STATUS_CONVERTED,
                new_service_id,
                now_text,
                int(service["id"]),
            ),
        )
        cursor.execute(
            """
            UPDATE accounts
            SET order_id = ?,
                status = 'assigned'
            WHERE username = ?
            """,
            (new_service_id, service["username"]),
        )
        _insert_conversion_log(
            cursor,
            service,
            target_plan_id=int(target_plan["id"]),
            new_service_id=new_service_id,
            status="converted",
            converted_at=now_text,
            created_at=now_text,
        )
        conn.commit()

        new_service = _fetch_service_from_conn(conn, new_service_id, user_id=user_id)
    except Exception as exc:
        try:
            conn.rollback()
        except Exception:
            pass

        logger.exception("Conversion apply failed. user_id=%s service_id=%s", user_id, service_id)
        service = None
        try:
            service = _fetch_service_from_conn(conn, service_id, user_id=user_id)
        except Exception:
            service = None
        if service:
            try:
                cursor = conn.cursor()
                _insert_conversion_log(
                    cursor,
                    service,
                    target_plan_id=int(config["target_plan_id"]) or None,
                    status="failed",
                    failure_reason=f"{type(exc).__name__}: {exc}",
                    created_at=_now_text(),
                )
                conn.commit()
            except Exception:
                logger.warning("Failed to write conversion failure log.", exc_info=True)
        return {"ok": False, "error": "failed", "exception": str(exc)}
    finally:
        try:
            conn.close()
        except Exception:
            pass

    ibs_warning = None
    try:
        reset_account_client(str(service["username"]))
        change_group(str(service["username"]), str(target_plan["group_name"]))
    except Exception as exc:
        ibs_warning = f"{type(exc).__name__}: {exc}"
        logger.warning(
            "Conversion IBS sync warning. user_id=%s service_id=%s new_service_id=%s warning=%s",
            user_id,
            service_id,
            new_service_id,
            ibs_warning,
        )

    return {
        "ok": True,
        "already_converted": False,
        "service": service,
        "new_service": new_service,
        "target_plan": target_plan,
        "new_service_id": new_service_id,
        "ibs_warning": ibs_warning,
    }
