# handlers/user/renew_service.py

import datetime
from typing import Optional, List, Dict, Any, Tuple

import jdatetime
from aiogram import Router, F
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import (
    Message,
    CallbackQuery,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
)

from handlers.user.get_cards import show_cards
from keyboards.user_main_menu import user_main_menu_keyboard

# از plan_picker همه‌ی لیبل‌ها + کیبوردهای اشتراکی را می‌آوریم
from keyboards.plan_picker import (
    category_label,
    location_label,
    fair_usage_label,
    format_price,
    normalize_category,         # نرمال‌سازی دسته‌ها
    keyboard_categories,        # با prefix قابل تنظیم
    keyboard_durations,         # با prefix قابل تنظیم
    keyboard_locations,         # با prefix قابل تنظیم
    keyboard_confirm,           # با prefix قابل تنظیم
)

from services import IBSng
from services.IBSng import change_group
from services.admin_notifier import send_message_to_admins
from services.db import (
    get_all_plans,
    get_user_balance,
    update_user_balance,
    get_services_for_renew,
    insert_renewed_order,
    update_order_status,
    get_active_locations_by_category,
)

router = Router()


# ---------------- Helpers ---------------- #
def _is_active(plan: Dict[str, Any]) -> bool:
    val = plan.get("is_active", plan.get("active", 1))
    try:
        return int(val) == 1
    except Exception:
        return bool(val)


async def edit_then_show_main_menu(message: Message, text: str, *, parse_mode: Optional[str] = None):
    await message.edit_text(text, parse_mode=parse_mode)
    await message.answer("بازگشت به منوی اصلی", reply_markup=user_main_menu_keyboard())


# ---------------- FSM States ---------------- #
class RenewStates(StatesGroup):
    choosing_service = State()
    choosing_category = State()
    choosing_location = State()
    choosing_plan = State()
    confirming = State()


# ---------------- Keyboards (Renew namespace) ---------------- #
def kb_services_inline(services: List[Dict[str, Any]]) -> InlineKeyboardMarkup:
    rows = [[InlineKeyboardButton(text=str(s["username"]), callback_data=f"renew|service|{s['id']}")] for s in services]
    return InlineKeyboardMarkup(inline_keyboard=rows)


# ---------- Initial chooser (like buy) ----------
def make_initial_renew_keyboard(all_plans: List[Dict[str, Any]]) -> Tuple[str, InlineKeyboardMarkup, Optional[str], List[Dict[str, Any]]]:
    """
    خروجی:
      kind: "categories" یا "plans"
      markup: کیبورد آماده (با prefix=renew)
      only_category: اگر فقط یک دسته فعال بود، نام نرمال‌شدهٔ آن (برای ذخیره در state)
      plans_for_only_category: اگر kind == "plans" است، لیست پلن‌های همان دسته
    """
    active_plans = [p for p in all_plans if _is_active(p)]
    categories_set = {normalize_category(p.get("category")) for p in active_plans}
    categories = list(categories_set)  # ترتیب‌دهی را به keyboard_categories می‌سپاریم

    if len(categories) <= 1:
        only_cat = categories[0] if categories else None
        plans_for_cat = [p for p in active_plans if normalize_category(p.get("category")) == (only_cat or "standard")]
        markup = keyboard_durations(plans_for_cat, back_to="category", show_back=False, prefix="renew")
        return "plans", markup, only_cat, plans_for_cat

    markup = keyboard_categories(categories, prefix="renew")
    return "categories", markup, None, []


# ---------------- Step 0: Entry ---------------- #
@router.message(F.text == "📄 تمدید سرویس")
async def renew_start(message: Message, state: FSMContext):
    user_id = message.from_user.id
    services = get_services_for_renew(user_id)

    if not services:
        return await message.answer("⚠️ هیچ سرویسی برای تمدید پیدا نشد.", reply_markup=user_main_menu_keyboard())

    await state.clear()
    await state.update_data(services=services)
    await state.set_state(RenewStates.choosing_service)
    return await message.answer(
        "لطفاً سرویسی که می‌خواهید تمدید کنید را انتخاب کنید:",
        reply_markup=kb_services_inline(services)
    )


