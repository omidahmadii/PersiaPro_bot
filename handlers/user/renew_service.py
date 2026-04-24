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
from keyboards.main_menu import main_menu_keyboard_for_user
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
    get_pending_renewal_order,
    get_order_data,
)
from services.runtime_settings import get_access_mode_setting, get_bool_setting, get_text_setting
from services.payment_workflow import format_card_number_for_display
from services.usage_policy import get_volume_policy_alert, get_volume_policy_text

router = Router()

DEFAULT_MEMBERSHIP_REQUIRED_TEXT = "🔒 برای استفاده از این بخش باید عضو کانال PersiaPro باشید."
DEFAULT_RENEW_DISABLED_TEXT = "در حال حاضر تمدید سرویس غیر فعال می باشد."
DEFAULT_RENEW_NO_SERVICES_TEXT = "⚠️ هیچ سرویسی برای تمدید پیدا نشد."
def volume_policy_text() -> str:
    return get_volume_policy_text()


def volume_policy_alert() -> str:
    return get_volume_policy_alert()


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


def get_pending_renewal_services(services: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    return [service for service in services if service.get("status") == "waiting_for_renewal_not_paid"]


def build_renew_access_blocked_text(current_balance: int, min_price: int) -> str:
    _ = current_balance, min_price
    return "در حال حاضر امکان تمدید سرویس فعال نیست."


def get_renew_access_block_message(user_id: int) -> Optional[str]:
    if not is_renew_enabled():
        return get_renew_disabled_text()

    renew_plans = get_renew_plans(user_id=user_id)
    active_plans = [plan for plan in renew_plans if _is_active(plan)]
    if not active_plans:
        return None

    if not is_renew_funded_only_mode():
        return None

    services = get_services_for_renew(user_id)
    if get_pending_renewal_services(services):
        return None

    current_balance = int(get_user_balance(user_id) or 0)
    min_price = get_min_active_plan_price(active_plans)
    if current_balance >= min_price:
        return None

    return build_renew_access_blocked_text(current_balance, min_price)


async def ensure_renew_enabled_message(message: Message, state: FSMContext) -> bool:
    blocked_text = get_renew_access_block_message(message.from_user.id)
    if blocked_text is None:
        return True

    await state.clear()
    await message.answer(blocked_text, reply_markup=main_menu_keyboard_for_user(message.from_user.id))
    return False


async def ensure_renew_enabled_callback(callback: CallbackQuery, state: FSMContext) -> bool:
    blocked_text = get_renew_access_block_message(callback.from_user.id)
    if blocked_text is None:
        return True

    await state.clear()
    await callback.message.answer(
        blocked_text,
        reply_markup=main_menu_keyboard_for_user(callback.from_user.id),
    )
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
            return "نامحدود"
    except Exception:
        pass
    vol = plan.get("volume_gb")
    if vol:
        return f"{vol} گیگ"
    return "بدون حجم مشخص"


def format_price(amount: Union[int, float]) -> str:
    try:
        return f"{int(amount):,}"
    except Exception:
        return str(amount)


def format_created_at(created_at: Optional[str]) -> str:
    if not created_at:
        return "-"
    return str(created_at).replace("T", " ")


def build_cards_text() -> str:
    active_cards = get_active_cards()
    if not active_cards:
        return ""

    parts = []
    for card in active_cards:
        parts.append(
            f"🏦 {card['bank_name']} به نام {card['owner_name']}\n"
            f"<code>{format_card_number_for_display(card['card_number'])}</code>"
        )
    return "\n\n".join(parts)


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


def keyboard_pending_renewal_actions(service_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="❌ لغو این تمدید", callback_data=f"renew|pending_cancel|{service_id}")],
        [InlineKeyboardButton(text="⬅️ بازگشت", callback_data="renew|back|service")],
    ])


