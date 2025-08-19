import asyncio
from aiogram import Router, F
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import StatesGroup, State
from aiogram.types import Message, CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup

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
    choosing_category = State()
    choosing_location = State()
    choosing_duration = State()
    confirming = State()

# ---------------- Keyboards ---------------- #
def keyboard_categories():
    rows = [
        [InlineKeyboardButton(text="استاندارد", callback_data="buy|category|standard")],
        [InlineKeyboardButton(text="دوکاربره", callback_data="buy|category|dual")],
        [InlineKeyboardButton(text="آی‌پی ثابت", callback_data="buy|category|fixed_ip")],
        [InlineKeyboardButton(text="لوکیشن دلخواه قابل تغییر", callback_data="buy|category|custom_location")],
    ]
    return InlineKeyboardMarkup(inline_keyboard=rows)

def keyboard_locations():
    rows = [
        [InlineKeyboardButton(text="🇫🇷 فرانسه", callback_data="buy|location|france")],
        [InlineKeyboardButton(text="🇹🇷 ترکیه", callback_data="buy|location|turkey")],
        [InlineKeyboardButton(text="🇮🇷 ایران", callback_data="buy|location|iran")],
        [InlineKeyboardButton(text="🇬🇧 انگلیس", callback_data="buy|location|england")],
        [InlineKeyboardButton(text="⬅️ بازگشت", callback_data="buy|back|category")],
    ]
    return InlineKeyboardMarkup(inline_keyboard=rows)

def keyboard_durations(plans, back_to="category"):
    rows = []
    for plan in plans:
        rows.append([InlineKeyboardButton(
            text=f"{plan['name']} - {plan['price']} تومان",
            callback_data=f"buy|duration|{plan['id']}"
        )])
    rows.append([InlineKeyboardButton(text="⬅️ بازگشت", callback_data=f"buy|back|{back_to}")])
    return InlineKeyboardMarkup(inline_keyboard=rows)

def keyboard_confirm():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✅ تایید و پرداخت", callback_data="buy|confirm")],
        [InlineKeyboardButton(text="⬅️ بازگشت", callback_data="buy|back|duration")]
    ])

# ---------------- Step 0: Entry ---------------- #
@router.message(F.text == "🛒 خرید سرویس")
async def start_buy(message: Message, state: FSMContext):
    user_id = message.from_user.id
    first_name = message.from_user.first_name
    username = message.from_user.username
    role = "admin" if user_id in ADMINS else "user"

    if not ensure_user_exists(user_id=user_id):
        add_user(user_id, first_name, username, role)

    await state.set_state(BuyServiceStates.choosing_category)
    await message.answer("لطفاً نوع سرویس مورد نظر خود را انتخاب کنید:", reply_markup=keyboard_categories())

# ---------------- Step 1: Choose Category ---------------- #
@router.callback_query(F.data.startswith("buy|category"))
async def choose_category(callback: CallbackQuery, state: FSMContext):
    _, _, category = callback.data.split("|")
    await state.update_data(category=category)

    plans = [p for p in get_all_plans() if p["category"] == category]

    if category in ("standard", "dual"):
        await state.set_state(BuyServiceStates.choosing_duration)
        await callback.message.edit_text("مدت زمان سرویس را انتخاب کنید:", reply_markup=keyboard_durations(plans))
    elif category in ("fixed_ip", "custom_location"):
        await state.set_state(BuyServiceStates.choosing_location)
        await callback.message.edit_text("ابتدا لوکیشن را انتخاب کنید:", reply_markup=keyboard_locations())

# ---------------- Step 2: Choose Location ---------------- #
@router.callback_query(F.data.startswith("buy|location"))
async def choose_location(callback: CallbackQuery, state: FSMContext):
    _, _, location = callback.data.split("|")
    await state.update_data(location=location)

    plans = [p for p in get_all_plans() if p["location"] == location]
    await state.set_state(BuyServiceStates.choosing_duration)
    await callback.message.edit_text("مدت زمان سرویس را انتخاب کنید:", reply_markup=keyboard_durations(plans, back_to="location"))

