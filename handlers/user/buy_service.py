# handlers/user/buy_service.py

import re
from typing import Optional, List, Dict, Tuple, Union

from aiogram import Router, F
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import StatesGroup, State
from aiogram.types import Message, CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup

from config import ADMINS
from handlers.user.start import is_user_member, join_channel_keyboard
from keyboards.main_menu import main_menu_keyboard_for_user
from services.admin_notifier import send_message_to_admins
from services.IBSng import change_group
from services.db import (
    ensure_user_exists,
    add_user,
    get_buy_plans,
    insert_order,
    get_user_balance,
    find_free_account,
    update_user_balance,
    assign_account_to_order,
    get_active_locations_by_category,
    update_last_name, get_active_cards,
    count_user_active_orders,
    get_user_max_active_accounts,
    get_user_pending_purchase_orders,
    get_order_data,
    release_account_by_username,
    cancel_unpaid_order,
)
from services.runtime_settings import get_access_mode_setting, get_bool_setting, get_text_setting
from services.payment_workflow import format_card_number_for_display
from services.usage_policy import get_volume_policy_alert, get_volume_policy_text

router = Router()

DEFAULT_MEMBERSHIP_REQUIRED_TEXT = "🔒 برای استفاده از این بخش باید عضو کانال PersiaPro باشید."
DEFAULT_BUY_DISABLED_TEXT = "در حال حاضر فروش سرویس جدید غیر فعال می باشد."
DEFAULT_BUY_NO_ACTIVE_PLANS_TEXT = "در حال حاضر پلن فعالی برای فروش موجود نیست."
def volume_policy_text() -> str:
    return get_volume_policy_text()


def volume_policy_alert() -> str:
    return get_volume_policy_alert()


def is_buy_enabled() -> bool:
    return get_bool_setting("feature_buy_enabled", default=False)


def get_buy_access_mode() -> str:
    return get_access_mode_setting("feature_buy_access_mode", default="funded_only")


def is_buy_funded_only_mode() -> bool:
    return get_buy_access_mode() == "funded_only"


def get_membership_required_text() -> str:
    return get_text_setting("message_membership_required", DEFAULT_MEMBERSHIP_REQUIRED_TEXT)


def get_buy_disabled_text() -> str:
    return get_text_setting("message_buy_disabled", DEFAULT_BUY_DISABLED_TEXT)


def get_buy_no_active_plans_text() -> str:
    return get_text_setting("message_buy_no_active_plans", DEFAULT_BUY_NO_ACTIVE_PLANS_TEXT)


def build_buy_access_blocked_text(current_balance: int, min_price: int) -> str:
    _ = current_balance, min_price
    return "در حال حاضر امکان خرید سرویس فعال نیست."


def get_buy_access_block_message(user_id: int) -> Optional[str]:
    if not is_buy_enabled():
        return get_buy_disabled_text()

    buy_plans = get_buy_plans(user_id=user_id)
    active_plans = [plan for plan in buy_plans if _is_active(plan)]
    if not active_plans:
        return None

    if not is_buy_funded_only_mode():
        return None

    if get_user_pending_purchase_orders(user_id):
        return None

    current_balance = int(get_user_balance(user_id) or 0)
    min_price = get_min_active_plan_price(active_plans)
    if current_balance >= min_price:
        return None

    return build_buy_access_blocked_text(current_balance, min_price)


async def ensure_buy_enabled_message(message: Message, state: FSMContext) -> bool:
    blocked_text = get_buy_access_block_message(message.from_user.id)
    if blocked_text is None:
        return True

    await state.clear()
    await message.answer(blocked_text, reply_markup=main_menu_keyboard_for_user(message.from_user.id))
    return False


async def ensure_buy_enabled_callback(callback: CallbackQuery, state: FSMContext) -> bool:
    blocked_text = get_buy_access_block_message(callback.from_user.id)
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


