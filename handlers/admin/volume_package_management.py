import re
from typing import Dict, List, Optional, Tuple, Union

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message

from config import ADMINS
from keyboards.main_menu import admin_main_menu_keyboard
from services.db import (
    add_volume_package,
    attach_categories_to_volume_package,
    attach_segments_to_volume_package,
    detach_categories_from_volume_package,
    detach_segments_from_volume_package,
    get_all_segments,
    get_volume_package,
    get_volume_package_categories,
    get_volume_package_segments,
    get_volume_packages,
    set_volume_package_archived,
    update_volume_package_field,
)

router = Router()


class VolumePackageStates(StatesGroup):
    waiting_for_add = State()
    waiting_for_value = State()
    waiting_for_attach_segments = State()
    waiting_for_detach_segments = State()
    waiting_for_attach_categories = State()
    waiting_for_detach_categories = State()


PACKAGE_CATEGORY_LABELS = {
    "standard": "استاندارد",
    "fixed_ip": "آی‌پی ثابت",
    "dual": "دوگانه",
    "custom_location": "لوکیشن اختصاصی",
    "modem": "روتر/مودم",
    "special_access": "دسترسی ویژه",
}


def is_admin(user_id: int) -> bool:
    return str(user_id) in {str(admin_id) for admin_id in ADMINS}


def format_price(amount: int) -> str:
    try:
        return f"{int(amount):,}"
    except Exception:
        return str(amount)


def split_tokens(value: str) -> List[str]:
    return [token.strip() for token in re.split(r"[\s,\n،,]+", value or "") if token.strip()]


def normalize_category(value: str) -> str:
    category = (value or "").strip().lower().replace("-", "_").replace(" ", "_")
    while "__" in category:
        category = category.replace("__", "_")
    return category.strip("_")


def category_label(category: str) -> str:
    normalized = normalize_category(category)
    return PACKAGE_CATEGORY_LABELS.get(normalized, normalized or "-")


def resolve_categories(tokens: List[str]) -> Tuple[List[str], List[str]]:
    aliases = {
        "router": "modem",
        "routers": "modem",
        "modem": "modem",
        "vip": "special_access",
        "special": "special_access",
        "special_access": "special_access",
        "fixed": "fixed_ip",
        "fixedip": "fixed_ip",
        "fixed_ip": "fixed_ip",
    }
    resolved: List[str] = []
    missing: List[str] = []
    seen = set()

    for token in tokens:
        normalized = normalize_category(token)
        category = aliases.get(normalized, normalized)
        if not category:
            continue
        if category not in PACKAGE_CATEGORY_LABELS:
            missing.append(token)
            continue
        if category in seen:
            continue
        seen.add(category)
        resolved.append(category)

    return resolved, missing


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