# ---------------- Step 1: Choose Service ---------------- #
@router.callback_query(F.data.startswith("renew|service"))
async def renew_choose_service(callback: CallbackQuery, state: FSMContext):
    _, _, service_id = callback.data.split("|")
    data = await state.get_data()
    services = data.get("services", [])
    selected_service = next((s for s in services if str(s["id"]) == service_id), None)
    print("renew126")
    if not selected_service:
        return await callback.answer("سرویس معتبر نیست.", show_alert=True)

    await state.update_data(selected_service=selected_service)

    all_plans = get_all_plans()
    kind, markup, only_category, plans_for_only_category = make_initial_renew_keyboard(all_plans)

    if kind == "plans" and only_category == "fixed_ip":
        print("renew136")
        await state.update_data(category="fixed_ip")
        available_locations = get_active_locations_by_category("fixed_ip")
        if not available_locations:
            return await callback.message.edit_text("❌ فعلاً لوکیشنی برای این دسته موجود نیست.")
        await state.set_state(RenewStates.choosing_location)
        # استفاده از keyboard_locations با prefix=renew
        return await callback.message.edit_text("ابتدا لوکیشن را انتخاب کنید:", reply_markup=keyboard_locations(available_locations, prefix="renew"))

    if kind == "categories":
        print("renew146")
        await state.set_state(RenewStates.choosing_category)
        return await callback.message.edit_text(
            "لطفاً نوع سرویس مورد نظر برای تمدید را انتخاب کنید:",
            reply_markup=markup
        )

    if only_category:
        print("renew154")
        await state.update_data(category=only_category)

    await state.set_state(RenewStates.choosing_plan)
    text = (
        "لطفاً پلن تمدید را انتخاب کنید:\n"
        "ℹ️ این سرویس‌ها دارای «آستانه مصرف منصفانه» هستند؛ با عبور از آستانه، سرویس قطع نمی‌شود."
    )
    return await callback.message.edit_text(text, reply_markup=markup)


# ---------------- Step 2: Choose Category ---------------- #
@router.callback_query(F.data.startswith("renew|category"))
async def renew_choose_category(callback: CallbackQuery, state: FSMContext):
    _, _, category = callback.data.split("|")
    category = normalize_category(category)
    await state.update_data(category=category)

    if category in ("standard", "dual", "custom_location", "modem"):
        print("renew_173")
        plans = [
            p for p in get_all_plans()
            if normalize_category(p.get("category")) == category and _is_active(p)
        ]
        await state.set_state(RenewStates.choosing_plan)
        text = (
            "لطفاً پلن تمدید را انتخاب کنید:\n"
            "ℹ️ این سرویس‌ها دارای «آستانه مصرف منصفانه» هستند؛ با عبور از آستانه، سرویس قطع نمی‌شود."
        )
        return await callback.message.edit_text(text, reply_markup=keyboard_durations(plans, prefix="renew"))

    elif category == "fixed_ip":
        print("renew_186")
        available_locations = get_active_locations_by_category(category)
        if not available_locations:
            return await callback.message.edit_text("❌ فعلاً لوکیشنی برای این دسته موجود نیست.")
        await state.set_state(RenewStates.choosing_location)
        return await callback.message.edit_text(
            "ابتدا لوکیشن را انتخاب کنید:",
            reply_markup=keyboard_locations(available_locations, prefix="renew")
        )

    else:
        return await callback.message.edit_text("❌ دسته نامعتبر است.")


