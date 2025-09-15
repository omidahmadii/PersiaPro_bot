from aiogram import Router, F
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import StatesGroup, State
from aiogram.types import Message

from config import ADMINS
from keyboards.admin_main_menu import admin_main_menu_keyboard
from keyboards.user_main_menu import user_main_menu_keyboard
from services.IBSng import change_password as ibs_change_password
from services.db import get_accounts_id_by_username, update_account_password_by_username

router = Router()


# تعریف حالت‌ها
class ChangePasswordState(StatesGroup):
    waiting_for_username = State()
    waiting_for_new_password = State()


# هندلر شروع فرآیند
@router.message(F.text == "تغییر رمز عبور")
async def change_password(message: Message, state: FSMContext):
    user_id = message.from_user.id
    role = "admin" if user_id in ADMINS else "user"
    if role == "user":
        await message.answer("شما دسترسی لازم برای انجام این عملیات را ندارید.", reply_markup=user_main_menu_keyboard())
        return
    await message.answer("لطفاً نام کاربری موردنظر را وارد کنید.")
    await state.set_state(ChangePasswordState.waiting_for_username)


# مرحله ۲: دریافت نام کاربری و بررسی وجود آن
@router.message(ChangePasswordState.waiting_for_username)
async def receive_username(message: Message, state: FSMContext):
    username = message.text.strip()
    accounts_id = get_accounts_id_by_username(username)
    if not accounts_id:
        user_id = message.from_user.id
        role = "admin" if user_id in ADMINS else "user"
        main_menu_keyboard = admin_main_menu_keyboard() if role == "admin" else user_main_menu_keyboard()
        await message.answer("❌ کاربری با این نام پیدا نشد. لطفاً دوباره تلاش کنید.", reply_markup=main_menu_keyboard)
        return await state.clear()

    # ذخیره username در state
    await state.update_data(username=username)
    await message.answer("✅ نام کاربری پیدا شد. لطفاً رمز عبور جدید را وارد کنید.")
    await state.set_state(ChangePasswordState.waiting_for_new_password)


# مرحله ۳: دریافت رمز جدید و اعمال تغییرات
@router.message(ChangePasswordState.waiting_for_new_password)
async def set_new_password(message: Message, state: FSMContext):
    new_password = message.text.strip()
    data = await state.get_data()
    username = data["username"]
    update_account_password_by_username(username=username, new_password=new_password)

    # بروزرسانی رمز در IBS
    success = await update_password_in_ibs(username, new_password)
    if not success:
        await message.answer("رمز در دیتابیس تغییر کرد ولی هنگام تغییر در IBS خطایی رخ داد.")
        await state.clear()
        return
    user_id = message.from_user.id
    role = "admin" if user_id in ADMINS else "user"
    main_menu_keyboard = admin_main_menu_keyboard() if role == "admin" else user_main_menu_keyboard()
    await message.answer("✅ رمز عبور با موفقیت تغییر یافت.", reply_markup=main_menu_keyboard)
    await state.clear()


# تابع فرضی برای تغییر رمز در IBS
async def update_password_in_ibs(username: str, new_password: str) -> bool:
    try:
        # این قسمت را با کد واقعی IBS جایگزین کن
        # مثلاً: ibs.change_password(username=username, password=new_password)
        ibs_change_password(username=username, password=new_password)
        print(f"تغییر رمز در IBS برای {username} به {new_password}")
        return True
    except Exception as e:
        print("خطا در IBS:", e)
        return False