def packages_keyboard(include_archived: bool = False) -> InlineKeyboardMarkup:
    packages = get_volume_packages(include_archived=include_archived)
    rows = []
    for item in packages:
        active_icon = "✅" if int(item.get("is_active") or 0) == 1 else "🚫"
        segment_note = f" | {item['segment_count']} سگمنت" if int(item.get("segment_count") or 0) else ""
        category_note = f" | {item['category_count']} دسته" if int(item.get("category_count") or 0) else ""
        label = (
            f"#{item['id']} | {active_icon} {item['name']} | "
            f"{item.get('volume_gb') or 0} گیگ | {format_price(item.get('price') or 0)}"
            f"{segment_note}{category_note}"
        )
        rows.append([
            InlineKeyboardButton(
                text=label[:64],
                callback_data=f"volume_pkg|open|{item['id']}",
            )
        ])

    if include_archived:
        rows.append([InlineKeyboardButton(text="📦 بسته‌های فعال", callback_data="volume_pkg|list|active")])
    else:
        rows.append([InlineKeyboardButton(text="🗂 بسته‌های آرشیوشده", callback_data="volume_pkg|list|archived")])
        rows.append([InlineKeyboardButton(text="➕ افزودن بسته جدید", callback_data="volume_pkg|add")])
    rows.append([InlineKeyboardButton(text="🏠 منوی ادمین", callback_data="volume_pkg|main")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def package_detail_keyboard(package_id: int, archived: bool) -> InlineKeyboardMarkup:
    archive_text = "♻️ خروج از آرشیو" if archived else "🗂 آرشیو بسته"
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="✏️ نام", callback_data=f"volume_pkg|edit|name|{package_id}")],
            [InlineKeyboardButton(text="📦 حجم", callback_data=f"volume_pkg|edit|volume_gb|{package_id}")],
            [InlineKeyboardButton(text="💰 قیمت", callback_data=f"volume_pkg|edit|price|{package_id}")],
            [InlineKeyboardButton(text="🔢 اولویت", callback_data=f"volume_pkg|edit|sort_order|{package_id}")],
            [InlineKeyboardButton(text="🎯 اتصال سگمنت", callback_data=f"volume_pkg|segment_attach|{package_id}")],
            [InlineKeyboardButton(text="➖ حذف سگمنت", callback_data=f"volume_pkg|segment_detach|{package_id}")],
            [InlineKeyboardButton(text="🧭 اتصال دسته سرویس", callback_data=f"volume_pkg|category_attach|{package_id}")],
            [InlineKeyboardButton(text="➖ حذف دسته سرویس", callback_data=f"volume_pkg|category_detach|{package_id}")],
            [InlineKeyboardButton(text="✅/🚫 فعال‌سازی", callback_data=f"volume_pkg|toggle|{package_id}")],
            [InlineKeyboardButton(text=archive_text, callback_data=f"volume_pkg|archive|{package_id}")],
            [InlineKeyboardButton(text="🔙 بازگشت", callback_data=f"volume_pkg|list|{'archived' if archived else 'active'}")],
        ]
    )


def build_package_caption(
    package: dict,
    package_segments: Optional[List[Dict]] = None,
    package_categories: Optional[List[str]] = None,
) -> str:
    if package_segments is None:
        package_segments = get_volume_package_segments(int(package["id"]))
    if package_categories is None:
        package_categories = get_volume_package_categories(int(package["id"]))
    segment_lines = [
        f"• #{segment['id']} {segment['title']} ({segment['slug']})"
        for segment in package_segments
    ]
    segments_text = "\n".join(segment_lines) if segment_lines else "عمومی؛ بدون محدودیت سگمنت"
    categories_text = (
        "\n".join(f"• {category_label(category)} ({category})" for category in package_categories)
        if package_categories
        else "همه دسته‌های سرویس"
    )

    return (
        f"📚 بسته حجمی #{package['id']}\n"
        f"نام: {package.get('name') or '-'}\n"
        f"حجم: {package.get('volume_gb') or 0} گیگ\n"
        f"قیمت: {format_price(package.get('price') or 0)} تومان\n"
        f"اولویت: {package.get('sort_order') or 0}\n"
        f"وضعیت: {'فعال' if int(package.get('is_active') or 0) == 1 else 'غیرفعال'}\n"
        f"آرشیو: {'بله' if int(package.get('is_archived') or 0) == 1 else 'خیر'}\n"
        f"ایجاد: {package.get('created_at') or '-'}\n\n"
        f"سگمنت‌های مجاز:\n{segments_text}\n\n"
        f"دسته‌های سرویس مجاز:\n{categories_text}"
    )


async def show_package_list(target: Union[Message, CallbackQuery], include_archived: bool = False) -> None:
    text = (
        "📚 بسته‌های حجمی آرشیوشده:\n"
        "برای اتصال یا حذف سگمنت، ابتدا یکی از بسته‌ها را باز کن."
        if include_archived
        else
        "📚 بسته‌های حجمی فعال:\n"
        "برای اتصال یا حذف سگمنت، ابتدا یکی از بسته‌ها را باز کن."
    )
    keyboard = packages_keyboard(include_archived=include_archived)
    if isinstance(target, Message):
        await target.answer(text, reply_markup=keyboard)
    else:
        await target.message.answer(text, reply_markup=keyboard)
        await target.answer()


