from typing import Optional

from aiogram import Bot, F, Router
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message

from config import ADMINS
from keyboards.main_menu import admin_main_menu_keyboard
from services.db import get_order_with_plan, get_plans_for_admin, search_orders_for_admin
from services.order_workflow import FINAL_ORDER_STATUSES, adjust_manual_extra_volume, cancel_order, change_order_plan

router = Router()


class OrderManagementStates(StatesGroup):
    waiting_for_query = State()
    waiting_for_volume = State()


STATUS_LABELS = {
    "active": "فعال",
    "waiting_for_payment": "در انتظار پرداخت",
    "reserved": "ذخیره",
    "waiting_for_renewal": "در انتظار فعال‌سازی ذخیره",
    "waiting_for_renewal_not_paid": "تمدید در انتظار پرداخت",
    "expired": "منقضی",
    "canceled": "لغوشده",
    "renewed": "تمدیدشده",
    "archived": "آرشیوشده",
}


def is_admin(user_id: int) -> bool:
    return str(user_id) in {str(admin_id) for admin_id in ADMINS}


def format_price(amount: int) -> str:
    try:
        return f"{int(amount):,}"
    except Exception:
        return str(amount)


def status_label(status: Optional[str]) -> str:
    return STATUS_LABELS.get(str(status or "").strip(), str(status or "-"))


def search_help_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="🏠 منوی ادمین", callback_data="order_mgmt|main")],
        ]
    )


def search_results_keyboard(
    results: list[dict],
    view: str,
    active_count: int,
    archived_count: int,
) -> InlineKeyboardMarkup:
    rows = []
    for item in results:
        label = (
            f"#{item['id']} | {item.get('username') or '-'} | "
            f"{item.get('plan_name') or '-'} | {status_label(item.get('status'))}"
        )
        rows.append([
            InlineKeyboardButton(
                text=label[:64],
                callback_data=f"order_mgmt|open|{item['id']}",
            )
        ])

    if view == "active" and archived_count > 0:
        rows.append([InlineKeyboardButton(text=f"🗂 آرشیوشده‌ها ({archived_count})", callback_data="order_mgmt|results|archived")])
    if view == "archived" and active_count > 0:
        rows.append([InlineKeyboardButton(text=f"📂 سفارش‌های اصلی ({active_count})", callback_data="order_mgmt|results|active")])
    rows.append([InlineKeyboardButton(text="🔍 جست‌وجوی جدید", callback_data="order_mgmt|search")])
    rows.append([InlineKeyboardButton(text="🏠 منوی ادمین", callback_data="order_mgmt|main")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def order_actions_keyboard(order: dict) -> InlineKeyboardMarkup:
    order_id = int(order["id"])
    rows: list[list[InlineKeyboardButton]] = []

    if str(order.get("status") or "").strip() not in FINAL_ORDER_STATUSES:
        rows.extend([
            [InlineKeyboardButton(text="🛠 تغییر پلن سفارش", callback_data=f"order_mgmt|plans|{order_id}")],
            [InlineKeyboardButton(text="↕️ تغییر حجم دستی", callback_data=f"order_mgmt|volume|{order_id}")],
            [InlineKeyboardButton(text="❌ لغو سفارش", callback_data=f"order_mgmt|cancel|{order_id}")],
        ])

    rows.append([InlineKeyboardButton(text="🔍 جست‌وجوی جدید", callback_data="order_mgmt|search")])
    rows.append([InlineKeyboardButton(text="🏠 منوی ادمین", callback_data="order_mgmt|main")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def cancel_confirm_keyboard(order_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="✅ بله، لغو شود", callback_data=f"order_mgmt|cancel_confirm|{order_id}")],
            [InlineKeyboardButton(text="🔙 بازگشت", callback_data=f"order_mgmt|open|{order_id}")],
        ]
    )


def plans_keyboard(order_id: int) -> InlineKeyboardMarkup:
    rows = []
    for plan in get_plans_for_admin(include_archived=False):
        label = (
            f"#{plan['id']} | {plan.get('name') or '-'} | "
            f"{plan.get('volume_gb') or 0} گیگ | {format_price(plan.get('price') or 0)}"
        )
        rows.append([
            InlineKeyboardButton(
                text=label[:64],
                callback_data=f"order_mgmt|plan_pick|{order_id}|{plan['id']}",
            )
        ])
    rows.append([InlineKeyboardButton(text="🔙 بازگشت", callback_data=f"order_mgmt|open|{order_id}")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def plan_confirm_keyboard(order_id: int, plan_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="✅ اعمال این پلن", callback_data=f"order_mgmt|plan_apply|{order_id}|{plan_id}")],
            [InlineKeyboardButton(text="🔙 بازگشت", callback_data=f"order_mgmt|plans|{order_id}")],
        ]
    )


