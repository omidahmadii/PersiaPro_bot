import datetime
from typing import Union

import jdatetime
import requests

from config import BOT_TOKEN
from services import db, IBSng
from services.IBSng import change_group
from services.admin_notifier import send_message_to_admins
from services.db import get_auto_renew_orders


def format_price(amount: Union[int, float]) -> str:
    try:
        return f"{int(amount):,}"
    except Exception:
        return str(amount)


async def auto_renew():
    orders = get_auto_renew_orders()
    for order in orders:
        user_id = order['user_id']
        plan_id = order['plan_id']
        plan = db.get_plan_info(plan_id)
        plan_price = plan['price']
        user_balance = db.get_user_balance(user_id)

        if user_balance >= plan_price:
            new_balance = user_balance - plan_price
            db.update_user_balance(user_id, new_balance)

            plan_name = plan['name']
            plan_duration_months = plan.get("duration_months")
            plan_volume_gb = plan.get("volume_gb") or 0
            plan_group_name = plan['group_name']
            order_id = order['id']
            order_username = str(order['username'])
            order_auto_renew = order['auto_renew']
            # تشخیص انقضا
            expires_at_greg = jdatetime.datetime.strptime(order["expires_at"],
                                                          "%Y-%m-%d %H:%M").togregorian()
            is_expired = order["status"] == "expired" or expires_at_greg < datetime.datetime.now()
            if is_expired:
                # تمدید فوری
                db.update_order_status(order_id=order_id, new_status="renewed")
                db.insert_renewed_order_with_auto_renew(user_id=user_id, plan_id=plan_id, username=order_username, price=plan_price, status="active",
                                                        is_renewal_of_order=order_id, volume_gb=plan_volume_gb, auto_renew=order_auto_renew)

                IBSng.reset_account_client(username=order_username)
                change_group(username=order_username, group=plan_group_name)

                text_admin = (
                    "🔔 تمدید انجام شد (فعالسازی فوری)\n"
                    f"👤 کاربر: {user_id}\n🆔 یوزرنیم: {order_username}\n📦 پلن: {plan_name}\n"
                    f"⏳ مدت: {plan_duration_months} ماه\n💳 مبلغ: {format_price(plan_price)} تومان\n🟢 وضعیت: فعال شد"
                )
                await send_message_to_admins(text_admin)
                text_user = (
                    f"✅ تمدید با موفقیت انجام شد و سرویس شما فعال گردید.\n\n"
                    f"🔸 پلن: {plan_name}\n"
                    f"👤 نام کاربری: `{order_username}`\n"
                    f"💰 موجودی: {format_price(new_balance)} تومان"
                )
                await _notify_user(user_id=user_id, text=text_user)

            else:
                # اگر هنوز فعال است → رزرو تمدید در انتهای دوره
                db.update_order_status(order_id=order_id, new_status="waiting_for_renewal")
                db.insert_renewed_order_with_auto_renew(user_id, plan_id, order_username, plan_price, "reserved",
                                                        order_id, plan_volume_gb, auto_renew=order_auto_renew)

                text_admin = (
                    "🔔 تمدید رزروی ثبت شد\n"
                    f"👤 کاربر: {user_id}\n🆔 یوزرنیم: {order_username}\n📦 پلن: {plan_name}\n"
                    f"⏳ مدت: {plan_duration_months} ماه\n💳 مبلغ: {format_price(plan_price)} تومان\n🟡 وضعیت: در انتظار اتمام دوره"
                )
                await send_message_to_admins(text_admin)
                text_user = (
                    f"✅ دوست عزیز،\n"
                    f"سرویس شما با نام کاربری <code>{order_username}</code> به صورت خودکار تمدید "
                    f"و پس از پایان دوره‌ی فعلی به‌صورت خودکار فعال می شود.\n\n"
                    f"✨ در صورت بروز هرگونه مشکل با پشتیبانی در تماس باشید."
                )
                await _notify_user(user_id=user_id, text=text_user)


async def _notify_user(user_id: str, text: str) -> None:
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
    data = {
        "chat_id": user_id,
        "text": text,
        "parse_mode": "HTML"
    }

    response = requests.post(url, data=data)
    if not response.ok:
        raise Exception(f"Telegram API error: {response.text}")
