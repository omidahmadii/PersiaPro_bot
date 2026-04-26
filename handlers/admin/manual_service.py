from html import escape
from typing import Optional

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message

from config import ADMINS
from keyboards.main_menu import admin_main_menu_keyboard
from services.db import (
    MANUAL_SERVICE_SOURCE,
    OFFLINE_MANUAL_SERVICE_SOURCE,
    create_manual_service_order,
    ensure_offline_user_for_account,
    get_account_credentials_by_username,
    get_plans_for_admin,
    get_user_by_id,
    search_users_for_admin,
)

router = Router()

MENU_TEXT = "🧩 ثبت سرویس دستی"

_DIGIT_TRANSLATION = str.maketrans(
    "۰۱۲۳۴۵۶۷۸۹٠١٢٣٤٥٦٧٨٩",
    "01234567890123456789",
)


class ManualServiceStates(StatesGroup):
    waiting_for_user_query = State()
    waiting_for_account_username = State()
    waiting_for_password = State()
    choosing_plan = State()


def is_admin(user_id: int) -> bool:
    return str(user_id) in {str(admin_id) for admin_id in ADMINS}


def normalize_digits(value: str) -> str:
    return str(value or "").translate(_DIGIT_TRANSLATION)


def normalize_account_username(value: str) -> str:
    return normalize_digits(value).strip().lstrip("@")


def format_price(amount: int) -> str:
    try:
        return f"{int(amount):,}"
    except Exception:
        return str(amount)


def user_display(user: dict) -> str:
    full_name = " ".join(
        part for part in [user.get("first_name") or "", user.get("last_name") or ""] if part
    ).strip()
    username = user.get("username")
    role = user.get("role") or "-"
    user_id = user.get("id")
    label = full_name or (f"@{username}" if username else "-")
    username_part = f"@{username}" if username else "-"
    return f"{label} | {username_part} | {user_id} | {role}"


def mode_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="👤 کاربر ربات", callback_data="manual_service|mode|bot")],
            [InlineKeyboardButton(text="📴 کاربر خارج از ربات", callback_data="manual_service|mode|offline")],
            [InlineKeyboardButton(text="❌ انصراف", callback_data="manual_service|cancel")],
        ]
    )