def build_order_caption(order: dict) -> str:
    full_name = " ".join(part for part in [order.get("first_name") or "", order.get("last_name") or ""] if part).strip()
    return (
        f"🧾 سفارش #{order['id']}\n"
        f"👤 کاربر: {order.get('user_id') or '-'} {full_name or ''}\n"
        f"🔰 یوزرنیم تلگرام: @{order.get('telegram_username') or '-'}\n"
        f"🆔 یوزرنیم سرویس: <code>{order.get('username') or '-'}</code>\n"
        f"📦 پلن: {order.get('plan_name') or '-'}\n"
        f"💰 مبلغ: {format_price(order.get('price') or 0)} تومان\n"
        f"📊 حجم پایه: {order.get('volume_gb') or 0} گیگ\n"
        f"➕ حجم اضافه: {order.get('extra_volume_gb') or 0} گیگ\n"
        f"📍 وضعیت: {status_label(order.get('status'))}\n"
        f"🕒 ثبت سفارش: {order.get('created_at') or '-'}\n"
        f"🚀 شروع: {order.get('starts_at') or '-'}\n"
        f"⏳ پایان: {order.get('expires_at') or '-'}\n"
        f"🔁 نوع: {'تمدید' if order.get('is_renewal_of_order') else 'خرید'}"
    )


def build_plan_change_confirmation(order: dict, plan: dict) -> str:
    old_price = int(order.get("price") or 0)
    new_price = int(plan.get("price") or 0)
    price_diff = new_price - old_price
    if price_diff > 0:
        balance_text = f"{format_price(price_diff)} تومان از موجودی کاربر کسر می‌شود."
    elif price_diff < 0:
        balance_text = f"{format_price(abs(price_diff))} تومان به موجودی کاربر برمی‌گردد."
    else:
        balance_text = "تغییری در موجودی کاربر ایجاد نمی‌شود."

    return (
        f"سفارش <code>{order.get('username') or '-'}</code> از پلن «{order.get('plan_name') or '-'}» "
        f"به پلن «{plan.get('name') or '-'}» تغییر می‌کند.\n\n"
        f"پلن جدید: {plan.get('volume_gb') or 0} گیگ | {format_price(new_price)} تومان\n"
        f"نتیجه مالی: {balance_text}\n\n"
        "اگر سفارش زنده باشد، زمان/حجم/پروفایل سرویس بر اساس پلن جدید از نو اعمال می‌شود."
    )


async def store_search_context(state: FSMContext, keyword: str, active_count: int, archived_count: int) -> None:
    await state.update_data(
        order_management_last_keyword=keyword,
        order_management_last_active_count=active_count,
        order_management_last_archived_count=archived_count,
    )
    await state.set_state(None)


async def start_search_from_message(message: Message, state: FSMContext) -> None:
    await state.clear()
    await state.set_state(OrderManagementStates.waiting_for_query)
    await message.answer(
        "آیدی سفارش، آیدی کاربر یا یوزرنیم سرویس را بفرست تا جستجو کنم:",
        reply_markup=search_help_keyboard(),
    )


async def start_search_from_callback(callback: CallbackQuery, state: FSMContext) -> None:
    await state.clear()
    await state.set_state(OrderManagementStates.waiting_for_query)
    await callback.message.answer(
        "آیدی سفارش، آیدی کاربر یا یوزرنیم سرویس را بفرست تا جستجو کنم:",
        reply_markup=search_help_keyboard(),
    )
    await callback.answer()


@router.message(F.text == "🧾 مدیریت سفارش‌ها")
async def order_management_entry(message: Message, state: FSMContext):
    if not is_admin(message.from_user.id):
        return
    await start_search_from_message(message, state)


@router.callback_query(F.data == "order_mgmt|main")
async def order_management_main(callback: CallbackQuery, state: FSMContext):
    if not is_admin(callback.from_user.id):
        return await callback.answer("دسترسی نداری.", show_alert=True)
    await state.clear()
    await callback.message.answer("بازگشت به منوی ادمین.", reply_markup=admin_main_menu_keyboard())
    await callback.answer()


@router.callback_query(F.data == "order_mgmt|search")
async def order_management_search(callback: CallbackQuery, state: FSMContext):
    if not is_admin(callback.from_user.id):
        return await callback.answer("دسترسی نداری.", show_alert=True)
    await start_search_from_callback(callback, state)