def pending_service_button_text(service: Dict[str, Any]) -> str:
    username = str(service["username"])
    if service.get("status") == "waiting_for_renewal_not_paid":
        return f"{username} - در انتظار پرداخت"
    if service.get("status") == "expired":
        return f"{username} - منقضی"
    return username


def is_service_expired_now(service: Dict[str, Any]) -> bool:
    expires_at = service.get("expires_at")
    if not expires_at:
        return False

    try:
        exp_greg = jdatetime.datetime.strptime(expires_at, "%Y-%m-%d %H:%M").togregorian()
        return exp_greg < datetime.datetime.now()
    except Exception:
        return False


def build_pending_renewal_text(service: Dict[str, Any], pending_order: Dict[str, Any], user_balance: int) -> str:
    price = int(pending_order.get("price") or 0)
    required_balance = max(price - int(user_balance or 0), 0)
    lines = [
        "⏳ برای این سرویس یک تمدید در انتظار پرداخت ثبت شده است.",
        "",
        f"👤 نام کاربری: <code>{service['username']}</code>",
        f"📦 پلن تمدید: {pending_order.get('plan_name') or 'نامشخص'}",
        f"💰 مبلغ تمدید: {format_price(price)} تومان",
        f"💳 موجودی فعلی شما: {format_price(user_balance)} تومان",
        f"🕒 زمان ثبت درخواست: {format_created_at(pending_order.get('created_at'))}",
    ]

    if required_balance > 0:
        lines.append(f"💵 مبلغ مورد نیاز برای تکمیل: {format_price(required_balance)} تومان")
    else:
        lines.append("✅ موجودی فعلی شما برای این تمدید کافی است و به‌زودی خودکار اعمال می‌شود.")

    lines.extend([
        "",
        "اگر پرداختی انجام دهید، همین تمدید برای همین سرویس اعمال می‌شود.",
        "اگر منصرف شده‌اید، از دکمه لغو استفاده کنید.",
    ])

    cards_text = build_cards_text()
    if required_balance > 0 and cards_text:
        lines.extend([
            "",
            "برای تکمیل پرداخت می‌توانید مبلغ را به یکی از کارت‌های زیر واریز و رسید را ارسال کنید:",
            cards_text,
        ])

    return "\n".join(lines)


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
    await message.answer("بازگشت به منوی اصلی", reply_markup=main_menu_keyboard_for_user(message.chat.id))


# ---------------- FSM States ---------------- #
class RenewStates(StatesGroup):
    choosing_service = State()
    choosing_category = State()
    choosing_location = State()
    choosing_plan = State()
    confirming = State()


