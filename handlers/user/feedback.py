from aiogram import Router, F
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton, ReplyKeyboardRemove
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import StatesGroup, State
from datetime import datetime
from asyncio import create_task, sleep

from config import ADMINS
from keyboards.user_main_menu import user_main_menu_keyboard
from services.bot_instance import bot
from services.db import insert_feedback

router = Router()


class FeedbackStates(StatesGroup):
    waiting_for_type = State()
    waiting_for_message = State()


# تابع تایمر انقضا
async def feedback_timeout(user_id: int, state: FSMContext):
    await sleep(600)  # 10 دقیقه
    current_state = await state.get_state()
    if current_state in [FeedbackStates.waiting_for_type.state, FeedbackStates.waiting_for_message.state]:
        await bot.send_message(user_id, "⏰ زمان ثبت بازخورد به پایان رسید. لطفاً دوباره اقدام کنید.")
        await state.clear()


# شروع بخش بازخورد
@router.message(F.text == "📬 انتقادات و پیشنهادات")
async def start_feedback(msg: Message, state: FSMContext):
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📌 پیشنهاد", callback_data="feedback:suggestion")],
        [InlineKeyboardButton(text="⚠️ انتقاد", callback_data="feedback:complaint")],
        [InlineKeyboardButton(text="🔙 بازگشت به منوی اصلی", callback_data="feedback:cancel_not_paid_waiting_for_payment_orders.py")]
    ])

    # حذف کیبورد معمولی و نمایش اینلاین‌کیبورد
    await msg.answer("لطفاً نوع بازخورد خود را انتخاب کنید:",
                     reply_markup=keyboard)

    await state.set_state(FeedbackStates.waiting_for_type)
    create_task(feedback_timeout(msg.from_user.id, state))


# لغو بازخورد و برگشت به منو
@router.callback_query(F.data == "feedback:cancel_not_paid_waiting_for_payment_orders.py")
async def cancel_feedback(callback: CallbackQuery, state: FSMContext):
    await state.clear()
    await callback.message.edit_text("از بخش بازخورد خارج شدید. ✅")
    # در صورت نیاز، منوی اصلی رو با کیبورد معمولی می‌تونی اینجا بفرستی


# انتخاب نوع بازخورد
@router.callback_query(F.data.startswith("feedback:"), FeedbackStates.waiting_for_type)
async def select_feedback_type(callback: CallbackQuery, state: FSMContext):
    feedback_type = callback.data.split(":")[1]
    if feedback_type not in ["suggestion", "complaint"]:
        return  # جلوگیری از callback نامعتبر

    await state.update_data(feedback_type=feedback_type)
    await callback.message.edit_text("لطفاً بازخورد خود را ارسال کنید:")
    await state.set_state(FeedbackStates.waiting_for_message)


# دریافت پیام بازخورد
@router.message(FeedbackStates.waiting_for_message)
async def receive_feedback_message(msg: Message, state: FSMContext):
    data = await state.get_data()
    feedback_type = data.get("feedback_type")
    user_id = msg.from_user.id
    message = msg.text
    created_at = datetime.now().isoformat()

    # ذخیره بازخورد در دیتابیس
    insert_feedback(user_id, feedback_type, message, created_at)

    # اطلاع‌رسانی به ادمین‌ها
    for admin_id in ADMINS:
        await bot.send_message(admin_id,
                               f"📩 بازخورد جدید:\n"
                               f"نوع: {'پیشنهاد' if feedback_type == 'suggestion' else 'انتقاد'}\n"
                               f"از: {msg.from_user.full_name}\n\n{message}")

    await msg.answer("✅ بازخورد شما با موفقیت ثبت شد. ممنون از همراهی‌تون!", reply_markup=user_main_menu_keyboard())
    await state.clear()
