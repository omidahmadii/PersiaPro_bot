import asyncio
from aiogram import Router, F
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import StatesGroup, State
from aiogram.types import Message, CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup
from typing import Optional, Union   # بالای فایل

from config import ADMINS
from handlers.user.get_cards import show_cards
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
    get_active_locations_by_category,
)

router = Router()


# ---------------- Helpers ---------------- #
def category_label(category: str) -> str:
    mapping = {
        "standard": "معمولی",
        "dual": "دوکاربره",
        "fixed_ip": "آی‌پی ثابت",
        "custom_location": "لوکیشن دلخواه قابل تغییر",
    }
    return mapping.get(category or "", "نامشخص")


def location_label(location: Optional[str]) -> str:
    mapping = {
        "france": "🇫🇷 فرانسه",
        "turkey": "🇹🇷 ترکیه",
        "iran": "🇮🇷 ایران",
        "england": "🇬🇧 انگلیس",
        "global": "🌐 گلوبال",
        None: "ندارد",
        "": "ندارد",
    }
    return mapping.get(location, location or "ندارد")


def fair_usage_label(plan: dict) -> str:
    # نمایش حجم به‌عنوان آستانه مصرف منصفانه (FUP)
    try:
        if int(plan.get("is_unlimited") or 0) == 1:
            return "نامحدود (مصرف منصفانه)"
    except Exception:
        pass
    vol = plan.get("volume_gb")
    if vol:
        return f"{vol} گیگ"
    return "بدون آستانه مشخص"


def format_price(amount: Union[int, float]) -> str:
    try:
        return f"{int(amount):,}"
    except Exception:
        return str(amount)


async def edit_then_show_main_menu(
    message: Message,
    text: str,
    *,
    parse_mode: Optional[str] = None
):
    # اول متن پیام فعلی ادیت می‌شود (بدون ReplyKeyboard)
    await message.edit_text(text, parse_mode=parse_mode)
    # سپس یک پیام جدید با ReplyKeyboardMarkup ارسال می‌شود
    await message.answer("بازگشت به منوی اصلی", reply_markup=user_main_menu_keyboard())


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
        # [InlineKeyboardButton(text="دوکاربره", callback_data="buy|category|dual")],
        # [InlineKeyboardButton(text="آی‌پی ثابت", callback_data="buy|category|fixed_ip")],
        # [InlineKeyboardButton(text="لوکیشن دلخواه قابل تغییر", callback_data="buy|category|custom_location")],
    ]
    return InlineKeyboardMarkup(inline_keyboard=rows)


