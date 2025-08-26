# handlers/user/tutorial.py
# اینلاین، بدون تایمر، بدون "بازگشت به منوی اصلی" و بدون "بازگشت به آموزش اتصال"
# با breadcrumb و smart_edit (text/caption/new-message) + بدون alert/text روی callbacks

from typing import Final, Optional

from aiogram import Router, F
from aiogram.enums import ParseMode, ContentType
from aiogram.exceptions import TelegramBadRequest
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import StatesGroup, State
from aiogram.types import (
    FSInputFile,
    Message,
    CallbackQuery,
    InlineKeyboardMarkup,
)
from aiogram.utils.keyboard import InlineKeyboardBuilder

router: Final = Router()

# ---------------------------------------------------------------------------
# 📁  Static media
# ---------------------------------------------------------------------------
MEDIA_DIR: Final = "media"

def mfile(name: str) -> FSInputFile:
    return FSInputFile(f"{MEDIA_DIR}/{name}")

OVPN_FILE = mfile("PersiaPro V1.ovpn")
OVPN_IMAGES = [mfile(f"ovpn_img0{i}.jpg") for i in range(1, 5)]
L2TP_IMAGES = [mfile(f"l2tp_img0{i}.jpg") for i in range(1, 3)]

# ---------------------------------------------------------------------------
# 🗂  States
# ---------------------------------------------------------------------------
class Tutorial(StatesGroup):
    menu = State()
    ios_method = State()
    ios_l2tp_step = State()
    ios_ovpn_step = State()

# ---------------------------------------------------------------------------
# 🛡  Helpers
# ---------------------------------------------------------------------------
async def smart_edit(
    message: Message,
    *,
    text: Optional[str] = None,
    reply_markup: Optional[InlineKeyboardMarkup] = None,
    parse_mode: Optional[ParseMode] = ParseMode.HTML,
):
    """
    اگر پیام text داشت => edit_text
    اگر caption داشت => edit_caption
    اگر هیچ‌کدوم نبود => answer جدید
    خطای "message is not modified" نادیده گرفته می‌شود.
    """
    try:
        if text is None:
            # فقط تغییر کیبورد
            return await message.edit_reply_markup(reply_markup=reply_markup)

        # اولویت: اگر پیام متنی است
        if message.text is not None:
            return await message.edit_text(text, reply_markup=reply_markup, parse_mode=parse_mode)

        # اگر پیام عکس/ویدیو/سند با کپشن است
        if message.caption is not None:
            return await message.edit_caption(caption=text, reply_markup=reply_markup, parse_mode=parse_mode)

        # در غیر اینصورت پیام جدید بده
        return await message.answer(text, reply_markup=reply_markup, parse_mode=parse_mode)

    except TelegramBadRequest as e:
        s = str(e)
        if "message is not modified" in s or "there is no text in the message to edit" in s:
            # در صورت عدم امکان ادیت، پیام جدید بده (fallback)
            if text is not None:
                return await message.answer(text, reply_markup=reply_markup, parse_mode=parse_mode)
            return None
        raise

# ---------------------------------------------------------------------------
# ⌨️  Inline Keyboards
# ---------------------------------------------------------------------------
def kb_root() -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    kb.button(text="📱 آیفون", callback_data="dev:ios")
    kb.button(text="📱 اندروید ⛏ به‌زودی", callback_data="noop")
    kb.button(text="💻 ویندوز ⛏ به‌زودی", callback_data="noop")
    kb.button(text="🖥 مک ⛏ به‌زودی", callback_data="noop")
    kb.button(text="🐧 لینوکس ⛏ به‌زودی", callback_data="noop")
    kb.button(text="📺 Smart TV ⛏ به‌زودی", callback_data="noop")
    kb.button(text="🎮 کنسول بازی ⛏ به‌زودی", callback_data="noop")
    kb.adjust(1, 2, 2, 2)
    return kb.as_markup()

def kb_ios_methods() -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    kb.button(text="🔸 آموزش L2TP", callback_data="ios:l2tp:start")
    kb.button(text="🔸 آموزش OpenVPN", callback_data="ios:ovpn:start")
    kb.button(text="⬅️ بازگشت", callback_data="back:root")
    kb.adjust(2, 1)
    return kb.as_markup()

def kb_next(flow: str) -> InlineKeyboardMarkup:
    # flow ∈ { "l2tp", "ovpn" }
    kb = InlineKeyboardBuilder()
    kb.button(text="➡️ مرحله بعد", callback_data=f"step:{flow}:next")
    kb.button(text="⬅️ بازگشت", callback_data="back:ios_methods")
    kb.adjust(1, 1)
    return kb.as_markup()

# ---------------------------------------------------------------------------
# 🚀  Entry
# ---------------------------------------------------------------------------
@router.message(F.text == "📚 آموزش")
async def start_tutorial(message: Message, state: FSMContext):
    await state.set_state(Tutorial.menu)
    await message.answer(
        "🏷️ <b>آموزش</b>\n"
        "دستگاه مورد نظر را انتخاب کنید:",
        reply_markup=kb_root(),
        parse_mode=ParseMode.HTML,
    )

