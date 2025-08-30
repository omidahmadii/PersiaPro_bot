# keyboards/plan_picker.py
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from typing import List, Dict, Tuple, Optional, Union

# ---------- Normalizers ----------
def normalize_category(category: Optional[str]) -> str:
    # هر چیزی که خالی/None باشه رو standard در نظر بگیر
    c = (category or "").strip().lower()
    return c if c else "standard"

# ---------- Labels & formatters ----------
def category_label(category: Optional[str]) -> str:
    cat = normalize_category(category)
    mapping = {
        "standard": "معمولی",
        "dual": "دوکاربره",
        "fixed_ip": "آی‌پی ثابت",
        "custom_location": "لوکیشن دلخواه قابل تغییر",
    }
    return mapping.get(cat, "نامشخص")

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

# ---------- Keyboards ----------
def keyboard_categories(categories: List[str]) -> InlineKeyboardMarkup:
    # categories باید از قبل normalize شده باشند
    rows = []
    for cat in categories:
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
    rows = []
    for plan in plans:
        label = f"{plan['name']} • {format_price(plan['price'])} تومان"
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
    categories = sorted(categories_set)

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
