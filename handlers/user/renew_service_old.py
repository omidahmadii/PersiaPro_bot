import asyncio
import datetime

import jdatetime
from aiogram import Router, F, Bot
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import Message, ReplyKeyboardMarkup, KeyboardButton

from config import BOT_TOKEN
from keyboards.user_main_menu import user_main_menu_keyboard
from services import IBSng
from services.IBSng import change_group
from services.admin_notifier import send_message_to_admins
from services.db import (
    get_all_plans,
    get_user_balance,
    update_user_balance,
    get_services_for_renew,
    insert_renewed_order,
    update_order_status,
)

router = Router()


# ---------------- FSM States ---------------- #
class RenewStates(StatesGroup):
    wait_service = State()
    wait_plan = State()
    confirming = State()


# ---------------- Keyboards ---------------- #
def confirm_keyboard() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text="✅ بله"), KeyboardButton(text="❌ خیر")]],
        resize_keyboard=True,
        one_time_keyboard=True,
    )


# ---------------- Step 0: Entry ---------------- #
@router.message(F.text == "📄 تمدید سرویس")
async def handle_renew_request(message: Message, state: FSMContext):
    user_id = message.from_user.id
    services = get_services_for_renew(user_id)

    if not services:
        return await message.answer("⚠️ هیچ سرویسی برای تمدید پیدا نشد.")

    buttons = [[KeyboardButton(text=str(srv["username"]))] for srv in services]
    buttons.append([KeyboardButton(text="بازگشت به منوی اصلی")])

    await state.set_state(RenewStates.wait_service)
    await state.update_data(services=services)

    await message.answer(
        "لطفاً سرویسی که می‌خوای تمدیدش کنی رو انتخاب کن:",
        reply_markup=ReplyKeyboardMarkup(resize_keyboard=True, keyboard=buttons),
    )

    task = asyncio.create_task(_timeout_cancel(state, message.chat.id))
    await state.update_data(timeout_task=task)


# ---------------- Step 1: Choose Service ---------------- #
@router.message(RenewStates.wait_service)
async def choose_service(message: Message, state: FSMContext):
    if message.text == "بازگشت به منوی اصلی":
        await _cancel_timeout(state)
        await state.clear()
        return await message.answer("بازگشت به منوی اصلی", reply_markup=user_main_menu_keyboard())

    data = await state.get_data()
    services = data.get("services", [])
    selected_service = next((s for s in services if str(s["username"]) == message.text.strip()), None)

    if not selected_service:
        return await message.answer("❌ سرویس نامعتبره. لطفاً یکی از گزینه‌ها رو انتخاب کن.")

    plans = get_all_plans()
    if not plans:
        await _cancel_timeout(state)
        await state.clear()
        return await message.answer("❌ هیچ پلنی برای تمدید موجود نیست.")

    user_balance = get_user_balance(message.from_user.id)
    await state.update_data(selected_service=selected_service, user_balance=user_balance)

    await _cancel_timeout(state)

    buttons = [[KeyboardButton(text=f"{p['name']} - {p['price']} تومان")] for p in plans]
    buttons.append([KeyboardButton(text="بازگشت به منوی اصلی")])

    await state.set_state(RenewStates.wait_plan)
    await message.answer(
        "پلن موردنظر برای تمدید رو انتخاب کن:",
        reply_markup=ReplyKeyboardMarkup(resize_keyboard=True, keyboard=buttons),
    )

    task = asyncio.create_task(_timeout_cancel(state, message.chat.id))
    await state.update_data(timeout_task=task)


# ---------------- Step 2: Choose Plan ---------------- #
@router.message(RenewStates.wait_plan)
async def choose_plan(message: Message, state: FSMContext):
    if message.text == "بازگشت به منوی اصلی":
        await _cancel_timeout(state)
        await state.clear()
        return await message.answer("بازگشت به منوی اصلی", reply_markup=user_main_menu_keyboard())

    plans = get_all_plans()
    selected_plan = next((p for p in plans if message.text.startswith(f"{p['name']} -")), None)

    if not selected_plan:
        return await message.answer("پلن معتبر نیست، لطفا دوباره انتخاب کنید.")

    data = await state.get_data()
    # موجودی ذخیره‌شده در state فقط برای نمایش/راستی‌آزمایی اولیه بود؛
    # تصمیم نهایی با موجودی تازه در مرحلهٔ بعد گرفته می‌شود.
    await _cancel_timeout(state)
    await state.update_data(selected_plan=selected_plan)
    await state.set_state(RenewStates.confirming)

    plan_price = selected_plan['price']
    await message.answer(
        f"شما در حال خریداری سرویس {selected_plan['name']} به مبلغ {plan_price} تومان می‌باشید. آیا مطمئن هستید؟",
        reply_markup=confirm_keyboard(),
    )


