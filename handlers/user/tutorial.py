# handlers/user/tutorial.py

from typing import Final, Optional
from aiogram import Router, F
from aiogram.enums import ParseMode
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
# 📁 Static Media (LOCAL FILES)
# ---------------------------------------------------------------------------
MEDIA_DIR: Final = "media"


def vfile(name: str) -> FSInputFile:
    return FSInputFile(f"{MEDIA_DIR}/{name}.mp4")


def dfile(name: str) -> FSInputFile:
    return FSInputFile(f"{MEDIA_DIR}/{name}")


ANDROID_ANYCONNECT_VIDEO = vfile("android_anycoonect")
ANDROID_OVPN_VIDEO = vfile("android_ovpn")

IOS_L2TP_VIDEO = vfile("iphone_l2tp")
IOS_OVPN_VIDEO = vfile("iphone_ovpn")
IOS_ANYCONNECT_VIDEO = vfile("iphone_anyconnect")

WINDOWS_L2TP_VIDEO = vfile("windows_l2tp")

OVPN_GLOBAL_FILE = dfile("gl.persiapro.com.ovpn")
OVPN_SWITCH_FILE = dfile("sw.persiapro.com.ovpn")


# ---------------------------------------------------------------------------
# 🗂 States
# ---------------------------------------------------------------------------
class Tutorial(StatesGroup):
    menu = State()
    file_menu = State()
    ios_method = State()
    android_method = State()
    windows_method = State()

    ios_ovpn_step = State()
    ios_anyconnect_step = State()

    android_ovpn_step = State()
    android_anyconnect_step = State()


# ---------------------------------------------------------------------------
# 🛡 smart_edit helper
# ---------------------------------------------------------------------------
async def smart_edit(
        message: Message,
        *,
        text: Optional[str],
        reply_markup: Optional[InlineKeyboardMarkup] = None,
):
    try:
        if message.text:
            return await message.edit_text(
                text, reply_markup=reply_markup, parse_mode=ParseMode.HTML
            )
        if message.caption:
            return await message.edit_caption(
                caption=text, reply_markup=reply_markup, parse_mode=ParseMode.HTML
            )
        return await message.answer(
            text, reply_markup=reply_markup, parse_mode=ParseMode.HTML
        )
    except TelegramBadRequest as e:
        if "message is not modified" in str(e):
            return
        raise


# ---------------------------------------------------------------------------
# ⌨️ Keyboards
# ---------------------------------------------------------------------------
def kb_root():
    kb = InlineKeyboardBuilder()
    kb.button(text="📱 اندروید", callback_data="dev:android")
    kb.button(text="📱 آیفون", callback_data="dev:ios")
    kb.button(text="💻 ویندوز", callback_data="dev:windows")
    kb.button(text="📥 دریافت فایل OpenVPN", callback_data="ovpn:files")
    kb.adjust(2, 1, 1)
    return kb.as_markup()


def kb_ios_methods():
    kb = InlineKeyboardBuilder()
    kb.button(text="🔸 OpenVPN", callback_data="ios:ovpn:start")
    kb.button(text="🔸 L2TP", callback_data="ios:l2tp:start")
    kb.button(text="⬅️ بازگشت", callback_data="back:root")
    kb.adjust(2, 1)
    return kb.as_markup()


def kb_android_methods():
    kb = InlineKeyboardBuilder()
    kb.button(text="🔸 OpenVPN", callback_data="android:ovpn:start")
    kb.button(text="🔸 AnyConnect", callback_data="android:anyconnect:start")
    kb.button(text="⬅️ بازگشت", callback_data="back:root")
    kb.adjust(2, 1)
    return kb.as_markup()


def kb_windows_methods():
    kb = InlineKeyboardBuilder()
    kb.button(text="🔸 L2TP", callback_data="windows:l2tp:start")
    kb.button(text="⬅️ بازگشت", callback_data="back:root")
    kb.adjust(1, 1)
    return kb.as_markup()


def kb_ovpn_files():
    kb = InlineKeyboardBuilder()
    kb.button(text="✨ معمولی", callback_data="ovpn:standard")
    kb.button(text="📌 آی‌پی ثابت", callback_data="ovpn:static")
    kb.button(text="⬅️ بازگشت", callback_data="back:root")
    kb.adjust(1)
    return kb.as_markup()


def kb_next(prefix: str):
    kb = InlineKeyboardBuilder()
    kb.button(text="➡️ مرحله بعد", callback_data=f"{prefix}:next")
    return kb.as_markup()


# ---------------------------------------------------------------------------
# 🚀 Entry
# ---------------------------------------------------------------------------
@router.message(F.text == "📚 آموزش")
async def start_tutorial(message: Message, state: FSMContext):
    await state.set_state(Tutorial.menu)
    await message.answer(
        "🏷️ <b>آموزش</b>\nدستگاه مورد نظر را انتخاب کنید:",
        reply_markup=kb_root(),
        parse_mode=ParseMode.HTML,
    )


