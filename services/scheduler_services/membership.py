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
"""

async def check_and_update_membership(user_id: int):
    membership_status = 'not_member'
    try:
        print("Before await", user_id)

        member = await asyncio.wait_for(
            bot.get_chat_member(CHANNEL_ID, user_id),
            timeout=10
        )

        print("After await", user_id)

        if member.status in VALID_STATUSES:
            membership_status = 'member'

    except asyncio.TimeoutError:
        print(f"Timeout user {user_id}")

    except TelegramBadRequest as e:
        print(f"BadRequest {user_id}: {e}")

    except Exception as e:
        print(f"Unexpected {user_id}: {e}")

    with sqlite3.connect(DB_PATH) as conn:
        conn.execute(
            "UPDATE users SET membership_status = ? WHERE id = ?",
            (membership_status, user_id)
        )
"""

async def check_membership():
    with sqlite3.connect(DB_PATH) as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT id FROM users")
        user_ids = cursor.fetchall()
    for (user_id,) in user_ids:
        try:
            await check_and_update_membership(user_id)
            await asyncio.sleep(0.05)  # ضد flood
        except Exception as e:
            print(e)