# ---------------- Step 3: Choose Duration ---------------- #
@router.callback_query(F.data.startswith("buy|duration"))
async def choose_duration(callback: CallbackQuery, state: FSMContext):
    _, _, plan_id = callback.data.split("|")
    plans = get_all_plans()
    selected_plan = next((p for p in plans if str(p["id"]) == plan_id), None)

    if not selected_plan:
        return await callback.answer("پلن معتبر یافت نشد", show_alert=True)

    await state.update_data(plan=selected_plan)
    await state.set_state(BuyServiceStates.confirming)

    # نمایش خلاصه سفارش
    data = await state.get_data()
    summary = [
        "🧾 پیش‌نمایش سفارش شما:",
        f"🔸 دسته: {data.get('category')}",
        f"🔹 لوکیشن: {data.get('location', 'ندارد')}",
        f"📅 مدت زمان: {selected_plan['name']}",
        f"💰 مبلغ: {selected_plan['price']} تومان"
    ]
    await callback.message.edit_text("\n".join(summary), reply_markup=keyboard_confirm())

# ---------------- Step 4: Confirm ---------------- #
@router.callback_query(F.data == "buy|confirm")
async def confirm_and_create(callback: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    plan = data.get("plan")

    if not plan:
        await state.clear()
        return await callback.message.edit_text("خطا در دریافت اطلاعات پلن. دوباره تلاش کنید.", reply_markup=user_main_menu_keyboard())

    user_id = callback.from_user.id
    user_balance = get_user_balance(user_id)
    if user_balance < plan["price"]:
        await state.clear()
        await callback.message.edit_text(
            f"❌ موجودی کافی نیست.\n💰 قیمت: {plan['price']:,} تومان\n💳 موجودی: {user_balance:,} تومان",
            reply_markup=user_main_menu_keyboard()
        )
        return await show_payment_info(callback.message, state)

    free_account = find_free_account()
    if not free_account:
        await state.clear()
        return await callback.message.edit_text("اکانت آزاد موجود نیست ❌", reply_markup=user_main_menu_keyboard())

    account_id, account_username, account_password = free_account
    try:
        order_id = insert_order(user_id=user_id, plan_id=plan["id"], username=account_username, price=plan["price"], status="active")
        assign_account_to_order(account_id, order_id, plan["id"], "active")
    except Exception as e:
        print(f"خطا در درج سفارش: {e}")
        await state.clear()
        return await callback.message.edit_text("❌ خطایی در ثبت سفارش رخ داد.", reply_markup=user_main_menu_keyboard())

    change_group(username=account_username, group=plan["group_name"])
    new_balance = user_balance - plan["price"]
    update_user_balance(user_id, new_balance)

    await callback.message.edit_text(
        f"✅ سرویس شما فعال شد!\n\n🔸 پلن: {plan['name']}\n👤 نام کاربری: `{account_username}`\n🔐 رمز: `{account_password}`\n💰 موجودی: {new_balance} تومان",
        parse_mode="Markdown",
        reply_markup=user_main_menu_keyboard()
    )

    admin_message = f"📢 کاربر {callback.from_user.full_name} (ID: {user_id})\nپلن: {plan['name']}\nیوزرنیم: `{account_username}`\nمبلغ: {plan['price']:,} تومان"
    for admin_id in ADMINS:
        try:
            await callback.bot.send_message(admin_id, admin_message, parse_mode="Markdown")
        except Exception as e:
            print(f"خطا در ارسال به ادمین {admin_id}: {e}")

    await state.clear()

# ---------------- Back Navigation ---------------- #
@router.callback_query(F.data.startswith("buy|back"))
async def go_back(callback: CallbackQuery, state: FSMContext):
    _, _, target = callback.data.split("|")

    if target == "category":
        await state.set_state(BuyServiceStates.choosing_category)
        await callback.message.edit_text("لطفاً نوع سرویس مورد نظر خود را انتخاب کنید:", reply_markup=keyboard_categories())

    elif target == "location":
        await state.set_state(BuyServiceStates.choosing_location)
        await callback.message.edit_text("ابتدا لوکیشن را انتخاب کنید:", reply_markup=keyboard_locations())

    elif target == "duration":
        data = await state.get_data()
        category = data.get("category")
        location = data.get("location")

        if category in ("standard", "dual"):
            plans = [p for p in get_all_plans() if p["category"] == category]
            await state.set_state(BuyServiceStates.choosing_duration)
            await callback.message.edit_text("مدت زمان سرویس را انتخاب کنید:", reply_markup=keyboard_durations(plans))

        elif category in ("fixed_ip", "custom_location") and location:
            plans = [p for p in get_all_plans() if p["location"] == location]
            await state.set_state(BuyServiceStates.choosing_duration)
            await callback.message.edit_text("مدت زمان سرویس را انتخاب کنید:", reply_markup=keyboard_durations(plans, back_to="location"))
