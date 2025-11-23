import asyncio
import sqlite3
from aiogram.exceptions import TelegramBadRequest
from config import CHANNEL_ID, DB_PATH
from services.bot_instance import bot


VALID_STATUSES = ['member', 'administrator', 'creator']


async def check_and_update_membership(user_id: int):
    try:

        member = await bot.get_chat_member(CHANNEL_ID, user_id)
        status = member.status

        if status in VALID_STATUSES:
            membership_status = 'member'
        else:
            membership_status = 'not_member'

        # print(f"user_id={user_id} → membership_status: {membership_status}")

    except TelegramBadRequest as e:
        membership_status = 'not_member'
        # print(f"⚠️ TelegramBadRequest for user_id={user_id}: {e}")

    except Exception as e:
        membership_status = 'not_member'
        # print(f"❌ Unexpected error for user_id={user_id}: {e}")

    # Update in database
    with sqlite3.connect(DB_PATH) as conn:
        cursor = conn.cursor()
        cursor.execute("UPDATE users SET membership_status = ? WHERE id = ?", (membership_status, user_id))
        conn.commit()


async def check_membership():
    with sqlite3.connect(DB_PATH) as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT id FROM users")
        user_ids = cursor.fetchall()

    for (user_id,) in user_ids:
        await check_and_update_membership(user_id)


