import re
from typing import Dict, List, Optional, Tuple, Union

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message

from config import ADMINS
from keyboards.main_menu import admin_main_menu_keyboard
from services.db import (
    add_users_to_segment,
    attach_segments_to_plan,
    create_segment,
    delete_segment,
    detach_segments_from_plan,
    get_all_plans_for_admin_audience,
    get_all_segments,
    get_plan_for_admin_audience,
    get_plan_segments,
    get_segment,
    get_segment_plans,
    get_segment_users,
    remove_users_from_segment,
    resolve_user_identifiers,
    set_segment_active,
    update_plan_access_level,
    update_plan_display_context,
    update_segment_info,
)

router = Router()

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


class PlanAudienceStates(StatesGroup):
    waiting_for_new_segment = State()
    waiting_for_segment_edit = State()
    waiting_for_segment_add_users = State()
    waiting_for_segment_remove_users = State()
    waiting_for_plan_attach_segments = State()
    waiting_for_plan_detach_segments = State()


def is_admin(user_id: int) -> bool:
    return str(user_id) in [str(admin_id) for admin_id in ADMINS]


def split_tokens(value: str) -> List[str]:
    return [token.strip() for token in re.split(r"[\s,\n،,]+", value or "") if token.strip()]


def format_price(value: Optional[int]) -> str:
    try:
        return f"{int(value or 0):,}"
    except Exception:
        return str(value or 0)


def get_access_level_label(value: Optional[str]) -> str:
    return ACCESS_LEVEL_LABELS.get((value or "all").strip().lower(), "همه کاربران")


def get_display_context_label(value: Optional[str]) -> str:
    return DISPLAY_CONTEXT_LABELS.get((value or "all").strip().lower(), "همه‌جا")


def resolve_segment_identifiers(tokens: List[str]) -> Tuple[List[Dict], List[str]]:
    segments = get_all_segments()
    by_id = {str(segment["id"]): segment for segment in segments}
    by_slug = {str(segment["slug"]).lower(): segment for segment in segments}
    resolved: List[Dict] = []
    missing: List[str] = []
    seen_ids = set()

    for raw_token in tokens:
        token = raw_token.strip()
        if not token:
            continue

        segment = by_id.get(token) or by_slug.get(token.lower())
        if not segment:
            missing.append(token)
            continue

        if segment["id"] in seen_ids:
            continue

        seen_ids.add(segment["id"])
        resolved.append(segment)

    return resolved, missing


def audience_main_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="📦 تنظیم مخاطب پلن‌ها", callback_data="audience|plans")],
            [InlineKeyboardButton(text="👥 مدیریت سگمنت‌ها", callback_data="audience|segments")],
            [InlineKeyboardButton(text="🔙 منوی اصلی", callback_data="audience|main_menu")],
        ]
    )


