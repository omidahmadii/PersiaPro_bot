# handlers/user/tutorial.py
# اینلاین، بدون تایمر، بدون "بازگشت به منوی اصلی" و بدون "بازگشت به آموزش اتصال"
# با breadcrumb و smart_edit (text/caption/new-message) + بدون alert/text روی callbacks

from typing import Final, Optional
from config import ADMINS
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
from config import ANDROID_OVPN_VIDEO, ANDROID_L2TP_VIDEO, WINDOWS_L2TP_VIDEO, IOS_OVPN_VIDEO, IOS_L2TP_VIDEO, \
    ANDROID_ANYCONNECT_VIDEO, IOS_ANYCONNECT_VIDEO

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
    android_method = State()
    windows_method = State()

    ios_ovpn_step = State()
    ios_anyconnect_step = State()

    android_ovpn_step = State()
    android_anyconnect_step = State()


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
    kb.button(text="📱 اندروید", callback_data="dev:android")
    kb.button(text="📱 آیفون", callback_data="dev:ios")
    # kb.button(text="🖥 مک", callback_data="noop")
    kb.button(text="💻 ویندوز", callback_data="dev:windows")
    # kb.button(text="📺 تلوزیون", callback_data="noop")
    # kb.button(text="🐧 لینوکس", callback_data="noop")
    kb.adjust(2, 2, 2, 2)
    return kb.as_markup()


def kb_ios_methods() -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    kb.button(text="🔸 آموزش L2TP", callback_data="ios:l2tp:start")
    kb.button(text="🔸 آموزش OpenVPN", callback_data="ios:ovpn:start")
    kb.button(text="⬅️ بازگشت", callback_data="back:root")
    kb.adjust(2, 1)
    return kb.as_markup()


def kb_android_methods() -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    kb.button(text="🔸 آموزش Any connect", callback_data="android:anyconnect:start")
    kb.button(text="🔸 آموزش OpenVPN", callback_data="android:ovpn:start")
    kb.button(text="⬅️ بازگشت", callback_data="back:root")
    kb.adjust(2, 1)
    return kb.as_markup()


def kb_windows_methods() -> InlineKeyboardMarkup:
    kb = InlineKeyboardBuilder()
    kb.button(text="🔸 آموزش L2TP", callback_data="windows:l2tp:start")
    # kb.button(text="🔸 آموزش Any connect", callback_data="android:anyconnect:start")
    # kb.button(text="🔸 آموزش OpenVPN", callback_data="android:ovpn:start")
    kb.button(text="⬅️ بازگشت", callback_data="back:root")
    kb.adjust(1, 1)
    return kb.as_markup()


def kb_next_ios(flow: str) -> InlineKeyboardMarkup:
    # flow ∈ { "l2tp", "ovpn" }
    kb = InlineKeyboardBuilder()
    kb.button(text="➡️ مرحله بعد", callback_data=f"ios_step:{flow}:next")
    kb.button(text="⬅️ بازگشت", callback_data="back:ios_methods")
    kb.adjust(1, 1)
    return kb.as_markup()


def kb_next_android(flow: str) -> InlineKeyboardMarkup:
    # flow ∈ { "l2tp", "ovpn" }
    kb = InlineKeyboardBuilder()
    kb.button(text="➡️ مرحله بعد", callback_data=f"android_step:{flow}:next")
    # kb.button(text="⬅️ بازگشت", callback_data="back:android_methods")
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
        "🏷️ <b>آموزش › آیفون</b>\n\n"
        "پیشنهاد ما <b>OpenVPN</b>\n\n"

    )
    await smart_edit(call.message, text=text, reply_markup=kb_ios_methods(), parse_mode=ParseMode.HTML)
    # پاسخِ callback بدون متن/هشدار (سریع و بی‌صدا)
    await call.answer()


