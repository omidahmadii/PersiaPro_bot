from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message
from typing import Optional, Union

from handlers.user.start import is_user_member, join_channel_keyboard
from keyboards.main_menu import main_menu_keyboard_for_user
from services.admin_notifier import send_message_to_admins
from services.db import get_active_volume_packages, get_volume_services_for_user
from services.order_workflow import purchase_volume_package
from services.runtime_settings import get_bool_setting, get_text_setting

router = Router()

DEFAULT_EXTRA_VOLUME_DISABLED_TEXT = "در حال حاضر خرید حجم اضافه غیر فعال می باشد."


class ExtraVolumeStates(StatesGroup):
    choosing_service = State()
    choosing_package = State()
    confirming = State()


def format_price(amount: int) -> str:
    try:
        return f"{int(amount):,}"
    except Exception:
        return str(amount)


def format_gb_from_mb(value_mb: int) -> str:
    return f"{round((value_mb or 0) / 1024, 2)}"


def status_label(status: Optional[str]) -> str:
    labels = {
        "active": "فعال",
        "waiting_for_renewal": "در انتظار تمدید",
        "waiting_for_renewal_not_paid": "تمدید در انتظار پرداخت",
        "reserved": "ذخیره",
    }
    return labels.get(str(status or "").strip(), str(status or "-"))


def services_keyboard(services: list[dict]) -> InlineKeyboardMarkup:
    rows = []
    for service in services:
        total_volume = int(service.get("volume_gb") or 0) + int(service.get("extra_volume_gb") or 0)
        rows.append([
            InlineKeyboardButton(
                text=(
                    f"{service['username']} | {status_label(service.get('status'))} | "
                    f"{service.get('plan_name') or '-'} | {total_volume} گیگ"
                ),
                callback_data=f"extra_volume|service|{service['id']}",
            )
        ])
    rows.append([InlineKeyboardButton(text="🔙 منوی اصلی", callback_data="extra_volume|main")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def packages_keyboard(packages: list[dict]) -> InlineKeyboardMarkup:
    rows = []
    for package in packages:
        rows.append([
            InlineKeyboardButton(
                text=f"{package['name']} | {package['volume_gb']} گیگ | {format_price(package['price'])} تومان",
                callback_data=f"extra_volume|package|{package['id']}",
            )
        ])
    rows.append([InlineKeyboardButton(text="🔙 بازگشت", callback_data="extra_volume|back|services")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def confirm_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="✅ تایید خرید حجم", callback_data="extra_volume|confirm")],
            [InlineKeyboardButton(text="🔙 بازگشت", callback_data="extra_volume|back|packages")],
        ]
    )


def is_extra_volume_enabled() -> bool:
    return get_bool_setting("feature_extra_volume_enabled", default=True)


def get_extra_volume_disabled_text() -> str:
    return get_text_setting("message_extra_volume_disabled", DEFAULT_EXTRA_VOLUME_DISABLED_TEXT)


async def ensure_extra_volume_enabled_message(message: Message, state: FSMContext) -> bool:
    if is_extra_volume_enabled():
        return True

    await state.clear()
    await message.answer(
        get_extra_volume_disabled_text(),
        reply_markup=main_menu_keyboard_for_user(message.from_user.id),
    )
    return False


async def ensure_extra_volume_enabled_callback(callback: CallbackQuery, state: FSMContext) -> bool:
    if is_extra_volume_enabled():
        return True

    await state.clear()
    await callback.message.answer(
        get_extra_volume_disabled_text(),
        reply_markup=main_menu_keyboard_for_user(callback.from_user.id),
    )
    await callback.answer()
    return False


async def membership_guard(message: Union[Message, CallbackQuery]) -> bool:
    user_id = message.from_user.id
    if await is_user_member(user_id):
        return True

    if isinstance(message, CallbackQuery):
        await message.answer("ابتدا عضو کانال شوید.", show_alert=True)
        await message.message.answer(
            "🔒 برای استفاده از این بخش باید عضو کانال PersiaPro باشید.",
            reply_markup=join_channel_keyboard(),
        )
    else:
        await message.answer(
            "🔒 برای استفاده از این بخش باید عضو کانال PersiaPro باشید.",
            reply_markup=join_channel_keyboard(),
        )
    return False


def build_service_summary(service: dict) -> str:
    base_volume = int(service.get("volume_gb") or 0)
    extra_volume = int(service.get("extra_volume_gb") or 0)
    total_volume = base_volume + extra_volume
    used_mb = int(service.get("usage_total_mb") or 0)
    return (
        f"👤 سرویس: <code>{service['username']}</code>\n"
        f"📦 پلن: {service.get('plan_name') or '-'}\n"
        f"📍 وضعیت: {status_label(service.get('status'))}\n"
        f"📊 حجم پایه: {base_volume} گیگ\n"
        f"➕ حجم اضافه فعلی: {extra_volume} گیگ\n"
        f"🧮 مجموع حجم فعلی: {total_volume} گیگ\n"
        f"📈 مصرف فعلی: {format_gb_from_mb(used_mb)} گیگ\n\n"
        "این حجم فقط روی همین سفارش اعمال می‌شود و به دوره یا سرویس بعدی منتقل نخواهد شد."
    )