def plans_keyboard(plans: List[Dict]) -> InlineKeyboardMarkup:
    rows = []
    for plan in plans:
        visibility = "✅" if int(plan.get("visible") or 0) == 1 else "🚫"
        segment_note = f" | {plan['segment_count']} سگمنت" if int(plan.get("segment_count") or 0) else ""
        text = (
            f"{visibility} #{plan['id']} {plan['name']}"
            f" | {get_access_level_label(plan.get('access_level'))}"
            f" | {get_display_context_label(plan.get('display_context'))}"
            f"{segment_note}"
        )
        rows.append([InlineKeyboardButton(text=text[:64], callback_data=f"audience|plan|{plan['id']}")])

    rows.append([InlineKeyboardButton(text="👥 مدیریت سگمنت‌ها", callback_data="audience|segments")])
    rows.append([InlineKeyboardButton(text="🔙 بازگشت", callback_data="audience|home")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def segments_keyboard(segments: List[Dict]) -> InlineKeyboardMarkup:
    rows = []
    for segment in segments:
        icon = "🟢" if int(segment.get("is_active") or 0) == 1 else "⚪"
        text = (
            f"{icon} #{segment['id']} {segment['title']}"
            f" | {segment['user_count']} کاربر"
            f" | {segment['plan_count']} پلن"
        )
        rows.append([InlineKeyboardButton(text=text[:64], callback_data=f"audience|segment|{segment['id']}")])

    rows.append([InlineKeyboardButton(text="➕ ساخت سگمنت جدید", callback_data="audience|segment_new")])
    rows.append([InlineKeyboardButton(text="📦 پلن‌ها", callback_data="audience|plans")])
    rows.append([InlineKeyboardButton(text="🔙 بازگشت", callback_data="audience|home")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def plan_detail_keyboard(plan_id: int, has_segments: bool) -> InlineKeyboardMarkup:
    rows = [
        [InlineKeyboardButton(text="🧭 محل نمایش", callback_data=f"audience|plan_context_menu|{plan_id}")],
        [InlineKeyboardButton(text="🎯 سطح دسترسی", callback_data=f"audience|plan_access_menu|{plan_id}")],
        [InlineKeyboardButton(text="➕ اتصال سگمنت", callback_data=f"audience|plan_attach_segments|{plan_id}")],
    ]
    if has_segments:
        rows.append([InlineKeyboardButton(text="➖ حذف سگمنت", callback_data=f"audience|plan_detach_segments|{plan_id}")])
    rows.append([InlineKeyboardButton(text="👥 مدیریت سگمنت‌ها", callback_data="audience|segments")])
    rows.append([InlineKeyboardButton(text="🔙 لیست پلن‌ها", callback_data="audience|plans")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def plan_access_keyboard(plan_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="همه کاربران", callback_data=f"audience|plan_access_set|{plan_id}|all")],
            [InlineKeyboardButton(text="فقط کاربران عادی", callback_data=f"audience|plan_access_set|{plan_id}|user")],
            [InlineKeyboardButton(text="فقط نماینده‌ها", callback_data=f"audience|plan_access_set|{plan_id}|agent")],
            [InlineKeyboardButton(text="فقط ادمین‌ها", callback_data=f"audience|plan_access_set|{plan_id}|admin")],
            [InlineKeyboardButton(text="🔙 بازگشت", callback_data=f"audience|plan|{plan_id}")],
        ]
    )


def plan_context_keyboard(plan_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="همه‌جا", callback_data=f"audience|plan_context_set|{plan_id}|all")],
            [InlineKeyboardButton(text="فقط خرید", callback_data=f"audience|plan_context_set|{plan_id}|purchase")],
            [InlineKeyboardButton(text="فقط تمدید", callback_data=f"audience|plan_context_set|{plan_id}|renew")],
            [InlineKeyboardButton(text="فقط نماینده‌ها", callback_data=f"audience|plan_context_set|{plan_id}|agent")],
            [InlineKeyboardButton(text="🔙 بازگشت", callback_data=f"audience|plan|{plan_id}")],
        ]
    )


def segment_detail_keyboard(segment_id: int, is_active: bool) -> InlineKeyboardMarkup:
    toggle_text = "⏸ غیرفعال‌کردن" if is_active else "▶️ فعال‌کردن"
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="➕ افزودن کاربر", callback_data=f"audience|segment_add_users|{segment_id}")],
            [InlineKeyboardButton(text="➖ حذف کاربر", callback_data=f"audience|segment_remove_users|{segment_id}")],
            [InlineKeyboardButton(text="✏️ ویرایش عنوان/توضیح", callback_data=f"audience|segment_edit|{segment_id}")],
            [InlineKeyboardButton(text=toggle_text, callback_data=f"audience|segment_toggle|{segment_id}")],
            [InlineKeyboardButton(text="🗑 حذف سگمنت", callback_data=f"audience|segment_delete_ask|{segment_id}")],
            [InlineKeyboardButton(text="📦 پلن‌ها", callback_data="audience|plans")],
            [InlineKeyboardButton(text="🔙 لیست سگمنت‌ها", callback_data="audience|segments")],
        ]
    )


def segment_delete_keyboard(segment_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="✅ حذف شود", callback_data=f"audience|segment_delete_confirm|{segment_id}")],
            [InlineKeyboardButton(text="🔙 انصراف", callback_data=f"audience|segment|{segment_id}")],
        ]
    )


