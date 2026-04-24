import sqlite3
from typing import Optional, Union

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message

from config import ADMINS, DB_PATH
from keyboards.main_menu import admin_main_menu_keyboard
from services.db import get_plan_info, get_plans_for_admin, set_plan_archived

router = Router()


class PlanStates(StatesGroup):
    waiting_for_value = State()
    waiting_for_add = State()


def is_admin(user_id: int) -> bool:
    return str(user_id) in {str(admin_id) for admin_id in ADMINS}


def format_price(amount: int) -> str:
    try:
        return f"{int(amount):,}"
    except Exception:
        return str(amount)


PLAN_CATEGORY_LABELS = {
    "standard": "عادی",
    "fixed_ip": "آی‌پی ثابت",
    "dual": "دوکاربره",
    "custom_location": "لوکیشن انتخابی",
    "modem": "مودم/روتر",
    "special_access": "دسترسی ویژه",
}

PLAN_CATEGORY_ALIASES = {
    "normal": "standard",
    "default": "standard",
    "regular": "standard",
    "عادی": "standard",
    "استاندارد": "standard",
    "router": "modem",
    "مودم": "modem",
    "روتر": "modem",
    "vip": "special_access",
    "special": "special_access",
    "ویژه": "special_access",
    "خاص": "special_access",
    "fixed": "fixed_ip",
    "آیپی_ثابت": "fixed_ip",
    "آی_پی_ثابت": "fixed_ip",
    "دوکاربره": "dual",
    "دو_کاربره": "dual",
    "لوکیشن_انتخابی": "custom_location",
}

ACCESS_LEVEL_LABELS = {
    "all": "همه کاربران",
    "user": "فقط کاربران عادی",
    "agent": "فقط نماینده‌ها",
    "admin": "فقط ادمین‌ها",
}

DISPLAY_CONTEXT_LABELS = {
    "all": "همه‌جا",
    "purchase": "فقط خرید",
    "renew": "فقط تمدید",
    "agent": "فقط نماینده‌ها",
}

PLAN_FIELD_LABELS = {
    "name": "نام",
    "volume_gb": "حجم",
    "duration_months": "ماه",
    "duration_days": "روز",
    "max_users": "تعداد یوزر",
    "price": "قیمت",
    "order_priority": "اولویت",
    "visible": "نمایش",
    "location": "لوکیشن",
    "is_unlimited": "نامحدود",
    "group_name": "گروه",
    "category": "دسته سرویس",
    "access_level": "سطح دسترسی",
    "display_context": "محل نمایش",
}

PLAN_INTEGER_FIELDS = {
    "volume_gb",
    "duration_months",
    "duration_days",
    "max_users",
    "price",
    "order_priority",
}
PLAN_BOOLEAN_FIELDS = {"visible", "is_unlimited"}
PLAN_NULLABLE_TEXT_FIELDS = {"location", "group_name"}
PLAN_CLEAR_VALUES = {"پاک", "خالی", "-", "none", "null", "clear"}
PLAN_SAFE_EDIT_FIELDS = set(PLAN_FIELD_LABELS)

_DIGIT_TRANSLATION = str.maketrans(
    "۰۱۲۳۴۵۶۷۸۹٠١٢٣٤٥٦٧٨٩",
    "01234567890123456789",
)


def normalize_digits(value: str) -> str:
    return str(value or "").translate(_DIGIT_TRANSLATION)


def normalize_slug(value: Optional[str]) -> str:
    normalized = normalize_digits(value or "").strip().lower().replace("-", "_").replace(" ", "_")
    while "__" in normalized:
        normalized = normalized.replace("__", "_")
    return normalized.strip("_")


def normalize_category(value: Optional[str]) -> str:
    normalized = normalize_slug(value or "standard")
    return PLAN_CATEGORY_ALIASES.get(normalized, normalized)


def category_label(value: Optional[str]) -> str:
    normalized = normalize_category(value)
    return PLAN_CATEGORY_LABELS.get(normalized, normalized or "-")


