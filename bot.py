import asyncio
import logging
import sys

from aiogram import Dispatcher

from handlers.admin import verify_transactions, temporary_charge, cards_managment, user_managment, plan_managment, \
    plan_audience, reports, exec_commands, runtime_settings, accounting_transactions, user_messaging, \
    order_management, volume_package_management
from handlers.shared import change_password, activate_stored
from handlers.user import placeholder, feedback, get_cards, other_features, start, buy_service, my_services, account, \
    tutorial, contact_support, payment, renew_service, extra_volume, conversion_offer, \
    FAQ, tariffs, transfer_ownership
from config import APP_ENV, ENABLE_SCHEDULER
from services.bot_menu import setup_bot_menu
from services.bot_instance import bot
from services.db import create_tables
from services.scheduler import scheduler  # همون فایلی که تسک رو نوشتی

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s %(levelname)s %(name)s: %(message)s',
    handlers=[logging.StreamHandler(sys.stdout)]
)


async def main():
    # تعریف بات با مشخصات پیش‌فرض

    dp = Dispatcher()

    dp.include_routers(
        start.router,
        account.router,
        payment.router,
        extra_volume.router,
        conversion_offer.router,
        verify_transactions.router,
        accounting_transactions.router,
        buy_service.router,
        contact_support.router,
        tutorial.router,
        my_services.router,
        renew_service.router,
        feedback.router,
        get_cards.router,
        temporary_charge.router,
        cards_managment.router,
        user_messaging.router,
        user_managment.router,
        plan_managment.router,
        order_management.router,
        volume_package_management.router,
        plan_audience.router,
        reports.router,
        runtime_settings.router,
        activate_stored.router,
        exec_commands.router,
        tariffs.router,
        other_features.router,
        transfer_ownership.router,

        change_password.router,
        FAQ.router,
        placeholder.router,
    )

    # ایجاد جداول دیتابیس
    create_tables()
    await setup_bot_menu(bot)

    # اجرای تسک زمان‌بندی‌شده
    logging.info("Starting bot with APP_ENV=%s, scheduler=%s", APP_ENV, "enabled" if ENABLE_SCHEDULER else "disabled")
    asyncio.create_task(scheduler())
    # asyncio.create_task(notifier())

    # اجرای ربات
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