async def show_package_detail(target: Union[Message, CallbackQuery], package_id: int) -> None:
    package = get_volume_package(package_id)
    message = target.message if isinstance(target, CallbackQuery) else target
    if not package:
        await message.answer("❌ این بسته پیدا نشد.")
        return

    package_segments = get_volume_package_segments(package_id)
    package_categories = get_volume_package_categories(package_id)
    await message.answer(
        build_package_caption(
            package,
            package_segments=package_segments,
            package_categories=package_categories,
        ),
        reply_markup=package_detail_keyboard(package_id, archived=bool(package.get("is_archived"))),
    )


def build_segment_reference_text(segments: List[Dict]) -> str:
    lines = [
        f"• #{segment['id']} | {segment['title']} | slug={segment['slug']}"
        for segment in segments[:25]
    ]
    if len(segments) > 25:
        lines.append(f"و {len(segments) - 25} سگمنت دیگر...")
    return "\n".join(lines) if lines else "سگمنتی ثبت نشده است."


def build_category_reference_text() -> str:
    return "\n".join(
        f"• {label}: <code>{category}</code>"
        for category, label in PACKAGE_CATEGORY_LABELS.items()
    )


@router.message(F.text == "📚 مدیریت بسته‌های حجمی")
async def package_management_entry(message: Message, state: FSMContext):
    if not is_admin(message.from_user.id):
        return
    await state.clear()
    await show_package_list(message, include_archived=False)


@router.callback_query(F.data == "volume_pkg|main")
async def package_management_main(callback: CallbackQuery, state: FSMContext):
    if not is_admin(callback.from_user.id):
        return await callback.answer("دسترسی نداری.", show_alert=True)
    await state.clear()
    await callback.message.answer("بازگشت به منوی ادمین.", reply_markup=admin_main_menu_keyboard())
    await callback.answer()


@router.callback_query(F.data.startswith("volume_pkg|list|"))
async def package_management_list(callback: CallbackQuery, state: FSMContext):
    if not is_admin(callback.from_user.id):
        return await callback.answer("دسترسی نداری.", show_alert=True)
    await state.clear()
    include_archived = callback.data.endswith("|archived")
    await show_package_list(callback, include_archived=include_archived)


@router.callback_query(F.data == "volume_pkg|add")
async def package_management_add_start(callback: CallbackQuery, state: FSMContext):
    if not is_admin(callback.from_user.id):
        return await callback.answer("دسترسی نداری.", show_alert=True)
    await state.set_state(VolumePackageStates.waiting_for_add)
    await callback.message.answer(
        "فرمت افزودن بسته:\n"
        "نام | حجم گیگ | قیمت | اولویت اختیاری\n\n"
        "مثال:\n"
        "۵ گیگ فوری | 5 | 500000 | 0"
    )
    await callback.answer()


@router.message(VolumePackageStates.waiting_for_add)
async def package_management_add_receive(message: Message, state: FSMContext):
    if not is_admin(message.from_user.id):
        await state.clear()
        return

    parts = [part.strip() for part in (message.text or "").split("|")]
    if len(parts) < 3:
        await message.answer("فرمت درست نیست. حداقل نام، حجم و قیمت لازم است.")
        return

    name = parts[0]
    try:
        volume_gb = int(parts[1])
        price = int(parts[2])
        sort_order = int(parts[3]) if len(parts) >= 4 and parts[3] else 0
    except Exception:
        await message.answer("حجم، قیمت و اولویت باید عدد باشند.")
        return

    add_volume_package(name=name, volume_gb=volume_gb, price=price, sort_order=sort_order)
    await state.clear()
    await message.answer("✅ بسته حجمی جدید اضافه شد.", reply_markup=packages_keyboard(include_archived=False))


@router.callback_query(F.data.startswith("volume_pkg|open|"))
async def package_management_open(callback: CallbackQuery, state: FSMContext):
    if not is_admin(callback.from_user.id):
        return await callback.answer("دسترسی نداری.", show_alert=True)
    package_id = int(callback.data.split("|")[2])
    package = get_volume_package(package_id)
    if not package:
        return await callback.answer("بسته پیدا نشد.", show_alert=True)

    await state.clear()
    await show_package_detail(callback, package_id)
    await callback.answer()


