import asyncio

from config import (
    APP_ENV,
    ENABLE_SCHEDULER,
    SCHEDULER_ACTIVATE_RESERVED,
    SCHEDULER_ACTIVATE_WAITING_FOR_PAYMENT,
    SCHEDULER_AUTO_RENEW,
    SCHEDULER_CANCEL_NOT_PAID,
    SCHEDULER_CONVERSION_NOTIFIER,
    SCHEDULER_EXPIRE_ORDERS,
    SCHEDULER_LIMIT_SPEED,
    SCHEDULER_MEMBERSHIP,
    SCHEDULER_NOTIFIER,
    SCHEDULER_USAGE_NOTIFIER,
    SCHEDULER_UPDATE_ORDER_TIMES,
    SCHEDULER_USAGE_LOGGER,
)
from services.IBSng import get_user_exp_date, get_user_start_date
from services.scheduler_services.activate_reserved_orders import activate_reserved_orders
from services.scheduler_services.activate_waiting_for_payment_orders import activate_waiting_for_payment_orders
from services.scheduler_services.cancel_not_paid_waiting_for_payment_orders import \
    cancel_not_paid_waiting_for_payment_orders
from services.conversion_offer import send_conversion_offer_notifications
from services.db import expire_old_orders, archive_old_orders
from services.db import get_active_orders_without_time, update_order_starts_at, update_order_expires_at
from services.scheduler_services.limit_speed import limit_speed
from services.scheduler_services.membership import check_membership
from services.scheduler_services.notifier import notifier
from services.scheduler_services.usage_notifier import notify_usage_thresholds
from services.scheduler_services.usage_logger import log_usage
from services.scheduler_services.auto_renew import auto_renew


async def update_orders_time_from_ibs():
    while True:
        print("update times started")
        orders = get_active_orders_without_time()
        for order in orders:
            try:
                username = order['username']
                starts_at = await asyncio.to_thread(get_user_start_date, username)
                expires_at = await asyncio.to_thread(get_user_exp_date, username)

                if starts_at:
                    update_order_starts_at(order['id'], starts_at)
                if expires_at:
                    update_order_expires_at(order['id'], expires_at)

            except Exception as e:
                print(f"خطا در دریافت اطلاعات برای سفارش {order['id']}: {e}")
        print("Update orders time from ibs loop finished.")
        await asyncio.sleep(15 * 60)


async def expire_orders_loop():
    while True:
        await asyncio.sleep(60 * 60)
        try:
            await asyncio.to_thread(expire_old_orders)
            await asyncio.to_thread(archive_old_orders)
        except Exception as e:
            print(f"خطا در expire کردن سفارش‌ها: {e}")
        print("Expire orders loop finished.")


async def activate_reserved_orders_loop():
    while True:
        try:
            await asyncio.to_thread(activate_reserved_orders)
        except Exception as e:
            print(f"خطا در فعال کردن سفارش‌های رزرو شده: {e}")
        print("Activate reserved orders loop finished.")
        await asyncio.sleep(60)


async def notifier_loop():
    while True:
        try:
            await asyncio.to_thread(notifier)
        except Exception as e:
            print(f"خطا در ارسال پیغام: {e}")
        await asyncio.sleep(15 * 60)


async def conversion_notifier_loop():
    while True:
        try:
            await asyncio.to_thread(send_conversion_offer_notifications)
        except Exception as e:
            print(f"Ø®Ø·Ø§ Ø¯Ø± Ø§Ø±Ø³Ø§Ù„ Ù¾ÛŒØ§Ù… Ø·Ø±Ø­ ØªØ¨Ø¯ÛŒÙ„: {e}")
        await asyncio.sleep(15 * 60)


async def log_usage_loop():
    while True:
        try:
            print("Log Usage Loop Starded")
            await asyncio.to_thread(log_usage)
        except Exception as e:
            print(f"خطا در ثبت مصرف کاربر: {e}")
        await asyncio.sleep(1 * 60)


async def usage_notifier_loop():
    while True:
        try:
            await asyncio.to_thread(notify_usage_thresholds)
        except Exception as e:
            print(f"خطا در ارسال هشدار مصرف حجم: {e}")
        await asyncio.sleep(5 * 60)


async def check_membership_loop():
    while True:
        try:
            await check_membership()
            print("Check MemberShip loop Finished.")
        except Exception as e:
            print(f"خطا در ثبت عضویت کاربر: {e}")
        await asyncio.sleep(60 * 60 * 24)


async def limit_speed_loop():
    while True:
        try:
            await asyncio.to_thread(limit_speed)
            print("limit speed loop Finished.")
        except Exception as e:
            print("Error during scheduler:", e)
        await asyncio.sleep(2 * 60)


async def activate_waiting_for_payment_orders_loop():
    while True:
        try:
            await asyncio.to_thread(activate_waiting_for_payment_orders)
        except Exception as e:
            print(f"خطا در فعال کردن سفارش‌های پرداخت نشده: {e}")
        print("Activate Waiting For Payment orders loop finished.")
        await asyncio.sleep(60)


async def cancel_not_paid_waiting_for_payment_orders_loop():
    while True:
        try:
            await asyncio.to_thread(cancel_not_paid_waiting_for_payment_orders)
        except Exception as e:
            print(f"خطا در کنسل کردن سفارش‌های پرداخت نشده: {e}")
        print("Cancel Not Paid Waiting For Payment orders loop finished.")
        await asyncio.sleep(60)


async def auto_renew_loop():
    while True:
        try:
            # pass
            await auto_renew()
        except Exception as e:
            print(f"خطا در اجرای تمدید خودکار: {e}")
        print("َAuto renew loop finished.")
        await asyncio.sleep(60)


async def scheduler():
    if not ENABLE_SCHEDULER:
        print(f"Scheduler disabled for APP_ENV={APP_ENV}.")
        return

    job_configs = [
        ("update_orders_time_from_ibs", SCHEDULER_UPDATE_ORDER_TIMES, update_orders_time_from_ibs),
        ("notifier", SCHEDULER_NOTIFIER, notifier_loop),
        ("conversion_notifier", SCHEDULER_CONVERSION_NOTIFIER, conversion_notifier_loop),
        ("activate_reserved_orders", SCHEDULER_ACTIVATE_RESERVED, activate_reserved_orders_loop),
        ("expire_orders", SCHEDULER_EXPIRE_ORDERS, expire_orders_loop),
        ("usage_logger", SCHEDULER_USAGE_LOGGER, log_usage_loop),
        ("usage_notifier", SCHEDULER_USAGE_NOTIFIER, usage_notifier_loop),
        ("membership", SCHEDULER_MEMBERSHIP, check_membership_loop),
        ("limit_speed", SCHEDULER_LIMIT_SPEED, limit_speed_loop),
        ("activate_waiting_for_payment", SCHEDULER_ACTIVATE_WAITING_FOR_PAYMENT, activate_waiting_for_payment_orders_loop),
        ("cancel_not_paid", SCHEDULER_CANCEL_NOT_PAID, cancel_not_paid_waiting_for_payment_orders_loop),
        ("auto_renew", SCHEDULER_AUTO_RENEW, auto_renew_loop),
    ]

    enabled_jobs = [factory() for _, enabled, factory in job_configs if enabled]
    enabled_names = [name for name, enabled, _ in job_configs if enabled]

    if not enabled_jobs:
        print(f"Scheduler enabled but no jobs selected for APP_ENV={APP_ENV}.")
        return

    print(f"Scheduler started for APP_ENV={APP_ENV} with jobs: {', '.join(enabled_names)}")
    await asyncio.gather(*enabled_jobs)
