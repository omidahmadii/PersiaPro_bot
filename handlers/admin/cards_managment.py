import sqlite3
from typing import Optional

from aiogram import Router, F
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import Message, CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup

from config import DB_PATH, ADMINS
from keyboards.admin_main_menu import admin_main_menu_keyboard  # فرض بر وجودش

router = Router()


# --- helper DB functions ---
def mask_card_number(num: Optional[str]) -> str:
    if not num:
        return "بدون شماره"
    s = ''.join(ch for ch in num if ch.isdigit())
    # چهار تا چهار تا جدا کنیم با '-'
    return '-'.join([s[i:i + 4] for i in range(0, len(s), 4)])


def get_all_cards():
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute(
        "SELECT id, card_number, owner_name, bank_name, priority, is_active FROM bank_cards ORDER BY priority DESC, id ASC")
    rows = cur.fetchall()
    conn.close()
    return rows


def get_card(card_id: int):
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute("SELECT id, card_number, owner_name, bank_name, priority, is_active FROM bank_cards WHERE id = ?",
                (card_id,))
    row = cur.fetchone()
    conn.close()
    return row


def add_card_to_db(card_number, owner_name, bank_name, priority=0, is_active=1):
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute(
        "INSERT INTO bank_cards (card_number, owner_name, bank_name, priority, is_active) VALUES (?, ?, ?, ?, ?)",
        (card_number, owner_name, bank_name, priority, is_active)
    )
    conn.commit()
    conn.close()


def update_card_field(card_id, field, value):
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    if field not in ("card_number", "owner_name", "bank_name", "priority", "is_active"):
        conn.close()
        return False
    cur.execute(f"UPDATE bank_cards SET {field} = ? WHERE id = ?", (value, card_id))
    conn.commit()
    conn.close()
    return True


def delete_card_from_db(card_id):
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute("DELETE FROM bank_cards WHERE id = ?", (card_id,))
    conn.commit()
    conn.close()


# --- FSM states ---
class CardStates(StatesGroup):
    waiting_for_action = State()
    waiting_for_value = State()
    waiting_for_add = State()


# --- admin check ---
def is_admin(user_id: int) -> bool:
    return str(user_id) in [str(a) for a in ADMINS]


# --- نمایش لیست کارت‌ها برای Message ---
@router.message(F.text == "💳 مدیریت کارت‌ها")
async def manage_cards_entry(msg: Message):
    if not is_admin(msg.from_user.id):
        return await msg.reply("دسترسی نداری عزیز 😅")
    await show_cards_list_message(msg)


# --- نمایش لیست کارت‌ها برای Callback ---
async def show_cards_list_callback(cb: CallbackQuery):
    if not is_admin(cb.from_user.id):
        return await cb.answer("دسترسی نداری عزیز 😅", show_alert=True)
    cards = get_all_cards()
    keyboard_rows = []
    for c in cards:
        cid, num, owner, bank, prio, active = c
        text = f"{'✅' if active else '🚫'} {mask_card_number(num)} | {bank or '-'} | {owner or '-'} | اولویت:{prio}"
        keyboard_rows.append([InlineKeyboardButton(text=text, callback_data=f"card_select_{cid}")])
    keyboard_rows.append([InlineKeyboardButton(text="➕ افزودن کارت جدید", callback_data="card_add")])
    keyboard_rows.append([InlineKeyboardButton(text="🔙 بازگشت به منوی اصلی", callback_data="card_back_main")])
    keyboard = InlineKeyboardMarkup(inline_keyboard=keyboard_rows)
    await cb.message.answer("لیست کارت‌ها:", reply_markup=keyboard)
    await cb.answer()