def build_plan_detail_text(plan: Dict, plan_segments: List[Dict]) -> str:
    segment_lines = [
        f"• #{segment['id']} {segment['title']} ({segment['slug']})"
        for segment in plan_segments
    ]
    segments_text = "\n".join(segment_lines) if segment_lines else "بدون محدودیت سگمنت"

    return (
        f"📦 <b>پلن #{plan['id']}</b>\n"
        f"نام: <b>{plan['name']}</b>\n"
        f"قیمت: <b>{format_price(plan.get('price'))}</b> تومان\n"
        f"دسته: <b>{plan.get('category') or '-'}</b>\n"
        f"لوکیشن: <b>{plan.get('location') or '-'}</b>\n"
        f"نمایش در: <b>{get_display_context_label(plan.get('display_context'))}</b>\n"
        f"سطح دسترسی: <b>{get_access_level_label(plan.get('access_level'))}</b>\n"
        f"وضعیت نمایش: <b>{'فعال' if int(plan.get('visible') or 0) == 1 else 'مخفی'}</b>\n\n"
        f"سگمنت‌های متصل:\n{segments_text}\n\n"
        "نکته: اگر هیچ سگمنتی وصل نباشد، پلن فقط با role/context فیلتر می‌شود."
    )


def build_segment_detail_text(segment: Dict, users: List[Dict], plans: List[Dict]) -> str:
    user_lines = []
    for user in users[:10]:
        name = f"{user.get('first_name') or '-'} {user.get('last_name') or ''}".strip()
        username = f"@{user['username']}" if user.get("username") else "-"
        user_lines.append(f"• {name} | {username} | #{user['id']} | {user.get('role') or 'user'}")
    if not user_lines:
        user_lines.append("• فعلا کاربری عضو این سگمنت نیست.")

    plan_lines = []
    for plan in plans[:10]:
        plan_lines.append(
            f"• #{plan['id']} {plan['name']} | "
            f"{get_access_level_label(plan.get('access_level'))} | "
            f"{get_display_context_label(plan.get('display_context'))}"
        )
    if not plan_lines:
        plan_lines.append("• فعلا پلنی به این سگمنت وصل نشده.")

    return (
        f"👥 <b>سگمنت #{segment['id']}</b>\n"
        f"عنوان: <b>{segment['title']}</b>\n"
        f"شناسه: <code>{segment['slug']}</code>\n"
        f"وضعیت: <b>{'فعال' if int(segment.get('is_active') or 0) == 1 else 'غیرفعال'}</b>\n"
        f"توضیح: <b>{segment.get('description') or '-'}</b>\n"
        f"تعداد اعضا: <b>{segment.get('user_count') or 0}</b>\n"
        f"تعداد پلن‌ها: <b>{segment.get('plan_count') or 0}</b>\n\n"
        f"اعضای اخیر:\n{chr(10).join(user_lines)}\n\n"
        f"پلن‌های متصل:\n{chr(10).join(plan_lines)}"
    )


async def show_audience_home(target: Union[Message, CallbackQuery], state: FSMContext) -> None:
    await state.clear()
    text = (
        "🎯 <b>مدیریت مخاطب پلن‌ها</b>\n\n"
        "از اینجا می‌توانی:\n"
        "• مشخص کنی هر پلن کجا نمایش داده شود\n"
        "• تعیین کنی پلن برای چه roleی دیده شود\n"
        "• سگمنت بسازی و کاربرهای خاص را عضو کنی\n"
        "• یک یا چند سگمنت را به یک پلن وصل کنی"
    )

    message = target.message if isinstance(target, CallbackQuery) else target
    await message.answer(text, parse_mode="HTML", reply_markup=audience_main_keyboard())


async def show_plans_list(target: Union[Message, CallbackQuery], state: FSMContext) -> None:
    await state.clear()
    plans = get_all_plans_for_admin_audience()
    message = target.message if isinstance(target, CallbackQuery) else target
    await message.answer(
        "📦 لیست پلن‌ها برای مدیریت مخاطب:",
        reply_markup=plans_keyboard(plans),
    )


async def show_segments_list(target: Union[Message, CallbackQuery], state: FSMContext) -> None:
    await state.clear()
    segments = get_all_segments()
    message = target.message if isinstance(target, CallbackQuery) else target
    await message.answer(
        "👥 لیست سگمنت‌ها:",
        reply_markup=segments_keyboard(segments),
    )


async def show_plan_detail(target: Union[Message, CallbackQuery], plan_id: int, state: FSMContext) -> None:
    await state.clear()
    plan = get_plan_for_admin_audience(plan_id)
    message = target.message if isinstance(target, CallbackQuery) else target
    if not plan:
        await message.answer("❌ این پلن پیدا نشد.")
        return

    plan_segments = get_plan_segments(plan_id)
    await message.answer(
        build_plan_detail_text(plan, plan_segments),
        parse_mode="HTML",
        reply_markup=plan_detail_keyboard(plan_id, has_segments=bool(plan_segments)),
    )