@router.callback_query(F.data.startswith("volume_pkg|toggle|"))
async def package_management_toggle(callback: CallbackQuery, state: FSMContext):
    if not is_admin(callback.from_user.id):
        return await callback.answer("دسترسی نداری.", show_alert=True)
    package_id = int(callback.data.split("|")[2])
    package = get_volume_package(package_id)
    if not package:
        return await callback.answer("بسته پیدا نشد.", show_alert=True)
    new_value = 0 if int(package.get("is_active") or 0) == 1 else 1
    update_volume_package_field(package_id, "is_active", new_value)
    updated_package = get_volume_package(package_id)
    await state.clear()
    await callback.message.answer("✅ وضعیت بسته بروزرسانی شد.")
    if updated_package:
        await show_package_detail(callback, package_id)
    await callback.answer()


@router.callback_query(F.data.startswith("volume_pkg|archive|"))
async def package_management_archive(callback: CallbackQuery, state: FSMContext):
    if not is_admin(callback.from_user.id):
        return await callback.answer("دسترسی نداری.", show_alert=True)
    package_id = int(callback.data.split("|")[2])
    package = get_volume_package(package_id)
    if not package:
        return await callback.answer("بسته پیدا نشد.", show_alert=True)

    archived = not bool(package.get("is_archived"))
    set_volume_package_archived(package_id, archived=archived)
    await state.clear()
    await callback.message.answer("✅ وضعیت آرشیو بسته تغییر کرد.")
    await show_package_list(callback.message, include_archived=archived)
    await callback.answer()


@router.callback_query(F.data.startswith("volume_pkg|segment_attach|"))
async def package_management_attach_segments_prompt(callback: CallbackQuery, state: FSMContext):
    if not is_admin(callback.from_user.id):
        return await callback.answer("دسترسی نداری.", show_alert=True)

    package_id = int(callback.data.split("|")[2])
    package = get_volume_package(package_id)
    if not package:
        return await callback.answer("بسته پیدا نشد.", show_alert=True)

    segments = get_all_segments()
    if not segments:
        return await callback.answer("اول باید سگمنت بسازی.", show_alert=True)

    await state.clear()
    await state.update_data(package_id=package_id)
    await state.set_state(VolumePackageStates.waiting_for_attach_segments)
    await callback.message.answer(
        "شناسه یا slug سگمنت‌هایی که باید به این بسته حجمی وصل شوند را بفرست.\n"
        "می‌توانی چند مورد را با فاصله، ویرگول یا خط جدید بفرستی.\n\n"
        "سگمنت‌های موجود:\n"
        f"{build_segment_reference_text(segments)}\n\n"
        "مثال:\nvip volume_250 friends_volume"
    )
    await callback.answer()


@router.callback_query(F.data.startswith("volume_pkg|segment_detach|"))
async def package_management_detach_segments_prompt(callback: CallbackQuery, state: FSMContext):
    if not is_admin(callback.from_user.id):
        return await callback.answer("دسترسی نداری.", show_alert=True)

    package_id = int(callback.data.split("|")[2])
    package = get_volume_package(package_id)
    if not package:
        return await callback.answer("بسته پیدا نشد.", show_alert=True)

    package_segments = get_volume_package_segments(package_id)
    if not package_segments:
        return await callback.answer("این بسته عمومی است و سگمنتی برای حذف ندارد.", show_alert=True)

    await state.clear()
    await state.update_data(package_id=package_id)
    await state.set_state(VolumePackageStates.waiting_for_detach_segments)
    await callback.message.answer(
        "شناسه یا slug سگمنت‌هایی که باید از این بسته حجمی جدا شوند را بفرست.\n"
        "می‌توانی چند مورد را با فاصله، ویرگول یا خط جدید بفرستی.\n\n"
        "سگمنت‌های فعلی این بسته:\n"
        f"{build_segment_reference_text(package_segments)}"
    )
    await callback.answer()


