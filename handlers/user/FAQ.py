import asyncio

from aiogram import Router, F
from aiogram.fsm.context import FSMContext
from aiogram.types import Message, ReplyKeyboardMarkup, KeyboardButton

from keyboards.user_main_menu import user_main_menu_keyboard

router = Router()

FAQ = {
    "چطور حسابمو شارژ کنم؟": "از منوی ربات، بخش 💳 شارژ حساب رو انتخاب کن و پرداخت رو انجام بده و تصویر فیش رو ارسال کن و منتظر تایید ادمین باش.",
    "چقدر زمان لازم هستش که فیش ارسال شده تایید بشه؟": "تایید فیش های ارسال شده معمولا در کمتر از 30 دقیقه صورت میگیره. درصورتی که فیش در بازه ی زمانی 12 شب تا 8 صبح ثبت بشه تا معمولا تا 9 صبح تایید میشه.",
    "چطور می‌تونم سرویس VPN بخرم؟": "از منوی اصلی گزینه ی 'خرید سرویس' رو بزن و بعد پلن مورد نظرت رو انتخاب کن ، نام کاربری و رمز عبور برات ارسال میشه. ",
    "چه نوع سرویس‌هایی ارائه می‌دید؟": "سرویس‌ها شامل OpenVPN، Cisco AnyConnect, L2tp, Pptp, Sstp و ... هستن. بسته به نیازت می‌تونی انتخاب کنی.",
    "سرویس برای کدوم سیستم‌عامل‌ها کار می‌کنه؟": "ویندوز، اندروید، iOS، مک و لینوکس",
    "بعد از خرید، اطلاعات سرویس کی به من داده می‌شه؟": "بلافاصله بعد از خرید اطلاعات سرویس به‌صورت خودکار برات ارسال می‌شه.",
    "اگه مشکلی پیش بیاد، چجوری پشتیبانی بگیرم؟": "از بخش 'پشتیبانی' یا '📬 انتقادات و پیشنهادات' استفاده کن. پاسخ سریع می‌گیری.",
    "میتونم چند دستگاه به یه سرویس وصل کنم؟": "در اکثر پلن‌ها فقط 1 اتصال هم‌زمان مجازه. سرویس های چند کاربره در آینده اضافه خواهد شد.",
    "رمز عبورم را فراموش کردم، چیکار کنم؟": "از بخش 'سرویس‌های من' اطلاعات مجدد برای شما ارسال می‌شه.",
    "سرویس با تلگرام و اینستا کار می‌کنه؟": "بله، تمام سرویس‌ها برای دور زدن فیلترینگ بهینه‌سازی شدن.",
    "میتونم قبل خرید، تست بگیرم؟": "در برخی زمان‌ها تست محدود ارائه میشه. از طریق پشتیبانی درخواست بده.",

}


# ⌨️ کیبورد سوالات
def faq_keyboard():
    buttons = [[KeyboardButton(text=q)] for q in FAQ.keys()]
    buttons.append([KeyboardButton(text="🔙 بازگشت به منوی اصلی")])
    return ReplyKeyboardMarkup(keyboard=buttons, resize_keyboard=True)


# 📥 هندلر نمایش سوالات
@router.message(F.text == "❓ سوالات متداول")
async def show_faq(message: Message, state: FSMContext):
    await message.answer("لطفاً یکی از سوالات زیر را انتخاب کنید:", reply_markup=faq_keyboard())
    asyncio.create_task(faq_timeout(state, message.chat.id, message.bot))


# 📤 هندلر پاسخ‌دهی به انتخاب سؤال
@router.message()
async def handle_faq_selection(message: Message, state: FSMContext):
    if message.text == "🔙 بازگشت به منوی اصلی":
        await message.answer("بازگشت به منوی اصلی", reply_markup=user_main_menu_keyboard())
        return

    answer = FAQ.get(message.text)
    if answer:
        await message.answer(answer)
    else:
        await message.answer("❓ سوال نامعتبره. لطفاً از دکمه‌های منو استفاده کن.")


# ⏳ تایمر بازگشت خودکار به منو
async def faq_timeout(state: FSMContext, chat_id: int, bot):
    await asyncio.sleep(300)
    await bot.send_message(chat_id, "بازگشت به منوی اصلی", reply_markup=user_main_menu_keyboard())