# ---------------- Keyboards (Renew namespace) ---------------- #
def kb_services_inline(services: List[Dict[str, Any]]) -> InlineKeyboardMarkup:
    rows = [[InlineKeyboardButton(text=pending_service_button_text(s), callback_data=f"renew|service|{s['id']}")] for s in services]
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
    current_balance = int(get_user_balance(user_id) or 0)
    renew_plans = get_renew_plans(user_id=user_id)
    active_plans = [p for p in renew_plans if _is_active(p)]
    services = get_services_for_renew(user_id)
    pending_services = get_pending_renewal_services(services)

    last_name = message.from_user.last_name
    if last_name:
        update_last_name(user_id=user_id, last_name=last_name)

    if not active_plans and not pending_services:
        await state.clear()
        return await message.answer(
            "در حال حاضر پلن فعالی برای تمدید موجود نیست.",
            reply_markup=main_menu_keyboard_for_user(user_id)
        )

    if not services:
        return await message.answer(get_renew_no_services_text(), reply_markup=main_menu_keyboard_for_user(user_id))

    restricted_to_pending = (
        is_renew_funded_only_mode()
        and bool(pending_services)
        and current_balance < get_min_active_plan_price(active_plans)
    )
    services_to_show = pending_services if restricted_to_pending else services
    prompt_text = (
        "در حال حاضر فقط تمدیدهای در انتظار پرداختت را می‌توانی مدیریت کنی.\n"
        "سرویسی را انتخاب کن:"
        if restricted_to_pending
        else "لطفاً سرویسی که می‌خواهید تمدید کنید را انتخاب کنید:"
    )

    await state.clear()
    await state.update_data(services=services_to_show)
    await state.set_state(RenewStates.choosing_service)
    return await message.answer(
        prompt_text,
        reply_markup=kb_services_inline(services_to_show)
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

    if selected_service.get("status") == "waiting_for_renewal_not_paid":
        pending_order = get_pending_renewal_order(selected_service["id"])
        if not pending_order:
            return await callback.answer("تمدید در انتظار پرداخت برای این سرویس پیدا نشد.", show_alert=True)

        user_balance = get_user_balance(callback.from_user.id)
        await state.set_state(RenewStates.choosing_service)
        return await callback.message.edit_text(
            build_pending_renewal_text(selected_service, pending_order, user_balance),
            parse_mode="HTML",
            reply_markup=keyboard_pending_renewal_actions(selected_service["id"]),
        )

    renew_plans = get_renew_plans(user_id=callback.from_user.id)
    kind, markup, only_category, plans_for_only_category = make_initial_renew_keyboard(renew_plans)

    if kind == "plans" and only_category == "fixed_ip":
        await state.update_data(category="fixed_ip")
        available_locations = get_active_locations_by_category(
            "fixed_ip",
            user_id=callback.from_user.id,
            display_context="renew",
        )
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
        + volume_policy_text()
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
            p for p in get_renew_plans(user_id=callback.from_user.id)
            if normalize_category(p.get("category")) == category and _is_active(p)
        ]
        await state.set_state(RenewStates.choosing_plan)
        text = (
            "لطفاً پلن تمدید را انتخاب کنید:\n"
            + volume_policy_text()
        )
        return await callback.message.edit_text(text, reply_markup=keyboard_durations(plans, prefix="renew"))

    elif category == "fixed_ip":
        available_locations = get_active_locations_by_category(
            category,
            user_id=callback.from_user.id,
            display_context="renew",
        )
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
        p for p in get_renew_plans(user_id=callback.from_user.id)
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
        + volume_policy_text()
    )
    return await callback.message.edit_text(text,
                                            reply_markup=keyboard_durations(plans, back_to="location", prefix="renew"))


# ---------------- Step 4: Choose Plan ---------------- #
@router.callback_query(F.data.startswith("renew|plan"))
async def renew_choose_plan(callback: CallbackQuery, state: FSMContext):
    if not await ensure_renew_enabled_callback(callback, state):
        return
    _, _, plan_id = callback.data.split("|")
    plans = get_renew_plans(user_id=callback.from_user.id)
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
        volume_policy_text(),
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
        return await callback.message.answer("بازگشت به منوی اصلی", reply_markup=main_menu_keyboard_for_user(callback.from_user.id))

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
        cards_text = build_cards_text()

        text_user = (
            f"⏳ تمدید این سرویس ثبت شد و تا 24 ساعت در انتظار پرداخت می‌ماند.\n\n"
            f"👤 نام کاربری: <code>{service_username}</code>\n"
            f"📦 پلن تمدید: {plan_name}\n"
            f"💰 مبلغ تمدید: {format_price(plan_price)} تومان\n"
            f"💳 موجودی فعلی شما: {format_price(current_balance)} تومان\n"
            f"💵 مبلغ مورد نیاز: {format_price(required_balanace)} تومان\n\n"
            f"{cards_text}\n\n"
            f"⚠️ اگر پرداختی انجام دهید، همین تمدید برای همین سرویس اعمال می‌شود.\n"
            f"⚠️ اگر تا 24 ساعت پرداخت نکنید، این درخواست تمدید خودکار لغو می‌شود."
        )
        await callback.message.answer(
            text=text_user,
            parse_mode="HTML",
            reply_markup=main_menu_keyboard_for_user(callback.from_user.id),
        )
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
                f"💰 موجودی: {format_price(new_balance)} تومان\n"
                + volume_policy_alert(),
                parse_mode="Markdown"
            )
            await callback.message.answer("بازگشت به منوی اصلی", reply_markup=main_menu_keyboard_for_user(callback.from_user.id))
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
            "✅ تمدید شما ثبت شد و پس از پایان دوره‌ی فعلی به‌صورت خودکار اعمال می‌شود.\n"
            "برای فعال‌سازی سرویس جدید پیش از موعد، از منوی ربات گزینه «🚀 فعال‌سازی سرویس ذخیره» را بزنید.\n\n"
            + volume_policy_alert()
        )
        await callback.message.answer("بازگشت به منوی اصلی", reply_markup=main_menu_keyboard_for_user(callback.from_user.id))
        await state.clear()


