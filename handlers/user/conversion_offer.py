from __future__ import annotations

import logging
from html import escape
from typing import Optional, Union

from aiogram import F, Router
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message

from handlers.user.start import is_user_member, join_channel_keyboard
from keyboards.main_menu import main_menu_keyboard_for_user
from services.admin_notifier import send_message_to_admins
from services.conversion_offer import (
    apply_conversion,
    get_conversion_disabled_text,
    get_conversion_menu_title,
    get_conversion_service_for_user,
    get_conversion_text,
    get_eligible_conversion_services,
    is_conversion_menu_enabled,
    log_conversion_cancelled,
    log_conversion_selected,
    log_conversion_viewed,
)

router = Router()
logger = logging.getLogger(__name__)


def _format_service_label(service: dict) -> str:
    username = str(service.get("username") or f"#{service['id']}")
    plan_name = str(service.get("plan_name") or "-")
    return f"{username} | {plan_name}"[:64]


def _format_price(amount: Optional[Union[int, float]]) -> str:
    try:
        return f"{int(amount or 0):,}"
    except Exception:
        return str(amount or 0)


def _format_text(value: object) -> str:
    text = str(value or "").strip()
    if not text:
        return "-"
    return escape(text)


def _format_code(value: object) -> str:
    return f"<code>{_format_text(value)}</code>"


def _format_volume_text(service: Optional[dict]) -> str:
    if not service:
        return "-"

    remaining = str(service.get("remaining_volume_display") or "").strip()
    if not remaining:
        return "-"
    if remaining == "نامحدود":
        return remaining
    return f"{remaining} گیگ"


def _build_conversion_admin_message(
    callback: CallbackQuery,
    previous_service: Optional[dict],
    new_service: Optional[dict],
) -> str:
    user_id = callback.from_user.id
    full_name = " ".join(
        part.strip()
        for part in [callback.from_user.first_name or "", callback.from_user.last_name or ""]
        if str(part).strip()
    )
    if not full_name:
        full_name = str(user_id)

    telegram_username = f"@{escape(callback.from_user.username)}" if callback.from_user.username else "-"
    previous_service = previous_service or {}
    new_service = new_service or {}

    lines = [
        "🔁 <b>تبدیل سرویس انجام شد</b>",
        f"👤 کاربر: <a href='tg://user?id={user_id}'>{escape(full_name)}</a>",
        f"🆔 آیدی عددی: <code>{user_id}</code>",
        f"🔹 یوزرنیم تلگرام: {telegram_username}",
        "",
        "📦 <b>سرویس قبلی</b>",
        f"• شماره سفارش: {_format_code(previous_service.get('id'))}",
        f"• یوزرنیم سرویس: {_format_code(previous_service.get('username'))}",
        f"• پلن: {_format_text(previous_service.get('plan_name'))}",
        f"• تاریخ شروع: {_format_code(previous_service.get('starts_at'))}",
        f"• تاریخ پایان: {_format_code(previous_service.get('expires_at'))}",
        f"• روز باقی‌مانده: {_format_code(previous_service.get('days_remaining'))}",
        f"• حجم باقی‌مانده: {_format_text(_format_volume_text(previous_service))}",
        f"• مبلغ ثبت‌شده: <code>{_format_price(previous_service.get('price'))}</code> تومان",
        "",
        "🆕 <b>سرویس جدید</b>",
        f"• شماره سفارش جدید: {_format_code(new_service.get('id'))}",
    ]
    return "\n".join(lines)


def _services_keyboard(services: list[dict]) -> InlineKeyboardMarkup:
    rows = [
        [
            InlineKeyboardButton(
                text=f"انتخاب این سرویس • {_format_service_label(service)}",
                callback_data=f"conversion_select:{service['id']}",
            )
        ]
        for service in services
    ]
    rows.append([InlineKeyboardButton(text="بروزرسانی لیست", callback_data="conversion_list")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def _detail_keyboard(service_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="تایید و فعال‌سازی", callback_data=f"conversion_confirm:{service_id}")],
            [InlineKeyboardButton(text="انصراف", callback_data=f"conversion_cancel:{service_id}")],
            [InlineKeyboardButton(text="بازگشت به لیست", callback_data="conversion_list")],
        ]
    )