def build_pending_purchase_text(pending_orders: List[Dict], user_balance: int) -> str:
    lines = [
        "⏳ شما یک خرید در انتظار پرداخت دارید.",
        "تا زمانی که این سفارش را پرداخت یا لغو نکنید، خرید جدید ثبت نمی‌شود.",
        "",
    ]

    for order in pending_orders:
        price = int(order.get("price") or 0)
        required_balance = max(price - int(user_balance or 0), 0)
        lines.extend([
            f"🆔 سفارش: {order['id']}",
            f"🔸 پلن: {order.get('plan_name') or 'نامشخص'}",
            f"👤 نام کاربری رزروشده: <code>{order['username']}</code>",
            f"💰 مبلغ سرویس: {format_price(price)} تومان",
            f"💳 موجودی فعلی شما: {format_price(user_balance)} تومان",
            f"🕒 زمان ثبت: {format_created_at(order.get('created_at'))}",
        ])
        if required_balance > 0:
            lines.append(f"💵 مبلغ مورد نیاز برای تکمیل: {format_price(required_balance)} تومان")
        else:
            lines.append("✅ موجودی فعلی شما برای این سفارش کافی است و به‌زودی خودکار فعال می‌شود.")
        lines.append("")

    cards_text = build_cards_text()
    if cards_text:
        lines.extend([
            "برای تکمیل پرداخت می‌توانید مبلغ را به یکی از کارت‌های زیر واریز و رسید را ارسال کنید:",
            cards_text,
            "",
        ])

    lines.append("اگر منصرف شده‌اید، از دکمه لغو همین سفارش استفاده کنید.")
    return "\n".join(lines)


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


def keyboard_pending_purchase_actions(pending_orders: List[Dict]) -> InlineKeyboardMarkup:
    rows = []
    for order in pending_orders:
        rows.append([
            InlineKeyboardButton(
                text=f"❌ لغو خرید {order['username']}",
                callback_data=f"buy|pending_cancel|{order['id']}"
            )
        ])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def make_initial_buy_keyboard(all_plans: List[Dict]) -> Tuple[str, InlineKeyboardMarkup, Optional[str], List[Dict]]:
    active_plans = [p for p in all_plans if _is_active(p)]
    categories_set = {normalize_category(p.get("category")) for p in active_plans}
    categories = _sort_categories(list(categories_set))

    if len(categories) <= 1:
        only_cat = categories[0] if categories else None
        plans_for_cat = [p for p in active_plans if normalize_category(p.get("category")) == (only_cat or "standard")]
        return "plans", keyboard_durations(plans_for_cat, back_to="category", show_back=False), only_cat, plans_for_cat

    return "categories", keyboard_categories(categories), None, []


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
        return "در حال حاضر پلن فعالی موجود نیست."

    lines = ["📋 لیست پلن‌های فعال:"]
    for plan in active_plans:
        name = plan.get("name", "بدون نام")
        price = format_price(plan.get("price", 0))
        lines.append(f"• {name} — {price} تومان")

    return "\n".join(lines)


# ---------------- Helpers ---------------- #

async def edit_then_show_main_menu(
        message: Message,
        user_id: int,
        text: str,
        *,
        parse_mode: Optional[str] = None
):
    await message.edit_text(text, parse_mode=parse_mode)
    await message.answer("بازگشت به منوی اصلی", reply_markup=main_menu_keyboard_for_user(user_id))


# ---------------- FSM States ---------------- #

class BuyServiceStates(StatesGroup):
    choosing_category = State()
    choosing_location = State()
    choosing_duration = State()
    confirming = State()


# ---------------- Step 0: Entry ---------------- #

