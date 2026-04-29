from aiogram import Router, F
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton

router = Router()

# سوال ↔ جواب
FAQ = {
    "چطور حسابمو شارژ کنم؟": "اگر شماره کارت‌ها را خواستی، عبارت «شماره کارت» را برای ربات بفرست. بعد از واریز هم فقط تصویر فیش را همین‌جا ارسال کن؛ با اولین عکس، ثبت تراکنش شروع می‌شود.",
    "چقدر زمان لازم هستش که فیش ارسال شده تایید بشه؟": "تایید فیش‌ها معمولا در کمتر از 30 دقیقه انجام میشه. اگر بین 12 شب تا 8 صبح ثبت بشه، معمولا تا 9 صبح تایید میشه.",
    "چطور می‌تونم سرویس VPN بخرم؟": "از منوی اصلی گزینه‌ی «خرید» رو بزن و پلن رو انتخاب کن؛ یوزرنیم و پسورد بلافاصله برات میاد.",
    "چه نوع سرویس‌هایی ارائه می‌دید؟": "OpenVPN، Cisco AnyConnect، L2TP، PPTP، SSTP و ... بسته به نیازت قابل انتخابه.",
    "سرویس برای کدوم سیستم‌عامل‌ها کار می‌کنه؟": "ویندوز، اندروید، iOS، مک و لینوکس.",
    "بعد از خرید، اطلاعات سرویس کی به من داده می‌شه؟": "بلافاصله بعد از خرید به‌صورت خودکار ارسال میشه.",
    "اگه مشکلی پیش بیاد، چجوری پشتیبانی بگیرم؟": "از بخش «پشتیبانی» یا «📬 انتقادات و پیشنهادات» استفاده کن.",
    "میتونم چند دستگاه به یه سرویس وصل کنم؟": "در اکثر پلن‌ها 1 اتصال هم‌زمان مجازه؛ سرویس‌های چندکاربره به‌زودی اضافه می‌شن.",
    "رمز عبورم را فراموش کردم، چیکار کنم؟": "از بخش «سرویس‌های من» اطلاعات مجدد برات ارسال میشه.",
    "سرویس با تلگرام و اینستا کار می‌کنه؟": "بله، برای دور زدن فیلترینگ بهینه‌سازی شدن.",
    "میتونم قبل خرید، تست بگیرم؟": "گاهی تست محدود ارائه میشه؛ از پشتیبانی درخواست بده.",
}
FAQ_ITEMS = list(FAQ.items())  # [(question, answer), ...]

def faq_list_keyboard() -> InlineKeyboardMarkup:
    rows = [[InlineKeyboardButton(text=q, callback_data=f"faq:{i}")]
            for i, (q, _) in enumerate(FAQ_ITEMS)]
    return InlineKeyboardMarkup(inline_keyboard=rows)

def answer_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="⬅️ بازگشت به سوالات", callback_data="faq:back")]
    ])

# نمایش لیست سوالات
@router.message(F.text == "❓ سوالات متداول")
async def show_faq(message: Message):
    await message.answer("لطفاً یکی از سوالات زیر را انتخاب کنید:", reply_markup=faq_list_keyboard())

# کال‌بک اینلاین
@router.callback_query(F.data.startswith("faq:"))
async def faq_callbacks(cb: CallbackQuery):
    action = cb.data.split("faq:")[1]

    if action == "back":
        await cb.message.edit_text("لطفاً یکی از سوالات زیر را انتخاب کنید:", reply_markup=faq_list_keyboard())
        await cb.answer()
        return

    # باید اندیس معتبر باشه
    try:
        idx = int(action)
        question, answer = FAQ_ITEMS[idx]
    except Exception:
        await cb.answer("❌ داده نامعتبر.", show_alert=True)
        return

    text = f"❓ {question}\n\n{answer}"
    await cb.message.edit_text(text, reply_markup=answer_keyboard())
    await cb.answer()
