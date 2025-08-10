import asyncio
import datetime
from services.admin_notifier import send_message_to_admins

import jdatetime
from aiogram import Router, F, Bot
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import Message, ReplyKeyboardMarkup, KeyboardButton

from keyboards.user_main_menu import user_main_menu_keyboard
from services import IBSng  # database access layer and IBSng api wrapper
from services.IBSng import change_group
from services.db import (
    get_all_plans,
    get_user_balance,
    update_user_balance,
    get_services_for_renew,
    insert_renewed_order,
    update_order_status,
)
from config import BOT_TOKEN

router = Router()


class RenewStates(StatesGroup):
    wait_service = State()
    wait_plan = State()
    confirming = State()


def confirm_keyboard() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text="✅ بله"), KeyboardButton(text="❌ خیر")]],
        resize_keyboard=True,
        one_time_keyboard=True,
    )


# ────────────────────────────────────────────────────────────────────────────────
# Entry‑point handler ─ Request to renew a service
# ────────────────────────────────────────────────────────────────────────────────
@router.message(F.text == "📄 تمدید سرویس")
async def handle_renew_request(message: Message, state: FSMContext):
    """Ask the user which service they want to renew and start timeout."""

    user_id = message.from_user.id
    services = get_services_for_renew(user_id)

    if not services:
        await message.answer("⚠️ هیچ سرویسی برای تمدید پیدا نشد.")
        return

    # Build keyboard: one button per service username
    buttons = [[KeyboardButton(text=str(srv["username"]))] for srv in services]
    buttons.append([KeyboardButton(text="بازگشت به منوی اصلی")])
    keyboard = ReplyKeyboardMarkup(resize_keyboard=True, keyboard=buttons)

    # FSM preparation
    await state.set_state(RenewStates.wait_service)
    await state.update_data(services=services)

    # Send prompt + set timeout task
    await message.answer("لطفاً سرویسی که می‌خوای تمدیدش کنی رو انتخاب کن:", reply_markup=keyboard)

    task = asyncio.create_task(_timeout_cancel(state, message.chat.id))
    await state.update_data(timeout_task=task)


# ────────────────────────────────────────────────────────────────────────────────
# Step 1 ─ Choose service
# ────────────────────────────────────────────────────────────────────────────────
@router.message(RenewStates.wait_service)
async def choose_service(message: Message, state: FSMContext):
    """Store selected service or let user go back."""

    if message.text == "بازگشت به منوی اصلی":
        await _cancel_timeout(state)
        await state.clear()
        return await message.answer("بازگشت به منوی اصلی", reply_markup=user_main_menu_keyboard())

    data = await state.get_data()
    services = data.get("services", [])
    selected_service = next((s for s in services if str(s["username"]) == message.text.strip()), None)

    if not selected_service:
        # Re‑send service list if input invalid
        buttons = [[KeyboardButton(text=str(srv["username"]))] for srv in services]
        buttons.append([KeyboardButton(text="بازگشت به منوی اصلی")])
        keyboard = ReplyKeyboardMarkup(resize_keyboard=True, keyboard=buttons)
        await message.answer("❌ سرویس نامعتبره. لطفاً یکی از گزینه‌ها رو انتخاب کن.", reply_markup=keyboard)
        return

    # Fetch plans once and current balance; store in FSM data
    plans = get_all_plans()
    if not plans:
        await _cancel_timeout(state)
        await state.clear()
        return await message.answer("❌ هیچ پلنی برای تمدید موجود نیست.")

    user_balance = get_user_balance(message.from_user.id)
    await state.update_data(selected_service=selected_service, user_balance=user_balance)

    # Cancel previous timeout and set a new one for next stage
    await _cancel_timeout(state)

    buttons = [[KeyboardButton(text=f"{name} - {price} تومان")] for _, name, *_, price in plans]
    buttons.append([KeyboardButton(text="بازگشت به منوی اصلی")])
    keyboard = ReplyKeyboardMarkup(resize_keyboard=True, keyboard=buttons)

    await state.set_state(RenewStates.wait_plan)
    await message.answer("پلن موردنظر برای تمدید رو انتخاب کن:", reply_markup=keyboard)

    task = asyncio.create_task(_timeout_cancel(state, message.chat.id))
    await state.update_data(timeout_task=task)