@router.message(VolumePackageStates.waiting_for_attach_segments)
async def package_management_attach_segments_receive(message: Message, state: FSMContext):
    if not is_admin(message.from_user.id):
        await state.clear()
        return

    data = await state.get_data()
    package_id = data.get("package_id")
    if not package_id:
        await state.clear()
        return await message.answer("❌ وضعیت عملیات پیدا نشد. دوباره تلاش کن.")

    resolved, missing = resolve_segment_identifiers(split_tokens(message.text or ""))
    if not resolved:
        return await message.answer("❌ هیچ سگمنت معتبری پیدا نشد.")

    added = attach_segments_to_volume_package(int(package_id), [segment["id"] for segment in resolved])
    summary = [f"✅ {added} اتصال سگمنت برای بسته حجمی #{package_id} ثبت شد."]
    if missing:
        summary.append("پیدا نشد: " + ", ".join(missing))
    await state.clear()
    await message.answer("\n".join(summary))
    await show_package_detail(message, int(package_id))


@router.message(VolumePackageStates.waiting_for_detach_segments)
async def package_management_detach_segments_receive(message: Message, state: FSMContext):
    if not is_admin(message.from_user.id):
        await state.clear()
        return

    data = await state.get_data()
    package_id = data.get("package_id")
    if not package_id:
        await state.clear()
        return await message.answer("❌ وضعیت عملیات پیدا نشد. دوباره تلاش کن.")

    resolved, missing = resolve_segment_identifiers(split_tokens(message.text or ""))
    if not resolved:
        return await message.answer("❌ هیچ سگمنت معتبری پیدا نشد.")

    removed = detach_segments_from_volume_package(int(package_id), [segment["id"] for segment in resolved])
    summary = [f"✅ {removed} اتصال سگمنت از بسته حجمی #{package_id} حذف شد."]
    if missing:
        summary.append("پیدا نشد: " + ", ".join(missing))
    await state.clear()
    await message.answer("\n".join(summary))
    await show_package_detail(message, int(package_id))


@router.callback_query(F.data.startswith("volume_pkg|category_attach|"))
async def package_management_attach_categories_prompt(callback: CallbackQuery, state: FSMContext):
    if not is_admin(callback.from_user.id):
        return await callback.answer("دسترسی نداری.", show_alert=True)

    package_id = int(callback.data.split("|")[2])
    package = get_volume_package(package_id)
    if not package:
        return await callback.answer("بسته پیدا نشد.", show_alert=True)

    await state.clear()
    await state.update_data(package_id=package_id)
    await state.set_state(VolumePackageStates.waiting_for_attach_categories)
    await callback.message.answer(
        "slug دسته سرویس‌هایی که این بسته فقط برای آن‌ها مجاز است را بفرست.\n"
        "اگر هیچ دسته‌ای وصل نباشد، بسته برای همه دسته‌های سرویس مجاز است.\n\n"
        "دسته‌های موجود:\n"
        f"{build_category_reference_text()}\n\n"
        "مثال برای روتر/مودم:\n<code>modem</code>",
        parse_mode="HTML",
    )
    await callback.answer()


@router.callback_query(F.data.startswith("volume_pkg|category_detach|"))
async def package_management_detach_categories_prompt(callback: CallbackQuery, state: FSMContext):
    if not is_admin(callback.from_user.id):
        return await callback.answer("دسترسی نداری.", show_alert=True)

    package_id = int(callback.data.split("|")[2])
    package = get_volume_package(package_id)
    if not package:
        return await callback.answer("بسته پیدا نشد.", show_alert=True)

    package_categories = get_volume_package_categories(package_id)
    if not package_categories:
        return await callback.answer("این بسته محدودیت دسته سرویس ندارد.", show_alert=True)

    await state.clear()
    await state.update_data(package_id=package_id)
    await state.set_state(VolumePackageStates.waiting_for_detach_categories)
    current_categories = "\n".join(
        f"• {category_label(category)}: <code>{category}</code>"
        for category in package_categories
    )
    await callback.message.answer(
        "slug دسته سرویس‌هایی که باید از این بسته حذف شوند را بفرست.\n\n"
        "دسته‌های فعلی این بسته:\n"
        f"{current_categories}",
        parse_mode="HTML",
    )
    await callback.answer()


