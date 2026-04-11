from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message
from typing import Union

from config import ADMINS
from keyboards.main_menu import admin_main_menu_keyboard
from services.db import (
    add_volume_package,
    get_volume_package,
    get_volume_packages,
    set_volume_package_archived,
    update_volume_package_field,
)

router = Router()


class VolumePackageStates(StatesGroup):
    waiting_for_add = State()
    waiting_for_value = State()


def is_admin(user_id: int) -> bool:
    return str(user_id) in {str(admin_id) for admin_id in ADMINS}


def format_price(amount: int) -> str:
    try:
        return f"{int(amount):,}"
    except Exception:
        return str(amount)


def packages_keyboard(include_archived: bool = False) -> InlineKeyboardMarkup:
    packages = get_volume_packages(include_archived=include_archived)
    rows = []
    for item in packages:
        active_icon = "✅" if int(item.get("is_active") or 0) == 1 else "🚫"
        label = (
            f"#{item['id']} | {active_icon} {item['name']} | "
            f"{item.get('volume_gb') or 0} گیگ | {format_price(item.get('price') or 0)}"
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
            [InlineKeyboardButton(text="✅/🚫 فعال‌سازی", callback_data=f"volume_pkg|toggle|{package_id}")],
            [InlineKeyboardButton(text=archive_text, callback_data=f"volume_pkg|archive|{package_id}")],
            [InlineKeyboardButton(text="🔙 بازگشت", callback_data=f"volume_pkg|list|{'archived' if archived else 'active'}")],
        ]
    )


def build_package_caption(package: dict) -> str:
    return (
        f"📚 بسته حجمی #{package['id']}\n"
        f"نام: {package.get('name') or '-'}\n"
        f"حجم: {package.get('volume_gb') or 0} گیگ\n"
        f"قیمت: {format_price(package.get('price') or 0)} تومان\n"
        f"اولویت: {package.get('sort_order') or 0}\n"
        f"وضعیت: {'فعال' if int(package.get('is_active') or 0) == 1 else 'غیرفعال'}\n"
        f"آرشیو: {'بله' if int(package.get('is_archived') or 0) == 1 else 'خیر'}\n"
        f"ایجاد: {package.get('created_at') or '-'}"
    )


async def show_package_list(target: Union[Message, CallbackQuery], include_archived: bool = False) -> None:
    text = "📚 بسته‌های حجمی آرشیوشده:" if include_archived else "📚 بسته‌های حجمی فعال:"
    keyboard = packages_keyboard(include_archived=include_archived)
    if isinstance(target, Message):
        await target.answer(text, reply_markup=keyboard)
    else:
        await target.message.answer(text, reply_markup=keyboard)
        await target.answer()


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
    await callback.message.answer(
        build_package_caption(package),
        reply_markup=package_detail_keyboard(package_id, archived=bool(package.get("is_archived"))),
    )
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
        await callback.message.answer(
            build_package_caption(updated_package),
            reply_markup=package_detail_keyboard(package_id, archived=bool(updated_package.get("is_archived"))),
        )
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
