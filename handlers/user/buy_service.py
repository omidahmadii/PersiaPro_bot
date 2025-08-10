import asyncio

from aiogram import Router, F
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import StatesGroup, State
from aiogram.types import Message, ReplyKeyboardMarkup, KeyboardButton

from config import ADMINS
from keyboards.user_main_menu import user_main_menu_keyboard
from services.IBSng import change_group
from services.db import assign_account_to_order, ensure_user_exists, add_user
from services.db import get_all_plans, insert_order, get_user_balance, \
    find_free_account
from services.db import update_user_balance
from handlers.user.payment import show_payment_info
router = Router()


# تعریف حالات FSM برای خرید سرویس
class BuyServiceStates(StatesGroup):
    choosing_plan = State()
    choosing_server = State()
    confirming = State()


# کلید بازگشت
def back_markup():
    return ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text="بازگشت به منوی اصلی")]],
        resize_keyboard=True
    )


def confirm_keyboard():
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="✅ بله"), KeyboardButton(text="❌ خیر")]
        ],
        resize_keyboard=True,
        one_time_keyboard=True
    )


# شروع عملیات خرید
@router.message(F.text == "🛒 خرید سرویس")
async def start_buy(message: Message, state: FSMContext):
    user_id = message.from_user.id
    first_name = message.from_user.first_name
    username = message.from_user.username
    role = "admin" if user_id in ADMINS else "user"
    exists = ensure_user_exists(user_id=user_id)
    # اگر وجود نداشت، اضافه کن
    if not exists:
        add_user(user_id, first_name, username, role)

    plans = get_all_plans()
    buttons = [[KeyboardButton(text=f"{name} - {price} تومان")] for _, name, *_, price in plans]
    buttons.append([KeyboardButton(text="بازگشت به منوی اصلی")])
    keyboard = ReplyKeyboardMarkup(keyboard=buttons, resize_keyboard=True)

    await message.answer("لطفا یک پلن انتخاب کنید:", reply_markup=keyboard)
    await state.set_state(BuyServiceStates.choosing_plan)
    asyncio.create_task(_timeout_cancel(state, message.chat.id))


# انتخاب پلن
@router.message(BuyServiceStates.choosing_plan)
async def choose_plan(message: Message, state: FSMContext):
    text = message.text
    if text == "بازگشت به منوی اصلی":
        await state.clear()
        return await message.answer("بازگشت به منوی اصلی", reply_markup=user_main_menu_keyboard())

    plans = get_all_plans()
    selected = next((p for p in plans if p[1] in text), None)  # فرض بر اینکه p[1] عنوان پلن است

    if not selected:
        return await message.answer("پلن معتبر نیست، لطفا دوباره انتخاب کنید.")
    plan_name = selected[1]
    plan_price = selected[5]
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

    # اگر موجودی کافی بود، ادامه پردازش
    await state.update_data(plan=selected)
    text = f"شما در حال خریداری سرویس {plan_name} به مبلغ {plan_price} می باشید. آیا از خرید این سرویس مطمئن هستید؟ "
    await message.answer(text, reply_markup=confirm_keyboard())
    await state.set_state(BuyServiceStates.confirming)


@router.message(BuyServiceStates.confirming)
async def confirm_and_create(message: Message, state: FSMContext):
    text = message.text.strip()
    user_id = message.from_user.id

    if text == "❌ خیر":
        await state.clear()
        await message.answer("خرید لغو شد ✅", reply_markup=user_main_menu_keyboard())
        return

    if text != "✅ بله":
        await message.answer("لطفاً فقط از دکمه‌های «✅ بله» یا «❌ خیر» استفاده کنید.")
        return

    # دریافت اطلاعات انتخاب‌شده
    data = await state.get_data()
    plan = data.get("plan")
    if not plan:
        await message.answer("خطا در دریافت اطلاعات پلن. لطفاً دوباره تلاش کنید.")
        await state.clear()
        return

    plan_id = plan[0]
    plan_name = plan[1]
    plan_duration = plan[4]  # فرض: مدت زمان سرویس به روز
    plan_price = plan[5]

    # بررسی اکانت آزاد
    free_account = find_free_account()
    if not free_account:
        await message.answer("متأسفانه در حال حاضر اکانت آزادی موجود نیست ❌", reply_markup=user_main_menu_keyboard())
        await state.clear()
        return

    account_id, username, password = free_account[0], free_account[1], free_account[2]

    try:
        # درج سفارش
        order_id = insert_order(user_id=user_id, plan_id=plan_id, username=username, price=plan_price, status="active")
        # اتصال اکانت به سفارش و فعال‌سازی
        assign_account_to_order(account_id, order_id, plan_id, "active")

    except Exception as e:
        print(f"خطا در درح سفارش: {e}")

    group_name = f"{plan_duration}-Month"
    change_group(username, group_name)

    user_balance = get_user_balance(user_id)
    new_balance = user_balance - plan_price
    update_user_balance(user_id, new_balance)

    await message.answer(
        f"✅ سرویس شما با موفقیت فعال شد!\n\n"
        f"🔸 پلن: {plan_name}\n"
        f"👤 نام کاربری: `{username}`\n"
        f"🔐 رمز عبور: `{password}`\n"
        f"💰 موجودی: {new_balance} تومان\n"
    )
    # کم کردن موجودی
    await message.answer("از خرید شما متشکریم 💚", reply_markup=user_main_menu_keyboard())

    admin_message = (
        f"📢 کاربر {message.from_user.full_name} (ID: {message.from_user.id})\n"
        f"یک سرویس خریداری کرد:\n\n"
        f"🔸 پلن: {plan_name}\n"
        f"👤 نام کاربری: `{username}`\n"
        f"💰 مبلغ: {plan_price:,} تومان"
    )

    for admin_id in ADMINS:
        try:
            await message.bot.send_message(admin_id, admin_message, parse_mode="Markdown")
        except Exception as e:
            print(f"خطا در ارسال پیام به ادمین {admin_id}: {e}")

    await state.clear()


async def _timeout_cancel(state: FSMContext, chat_id: int):
    await asyncio.sleep(120)
    if await state.get_state() in [
        BuyServiceStates.choosing_plan,
        BuyServiceStates.choosing_server,
        BuyServiceStates.confirming
    ]:
        await state.clear()
        from aiogram import Bot
        from config import BOT_TOKEN
        bot = Bot(token=BOT_TOKEN)
        await bot.send_message(chat_id, "زمان شما برای خرید سرویس به پایان رسید.",
                               reply_markup=user_main_menu_keyboard())


def register_buy_service(dp):
    dp.include_router(router)