async def show_segment_detail(target: Union[Message, CallbackQuery], segment_id: int, state: FSMContext) -> None:
    await state.clear()
    segment = get_segment(segment_id)
    message = target.message if isinstance(target, CallbackQuery) else target
    if not segment:
        await message.answer("❌ این سگمنت پیدا نشد.")
        return

    users = get_segment_users(segment_id)
    plans = get_segment_plans(segment_id)
    await message.answer(
        build_segment_detail_text(segment, users, plans),
        parse_mode="HTML",
        reply_markup=segment_detail_keyboard(segment_id, bool(int(segment.get("is_active") or 0))),
    )


@router.message(F.text == "🎯 مخاطب پلن‌ها")
@router.message(F.text.startswith("/plan_audience"))
@router.message(F.text.startswith("/segments"))
async def audience_entry(message: Message, state: FSMContext):
    if not is_admin(message.from_user.id):
        return await message.reply("دسترسی ندارید.")
    await show_audience_home(message, state)


@router.callback_query(F.data == "audience|home")
async def audience_home_callback(callback: CallbackQuery, state: FSMContext):
    if not is_admin(callback.from_user.id):
        return await callback.answer("دسترسی ندارید.", show_alert=True)
    await show_audience_home(callback, state)
    await callback.answer()


@router.callback_query(F.data == "audience|main_menu")
async def audience_back_main(callback: CallbackQuery, state: FSMContext):
    if not is_admin(callback.from_user.id):
        return await callback.answer("دسترسی ندارید.", show_alert=True)
    await state.clear()
    await callback.message.answer("بازگشت به منوی اصلی.", reply_markup=admin_main_menu_keyboard())
    await callback.answer()


@router.callback_query(F.data == "audience|plans")
async def audience_plans(callback: CallbackQuery, state: FSMContext):
    if not is_admin(callback.from_user.id):
        return await callback.answer("دسترسی ندارید.", show_alert=True)
    await show_plans_list(callback, state)
    await callback.answer()


@router.callback_query(F.data == "audience|segments")
async def audience_segments(callback: CallbackQuery, state: FSMContext):
    if not is_admin(callback.from_user.id):
        return await callback.answer("دسترسی ندارید.", show_alert=True)
    await show_segments_list(callback, state)
    await callback.answer()


@router.callback_query(F.data.startswith("audience|plan|"))
async def audience_plan_detail(callback: CallbackQuery, state: FSMContext):
    if not is_admin(callback.from_user.id):
        return await callback.answer("دسترسی ندارید.", show_alert=True)
    plan_id = int(callback.data.split("|")[2])
    await show_plan_detail(callback, plan_id, state)
    await callback.answer()


@router.callback_query(F.data.startswith("audience|plan_access_menu|"))
async def audience_plan_access_menu(callback: CallbackQuery):
    if not is_admin(callback.from_user.id):
        return await callback.answer("دسترسی ندارید.", show_alert=True)
    plan_id = int(callback.data.split("|")[2])
    await callback.message.answer(
        "🎯 سطح دسترسی این پلن را انتخاب کنید:",
        reply_markup=plan_access_keyboard(plan_id),
    )
    await callback.answer()


@router.callback_query(F.data.startswith("audience|plan_context_menu|"))
async def audience_plan_context_menu(callback: CallbackQuery):
    if not is_admin(callback.from_user.id):
        return await callback.answer("دسترسی ندارید.", show_alert=True)
    plan_id = int(callback.data.split("|")[2])
    await callback.message.answer(
        "🧭 محل نمایش این پلن را انتخاب کنید:",
        reply_markup=plan_context_keyboard(plan_id),
    )
    await callback.answer()


@router.callback_query(F.data.startswith("audience|plan_access_set|"))
async def audience_plan_access_set(callback: CallbackQuery, state: FSMContext):
    if not is_admin(callback.from_user.id):
        return await callback.answer("دسترسی ندارید.", show_alert=True)
    _, _, _, plan_id, access_level = callback.data.split("|")
    update_plan_access_level(int(plan_id), access_level)
    await callback.answer("سطح دسترسی پلن ذخیره شد.")
    await show_plan_detail(callback, int(plan_id), state)


