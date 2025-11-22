# handlers/user/buy_service.py

import asyncio
import re
from typing import Optional, List, Dict, Any, Tuple, Union

from aiogram import Router, F
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import StatesGroup, State
from aiogram.types import Message, CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup

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
    update_last_name
)

router = Router()


# ---------------- plan_picker content merged ---------------- #

def normalize_category(category: Optional[str]) -> str:
    c = (category or "").strip().lower()
    return c if c else "standard"


def category_label(category: Optional[str]) -> str:
    cat = normalize_category(category)
    mapping = {
        "standard": "✨ معمولی",
        "dual": "👥 دوکاربره",
        "fixed_ip": "📌 آی‌پی ثابت",
        "custom_location": "📍 لوکیشن دلخواه",
        "modem": "📶 مودم/روتر",
    }
    return mapping.get(cat, "❓ نامشخص")


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


def fair_usage_label(plan: Dict) -> str:
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


def _is_active(plan: Dict) -> bool:
    val = plan.get("is_active", plan.get("active", 1))
    try:
        return int(val) == 1
    except Exception:
        return bool(val)


CATEGORY_PRIORITY = [
    "standard",
    "dual",
    "fixed_ip",
    "custom_location",
    "modem",
]


def _sort_categories(categories: List[str]) -> List[str]:
    prio = {c: i for i, c in enumerate(CATEGORY_PRIORITY)}
    return sorted(categories, key=lambda c: prio.get(c, 10_000))


_PERSIAN_DIGITS = str.maketrans("۰۱۲۳۴۵۶۷۸۹", "0123456789")


def _to_en_digits(s: str) -> str:
    try:
        return s.translate(_PERSIAN_DIGITS)
    except Exception:
        return s


def _safe_int(x, default: int = 0) -> int:
    try:
        return int(x)
    except Exception:
        return default


def _infer_days_from_group(group_name: Optional[str]) -> int:
    if not group_name:
        return 0
    m = re.search(r"(\d+)\s*D\b", group_name.upper())
    if m:
        return _safe_int(m.group(1), 0)
    return 0


def _infer_days_from_name(name: Optional[str]) -> int:
    if not name:
        return 0
    s = _to_en_digits(str(name))
    m = re.search(r"(\d+)\s*روز", s)
    if m:
        return _safe_int(m.group(1), 0)
    m = re.search(r"(\d+)\s*ماه", s)
    if m:
        months = _safe_int(m.group(1), 0)
        if months == 3:
            return 90
    return 0


def _is_three_months(plan: Dict) -> bool:
    try:
        d_months = _safe_int(plan.get("duration_months") or 0, 0)
        if d_months == 3:
            return True
        d_days = _safe_int(plan.get("duration_days") or 0, 0)
        if d_days in (90, 91, 92, 93, 94, 95, 96, 97):
            return True
        if d_days == 0:
            d_from_group = _infer_days_from_group(plan.get("group_name"))
            if d_from_group in (90, 91, 92, 93, 94, 95, 96, 97):
                return True
            d_from_name = _infer_days_from_name(plan.get("name"))
            if d_from_name in (90, 91, 92, 93, 94, 95, 96, 97):
                return True
        return False
    except Exception:
        return False


def _plan_badge(plan: Dict) -> str:
    if _is_three_months(plan):
        return "⭐️"
    return ""


def keyboard_categories(categories: List[str]) -> InlineKeyboardMarkup:
    ordered = _sort_categories(categories)
    rows = []
    for cat in ordered:
        rows.append([
            InlineKeyboardButton(
                text=category_label(cat),
                callback_data=f"buy|category|{cat}"
            )
        ])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def keyboard_durations(
        plans: List[Dict],
        back_to: str = "category",
        show_back: bool = True
) -> InlineKeyboardMarkup:
    rows = []
    for plan in plans:
        badge = _plan_badge(plan)
        label = f"{badge}{plan.get('name', 'بدون نام')} • {format_price(plan.get('price', 0))} تومان{badge}"
        rows.append([
            InlineKeyboardButton(
                text=label,
                callback_data=f"buy|duration|{plan['id']}"
            )
        ])
    if show_back:
        rows.append([InlineKeyboardButton(text="⬅️ بازگشت", callback_data=f"buy|back|{back_to}")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def keyboard_locations(locations: List[str], back_to: str = "category") -> InlineKeyboardMarkup:
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


def keyboard_confirm() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✅ تایید و پرداخت", callback_data="buy|confirm")],
        [InlineKeyboardButton(text="⬅️ بازگشت", callback_data="buy|back|duration")]
    ])


