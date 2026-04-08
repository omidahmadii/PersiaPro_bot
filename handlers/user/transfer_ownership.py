from aiogram import Router, F
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.fsm.state import StatesGroup, State
from aiogram.fsm.context import FSMContext

from keyboards.main_menu import main_menu_keyboard_for_user
from services.bot_instance import bot
from services.admin_notifier import send_message_to_admins
from services.db import (
    get_user_by_id,
    get_user_display_name,
    get_distinct_usernames_by_user_id,
    count_orders_by_user_id_and_username,
    transfer_orders_by_username_to_another_user,
)

router = Router()


class TransferOwnershipState(StatesGroup):
    waiting_for_target_user_id = State()
    waiting_for_confirmation = State()


def usernames_inline_keyboard(usernames: list):
    buttons = []

    for username in usernames:
        username_text = str(username)
        buttons.append([
            InlineKeyboardButton(
                text=f"👤 {username_text}",
                callback_data=f"transfer_select:{username_text}"
            )
        ])

    buttons.append([
        InlineKeyboardButton(
            text="❌ لغو انتقال",
            callback_data="transfer_cancel"
        )
    ])

    return InlineKeyboardMarkup(inline_keyboard=buttons)


def confirm_inline_keyboard():
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="✅ تایید انتقال", callback_data="transfer_confirm"),
                InlineKeyboardButton(text="❌ لغو", callback_data="transfer_cancel")
            ]
        ]
    )


@router.message(F.text == "🔁 انتقال مالکیت سرویس")
async def start_transfer_ownership(message: Message, state: FSMContext):
    from_user_id = message.from_user.id

    user = get_user_by_id(from_user_id)
    if not user:
        await message.answer(
            "اطلاعات حساب شما در سیستم پیدا نشد.",
            reply_markup=main_menu_keyboard_for_user(from_user_id)
        )
        return

    usernames = get_distinct_usernames_by_user_id(from_user_id)
    if not usernames:
        await message.answer(
            "شما هیچ اکانتی برای انتقال ندارید.",
            reply_markup=main_menu_keyboard_for_user(from_user_id)
        )
        return

    await state.clear()
    await state.update_data(from_user_id=from_user_id)
    await state.set_state(TransferOwnershipState.waiting_for_target_user_id)

    await message.answer(
        "لطفا اکانتی که می‌خواهید منتقل شود را انتخاب کنید.\n\n"
        "با انتخاب هر اکانت، تمام سفارش‌ها و تمدیدهای مربوط به همان اکانت منتقل خواهد شد.",
        reply_markup=usernames_inline_keyboard(usernames)
    )


@router.callback_query(F.data == "transfer_cancel")
async def cancel_transfer_callback(callback: CallbackQuery, state: FSMContext):
    await state.clear()
    await callback.message.edit_text("عملیات انتقال لغو شد.")
    await callback.message.answer(
        "به منوی اصلی برگشتید.",
        reply_markup=main_menu_keyboard_for_user(callback.from_user.id)
    )
    await callback.answer()


