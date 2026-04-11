from aiogram import Router, types
from typing import Optional

from config import ADMINS
from keyboards.main_menu import admin_main_menu_keyboard, user_main_menu_keyboard
from services.db import get_user_services, update_last_name

router = Router()


def format_datetime(value: Optional[str]) -> str:
    if not value:
        return "-"
    return str(value).replace("T", " ")


def format_gb(value: float) -> str:
    if abs(value - int(value)) < 0.01:
        return str(int(value))
    return f"{value:.2f}".rstrip("0").rstrip(".")


def build_volume_section(service: dict) -> str:
    is_unlimited = int(service.get("is_unlimited") or 0) == 1
    if is_unlimited:
        return (
            "📊 <b>مصرف:</b> نامحدود\n"
            "📦 <b>حجم پایه:</b> نامحدود\n"
            "➕ <b>حجم اضافه خریداری‌شده:</b> -\n"
            "🧮 <b>مجموع حجم:</b> نامحدود\n"
            "📉 <b>حجم باقی‌مانده:</b> نامحدود"
        )

    usage_mb = int(service.get("usage_total_mb") or 0)
    usage_gb = max(usage_mb / 1024, 0)
    base_volume_gb = float(service.get("volume_gb") or 0)
    extra_volume_gb = float(service.get("extra_volume_gb") or 0)
    total_volume_gb = base_volume_gb + extra_volume_gb
    remaining_volume_gb = max(total_volume_gb - usage_gb, 0)

    return (
        f"📊 <b>مصرف:</b> {format_gb(usage_gb)} گیگ\n"
        f"📦 <b>حجم پایه:</b> {format_gb(base_volume_gb)} گیگ\n"
        f"➕ <b>حجم اضافه خریداری‌شده:</b> {format_gb(extra_volume_gb)} گیگ\n"
        f"🧮 <b>مجموع حجم:</b> {format_gb(total_volume_gb)} گیگ\n"
        f"📉 <b>حجم باقی‌مانده:</b> {format_gb(remaining_volume_gb)} گیگ"
    )


@router.message(lambda msg: msg.text == "📦 سرویس‌های من")
async def my_services_handler(message: types.Message):
    user_id = message.from_user.id
    services = get_user_services(user_id)
    last_name = message.from_user.last_name
    if last_name:
        update_last_name(user_id=user_id, last_name=last_name)

    role = "admin" if user_id in ADMINS else "user"
    keyboard = admin_main_menu_keyboard() if role == "admin" else user_main_menu_keyboard()

    if not services:
        await message.answer("📭 شما هنوز هیچ سرویسی خریداری نکرده‌اید.", reply_markup=keyboard)
        return

    status_map = {
        "active": "✅ فعال",
        "waiting_for_renewal": "✅ فعال",
        "waiting_for_renewal_not_paid": "⏳ تمدید در انتظار پرداخت",
        "reserved": "🎟 ذخیره",
        "waiting_for_payment": "🎟 در انتظار پرداخت",
        "expired": "⛔️ منقضی",
        "renewed": "⛔️ منقضی",
        "canceled": "❌ لغوشده",
    }

    for service in services:
        username = service.get("username") or "-"
        password = service.get("password") or "-"
        plan_name = service.get("plan_name") or "-"
        starts_at = format_datetime(service.get("starts_at"))
        expires_at = format_datetime(service.get("expires_at"))
        usage_last_update = format_datetime(service.get("usage_last_update"))
        status_value = service.get("status")
        status_fa = status_map.get(status_value, status_value or "-")

        text = (
            f"📦 <b>پلن:</b> {plan_name}\n\n"
            f"📄 <b>نام کاربری:</b> <code>{username}</code>\n"
            f"🔑 <b>رمز عبور:</b> <code>{password}</code>\n\n"
            f"📅 <b>شروع:</b> {starts_at}\n"
            f"📆 <b>انقضا:</b> {expires_at}\n"
            f"🕒 <b>آخرین آپدیت مصرف:</b> {usage_last_update}\n\n"
            f"{build_volume_section(service)}\n\n"
            f"📍 <b>وضعیت:</b> {status_fa}"
        )

        await message.answer(text, parse_mode="HTML", reply_markup=keyboard)