def build_confirmation_text(service: dict, package: dict) -> str:
    current_extra = int(service.get("extra_volume_gb") or 0)
    new_extra = current_extra + int(package.get("volume_gb") or 0)
    return (
        f"{build_service_summary(service)}\n\n"
        f"🛒 بسته انتخابی: {package['name']}\n"
        f"📦 حجم بسته: {package['volume_gb']} گیگ\n"
        f"💰 مبلغ: {format_price(package['price'])} تومان\n"
        f"🔢 حجم اضافه جدید این سفارش بعد از خرید: {new_extra} گیگ\n\n"
        "اگر تایید کنی، مبلغ از کیف پولت کم می‌شود و حجم همین حالا روی همین سرویس اعمال می‌شود."
    )


@router.message(F.text == "📦 خرید حجم اضافه")
async def extra_volume_entry(message: Message, state: FSMContext):
    if not await membership_guard(message):
        return
    if not await ensure_extra_volume_enabled_message(message, state):
        return

    services = get_volume_services_for_user(message.from_user.id)
    packages = get_active_volume_packages(user_id=message.from_user.id)
    if not services:
        await state.clear()
        await message.answer(
            "سرویسی که امکان خرید حجم اضافه برای آن باشد پیدا نشد.",
            reply_markup=main_menu_keyboard_for_user(message.from_user.id),
        )
        return
    if not packages:
        await state.clear()
        await message.answer(
            "فعلاً بسته حجمی فعالی برای فروش ثبت نشده است.",
            reply_markup=main_menu_keyboard_for_user(message.from_user.id),
        )
        return

    await state.clear()
    await state.update_data(extra_volume_services=services)
    await state.set_state(ExtraVolumeStates.choosing_service)
    await message.answer(
        "سرویسی که می‌خواهی برایش حجم اضافه بخری را انتخاب کن:",
        parse_mode="HTML",
        reply_markup=services_keyboard(services),
    )


@router.callback_query(F.data == "extra_volume|main")
async def extra_volume_back_main(callback: CallbackQuery, state: FSMContext):
    await state.clear()
    await callback.message.answer(
        "بازگشت به منوی اصلی.",
        reply_markup=main_menu_keyboard_for_user(callback.from_user.id),
    )
    await callback.answer()


@router.callback_query(F.data.startswith("extra_volume|service|"))
async def extra_volume_choose_service(callback: CallbackQuery, state: FSMContext):
    if not await membership_guard(callback):
        return
    if not await ensure_extra_volume_enabled_callback(callback, state):
        return

    service_id = int(callback.data.split("|")[2])
    data = await state.get_data()
    services = data.get("extra_volume_services") or get_volume_services_for_user(callback.from_user.id)
    packages = get_active_volume_packages(user_id=callback.from_user.id, service_id=service_id)
    selected_service = next((service for service in services if int(service["id"]) == service_id), None)
    if not selected_service:
        return await callback.answer("سرویس پیدا نشد.", show_alert=True)
    if not packages:
        return await callback.message.answer(
            "برای این سرویس بسته حجمی قابل خریدی ثبت نشده است.",
            reply_markup=services_keyboard(services),
        )

    await state.update_data(selected_service=selected_service, extra_volume_packages=packages)
    await state.set_state(ExtraVolumeStates.choosing_package)
    await callback.message.answer(
        f"{build_service_summary(selected_service)}\n\nبسته حجمی مورد نظر را انتخاب کن:",
        parse_mode="HTML",
        reply_markup=packages_keyboard(packages),
    )
    await callback.answer()


@router.callback_query(F.data.startswith("extra_volume|package|"))
async def extra_volume_choose_package(callback: CallbackQuery, state: FSMContext):
    if not await ensure_extra_volume_enabled_callback(callback, state):
        return

    package_id = int(callback.data.split("|")[2])
    data = await state.get_data()
    selected_service = data.get("selected_service")
    if not selected_service:
        return await callback.answer("اطلاعات سرویس پیدا نشد.", show_alert=True)

    packages = get_active_volume_packages(
        user_id=callback.from_user.id,
        service_id=int(selected_service["id"]),
    )
    selected_package = next((package for package in packages if int(package["id"]) == package_id), None)
    if not selected_service or not selected_package:
        return await callback.answer("اطلاعات خرید پیدا نشد.", show_alert=True)

    await state.update_data(selected_package=selected_package)
    await state.set_state(ExtraVolumeStates.confirming)
    await callback.message.answer(
        build_confirmation_text(selected_service, selected_package),
        parse_mode="HTML",
        reply_markup=confirm_keyboard(),
    )
    await callback.answer()


