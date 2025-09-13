# keyboards/plan_picker.py
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from typing import List, Dict, Tuple, Optional, Union
import re

# ---------- Normalizers ----------
def normalize_category(category: Optional[str]) -> str:
    """
    هر چیزی که خالی/None باشه رو standard در نظر می‌گیریم.
    """
    c = (category or "").strip().lower()
    return c if c else "standard"


# ---------- Labels & formatters ----------
def category_label(category: Optional[str]) -> str:
    """
    لیبل دسته‌بندی‌ها با ایموجی. اگر چیزی ناشناخته بود، «نامشخص» برمی‌گرده.
    """
    cat = normalize_category(category)
    mapping = {
        "standard": "✨ معمولی",
        "dual": "👥 دوکاربره",
        "fixed_ip": "📌 آی‌پی ثابت",
        "custom_location": "📍 لوکیشن دلخواه",
        "modem": "📶 مودم/روتر",
    }
    return mapping.get(cat, "❓ نامشخص")


def location_label(location: Optional[str]) -> str:
    mapping = {
        "france": "🇫🇷 فرانسه",
        "turkey": "🇹🇷 ترکیه",
        "iran": "🇮🇷 ایران",
        "england": "🇬🇧 انگلیس",
        "global": "🌐 گلوبال",
        None: "ندارد",
        "": "ندارد",
    }
    return mapping.get(location, location or "ندارد")


def fair_usage_label(plan: Dict) -> str:
    try:
        if int(plan.get("is_unlimited") or 0) == 1:
            return "نامحدود (مصرف منصفانه)"
    except Exception:
        pass
    vol = plan.get("volume_gb")
    if vol:
        return f"{vol} گیگ"
    return "بدون آستانه مشخص"


def format_price(amount: Union[int, float]) -> str:
    try:
        return f"{int(amount):,}"
    except Exception:
        return str(amount)


def _is_active(plan: Dict) -> bool:
    val = plan.get("is_active", plan.get("active", 1))
    try:
        return int(val) == 1
    except Exception:
        return bool(val)


# ---------- Ordering preferences ----------
# ترتیب نمایش دسته‌ها با اولویت دلخواه (نه حروف الفبا)
# هر چیزی که اینجا نباشه، ته لیست میاد.
CATEGORY_PRIORITY = [
    "standard",        # 1
    "dual",            # 2
    "fixed_ip",        # 3
    "custom_location", # 4
    "modem",           # 5  ← فعلاً آخر
]


def _sort_categories(categories: List[str]) -> List[str]:
    prio = {c: i for i, c in enumerate(CATEGORY_PRIORITY)}
    return sorted(categories, key=lambda c: prio.get(c, 10_000))


# ---------- Helpers: robust 3-month detection ----------
_PERSIAN_DIGITS = str.maketrans("۰۱۲۳۴۵۶۷۸۹", "0123456789")

def _to_en_digits(s: str) -> str:
    try:
        return s.translate(_PERSIAN_DIGITS)
    except Exception:
        return s

def _safe_int(x, default: int = 0) -> int:
    try:
        return int(x)
    except Exception:
        return default

def _infer_days_from_group(group_name: Optional[str]) -> int:
    """
    اگر group_name مثل 'GL-S-97D-120G' بود، 97 رو برمی‌گردونه.
    """
    if not group_name:
        return 0
    m = re.search(r"(\d+)\s*D\b", group_name.upper())
    if m:
        return _safe_int(m.group(1), 0)
    return 0

def _infer_days_from_name(name: Optional[str]) -> int:
    """
    از name هم تلاش می‌کنیم روز/ماه رو دربیاریم:
    - الگوهای «90 روز» یا «۹۰ روز»
    - الگوی «3 ماه» یا «۳ ماه» را ~90 روز فرض می‌کنیم.
    """
    if not name:
        return 0
    s = _to_en_digits(str(name))
    #  ... روز
    m = re.search(r"(\d+)\s*روز", s)
    if m:
        return _safe_int(m.group(1), 0)
    #  ... ماه
    m = re.search(r"(\d+)\s*ماه", s)
    if m:
        months = _safe_int(m.group(1), 0)
        if months == 3:
            return 90
    return 0


