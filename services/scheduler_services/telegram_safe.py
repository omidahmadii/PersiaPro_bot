from __future__ import annotations

from typing import Any

import requests

from config import BOT_TOKEN

_IGNORABLE_ERROR_TOKENS = (
    "bot was blocked by the user",
    "chat not found",
    "user is deactivated",
    "bot can't initiate conversation with a user",
    "forbidden",
)


def _extract_description(response: requests.Response) -> str:
    try:
        payload: Any = response.json()
        description = str(payload.get("description") or "").strip()
        if description:
            return description
    except Exception:
        pass
    return str(response.text or "").strip()


def _is_ignorable_error(status_code: int, description: str) -> bool:
    text = (description or "").strip().lower()
    if status_code in {401, 403}:
        return True
    return any(token in text for token in _IGNORABLE_ERROR_TOKENS)


def send_scheduler_notification(chat_id: int, text: str, *, parse_mode: str = "HTML", timeout: int = 15) -> bool:
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
    data = {
        "chat_id": chat_id,
        "text": text,
        "parse_mode": parse_mode,
    }

    try:
        response = requests.post(url, data=data, timeout=timeout)
    except Exception as exc:
        print(f"[!] scheduler notify network error chat_id={chat_id}: {exc}")
        return False

    if response.ok:
        return True

    description = _extract_description(response)
    if _is_ignorable_error(response.status_code, description):
        print(
            f"[i] scheduler notify skipped chat_id={chat_id}, "
            f"status={response.status_code}, reason={description or '-'}"
        )
        return False

    print(
        f"[!] scheduler notify failed chat_id={chat_id}, "
        f"status={response.status_code}, reason={description or '-'}"
    )
    return False