async def show_cards_list_message(msg: Message):
    cards = get_all_cards()
    keyboard_rows = []
    for c in cards:
        cid, num, owner, bank, prio, active = c
        text = f"{'✅' if active else '🚫'} {mask_card_number(num)} | {bank or '-'} | {owner or '-'} | اولویت:{prio}"
        keyboard_rows.append([InlineKeyboardButton(text=text, callback_data=f"card_select_{cid}")])
    keyboard_rows.append([InlineKeyboardButton(text="➕ افزودن کارت جدید", callback_data="card_add")])
    keyboard_rows.append([InlineKeyboardButton(text="🔙 بازگشت به منوی اصلی", callback_data="card_back_main")])
    keyboard = InlineKeyboardMarkup(inline_keyboard=keyboard_rows)
    await msg.answer("لیست کارت‌ها:", reply_markup=keyboard)


# --- بازگشت به منوی اصلی ---
@router.callback_query(F.data == "card_back_main")
async def card_back_main(cb: CallbackQuery, state: FSMContext):
    if not is_admin(cb.from_user.id):
        return await cb.answer("دسترسی ندارید.", show_alert=True)
    await state.clear()
    await cb.message.answer("بازگشت به منوی اصلی.", reply_markup=admin_main_menu_keyboard())
    await cb.answer()


# --- افزودن کارت جدید ---
@router.callback_query(F.data == "card_add")
async def card_add_start(cb: CallbackQuery, state: FSMContext):
    if not is_admin(cb.from_user.id):
        return await cb.answer("دسترسی ندارید.", show_alert=True)
    await state.update_data(card_action="add")
    await cb.message.answer(
        "فرمت:\nشماره کارت | نام صاحب | نام بانک | (اختیاری)اولویت\n"
        "مثال:\n6037123412341234 | علی رضایی | بانک ملی | 1"
    )
    await state.set_state(CardStates.waiting_for_add)
    await cb.answer()


@router.message(CardStates.waiting_for_add)
async def card_add_receive(msg: Message, state: FSMContext):
    data = msg.text.split("|")
    if len(data) < 3:
        return await msg.answer("فرمت نادرست — حداقل شماره، نام صاحب و نام بانک لازم است.")
    card_number = data[0].strip()
    owner = data[1].strip()
    bank = data[2].strip()
    prio = 0
    if len(data) >= 4:
        try:
            prio = int(data[3].strip())
        except:
            prio = 0
    add_card_to_db(card_number, owner, bank, prio, 1)
    await msg.answer("✅ کارت اضافه شد.")
    await state.clear()


# --- انتخاب کارت ---
@router.callback_query(F.data.startswith("card_select_"))
async def card_selected(cb: CallbackQuery, state: FSMContext):
    if not is_admin(cb.from_user.id):
        return await cb.answer("دسترسی ندارید.", show_alert=True)
    card_id = int(cb.data.split("_")[2])
    row = get_card(card_id)
    if not row:
        return await cb.answer("کارت پیدا نشد.", show_alert=True)
    cid, num, owner, bank, prio, active = row
    caption = (
        f"کارت #{cid}\n"
        f"شماره: {mask_card_number(num)}\n"
        f"صاحب: {owner or '-'}\n"
        f"بانک: {bank or '-'}\n"
        f"اولویت: {prio}\n"
        f"وضعیت: {'فعال' if active else 'غیرفعال'}"
    )
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✏️ شماره", callback_data=f"card_edit_card_number_{cid}")],
        [InlineKeyboardButton(text="👤 مالک", callback_data=f"card_edit_owner_name_{cid}")],
        [InlineKeyboardButton(text="🏦 بانک", callback_data=f"card_edit_bank_name_{cid}")],
        [InlineKeyboardButton(text="🔢 اولویت", callback_data=f"card_edit_priority_{cid}")],
        [InlineKeyboardButton(text="✅/🚫 فعال/غیرفعال", callback_data=f"card_toggle_{cid}")],
        [InlineKeyboardButton(text="❌ حذف کارت", callback_data=f"card_delete_{cid}")],
        [InlineKeyboardButton(text="🔙 بازگشت", callback_data="manage_cards")],
    ])
    await state.update_data(card_id=cid)
    await cb.message.answer(caption, reply_markup=keyboard)
    await state.set_state(CardStates.waiting_for_action)
    await cb.answer()