def _final_confirm_keyboard(service_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="بله", callback_data=f"conversion_apply:{service_id}")],
            [InlineKeyboardButton(text="خیر", callback_data=f"conversion_decline:{service_id}")],
        ]
    )


async def _membership_guard(message: Union[Message, CallbackQuery]) -> bool:
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


async def _ensure_conversion_available(target: Union[Message, CallbackQuery]) -> bool:
    if is_conversion_menu_enabled():
        return True

    text = get_conversion_disabled_text()
    if isinstance(target, CallbackQuery):
        await target.answer()
        await target.message.answer(text, reply_markup=main_menu_keyboard_for_user(target.from_user.id))
    else:
        await target.answer(text, reply_markup=main_menu_keyboard_for_user(target.from_user.id))
    return False


def _build_services_text(services: list[dict]) -> str:
    lines = [get_conversion_text("message_conversion_list"), ""]
    for index, service in enumerate(services, start=1):
        remaining_volume = service.get("remaining_volume_display") or "-"
        remaining_volume_text = remaining_volume if remaining_volume == "نامحدود" else f"{remaining_volume} گیگ"
        lines.extend(
            [
                f"{index}. سرویس: <code>{service.get('username') or service['id']}</code>",
                f"پلن فعلی: {service.get('plan_name') or '-'}",
                f"تاریخ پایان فعلی: {service.get('expires_at') or '-'}",
                f"روز باقی‌مانده: {service.get('days_remaining') or 0}",
                f"حجم باقی‌مانده: {remaining_volume_text}",
                "",
            ]
        )
    return "\n".join(lines).strip()


def _build_detail_text(service: dict) -> str:
    return get_conversion_text("message_conversion_detail", service).strip()


def _build_confirm_text(service: dict) -> str:
    return get_conversion_text("message_conversion_confirm", service).strip()


async def _answer_callback(callback: CallbackQuery, text: Optional[str] = None) -> None:
    if text:
        await callback.answer(text)
        return
    await callback.answer()


async def _show_service_detail(
    callback: CallbackQuery,
    service_id: int,
    *,
    callback_notice: Optional[str] = None,
    log_selection: bool = False,
) -> None:
    service, eligibility = get_conversion_service_for_user(callback.from_user.id, service_id)
    if not service or not eligibility.get("is_eligible"):
        await callback.message.edit_text(get_conversion_text("message_conversion_no_longer_eligible"))
        await _answer_callback(callback, callback_notice)
        return

    if log_selection:
        log_conversion_selected(service)

    await callback.message.edit_text(
        _build_detail_text(service),
        parse_mode="HTML",
        reply_markup=_detail_keyboard(service_id),
    )
    await _answer_callback(callback, callback_notice)


async def _show_services_list(
    target: Union[Message, CallbackQuery],
    *,
    edit: bool = False,
    callback_notice: Optional[str] = None,
) -> None:
    services = get_eligible_conversion_services(target.from_user.id)
    if not services:
        text = get_conversion_text("message_conversion_no_services")
        if isinstance(target, CallbackQuery):
            if edit:
                await target.message.edit_text(text)
            else:
                await target.message.answer(text, reply_markup=main_menu_keyboard_for_user(target.from_user.id))
            await _answer_callback(target, callback_notice)
        else:
            await target.answer(text, reply_markup=main_menu_keyboard_for_user(target.from_user.id))
        return

    log_conversion_viewed(target.from_user.id, services)
    text = _build_services_text(services)
    markup = _services_keyboard(services)

    if isinstance(target, CallbackQuery):
        if edit:
            await target.message.edit_text(text, parse_mode="HTML", reply_markup=markup)
        else:
            await target.message.answer(text, parse_mode="HTML", reply_markup=markup)
        await _answer_callback(target, callback_notice)
        return

    await target.answer(text, parse_mode="HTML", reply_markup=markup)


@router.message(lambda message: (message.text or "").strip() == get_conversion_menu_title())
async def conversion_entry(message: Message):
    if not await _membership_guard(message):
        return
    if not await _ensure_conversion_available(message):
        return
    await _show_services_list(message)