def access_level_label(value: Optional[str]) -> str:
    normalized = (value or "all").strip().lower()
    return ACCESS_LEVEL_LABELS.get(normalized, ACCESS_LEVEL_LABELS["all"])


def display_context_label(value: Optional[str]) -> str:
    normalized = (value or "all").strip().lower()
    return DISPLAY_CONTEXT_LABELS.get(normalized, DISPLAY_CONTEXT_LABELS["all"])


def parse_bool_value(value: str) -> int:
    normalized = normalize_slug(value)
    if normalized in {"1", "true", "yes", "on", "active", "enabled", "بله", "بلی", "فعال", "روشن", "نامحدود"}:
        return 1
    if normalized in {"0", "false", "no", "off", "inactive", "disabled", "خیر", "نه", "غیرفعال", "غیر_فعال", "خاموش", "مخفی", "حجمی", "محدود"}:
        return 0
    raise ValueError("برای این فیلد مقدار 1/0، بله/خیر یا فعال/غیرفعال بفرست.")


def parse_plan_field_value(field: str, raw_value: str):
    value_text = (raw_value or "").strip()

    if field == "name":
        if not value_text:
            raise ValueError("نام پلن نمی‌تواند خالی باشد.")
        return value_text

    if field in PLAN_INTEGER_FIELDS:
        try:
            number = int(normalize_digits(value_text))
        except Exception:
            raise ValueError("این فیلد باید عدد صحیح باشد.")
        if number < 0:
            raise ValueError("عدد منفی برای این فیلد معتبر نیست.")
        return number

    if field in PLAN_BOOLEAN_FIELDS:
        return parse_bool_value(value_text)

    if field == "category":
        category = "standard" if value_text in PLAN_CLEAR_VALUES else normalize_category(value_text)
        if category not in PLAN_CATEGORY_LABELS:
            allowed = ", ".join(PLAN_CATEGORY_LABELS)
            raise ValueError(f"دسته معتبر نیست. مقدارهای مجاز: {allowed}")
        return category

    if field == "access_level":
        access_level = (normalize_slug(value_text) or "all")
        if access_level not in ACCESS_LEVEL_LABELS:
            allowed = ", ".join(ACCESS_LEVEL_LABELS)
            raise ValueError(f"سطح دسترسی معتبر نیست. مقدارهای مجاز: {allowed}")
        return access_level

    if field == "display_context":
        display_context = (normalize_slug(value_text) or "all")
        if display_context not in DISPLAY_CONTEXT_LABELS:
            allowed = ", ".join(DISPLAY_CONTEXT_LABELS)
            raise ValueError(f"محل نمایش معتبر نیست. مقدارهای مجاز: {allowed}")
        return display_context

    if field in PLAN_NULLABLE_TEXT_FIELDS:
        return None if value_text in PLAN_CLEAR_VALUES else value_text

    raise ValueError("فیلد نامعتبر است.")


def plan_field_help_lines(field: str) -> list[str]:
    if field in PLAN_BOOLEAN_FIELDS:
        return ["مقدار مجاز: 1 یا 0، بله یا خیر، فعال یا غیرفعال"]
    if field == "category":
        return [
            "مقدارهای مجاز:",
            ", ".join(f"{key} ({label})" for key, label in PLAN_CATEGORY_LABELS.items()),
        ]
    if field == "access_level":
        return [
            "مقدارهای مجاز:",
            ", ".join(f"{key} ({label})" for key, label in ACCESS_LEVEL_LABELS.items()),
        ]
    if field == "display_context":
        return [
            "مقدارهای مجاز:",
            ", ".join(f"{key} ({label})" for key, label in DISPLAY_CONTEXT_LABELS.items()),
        ]
    if field in PLAN_NULLABLE_TEXT_FIELDS:
        return ["برای خالی‌کردن مقدار، «پاک» یا «-» را ارسال کن."]
    if field in PLAN_INTEGER_FIELDS:
        return ["فقط عدد صحیح غیرمنفی قابل قبول است."]
    return []