# ---------------------------------------------------------------------------
# 📱 android
# ---------------------------------------------------------------------------
@router.callback_query(F.data == "dev:android")
async def android_methods(call: CallbackQuery, state: FSMContext):
    await state.set_state(Tutorial.android_method)
    text = (
        "🏷️ <b>آموزش › اندروید</b>\n\n"
        "پیشنهاد ما <b>OpenVPN</b>\n\n"
    )
    await smart_edit(call.message, text=text, reply_markup=kb_android_methods(), parse_mode=ParseMode.HTML)
    # پاسخِ callback بدون متن/هشدار (سریع و بی‌صدا)
    await call.answer()


# ---------------------------------------------------------------------------
# 📱 windows
# ---------------------------------------------------------------------------
@router.callback_query(F.data == "dev:windows")
async def windows_methods(call: CallbackQuery, state: FSMContext):
    await state.set_state(Tutorial.windows_method)
    text = (
        "🏷️ <b>آموزش › ویندوز</b>\n\n"
        "پیشنهاد ما <b>L2TP</b>\n\n"
    )
    await smart_edit(call.message, text=text, reply_markup=kb_windows_methods(), parse_mode=ParseMode.HTML)
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
# 📚 iOS L2TP steps
# ---------------------------------------------------------------------------
@router.callback_query(F.data == "ios:l2tp:start")
async def start_l2tp(call: CallbackQuery, state: FSMContext):
    await call.message.answer_video(
        IOS_L2TP_VIDEO,
        caption="🔐 جهت اتصال از طریق ستینگ آیفون از این آموزش استفاده نمایید.",
    )
    await state.clear()


# ---------------------------------------------------------------------------
# 📚  iOS OpenVPN steps
# ---------------------------------------------------------------------------
@router.callback_query(F.data == "ios:ovpn:start")
async def start_ovpn(call: CallbackQuery, state: FSMContext):
    await state.set_state(Tutorial.ios_ovpn_step)
    await state.update_data(step=0)
    text = (
        "ابتدا <b>OpenVPN Connect</b> را از App Store نصب کنید:\n\n"
        "🔗 https://apps.apple.com/us/app/openvpn-connect/id590379981"
    )
    await smart_edit(call.message, text=text, reply_markup=kb_next_ios("ovpn"), parse_mode=ParseMode.HTML)
    await call.answer()

