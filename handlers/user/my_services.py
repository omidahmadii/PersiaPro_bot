from aiogram import Router, types

from keyboards.main_menu import user_main_menu_keyboard, admin_main_menu_keyboard

from services.db import get_user_services, get_order_usage, update_last_name
from config import ADMINS

router = Router()


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
        text = "📭 شما هنوز هیچ سرویسی خریداری نکرده‌اید."
        await message.answer(text, reply_markup=keyboard)
        return

    for service in services:
        order_id, username, password, plan_name, starts_at, expires_at, status, created_at = service

        if not starts_at:
            starts_at = ""
        if not expires_at:
            expires_at = ""

        usage_mb = get_order_usage(order_id)
        usage_gb = round(usage_mb / 1024, 2)
        status_map = {
            "active": "✅ فعال",
            "waiting_for_renewal": "✅ فعال",
            "waiting_for_renewal_not_paid": "⏳ تمدید در انتظار پرداخت",
            "reserved": "🎟 ذخیره",
            "waiting_for_payment": "🎟 در انتظار پرداخت",
            "expired": "⛔️ منقضی",
            "renewed": "⛔️ منقضی",
        }

        # مقدار پیش‌فرض اگر کلید پیدا نشود
        status_fa = status_map.get(status)

        text = (
            f"📦 <b>پلن:</b> {plan_name}\n"
            f"\n"
            f"📄 <b>نام کاربری:</b> <code>{username}</code>\n"
            f"🔑 <b>رمز عبور:</b> <code>{password}</code>\n"
            f"\n"
            f"📅 <b>شروع:</b> {starts_at}\n"
            f"📆 <b>انقضا:</b> {expires_at}\n"
            f"\n"
            f"📊 <b>مصرف:</b> {usage_gb} گیگ\n"
            f"\n"
            f"📍 <b>وضعیت:</b> {status_fa}\n"
        )

        await message.answer(text, parse_mode="HTML", reply_markup=keyboard)