def update_plan_field(plan_id: int, field: str, value) -> bool:
    if field not in PLAN_SAFE_EDIT_FIELDS:
        return False
    with sqlite3.connect(DB_PATH) as conn:
        cursor = conn.cursor()
        cursor.execute(f"UPDATE plans SET {field} = ? WHERE id = ?", (value, plan_id))
        conn.commit()
        return cursor.rowcount > 0


def add_plan_to_db(
    name: str,
    volume_gb: int,
    duration_months: int,
    duration_days: int,
    max_users: int,
    price: int,
    order_priority: int = 0,
) -> int:
    with sqlite3.connect(DB_PATH) as conn:
        cursor = conn.cursor()
        cursor.execute(
            """
            INSERT INTO plans (
                name,
                volume_gb,
                duration_months,
                duration_days,
                max_users,
                price,
                order_priority,
                visible,
                is_archived,
                access_level,
                display_context
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, 1, 0, 'all', 'all')
            """,
            (name, volume_gb, duration_months, duration_days, max_users, price, order_priority),
        )
        conn.commit()
        return int(cursor.lastrowid)


def delete_plan_from_db(plan_id: int) -> bool:
    with sqlite3.connect(DB_PATH) as conn:
        cursor = conn.cursor()
        cursor.execute("DELETE FROM plan_segments WHERE plan_id = ?", (plan_id,))
        cursor.execute("DELETE FROM plans WHERE id = ?", (plan_id,))
        conn.commit()
        return cursor.rowcount > 0


def plans_list_keyboard(include_archived: bool = False) -> InlineKeyboardMarkup:
    rows = []
    for plan in get_plans_for_admin(include_archived=include_archived):
        visible_icon = "✅" if int(plan.get("visible") or 0) == 1 else "🚫"
        label = f"#{plan['id']} | {visible_icon} {plan['name']} | {format_price(plan['price'])} تومان"
        rows.append([
            InlineKeyboardButton(
                text=label[:64],
                callback_data=f"plan_mgmt|open|{plan['id']}",
            )
        ])

    if include_archived:
        rows.append([InlineKeyboardButton(text="📦 پلن‌های فعال", callback_data="plan_mgmt|list|active")])
    else:
        rows.append([InlineKeyboardButton(text="🗂 پلن‌های آرشیوشده", callback_data="plan_mgmt|list|archived")])
        rows.append([InlineKeyboardButton(text="➕ افزودن پلن جدید", callback_data="plan_mgmt|add")])
    rows.append([InlineKeyboardButton(text="🏠 منوی ادمین", callback_data="plan_mgmt|main")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def plan_detail_keyboard(plan_id: int, archived: bool) -> InlineKeyboardMarkup:
    archive_text = "♻️ خروج از آرشیو" if archived else "🗂 آرشیو پلن"
    list_target = "archived" if archived else "active"
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="✏️ نام", callback_data=f"plan_mgmt|edit|name|{plan_id}")],
            [
                InlineKeyboardButton(text="📦 حجم", callback_data=f"plan_mgmt|edit|volume_gb|{plan_id}"),
                InlineKeyboardButton(text="♾ نامحدود", callback_data=f"plan_mgmt|edit|is_unlimited|{plan_id}"),
            ],
            [
                InlineKeyboardButton(text="🗓 ماه", callback_data=f"plan_mgmt|edit|duration_months|{plan_id}"),
                InlineKeyboardButton(text="📅 روز", callback_data=f"plan_mgmt|edit|duration_days|{plan_id}"),
            ],
            [
                InlineKeyboardButton(text="👥 یوزرها", callback_data=f"plan_mgmt|edit|max_users|{plan_id}"),
                InlineKeyboardButton(text="💰 قیمت", callback_data=f"plan_mgmt|edit|price|{plan_id}"),
            ],
            [
                InlineKeyboardButton(text="🔢 اولویت", callback_data=f"plan_mgmt|edit|order_priority|{plan_id}"),
                InlineKeyboardButton(text="👁 نمایش", callback_data=f"plan_mgmt|edit|visible|{plan_id}"),
            ],
            [
                InlineKeyboardButton(text="🧭 دسته", callback_data=f"plan_mgmt|edit|category|{plan_id}"),
                InlineKeyboardButton(text="📍 لوکیشن", callback_data=f"plan_mgmt|edit|location|{plan_id}"),
            ],
            [InlineKeyboardButton(text="🏷 گروه", callback_data=f"plan_mgmt|edit|group_name|{plan_id}")],
            [
                InlineKeyboardButton(text="👥 سطح دسترسی", callback_data=f"plan_mgmt|edit|access_level|{plan_id}"),
                InlineKeyboardButton(text="🛒 محل نمایش", callback_data=f"plan_mgmt|edit|display_context|{plan_id}"),
            ],
            [InlineKeyboardButton(text="✅/🚫 نمایش", callback_data=f"plan_mgmt|toggle|{plan_id}")],
            [InlineKeyboardButton(text=archive_text, callback_data=f"plan_mgmt|archive|{plan_id}")],
            [InlineKeyboardButton(text="🗑 حذف کامل", callback_data=f"plan_mgmt|delete|{plan_id}")],
            [InlineKeyboardButton(text="🔙 بازگشت", callback_data=f"plan_mgmt|list|{list_target}")],
        ]
    )


