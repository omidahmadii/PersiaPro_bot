from html import escape
from typing import Optional

from aiogram import Router, F
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.fsm.state import StatesGroup, State
from aiogram.fsm.context import FSMContext

from config import ADMINS
from keyboards.main_menu import admin_main_menu_keyboard, main_menu_keyboard_for_user
from services.bot_instance import bot
from services.admin_notifier import send_message_to_admins
from services.db import (
    get_user_by_id,
    get_user_display_name,
    get_distinct_usernames_by_user_id,
    count_orders_by_user_id_and_username,
    get_admin_transfer_account_preview,
    search_accounts_for_admin_transfer,
    transfer_orders_by_username_to_another_user,
)

router = Router()


class TransferOwnershipState(StatesGroup):
    waiting_for_target_user_id = State()
    waiting_for_confirmation = State()
    waiting_for_admin_query = State()
    waiting_for_admin_target_user_id = State()
    waiting_for_admin_confirmation = State()


STATUS_LABELS = {
    "active": "فعال",
    "expired": "منقضی",
    "reserved": "ذخیره",
    "waiting_for_payment": "در انتظار پرداخت",
    "waiting_for_renewal": "در انتظار فعال‌سازی ذخیره",
    "waiting_for_renewal_not_paid": "تمدید در انتظار پرداخت",
    "canceled": "لغوشده",
    "renewed": "تمدیدشده",
    "converted": "تبدیل‌شده",
    "archived": "آرشیوشده",
}


def is_admin(user_id: int) -> bool:
    return str(user_id) in {str(admin_id) for admin_id in ADMINS}


def status_label(status: Optional[str]) -> str:
    return STATUS_LABELS.get(str(status or "").strip(), str(status or "-"))


def admin_owner_label(account: dict) -> str:
    full_name = " ".join(
        part for part in [account.get("first_name") or "", account.get("last_name") or ""] if part
    ).strip()
    telegram_username = account.get("telegram_username")
    name = full_name or (f"@{telegram_username}" if telegram_username else "-")
    username_part = f"@{telegram_username}" if telegram_username else "-"
    return f"{name} | {username_part} | {account.get('user_id') or '-'}"


def admin_transfer_results_keyboard(accounts: list[dict]) -> InlineKeyboardMarkup:
    rows = []
    for account in accounts:
        label = (
            f"{account.get('username') or '-'} | "
            f"{account.get('user_id') or '-'} | "
            f"{account.get('latest_expires_at') or '-'}"
        )
        rows.append([
            InlineKeyboardButton(
                text=label[:64],
                callback_data=f"admin_transfer|select|{account['representative_order_id']}",
            )
        ])
    rows.append([InlineKeyboardButton(text="🔎 جست‌وجوی دوباره", callback_data="admin_transfer|search")])
    rows.append([InlineKeyboardButton(text="❌ انصراف", callback_data="admin_transfer|cancel")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def admin_transfer_confirm_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="✅ تایید انتقال", callback_data="admin_transfer|confirm"),
                InlineKeyboardButton(text="❌ لغو", callback_data="admin_transfer|cancel"),
            ]
        ]
    )


def build_admin_account_preview(account: dict) -> str:
    return (
        "🔁 <b>پیش‌نمایش انتقال مالکیت</b>\n\n"
        f"👤 اکانت سرویس: <code>{escape(str(account.get('username') or '-'))}</code>\n"
        f"👥 مالک فعلی: <code>{escape(admin_owner_label(account))}</code>\n"
        f"⏳ پایان سرویس: <code>{escape(str(account.get('latest_expires_at') or '-'))}</code>\n"
        f"📦 آخرین پلن: {escape(str(account.get('latest_plan_name') or '-'))}\n"
        f"📍 وضعیت آخرین سفارش: {status_label(account.get('latest_status'))}\n"
        f"🧾 تعداد سفارش‌های قابل انتقال: {account.get('total_orders') or 0}\n\n"
        "حالا شناسه عددی کاربر مقصد را بفرست."
    )


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


@router.message(F.text == "🔁 انتقال مالکیت")
async def start_transfer_ownership(message: Message, state: FSMContext):
    from_user_id = message.from_user.id

    if is_admin(from_user_id):
        await state.clear()
        await state.set_state(TransferOwnershipState.waiting_for_admin_query)
        await message.answer(
            "نام اکانت سرویس، آیدی سفارش، آیدی مالک فعلی یا یوزرنیم/نام کاربر را بفرست تا اکانت را پیدا کنم."
        )
        return

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