@router.callback_query(F.data.startswith("extra_volume|back|"))
async def extra_volume_back(callback: CallbackQuery, state: FSMContext):
    if not await ensure_extra_volume_enabled_callback(callback, state):
        return

    target = callback.data.split("|")[2]
    data = await state.get_data()

    if target == "services":
        services = data.get("extra_volume_services") or get_volume_services_for_user(callback.from_user.id)
        await state.set_state(ExtraVolumeStates.choosing_service)
        await callback.message.answer(
            "سرویسی که می‌خواهی برایش حجم اضافه بخری را انتخاب کن:",
            reply_markup=services_keyboard(services),
        )
        return await callback.answer()

    if target == "packages":
        selected_service = data.get("selected_service")
        if not selected_service:
            return await callback.answer("اطلاعات سرویس پیدا نشد.", show_alert=True)
        packages = get_active_volume_packages(
            user_id=callback.from_user.id,
            service_id=int(selected_service["id"]),
        )
        await state.set_state(ExtraVolumeStates.choosing_package)
        await callback.message.answer(
            f"{build_service_summary(selected_service)}\n\nبسته حجمی مورد نظر را انتخاب کن:",
            parse_mode="HTML",
            reply_markup=packages_keyboard(packages),
        )
        return await callback.answer()

    await callback.answer()


@router.callback_query(F.data == "extra_volume|confirm")
async def extra_volume_confirm(callback: CallbackQuery, state: FSMContext):
    if not await ensure_extra_volume_enabled_callback(callback, state):
        return

    data = await state.get_data()
    selected_service = data.get("selected_service")
    selected_package = data.get("selected_package")
    if not selected_service or not selected_package:
        await state.clear()
        await callback.message.answer(
            "اطلاعات خرید حجم اضافه پیدا نشد.",
            reply_markup=main_menu_keyboard_for_user(callback.from_user.id),
        )
        return await callback.answer()

    result = purchase_volume_package(
        user_id=callback.from_user.id,
        order_id=int(selected_service["id"]),
        package_id=int(selected_package["id"]),
    )
    if not result.get("ok"):
        if result.get("error") == "insufficient_balance":
            await callback.message.answer(
                "موجودی کیف پولت برای این بسته کافی نیست.\n"
                f"💳 موجودی فعلی: {format_price(result.get('current_balance') or 0)} تومان\n"
                f"💰 مبلغ بسته: {format_price(result.get('package_price') or 0)} تومان\n"
                f"💵 مبلغ موردنیاز: {format_price(result.get('required') or 0)} تومان\n\n"
                "اول کیف پول را شارژ کن و بعد دوباره همین مسیر را انجام بده.",
                reply_markup=main_menu_keyboard_for_user(callback.from_user.id),
            )
        else:
            await callback.message.answer(
                "خرید حجم اضافه انجام نشد. دوباره تلاش کن.",
                reply_markup=main_menu_keyboard_for_user(callback.from_user.id),
            )
        await state.clear()
        return await callback.answer()

    await callback.message.answer(
        "✅ خرید حجم اضافه انجام شد.\n"
        f"👤 سرویس: <code>{result['username']}</code>\n"
        f"🛒 بسته: {result['package_name']}\n"
        f"📦 حجم اضافه‌شده: {result['volume_gb']} گیگ\n"
        f"➕ مجموع حجم اضافه فعلی این سفارش: {result['new_extra_volume_gb']} گیگ\n"
        f"💳 موجودی جدید: {format_price(result['new_balance'])} تومان",
        parse_mode="HTML",
        reply_markup=main_menu_keyboard_for_user(callback.from_user.id),
    )

    admin_text = (
        "📦 خرید حجم اضافه ثبت شد\n"
        f"👤 کاربر: <a href='tg://user?id={callback.from_user.id}'>{callback.from_user.id}</a>\n"
        f"🆔 سرویس: <code>{result['username']}</code>\n"
        f"🛒 بسته: {result['package_name']}\n"
        f"📦 حجم: {result['volume_gb']} گیگ\n"
        f"💰 مبلغ: {format_price(result['price'])} تومان"
    )
    await send_message_to_admins(admin_text)

    if result.get("ibs_warning"):
        await callback.message.answer(
            "حجم در دیتابیس ثبت شد ولی اعمال تنظیمات سرویس روی IBS با هشدار همراه بود:\n"
            f"<code>{result['ibs_warning']}</code>",
            parse_mode="HTML",
        )

    await state.clear()
    await callback.answer("خرید انجام شد.")