def build_plan_caption(plan: dict) -> str:
    return (
        f"📦 پلن #{plan['id']}\n"
        f"نام: {plan.get('name') or '-'}\n"
        f"حجم: {plan.get('volume_gb') or 0} گیگ\n"
        f"مدت: {plan.get('duration_months') or 0} ماه / {plan.get('duration_days') or 0} روز\n"
        f"یوزر: {plan.get('max_users') or 0}\n"
        f"قیمت: {format_price(plan.get('price') or 0)} تومان\n"
        f"اولویت: {plan.get('order_priority') or 0}\n"
        f"نمایش: {'فعال' if int(plan.get('visible') or 0) == 1 else 'مخفی'}\n"
        f"آرشیو: {'بله' if int(plan.get('is_archived') or 0) == 1 else 'خیر'}\n"
        f"زمان آرشیو: {plan.get('archived_at') or '-'}\n"
        f"دسته: {category_label(plan.get('category'))} ({plan.get('category') or 'standard'})\n"
        f"سطح دسترسی: {access_level_label(plan.get('access_level'))} ({plan.get('access_level') or 'all'})\n"
        f"محل نمایش: {display_context_label(plan.get('display_context'))} ({plan.get('display_context') or 'all'})\n"
        f"گروه: {plan.get('group_name') or '-'}\n"
        f"لوکیشن: {plan.get('location') or '-'}\n"
        f"نامحدود: {'بله' if int(plan.get('is_unlimited') or 0) == 1 else 'خیر'}"
    )


async def show_plans_list(target: Union[Message, CallbackQuery], include_archived: bool = False):
    text = "📦 پلن‌های آرشیوشده:" if include_archived else "📦 پلن‌های فعال:"
    keyboard = plans_list_keyboard(include_archived=include_archived)
    if isinstance(target, Message):
        await target.answer(text, reply_markup=keyboard)
    else:
        await target.message.answer(text, reply_markup=keyboard)
        await target.answer()


@router.message(F.text == "📦 مدیریت پلن‌ها")
async def manage_plans_entry(message: Message, state: FSMContext):
    if not is_admin(message.from_user.id):
        return
    await state.clear()
    await show_plans_list(message, include_archived=False)


@router.callback_query(F.data == "manage_plans")
async def manage_plans_callback(callback: CallbackQuery, state: FSMContext):
    if not is_admin(callback.from_user.id):
        return await callback.answer("دسترسی نداری.", show_alert=True)
    await state.clear()
    await show_plans_list(callback, include_archived=False)


@router.callback_query(F.data == "plan_mgmt|main")
async def plan_back_main(callback: CallbackQuery, state: FSMContext):
    if not is_admin(callback.from_user.id):
        return await callback.answer("دسترسی نداری.", show_alert=True)
    await state.clear()
    await callback.message.answer("بازگشت به منوی ادمین.", reply_markup=admin_main_menu_keyboard())
    await callback.answer()


