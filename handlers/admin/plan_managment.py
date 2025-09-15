import sqlite3
from typing import Optional, List, Tuple

from aiogram import Router, F
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import Message, CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup

from config import DB_PATH, ADMINS
from keyboards.admin_main_menu import admin_main_menu_keyboard

router = Router()

# --- helper DB functions ---
def get_all_plans() -> List[Tuple]:
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute("SELECT id, name, volume_gb, duration_months, duration_days, max_users, price, order_priority, visible, location, is_unlimited, group_name FROM plans ORDER BY order_priority DESC, id ASC")
    rows = cur.fetchall()
    conn.close()
    return rows

def get_plan(plan_id: int) -> Optional[Tuple]:
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute("SELECT id, name, volume_gb, duration_months, duration_days, max_users, price, order_priority, visible, location, is_unlimited, group_name FROM plans WHERE id = ?", (plan_id,))
    row = cur.fetchone()
    conn.close()
    return row

def add_plan_to_db(name, volume_gb, duration_months, duration_days, max_users, price, order_priority=0, visible=1, location=None, is_unlimited=0, group_name=None):
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute(
        """INSERT INTO plans (name, volume_gb, duration_months, duration_days, max_users, price, order_priority, visible, location, is_unlimited, group_name)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (name, volume_gb, duration_months, duration_days, max_users, price, order_priority, visible, location, is_unlimited, group_name)
    )
    conn.commit()
    conn.close()

def update_plan_field(plan_id: int, field: str, value):
    allowed = ["name", "volume_gb", "duration_months", "duration_days", "max_users", "price", "order_priority", "visible", "location", "is_unlimited", "group_name"]
    if field not in allowed:
        return False
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute(f"UPDATE plans SET {field} = ? WHERE id = ?", (value, plan_id))
    conn.commit()
    conn.close()
    return True

def delete_plan_from_db(plan_id: int):
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute("DELETE FROM plans WHERE id = ?", (plan_id,))
    conn.commit()
    conn.close()


# --- FSM states ---
class PlanStates(StatesGroup):
    waiting_for_action = State()
    waiting_for_value = State()
    waiting_for_add = State()


# --- admin check ---
def is_admin(user_id: int) -> bool:
    return str(user_id) in [str(a) for a in ADMINS]


# --- نمایش لیست پلن‌ها ---
@router.message(F.text == "📦 مدیریت پلن‌ها")
async def manage_plans_entry(msg: Message):
    if not is_admin(msg.from_user.id):
        return await msg.reply("دسترسی نداری 😅")
    await show_plans_list_message(msg)



async def show_plans_list_message(msg: Message):
    plans = get_all_plans()
    keyboard_rows = []
    for p in plans:
        pid, name, vol, m, d, maxu, price, prio, vis, loc, unlim, gname = p
        desc = f"{'✅' if vis else '🚫'} {name} | {price} تومان"
        keyboard_rows.append([InlineKeyboardButton(text=desc, callback_data=f"plan_select_{pid}")])
    keyboard_rows.append([InlineKeyboardButton(text="➕ افزودن پلن جدید", callback_data="plan_add")])
    keyboard_rows.append([InlineKeyboardButton(text="🔙 بازگشت", callback_data="plan_back_main")])
    keyboard = InlineKeyboardMarkup(inline_keyboard=keyboard_rows)
    await msg.answer("لیست پلن‌ها:", reply_markup=keyboard)

async def show_plans_list_callback(cb: CallbackQuery):
    await show_plans_list_message(cb.message)
    await cb.answer()


# --- بازگشت ---
@router.callback_query(F.data == "plan_back_main")
async def plan_back_main(cb: CallbackQuery, state: FSMContext):
    await state.clear()
    await cb.message.answer("بازگشت به منوی اصلی.", reply_markup=admin_main_menu_keyboard())
    await cb.answer()


# --- افزودن پلن ---
@router.callback_query(F.data == "plan_add")
async def plan_add_start(cb: CallbackQuery, state: FSMContext):
    await state.update_data(plan_action="add")
    await cb.message.answer(
        "فرمت:\n"
        "نام | حجمGB | ماه | روز | تعداد یوزر | قیمت | (اختیاری)اولویت\n\n"
        "مثال:\n۳۰ روزه | 40 | 1 | 30 | 1 | 100000 | 1"
    )
    await state.set_state(PlanStates.waiting_for_add)
    await cb.answer()

@router.message(PlanStates.waiting_for_add)
async def plan_add_receive(msg: Message, state: FSMContext):
    data = [d.strip() for d in msg.text.split("|")]
    if len(data) < 6:
        return await msg.answer("فرمت نادرست — حداقل نام، حجم، ماه، روز، یوزر، قیمت لازم است.")
    name, vol, m, d, maxu, price = data[:6]
    prio = int(data[6]) if len(data) >= 7 and data[6].isdigit() else 0
    add_plan_to_db(name, int(vol), int(m), int(d), int(maxu), int(price), prio, 1)
    await msg.answer("✅ پلن اضافه شد.")
    await state.clear()


# --- انتخاب پلن ---
@router.callback_query(F.data.startswith("plan_select_"))
async def plan_selected(cb: CallbackQuery, state: FSMContext):
    pid = int(cb.data.split("_")[2])
    row = get_plan(pid)
    if not row:
        return await cb.answer("پلن پیدا نشد.", show_alert=True)
    pid, name, vol, m, d, maxu, price, prio, vis, loc, unlim, gname = row
    caption = (
        f"پلن #{pid}\n"
        f"نام: {name}\n"
        f"حجم: {vol} GB\n"
        f"مدت: {m} ماه {d} روز\n"
        f"یوزر: {maxu}\n"
        f"قیمت: {price}\n"
        f"اولویت: {prio}\n"
        f"وضعیت: {'نمایش' if vis else 'مخفی'}\n"
        f"نام گروه: {gname or '-'}\n"
        f"لوکیشن: {loc or '-'}\n"
        f"نامحدود: {'✅' if unlim else '❌'}"
    )
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✏️ نام", callback_data=f"plan_edit_name_{pid}")],
        [InlineKeyboardButton(text="📦 حجم", callback_data=f"plan_edit_volume_gb_{pid}")],
        [InlineKeyboardButton(text="🗓 ماه", callback_data=f"plan_edit_duration_months_{pid}")],
        [InlineKeyboardButton(text="📅 روز", callback_data=f"plan_edit_duration_days_{pid}")],
        [InlineKeyboardButton(text="👥 یوزرها", callback_data=f"plan_edit_max_users_{pid}")],
        [InlineKeyboardButton(text="💰 قیمت", callback_data=f"plan_edit_price_{pid}")],
        [InlineKeyboardButton(text="🔢 اولویت", callback_data=f"plan_edit_order_priority_{pid}")],
        [InlineKeyboardButton(text="✅/🚫 نمایش/مخفی", callback_data=f"plan_toggle_{pid}")],
        [InlineKeyboardButton(text="❌ حذف پلن", callback_data=f"plan_delete_{pid}")],
        [InlineKeyboardButton(text="🔙 بازگشت", callback_data="manage_plans")],
    ])
    await state.update_data(plan_id=pid)
    await cb.message.answer(caption, reply_markup=keyboard)
    await state.set_state(PlanStates.waiting_for_action)
    await cb.answer()


# --- toggle visible ---
@router.callback_query(PlanStates.waiting_for_action, F.data.startswith("plan_toggle_"))
async def plan_toggle(cb: CallbackQuery, state: FSMContext):
    pid = int(cb.data.split("_")[2])
    plan = get_plan(pid)
    new_vis = 0 if plan[8] else 1
    update_plan_field(pid, "visible", new_vis)
    await cb.message.answer(f"پلن #{pid} {'نمایش داده میشه' if new_vis else 'مخفی شد'}.")
    await state.clear()
    await show_plans_list_callback(cb)


# --- delete ---
@router.callback_query(PlanStates.waiting_for_action, F.data.startswith("plan_delete_"))
async def plan_delete(cb: CallbackQuery, state: FSMContext):
    pid = int(cb.data.split("_")[2])
    delete_plan_from_db(pid)
    await cb.message.answer(f"🗑️ پلن #{pid} حذف شد.")
    await state.clear()
    await show_plans_list_callback(cb)


# --- edit field ---
@router.callback_query(PlanStates.waiting_for_action, F.data.startswith("plan_edit_"))
async def plan_edit_start(cb: CallbackQuery, state: FSMContext):
    tmp = cb.data[len("plan_edit_"):]
    field_name, pid = tmp.rsplit("_", 1)
    pid = int(pid)
    field_map = {
        "name": "نام",
        "volume_gb": "حجم GB",
        "duration_months": "ماه",
        "duration_days": "روز",
        "max_users": "یوزرها",
        "price": "قیمت",
        "order_priority": "اولویت"
    }
    if field_name not in field_map:
        return await cb.answer("فیلد نامعتبر.", show_alert=True)
    await state.update_data(edit_plan_id=pid, edit_field=field_name)
    await cb.message.answer(f"لطفاً مقدار جدید برای {field_map[field_name]} را بفرستید:")
    await state.set_state(PlanStates.waiting_for_value)
    await cb.answer()

@router.message(PlanStates.waiting_for_value)
async def plan_receive_new_value(msg: Message, state: FSMContext):
    data = await state.get_data()
    pid = data.get("edit_plan_id")
    field = data.get("edit_field")
    if not pid or not field:
        await msg.answer("خطای وضعیت. دوباره تلاش کنید.")
        return await state.clear()
    value_text = msg.text.strip()
    if field in ["volume_gb", "duration_months", "duration_days", "max_users", "price", "order_priority"]:
        try:
            value = int(value_text)
        except:
            return await msg.answer("این فیلد باید عدد باشد.")
    else:
        value = value_text
    if update_plan_field(pid, field, value):
        await msg.answer("✅ بروزرسانی شد.")
    else:
        await msg.answer("❌ خطا در بروزرسانی.")
    await state.clear()
    await show_plans_list_message(msg)