def keyboard_locations(locations: list, back_to="category"):
    rows = []
    flags = {
        "france": "🇫🇷 فرانسه",
        "turkey": "🇹🇷 ترکیه",
        "iran": "🇮🇷 ایران",
        "england": "🇬🇧 انگلیس",
    }
    for loc in locations:
        label = flags.get(loc, loc)
        rows.append([InlineKeyboardButton(text=label, callback_data=f"buy|location|{loc}")])
    rows.append([InlineKeyboardButton(text="⬅️ بازگشت", callback_data=f"buy|back|{back_to}")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def keyboard_durations(plans, back_to="category"):
    rows = []
    for plan in plans:
        label = f"{plan['name']} • {fair_usage_label(plan)} • {format_price(plan['price'])} تومان"
        rows.append([InlineKeyboardButton(
            text=label,
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

    # فهرست پلن‌ها براساس دسته
    plans = [p for p in get_all_plans() if p["category"] == category]

    # برای standard و dual و custom_location مستقیم می‌رویم سراغ مدت زمان
    if category in ("standard", "dual", "custom_location"):
        await state.set_state(BuyServiceStates.choosing_duration)
        text = (
            "مدت زمان سرویس را انتخاب کنید:\n"
            "ℹ️ این سرویس‌ها دارای «آستانه مصرف منصفانه» هستند؛ با عبور از آستانه، سرویس قطع نمی‌شود."
        )
        return await callback.message.edit_text(text, reply_markup=keyboard_durations(plans))

    # برای fixed_ip ابتدا لوکیشن‌ها را از دیتابیس می‌خوانیم
    elif category == "fixed_ip":
        available_locations = get_active_locations_by_category(category)
        if not available_locations:
            return await callback.message.edit_text("❌ فعلاً لوکیشنی برای این دسته موجود نیست.")
        await state.set_state(BuyServiceStates.choosing_location)
        return await callback.message.edit_text(
            "ابتدا لوکیشن را انتخاب کنید:",
            reply_markup=keyboard_locations(available_locations)
        )

    else:
        return await callback.message.edit_text("❌ دسته نامعتبر است.")


# ---------------- Step 2: Choose Location ---------------- #
@router.callback_query(F.data.startswith("buy|location"))
async def choose_location(callback: CallbackQuery, state: FSMContext):
    _, _, location = callback.data.split("|")
    await state.update_data(location=location)

    # پلن‌های همان لوکیشن (برای fixed_ip)
    plans = [p for p in get_all_plans() if p.get("location") == location]
    await state.set_state(BuyServiceStates.choosing_duration)
    text = (
        "مدت زمان سرویس را انتخاب کنید:\n"
        "ℹ️ این سرویس‌ها دارای «آستانه مصرف منصفانه» هستند؛ با عبور از آستانه، سرویس قطع نمی‌شود."
    )
    await callback.message.edit_text(text, reply_markup=keyboard_durations(plans, back_to="location"))


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

    data = await state.get_data()
    cat_text = category_label(data.get("category"))
    loc_text = location_label(selected_plan.get("location"))
    fup_text = fair_usage_label(selected_plan)
    price_text = format_price(selected_plan["price"])

    summary = [
        "🧾 پیش‌نمایش سفارش شما:",
        f"🔸 دسته: {cat_text}",
        f"🔹 لوکیشن: {loc_text}",
        f"📦 {fup_text}",
        f"📅 مدت زمان: {selected_plan['name']}",
        f"💰 مبلغ: {price_text} تومان",
        "",
        "ℹ️ توجه: «آستانه مصرف منصفانه» به معنی قطع سرویس بعد از اتمام نیست."
    ]
    return await callback.message.edit_text("\n".join(summary), reply_markup=keyboard_confirm())


# ---------------- Step 4: Confirm ---------------- #
@router.callback_query(F.data == "buy|confirm")
async def confirm_and_create(callback: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    plan = data.get("plan")

    if not plan:
        await state.clear()
        return await edit_then_show_main_menu(callback.message, "خطا در دریافت اطلاعات پلن. دوباره تلاش کنید.")

    user_id = callback.from_user.id
    user_balance = get_user_balance(user_id)
    if user_balance < plan["price"]:
        await state.clear()
        await callback.message.edit_text(
            f"❌ موجودی کافی نیست.\n💰 قیمت: {format_price(plan['price'])} تومان\n💳 موجودی: {format_price(user_balance)} تومان"
        )
        return await show_cards(callback.message, state)

    free_account = find_free_account()
    if not free_account:
        await state.clear()
        return await edit_then_show_main_menu(callback.message, "اکانت آزاد موجود نیست ❌")

    account_id, account_username, account_password = free_account
    try:
        order_id = insert_order(
            user_id=user_id,
            plan_id=plan["id"],
            username=account_username,
            price=plan["price"],
            status="active",
        )
        assign_account_to_order(account_id, order_id, plan["id"], "active")
    except Exception as e:
        print(f"خطا در درج سفارش: {e}")
        await state.clear()
        return await edit_then_show_main_menu(callback.message, "❌ خطایی در ثبت سفارش رخ داد.")

    change_group(username=account_username, group=plan["group_name"])
    new_balance = user_balance - plan["price"]
    update_user_balance(user_id, new_balance)

    await callback.message.answer(
        f"✅ سرویس شما فعال شد!\n\n"
        f"🔸 پلن: {plan['name']}\n"
        f"📦 {fair_usage_label(plan)}\n"
        f"👤 نام کاربری: `{account_username}`\n"
        f"🔐 رمز: `{account_password}`\n"
        f"💰 موجودی: {format_price(new_balance)} تومان",
        parse_mode="Markdown",
        reply_markup=user_main_menu_keyboard()
    )

    admin_message = (
        f"📢 کاربر {callback.from_user.full_name} (ID: {user_id})\n"
        f"پلن: {plan['name']}\n"
        f"یوزرنیم: `{account_username}`\n"
        f"مبلغ: {format_price(plan['price'])} تومان"
    )
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
        return await callback.message.edit_text(
            "لطفاً نوع سرویس مورد نظر خود را انتخاب کنید:",
            reply_markup=keyboard_categories()
        )

    elif target == "location":
        data = await state.get_data()
        category = data.get("category") or "fixed_ip"
        await state.set_state(BuyServiceStates.choosing_location)
        available_locations = get_active_locations_by_category(category)
        if not available_locations:
            return await callback.message.edit_text("❌ فعلاً لوکیشنی برای این دسته موجود نیست.")
        return await callback.message.edit_text(
            "ابتدا لوکیشن را انتخاب کنید:",
            reply_markup=keyboard_locations(available_locations)
        )

    elif target == "duration":
        data = await state.get_data()
        category = data.get("category")
        location = data.get("location")

        if category in ("standard", "dual", "custom_location"):
            plans = [p for p in get_all_plans() if p["category"] == category]
            await state.set_state(BuyServiceStates.choosing_duration)
            text = (
                "مدت زمان سرویس را انتخاب کنید:\n"
                "ℹ️ این سرویس‌ها دارای «آستانه مصرف منصفانه» هستند؛ با عبور از آستانه، سرویس قطع نمی‌شود."
            )
            return await callback.message.edit_text(text, reply_markup=keyboard_durations(plans))

        elif category == "fixed_ip" and location:
            plans = [p for p in get_all_plans() if p.get("location") == location]
            await state.set_state(BuyServiceStates.choosing_duration)
            text = (
                "مدت زمان سرویس را انتخاب کنید:\n"
                "ℹ️ این سرویس‌ها دارای «آستانه مصرف منصفانه» هستند؛ با عبور از آستانه، سرویس قطع نمی‌شود."
            )
            return await callback.message.edit_text(text, reply_markup=keyboard_durations(plans, back_to="location"))

    # fallback
    return