@router.callback_query(F.data.startswith("plan_mgmt|list|"))
async def plan_list_callback(callback: CallbackQuery, state: FSMContext):
    if not is_admin(callback.from_user.id):
        return await callback.answer("دسترسی نداری.", show_alert=True)
    await state.clear()
    include_archived = callback.data.endswith("|archived")
    await show_plans_list(callback, include_archived=include_archived)


@router.callback_query(F.data == "plan_mgmt|add")
async def plan_add_start(callback: CallbackQuery, state: FSMContext):
    if not is_admin(callback.from_user.id):
        return await callback.answer("دسترسی نداری.", show_alert=True)
    await state.set_state(PlanStates.waiting_for_add)
    await callback.message.answer(
        "فرمت افزودن پلن:\n"
        "نام | حجم گیگ | ماه | روز | تعداد یوزر | قیمت | اولویت اختیاری\n\n"
        "مثال:\n"
        "۳۰ روزه | 40 | 1 | 30 | 1 | 100000 | 0"
    )
    await callback.answer()


@router.message(PlanStates.waiting_for_add)
async def plan_add_receive(message: Message, state: FSMContext):
    if not is_admin(message.from_user.id):
        await state.clear()
        return

    parts = [part.strip() for part in (message.text or "").split("|")]
    if len(parts) < 6:
        await message.answer("فرمت درست نیست. نام، حجم، ماه، روز، یوزر و قیمت لازم است.")
        return

    try:
        add_plan_to_db(
            name=parts[0],
            volume_gb=int(parts[1]),
            duration_months=int(parts[2]),
            duration_days=int(parts[3]),
            max_users=int(parts[4]),
            price=int(parts[5]),
            order_priority=int(parts[6]) if len(parts) >= 7 and parts[6] else 0,
        )
    except Exception:
        await message.answer("مقادیر عددی پلن درست نیستند.")
        return

    await state.clear()
    await message.answer("✅ پلن جدید اضافه شد.", reply_markup=plans_list_keyboard(include_archived=False))


@router.callback_query(F.data.startswith("plan_mgmt|open|"))
async def plan_open(callback: CallbackQuery, state: FSMContext):
    if not is_admin(callback.from_user.id):
        return await callback.answer("دسترسی نداری.", show_alert=True)
    plan_id = int(callback.data.split("|")[2])
    plan = get_plan_info(plan_id)
    if not plan:
        return await callback.answer("پلن پیدا نشد.", show_alert=True)
    await state.clear()
    await callback.message.answer(
        build_plan_caption(plan),
        reply_markup=plan_detail_keyboard(plan_id, archived=bool(plan.get("is_archived"))),
    )
    await callback.answer()


@router.callback_query(F.data.startswith("plan_mgmt|toggle|"))
async def plan_toggle(callback: CallbackQuery, state: FSMContext):
    if not is_admin(callback.from_user.id):
        return await callback.answer("دسترسی نداری.", show_alert=True)
    plan_id = int(callback.data.split("|")[2])
    plan = get_plan_info(plan_id)
    if not plan:
        return await callback.answer("پلن پیدا نشد.", show_alert=True)
    new_visible = 0 if int(plan.get("visible") or 0) == 1 else 1
    update_plan_field(plan_id, "visible", new_visible)
    updated = get_plan_info(plan_id)
    await state.clear()
    await callback.message.answer("✅ وضعیت نمایش پلن تغییر کرد.")
    if updated:
        await callback.message.answer(
            build_plan_caption(updated),
            reply_markup=plan_detail_keyboard(plan_id, archived=bool(updated.get("is_archived"))),
        )
    await callback.answer()


