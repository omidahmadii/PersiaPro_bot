import asyncio
import datetime
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
from typing import Optional, Union, List, Dict, Any

from config import BOT_TOKEN
from keyboards.user_main_menu import user_main_menu_keyboard
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
    get_active_locations_by_category,  # اضافه شده برای لوکیشن‌های fixed_ip
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


def fair_usage_label(plan: Dict[str, Any]) -> str:
    try:
        if int(plan.get("is_unlimited") or 0) == 1:
            return "نامحدود (مصرف منصفانه)"
    except Exception:
        pass
    vol = plan.get("volume_gb")
    if vol:
        return f"آستانه مصرف منصفانه: {vol} گیگ"
    return "بدون آستانه مشخص"


def format_price(amount: Union[int, float]) -> str:
    try:
        return f"{int(amount):,}"
    except Exception:
        return str(amount)


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


# ---------------- Keyboards ---------------- #
def kb_services_inline(services: List[Dict[str, Any]]) -> InlineKeyboardMarkup:
    # هر سرویس با username نمایش داده می‌شود
    rows = [[InlineKeyboardButton(text=str(s["username"]), callback_data=f"renew|service|{s['id']}") ] for s in services]
    return InlineKeyboardMarkup(inline_keyboard=rows)

def kb_categories() -> InlineKeyboardMarkup:
    rows = [
        [InlineKeyboardButton(text="معمولی", callback_data="renew|category|standard")],
        [InlineKeyboardButton(text="دوکاربره", callback_data="renew|category|dual")],
        [InlineKeyboardButton(text="آی‌پی ثابت", callback_data="renew|category|fixed_ip")],
        [InlineKeyboardButton(text="لوکیشن دلخواه قابل تغییر", callback_data="renew|category|custom_location")],
        [InlineKeyboardButton(text="⬅️ بازگشت", callback_data="renew|back|service")],
    ]
    return InlineKeyboardMarkup(inline_keyboard=rows)

def kb_locations(locations: List[str], back_to: str = "category") -> InlineKeyboardMarkup:
    flags = {
        "france": "🇫🇷 فرانسه",
        "turkey": "🇹🇷 ترکیه",
        "iran": "🇮🇷 ایران",
        "england": "🇬🇧 انگلیس",
    }
    rows: List[List[InlineKeyboardButton]] = []
    for loc in locations:
        label = flags.get(loc, loc)
        rows.append([InlineKeyboardButton(text=label, callback_data=f"renew|location|{loc}")])
    rows.append([InlineKeyboardButton(text="⬅️ بازگشت", callback_data=f"renew|back|{back_to}")])
    return InlineKeyboardMarkup(inline_keyboard=rows)

def kb_plans(plans: List[Dict[str, Any]], back_to: str = "category") -> InlineKeyboardMarkup:
    rows = []
    for p in plans:
        # label = f"{p['name']} • {fair_usage_label(p)} • {format_price(p['price'])} تومان"
        label = f"{p['name']} - {format_price(p['price'])} تومان"
        rows.append([InlineKeyboardButton(text=label, callback_data=f"renew|plan|{p['id']}")])
    rows.append([InlineKeyboardButton(text="⬅️ بازگشت", callback_data=f"renew|back|{back_to}")])
    return InlineKeyboardMarkup(inline_keyboard=rows)

def kb_confirm() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✅ تایید و تمدید", callback_data="renew|confirm")],
        [InlineKeyboardButton(text="⬅️ بازگشت", callback_data="renew|back|plan")],
    ])



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
    return await message.answer("لطفاً سرویسی که می‌خواهید تمدید کنید را انتخاب کنید:", reply_markup=kb_services_inline(services))


# ---------------- Step 1: Choose Service ---------------- #
@router.callback_query(F.data.startswith("renew|service"))
async def renew_choose_service(callback: CallbackQuery, state: FSMContext):
    _, _, service_id = callback.data.split("|")
    data = await state.get_data()
    services = data.get("services", [])
    selected_service = next((s for s in services if str(s["id"]) == service_id), None)

    if not selected_service:
        return await callback.answer("سرویس معتبر نیست.", show_alert=True)

    # ذخیره سرویس انتخاب‌شده
    await state.update_data(selected_service=selected_service)

    await state.set_state(RenewStates.choosing_category)
    return await callback.message.edit_text(
        "لطفاً نوع سرویس مورد نظر برای تمدید را انتخاب کنید:",
        reply_markup=kb_categories()
    )


# ---------------- Step 2: Choose Category ---------------- #
@router.callback_query(F.data.startswith("renew|category"))
async def renew_choose_category(callback: CallbackQuery, state: FSMContext):
    _, _, category = callback.data.split("|")
    await state.update_data(category=category)

    plans = [p for p in get_all_plans() if p["category"] == category]

    if category in ("standard", "dual", "custom_location"):
        await state.set_state(RenewStates.choosing_plan)
        text = (
            "لطفاً پلن تمدید را انتخاب کنید:\n"
            "ℹ️ این سرویس‌ها دارای «آستانه مصرف منصفانه» هستند؛ با عبور از آستانه، سرویس قطع نمی‌شود."
        )
        return await callback.message.edit_text(text, reply_markup=kb_plans(plans))

    elif category == "fixed_ip":
        available_locations = get_active_locations_by_category(category)
        if not available_locations:
            return await callback.message.edit_text("❌ فعلاً لوکیشنی برای این دسته موجود نیست.")
        await state.set_state(RenewStates.choosing_location)
        return await callback.message.edit_text("ابتدا لوکیشن را انتخاب کنید:", reply_markup=kb_locations(available_locations))

    else:
        return await callback.message.edit_text("❌ دسته نامعتبر است.")