def make_initial_buy_keyboard(all_plans: List[Dict]) -> Tuple[str, InlineKeyboardMarkup, Optional[str], List[Dict]]:
    active_plans = [p for p in all_plans if _is_active(p)]
    categories_set = {normalize_category(p.get("category")) for p in active_plans}
    categories = _sort_categories(list(categories_set))

    if len(categories) <= 1:
        only_cat = categories[0] if categories else None
        plans_for_cat = [p for p in active_plans if normalize_category(p.get("category")) == (only_cat or "standard")]
        return "plans", keyboard_durations(plans_for_cat, back_to="category", show_back=False), only_cat, plans_for_cat

    return "categories", keyboard_categories(categories), None, []


# ---------------- Helpers ---------------- #

async def edit_then_show_main_menu(
        message: Message,
        text: str,
        *,
        parse_mode: Optional[str] = None
):
    await message.edit_text(text, parse_mode=parse_mode)
    await message.answer("بازگشت به منوی اصلی", reply_markup=user_main_menu_keyboard())


# ---------------- FSM States ---------------- #

class BuyServiceStates(StatesGroup):
    choosing_category = State()
    choosing_location = State()
    choosing_duration = State()
    confirming = State()


# ---------------- Step 0: Entry ---------------- #

@router.message(F.text == "🛒 خرید سرویس")
async def start_buy(message: Message, state: FSMContext):
    user_id = message.from_user.id
    first_name = message.from_user.first_name
    last_name = message.from_user.last_name
    username = message.from_user.username
    role = "admin" if user_id in ADMINS else "user"
    if last_name:
        update_last_name(user_id=user_id, last_name=last_name)

    if not ensure_user_exists(user_id=user_id):
        add_user(user_id, first_name, username, role)

    all_plans = get_all_plans()
    kind, markup, only_category, _plans_for_only_category = make_initial_buy_keyboard(all_plans)

    if kind == "categories":
        await state.set_state(BuyServiceStates.choosing_category)
        await message.answer("لطفاً نوع سرویس مورد نظر خود را انتخاب کنید:", reply_markup=markup)
        return

    if only_category:
        await state.update_data(category=only_category)
    await state.set_state(BuyServiceStates.choosing_duration)
    text = (
        "مدت زمان سرویس را انتخاب کنید:\n"
        "ℹ️ این سرویس‌ها دارای «آستانه مصرف منصفانه» هستند؛ با عبور از آستانه، سرویس قطع نمی‌شود."
    )
    await message.answer(text, reply_markup=markup)


# ---------------- Step 1: Choose Category ---------------- #

@router.callback_query(F.data.startswith("buy|category"))
async def choose_category(callback: CallbackQuery, state: FSMContext):
    _, _, category_raw = callback.data.split("|")
    category = normalize_category(category_raw)
    await state.update_data(category=category)

    plans = [
        p for p in get_all_plans()
        if normalize_category(p.get("category")) == category and _is_active(p)
    ]

    if category in ("standard", "dual", "custom_location", "modem"):
        await state.set_state(BuyServiceStates.choosing_duration)
        text = (
            "مدت زمان سرویس را انتخاب کنید:\n"
            "ℹ️ این سرویس‌ها دارای «آستانه مصرف منصفانه» هستند؛ با عبور از آستانه، سرویس قطع نمی‌شود."
        )
        return await callback.message.edit_text(text, reply_markup=keyboard_durations(plans))

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

    plans = [
        p for p in get_all_plans()
        if p.get("location") == location
           and normalize_category(p.get("category")) == "fixed_ip"
           and _is_active(p)
    ]

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
    selected_plan = next((p for p in plans if str(p.get("id")) == plan_id), None)

    if not selected_plan:
        return await callback.answer("پلن معتبر یافت نشد", show_alert=True)

    await state.update_data(
        plan=selected_plan,
        category=normalize_category(selected_plan.get("category")),
        location=selected_plan.get("location"),
    )

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
        "ℹ️ توجه: «مصرف منصفانه» به معنی قطع سرویس بعد از اتمام نیست.",
        "",
        "لطفاً تایید کنید:",
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
    first_name = callback.from_user.first_name
    last_name = callback.from_user.last_name

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
            volume_gb=plan.get("volume_gb"),
        )
        assign_account_to_order(account_id)
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
        f"📥 کاربر <a href='tg://user?id={user_id}'>{user_id} {first_name} {last_name or ' '}</a> \n"
        f"سرویس جدید خریداری کرد\n"
        f"پلن: {plan['name']}\n"
        f"یوزرنیم: `{account_username}`\n"
        f"رمزعبور: `{account_password}`\n"
        f"مبلغ: {format_price(plan['price'])} تومان"
    )
    for admin_id in ADMINS:
        try:
            await callback.bot.send_message(admin_id, admin_message, parse_mode="HTML")
        except Exception as e:
            print(f"خطا در ارسال به ادمین {admin_id}: {e}")

    await state.clear()