# --- بازگشت به لیست ---
@router.callback_query(F.data == "card_back_list")
async def card_back_list(cb: CallbackQuery, state: FSMContext):
    await state.clear()
    await show_cards_list_callback(cb)


# --- toggle active ---
@router.callback_query(CardStates.waiting_for_action, F.data.startswith("card_toggle_"))
async def card_toggle(cb: CallbackQuery, state: FSMContext):
    if not is_admin(cb.from_user.id):
        return await cb.answer("دسترسی ندارید.", show_alert=True)
    cid = int(cb.data.split("_")[2])
    card = get_card(cid)
    if not card:
        return await cb.answer("کارت پیدا نشد.", show_alert=True)
    new_active = 0 if card[5] else 1
    update_card_field(cid, "is_active", new_active)
    await cb.message.answer(f"✅ کارت #{cid} {'فعال' if new_active else 'غیرفعال'} شد.")
    await state.clear()
    await show_cards_list_callback(cb)


# --- delete ---
@router.callback_query(CardStates.waiting_for_action, F.data.startswith("card_delete_"))
async def card_delete(cb: CallbackQuery, state: FSMContext):
    if not is_admin(cb.from_user.id):
        return await cb.answer("دسترسی ندارید.", show_alert=True)
    cid = int(cb.data.split("_")[2])
    delete_card_from_db(cid)
    await cb.message.answer(f"🗑️ کارت #{cid} حذف شد.")
    await state.clear()
    await show_cards_list_callback(cb)


# --- edit field ---
@router.callback_query(CardStates.waiting_for_action, F.data.startswith("card_edit_"))
async def card_edit_start(cb: CallbackQuery, state: FSMContext):
    if not is_admin(cb.from_user.id):
        return await cb.answer("دسترسی ندارید.", show_alert=True)
    tmp = cb.data[len("card_edit_"):]
    field_name, cid = tmp.rsplit("_", 1)
    cid = int(cid)
    field_map = {
        "card_number": "شماره کارت",
        "owner_name": "نام صاحب",
        "bank_name": "نام بانک",
        "priority": "اولویت"
    }
    if field_name not in field_map:
        return await cb.answer("فیلد نامعتبر.", show_alert=True)
    await state.update_data(edit_card_id=cid, edit_field=field_name)
    await cb.message.answer(f"لطفاً مقدار جدید برای {field_map[field_name]} را بفرستید:")
    await state.set_state(CardStates.waiting_for_value)
    await cb.answer()


@router.message(CardStates.waiting_for_value)
async def card_receive_new_value(msg: Message, state: FSMContext):
    data = await state.get_data()
    cid = data.get("edit_card_id")
    field = data.get("edit_field")
    if not cid or not field:
        await msg.answer("خطای وضعیت. دوباره تلاش کنید.")
        return await state.clear()
    value_text = msg.text.strip()
    if field == "priority":
        try:
            value = int(value_text)
        except:
            return await msg.answer("اولویت باید عدد باشد.")
    else:
        value = value_text
    if update_card_field(cid, field, value):
        await msg.answer("✅ بروزرسانی شد.")
    else:
        await msg.answer("❌ خطا در بروزرسانی.")
    await state.clear()
    await show_cards_list_message(msg)


# --- command سریع ---
@router.message(F.text.startswith("/edit_card"))
async def quick_edit_cmd(msg: Message):
    if not is_admin(msg.from_user.id):
        return await msg.reply("دسترسی نداری عزیز 😅")
    parts = msg.text.split(maxsplit=3)
    if len(parts) < 4:
        return await msg.reply("فرمت: /edit_card <id> <field> <value>")
    try:
        cid = int(parts[1])
    except:
        return await msg.reply("id نامعتبر.")
    field, value = parts[2], parts[3]
    if field == "priority":
        try:
            value = int(value)
        except:
            return await msg.reply("priority باید عدد باشد.")
    if update_card_field(cid, field, value):
        await msg.reply("✅ بروزرسانی انجام شد.")
    else:
        await msg.reply("❌ خطا یا فیلد غیرمجاز.")