@router.callback_query(F.data.startswith("audience|plan_context_set|"))
async def audience_plan_context_set(callback: CallbackQuery, state: FSMContext):
    if not is_admin(callback.from_user.id):
        return await callback.answer("دسترسی ندارید.", show_alert=True)
    _, _, _, plan_id, display_context = callback.data.split("|")
    update_plan_display_context(int(plan_id), display_context)
    await callback.answer("محل نمایش پلن ذخیره شد.")
    await show_plan_detail(callback, int(plan_id), state)


@router.callback_query(F.data.startswith("audience|plan_attach_segments|"))
async def audience_plan_attach_segments_prompt(callback: CallbackQuery, state: FSMContext):
    if not is_admin(callback.from_user.id):
        return await callback.answer("دسترسی ندارید.", show_alert=True)
    plan_id = int(callback.data.split("|")[2])
    await state.clear()
    await state.update_data(plan_id=plan_id)
    await state.set_state(PlanAudienceStates.waiting_for_plan_attach_segments)
    await callback.message.answer(
        "شناسه یا slug سگمنت‌ها را بفرست.\n"
        "می‌توانی چند مورد را با فاصله، ویرگول یا خط جدید بفرستی.\n\n"
        "مثال:\n1 3 friends old_users"
    )
    await callback.answer()


@router.callback_query(F.data.startswith("audience|plan_detach_segments|"))
async def audience_plan_detach_segments_prompt(callback: CallbackQuery, state: FSMContext):
    if not is_admin(callback.from_user.id):
        return await callback.answer("دسترسی ندارید.", show_alert=True)
    plan_id = int(callback.data.split("|")[2])
    await state.clear()
    await state.update_data(plan_id=plan_id)
    await state.set_state(PlanAudienceStates.waiting_for_plan_detach_segments)
    await callback.message.answer(
        "شناسه یا slug سگمنت‌هایی را بفرست که باید از این پلن جدا شوند.\n"
        "می‌توانی چند مورد را با فاصله، ویرگول یا خط جدید بفرستی."
    )
    await callback.answer()


@router.message(PlanAudienceStates.waiting_for_plan_attach_segments)
async def audience_plan_attach_segments_receive(message: Message, state: FSMContext):
    if not is_admin(message.from_user.id):
        await state.clear()
        return await message.reply("دسترسی ندارید.")

    data = await state.get_data()
    plan_id = data.get("plan_id")
    if not plan_id:
        await state.clear()
        return await message.answer("❌ وضعیت عملیات پیدا نشد.")

    tokens = split_tokens(message.text)
    resolved, missing = resolve_segment_identifiers(tokens)
    if not resolved:
        return await message.answer("❌ هیچ سگمنت معتبری پیدا نشد.")

    added = attach_segments_to_plan(int(plan_id), [segment["id"] for segment in resolved])
    summary = [f"✅ {added} اتصال برای پلن #{plan_id} ثبت شد."]
    if missing:
        summary.append("موارد پیدا نشد: " + ", ".join(missing))
    await state.clear()
    await message.answer("\n".join(summary))
    await show_plan_detail(message, int(plan_id), state)


@router.message(PlanAudienceStates.waiting_for_plan_detach_segments)
async def audience_plan_detach_segments_receive(message: Message, state: FSMContext):
    if not is_admin(message.from_user.id):
        await state.clear()
        return await message.reply("دسترسی ندارید.")

    data = await state.get_data()
    plan_id = data.get("plan_id")
    if not plan_id:
        await state.clear()
        return await message.answer("❌ وضعیت عملیات پیدا نشد.")

    tokens = split_tokens(message.text)
    resolved, missing = resolve_segment_identifiers(tokens)
    if not resolved:
        return await message.answer("❌ هیچ سگمنت معتبری پیدا نشد.")

    removed = detach_segments_from_plan(int(plan_id), [segment["id"] for segment in resolved])
    summary = [f"✅ {removed} اتصال از پلن #{plan_id} حذف شد."]
    if missing:
        summary.append("موارد پیدا نشد: " + ", ".join(missing))
    await state.clear()
    await message.answer("\n".join(summary))
    await show_plan_detail(message, int(plan_id), state)