@router.callback_query(F.data == "conversion_list")
async def conversion_list(callback: CallbackQuery):
    if not await _membership_guard(callback):
        return
    if not await _ensure_conversion_available(callback):
        return
    await _show_services_list(callback, edit=True)


@router.callback_query(F.data.startswith("conversion_select:"))
async def conversion_select(callback: CallbackQuery):
    if not await _membership_guard(callback):
        return
    if not await _ensure_conversion_available(callback):
        return

    service_id = int(callback.data.split(":", 1)[1])
    await _show_service_detail(callback, service_id, log_selection=True)


@router.callback_query(F.data.startswith("conversion_confirm:"))
async def conversion_confirm(callback: CallbackQuery):
    if not await _membership_guard(callback):
        return
    if not await _ensure_conversion_available(callback):
        return

    service_id = int(callback.data.split(":", 1)[1])
    service, eligibility = get_conversion_service_for_user(callback.from_user.id, service_id)
    if not service or not eligibility.get("is_eligible"):
        await callback.message.edit_text(get_conversion_text("message_conversion_no_longer_eligible"))
        await callback.answer()
        return

    await callback.message.edit_text(
        _build_confirm_text(service),
        parse_mode="HTML",
        reply_markup=_final_confirm_keyboard(service_id),
    )
    await callback.answer()


@router.callback_query(F.data.startswith("conversion_cancel:"))
async def conversion_cancel(callback: CallbackQuery):
    if not await _membership_guard(callback):
        return
    if not await _ensure_conversion_available(callback):
        return

    service_id = int(callback.data.split(":", 1)[1])
    service, _ = get_conversion_service_for_user(callback.from_user.id, service_id)
    if service:
        log_conversion_cancelled(service)

    await _show_services_list(
        callback,
        edit=True,
        callback_notice=get_conversion_text("message_conversion_cancelled"),
    )


@router.callback_query(F.data.startswith("conversion_decline:"))
async def conversion_decline(callback: CallbackQuery):
    if not await _membership_guard(callback):
        return
    if not await _ensure_conversion_available(callback):
        return

    service_id = int(callback.data.split(":", 1)[1])
    await _show_service_detail(callback, service_id)


@router.callback_query(F.data.startswith("conversion_apply:"))
async def conversion_apply(callback: CallbackQuery):
    if not await _membership_guard(callback):
        return
    if not await _ensure_conversion_available(callback):
        return

    service_id = int(callback.data.split(":", 1)[1])
    result = apply_conversion(callback.from_user.id, service_id)

    if result.get("ok"):
        if not result.get("already_converted"):
            try:
                previous_service, _ = get_conversion_service_for_user(callback.from_user.id, service_id)
                await send_message_to_admins(
                    _build_conversion_admin_message(
                        callback,
                        previous_service or result.get("service"),
                        result.get("new_service"),
                    )
                )
            except Exception:
                logger.warning(
                    "Failed to notify admins about conversion. user_id=%s service_id=%s",
                    callback.from_user.id,
                    service_id,
                    exc_info=True,
                )

        text = get_conversion_text("message_conversion_success", result.get("new_service"))
        if result.get("already_converted"):
            text = get_conversion_text("message_conversion_success", result.get("new_service") or result.get("service"))
        if result.get("ibs_warning"):
            text += "\n\nاگر سرویس تا دقایقی دیگر به‌روزرسانی نشد، از بخش پشتیبانی پیگیری کنید."

        await callback.message.edit_text(text)
        await callback.message.answer(
            "بازگشت به منوی اصلی.",
            reply_markup=main_menu_keyboard_for_user(callback.from_user.id),
        )
        await callback.answer("انجام شد.")
        return

    error = result.get("error")
    if error == "no_longer_eligible":
        await callback.message.edit_text(get_conversion_text("message_conversion_no_longer_eligible"))
    elif error in {"feature_disabled", "target_plan_unavailable"}:
        await callback.message.edit_text(get_conversion_disabled_text())
    else:
        await callback.message.edit_text(get_conversion_text("message_conversion_failed"))

    await callback.answer()