@router.message(OrderManagementStates.waiting_for_query)
async def order_management_receive_query(message: Message, state: FSMContext):
    if not is_admin(message.from_user.id):
        await state.clear()
        return

    keyword = (message.text or "").strip()
    active_results = search_orders_for_admin(keyword, archived_only=False)
    archived_results = search_orders_for_admin(keyword, archived_only=True)
    active_count = len(active_results)
    archived_count = len(archived_results)

    if not active_results and not archived_results:
        await message.answer(
            "سفارشی با این مشخصات پیدا نشد. دوباره امتحان کن.",
            reply_markup=search_help_keyboard(),
        )
        return

    await store_search_context(state, keyword, active_count, archived_count)
    if active_results:
        text = f"نتایج جست‌وجو برای <code>{keyword}</code>:"
    else:
        text = (
            f"برای <code>{keyword}</code> سفارش غیرآرشیوی پیدا نشد.\n"
            f"اما {archived_count} سفارش آرشیوشده پیدا شد."
        )
    await message.answer(
        text,
        parse_mode="HTML",
        reply_markup=search_results_keyboard(
            active_results,
            view="active",
            active_count=active_count,
            archived_count=archived_count,
        ),
    )


@router.callback_query(F.data.startswith("order_mgmt|results|"))
async def order_management_results_switch(callback: CallbackQuery, state: FSMContext):
    if not is_admin(callback.from_user.id):
        return await callback.answer("دسترسی نداری.", show_alert=True)

    view = callback.data.split("|")[2]
    data = await state.get_data()
    keyword = (data.get("order_management_last_keyword") or "").strip()
    if not keyword:
        return await callback.answer("اطلاعات جست‌وجوی قبلی پیدا نشد. دوباره جستجو کن.", show_alert=True)

    active_results = search_orders_for_admin(keyword, archived_only=False)
    archived_results = search_orders_for_admin(keyword, archived_only=True)
    active_count = len(active_results)
    archived_count = len(archived_results)
    await store_search_context(state, keyword, active_count, archived_count)

    if view == "archived":
        if not archived_results:
            return await callback.answer("سفارش آرشیوشده‌ای برای این جستجو پیدا نشد.", show_alert=True)
        await callback.message.answer(
            f"نتایج آرشیوشده برای <code>{keyword}</code>:",
            parse_mode="HTML",
            reply_markup=search_results_keyboard(
                archived_results,
                view="archived",
                active_count=active_count,
                archived_count=archived_count,
            ),
        )
        return await callback.answer()

    if not active_results:
        return await callback.answer("برای این جستجو سفارش غیرآرشیوی پیدا نشد.", show_alert=True)

    await callback.message.answer(
        f"نتایج اصلی برای <code>{keyword}</code>:",
        parse_mode="HTML",
        reply_markup=search_results_keyboard(
            active_results,
            view="active",
            active_count=active_count,
            archived_count=archived_count,
        ),
    )
    await callback.answer()


@router.callback_query(F.data.startswith("order_mgmt|open|"))
async def order_management_open(callback: CallbackQuery, state: FSMContext):
    if not is_admin(callback.from_user.id):
        return await callback.answer("دسترسی نداری.", show_alert=True)

    order_id = int(callback.data.split("|")[2])
    order = get_order_with_plan(order_id)
    if not order:
        return await callback.answer("سفارش پیدا نشد.", show_alert=True)

    await state.set_state(None)
    await callback.message.answer(
        build_order_caption(order),
        parse_mode="HTML",
        reply_markup=order_actions_keyboard(order),
    )
    await callback.answer()


@router.callback_query(F.data.startswith("order_mgmt|cancel|"))
async def order_management_cancel(callback: CallbackQuery, state: FSMContext):
    if not is_admin(callback.from_user.id):
        return await callback.answer("دسترسی نداری.", show_alert=True)

    order_id = int(callback.data.split("|")[2])
    order = get_order_with_plan(order_id)
    if not order:
        return await callback.answer("سفارش پیدا نشد.", show_alert=True)

    await state.set_state(None)
    await callback.message.answer(
        f"آیا مطمئنی می‌خواهی سفارش <code>{order.get('username') or '-'}</code> را لغو کنی؟",
        parse_mode="HTML",
        reply_markup=cancel_confirm_keyboard(order_id),
    )
    await callback.answer()


