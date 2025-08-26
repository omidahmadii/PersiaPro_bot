import asyncio
from pathlib import Path

from aiogram import Router, F, Bot
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import Message
from services.db import get_active_cards

from config import ADMINS
from keyboards.payment import payment_keyboard
from keyboards.user_main_menu import user_main_menu_keyboard
from services.db import insert_transaction, get_all_photo_hashes, ensure_user_exists, add_user
import hashlib


router = Router()


class PaymentStates(StatesGroup):
    waiting_for_receipt = State()


def calculate_photo_hash(file_path: str) -> str:
    with open(file_path, "rb") as f:
        return hashlib.sha256(f.read()).hexdigest()


@router.message(F.photo)
async def catch_any_photo_as_receipt(message: Message, state: FSMContext, bot: Bot):
    # اگر کاربر داخل استیت خاصی است (مثل PaymentStates.waiting_for_receipt) نذار این هندلر دخالت کنه
    if await state.get_state():
        return
    user_id = message.from_user.id
    first_name = message.from_user.first_name
    username = message.from_user.username
    role = "admin" if user_id in ADMINS else "user"
    exists = ensure_user_exists(user_id=user_id)
    # اگر وجود نداشت، اضافه کن
    if not exists:
        add_user(user_id, first_name, username, role)
    photo = message.photo[-1]
    file_id = photo.file_id
    user_id = message.from_user.id

    # ذخیره فایل محلی (اختیاری)
    photo_path = f"transactions/{user_id}-{file_id}.jpg"
    Path("transactions").mkdir(exist_ok=True)
    file = await bot.get_file(file_id)
    # insert_transaction(user_id=user_id, photo_id=file_id, photo_path=photo_path)
    await bot.download_file(file.file_path, destination=photo_path)
    photo_hash = calculate_photo_hash(photo_path)

    # چک تکراری بودن
    existing_hashes = get_all_photo_hashes()
    if photo_hash in existing_hashes:
        Path(photo_path).unlink(missing_ok=True)  # حذف فایل تکراری

        return await message.answer("❌ این فیش قبلاً ثبت شده است. لطفاً منتظر تایید ادمین بمانید.",
                                    reply_markup=user_main_menu_keyboard())

    # درج در دیتابیس
    insert_transaction(
        user_id=user_id,
        photo_id=file_id,
        photo_path=photo_path,
        photo_hash=photo_hash
    )

    await message.answer("✅ فیش شما با موفقیت ثبت شد. منتظر تایید ادمین بمانید.",
                         reply_markup=user_main_menu_keyboard())
    await state.clear()

    for admin_id in ADMINS:
        await bot.send_photo(
            chat_id=admin_id,
            photo=file_id,
            caption=(
                f"📥 کاربر <a href='tg://user?id={user_id}'>{user_id}</a> فیش پرداخت ارسال کرد.\n"
                f"نام: {message.from_user.first_name or 'ناموجود'}\n"
                f"نام خانوادگی: {message.from_user.last_name or 'ناموجود'}\n"
                f"یوزرنیم: @{message.from_user.username or 'ندارد'}"
            ),
            parse_mode="HTML"
        )
    return None

