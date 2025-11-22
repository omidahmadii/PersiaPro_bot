import asyncio

from services.IBSng import get_user_exp_date, get_user_start_date
from services.activate_reserved_orders import activate_reserved_orders
from services.activate_waiting_for_payment_orders import activate_waiting_for_payment_orders
from services.cancel_not_paid_waiting_for_payment_orders import cancel_not_paid_waiting_for_payment_orders
from services.auto_renew import auto_renew
from services.db import expire_old_orders, archive_old_orders
from services.db import get_active_orders_without_time, update_order_starts_at, update_order_expires_at
from services.limit_speed import limit_speed
from services.membership import check_membership
from services.notifier import notifier
from services.usage_logger import log_usage


async def update_orders_time_from_ibs():
    while True:
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


async def log_usage_loop():
    while True:
        try:
            await asyncio.to_thread(log_usage)
        except Exception as e:
            print(f"خطا در ثبت مصرف کاربر: {e}")
        await asyncio.sleep(60 * 60)


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

        except Exception as e:
            print("Error during scheduler:", e)
        await asyncio.sleep(60 * 60 * 24)  # هر 24 ساعت


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
            pass
            # await asyncio.to_thread(auto_renew)
        except Exception as e:
            print(f"خطا در اجرای تمدید خودکار: {e}")
        print("َAuto renew loop finished.")
        await asyncio.sleep(60)


async def scheduler():
    await asyncio.gather(
        # update_orders_time_from_ibs(),
        # notifier_loop(),
        # activate_reserved_orders_loop(),
        # expire_orders_loop(),
        # log_usage_loop(),
        # check_membership_loop(),
        # limit_speed_loop(),
        # activate_waiting_for_payment_orders_loop(),
        # cancel_not_paid_waiting_for_payment_orders_loop(),
        # auto_renew_loop()

    )