@router.callback_query(F.data == "admin_transfer|cancel")
async def admin_cancel_transfer_callback(callback: CallbackQuery, state: FSMContext):
    if not is_admin(callback.from_user.id):
        return await callback.answer("دسترسی نداری.", show_alert=True)

    await state.clear()
    await callback.message.answer("عملیات انتقال مالکیت لغو شد.", reply_markup=admin_main_menu_keyboard())
    await callback.answer()


@router.callback_query(F.data == "admin_transfer|search")
async def admin_transfer_search_again(callback: CallbackQuery, state: FSMContext):
    if not is_admin(callback.from_user.id):
        return await callback.answer("دسترسی نداری.", show_alert=True)

    await state.clear()
    await state.set_state(TransferOwnershipState.waiting_for_admin_query)
    await callback.message.answer("عبارت جست‌وجوی اکانت را بفرست.")
    await callback.answer()


@router.message(TransferOwnershipState.waiting_for_admin_query)
async def admin_receive_transfer_query(message: Message, state: FSMContext):
    if not is_admin(message.from_user.id):
        await state.clear()
        return

    keyword = (message.text or "").strip()
    accounts = search_accounts_for_admin_transfer(keyword)
    if not accounts:
        await message.answer("اکانتی با این مشخصات پیدا نشد. دوباره جست‌وجو کن.")
        return

    await state.update_data(admin_transfer_last_query=keyword)
    await message.answer(
        f"نتایج جست‌وجو برای <code>{escape(keyword)}</code>:",
        parse_mode="HTML",
        reply_markup=admin_transfer_results_keyboard(accounts),
    )


@router.callback_query(F.data.startswith("admin_transfer|select|"))
async def admin_select_transfer_account(callback: CallbackQuery, state: FSMContext):
    if not is_admin(callback.from_user.id):
        return await callback.answer("دسترسی نداری.", show_alert=True)

    representative_order_id = int(callback.data.split("|")[2])
    account = get_admin_transfer_account_preview(representative_order_id)
    if not account:
        return await callback.answer("این اکانت دیگر معتبر نیست.", show_alert=True)

    await state.update_data(
        admin_from_user_id=account["user_id"],
        admin_selected_username=account["username"],
        admin_selected_account=account,
        admin_orders_count=account.get("total_orders") or 0,
    )
    await state.set_state(TransferOwnershipState.waiting_for_admin_target_user_id)
    await callback.message.answer(build_admin_account_preview(account), parse_mode="HTML")
    await callback.answer()


@router.message(TransferOwnershipState.waiting_for_admin_target_user_id)
async def admin_receive_target_user_id(message: Message, state: FSMContext):
    if not is_admin(message.from_user.id):
        await state.clear()
        return

    text = (message.text or "").strip()
    if not text.isdigit():
        await message.answer("لطفا فقط شناسه عددی کاربر مقصد را بفرست.")
        return

    to_user_id = int(text)
    data = await state.get_data()
    from_user_id = data.get("admin_from_user_id")
    selected_username = data.get("admin_selected_username")
    account = data.get("admin_selected_account") or {}

    if not from_user_id or not selected_username:
        await state.clear()
        await message.answer("اطلاعات انتقال ناقص است. دوباره شروع کن.", reply_markup=admin_main_menu_keyboard())
        return

    if int(from_user_id) == to_user_id:
        await message.answer("مقصد با مالک فعلی یکی است. شناسه مقصد دیگری وارد کن.")
        return

    target_user = get_user_by_id(to_user_id)
    if not target_user or int(target_user.get("id") or 0) <= 0 or target_user.get("role") == "offline":
        await message.answer("کاربر مقصد در ربات پیدا نشد. شناسه عددی درست را بفرست.")
        return

    from_name = get_user_display_name(from_user_id)
    to_name = get_user_display_name(to_user_id)
    await state.update_data(admin_to_user_id=to_user_id)
    await state.set_state(TransferOwnershipState.waiting_for_admin_confirmation)

    await message.answer(
        "⚠️ <b>تایید انتقال مالکیت توسط ادمین</b>\n\n"
        f"👤 اکانت: <code>{escape(str(selected_username))}</code>\n"
        f"⬅️ مالک فعلی: {escape(from_name)}\n"
        f"🆔 مالک فعلی: <code>{from_user_id}</code>\n"
        f"⏳ پایان سرویس: <code>{escape(str(account.get('latest_expires_at') or '-'))}</code>\n\n"
        f"➡️ مقصد: {escape(to_name)}\n"
        f"🆔 مقصد: <code>{to_user_id}</code>\n\n"
        "با تایید، تمام سفارش‌های همین اکانت از مالک فعلی به کاربر مقصد منتقل می‌شود.",
        parse_mode="HTML",
        reply_markup=admin_transfer_confirm_keyboard(),
    )