@router.callback_query(F.data == "audience|segment_new")
async def audience_segment_new_prompt(callback: CallbackQuery, state: FSMContext):
    if not is_admin(callback.from_user.id):
        return await callback.answer("دسترسی ندارید.", show_alert=True)
    await state.clear()
    await state.set_state(PlanAudienceStates.waiting_for_new_segment)
    await callback.message.answer(
        "فرمت ساخت سگمنت:\n"
        "slug | عنوان | توضیح اختیاری\n\n"
        "مثال:\nold_users | کاربران قدیمی | برای پیشنهادهای وفاداری"
    )
    await callback.answer()


@router.message(PlanAudienceStates.waiting_for_new_segment)
async def audience_segment_new_receive(message: Message, state: FSMContext):
    if not is_admin(message.from_user.id):
        await state.clear()
        return await message.reply("دسترسی ندارید.")

    parts = [part.strip() for part in message.text.split("|")]
    if len(parts) < 2:
        return await message.answer("فرمت درست نیست. حداقل slug و عنوان لازم است.")

    slug, title = parts[:2]
    description = parts[2] if len(parts) >= 3 else None
    try:
        segment_id = create_segment(slug, title, description)
    except Exception as exc:
        return await message.answer(f"❌ ساخت سگمنت انجام نشد: {exc}")

    await state.clear()
    await message.answer(f"✅ سگمنت #{segment_id} ساخته شد.")
    await show_segment_detail(message, segment_id, state)


@router.callback_query(F.data.startswith("audience|segment|"))
async def audience_segment_detail(callback: CallbackQuery, state: FSMContext):
    if not is_admin(callback.from_user.id):
        return await callback.answer("دسترسی ندارید.", show_alert=True)
    segment_id = int(callback.data.split("|")[2])
    await show_segment_detail(callback, segment_id, state)
    await callback.answer()


@router.callback_query(F.data.startswith("audience|segment_edit|"))
async def audience_segment_edit_prompt(callback: CallbackQuery, state: FSMContext):
    if not is_admin(callback.from_user.id):
        return await callback.answer("دسترسی ندارید.", show_alert=True)
    segment_id = int(callback.data.split("|")[2])
    await state.clear()
    await state.update_data(segment_id=segment_id)
    await state.set_state(PlanAudienceStates.waiting_for_segment_edit)
    await callback.message.answer(
        "فرمت ویرایش:\n"
        "عنوان جدید | توضیح جدید اختیاری\n\n"
        "مثال:\nکاربران قدیمی VIP | فقط برای پیشنهادهای تمدید"
    )
    await callback.answer()


@router.message(PlanAudienceStates.waiting_for_segment_edit)
async def audience_segment_edit_receive(message: Message, state: FSMContext):
    if not is_admin(message.from_user.id):
        await state.clear()
        return await message.reply("دسترسی ندارید.")

    data = await state.get_data()
    segment_id = data.get("segment_id")
    if not segment_id:
        await state.clear()
        return await message.answer("❌ وضعیت عملیات پیدا نشد.")

    parts = [part.strip() for part in message.text.split("|")]
    if not parts or not parts[0]:
        return await message.answer("عنوان جدید را ارسال کن.")

    title = parts[0]
    description = parts[1] if len(parts) >= 2 else None
    update_segment_info(int(segment_id), title, description)
    await state.clear()
    await message.answer("✅ اطلاعات سگمنت به‌روزرسانی شد.")
    await show_segment_detail(message, int(segment_id), state)


@router.callback_query(F.data.startswith("audience|segment_add_users|"))
async def audience_segment_add_users_prompt(callback: CallbackQuery, state: FSMContext):
    if not is_admin(callback.from_user.id):
        return await callback.answer("دسترسی ندارید.", show_alert=True)
    segment_id = int(callback.data.split("|")[2])
    await state.clear()
    await state.update_data(segment_id=segment_id)
    await state.set_state(PlanAudienceStates.waiting_for_segment_add_users)
    await callback.message.answer(
        "آیدی یا یوزرنیم کاربران را بفرست.\n"
        "می‌توانی چند مورد را با فاصله، ویرگول یا خط جدید بفرستی.\n\n"
        "مثال:\n123456789 @omid another_user"
    )
    await callback.answer()