@router.callback_query(F.data.startswith("renew|pending_cancel|"))
async def cancel_pending_renewal(callback: CallbackQuery, state: FSMContext):
    parts = callback.data.split("|")
    service_id = int(parts[2])

    base_service = get_order_data(service_id)
    pending_order = get_pending_renewal_order(service_id)

    if not base_service or not pending_order:
        return await callback.answer("تمدید در انتظار پرداخت پیدا نشد.", show_alert=True)

    if base_service.get("user_id") != callback.from_user.id or pending_order.get("user_id") != callback.from_user.id:
        return await callback.answer("این تمدید برای شما نیست.", show_alert=True)

    restored_status = "expired" if is_service_expired_now(base_service) else "active"
    update_order_status(order_id=base_service["id"], new_status=restored_status)
    update_order_status(order_id=pending_order["id"], new_status="canceled")

    await state.clear()
    await callback.message.edit_text(
        f"✅ تمدید در انتظار پرداخت برای سرویس <code>{base_service['username']}</code> لغو شد.",
        parse_mode="HTML",
    )
    await callback.message.answer("بازگشت به منوی اصلی", reply_markup=main_menu_keyboard_for_user(callback.from_user.id))
    await callback.answer("تمدید لغو شد.")


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
        all_plans = get_renew_plans(user_id=callback.from_user.id)
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
                available_locations = get_active_locations_by_category(
                    "fixed_ip",
                    user_id=callback.from_user.id,
                    display_context="renew",
                )
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
                + volume_policy_text()
            )
            return await callback.message.edit_text(text, reply_markup=markup)

    if target == "location":
        category = data.get("category") or "fixed_ip"
        await state.set_state(RenewStates.choosing_location)
        available_locations = get_active_locations_by_category(
            category,
            user_id=callback.from_user.id,
            display_context="renew",
        )
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
                p for p in get_renew_plans(user_id=callback.from_user.id)
                if normalize_category(p.get("category")) == category and _is_active(p)
            ]
            await state.set_state(RenewStates.choosing_plan)
            text = (
                "لطفاً پلن تمدید را انتخاب کنید:\n"
                + volume_policy_text()
            )
            return await callback.message.edit_text(text, reply_markup=keyboard_durations(plans, prefix="renew"))

        elif category == "fixed_ip" and location:
            plans = [
                p for p in get_renew_plans(user_id=callback.from_user.id)
                if
                p.get("location") == location and normalize_category(p.get("category")) == "fixed_ip" and _is_active(p)
            ]
            await state.set_state(RenewStates.choosing_plan)
            text = (
                "لطفاً پلن تمدید را انتخاب کنید:\n"
                + volume_policy_text()
            )
            return await callback.message.edit_text(text, reply_markup=keyboard_durations(plans, back_to="location",
                                                                                          prefix="renew"))

        # fallback به ورودی
        all_plans = get_renew_plans(user_id=callback.from_user.id)
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
                available_locations = get_active_locations_by_category(
                    "fixed_ip",
                    user_id=callback.from_user.id,
                    display_context="renew",
                )
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
                + volume_policy_text()
            )
            return await callback.message.edit_text(text, reply_markup=markup)
    return