# ---------------- Back Navigation ---------------- #
@router.callback_query(F.data.startswith("buy|back"))
async def go_back(callback: CallbackQuery, state: FSMContext):
    _, _, target = callback.data.split("|")

    if target == "category":
        # اگر چند دسته داشته‌ایم، دوباره همان لیست را نشان می‌دهیم
        all_plans = get_all_plans()
        kind, markup, only_category, _ = make_initial_buy_keyboard(all_plans)

        if kind == "categories":
            await state.set_state(BuyServiceStates.choosing_category)
            text = "لطفاً نوع سرویس مورد نظر خود را انتخاب کنید:"
            return await callback.message.edit_text(text, reply_markup=markup)
        else:
            # فقط یک دسته داریم → مستقیم به مدت‌ها برگردیم
            if only_category:
                await state.update_data(category=only_category)
            await state.set_state(BuyServiceStates.choosing_duration)
            text = (
                "مدت زمان سرویس را انتخاب کنید:\n"
                "ℹ️ این سرویس‌ها دارای «آستانه مصرف منصفانه» هستند؛ با عبور از آستانه، سرویس قطع نمی‌شود."
            )
            return await callback.message.edit_text(text, reply_markup=markup)

    elif target == "location":
        data = await state.get_data()
        category = normalize_category(data.get("category") or "fixed_ip")
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
        plan = data.get("plan")
        category = normalize_category(data.get("category") or (plan.get("category") if plan else None))
        location = data.get("location") or (plan.get("location") if plan else None)

        await state.update_data(category=category, location=location)

        if category in ("standard", "dual", "custom_location", "modem"):
            plans = [
                p for p in get_all_plans()
                if normalize_category(p.get("category")) == category and _is_active(p)
            ]
            await state.set_state(BuyServiceStates.choosing_duration)
            text = (
                "مدت زمان سرویس را انتخاب کنید:\n"
                "ℹ️ این سرویس‌ها دارای «آستانه مصرف منصفانه» هستند؛ با عبور از آستانه، سرویس قطع نمی‌شود."
            )
            return await callback.message.edit_text(text, reply_markup=keyboard_durations(plans))

        elif category == "fixed_ip" and location:
            plans = [
                p for p in get_all_plans()
                if p.get("location") == location
                   and normalize_category(p.get("category")) == "fixed_ip"
                   and _is_active(p)
            ]
            await state.set_state(BuyServiceStates.choosing_duration)
            text = (
                "مدت زمان سرویس را انتخاب کنید:\n"
                "ℹ️ این سرویس‌ها دارای «آستانه مصرف منصفانه» هستند؛ با عبور از آستانه، سرویس قطع نمی‌شود."
            )
            return await callback.message.edit_text(
                text,
                reply_markup=keyboard_durations(plans, back_to="location")
            )

        # اگر هنوز چیزی پیدا نشد، برگرد به مرحلهٔ اول
        all_plans = get_all_plans()
        kind, markup, only_category, _ = make_initial_buy_keyboard(all_plans)
        if kind == "categories":
            await state.set_state(BuyServiceStates.choosing_category)
            text = "لطفاً نوع سرویس مورد نظر خود را انتخاب کنید:"
            return await callback.message.edit_text(text, reply_markup=markup)
        else:
            if only_category:
                await state.update_data(category=only_category)
            await state.set_state(BuyServiceStates.choosing_duration)
            text = (
                "مدت زمان سرویس را انتخاب کنید:\n"
                "ℹ️ این سرویس‌ها دارای «آستانه مصرف منصفانه» هستند؛ با عبور از آستانه، سرویس قطع نمی‌شود."
            )
            return await callback.message.edit_text(text, reply_markup=markup)

    # fallback
    return