@router.callback_query(F.data.startswith("audience|segment_remove_users|"))
async def audience_segment_remove_users_prompt(callback: CallbackQuery, state: FSMContext):
    if not is_admin(callback.from_user.id):
        return await callback.answer("دسترسی ندارید.", show_alert=True)
    segment_id = int(callback.data.split("|")[2])
    await state.clear()
    await state.update_data(segment_id=segment_id)
    await state.set_state(PlanAudienceStates.waiting_for_segment_remove_users)
    await callback.message.answer(
        "آیدی یا یوزرنیم کاربرهایی را بفرست که باید از سگمنت حذف شوند.\n"
        "می‌توانی چند مورد را با فاصله، ویرگول یا خط جدید بفرستی."
    )
    await callback.answer()


@router.message(PlanAudienceStates.waiting_for_segment_add_users)
async def audience_segment_add_users_receive(message: Message, state: FSMContext):
    if not is_admin(message.from_user.id):
        await state.clear()
        return await message.reply("دسترسی ندارید.")

    data = await state.get_data()
    segment_id = data.get("segment_id")
    if not segment_id:
        await state.clear()
        return await message.answer("❌ وضعیت عملیات پیدا نشد.")

    users, missing = resolve_user_identifiers(split_tokens(message.text))
    if not users:
        return await message.answer("❌ هیچ کاربر معتبری پیدا نشد.")

    added = add_users_to_segment(int(segment_id), [user["id"] for user in users])
    summary = [f"✅ {added} عضویت برای سگمنت #{segment_id} ثبت شد."]
    if missing:
        summary.append("پیدا نشد: " + ", ".join(missing))
    await state.clear()
    await message.answer("\n".join(summary))
    await show_segment_detail(message, int(segment_id), state)


@router.message(PlanAudienceStates.waiting_for_segment_remove_users)
async def audience_segment_remove_users_receive(message: Message, state: FSMContext):
    if not is_admin(message.from_user.id):
        await state.clear()
        return await message.reply("دسترسی ندارید.")

    data = await state.get_data()
    segment_id = data.get("segment_id")
    if not segment_id:
        await state.clear()
        return await message.answer("❌ وضعیت عملیات پیدا نشد.")

    users, missing = resolve_user_identifiers(split_tokens(message.text))
    if not users:
        return await message.answer("❌ هیچ کاربر معتبری پیدا نشد.")

    removed = remove_users_from_segment(int(segment_id), [user["id"] for user in users])
    summary = [f"✅ {removed} عضویت از سگمنت #{segment_id} حذف شد."]
    if missing:
        summary.append("پیدا نشد: " + ", ".join(missing))
    await state.clear()
    await message.answer("\n".join(summary))
    await show_segment_detail(message, int(segment_id), state)


@router.callback_query(F.data.startswith("audience|segment_toggle|"))
async def audience_segment_toggle(callback: CallbackQuery, state: FSMContext):
    if not is_admin(callback.from_user.id):
        return await callback.answer("دسترسی ندارید.", show_alert=True)
    segment_id = int(callback.data.split("|")[2])
    segment = get_segment(segment_id)
    if not segment:
        return await callback.answer("این سگمنت پیدا نشد.", show_alert=True)
    new_status = 0 if int(segment.get("is_active") or 0) == 1 else 1
    set_segment_active(segment_id, new_status)
    await callback.answer("وضعیت سگمنت به‌روزرسانی شد.")
    await show_segment_detail(callback, segment_id, state)


@router.callback_query(F.data.startswith("audience|segment_delete_ask|"))
async def audience_segment_delete_ask(callback: CallbackQuery):
    if not is_admin(callback.from_user.id):
        return await callback.answer("دسترسی ندارید.", show_alert=True)
    segment_id = int(callback.data.split("|")[2])
    await callback.message.answer(
        "اگر این سگمنت حذف شود، اتصالش از پلن‌ها و عضویت کاربرانش هم پاک می‌شود.",
        reply_markup=segment_delete_keyboard(segment_id),
    )
    await callback.answer()


@router.callback_query(F.data.startswith("audience|segment_delete_confirm|"))
async def audience_segment_delete_confirm(callback: CallbackQuery, state: FSMContext):
    if not is_admin(callback.from_user.id):
        return await callback.answer("دسترسی ندارید.", show_alert=True)
    segment_id = int(callback.data.split("|")[2])
    delete_segment(segment_id)
    await state.clear()
    await callback.answer("سگمنت حذف شد.")
    await show_segments_list(callback, state)