# ---------------- Step 3: Choose Location (for fixed_ip) ---------------- #
@router.callback_query(F.data.startswith("renew|location"))
async def renew_choose_location(callback: CallbackQuery, state: FSMContext):
    _, _, location = callback.data.split("|")
    await state.update_data(location=location)

    plans = [
        p for p in get_all_plans()
        if p.get("location") == location and normalize_category(p.get("category")) == "fixed_ip" and _is_active(p)
    ]
    if not plans:
        return await callback.message.edit_text(
            "❌ برای این لوکیشن فعلاً پلنی موجود نیست.",
            reply_markup=keyboard_locations([location], back_to="category", prefix="renew")
        )

    await state.set_state(RenewStates.choosing_plan)
    text = (
        "لطفاً پلن تمدید را انتخاب کنید:\n"
        "ℹ️ این سرویس‌ها دارای «آستانه مصرف منصفانه» هستند؛ با عبور از آستانه، سرویس قطع نمی‌شود."
    )
    return await callback.message.edit_text(text, reply_markup=keyboard_durations(plans, back_to="location", prefix="renew"))


# ---------------- Step 4: Choose Plan ---------------- #
@router.callback_query(F.data.startswith("renew|plan"))
async def renew_choose_plan(callback: CallbackQuery, state: FSMContext):
    _, _, plan_id = callback.data.split("|")
    plans = get_all_plans()
    selected_plan = next((p for p in plans if str(p.get("id")) == plan_id), None)
    if not selected_plan:
        return await callback.answer("پلن معتبر نیست.", show_alert=True)
    print("renew272")

    await state.update_data(
        selected_plan=selected_plan,
        category=normalize_category(selected_plan.get("category")),
        location=selected_plan.get("location"),
    )
    await state.set_state(RenewStates.confirming)

    data = await state.get_data()
    selected_service = data.get("selected_service") or {}
    service_username = str(selected_service.get("username", ""))

    cat_text = category_label(data.get("category"))
    loc_text = location_label(selected_plan.get("location"))
    fup_text = fair_usage_label(selected_plan)
    price_text = format_price(selected_plan["price"])
    print("renew_249")

    summary = [
        "🧾 پیش‌نمایش تمدید:",
        f"🔸 دسته: {cat_text}",
        f"🔹 لوکیشن: {loc_text}",
        f"👤 نام کاربری فعلی: `{service_username}`",
        f"📦 {fup_text}",
        f"📅 مدت زمان: {selected_plan['name']}",
        f"💰 مبلغ: {price_text} تومان",
        "",
        "ℹ️ این تمدید روی همین نام‌کاربری اعمال می‌شود و یوزرنیم/رمز جدید ساخته نمی‌شود.",
        "",
        "لطفاً تایید کنید:",
    ]
    return await callback.message.edit_text("\n".join(summary), reply_markup=keyboard_confirm(prefix="renew"), parse_mode="Markdown")


