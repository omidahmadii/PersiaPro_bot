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


def update_plan_field(plan_id: int, field: str, value) -> bool:
    allowed_fields = {
        "name",
        "volume_gb",
        "duration_months",
        "duration_days",
        "max_users",
        "price",
        "order_priority",
        "visible",
        "location",
        "is_unlimited",
        "group_name",
    }
    if field not in allowed_fields:
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
            [InlineKeyboardButton(text="📦 حجم", callback_data=f"plan_mgmt|edit|volume_gb|{plan_id}")],
            [InlineKeyboardButton(text="🗓 ماه", callback_data=f"plan_mgmt|edit|duration_months|{plan_id}")],
            [InlineKeyboardButton(text="📅 روز", callback_data=f"plan_mgmt|edit|duration_days|{plan_id}")],
            [InlineKeyboardButton(text="👥 یوزرها", callback_data=f"plan_mgmt|edit|max_users|{plan_id}")],
            [InlineKeyboardButton(text="💰 قیمت", callback_data=f"plan_mgmt|edit|price|{plan_id}")],
            [InlineKeyboardButton(text="🔢 اولویت", callback_data=f"plan_mgmt|edit|order_priority|{plan_id}")],
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
    field_labels = {
        "name": "نام",
        "volume_gb": "حجم",
        "duration_months": "ماه",
        "duration_days": "روز",
        "max_users": "تعداد یوزر",
        "price": "قیمت",
        "order_priority": "اولویت",
    }
    if field not in field_labels:
        return await callback.answer("فیلد نامعتبر است.", show_alert=True)
    await state.update_data(edit_plan_id=int(plan_id), edit_plan_field=field)
    await state.set_state(PlanStates.waiting_for_value)
    await callback.message.answer(f"مقدار جدید برای «{field_labels[field]}» را بفرست:")
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
    value = value_text
    if field in {"volume_gb", "duration_months", "duration_days", "max_users", "price", "order_priority"}:
        try:
            value = int(value_text)
        except Exception:
            await message.answer("این فیلد باید عدد باشد.")
            return

    ok = update_plan_field(int(plan_id), field, value)
    await state.clear()
    if ok:
        await message.answer("✅ پلن بروزرسانی شد.", reply_markup=plans_list_keyboard(include_archived=False))
    else:
        await message.answer("❌ بروزرسانی پلن انجام نشد.", reply_markup=plans_list_keyboard(include_archived=False))
