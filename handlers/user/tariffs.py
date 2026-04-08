from html import escape
from typing import Dict, List, Optional

from aiogram import Router
from aiogram.types import Message

from config import ADMINS
from keyboards.main_menu import main_menu_keyboard_for_user
from services.db import add_user, ensure_user_exists, get_buy_plans, update_last_name

router = Router()

CATEGORY_PRIORITY = [
    "special_access",
    "standard",
    "dual",
    "fixed_ip",
    "custom_location",
    "modem",
]


def _normalize_text(value: Optional[str]) -> str:
    if not value:
        return ""
    return " ".join(value.replace("\u200c", " ").strip().split())


def _is_tariff_button_text(value: Optional[str]) -> bool:
    normalized = _normalize_text(value)
    return normalized in {"💷 تعرفه ها", "💷 تعرفه‌ها"}


def _normalize_category(category: Optional[str]) -> str:
    normalized = (category or "").strip().lower()
    return normalized if normalized else "standard"


def _category_label(category: Optional[str]) -> str:
    mapping = {
        "standard": "✨ معمولی",
        "dual": "👥 دوکاربره",
        "fixed_ip": "📌 آی‌پی ثابت",
        "custom_location": "📍 لوکیشن دلخواه",
        "modem": "📶 مودم/روتر",
        "special_access": "⚡ دسترسی ویژه",
    }
    return mapping.get(_normalize_category(category), "❓ سایر")


def _location_label(location: Optional[str]) -> str:
    mapping = {
        "france": "🇫🇷 فرانسه",
        "turkey": "🇹🇷 ترکیه",
        "iran": "🇮🇷 ایران",
        "england": "🇬🇧 انگلیس",
        "global": "🌐 گلوبال",
    }
    key = (location or "").strip().lower()
    if not key:
        return ""
    return mapping.get(key, key)


def _format_price(amount: int) -> str:
    try:
        return f"{int(amount):,}"
    except Exception:
        return str(amount)


def _format_duration(plan: Dict) -> str:
    try:
        days = int(plan.get("duration_days") or 0)
    except Exception:
        days = 0

    if days > 0:
        return f"{days} روز"

    try:
        months = int(plan.get("duration_months") or 0)
    except Exception:
        months = 0

    if months > 0:
        return f"{months} ماه"

    return "مدت نامشخص"


def _format_volume(plan: Dict) -> str:
    try:
        if int(plan.get("is_unlimited") or 0) == 1:
            return "نامحدود"
    except Exception:
        pass

    volume = plan.get("volume_gb")
    if volume not in (None, ""):
        return f"{volume} گیگ"

    return "حجم نامشخص"


def _sorted_categories(categories: List[str]) -> List[str]:
    rank = {name: idx for idx, name in enumerate(CATEGORY_PRIORITY)}
    return sorted(categories, key=lambda item: rank.get(item, 10_000))


def _build_tariffs_text(plans: List[Dict]) -> str:
    if not plans:
        return (
            "💷 <b>تعرفه‌های من</b>\n\n"
            "در حال حاضر پلن فعالی برای نمایش به شما وجود ندارد."
        )

    grouped: Dict[str, List[Dict]] = {}
    for plan in plans:
        grouped.setdefault(_normalize_category(plan.get("category")), []).append(plan)

    lines = [
        "💷 <b>تعرفه‌های من</b>",
        "پلن‌های زیر بر اساس سطح دسترسی و شرایط فعال برای شما نمایش داده شده‌اند.",
        "",
    ]

    for category in _sorted_categories(list(grouped.keys())):
        lines.append(f"<b>{escape(_category_label(category))}</b>")
        for plan in grouped[category]:
            plan_name = escape(str(plan.get("name") or "پلن بدون نام"))
            duration = _format_duration(plan)
            volume = _format_volume(plan)
            price = _format_price(plan.get("price", 0))
            location = _location_label(plan.get("location"))
            location_part = f" | {escape(location)}" if location else ""
            lines.append(f"• {plan_name} | {escape(duration)} | {escape(volume)}{location_part} | <b>{price} تومان</b>")
        lines.append("")

    return "\n".join(lines).strip()


@router.message(lambda msg: _is_tariff_button_text(msg.text))
async def tariffs_handler(message: Message):
    user_id = message.from_user.id
    first_name = message.from_user.first_name
    username = message.from_user.username
    last_name = message.from_user.last_name

    role = "admin" if str(user_id) in {str(admin_id) for admin_id in ADMINS} else "user"

    if not ensure_user_exists(user_id=user_id):
        add_user(user_id, first_name, username, role)

    if last_name:
        update_last_name(user_id=user_id, last_name=last_name)

    plans = get_buy_plans(user_id=user_id)
    text = _build_tariffs_text(plans)

    await message.answer(
        text=text,
        parse_mode="HTML",
        reply_markup=main_menu_keyboard_for_user(user_id),
    )