@router.callback_query(F.data.startswith("transfer_select:"))
async def select_username_callback(callback: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    from_user_id = data.get("from_user_id")

    if not from_user_id:
        await state.clear()
        await callback.message.edit_text("اطلاعات عملیات منقضی شده. لطفا دوباره تلاش کنید.")
        await callback.message.answer(
            "به منوی اصلی برگشتید.",
            reply_markup=main_menu_keyboard_for_user(callback.from_user.id)
        )
        await callback.answer()
        return

    selected_username = callback.data.split("transfer_select:", 1)[1].strip()

    usernames = get_distinct_usernames_by_user_id(from_user_id)
    usernames_as_str = [str(item) for item in usernames]

    if selected_username not in usernames_as_str:
        await callback.answer("این اکانت معتبر نیست.", show_alert=True)
        return

    orders_count = count_orders_by_user_id_and_username(from_user_id, selected_username)
    if orders_count <= 0:
        await callback.answer("برای این اکانت سفارشی پیدا نشد.", show_alert=True)
        return

    await state.update_data(
        selected_username=selected_username,
        orders_count=orders_count
    )
    await state.set_state(TransferOwnershipState.waiting_for_target_user_id)

    await callback.message.edit_text(
        f"✨ <b>اکانت موردنظر انتخاب شد</b>\n\n"
        f"👤 اکانت انتخاب‌شده:\n"
        f"<code>{selected_username}</code>\n\n"
        f"📩 لطفا <b>آیدی عددی تلگرام</b> شخصی که می‌خواهید این اکانت به او منتقل شود را ارسال کنید.\n\n"
        f"او می‌تواند این شناسه را از بخش <b>«حساب کاربری»</b> در ربات مشاهده کرده و برای شما بفرستد.\n\n"
        f"⚠️ دقت کنید: پس از تایید نهایی، این اکانت از حساب شما خارج می‌شود.",
        parse_mode="HTML"
    )
    await callback.answer()


@router.message(TransferOwnershipState.waiting_for_target_user_id)
async def receive_target_user_id(message: Message, state: FSMContext):
    text = (message.text or "").strip()

    if not text.isdigit():
        await message.answer("لطفا فقط آیدی عددی تلگرام کاربر مقصد را ارسال کنید.")
        return

    to_user_id = int(text)

    data = await state.get_data()
    from_user_id = data.get("from_user_id")
    selected_username = data.get("selected_username")
    orders_count = data.get("orders_count", 0)

    if not from_user_id or not selected_username:
        await state.clear()
        await message.answer(
            "اطلاعات عملیات ناقص است. لطفا دوباره تلاش کنید.",
            reply_markup=main_menu_keyboard_for_user(message.from_user.id)
        )
        return

    if from_user_id == to_user_id:
        await message.answer("شما نمی‌توانید این اکانت را به خودتان منتقل کنید.")
        return

    from_user = get_user_by_id(from_user_id)
    if not from_user:
        await state.clear()
        await message.answer(
            "اطلاعات حساب شما در سیستم پیدا نشد.",
            reply_markup=main_menu_keyboard_for_user(message.from_user.id)
        )
        return

    target_user = get_user_by_id(to_user_id)
    if not target_user:
        await message.answer(
            "کاربری با این آیدی عددی در سیستم پیدا نشد.\n"
            "لطفا آیدی صحیح را وارد کنید."
        )
        return

    target_name = get_user_display_name(to_user_id)

    await state.update_data(to_user_id=to_user_id)
    await state.set_state(TransferOwnershipState.waiting_for_confirmation)

    await message.answer(
        f"⚠️ <b>تایید انتقال مالکیت</b>\n\n"
        f"شما در حال انتقال این اکانت هستید:\n"
        f"👤 <code>{selected_username}</code>\n\n"
        f"به کاربر:\n"
        f"🆔 <code>{to_user_id}</code>\n\n"
        f"بعد از تایید:\n"
        f"• این اکانت دیگر در حساب شما نمایش داده نمی‌شود\n"
        f"• مالکیت آن به کاربر جدید منتقل می‌شود\n\n"
        f"آیا از انجام این عملیات مطمئن هستید؟",
        reply_markup=confirm_inline_keyboard(),
        parse_mode="HTML"
    )


@router.callback_query(F.data == "transfer_confirm")
async def confirm_transfer_callback(callback: CallbackQuery, state: FSMContext):
    data = await state.get_data()

    from_user_id = data.get("from_user_id")
    to_user_id = data.get("to_user_id")
    selected_username = data.get("selected_username")

    if not from_user_id or not to_user_id or not selected_username:
        await state.clear()
        await callback.message.edit_text("اطلاعات انتقال ناقص است. لطفا دوباره تلاش کنید.")
        await callback.message.answer(
            "به منوی اصلی برگشتید.",
            reply_markup=main_menu_keyboard_for_user(callback.from_user.id)
        )
        await callback.answer()
        return

    success, error, moved_count = transfer_orders_by_username_to_another_user(
        from_user_id=from_user_id,
        to_user_id=to_user_id,
        username=selected_username
    )

    if not success:
        await state.clear()
        await callback.message.edit_text(f"انتقال انجام نشد.\n{error}")
        await callback.message.answer(
            "به منوی اصلی برگشتید.",
            reply_markup=main_menu_keyboard_for_user(callback.from_user.id)
        )
        await callback.answer()
        return

    from_name = get_user_display_name(from_user_id)
    to_name = get_user_display_name(to_user_id)

    await callback.message.edit_text(
        f"✅ <b>انتقال با موفقیت انجام شد</b>\n\n"
        f"👤 اکانت منتقل‌شده:\n"
        f"<code>{selected_username}</code>\n\n"
        f"👥 مالک جدید:\n"
        f"{to_name}\n\n"
        f"از این لحظه این اکانت دیگر در لیست سرویس‌های شما نمایش داده نمی‌شود.",
        parse_mode="HTML"
    )

    try:
        await bot.send_message(
            chat_id=to_user_id,
            text=(
                f"🎉 <b>یک سرویس به حساب شما منتقل شد</b>\n\n"
                f"👤 نام کاربری اکانت:\n"
                f"<code>{selected_username}</code>\n\n"
                f"👤 انتقال‌دهنده:\n"
                f"{from_name}\n\n"
                f"این سرویس اکنون در بخش <b>«سرویس‌های من»</b> برای شما قابل مشاهده است."
            ),
            parse_mode="HTML"
        )
    except Exception:
        pass

    try:
        await send_message_to_admins(
            f"🔁 <b>انتقال مالکیت سرویس</b>\n\n"
            f"👤 اکانت:\n"
            f"<code>{selected_username}</code>\n\n"
            f"⬅️ انتقال از:\n"
            f"{from_name}\n"
            f"<code>{from_user_id}</code>\n\n"
            f"➡️ انتقال به:\n"
            f"{to_name}\n"
            f"<code>{to_user_id}</code>"
        )
    except Exception:
        pass

    await state.clear()
    await callback.message.answer(
        "به منوی اصلی برگشتید.",
        reply_markup=main_menu_keyboard_for_user(callback.from_user.id)
    )
    await callback.answer()


@router.message(TransferOwnershipState.waiting_for_confirmation)
async def invalid_transfer_confirmation(message: Message):
    await message.answer("لطفا از دکمه «✅ تایید انتقال» یا «❌ لغو» استفاده کنید.")
