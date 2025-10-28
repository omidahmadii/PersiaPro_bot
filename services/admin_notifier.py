# services/admin_notifier.py
from aiogram import Bot
from config import BOT_TOKEN, ADMINS  # اطمینان حاصل کن ADMIN_IDS در config لیست آیدی ادمین‌هاست


async def send_message_to_admins(text: str):
    bot = Bot(token=BOT_TOKEN)
    try:
        for admin_id in ADMINS:
            try:
                await bot.send_message(admin_id, text)
            except Exception:
                # نذار یک ادمین خراب، کل حلقه رو بترکونه
                pass
    finally:
        # بستن سشن برای تمیزی
        await bot.session.close()