@router.callback_query(F.data == "admin_transfer|confirm")
async def admin_confirm_transfer_callback(callback: CallbackQuery, state: FSMContext):
    if not is_admin(callback.from_user.id):
        return await callback.answer("دسترسی نداری.", show_alert=True)

    data = await state.get_data()
    from_user_id = data.get("admin_from_user_id")
    to_user_id = data.get("admin_to_user_id")
    selected_username = data.get("admin_selected_username")

    if not from_user_id or not to_user_id or not selected_username:
        await state.clear()
        await callback.message.answer("اطلاعات انتقال ناقص است. دوباره شروع کن.", reply_markup=admin_main_menu_keyboard())
        await callback.answer()
        return

    success, error, moved_count = transfer_orders_by_username_to_another_user(
        from_user_id=from_user_id,
        to_user_id=to_user_id,
        username=selected_username,
        transferred_by=callback.from_user.id,
    )

    if not success:
        await state.clear()
        await callback.message.answer(f"انتقال انجام نشد.\n{error}", reply_markup=admin_main_menu_keyboard())
        await callback.answer()
        return

    from_name = get_user_display_name(from_user_id)
    to_name = get_user_display_name(to_user_id)
    admin_name = get_user_display_name(callback.from_user.id)

    await callback.message.answer(
        "✅ <b>انتقال مالکیت انجام شد</b>\n\n"
        f"👤 اکانت: <code>{escape(str(selected_username))}</code>\n"
        f"🧾 تعداد سفارش منتقل‌شده: {moved_count}\n"
        f"⬅️ از: {escape(from_name)} (<code>{from_user_id}</code>)\n"
        f"➡️ به: {escape(to_name)} (<code>{to_user_id}</code>)",
        parse_mode="HTML",
        reply_markup=admin_main_menu_keyboard(),
    )

    try:
        await bot.send_message(
            chat_id=to_user_id,
            text=(
                "🎉 <b>یک سرویس به حساب شما منتقل شد</b>\n\n"
                f"👤 نام کاربری اکانت:\n<code>{escape(str(selected_username))}</code>\n\n"
                f"انتقال توسط ادمین انجام شد و سرویس در بخش <b>«سرویس‌های من»</b> قابل مشاهده است."
            ),
            parse_mode="HTML",
        )
    except Exception:
        pass

    try:
        await bot.send_message(
            chat_id=from_user_id,
            text=(
                "🔁 <b>مالکیت یکی از سرویس‌های شما منتقل شد</b>\n\n"
                f"👤 اکانت:\n<code>{escape(str(selected_username))}</code>\n\n"
                "این تغییر توسط پشتیبانی انجام شده است."
            ),
            parse_mode="HTML",
        )
    except Exception:
        pass

    try:
        await send_message_to_admins(
            "🔁 <b>انتقال مالکیت سرویس توسط ادمین</b>\n\n"
            f"👤 اکانت:\n<code>{escape(str(selected_username))}</code>\n\n"
            f"👮 ادمین:\n{escape(admin_name)}\n<code>{callback.from_user.id}</code>\n\n"
            f"⬅️ انتقال از:\n{escape(from_name)}\n<code>{from_user_id}</code>\n\n"
            f"➡️ انتقال به:\n{escape(to_name)}\n<code>{to_user_id}</code>"
        )
    except Exception:
        pass

    await state.clear()
    await callback.answer()


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
    if not target_user or int(target_user.get("id") or 0) <= 0 or target_user.get("role") == "offline":
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