# ────────────────────────────────────────────────────────────────────────────────
# Step 2 ─ Choose plan
# ────────────────────────────────────────────────────────────────────────────────
@router.message(RenewStates.wait_plan)
async def choose_plan(message: Message, state: FSMContext):
    if message.text == "بازگشت به منوی اصلی":
        await _cancel_timeout(state)
        await state.clear()
        return await message.answer("بازگشت به منوی اصلی", reply_markup=user_main_menu_keyboard())

    plans = get_all_plans()
    selected_plan = next((p for p in plans if p[1] in message.text), None)  # Using simple match per request

    if not selected_plan:
        buttons = [[KeyboardButton(text=f"{name} - {price} تومان")] for _, name, *_, price in plans]
        buttons.append([KeyboardButton(text="بازگشت به منوی اصلی")])
        keyboard = ReplyKeyboardMarkup(resize_keyboard=True, keyboard=buttons)
        return await message.answer("پلن معتبر نیست، لطفا دوباره انتخاب کنید.", reply_markup=keyboard)

    # Balance check (we already fetched balance earlier)
    data = await state.get_data()
    user_balance: int = data.get("user_balance", 0)
    plan_price = selected_plan[5]

    if user_balance < plan_price:
        buttons = [[KeyboardButton(text=f"{name} - {price} تومان")] for _, name, *_, price in plans]
        buttons.append([KeyboardButton(text="بازگشت به منوی اصلی")])
        keyboard = ReplyKeyboardMarkup(resize_keyboard=True, keyboard=buttons)
        return await message.answer(
            f"❌ موجودی کافی نیست. برای این پلن به {plan_price} تومان نیاز داری.", reply_markup=keyboard
        )

    # Cancel previous timeout, prepare confirmation
    await _cancel_timeout(state)

    await state.update_data(selected_plan=selected_plan)
    await state.set_state(RenewStates.confirming)
    await message.answer(
        f"شما در حال خریداری سرویس {selected_plan[1]} به مبلغ {plan_price} تومان می‌باشید. آیا مطمئن هستید؟",
        reply_markup=confirm_keyboard(),
    )


# ────────────────────────────────────────────────────────────────────────────────
# Step 3 ─ Confirmation and renew logic
# ────────────────────────────────────────────────────────────────────────────────
@router.message(RenewStates.confirming)
async def confirm_and_renew(message: Message, state: FSMContext):
    if message.text.strip() == "❌ خیر":
        await state.clear()
        return await message.answer("خرید لغو شد ✅", reply_markup=user_main_menu_keyboard())

    if message.text.strip() != "✅ بله":
        return await message.answer("لطفاً فقط از دکمه‌های «✅ بله» یا «❌ خیر» استفاده کنید.",
                                    reply_markup=confirm_keyboard())

    data = await state.get_data()
    selected_plan = data.get("selected_plan")
    selected_service = data.get("selected_service")
    user_balance: int = data.get("user_balance", 0)

    # Safety check
    if not selected_plan or not selected_service:
        await state.clear()
        return await message.answer("❌ خطا در دریافت اطلاعات انتخاب‌شده. لطفاً دوباره تلاش کنید.")

    # Perform renewal based on expiration state
    result_text = await _process_renewal(message.from_user.id, selected_service, selected_plan, user_balance)

    await state.clear()
    await message.answer(result_text, reply_markup=user_main_menu_keyboard())


