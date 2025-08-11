import asyncio
from aiogram import Router, F
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import StatesGroup, State
from aiogram.types import Message, ReplyKeyboardMarkup, KeyboardButton

from config import ADMINS
from keyboards.user_main_menu import user_main_menu_keyboard
from services.IBSng import change_group
from services.db import (
    ensure_user_exists,
    add_user,
    get_all_plans,
    insert_order,
    get_user_balance,
    find_free_account,
    update_user_balance,
    assign_account_to_order,
)
from handlers.user.payment import show_payment_info

router = Router()


# ---------------- FSM States ---------------- #
class BuyServiceStates(StatesGroup):
    choosing_plan = State()
    confirming = State()


# ---------------- Keyboards ---------------- #
def back_markup():
    return ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text="بازگشت به منوی اصلی")]],
        resize_keyboard=True
    )


def confirm_keyboard():
    return ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text="✅ بله"), KeyboardButton(text="❌ خیر")]],
        resize_keyboard=True,
        one_time_keyboard=True
    )


# ---------------- Step 0: Entry ---------------- #
@router.message(F.text == "🛒 خرید سرویس")
async def start_buy(message: Message, state: FSMContext):
    user_id = message.from_user.id
    first_name = message.from_user.first_name
    username = message.from_user.username
    role = "admin" if user_id in ADMINS else "user"

    # ایجاد کاربر در دیتابیس در صورت عدم وجود
    if not ensure_user_exists(user_id=user_id):
        add_user(user_id, first_name, username, role)

    plans = get_all_plans()
    buttons = [[KeyboardButton(text=f"{plan['name']} - {plan['price']} تومان")]for plan in plans]
    buttons.append([KeyboardButton(text="بازگشت به منوی اصلی")])

    await message.answer(
        "لطفا یک پلن انتخاب کنید:",
        reply_markup=ReplyKeyboardMarkup(keyboard=buttons, resize_keyboard=True)
    )
    await state.set_state(BuyServiceStates.choosing_plan)
    asyncio.create_task(_timeout_cancel(state, message.chat.id))


# ---------------- Step 1: Choose Plan ---------------- #
@router.message(BuyServiceStates.choosing_plan)
async def choose_plan(message: Message, state: FSMContext):
    if message.text == "بازگشت به منوی اصلی":
        await state.clear()
        return await message.answer("بازگشت به منوی اصلی", reply_markup=user_main_menu_keyboard())

    plans = get_all_plans()
    selected_plan = next((p for p in plans if message.text.startswith(f"{p['name']} -")), None)

    if not selected_plan:
        return await message.answer("پلن معتبر نیست، لطفا دوباره انتخاب کنید.")

    plan_name = selected_plan['name']
    plan_price = selected_plan['price']

    user_id = message.from_user.id
    user_balance = get_user_balance(user_id)

    if user_balance < plan_price:
        await state.clear()
        await message.answer(
            f"❌ موجودی حساب شما کافی نیست.\n"
            f"💰 قیمت پلن: {plan_price:,} تومان\n"
            f"💳 موجودی شما: {user_balance:,} تومان\n"
            "در حال انتقال به بخش شارژ حساب..."
        )
        return await show_payment_info(message, state)

    await state.update_data(plan=selected_plan)
    await state.set_state(BuyServiceStates.confirming)
    await message.answer(
        f"شما در حال خریداری سرویس {plan_name} به مبلغ {plan_price} می‌باشید. آیا مطمئن هستید؟",
        reply_markup=confirm_keyboard()
    )


# ---------------- Step 2: Confirm & Process ---------------- #
@router.message(BuyServiceStates.confirming)
async def confirm_and_create(message: Message, state: FSMContext):
    if message.text.strip() == "❌ خیر":
        await state.clear()
        return await message.answer("خرید لغو شد ✅", reply_markup=user_main_menu_keyboard())

    if message.text.strip() != "✅ بله":
        return await message.answer("لطفاً فقط از دکمه‌های «✅ بله» یا «❌ خیر» استفاده کنید.")

    data = await state.get_data()
    plan = data.get("plan")
    if not plan:
        await state.clear()
        return await message.answer("خطا در دریافت اطلاعات پلن. لطفاً دوباره تلاش کنید.")

    plan_id = plan['id']
    plan_name = plan['name']
    plan_duration = plan['duration_months']  # یا اگر روز میخوای plan['duration_days']
    plan_price = plan['price']
    user_id = message.from_user.id

    # پیدا کردن اکانت آزاد
    free_account = find_free_account()
    if not free_account:
        await state.clear()
        return await message.answer("متأسفانه در حال حاضر اکانت آزادی موجود نیست ❌",
                                    reply_markup=user_main_menu_keyboard())

    account_id, account_username, account_password = free_account

    try:
        # ثبت سفارش و اتصال اکانت
        order_id = insert_order(user_id=user_id, plan_id=plan_id, username=account_username, price=plan_price,
                                status="active")
        assign_account_to_order(account_id, order_id, plan_id, "active")
    except Exception as e:
        print(f"خطا در درج سفارش: {e}")
        await state.clear()
        return await message.answer("❌ خطایی در ثبت سفارش رخ داد. لطفاً دوباره تلاش کنید.")

    # تغییر گروه در IBSng
    change_group(account_username, f"{plan_duration}-Month")

    # کم کردن موجودی
    user_balance = get_user_balance(user_id)
    new_balance = user_balance - plan_price
    update_user_balance(user_id, new_balance)

    # پیام موفقیت به کاربر
    await message.answer(
        f"✅ سرویس شما با موفقیت فعال شد!\n\n"
        f"🔸 پلن: {plan_name}\n"
        f"👤 نام کاربری: `{account_username}`\n"
        f"🔐 رمز عبور: `{account_password}`\n"
        f"💰 موجودی: {new_balance} تومان",
        parse_mode="Markdown"
    )
    await message.answer("از خرید شما متشکریم 💚", reply_markup=user_main_menu_keyboard())

    # پیام به ادمین‌ها
    admin_message = (
        f"📢 کاربر {message.from_user.full_name} (ID: {user_id})\n"
        f"یک سرویس خریداری کرد:\n\n"
        f"🔸 پلن: {plan_name}\n"
        f"👤 نام کاربری: `{account_username}`\n"
        f"💰 مبلغ: {plan_price:,} تومان"
    )
    for admin_id in ADMINS:
        try:
            await message.bot.send_message(admin_id, admin_message, parse_mode="Markdown")
        except Exception as e:
            print(f"خطا در ارسال پیام به ادمین {admin_id}: {e}")

    await state.clear()


# ---------------- Timeout Helper ---------------- #
async def _timeout_cancel(state: FSMContext, chat_id: int):
    await asyncio.sleep(120)
    if await state.get_state() in [
        BuyServiceStates.choosing_plan,
        BuyServiceStates.confirming
    ]:
        await state.clear()
        from aiogram import Bot
        from config import BOT_TOKEN
        bot = Bot(token=BOT_TOKEN)
        await bot.send_message(chat_id, "زمان شما برای خرید سرویس به پایان رسید.",
                               reply_markup=user_main_menu_keyboard())