# ---------------------------------------------------------------------------
# 📱 iOS
# ---------------------------------------------------------------------------
@router.callback_query(F.data == "dev:ios")
async def ios_menu(call: CallbackQuery, state: FSMContext):
    await state.set_state(Tutorial.ios_method)
    await smart_edit(
        call.message,
        text="🏷️ <b>آموزش › آیفون</b>",
        reply_markup=kb_ios_methods(),
    )
    await call.answer()


@router.callback_query(F.data == "ios:l2tp:start")
async def ios_l2tp(call: CallbackQuery, state: FSMContext):
    await call.message.answer_video(
        IOS_L2TP_VIDEO,
        caption="🔐 آموزش اتصال L2TP در آیفون",
    )
    await state.clear()
    await call.answer()


@router.callback_query(F.data == "ios:ovpn:start")
async def ios_ovpn(call: CallbackQuery, state: FSMContext):
    await state.set_state(Tutorial.ios_ovpn_step)
    await state.update_data(step=1)
    await call.message.answer_video(
        IOS_OVPN_VIDEO,
        caption="🔐 آموزش OpenVPN در آیفون",
    )
    await call.message.answer_document(
        OVPN_GLOBAL_FILE,
        caption="📄 فایل تنظیمات OpenVPN",
    )
    await state.clear()
    await call.answer()


@router.callback_query(F.data == "ios:anyconnect:start")
async def ios_anyconnect(call: CallbackQuery, state: FSMContext):
    await call.message.answer_video(
        IOS_ANYCONNECT_VIDEO,
        caption="🔐 آموزش AnyConnect در آیفون",
    )
    await state.clear()
    await call.answer()


# ---------------------------------------------------------------------------
# 📱 Android
# ---------------------------------------------------------------------------
@router.callback_query(F.data == "dev:android")
async def android_menu(call: CallbackQuery, state: FSMContext):
    await state.set_state(Tutorial.android_method)
    await smart_edit(
        call.message,
        text="🏷️ <b>آموزش › اندروید</b>",
        reply_markup=kb_android_methods(),
    )
    await call.answer()


@router.callback_query(F.data == "android:ovpn:start")
async def android_ovpn(call: CallbackQuery, state: FSMContext):
    await call.message.answer_video(
        ANDROID_OVPN_VIDEO,
        caption="🔐 آموزش OpenVPN در اندروید",
    )
    await call.message.answer_document(
        OVPN_GLOBAL_FILE,
        caption="📄 فایل تنظیمات OpenVPN",
    )
    await state.clear()
    await call.answer()


@router.callback_query(F.data == "android:anyconnect:start")
async def android_anyconnect(call: CallbackQuery, state: FSMContext):
    await call.message.answer_video(
        ANDROID_ANYCONNECT_VIDEO,
        caption="🔐 آموزش AnyConnect در اندروید",
    )
    await state.clear()
    await call.answer()


# ---------------------------------------------------------------------------
# 💻 Windows
# ---------------------------------------------------------------------------

@router.callback_query(F.data == "dev:windows")
async def windows_menu(call: CallbackQuery, state: FSMContext):
    await state.set_state(Tutorial.windows_method)
    await smart_edit(
        call.message,
        text="🏷️ <b>آموزش › ویندوز</b>",
        reply_markup=kb_windows_methods(),
    )
    await call.answer()


@router.callback_query(F.data == "windows:l2tp:start")
async def windows_l2tp(call: CallbackQuery, state: FSMContext):
    await call.message.answer_video(
        WINDOWS_L2TP_VIDEO,
        caption="🔐 آموزش L2TP در ویندوز",
    )
    await state.clear()
    await call.answer()


# ---------------------------------------------------------------------------
# 💻 OpenVPN Files
# ---------------------------------------------------------------------------

@router.callback_query(F.data == "ovpn:files")
async def ovpn_files_menu(call: CallbackQuery, state: FSMContext):
    await state.set_state(Tutorial.file_menu)
    await smart_edit(
        call.message,
        text="📥 <b>دریافت فایل OpenVPN</b>\nنوع سرویس را انتخاب کنید:",
        reply_markup=kb_ovpn_files(),
    )
    await call.answer()


@router.callback_query(F.data == "ovpn:standard")
async def ovpn_standard(call: CallbackQuery):
    await call.message.answer_document(
        OVPN_GLOBAL_FILE,
        caption="📄 فایل OpenVPN سرویس معمولی",
    )
    await call.answer()


@router.callback_query(F.data == "ovpn:static")
async def ovpn_static(call: CallbackQuery):
    await call.message.answer_document(
        OVPN_SWITCH_FILE,
        caption="📄 فایل OpenVPN آی‌پی ثابت",
    )
    await call.answer()


# ---------------------------------------------------------------------------
# 🔙 Back
# ---------------------------------------------------------------------------
@router.callback_query(F.data == "back:root")
async def back_root(call: CallbackQuery, state: FSMContext):
    await state.set_state(Tutorial.menu)
    await smart_edit(
        call.message,
        text="🏷️ <b>آموزش</b>\nدستگاه مورد نظر را انتخاب کنید:",
        reply_markup=kb_root(),
    )
    await call.answer()