@router.callback_query(F.data.startswith("plan_mgmt|archive|"))
async def plan_archive(callback: CallbackQuery, state: FSMContext):
    if not is_admin(callback.from_user.id):
        return await callback.answer("دسترسی نداری.", show_alert=True)
    plan_id = int(callback.data.split("|")[2])
    plan = get_plan_info(plan_id)
    if not plan:
        return await callback.answer("پلن پیدا نشد.", show_alert=True)

    archived = not bool(plan.get("is_archived"))
    set_plan_archived(plan_id, archived=archived)
    await state.clear()
    await callback.message.answer("✅ وضعیت آرشیو پلن تغییر کرد.")
    await show_plans_list(callback.message, include_archived=archived)
    await callback.answer()


@router.callback_query(F.data.startswith("plan_mgmt|delete|"))
async def plan_delete(callback: CallbackQuery, state: FSMContext):
    if not is_admin(callback.from_user.id):
        return await callback.answer("دسترسی نداری.", show_alert=True)
    plan_id = int(callback.data.split("|")[2])
    delete_plan_from_db(plan_id)
    await state.clear()
    await callback.message.answer("🗑 پلن حذف شد.")
    await show_plans_list(callback.message, include_archived=False)
    await callback.answer()


@router.callback_query(F.data.startswith("plan_mgmt|edit|"))
async def plan_edit_start(callback: CallbackQuery, state: FSMContext):
    if not is_admin(callback.from_user.id):
        return await callback.answer("دسترسی نداری.", show_alert=True)
    _, _, field, plan_id = callback.data.split("|", 3)
    if field not in PLAN_FIELD_LABELS:
        return await callback.answer("فیلد نامعتبر است.", show_alert=True)
    plan = get_plan_info(int(plan_id))
    if not plan:
        return await callback.answer("پلن پیدا نشد.", show_alert=True)

    await state.update_data(edit_plan_id=int(plan_id), edit_plan_field=field)
    await state.set_state(PlanStates.waiting_for_value)
    current_value = plan.get(field)
    prompt_lines = [
        f"مقدار جدید برای «{PLAN_FIELD_LABELS[field]}» را بفرست:",
        "",
        f"مقدار فعلی: {current_value if current_value not in (None, '') else '-'}",
    ]
    help_lines = plan_field_help_lines(field)
    if help_lines:
        prompt_lines.extend(["", *help_lines])
    prompt_lines.extend(["", "برای لغو، «لغو» را ارسال کن."])
    await callback.message.answer("\n".join(prompt_lines))
    await callback.answer()


@router.message(PlanStates.waiting_for_value)
async def plan_receive_new_value(message: Message, state: FSMContext):
    if not is_admin(message.from_user.id):
        await state.clear()
        return

    data = await state.get_data()
    plan_id = data.get("edit_plan_id")
    field = data.get("edit_plan_field")
    if not plan_id or not field:
        await state.clear()
        await message.answer("خطای وضعیت. دوباره تلاش کن.")
        return

    value_text = (message.text or "").strip()
    if value_text in {"لغو", "انصراف"}:
        await state.clear()
        plan = get_plan_info(int(plan_id))
        if plan:
            await message.answer(
                build_plan_caption(plan),
                reply_markup=plan_detail_keyboard(int(plan_id), archived=bool(plan.get("is_archived"))),
            )
        else:
            await message.answer("ویرایش لغو شد.", reply_markup=plans_list_keyboard(include_archived=False))
        return

    try:
        value = parse_plan_field_value(str(field), value_text)
    except ValueError as exc:
        await message.answer(str(exc))
        return

    ok = update_plan_field(int(plan_id), field, value)
    await state.clear()
    if ok:
        updated = get_plan_info(int(plan_id))
        await message.answer("✅ پلن بروزرسانی شد.")
        if updated:
            await message.answer(
                build_plan_caption(updated),
                reply_markup=plan_detail_keyboard(int(plan_id), archived=bool(updated.get("is_archived"))),
            )
        else:
            await message.answer("پلن پیدا نشد.", reply_markup=plans_list_keyboard(include_archived=False))
    else:
        await message.answer("❌ بروزرسانی پلن انجام نشد.", reply_markup=plans_list_keyboard(include_archived=False))