# ---------------- Step 5: Confirm & Process ---------------- #
@router.callback_query(F.data == "renew|confirm")
async def renew_confirm_and_process(callback: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    selected_plan = data.get("selected_plan")
    selected_service = data.get("selected_service")
    print("renew273")
    print(selected_service)

    if not selected_plan or not selected_service:
        await state.clear()
        return await edit_then_show_main_menu(callback.message, "❌ خطا در دریافت اطلاعات. لطفاً دوباره تلاش کنید.")

    # کنترل موجودی
    user_id = callback.from_user.id
    current_balance = get_user_balance(user_id)
    plan_price = selected_plan["price"]
    if current_balance < plan_price:
        await state.clear()
        await callback.message.edit_text(
            f"❌ موجودی کافی نیست.\n💰 قیمت: {format_price(plan_price)} تومان\n💳 موجودی: {format_price(current_balance)} تومان"
        )
        return await show_cards(callback.message, state)

    # منطق تمدید
    plan_id = selected_plan["id"]
    plan_name = selected_plan["name"]
    plan_duration_months = selected_plan.get("duration_months")
    plan_group_name = selected_plan["group_name"]
    service_id = selected_service["id"]
    service_username = str(selected_service["username"])

    # تشخیص انقضا
    expires_at_greg = jdatetime.datetime.strptime(selected_service["expires_at"], "%Y-%m-%d %H:%M").togregorian()
    is_expired = selected_service["status"] == "expired" or expires_at_greg < datetime.datetime.now()

    # کسر موجودی
    new_balance = current_balance - plan_price
    update_user_balance(user_id, new_balance)

    if is_expired:
        # تمدید فوری
        update_order_status(order_id=service_id, new_status="renewed")
        insert_renewed_order(user_id, plan_id, service_username, plan_price, "active", service_id)

        IBSng.reset_account_client(username=service_username)
        change_group(username=service_username, group=plan_group_name)

        text_admin = (
            "🔔 تمدید انجام شد (فعالسازی فوری)\n"
            f"👤 کاربر: {user_id}\n🆔 یوزرنیم: {service_username}\n📦 پلن: {plan_name}\n"
            f"⏳ مدت: {plan_duration_months} ماه\n💳 مبلغ: {format_price(plan_price)} تومان\n🟢 وضعیت: فعال شد"
        )
        await send_message_to_admins(text_admin)

        await callback.message.edit_text(
            f"✅ تمدید با موفقیت انجام شد و سرویس شما فوراً فعال گردید.\n\n"
            f"🔸 پلن: {plan_name}\n"
            f"👤 نام کاربری: `{service_username}`\n"
            f"💰 موجودی: {format_price(new_balance)} تومان",
            parse_mode="Markdown"
        )
        await callback.message.answer("بازگشت به منوی اصلی", reply_markup=user_main_menu_keyboard())
        await state.clear()
        return

    # اگر هنوز فعال است → رزرو تمدید در انتهای دوره
    update_order_status(order_id=service_id, new_status="waiting_for_renewal")
    insert_renewed_order(user_id, plan_id, service_username, plan_price, "reserved", service_id)

    text_admin = (
        "🔔 تمدید رزروی ثبت شد\n"
        f"👤 کاربر: {user_id}\n🆔 یوزرنیم: {service_username}\n📦 پلن: {plan_name}\n"
        f"⏳ مدت: {plan_duration_months} ماه\n💳 مبلغ: {format_price(plan_price)} تومان\n🟡 وضعیت: در انتظار اتمام دوره"
    )
    await send_message_to_admins(text_admin)

    await callback.message.edit_text(
        "✅ تمدید شما ثبت شد و پس از پایان دوره‌ی فعلی به‌صورت خودکار اعمال می‌شود."
    )
    await callback.message.answer("بازگشت به منوی اصلی", reply_markup=user_main_menu_keyboard())
    await state.clear()


# ---------------- Back Navigation ---------------- #
@router.callback_query(F.data.startswith("renew|back"))
async def renew_go_back(callback: CallbackQuery, state: FSMContext):
    _, _, target = callback.data.split("|")
    data = await state.get_data()

    if target == "service":
        services = data.get("services") or get_services_for_renew(callback.from_user.id)
        await state.set_state(RenewStates.choosing_service)
        return await callback.message.edit_text(
            "لطفاً سرویسی که می‌خواهید تمدید کنید را انتخاب کنید:",
            reply_markup=kb_services_inline(services)
        )

    if target == "category":
        all_plans = get_all_plans()
        kind, markup, only_category, _ = make_initial_renew_keyboard(all_plans)
        if kind == "categories":
            await state.set_state(RenewStates.choosing_category)
            return await callback.message.edit_text(
                "لطفاً نوع سرویس مورد نظر برای تمدید را انتخاب کنید:",
                reply_markup=markup
            )
        else:
            if only_category == "fixed_ip":
                await state.update_data(category="fixed_ip")
                available_locations = get_active_locations_by_category("fixed_ip")
                if not available_locations:
                    return await callback.message.edit_text("❌ فعلاً لوکیشنی برای این دسته موجود نیست.")
                await state.set_state(RenewStates.choosing_location)
                return await callback.message.edit_text(
                    "ابتدا لوکیشن را انتخاب کنید:", reply_markup=keyboard_locations(available_locations, prefix="renew")
                )
            if only_category:
                await state.update_data(category=only_category)
            await state.set_state(RenewStates.choosing_plan)
            text = (
                "لطفاً پلن تمدید را انتخاب کنید:\n"
                "ℹ️ این سرویس‌ها دارای «آستانه مصرف منصفانه» هستند؛ با عبور از آستانه، سرویس قطع نمی‌شود."
            )
            return await callback.message.edit_text(text, reply_markup=markup)

    if target == "location":
        category = data.get("category") or "fixed_ip"
        await state.set_state(RenewStates.choosing_location)
        available_locations = get_active_locations_by_category(category)
        if not available_locations:
            return await callback.message.edit_text("❌ فعلاً لوکیشنی برای این دسته موجود نیست.")
        return await callback.message.edit_text(
            "ابتدا لوکیشن را انتخاب کنید:", reply_markup=keyboard_locations(available_locations, prefix="renew")
        )

    if target == "plan":
        plan = data.get("selected_plan")
        category = data.get("category")
        location = data.get("location")

        if not category and plan:
            category = normalize_category(plan.get("category"))
            await state.update_data(category=category)
        if not location and plan:
            location = plan.get("location")
            await state.update_data(location=location)

        if category in ("standard", "dual", "custom_location", "modem"):
            plans = [
                p for p in get_all_plans()
                if normalize_category(p.get("category")) == category and _is_active(p)
            ]
            await state.set_state(RenewStates.choosing_plan)
            text = (
                "لطفاً پلن تمدید را انتخاب کنید:\n"
                "ℹ️ این سرویس‌ها دارای «آستانه مصرف منصفانه» هستند؛ با عبور از آستانه، سرویس قطع نمی‌شود."
            )
            return await callback.message.edit_text(text, reply_markup=keyboard_durations(plans, prefix="renew"))

        elif category == "fixed_ip" and location:
            plans = [
                p for p in get_all_plans()
                if p.get("location") == location and normalize_category(p.get("category")) == "fixed_ip" and _is_active(p)
            ]
            await state.set_state(RenewStates.choosing_plan)
            text = (
                "لطفاً پلن تمدید را انتخاب کنید:\n"
                "ℹ️ این سرویس‌ها دارای «آستانه مصرف منصفانه» هستند؛ با عبور از آستانه، سرویس قطع نمی‌شود."
            )
            return await callback.message.edit_text(text, reply_markup=keyboard_durations(plans, back_to="location", prefix="renew"))

        # fallback به ورودی
        all_plans = get_all_plans()
        kind, markup, only_category, _ = make_initial_renew_keyboard(all_plans)
        if kind == "categories":
            await state.set_state(RenewStates.choosing_category)
            return await callback.message.edit_text(
                "لطفاً نوع سرویس مورد نظر برای تمدید را انتخاب کنید:",
                reply_markup=markup
            )
        else:
            if only_category == "fixed_ip":
                await state.update_data(category="fixed_ip")
                available_locations = get_active_locations_by_category("fixed_ip")
                if not available_locations:
                    return await callback.message.edit_text("❌ فعلاً لوکیشنی برای این دسته موجود نیست.")
                await state.set_state(RenewStates.choosing_location)
                return await callback.message.edit_text(
                    "ابتدا لوکیشن را انتخاب کنید:", reply_markup=keyboard_locations(available_locations, prefix="renew")
                )
            if only_category:
                await state.update_data(category=only_category)
            await state.set_state(RenewStates.choosing_plan)
            text = (
                "لطفاً پلن تمدید را انتخاب کنید:\n"
                "ℹ️ این سرویس‌ها دارای «آستانه مصرف منصفانه» هستند؛ با عبور از آستانه، سرویس قطع نمی‌شود."
            )
            return await callback.message.edit_text(text, reply_markup=markup)
    return