# ---------- Badges (صرفاً نشانه‌گذاری بصری) ----------
def _is_three_months(plan: Dict) -> bool:
    """
    تشخیص پلن‌های حدوداً ۳ ماهه:
    - duration_months == 3
    - یا duration_days در بازهٔ مرسوم 90..97
    - یا استنتاج از group_name / name (برای فلو تمدید که ممکنه فیلدها نباشن)
    """
    try:
        d_months = _safe_int(plan.get("duration_months") or 0, 0)
        if d_months == 3:
            return True

        d_days = _safe_int(plan.get("duration_days") or 0, 0)
        if d_days in (90, 91, 92, 93, 94, 95, 96, 97):
            return True

        if d_days == 0:
            # تلاش برای استنتاج
            d_from_group = _infer_days_from_group(plan.get("group_name"))
            if d_from_group in (90, 91, 92, 93, 94, 95, 96, 97):
                return True

            d_from_name = _infer_days_from_name(plan.get("name"))
            if d_from_name in (90, 91, 92, 93, 94, 95, 96, 97):
                return True

        return False
    except Exception:
        return False


def _plan_badge(plan: Dict) -> str:
    """
    فقط بِج پیشنهادی می‌چسبونیم، ترتیب رو تغییر نمی‌دیم.
    """
    if _is_three_months(plan):
        return "⭐️"
    return ""


# ---------- Keyboards ----------
def keyboard_categories(categories: List[str]) -> InlineKeyboardMarkup:
    """
    ورودی: دسته‌ها باید از قبل normalize شده باشند.
    اینجا به‌جای مرتب‌سازی الفبایی، بر اساس اولویت داخلی سورت می‌کنیم.
    """
    ordered = _sort_categories(categories)
    rows = []
    for cat in ordered:
        rows.append([
            InlineKeyboardButton(
                text=category_label(cat),
                callback_data=f"buy|category|{cat}"  # cat اینجا normalized هست
            )
        ])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def keyboard_durations(
    plans: List[Dict],
    back_to: str = "category",
    show_back: bool = True
) -> InlineKeyboardMarkup:
    """
    ترتیب همان ترتیبی است که لیست plans دریافت می‌کند.
    فقط در لیبل، بِجِ ۳ماهه اضافه می‌شود.
    """
    rows = []
    for plan in plans:
        badge = _plan_badge(plan)
        label = f"{badge}{plan.get('name', 'بدون نام')} • {format_price(plan.get('price', 0))} تومان{badge}"
        rows.append([
            InlineKeyboardButton(
                text=label,
                callback_data=f"buy|duration|{plan['id']}"
            )
        ])
    if show_back:
        rows.append([InlineKeyboardButton(text="⬅️ بازگشت", callback_data=f"buy|back|{back_to}")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def keyboard_locations(locations: List[str], back_to: str = "category") -> InlineKeyboardMarkup:
    rows = []
    flags = {
        "france": "🇫🇷 فرانسه",
        "turkey": "🇹🇷 ترکیه",
        "iran": "🇮🇷 ایران",
        "england": "🇬🇧 انگلیس",
    }
    for loc in locations:
        label = flags.get(loc, loc)
        rows.append([InlineKeyboardButton(text=label, callback_data=f"buy|location|{loc}")])
    rows.append([InlineKeyboardButton(text="⬅️ بازگشت", callback_data=f"buy|back|{back_to}")])
    return InlineKeyboardMarkup(inline_keyboard=rows)


def keyboard_confirm() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✅ تایید و پرداخت", callback_data="buy|confirm")],
        [InlineKeyboardButton(text="⬅️ بازگشت", callback_data="buy|back|duration")]
    ])


# ---------- نقطه ورود مشترک ----------
def make_initial_buy_keyboard(all_plans: List[Dict]) -> Tuple[str, InlineKeyboardMarkup, Optional[str], List[Dict]]:
    """
    خروجی:
      kind: "categories" یا "plans"
      markup: کیبورد آماده
      only_category: اگر فقط یک دسته بود، همان نام (normalized) برای ذخیره در state
      plans_for_only_category: اگر kind == "plans" است، لیست پلن‌های همان دسته (با مقایسهٔ normalized)
    """
    active_plans = [p for p in all_plans if _is_active(p)]

    # مجموعهٔ دسته‌ها بر اساس normalized
    categories_set = {normalize_category(p.get("category")) for p in active_plans}
    categories = _sort_categories(list(categories_set))

    if len(categories) <= 1:
        only_cat = categories[0] if categories else None
        plans_for_cat = [p for p in active_plans if normalize_category(p.get("category")) == (only_cat or "standard")]
        # بدون دکمهٔ بازگشت چون کاربر مستقیماً وارد لیست پلن‌ها شده
        return "plans", keyboard_durations(plans_for_cat, back_to="category", show_back=False), only_cat, plans_for_cat

    # بیش از یک دسته
    return "categories", keyboard_categories(categories), None, []


# برای استفادهٔ بیرونی:
__all__ = [
    "normalize_category",
    "category_label",
    "location_label",
    "fair_usage_label",
    "format_price",
    "keyboard_categories",
    "keyboard_durations",
    "keyboard_locations",
    "keyboard_confirm",
    "make_initial_buy_keyboard",
]
