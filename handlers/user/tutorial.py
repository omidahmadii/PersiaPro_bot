import asyncio
from typing import Final, Set

from aiogram import Router, F
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import StatesGroup, State
from aiogram.types import FSInputFile, Message, ReplyKeyboardMarkup, KeyboardButton

from keyboards.user_main_menu import user_main_menu_keyboard

router: Final = Router()

# ---------------------------------------------------------------------------
# 📁  Static media ------------------------------------------------------------
# ---------------------------------------------------------------------------
MEDIA_DIR: Final = "media"

# Use a tiny helper so we do not repeat FSInputFile everywhere ----------------

def mfile(name: str) -> FSInputFile:
    """Return an FSInputFile from the MEDIA_DIR."""
    return FSInputFile(f"{MEDIA_DIR}/{name}")

OVPN_FILE = mfile("PersiaPro V1.ovpn")
OVPN_IMAGES = [mfile(f"ovpn_img0{i}.jpg") for i in range(1, 5)]
L2TP_IMAGES = [mfile(f"l2tp_img0{i}.jpg") for i in range(1, 3)]

# ---------------------------------------------------------------------------
# 🗂  States ------------------------------------------------------------------
# ---------------------------------------------------------------------------
class Tutorial(StatesGroup):
    menu = State()
    ios_method = State()
    ios_l2tp_step = State()
    ios_ovpn_step = State()


# ---------------------------------------------------------------------------
# ⌨️  Keyboards ---------------------------------------------------------------
# ---------------------------------------------------------------------------
main_menu_kb = ReplyKeyboardMarkup(
    keyboard=[
        [KeyboardButton(text="📱 اندروید"), KeyboardButton(text="📱 آیفون")],
        [KeyboardButton(text="💻 ویندوز"), KeyboardButton(text="🖥 مک")],
        [KeyboardButton(text="🐧 لینوکس"), KeyboardButton(text="📺 Smart TV")],
        [KeyboardButton(text="🎮 کنسول بازی")],
        # [KeyboardButton(text="🌐 مرورگر (افزونه)"), KeyboardButton(text="🎮 کنسول بازی")],
        [KeyboardButton(text="🔙 بازگشت به منوی اصلی")],
    ],
    resize_keyboard=True,
)

ios_method_kb = ReplyKeyboardMarkup(
    keyboard=[
        [KeyboardButton(text="🔸 آموزش L2TP"), KeyboardButton(text="🔸 آموزش OpenVPN")],
        [KeyboardButton(text="🔙 بازگشت به آموزش‌ اتصال")],
    ],
    resize_keyboard=True,
)

next_step_kb = ReplyKeyboardMarkup(
    keyboard=[
        [KeyboardButton(text="➡️ مرحله بعد")],
        [KeyboardButton(text="🔙 بازگشت به انتخاب روش آیفون")],
    ],
    resize_keyboard=True,
)

# ---------------------------------------------------------------------------
# 🔔  Timeout helper ----------------------------------------------------------
# ---------------------------------------------------------------------------
TIMEOUT_SECONDS: Final = 600  # 10 minutes

async def _tutorial_timeout(chat_id: int, state: FSMContext, bot_send):
    """Send timeout message after TIMEOUT_SECONDS if user still in tutorial."""
    await asyncio.sleep(TIMEOUT_SECONDS)
    if (await state.get_state()) in {
        Tutorial.menu.state,
        Tutorial.ios_method.state,
        Tutorial.ios_l2tp_step.state,
        Tutorial.ios_ovpn_step.state,
    }:
        await bot_send(
            chat_id,
            "⏳ زمان مشاهده بخش آموزش به پایان رسید. بازگشت به منوی اصلی.",
            reply_markup=user_main_menu_keyboard(),
        )
        await state.clear()

# ---------------------------------------------------------------------------
# 🚀  Handlers ----------------------------------------------------------------
# ---------------------------------------------------------------------------
@router.message(F.text == "📚 آموزش")
async def start_tutorial(message: Message, state: FSMContext):
    """Entry point for tutorial menu."""
    await message.answer("لطفاً دستگاه مورد نظر را انتخاب کنید:", reply_markup=main_menu_kb)
    await state.set_state(Tutorial.menu)

    # Fire‑and‑forget timeout – no blocking of the handler! -------------------
    asyncio.create_task(_tutorial_timeout(message.chat.id, state, message.bot.send_message))


# -------------------- iOS root menu -----------------------------------------
@router.message(F.text == "📱 آیفون")
async def ios_methods(message: Message, state: FSMContext):
    text = (
        "👋 خوش اومدی به بخش آموزش اتصال.\n\n"
        "🔻 اگه اپلیکیشن OpenVPN رو نصب داری یا می‌تونی از App Store نصبش کنی، اون رو انتخاب کن (پیشنهاد ما).\n\n"
        "🔹 اگر هیچ دسترسی نداری، ابتدا از روش L2TP استفاده کن. بعداً وقتی تونستی، حتماً به OpenVPN سوییچ کن چون:\n\n"
        "👇 لطفاً یکی از گزینه‌های زیر رو انتخاب کن:"
    )
    await message.answer(text, reply_markup=ios_method_kb)
    await state.set_state(Tutorial.ios_method)


# -------------------- Android placeholder -----------------------------------
@router.message(F.text == "📱 اندروید")
async def android_placeholder(message: Message, state: FSMContext):
    await state.clear()
    await message.answer(
        "⛏ این بخش در حال توسعه است. به‌زودی فعال خواهد شد!",
        reply_markup=user_main_menu_keyboard(),
    )