# ---------------- Step 3: Confirm & Process ---------------- #
@router.message(RenewStates.confirming)
async def confirm_and_renew(message: Message, state: FSMContext):
    if message.text.strip() == "❌ خیر":
        await state.clear()
        return await message.answer("خرید لغو شد ✅", reply_markup=user_main_menu_keyboard())

    if message.text.strip() != "✅ بله":
        return await message.answer("لطفاً از دکمه‌های تأیید یا لغو استفاده کنید.", reply_markup=confirm_keyboard())

    data = await state.get_data()
    selected_plan = data.get("selected_plan")
    selected_service = data.get("selected_service")

    if not selected_plan or not selected_service:
        await state.clear()
        return await message.answer("❌ خطا در دریافت اطلاعات. لطفاً دوباره تلاش کنید.")

    # ✅ خواندن موجودی تازه از DB برای جلوگیری از ناسازگاری
    user_id = message.from_user.id
    current_balance = get_user_balance(user_id)
    plan_price = selected_plan['price']
    if current_balance < plan_price:
        await state.clear()
        return await message.answer(f"❌ موجودی کافی نیست. برای این پلن به {plan_price} تومان نیاز داری.")

    result_text = await _process_renewal(user_id, selected_service, selected_plan, current_balance)

    await state.clear()
    await message.answer(result_text, reply_markup=user_main_menu_keyboard())


# ---------------- Core Renewal Logic ---------------- #
async def _process_renewal(user_id: int, service: dict, plan: dict, user_balance: int) -> str:
    plan_id = plan['id']
    plan_name = plan['name']
    plan_duration = plan['duration_months']  # اگر بعداً روزی شد: plan['duration_days']
    plan_price = plan['price']
    plan_group_name = plan['group_name']

    service_id = service["id"]
    service_username = str(service["username"])

    expires_at_greg = jdatetime.datetime.strptime(service["expires_at"], "%Y-%m-%d %H:%M").togregorian()
    is_expired = service["status"] == "expired" or expires_at_greg < datetime.datetime.now()

    new_balance = user_balance - plan_price
    update_user_balance(user_id, new_balance)

    if is_expired:
        await _renew_expired_service(user_id, service_id, service_username, plan_id, plan_name, plan_duration,
                                     plan_price, plan_group_name)
        return "✅ سرویس با موفقیت تمدید شد.\nبازگشت به منوی اصلی"

    await _queue_active_service(user_id, service_id, service_username, plan_id, plan_name, plan_duration, plan_price)
    return (
        "✅ سرویس در وضعیت ذخیره قرار گرفت و پس از پایان دوره‌ی قبلی به صورت خودکار فعال خواهد شد.\n"
        "بازگشت به منوی اصلی"
    )


# ---------------- Service Actions ---------------- #
async def _renew_expired_service(user_id, service_id, username, plan_id, plan_name, plan_duration, plan_price,
                                 plan_group_name):
    update_order_status(order_id=service_id, new_status="renewed")
    insert_renewed_order(user_id, plan_id, username, plan_price, "active", service_id)

    IBSng.reset_account_client(username=username)
    # change_group(username, f"{plan_duration}-Month")
    change_group(username=username, group=plan_group_name)

    text = (
        "🔔 تمدید انجام شد (فعالسازی فوری)\n"
        f"👤 کاربر: {user_id}\n🆔 یوزرنیم: {username}\n📦 پلن: {plan_name}\n"
        f"⏳ مدت: {plan_duration} ماه\n💳 مبلغ: {plan_price} تومان\n🟢 وضعیت: فعال شد"
    )
    await send_message_to_admins(text)


async def _queue_active_service(user_id, service_id, username, plan_id, plan_name, plan_duration, plan_price):
    update_order_status(order_id=service_id, new_status="waiting_for_renewal")
    insert_renewed_order(user_id, plan_id, username, plan_price, "reserved", service_id)

    text = (
        "🔔 تمدید رزروی ثبت شد\n"
        f"👤 کاربر: {user_id}\n🆔 یوزرنیم: {username}\n📦 پلن: {plan_name}\n"
        f"⏳ مدت: {plan_duration} ماه\n💳 مبلغ: {plan_price} تومان\n🟡 وضعیت: در انتظار اتمام دوره"
    )
    await send_message_to_admins(text)


# ---------------- Timeout Helpers ---------------- #
async def _timeout_cancel(state: FSMContext, chat_id: int):
    await asyncio.sleep(120)
    if await state.get_state() in {RenewStates.wait_service, RenewStates.wait_plan}:
        await state.clear()
        await Bot(token=BOT_TOKEN).send_message(
            chat_id,
            "⏰ زمان تمدید تمام شد.",
            reply_markup=user_main_menu_keyboard()
        )


async def _cancel_timeout(state: FSMContext):
    data = await state.get_data()
    task: asyncio.Task | None = data.get("timeout_task")
    if task and not task.done():
        task.cancel()