@router.callback_query(F.data == "ios_step:ovpn:next")
async def next_ovpn_step(call: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    step = int(data.get("step", 0)) + 1
    await state.update_data(step=step)

    if step == 1:

        await call.message.answer_video(
            IOS_OVPN_VIDEO,
            caption="🔐 جهت دریافت فایل تنظیمات OpenVPN به مرحله ی بعد بروید",
            reply_markup=kb_next_ios("ovpn"),
        )

    elif step == 2:
        await call.message.answer_document(
            OVPN_FILE,
            caption="🔐 فایل تنظیمات OpenVPN",
        )
        await state.clear()
    await call.answer()


# ---------------------------------------------------------------------------
# 📚  ios AnyConnect steps
# ---------------------------------------------------------------------------
@router.callback_query(F.data == "ios:anyconnect:start")
async def start_anyconnect(call: CallbackQuery, state: FSMContext):
    await state.set_state(Tutorial.ios_anyconnect_step)
    await state.update_data(step=0)
    text = (
        "ابتدا <b>Cisco Secure Client</b> را از App Store نصب کنید:\n\n"
        "🔗 https://apps.apple.com/us/app/cisco-secure-client/id1135064690"
    )
    await smart_edit(call.message, text=text, reply_markup=kb_next_ios("anyconnect"), parse_mode=ParseMode.HTML)
    await call.answer()


@router.callback_query(F.data == "ios_step:anyconnect:next")
async def next_anyconnect_step(call: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    step = int(data.get("step", 0)) + 1
    await state.update_data(step=step)

    if step == 1:
        await call.message.answer_video(
            IOS_ANYCONNECT_VIDEO,
            caption="🔐 جهت اتصال از طریق AnyConnect آیفون از این آموزش استفاده نمایید.",
        )
        await state.clear()
    await call.answer()

# ---------------------------------------------------------------------------
# 📚  android OpenVPN steps
# ---------------------------------------------------------------------------
@router.callback_query(F.data == "android:ovpn:start")
async def start_ovpn(call: CallbackQuery, state: FSMContext):
    await state.set_state(Tutorial.android_ovpn_step)
    await state.update_data(step=0)
    text = (
        "مرحله ۱:\n"
        "ابتدا <b>OpenVPN Connect</b> را از Play Store نصب کنید:\n\n"
        "🔗 https://play.google.com/store/apps/details?id=net.openvpn.openvpn&pcampaignid=web_share"
    )
    await smart_edit(call.message, text=text, reply_markup=kb_next_android("ovpn"), parse_mode=ParseMode.HTML)
    await call.answer()


@router.callback_query(F.data == "android_step:ovpn:next")
async def next_ovpn_step(call: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    step = int(data.get("step", 0)) + 1
    await state.update_data(step=step)

    if step == 1:

        await call.message.answer_video(
            ANDROID_OVPN_VIDEO,
            caption="🔐 جهت دریافت فایل تنظیمات OpenVPN به مرحله ی بعد بروید",
            reply_markup=kb_next_android("ovpn"),
        )

    elif step == 2:
        await call.message.answer_document(
            OVPN_FILE,
            caption="🔐 فایل تنظیمات OpenVPN",
        )
        await state.clear()
    await call.answer()


# ---------------------------------------------------------------------------
# 📚 android L2TP steps
# ---------------------------------------------------------------------------
@router.callback_query(F.data == "android:l2tp:start")
async def start_l2tp(call: CallbackQuery, state: FSMContext):
    await call.message.answer_video(
        ANDROID_L2TP_VIDEO,
        caption="🔐 جهت اتصال از طریق ستینگ اندروید از این آموزش استفاده نمایید.",
    )
    await state.clear()


# ---------------------------------------------------------------------------
# 📚  android AnyConnect steps
# ---------------------------------------------------------------------------
@router.callback_query(F.data == "android:anyconnect:start")
async def start_anyconnect(call: CallbackQuery, state: FSMContext):
    await state.set_state(Tutorial.android_anyconnect_step)
    await state.update_data(step=0)
    text = (
        "مرحله ۱:\n"
        "ابتدا <b>Cisco Secure Client : AnyConnect</b> را از Play Store نصب کنید:\n\n"
        "🔗 https://play.google.com/store/apps/details?id=com.cisco.anyconnect.vpn.android.avf&pcampaignid=web_share"
    )
    await smart_edit(call.message, text=text, reply_markup=kb_next_android("anyconnect"), parse_mode=ParseMode.HTML)
    await call.answer()


@router.callback_query(F.data == "android_step:anyconnect:next")
async def next_anyconnect_step(call: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    step = int(data.get("step", 0)) + 1
    await state.update_data(step=step)

    if step == 1:
        await call.message.answer_video(
            ANDROID_ANYCONNECT_VIDEO,
            caption="🔐 جهت اتصال از طریق AnyConnect اندروید از این آموزش استفاده نمایید.",
        )
        await state.clear()
    await call.answer()


# ---------------------------------------------------------------------------
# 📚 Windows L2TP steps
# ---------------------------------------------------------------------------
@router.callback_query(F.data == "windows:l2tp:start")
async def start_l2tp(call: CallbackQuery, state: FSMContext):
    await call.message.answer_video(
        WINDOWS_L2TP_VIDEO,
        caption="🔐 جهت اتصال از طریق L2TP و یا PPTP در ویندوز از این آموزش استفاده نمایید.",
    )
    await state.clear()


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


@router.callback_query(F.data == "back:android_methods")
async def back_to_ios_methods(call: CallbackQuery, state: FSMContext):
    await state.set_state(Tutorial.android_method)
    text = (
        "🏷️ <b>آموزش › اندروید</b>\n\n"
        "پیشنهاد ما <b>OpenVPN</b>\n\n"
    )
    await smart_edit(
        call.message,
        text=text,
        reply_markup=kb_android_methods(),
        parse_mode=ParseMode.HTML,
    )
    await call.answer()