@router.message(VolumePackageStates.waiting_for_attach_categories)
async def package_management_attach_categories_receive(message: Message, state: FSMContext):
    if not is_admin(message.from_user.id):
        await state.clear()
        return

    data = await state.get_data()
    package_id = data.get("package_id")
    if not package_id:
        await state.clear()
        return await message.answer("❌ وضعیت عملیات پیدا نشد. دوباره تلاش کن.")

    resolved, missing = resolve_categories(split_tokens(message.text or ""))
    if not resolved:
        return await message.answer("❌ هیچ دسته سرویس معتبری پیدا نشد.")

    added = attach_categories_to_volume_package(int(package_id), resolved)
    summary = [f"✅ {added} دسته سرویس برای بسته حجمی #{package_id} ثبت شد."]
    if missing:
        summary.append("نامعتبر: " + ", ".join(missing))
    await state.clear()
    await message.answer("\n".join(summary))
    await show_package_detail(message, int(package_id))


@router.message(VolumePackageStates.waiting_for_detach_categories)
async def package_management_detach_categories_receive(message: Message, state: FSMContext):
    if not is_admin(message.from_user.id):
        await state.clear()
        return

    data = await state.get_data()
    package_id = data.get("package_id")
    if not package_id:
        await state.clear()
        return await message.answer("❌ وضعیت عملیات پیدا نشد. دوباره تلاش کن.")

    resolved, missing = resolve_categories(split_tokens(message.text or ""))
    if not resolved:
        return await message.answer("❌ هیچ دسته سرویس معتبری پیدا نشد.")

    removed = detach_categories_from_volume_package(int(package_id), resolved)
    summary = [f"✅ {removed} دسته سرویس از بسته حجمی #{package_id} حذف شد."]
    if missing:
        summary.append("نامعتبر: " + ", ".join(missing))
    await state.clear()
    await message.answer("\n".join(summary))
    await show_package_detail(message, int(package_id))


@router.callback_query(F.data.startswith("volume_pkg|edit|"))
async def package_management_edit_start(callback: CallbackQuery, state: FSMContext):
    if not is_admin(callback.from_user.id):
        return await callback.answer("دسترسی نداری.", show_alert=True)
    _, _, field, package_id = callback.data.split("|", 3)
    field_labels = {
        "name": "نام",
        "volume_gb": "حجم",
        "price": "قیمت",
        "sort_order": "اولویت",
    }
    if field not in field_labels:
        return await callback.answer("فیلد نامعتبر است.", show_alert=True)
    await state.update_data(edit_package_id=int(package_id), edit_package_field=field)
    await state.set_state(VolumePackageStates.waiting_for_value)
    await callback.message.answer(f"مقدار جدید برای «{field_labels[field]}» را بفرست:")
    await callback.answer()


@router.message(VolumePackageStates.waiting_for_value)
async def package_management_edit_receive(message: Message, state: FSMContext):
    if not is_admin(message.from_user.id):
        await state.clear()
        return

    data = await state.get_data()
    package_id = data.get("edit_package_id")
    field = data.get("edit_package_field")
    if not package_id or not field:
        await state.clear()
        await message.answer("خطای وضعیت. دوباره تلاش کن.")
        return

    value_text = (message.text or "").strip()
    value = value_text
    if field in {"volume_gb", "price", "sort_order"}:
        try:
            value = int(value_text)
        except Exception:
            await message.answer("این فیلد باید عدد باشد.")
            return

    ok = update_volume_package_field(int(package_id), field, value)
    await state.clear()
    if ok:
        await message.answer("✅ بسته حجمی بروزرسانی شد.", reply_markup=packages_keyboard(include_archived=False))
    else:
        await message.answer("❌ بروزرسانی انجام نشد.", reply_markup=packages_keyboard(include_archived=False))