# ────────────────────────────────────────────────────────────────────────────────
# Helper functions
# ────────────────────────────────────────────────────────────────────────────────
async def _process_renewal(user_id: int, service: dict, plan: tuple, user_balance: int) -> str:
    """Renew expired service immediately or queue renewal for active service."""

    plan_id, plan_name, *_rest, plan_duration, plan_price = plan

    service_id = service["id"]
    service_username = str(service["username"])

    # Determine expiration accurately using Gregorian datetime
    expires_at_greg = jdatetime.datetime.strptime(service["expires_at"], "%Y-%m-%d %H:%M").togregorian()
    is_expired = service["status"] == "expired" or expires_at_greg < datetime.datetime.now()

    new_balance = user_balance - plan_price
    update_user_balance(user_id, new_balance)

    if is_expired:
        await _renew_expired_service(user_id, service_id, service_username, plan_id, plan_name, plan_duration,
                                     plan_price)
        return "✅ سرویس با موفقیت تمدید شد. بازگشت به منوی اصلی"

    await _queue_active_service(user_id, service_id, service_username, plan_id, plan_name, plan_duration, plan_price)

    return (
        "✅ سرویس در وضعیت ذخیره قرار گرفت و پس از پایان دوره‌ی قبلی به صورت خودکار فعال خواهد شد.\n"
        "بازگشت به منوی اصلی"
    )


async def _renew_expired_service(
        user_id: int,
        service_id: int,
        username: str,
        plan_id: int,
        plan_name: str,
        plan_duration: int,
        plan_price: int,
):
    """Immediately renew an expired service."""

    update_order_status(order_id=service_id, new_status="renewed")
    insert_renewed_order(
        user_id=user_id,
        plan_id=plan_id,
        username=username,
        price=plan_price,
        status="active",
        is_renewal_of_order=service_id,
    )

    # Reset in IBSng and change group
    IBSng.reset_account_client(username=username)
    group_name = f"{plan_duration}-Month"
    change_group(username, group_name)

    # اعلان به ادمین‌ها: تمدید واقعی انجام شد
    text = (
        "🔔 تمدید انجام شد (فعالسازی فوری)\n"
        f"👤 کاربر: {user_id}\n"
        f"🆔 یوزرنیم: {username}\n"
        f"📦 پلن: {plan_name}\n"
        f"⏳ مدت: {plan_duration} ماه\n"
        f"💳 مبلغ: {plan_price} تومان\n"
        f"🟢 وضعیت: فعال شد (سرویس منقضی بود)"
    )
    await send_message_to_admins(text)


async def _queue_active_service(
        user_id: int,
        service_id: int,
        username: str,
        plan_id: int,
        plan_name: str,
        plan_duration: int,
        plan_price: int,
):
    """Create a reserved renewal record for an active service."""

    update_order_status(order_id=service_id, new_status="waiting_for_renewal")
    insert_renewed_order(
        user_id=user_id,
        plan_id=plan_id,
        username=username,
        price=plan_price,
        status="reserved",
        is_renewal_of_order=service_id,
    )

    # اعلان به ادمین‌ها: تمدید رزروی ثبت شد
    text = (
        "🔔 تمدید رزروی ثبت شد\n"
        f"👤 کاربر: {user_id}\n"
        f"🆔 یوزرنیم: {username}\n"
        f"📦 پلن: {plan_name}\n"
        f"⏳ مدت: {plan_duration} ماه\n"
        f"💳 مبلغ: {plan_price} تومان\n"
        "🟡 وضعیت: در انتظار اتمام دوره‌ی فعلی"
    )
    await send_message_to_admins(text)


async def _timeout_cancel(state: FSMContext, chat_id: int):
    """Cancel renewal flow after 2 minutes of inactivity."""

    await asyncio.sleep(120)
    if await state.get_state() in {RenewStates.wait_service, RenewStates.wait_plan}:
        await state.clear()
        bot = Bot(token=BOT_TOKEN)
        await bot.send_message(chat_id, "⏰ زمان شما برای تمدید سرویس به پایان رسید.",
                               reply_markup=user_main_menu_keyboard())


async def _cancel_timeout(state: FSMContext):
    """Utility to cancel existing timeout tasks stored in FSM data."""

    data = await state.get_data()
    task: asyncio.Task | None = data.get("timeout_task")
    if task and not task.done():
        task.cancel()
