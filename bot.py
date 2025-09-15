import asyncio
import logging
import sys

from aiogram import Dispatcher

from handlers.admin import verify_transactions, temporary_charge, cards_managment, user_managment, plan_managment, \
    reports
from handlers.shared import change_password
from handlers.user import placeholder, feedback, get_cards
from handlers.user import start, buy_service, my_services, account, tutorial, contact_support, payment, renew_service, \
    FAQ
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
        verify_transactions.router,
        buy_service.router,
        contact_support.router,
        tutorial.router,
        my_services.router,
        renew_service.router,
        feedback.router,
        get_cards.router,
        temporary_charge.router,
        cards_managment.router,
        user_managment.router,
        plan_managment.router,
        reports.router,


        change_password.router,
        FAQ.router,
        placeholder.router,
    )

    # ایجاد جداول دیتابیس
    create_tables()

    # اجرای تسک زمان‌بندی‌شده
    asyncio.create_task(scheduler())
    # asyncio.create_task(notifier())

    # اجرای ربات
    await dp.start_polling(bot)


if __name__ == "__main__":
    asyncio.run(main())