@router.message(F.text == "🛒 خرید")
async def start_buy(message: Message, state: FSMContext):
    if not await membership_guard_message(message):
        return
    if not await ensure_buy_enabled_message(message, state):
        return

    user_id = message.from_user.id
    first_name = message.from_user.first_name
    last_name = message.from_user.last_name
    username = message.from_user.username
    role = "admin" if user_id in ADMINS else "user"

    if last_name:
        update_last_name(user_id=user_id, last_name=last_name)

    if not ensure_user_exists(user_id=user_id):
        add_user(user_id, first_name, username, role)

    pending_purchase_orders = get_user_pending_purchase_orders(user_id)
    if pending_purchase_orders:
        await state.clear()
        user_balance = get_user_balance(user_id)
        return await message.answer(
            build_pending_purchase_text(pending_purchase_orders, user_balance),
            parse_mode="HTML",
            reply_markup=keyboard_pending_purchase_actions(pending_purchase_orders),
        )

    active_orders_count = count_user_active_orders(user_id)
    max_active_accounts = get_user_max_active_accounts(user_id)

    if active_orders_count >= max_active_accounts:
        await state.clear()
        return await message.answer(
            "🚫 امکان خرید سرویس جدید برای شما وجود ندارد.\n\n"
            f"شما هم‌اکنون {active_orders_count} اکانت فعال دارید.\n"
            f"📌 سقف مجاز خرید برای شما: {max_active_accounts} اکانت\n\n"
            "برای خرید مجدد، ابتدا باید یکی از اکانت‌های فعال شما آزاد شود.",
            reply_markup=main_menu_keyboard_for_user(user_id)
        )

    buy_plans = get_buy_plans(user_id=user_id)
    active_plans = [p for p in buy_plans if _is_active(p)]

    if not active_plans:
        await state.clear()
        return await message.answer(
            get_buy_no_active_plans_text(),
            reply_markup=main_menu_keyboard_for_user(user_id)
        )

    kind, markup, only_category, _plans_for_only_category = make_initial_buy_keyboard(active_plans)

    if kind == "categories":
        await state.set_state(BuyServiceStates.choosing_category)
        await message.answer("لطفاً نوع سرویس مورد نظر خود را انتخاب کنید:", reply_markup=markup)
        return

    if only_category:
        await state.update_data(category=only_category)

    await state.set_state(BuyServiceStates.choosing_duration)
    text = (
        "🛒 مدت زمان سرویس را انتخاب کنید:\n\n"
        "🚨 توجه قبل از خرید\n"
        f"حداکثر تعداد اکانت فعال مجاز برای شما: {max_active_accounts} عدد\n"
        f"📦 تعداد اکانت فعال فعلی شما: {active_orders_count} عدد\n\n"
        + volume_policy_text()
    )
    await message.answer(text, reply_markup=markup)


# ---------------- Step 1: Choose Category ---------------- #

@router.callback_query(F.data.startswith("buy|category"))
async def choose_category(callback: CallbackQuery, state: FSMContext):
    if not await ensure_buy_enabled_callback(callback, state):
        return
    _, _, category_raw = callback.data.split("|")
    category = normalize_category(category_raw)
    await state.update_data(category=category)

    plans = [
        p for p in get_buy_plans(user_id=callback.from_user.id)
        if normalize_category(p.get("category")) == category and _is_active(p)
    ]

    if category in ("standard", "dual", "custom_location", "modem", "special_access"):
        await state.set_state(BuyServiceStates.choosing_duration)
        text = (
            "مدت زمان سرویس را انتخاب کنید:\n"
            + volume_policy_text()
        )
        return await callback.message.edit_text(text, reply_markup=keyboard_durations(plans))

    elif category == "fixed_ip":
        available_locations = get_active_locations_by_category(
            category,
            user_id=callback.from_user.id,
            display_context="purchase",
        )
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
    if not await ensure_buy_enabled_callback(callback, state):
        return
    _, _, location = callback.data.split("|")
    await state.update_data(location=location)

    plans = [
        p for p in get_buy_plans(user_id=callback.from_user.id)
        if p.get("location") == location
           and normalize_category(p.get("category")) == "fixed_ip"
           and _is_active(p)
    ]

    await state.set_state(BuyServiceStates.choosing_duration)
    text = (
        "مدت زمان سرویس را انتخاب کنید:\n"
        + volume_policy_text()
    )
    await callback.message.edit_text(text, reply_markup=keyboard_durations(plans, back_to="location"))


# ---------------- Step 3: Choose Duration ---------------- #

@router.callback_query(F.data.startswith("buy|duration"))
async def choose_duration(callback: CallbackQuery, state: FSMContext):
    if not await ensure_buy_enabled_callback(callback, state):
        return
    _, _, plan_id = callback.data.split("|")
    plans = get_buy_plans(user_id=callback.from_user.id)
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
        volume_policy_text(),
        "",
        "لطفاً تایید کنید:",
    ]
    return await callback.message.edit_text("\n".join(summary), reply_markup=keyboard_confirm())


