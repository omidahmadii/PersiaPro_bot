# handlers/user/renew_service.py

import datetime
import re
from typing import Optional, List, Dict, Any, Tuple, Union

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

from handlers.user.start import is_user_member, join_channel_keyboard
from keyboards.main_menu import user_main_menu_keyboard
from services import IBSng
from services.IBSng import change_group
from services.admin_notifier import send_message_to_admins
from services.db import get_active_cards
from services.db import (
    get_renew_plans,
    get_user_balance,
    update_user_balance,
    get_services_for_renew,
    insert_renewed_order,
    update_order_status,
    get_active_locations_by_category,
    get_order_status,
    update_last_name,
)
from services.runtime_settings import get_access_mode_setting, get_bool_setting, get_text_setting

router = Router()

DEFAULT_MEMBERSHIP_REQUIRED_TEXT = "🔒 برای استفاده از این بخش باید عضو کانال PersiaPro باشید."
DEFAULT_RENEW_DISABLED_TEXT = "در حال حاضر تمدید سرویس غیر فعال می باشد."
DEFAULT_RENEW_NO_SERVICES_TEXT = "⚠️ هیچ سرویسی برای تمدید پیدا نشد."


def is_renew_enabled() -> bool:
    return get_bool_setting("feature_renew_enabled", default=False)


def get_renew_access_mode() -> str:
    return get_access_mode_setting("feature_renew_access_mode", default="funded_only")


def is_renew_funded_only_mode() -> bool:
    return get_renew_access_mode() == "funded_only"


def get_membership_required_text() -> str:
    return get_text_setting("message_membership_required", DEFAULT_MEMBERSHIP_REQUIRED_TEXT)


def get_renew_disabled_text() -> str:
    return get_text_setting("message_renew_disabled", DEFAULT_RENEW_DISABLED_TEXT)


def get_renew_no_services_text() -> str:
    return get_text_setting("message_renew_no_services", DEFAULT_RENEW_NO_SERVICES_TEXT)


async def ensure_renew_enabled_message(message: Message, state: FSMContext) -> bool:
    if is_renew_enabled():
        return True

    await state.clear()
    await message.answer(get_renew_disabled_text(), reply_markup=user_main_menu_keyboard())
    return False


async def ensure_renew_enabled_callback(callback: CallbackQuery, state: FSMContext) -> bool:
    if is_renew_enabled():
        return True

    await state.clear()
    await callback.message.answer(get_renew_disabled_text(), reply_markup=user_main_menu_keyboard())
    return False


# ------------------------ MemberShip ------------------------ #

async def membership_guard_message(message: Message) -> bool:
    if not await is_user_member(message.from_user.id):
        await message.answer(
            get_membership_required_text(),
            reply_markup=join_channel_keyboard()
        )
        return False
    return True


async def membership_guard_callback(callback: CallbackQuery) -> bool:
    if not await is_user_member(callback.from_user.id):
        await callback.answer("❌ ابتدا عضو کانال شوید", show_alert=True)
        await callback.message.answer(
            get_membership_required_text(),
            reply_markup=join_channel_keyboard()
        )
        return False
    return True


# ---------------- plan_picker (merged & adapted for renew) ---------------- #

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
        "special_access": "⚡ دسترسی ویژه",
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
    "special_access",
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
    m = re.search(r"(\d+)\s*D\b", (group_name or "").upper())
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