def users_keyboard(users: list[dict]) -> InlineKeyboardMarkup:
    rows = []
    for user in users:
        rows.append(
            [
                InlineKeyboardButton(
                    text=user_display(user)[:64],
                    callback_data=f"manual_service|user|{user['id']}",
                )
            ]
        )
    rows.append([InlineKeyboardButton(text="🔎 جست‌وجوی دوباره", callback_data="manual_service|mode|bot")])
    rows.append([InlineKeyboardButton(text="❌ انصراف", callback_data="manual_service|cancel")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def plans_keyboard() -> InlineKeyboardMarkup:
    rows = []
    for plan in get_plans_for_admin(include_archived=None):
        volume = plan.get("volume_gb") or 0
        price = format_price(plan.get("price") or 0)
        is_archived = int(plan.get("is_archived") or 0) == 1
        is_visible = int(plan.get("visible") or 0) == 1
        status = "آرشیو" if is_archived else ("فعال" if is_visible else "غیرفعال")
        label = f"#{plan['id']} | {status} | {plan.get('name') or '-'} | {volume}GB | {price}"
        rows.append(
            [
                InlineKeyboardButton(
                    text=label[:64],
                    callback_data=f"manual_service|plan|{plan['id']}",
                )
            ]
        )
    rows.append([InlineKeyboardButton(text="❌ انصراف", callback_data="manual_service|cancel")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def account_prompt(mode: str, user: Optional[dict] = None) -> str:
    if mode == "offline":
        return (
            "آیدی/یوزرنیم اکانت سرویس را بفرست.\n\n"
            "برای کاربر خارج از ربات، اگر مقدار عددی باشد، کاربر داخلی با آیدی منفی همان عدد ساخته می‌شود."
        )

    selected = user_display(user or {})
    return (
        f"کاربر انتخاب شد:\n<code>{escape(selected)}</code>\n\n"
        "حالا آیدی/یوزرنیم اکانت سرویس را بفرست."
    )


def password_prompt(account_username: str) -> str:
    return (
        f"رمز عبور اکانت <code>{escape(account_username)}</code> را بفرست.\n\n"
        "اگر این اکانت قبلا در ربات ثبت شده و می‌خواهی همان رمز قبلی بماند، فقط <code>-</code> بفرست."
    )


@router.message(F.text == MENU_TEXT)
async def manual_service_entry(message: Message, state: FSMContext):
    if not is_admin(message.from_user.id):
        return

    await state.clear()
    await message.answer(
        "ثبت سرویس دستی برای کدام نوع کاربر انجام شود؟",
        reply_markup=mode_keyboard(),
    )


@router.callback_query(F.data == "manual_service|cancel")
async def manual_service_cancel(callback: CallbackQuery, state: FSMContext):
    if not is_admin(callback.from_user.id):
        return await callback.answer("دسترسی ندارید.", show_alert=True)

    await state.clear()
    await callback.message.answer("ثبت سرویس دستی لغو شد.", reply_markup=admin_main_menu_keyboard())
    await callback.answer()


@router.callback_query(F.data.startswith("manual_service|mode|"))
async def manual_service_mode(callback: CallbackQuery, state: FSMContext):
    if not is_admin(callback.from_user.id):
        return await callback.answer("دسترسی ندارید.", show_alert=True)

    mode = callback.data.split("|")[2]
    await state.clear()
    await state.update_data(mode=mode)

    if mode == "bot":
        await state.set_state(ManualServiceStates.waiting_for_user_query)
        await callback.message.answer(
            "نام، یوزرنیم یا آیدی عددی کاربر ربات را بفرست تا جست‌وجو کنم."
        )
    elif mode == "offline":
        await state.set_state(ManualServiceStates.waiting_for_account_username)
        await callback.message.answer(account_prompt(mode))
    else:
        await callback.answer("حالت نامعتبر است.", show_alert=True)
        return

    await callback.answer()


@router.message(ManualServiceStates.waiting_for_user_query)
async def manual_service_user_query(message: Message, state: FSMContext):
    if not is_admin(message.from_user.id):
        await state.clear()
        return

    keyword = (message.text or "").strip()
    users = search_users_for_admin(keyword, include_offline=False, limit=10)
    if not users:
        await message.answer("کاربری با این مشخصات پیدا نشد. دوباره جست‌وجو کن.")
        return

    await message.answer(
        f"نتایج جست‌وجو برای <code>{escape(keyword)}</code>:",
        parse_mode="HTML",
        reply_markup=users_keyboard(users),
    )


@router.callback_query(F.data.startswith("manual_service|user|"))
async def manual_service_pick_user(callback: CallbackQuery, state: FSMContext):
    if not is_admin(callback.from_user.id):
        return await callback.answer("دسترسی ندارید.", show_alert=True)

    user_id = int(callback.data.split("|")[2])
    selected_user = get_user_by_id(user_id)
    if not selected_user or int(selected_user.get("id") or 0) <= 0 or selected_user.get("role") == "offline":
        return await callback.answer("کاربر انتخاب‌شده پیدا نشد.", show_alert=True)

    await state.update_data(target_user_id=user_id, target_user=selected_user, mode="bot")
    await state.set_state(ManualServiceStates.waiting_for_account_username)
    await callback.message.answer(account_prompt("bot", selected_user), parse_mode="HTML")
    await callback.answer()


@router.message(ManualServiceStates.waiting_for_account_username)
async def manual_service_account_username(message: Message, state: FSMContext):
    if not is_admin(message.from_user.id):
        await state.clear()
        return

    data = await state.get_data()
    mode = data.get("mode")
    account_username = normalize_account_username(message.text or "")
    if not account_username:
        await message.answer("آیدی/یوزرنیم اکانت معتبر نیست. دوباره بفرست.")
        return

    if mode == "offline":
        offline_result = ensure_offline_user_for_account(account_username)
        if not offline_result.get("ok"):
            await state.clear()
            await message.answer("ساخت کاربر خارج از ربات انجام نشد.", reply_markup=admin_main_menu_keyboard())
            return

        offline_user = offline_result["user"]
        await state.update_data(
            target_user_id=int(offline_user["id"]),
            target_user=offline_user,
            offline_user_created=bool(offline_result.get("created")),
        )
    elif not data.get("target_user_id"):
        await state.clear()
        await message.answer("کاربر ربات انتخاب نشده بود. دوباره شروع کن.", reply_markup=admin_main_menu_keyboard())
        return

    await state.update_data(account_username=account_username)
    await state.set_state(ManualServiceStates.waiting_for_password)
    await message.answer(password_prompt(account_username), parse_mode="HTML")


@router.message(ManualServiceStates.waiting_for_password)
async def manual_service_password(message: Message, state: FSMContext):
    if not is_admin(message.from_user.id):
        await state.clear()
        return

    data = await state.get_data()
    account_username = data.get("account_username")
    raw_password = (message.text or "").strip()

    if raw_password == "-":
        account = get_account_credentials_by_username(account_username)
        if not account or not account.get("password"):
            await message.answer("برای این اکانت رمز قبلی پیدا نشد. رمز عبور را کامل بفرست.")
            return
        password = account["password"]
    else:
        password = raw_password

    if not password:
        await message.answer("رمز عبور نمی‌تواند خالی باشد.")
        return

    await state.update_data(password=password)
    await state.set_state(ManualServiceStates.choosing_plan)
    await message.answer(
        "پلن این سرویس را انتخاب کن:",
        reply_markup=plans_keyboard(),
    )


@router.callback_query(F.data.startswith("manual_service|plan|"))
async def manual_service_pick_plan(callback: CallbackQuery, state: FSMContext):
    if not is_admin(callback.from_user.id):
        return await callback.answer("دسترسی ندارید.", show_alert=True)

    data = await state.get_data()
    plan_id = int(callback.data.split("|")[2])
    mode = data.get("mode")
    target_user_id = data.get("target_user_id")
    account_username = data.get("account_username")
    password = data.get("password")

    if not target_user_id or not account_username or not password:
        await state.clear()
        await callback.message.answer("اطلاعات ثبت سرویس ناقص بود. دوباره شروع کن.", reply_markup=admin_main_menu_keyboard())
        await callback.answer()
        return

    source = OFFLINE_MANUAL_SERVICE_SOURCE if mode == "offline" else MANUAL_SERVICE_SOURCE
    result = create_manual_service_order(
        user_id=int(target_user_id),
        plan_id=plan_id,
        account_username=account_username,
        password=password,
        admin_id=callback.from_user.id,
        service_source=source,
    )

    if not result.get("ok"):
        await state.clear()
        error = result.get("error")
        if error == "account_has_open_order":
            rows = result.get("open_orders") or []
            lines = [
                f"این اکانت قبلا سفارش باز دارد: <code>{escape(account_username)}</code>",
                "",
            ]
            for row in rows[:10]:
                lines.append(
                    f"سفارش #{row.get('id')} | user={row.get('user_id')} | status={escape(str(row.get('status') or '-'))}"
                )
            lines.append("")
            lines.append("برای جلوگیری از دوباره‌کاری، اول سفارش قبلی را بررسی یا لغو کن.")
            await callback.message.answer("\n".join(lines), parse_mode="HTML", reply_markup=admin_main_menu_keyboard())
        elif error == "plan_not_found":
            await callback.message.answer("پلن انتخاب‌شده پیدا نشد.", reply_markup=admin_main_menu_keyboard())
        elif error == "user_not_found":
            await callback.message.answer("کاربر مقصد پیدا نشد.", reply_markup=admin_main_menu_keyboard())
        else:
            await callback.message.answer("ثبت سرویس دستی انجام نشد.", reply_markup=admin_main_menu_keyboard())
        await callback.answer()
        return

    await state.clear()

    user = result["user"]
    plan = result["plan"]
    account_state = "جدید ساخته شد" if result.get("account_created") else "قبلی بود و به‌روزرسانی شد"
    offline_line = ""
    if mode == "offline":
        created = data.get("offline_user_created")
        offline_line = (
            f"\nکاربر خارج از ربات: <code>{user.get('id')}</code>"
            f" ({'ساخته شد' if created else 'از قبل وجود داشت'})"
        )

    await callback.message.answer(
        "\n".join(
            [
                "✅ سرویس دستی ثبت شد.",
                f"سفارش: <code>#{result['order_id']}</code>",
                f"اکانت: <code>{escape(result['account_username'])}</code>",
                f"وضعیت اکانت در ربات: {account_state}",
                f"کاربر: <code>{user.get('id')}</code> {escape(user_display(user))}",
                f"پلن: {escape(plan.get('name') or '-')}",
                f"منبع ثبت: <code>{escape(result.get('service_source') or '-')}</code>",
                offline_line.strip(),
                "",
                "تاریخ شروع و پایان این سفارش توسط scheduler مثل بقیه سرویس‌ها سینک می‌شود.",
            ]
        ).strip(),
        parse_mode="HTML",
        reply_markup=admin_main_menu_keyboard(),
    )
    await callback.answer("ثبت شد.")