# ---------------- Step 3: Choose Location (for fixed_ip) ---------------- #
@router.callback_query(F.data.startswith("renew|location"))
async def renew_choose_location(callback: CallbackQuery, state: FSMContext):
    _, _, location = callback.data.split("|")
    await state.update_data(location=location)

    plans = [p for p in get_all_plans() if p.get("location") == location and p["category"] == "fixed_ip"]
    if not plans:
        return await callback.message.edit_text("❌ برای این لوکیشن فعلاً پلنی موجود نیست.", reply_markup=kb_locations([location], back_to="category"))

    await state.set_state(RenewStates.choosing_plan)
    text = (
        "لطفاً پلن تمدید را انتخاب کنید:\n"
        "ℹ️ این سرویس‌ها دارای «آستانه مصرف منصفانه» هستند؛ با عبور از آستانه، سرویس قطع نمی‌شود."
    )
    return await callback.message.edit_text(text, reply_markup=kb_plans(plans, back_to="location"))


# ---------------- Step 4: Choose Plan ---------------- #
@router.callback_query(F.data.startswith("renew|plan"))
async def renew_choose_plan(callback: CallbackQuery, state: FSMContext):
    _, _, plan_id = callback.data.split("|")
    plans = get_all_plans()
    selected_plan = next((p for p in plans if str(p["id"]) == plan_id), None)
    if not selected_plan:
        return await callback.answer("پلن معتبر نیست.", show_alert=True)

    await state.update_data(selected_plan=selected_plan)
    await state.set_state(RenewStates.confirming)

    data = await state.get_data()
    cat_text = category_label(data.get("category"))
    loc_text = location_label(selected_plan.get("location"))
    fup_text = fair_usage_label(selected_plan)
    price_text = format_price(selected_plan["price"])

    summary = [
        "🧾 پیش‌نمایش تمدید:",
        f"🔸 دسته: {cat_text}",
        f"🔹 لوکیشن: {loc_text}",
        f"📦 {fup_text}",
        f"📅 مدت زمان: {selected_plan['name']}",
        f"💰 مبلغ: {price_text} تومان",
        "",
        "ℹ️ توجه: «آستانه مصرف منصفانه» به معنی قطع سرویس بعد از اتمام نیست."
    ]
    return await callback.message.edit_text("\n".join(summary), reply_markup=kb_confirm())


# ---------------- Step 5: Confirm & Process ---------------- #
@router.callback_query(F.data == "renew|confirm")
async def renew_confirm_and_process(callback: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    selected_plan = data.get("selected_plan")
    selected_service = data.get("selected_service")

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
        await callback.message.answer("بازگشت به منوی اصلی", reply_markup=user_main_menu_keyboard())
        # هدایت به شارژ حساب/درگاه (منطق خودت)
        return

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
        await state.set_state(RenewStates.choosing_category)
        return await callback.message.edit_text(
            "لطفاً نوع سرویس مورد نظر برای تمدید را انتخاب کنید:",
            reply_markup=kb_categories()
        )

    if target == "location":
        category = data.get("category") or "fixed_ip"
        await state.set_state(RenewStates.choosing_location)
        available_locations = get_active_locations_by_category(category)
        if not available_locations:
            return await callback.message.edit_text("❌ فعلاً لوکیشنی برای این دسته موجود نیست.")
        return await callback.message.edit_text(
            "ابتدا لوکیشن را انتخاب کنید:", reply_markup=kb_locations(available_locations)
        )

    if target == "plan":
        category = data.get("category")
        location = data.get("location")
        if category in ("standard", "dual", "custom_location"):
            plans = [p for p in get_all_plans() if p["category"] == category]
            await state.set_state(RenewStates.choosing_plan)
            text = (
                "لطفاً پلن تمدید را انتخاب کنید:\n"
                "ℹ️ این سرویس‌ها دارای «آستانه مصرف منصفانه» هستند؛ با عبور از آستانه، سرویس قطع نمی‌شود."
            )
            return await callback.message.edit_text(text, reply_markup=kb_plans(plans))
        elif category == "fixed_ip" and location:
            plans = [p for p in get_all_plans() if p.get("location") == location and p["category"] == "fixed_ip"]
            await state.set_state(RenewStates.choosing_plan)
            text = (
                "لطفاً پلن تمدید را انتخاب کنید:\n"
                "ℹ️ این سرویس‌ها دارای «آستانه مصرف منصفانه» هستند؛ با عبور از آستانه، سرویس قطع نمی‌شود."
            )
            return await callback.message.edit_text(text, reply_markup=kb_plans(plans, back_to="location"))

    return