def keyboard_categories(categories: List[str], prefix: str = "renew") -> InlineKeyboardMarkup:
    ordered = _sort_categories(categories)
    rows = []
    for cat in ordered:
        rows.append([
            InlineKeyboardButton(
                text=category_label(cat),
                callback_data=f"{prefix}|category|{cat}"
            )
        ])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def keyboard_durations(
        plans: List[Dict],
        back_to: str = "category",
        show_back: bool = True,
        prefix: str = "renew"
) -> InlineKeyboardMarkup:
    rows = []
    for plan in plans:
        badge = _plan_badge(plan)
        label = f"{badge}{plan.get('name', 'بدون نام')} • {format_price(plan.get('price', 0))} تومان{badge}"
        rows.append([
            InlineKeyboardButton(
                text=label,
                callback_data=f"{prefix}|plan|{plan['id']}"
            )
        ])
    if show_back:
        rows.append([InlineKeyboardButton(text="⬅️ بازگشت", callback_data=f"{prefix}|back|{back_to}")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def keyboard_locations(locations: List[str], back_to: str = "category", prefix: str = "renew") -> InlineKeyboardMarkup:
    rows = []
    flags = {
        "france": "🇫🇷 فرانسه",
        "turkey": "🇹🇷 ترکیه",
        "iran": "🇮🇷 ایران",
        "england": "🇬🇧 انگلیس",
    }
    for loc in locations:
        label = flags.get(loc, loc)
        rows.append([InlineKeyboardButton(text=label, callback_data=f"{prefix}|location|{loc}")])
    rows.append([InlineKeyboardButton(text="⬅️ بازگشت", callback_data=f"{prefix}|back|{back_to}")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def keyboard_confirm(prefix: str = "renew") -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✅ تایید", callback_data=f"{prefix}|confirm")],
        [InlineKeyboardButton(text="⬅️ بازگشت", callback_data=f"{prefix}|back|plan")]
    ])


def make_initial_renew_keyboard(all_plans: List[Dict]) -> Tuple[str, InlineKeyboardMarkup, Optional[str], List[Dict]]:
    active_plans = [p for p in all_plans if _is_active(p)]
    categories_set = {normalize_category(p.get("category")) for p in active_plans}
    categories = _sort_categories(list(categories_set))

    if len(categories) <= 1:
        only_cat = categories[0] if categories else None
        plans_for_cat = [p for p in active_plans if normalize_category(p.get("category")) == (only_cat or "standard")]
        return "plans", keyboard_durations(plans_for_cat, back_to="category", show_back=False,
                                           prefix="renew"), only_cat, plans_for_cat

    return "categories", keyboard_categories(categories, prefix="renew"), None, []


def get_min_active_plan_price(plans: List[Dict]) -> int:
    active_plans = [p for p in plans if _is_active(p)]
    if not active_plans:
        return 0
    try:
        return min(int(p.get("price", 0) or 0) for p in active_plans)
    except Exception:
        return 0


def build_plans_price_list(plans: List[Dict]) -> str:
    active_plans = [p for p in plans if _is_active(p)]
    if not active_plans:
        return "در حال حاضر پلن فعالی برای تمدید موجود نیست."

    lines = ["📋 لیست پلن‌های فعال تمدید:"]
    for plan in active_plans:
        name = plan.get("name", "بدون نام")
        price = format_price(plan.get("price", 0))
        lines.append(f"• {name} — {price} تومان")

    return "\n".join(lines)


# ---------------- Helpers ---------------- #

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
    # اگر می‌خواهی، می‌توانیم یک دکمه برگشت هم اضافه کنیم؛ الان نمایشی ساده است.
    return InlineKeyboardMarkup(inline_keyboard=rows)


# ---------------- Step 0: Entry ---------------- #
@router.message(F.text == "📄 تمدید سرویس")
async def renew_start(message: Message, state: FSMContext):
    if not await membership_guard_message(message):
        return
    if not await ensure_renew_enabled_message(message, state):
        return
    user_id = message.from_user.id
    renew_plans = get_renew_plans()
    active_plans = [p for p in renew_plans if _is_active(p)]
    services = get_services_for_renew(user_id)

    last_name = message.from_user.last_name
    if last_name:
        update_last_name(user_id=user_id, last_name=last_name)

    if not active_plans:
        await state.clear()
        return await message.answer(
            "در حال حاضر پلن فعالی برای تمدید موجود نیست.",
            reply_markup=user_main_menu_keyboard()
        )

    if is_renew_funded_only_mode():
        user_balance = get_user_balance(user_id)
        min_price = get_min_active_plan_price(active_plans)

        if user_balance < min_price:
            await state.clear()
            plans_text = build_plans_price_list(active_plans)
            return await message.answer(
                "❌ در حال حاضر تمدید بسته است.\n\n"
                f"{plans_text}",
                reply_markup=user_main_menu_keyboard()
            )

    if not services:
        return await message.answer(get_renew_no_services_text(), reply_markup=user_main_menu_keyboard())

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
    if not await ensure_renew_enabled_callback(callback, state):
        return
    _, _, service_id = callback.data.split("|")
    data = await state.get_data()
    services = data.get("services", [])
    selected_service = next((s for s in services if str(s["id"]) == service_id), None)

    if not selected_service:
        return await callback.answer("سرویس معتبر نیست.", show_alert=True)

    await state.update_data(selected_service=selected_service)

    renew_plans = get_renew_plans()
    kind, markup, only_category, plans_for_only_category = make_initial_renew_keyboard(renew_plans)

    if kind == "plans" and only_category == "fixed_ip":
        await state.update_data(category="fixed_ip")
        available_locations = get_active_locations_by_category("fixed_ip")
        if not available_locations:
            return await callback.message.edit_text("❌ فعلاً لوکیشنی برای این دسته موجود نیست.")
        await state.set_state(RenewStates.choosing_location)
        return await callback.message.edit_text("ابتدا لوکیشن را انتخاب کنید:",
                                                reply_markup=keyboard_locations(available_locations, prefix="renew"))

    if kind == "categories":
        await state.set_state(RenewStates.choosing_category)
        return await callback.message.edit_text(
            "لطفاً نوع سرویس مورد نظر برای تمدید را انتخاب کنید:",
            reply_markup=markup
        )

    if only_category:
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
    if not await ensure_renew_enabled_callback(callback, state):
        return
    _, _, category = callback.data.split("|")
    category = normalize_category(category)
    await state.update_data(category=category)

    if category in ("standard", "dual", "custom_location", "modem", "special_access"):
        plans = [
            p for p in get_renew_plans()
            if normalize_category(p.get("category")) == category and _is_active(p)
        ]
        await state.set_state(RenewStates.choosing_plan)
        text = (
            "لطفاً پلن تمدید را انتخاب کنید:\n"
            "ℹ️ این سرویس‌ها دارای «آستانه مصرف منصفانه» هستند؛ با عبور از آستانه، سرویس قطع نمی‌شود."
        )
        return await callback.message.edit_text(text, reply_markup=keyboard_durations(plans, prefix="renew"))

    elif category == "fixed_ip":
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
    if not await ensure_renew_enabled_callback(callback, state):
        return
    _, _, location = callback.data.split("|")
    await state.update_data(location=location)

    plans = [
        p for p in get_renew_plans()
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
    return await callback.message.edit_text(text,
                                            reply_markup=keyboard_durations(plans, back_to="location", prefix="renew"))


# ---------------- Step 4: Choose Plan ---------------- #
@router.callback_query(F.data.startswith("renew|plan"))
async def renew_choose_plan(callback: CallbackQuery, state: FSMContext):
    if not await ensure_renew_enabled_callback(callback, state):
        return
    _, _, plan_id = callback.data.split("|")
    plans = get_renew_plans()
    selected_plan = next((p for p in plans if str(p.get("id")) == plan_id), None)
    if not selected_plan:
        return await callback.answer("پلن معتبر نیست.", show_alert=True)

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
    return await callback.message.edit_text("\n".join(summary), reply_markup=keyboard_confirm(prefix="renew"),
                                            parse_mode="Markdown")


# ---------------- Step 5: Confirm & Process ---------------- #
@router.callback_query(F.data == "renew|confirm")
async def renew_confirm_and_process(callback: CallbackQuery, state: FSMContext):
    if not await ensure_renew_enabled_callback(callback, state):
        return
    data = await state.get_data()
    selected_plan = data.get("selected_plan")
    selected_service = data.get("selected_service")

    if not selected_plan or not selected_service:
        await state.clear()
        return await edit_then_show_main_menu(callback.message, "❌ خطا در دریافت اطلاعات. لطفاً دوباره تلاش کنید.")

    # کنترل موجودی
    user_id = callback.from_user.id
    first_name = callback.from_user.first_name
    last_name = callback.from_user.last_name

    current_balance = get_user_balance(user_id)
    plan_price = selected_plan["price"]

    # منطق تمدید
    plan_id = selected_plan["id"]
    plan_name = selected_plan["name"]
    plan_duration_months = selected_plan.get("duration_months")
    plan_group_name = selected_plan["group_name"]
    service_id = selected_service["id"]
    service_username = str(selected_service["username"])
    volume_gb = selected_plan.get("volume_gb") or 0
    # تشخیص انقضا
    expires_at_greg = jdatetime.datetime.strptime(selected_service["expires_at"], "%Y-%m-%d %H:%M").togregorian()
    is_expired = selected_service["status"] == "expired" or expires_at_greg < datetime.datetime.now()
    latest_status = get_order_status(service_id)

    if latest_status is None:
        await state.clear()
        return await edit_then_show_main_menu(callback.message, "❌ سفارش پیدا نشد. لطفاً دوباره تلاش کنید.")
        # اگر قبلاً رزرو یا تمدید شده، دیگر اجازه تمدید مجدد نده

    block_statuses = {"waiting_for_renewal", "reserved", "renewed", "waiting_for_renewal_not_paid"}
    if latest_status in block_statuses:
        await state.clear()
        await callback.message.edit_text(
            "⚠️ این سرویس قبلاً برای تمدید ثبت شده یا هم‌اکنون تمدید شده است. "
            "اگر فکر می‌کنید اشتباه شده با پشتیبانی تماس بگیرید."
        )
        return await callback.message.answer("بازگشت به منوی اصلی", reply_markup=user_main_menu_keyboard())

    if current_balance < plan_price:

        update_order_status(order_id=service_id, new_status="waiting_for_renewal_not_paid")
        insert_renewed_order(user_id, plan_id, service_username, plan_price, "waiting_for_payment", service_id,
                             volume_gb)

        text_admin = (
            f"🔔 درخواست تمدید ایجاد شد (وضعیت در انتظار پرداخت)\n"
            f"📥 کاربر <a href='tg://user?id={user_id}'>{user_id} {first_name} {last_name or ' '}</a> \n"
            f"🆔 یوزرنیم: {service_username}\n"
            f"📦 پلن: {plan_name}\n"
            f"⏳ مدت: {plan_duration_months} ماه\n"
            f"💳 مبلغ: {format_price(plan_price)} تومان\n"
            f"🟢 وضعیت: در انتظار پرداخت"
        )
        await send_message_to_admins(text_admin)
        required_balanace = plan_price - current_balance
        active_cards = get_active_cards()
        cards_text = ""
        for card in active_cards:
            cards_text += (
                f"🏦 {card['bank_name']} "
                f"به نام {card['owner_name']}\n"
                f"<code>\u200F{card['card_number']}</code>\n\n"
            )

        text_user = (
            f"⚠️ موجودی شما کافی نمی باشد.\n"
            f" سرویس شما در وضعیت در انتظار پرداخت قرار گرفت.\n\n"
            f"لطفا مبلغ {format_price(required_balanace)} تومان به کارت زیر واریز نموده و تصویر آن را ارسال نمایید.\n\n"
            f"{cards_text}\n"
            f"⚠️ پس از تایید مبلغ توسط ادمین سرویس شما فعال خواهد شد."
        )
        await callback.message.answer(text=text_user, parse_mode="HTML", reply_markup=user_main_menu_keyboard())
        await state.clear()
    else:
        # کسر موجودی
        new_balance = current_balance - plan_price
        update_user_balance(user_id, new_balance)

        if is_expired:
            # تمدید فوری
            update_order_status(order_id=service_id, new_status="renewed")
            insert_renewed_order(user_id, plan_id, service_username, plan_price, "active", service_id, volume_gb)

            IBSng.reset_account_client(username=service_username)
            change_group(username=service_username, group=plan_group_name)

            text_admin = (
                "🔔 تمدید انجام شد (فعالسازی فوری)\n"
                f"📥 کاربر <a href='tg://user?id={user_id}'>{user_id} {first_name} {last_name or ' '}</a> \n"
                f"🆔 یوزرنیم: {service_username}\n📦 پلن: "
                f"{plan_name}\n"
                f"⏳ مدت: {plan_duration_months} ماه\n"
                f"💳 مبلغ: {format_price(plan_price)} تومان\n"
                f"🟢 وضعیت: فعال شد"
            )
            await send_message_to_admins(text_admin)

            await callback.message.edit_text(
                f"✅ تمدید با موفقیت انجام شد و سرویس شما فعال گردید.\n\n"
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
        insert_renewed_order(user_id, plan_id, service_username, plan_price, "reserved", service_id, volume_gb)

        text_admin = (
            "🔔 تمدید رزروی ثبت شد\n"
            f"📥 کاربر <a href='tg://user?id={user_id}'>{user_id} {first_name} {last_name or ' '}</a> \n"
            f"🆔 یوزرنیم: {service_username}\n📦 پلن: "
            f"{plan_name}\n"
            f"⏳ مدت: {plan_duration_months} ماه\n"
            f"💳 مبلغ: {format_price(plan_price)} تومان\n"
            f"🟡 وضعیت: در انتظار اتمام دوره"
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
    if not await ensure_renew_enabled_callback(callback, state):
        return
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
        all_plans = get_renew_plans()
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

        if category in ("standard", "dual", "custom_location", "modem", "special_access"):
            plans = [
                p for p in get_renew_plans()
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
                p for p in get_renew_plans()
                if
                p.get("location") == location and normalize_category(p.get("category")) == "fixed_ip" and _is_active(p)
            ]
            await state.set_state(RenewStates.choosing_plan)
            text = (
                "لطفاً پلن تمدید را انتخاب کنید:\n"
                "ℹ️ این سرویس‌ها دارای «آستانه مصرف منصفانه» هستند؛ با عبور از آستانه، سرویس قطع نمی‌شود."
            )
            return await callback.message.edit_text(text, reply_markup=keyboard_durations(plans, back_to="location",
                                                                                          prefix="renew"))

        # fallback به ورودی
        all_plans = get_renew_plans()
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