@router.message(F.text == "💻 ویندوز")
async def android_placeholder(message: Message, state: FSMContext):
    await state.clear()
    await message.answer(
        "⛏ این بخش در حال توسعه است. به‌زودی فعال خواهد شد!",
        reply_markup=user_main_menu_keyboard(),
    )


@router.message(F.text == "🖥 مک")
async def android_placeholder(message: Message, state: FSMContext):
    await state.clear()
    await message.answer(
        "⛏ این بخش در حال توسعه است. به‌زودی فعال خواهد شد!",
        reply_markup=user_main_menu_keyboard(),
    )


@router.message(F.text == "🐧 لینوکس")
async def android_placeholder(message: Message, state: FSMContext):
    await state.clear()
    await message.answer(
        "⛏ این بخش در حال توسعه است. به‌زودی فعال خواهد شد!",
        reply_markup=user_main_menu_keyboard(),
    )


@router.message(F.text == "📺 Smart TV")
async def android_placeholder(message: Message, state: FSMContext):
    await state.clear()
    await message.answer(
        "⛏ این بخش در حال توسعه است. به‌زودی فعال خواهد شد!",
        reply_markup=user_main_menu_keyboard(),
    )

@router.message(F.text == "🎮 کنسول بازی")
async def android_placeholder(message: Message, state: FSMContext):
    await state.clear()
    await message.answer(
        "⛏ این بخش در حال توسعه است. به‌زودی فعال خواهد شد!",
        reply_markup=user_main_menu_keyboard(),
    )


# ---------------------------------------------------------------------------
# 📚  L2TP steps --------------------------------------------------------------
# ---------------------------------------------------------------------------
@router.message(F.text == "🔸 آموزش L2TP")
async def start_l2tp(message: Message, state: FSMContext):
    await state.update_data(step=0)
    await message.answer(
        "وارد قسمت Settings گوشی شده ...",
        reply_markup=next_step_kb,
    )
    await state.set_state(Tutorial.ios_l2tp_step)


@router.message(Tutorial.ios_l2tp_step, F.text == "➡️ مرحله بعد")
async def next_l2tp_step(message: Message, state: FSMContext):
    data = await state.get_data()
    step = data.get("step", 0) + 1
    await state.update_data(step=step)

    if step == 1:
        await message.answer_photo(
            photo=L2TP_IMAGES[0],
            caption="📸 ...",
            reply_markup=next_step_kb,
        )
    elif step == 2:
        await state.clear()
        await message.answer_photo(
            photo=L2TP_IMAGES[1],
            caption="📸 ...",
            reply_markup=user_main_menu_keyboard(),
        )


# ---------------------------------------------------------------------------
# 📚  OpenVPN steps -----------------------------------------------------------
# ---------------------------------------------------------------------------
@router.message(F.text == "🔸 آموزش OpenVPN")
async def start_ovpn(message: Message, state: FSMContext):
    await state.set_state(Tutorial.ios_ovpn_step)
    await state.update_data(step=0)
    await message.answer(
        "مرحله ۱:\nاپلیکیشن OpenVPN Connect را از App Store نصب کنید:\n"
        "🔗 https://apps.apple.com/us/app/openvpn-connect/id590379981",
        reply_markup=next_step_kb,
    )


@router.message(Tutorial.ios_ovpn_step, F.text == "➡️ مرحله بعد")
async def next_ovpn_step(message: Message, state: FSMContext):
    data = await state.get_data()
    step = data.get("step", 0) + 1
    await state.update_data(step=step)

    if step == 1:
        await message.answer_document(OVPN_FILE, caption="🔐 فایل تنظیمات ...")
        await message.answer_photo(
            photo=OVPN_IMAGES[0],
            caption="📸 ...",
            reply_markup=next_step_kb,
        )
    elif step == 2:
        await message.answer_photo(OVPN_IMAGES[1], caption="📸 ...", reply_markup=next_step_kb)
    elif step == 3:
        await message.answer_photo(OVPN_IMAGES[2], caption="📸 ...", reply_markup=next_step_kb)
    elif step == 4:
        await state.clear()
        await message.answer_photo(
            OVPN_IMAGES[3],
            caption="📸 ...",
            reply_markup=next_step_kb,
        )
        await message.answer_document(
            OVPN_FILE,
            caption="🔐 فایل تنظیمات OpenVPN ...",
            reply_markup=user_main_menu_keyboard(),
        )


# ---------------------------------------------------------------------------
# 🔙  Back buttons ------------------------------------------------------------
# ---------------------------------------------------------------------------
@router.message(F.text == "🔙 بازگشت به انتخاب روش آیفون")
async def back_to_select_methods(message: Message, state: FSMContext):
    await message.answer("روش اتصال را انتخاب کنید:", reply_markup=ios_method_kb)
    await state.set_state(Tutorial.ios_method)


@router.message(F.text == "🔙 بازگشت به آموزش‌ اتصال")
async def back_to_ios_methods(message: Message, state: FSMContext):
    await message.answer("لطفاً دستگاه مورد نظر را انتخاب کنید:", reply_markup=main_menu_kb)
    await state.set_state(Tutorial.menu)


@router.message(F.text == "🔙 بازگشت به منوی اصلی")
async def back_to_main(message: Message, state: FSMContext):
    await state.clear()
    await message.answer("بازگشت به منوی اصلی", reply_markup=user_main_menu_keyboard())