# ---------------------------------------------------------------------------
# 📱 iOS
# ---------------------------------------------------------------------------
@router.callback_query(F.data == "dev:ios")
async def ios_methods(call: CallbackQuery, state: FSMContext):
    await state.set_state(Tutorial.ios_method)
    text = (
        "🏷️ <b>آموزش › iOS</b>\n\n"
        "اگر امکانش هست، <b>OpenVPN</b> را نصب و استفاده کنید (پیشنهاد ما).\n"
        "اگر دسترسی ندارید، فعلاً از <b>L2TP</b> استفاده کنید و بعداً به OpenVPN سویچ کنید.\n\n"
        "👇 یکی را انتخاب کنید:"
    )
    await smart_edit(call.message, text=text, reply_markup=kb_ios_methods(), parse_mode=ParseMode.HTML)
    # پاسخِ callback بدون متن/هشدار (سریع و بی‌صدا)
    await call.answer()

# ---------------------------------------------------------------------------
# 🧱 دکمه‌های به‌زودی (بی‌صدا)
# ---------------------------------------------------------------------------
@router.callback_query(F.data == "noop")
async def noop_silent(call: CallbackQuery):
    # هیچ کاری نکن؛ فقط ack بی‌صدا تا لودینگ متوقف شود
    await call.answer()

# ---------------------------------------------------------------------------
# 📚  L2TP steps (iOS)
# ---------------------------------------------------------------------------
@router.callback_query(F.data == "ios:l2tp:start")
async def start_l2tp(call: CallbackQuery, state: FSMContext):
    await state.set_state(Tutorial.ios_l2tp_step)
    await state.update_data(step=0)
    text = (
        "🏷️ <b>آموزش › iOS › L2TP</b>\n"
        "مرحله ۱: از Settings → VPN → <b>Add VPN Configuration</b>."
    )
    await smart_edit(call.message, text=text, reply_markup=kb_next("l2tp"), parse_mode=ParseMode.HTML)
    await call.answer()

@router.callback_query(F.data == "step:l2tp:next")
async def next_l2tp_step(call: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    step = int(data.get("step", 0)) + 1
    await state.update_data(step=step)

    if step == 1:
        await call.message.answer_photo(
            photo=L2TP_IMAGES[0],
            caption="📸 نمونهٔ تنظیمات L2TP – فیلدهای Server / Account / Password را وارد کنید.",
            reply_markup=kb_next("l2tp"),
        )
    elif step == 2:
        await call.message.answer_photo(
            photo=L2TP_IMAGES[1],
            caption="📸 اتصال برقرار شد ✅ اگر مشکلی بود به پشتیبانی پیام بده.",
        )
        await state.clear()
    await call.answer()

# ---------------------------------------------------------------------------
# 📚  OpenVPN steps (iOS)
# ---------------------------------------------------------------------------
@router.callback_query(F.data == "ios:ovpn:start")
async def start_ovpn(call: CallbackQuery, state: FSMContext):
    await state.set_state(Tutorial.ios_ovpn_step)
    await state.update_data(step=0)
    text = (
        "🏷️ <b>آموزش › iOS › OpenVPN</b>\n"
        "مرحله ۱: اپ <b>OpenVPN Connect</b> را از App Store نصب کنید:\n"
        "🔗 https://apps.apple.com/us/app/openvpn-connect/id590379981"
    )
    await smart_edit(call.message, text=text, reply_markup=kb_next("ovpn"), parse_mode=ParseMode.HTML)
    await call.answer()

@router.callback_query(F.data == "step:ovpn:next")
async def next_ovpn_step(call: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    step = int(data.get("step", 0)) + 1
    await state.update_data(step=step)

    if step == 1:
        await call.message.answer_document(
            OVPN_FILE,
            caption="🔐 فایل تنظیمات OpenVPN را ایمپورت کنید.",
        )
        await call.message.answer_photo(
            OVPN_IMAGES[0],
            caption="📸 وارد اپ شوید و روی Import بزنید.",
            reply_markup=kb_next("ovpn"),
        )
    elif step == 2:
        await call.message.answer_photo(
            OVPN_IMAGES[1],
            caption="📸 پروفایل آماده است.",
            reply_markup=kb_next("ovpn"),
        )
    elif step == 3:
        await call.message.answer_photo(
            OVPN_IMAGES[2],
            caption="📸 دکمهٔ Connect را بزنید.",
            reply_markup=kb_next("ovpn"),
        )
    elif step == 4:
        await call.message.answer_photo(
            OVPN_IMAGES[3],
            caption="📸 اتصال برقرار شد ✅",
        )
        await call.message.answer_document(
            OVPN_FILE,
            caption="🔐 اگر نیاز بود دوباره فایل کانفیگ:",
        )
        await state.clear()
    await call.answer()

# ---------------------------------------------------------------------------
# 🔙  Backهای داخل آموزش
# ---------------------------------------------------------------------------
@router.callback_query(F.data == "back:root")
async def back_to_root(call: CallbackQuery, state: FSMContext):
    await state.set_state(Tutorial.menu)
    await smart_edit(
        call.message,
        text="🏷️ <b>آموزش</b>\nدستگاه مورد نظر را انتخاب کنید:",
        reply_markup=kb_root(),
        parse_mode=ParseMode.HTML,
    )
    await call.answer()

@router.callback_query(F.data == "back:ios_methods")
async def back_to_ios_methods(call: CallbackQuery, state: FSMContext):
    await state.set_state(Tutorial.ios_method)
    await smart_edit(
        call.message,
        text="🏷️ <b>آموزش › iOS</b>\nروش اتصال را انتخاب کنید:",
        reply_markup=kb_ios_methods(),
        parse_mode=ParseMode.HTML,
    )
    await call.answer()