@router.callback_query(F.data.startswith("order_mgmt|cancel_confirm|"))
async def order_management_cancel_confirm(callback: CallbackQuery, state: FSMContext, bot: Bot):
    if not is_admin(callback.from_user.id):
        return await callback.answer("دسترسی نداری.", show_alert=True)

    order_id = int(callback.data.split("|")[2])
    result = cancel_order(order_id=order_id, admin_id=callback.from_user.id)
    if not result:
        return await callback.answer("لغو سفارش انجام نشد.", show_alert=True)

    await state.set_state(None)
    await callback.message.answer(
        f"✅ سفارش #{order_id} لغو شد.\n"
        f"🆔 سرویس: <code>{result.get('username') or '-'}</code>\n"
        f"🔁 تعداد سفارش‌های وابسته لغوشده: {result.get('canceled_children') or 0}",
        parse_mode="HTML",
        reply_markup=admin_main_menu_keyboard(),
    )

    order = get_order_with_plan(order_id)
    if order and order.get("user_id"):
        await bot.send_message(
            int(order["user_id"]),
            f"❌ سفارش سرویس <code>{order.get('username') or '-'}</code> توسط ادمین لغو شد.",
            parse_mode="HTML",
        )
    if result.get("ibs_warning"):
        await callback.message.answer(
            "لغو سفارش در دیتابیس ثبت شد ولی عملیات آزادسازی/ریست روی IBS با هشدار همراه بود:\n"
            f"<code>{result['ibs_warning']}</code>",
            parse_mode="HTML",
        )
    await callback.answer("لغو شد.")


@router.callback_query(F.data.startswith("order_mgmt|plans|"))
async def order_management_plans(callback: CallbackQuery, state: FSMContext):
    if not is_admin(callback.from_user.id):
        return await callback.answer("دسترسی نداری.", show_alert=True)

    order_id = int(callback.data.split("|")[2])
    order = get_order_with_plan(order_id)
    if not order:
        return await callback.answer("سفارش پیدا نشد.", show_alert=True)

    await state.set_state(None)
    await callback.message.answer(
        f"پلن جدید برای سفارش <code>{order.get('username') or '-'}</code> را انتخاب کن:",
        parse_mode="HTML",
        reply_markup=plans_keyboard(order_id),
    )
    await callback.answer()


@router.callback_query(F.data.startswith("order_mgmt|plan_pick|"))
async def order_management_plan_pick(callback: CallbackQuery, state: FSMContext):
    if not is_admin(callback.from_user.id):
        return await callback.answer("دسترسی نداری.", show_alert=True)

    _, _, order_id, plan_id = callback.data.split("|", 3)
    order = get_order_with_plan(int(order_id))
    plan = next((item for item in get_plans_for_admin(include_archived=False) if int(item["id"]) == int(plan_id)), None)
    if not order or not plan:
        return await callback.answer("اطلاعات سفارش یا پلن پیدا نشد.", show_alert=True)

    await state.set_state(None)
    await callback.message.answer(
        build_plan_change_confirmation(order, plan),
        parse_mode="HTML",
        reply_markup=plan_confirm_keyboard(int(order_id), int(plan_id)),
    )
    await callback.answer()


@router.callback_query(F.data.startswith("order_mgmt|plan_apply|"))
async def order_management_plan_apply(callback: CallbackQuery, state: FSMContext, bot: Bot):
    if not is_admin(callback.from_user.id):
        return await callback.answer("دسترسی نداری.", show_alert=True)

    _, _, order_id, plan_id = callback.data.split("|", 3)
    result = change_order_plan(int(order_id), int(plan_id), admin_id=callback.from_user.id)
    if not result:
        return await callback.answer("تغییر پلن انجام نشد.", show_alert=True)

    await state.set_state(None)
    admin_lines = [
        f"✅ پلن سفارش #{order_id} تغییر کرد.",
        f"پلن قبلی: {result['old_plan_name'] or '-'}",
        f"پلن جدید: {result['new_plan_name'] or '-'}",
        f"اختلاف قیمت: {format_price(result['price_diff'])} تومان",
        f"موجودی جدید کاربر: {format_price(result['new_balance'] or 0)} تومان",
        f"شروع فعلی سرویس: {result.get('starts_at') or '-'}",
        f"پایان فعلی سرویس: {result.get('expires_at') or '-'}",
    ]
    if result.get("limit_applied"):
        admin_lines.append("🚦 چون مصرف از سقف پلن جدید بالاتر بود، محدودسازی سرعت دوباره اعمال شد.")
    await callback.message.answer(
        "\n".join(admin_lines),
        reply_markup=admin_main_menu_keyboard(),
    )

    order = get_order_with_plan(int(order_id))
    if order and order.get("user_id"):
        user_lines = [
            f"🛠 پلن سرویس <code>{order.get('username') or '-'}</code> توسط ادمین اصلاح شد.",
            f"پلن جدید: {result['new_plan_name'] or '-'}",
        ]
        if result.get("limit_applied"):
            user_lines.append("🚦 با توجه به سقف پلن جدید، محدودسازی سرعت سرویس هم دوباره بررسی و اعمال شد.")
        await bot.send_message(
            int(order["user_id"]),
            "\n".join(user_lines),
            parse_mode="HTML",
        )
    if result.get("ibs_warning"):
        await callback.message.answer(
            "پلن در دیتابیس تغییر کرد ولی اعمال آن روی IBS با هشدار همراه بود:\n"
            f"<code>{result['ibs_warning']}</code>",
            parse_mode="HTML",
        )
    await callback.answer("پلن تغییر کرد.")