# ---------------- Step 4: Confirm ---------------- #

@router.callback_query(F.data == "buy|confirm")
async def confirm_and_create(callback: CallbackQuery, state: FSMContext):
    if not await ensure_buy_enabled_callback(callback, state):
        return
    data = await state.get_data()
    plan = data.get("plan")

    if not plan:
        await state.clear()
        return await edit_then_show_main_menu(callback.message, callback.from_user.id, "خطا در دریافت اطلاعات پلن. دوباره تلاش کنید.")

    user_id = callback.from_user.id
    first_name = callback.from_user.first_name
    last_name = callback.from_user.last_name

    pending_purchase_orders = get_user_pending_purchase_orders(user_id)
    if pending_purchase_orders:
        await state.clear()
        user_balance = get_user_balance(user_id)
        return await callback.message.answer(
            build_pending_purchase_text(pending_purchase_orders, user_balance),
            parse_mode="HTML",
            reply_markup=keyboard_pending_purchase_actions(pending_purchase_orders),
        )

    user_balance = get_user_balance(user_id)
    if user_balance < plan["price"]:
        free_account = find_free_account()
        if not free_account:
            await state.clear()
            return await edit_then_show_main_menu(callback.message, callback.from_user.id, "اکانت آزاد موجود نیست ❌")

        account_id, account_username, _account_password = free_account
        required_balanace = plan["price"] - user_balance
        cards_text = build_cards_text()

        try:
            order_id = insert_order(
                user_id=user_id,
                plan_id=plan["id"],
                username=account_username,
                price=plan["price"],
                status="waiting_for_payment",
                volume_gb=plan.get("volume_gb"),
            )
            assign_account_to_order(account_id, order_id)
        except Exception as e:
            print(f"خطا در ثبت خرید در انتظار پرداخت: {e}")
            await state.clear()
            return await edit_then_show_main_menu(callback.message, callback.from_user.id, "❌ خطایی در ثبت سفارش رخ داد.")

        text_user = (
            f"⏳ سفارش شما ثبت شد و اکانت تا 24 ساعت برایتان رزرو شد.\n\n"
            f"🔸 پلن: {plan['name']}\n"
            f"👤 نام کاربری رزروشده: <code>{account_username}</code>\n"
            f"💰 مبلغ سرویس: {format_price(plan['price'])} تومان\n"
            f"💳 موجودی فعلی شما: {format_price(user_balance)} تومان\n"
            f"💵 مبلغ مورد نیاز: {format_price(required_balanace)} تومان\n\n"
            f"{cards_text}\n\n"
            f"⚠️ پس از تایید پرداخت، همین سرویس به‌صورت خودکار برای شما فعال می‌شود.\n"
            f"⚠️ اگر تا 24 ساعت پرداخت نکنید، سفارش لغو و این اکانت دوباره آزاد می‌شود."
        )
        text_admin = (
            "🔔 درخواست خرید جدید ثبت شد (در انتظار پرداخت)\n"
            f"📥 کاربر <a href='tg://user?id={user_id}'>{user_id} {first_name} {last_name or ' '}</a>\n"
            f"📦 پلن: {plan['name']}\n"
            f"👤 نام کاربری رزروشده: <code>{account_username}</code>\n"
            f"💳 مبلغ: {format_price(plan['price'])} تومان\n"
            f"🟡 وضعیت: در انتظار پرداخت"
        )
        await send_message_to_admins(text_admin)
        await state.clear()
        return await callback.message.answer(
            text=text_user,
            parse_mode="HTML",
            reply_markup=main_menu_keyboard_for_user(callback.from_user.id),
        )

    free_account = find_free_account()
    if not free_account:
        await state.clear()
        return await edit_then_show_main_menu(callback.message, callback.from_user.id, "اکانت آزاد موجود نیست ❌")

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
        assign_account_to_order(account_id, order_id)
    except Exception as e:
        print(f"خطا در درج سفارش: {e}")
        await state.clear()
        return await edit_then_show_main_menu(callback.message, callback.from_user.id, "❌ خطایی در ثبت سفارش رخ داد.")

    change_group(username=account_username, group=plan["group_name"])

    new_balance = user_balance - plan["price"]
    update_user_balance(user_id, new_balance)

    await callback.message.answer(
        f"✅ سرویس شما فعال شد!\n\n"
        f"🔸 پلن: {plan['name']}\n"
        f"📦 {fair_usage_label(plan)}\n"
        f"👤 نام کاربری: `{account_username}`\n"
        f"🔐 رمز: `{account_password}`\n"
        f"💰 موجودی: {format_price(new_balance)} تومان\n"
        + volume_policy_alert(),
        parse_mode="Markdown",
            reply_markup=main_menu_keyboard_for_user(user_id)
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


@router.callback_query(F.data.startswith("buy|pending_cancel|"))
async def cancel_pending_purchase(callback: CallbackQuery, state: FSMContext):
    _, _, order_id = callback.data.split("|")
    order = get_order_data(int(order_id))

    if not order or order.get("user_id") != callback.from_user.id:
        return await callback.answer("این سفارش برای شما نیست.", show_alert=True)

    if order.get("status") != "waiting_for_payment" or order.get("is_renewal_of_order"):
        return await callback.answer("این سفارش دیگر قابل لغو نیست.", show_alert=True)

    release_account_by_username(str(order["username"]))
    cancel_unpaid_order(order_id=order["id"])
    await state.clear()

    remaining_orders = get_user_pending_purchase_orders(callback.from_user.id)
    if remaining_orders:
        user_balance = get_user_balance(callback.from_user.id)
        await callback.message.edit_text(
            build_pending_purchase_text(remaining_orders, user_balance),
            parse_mode="HTML",
            reply_markup=keyboard_pending_purchase_actions(remaining_orders),
        )
    else:
        await callback.message.edit_text(
            "✅ خرید در انتظار پرداخت لغو شد و اکانت رزروشده دوباره آزاد شد."
        )
        await callback.message.answer("بازگشت به منوی اصلی", reply_markup=main_menu_keyboard_for_user(callback.from_user.id))

    await callback.answer("سفارش لغو شد.")


# ---------------- Back Navigation ---------------- #
@router.callback_query(F.data.startswith("buy|back"))
async def go_back(callback: CallbackQuery, state: FSMContext):
    if not await ensure_buy_enabled_callback(callback, state):
        return
    _, _, target = callback.data.split("|")

    if target == "category":
        # اگر چند دسته داشته‌ایم، دوباره همان لیست را نشان می‌دهیم
        all_plans = get_buy_plans(user_id=callback.from_user.id)
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
                + volume_policy_text()
            )
            return await callback.message.edit_text(text, reply_markup=markup)

    elif target == "location":
        data = await state.get_data()
        category = normalize_category(data.get("category") or "fixed_ip")
        await state.set_state(BuyServiceStates.choosing_location)
        available_locations = get_active_locations_by_category(
            category,
            user_id=callback.from_user.id,
            display_context="purchase",
        )
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

        if category in ("standard", "dual", "custom_location", "modem", "special_access"):
            plans = [
                p for p in get_buy_plans(user_id=callback.from_user.id)
                if normalize_category(p.get("category")) == category and _is_active(p)
            ]
            await state.set_state(BuyServiceStates.choosing_duration)
            text = (
                "مدت زمان سرویس را انتخاب کنید:\n"
                + volume_policy_text()
            )
            return await callback.message.edit_text(text, reply_markup=keyboard_durations(plans))

        elif category == "fixed_ip" and location:
            plans = [
                p for p in get_buy_plans(user_id=callback.from_user.id)
                if p.get("location") == location
                   and normalize_category(p.get("category")) == "fixed_ip"
                   and _is_active(p)
            ]
            await state.set_state(BuyServiceStates.choosing_duration)
            text = (
                "مدت زمان سرویس را انتخاب کنید:\n"
                + volume_policy_text()
            )
            return await callback.message.edit_text(
                text,
                reply_markup=keyboard_durations(plans, back_to="location")
            )

        # اگر هنوز چیزی پیدا نشد، برگرد به مرحلهٔ اول
        all_plans = get_buy_plans(user_id=callback.from_user.id)
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
                + volume_policy_text()
            )
            return await callback.message.edit_text(text, reply_markup=markup)

    return