@router.callback_query(F.data.startswith("order_mgmt|volume|"))
async def order_management_volume(callback: CallbackQuery, state: FSMContext):
    if not is_admin(callback.from_user.id):
        return await callback.answer("دسترسی نداری.", show_alert=True)

    order_id = int(callback.data.split("|")[2])
    order = get_order_with_plan(order_id)
    if not order:
        return await callback.answer("سفارش پیدا نشد.", show_alert=True)

    await state.update_data(order_management_order_id=order_id)
    await state.set_state(OrderManagementStates.waiting_for_volume)
    await callback.message.answer(
        f"تغییر حجم دستی برای سرویس <code>{order.get('username') or '-'}</code> را بفرست.\n"
        "عدد مثبت برای افزایش و عدد منفی برای کاهش بفرست.\n"
        "مثال: <code>1</code> یا <code>-1</code>",
        parse_mode="HTML",
    )
    await callback.answer()


@router.message(OrderManagementStates.waiting_for_volume)
async def order_management_receive_volume(message: Message, state: FSMContext, bot: Bot):
    if not is_admin(message.from_user.id):
        await state.set_state(None)
        return

    data = await state.get_data()
    order_id = data.get("order_management_order_id")
    try:
        volume_gb = int((message.text or "").strip())
    except Exception:
        await message.answer("فقط عدد صحیح بفرست. مثال: 1 یا -1")
        return

    result = adjust_manual_extra_volume(
        order_id=int(order_id),
        volume_gb=volume_gb,
        admin_id=message.from_user.id,
    )
    if not result.get("ok"):
        error = result.get("error")
        if error == "insufficient_extra_volume":
            await message.answer(
                f"کاهش حجم انجام نشد. حجم اضافه فعلی این سفارش فقط {result.get('current_extra_volume_gb') or 0} گیگ است."
            )
            return
        if error == "invalid_delta":
            await message.answer("عدد صفر قابل قبول نیست. مثال: 1 یا -1")
            return

        await state.set_state(None)
        await message.answer("تغییر حجم انجام نشد.", reply_markup=admin_main_menu_keyboard())
        return

    await state.set_state(None)
    delta = int(result["volume_delta_gb"])
    changed_volume = int(result["changed_volume_gb"])
    if delta > 0:
        user_text = f"✅ {changed_volume} گیگ حجم اضافه به سرویس <code>{result['username']}</code> شما افزوده شد."
        admin_text = f"✅ {changed_volume} گیگ به سرویس <code>{result['username']}</code> اضافه شد."
    else:
        user_text = f"⚠️ {changed_volume} گیگ از حجم اضافه سرویس <code>{result['username']}</code> شما کم شد."
        admin_text = f"✅ {changed_volume} گیگ از حجم اضافه سرویس <code>{result['username']}</code> کم شد."

    if result.get("limit_applied"):
        admin_text += "\n🚦 چون مصرف کاربر از سقف جدید عبور کرده بود، محدودسازی سرعت هم اعمال شد."
        user_text += "\n🚦 به دلیل عبور مصرف از سقف جدید، محدودسازی سرعت سرویس هم اعمال شد."

    await message.answer(
        f"{admin_text}\n"
        f"➕ مجموع حجم اضافه فعلی این سفارش: {result['new_extra_volume_gb']} گیگ",
        parse_mode="HTML",
        reply_markup=admin_main_menu_keyboard(),
    )

    order = get_order_with_plan(int(order_id))
    if order and order.get("user_id"):
        await bot.send_message(
            int(order["user_id"]),
            user_text,
            parse_mode="HTML",
        )
    if result.get("ibs_warning"):
        await message.answer(
            "تغییر حجم در دیتابیس ثبت شد ولی اعمال آن روی IBS با هشدار همراه بود:\n"
            f"<code>{result['ibs_warning']}</code>",
            parse_mode="HTML",
        )
