from services.IBSng import get_user_radius_attribute, apply_user_radius_attrs
from services.db import get_orders_usage_for_limitation, save_applied_speed_to_db

# حجم‌ها بر حسب MB (گیگ × 1024)
SPEED_THRESHOLDS = [
    (20480, '8m'),
    (30720, '4m'),
    (40960, '2m'),
    (51200, '1m'),
    (61440, '512k'),
    (71680, '256k'),
]


def determine_speed(total_mb: int, duration_months: int):
    for threshold, speed in reversed(SPEED_THRESHOLDS):
        if total_mb >= threshold * duration_months:
            return speed
    return None


def get_rate_limit(speed):
    rate_limit = {
        '8m': "Rate-Limit=\"8m/8m\"",
        '6m': "Rate-Limit=\"6m/6m\"",
        '4m': "Rate-Limit=\"4m/4m\"",
        '2m': "Rate-Limit=\"2m/2m\"",
        '1m': "Rate-Limit=\"1m/1m\"",
        '512k': "Rate-Limit=\"512k/512k\"",
        '256k': "Rate-Limit=\"256k/256k\"",
    }
    return rate_limit[speed]


async def limit_speed():
    rows = get_orders_usage_for_limitation()
    print(len(rows))
    for row in rows:
        usage_id, order_id, username, total_mb, applied_speed, is_unlimited, duration_months = row

        if not is_unlimited:
            continue  # رد کن اگه حجمیه

        new_speed = determine_speed(total_mb, duration_months)
        if not new_speed:
            continue  # هنوز به حدی نرسیده که نیاز به محدودیت باشه

        if applied_speed == new_speed:
            continue  # از قبل محدود شده به همین سرعت

        # دریافت اتربیوت فعلی از IBS
        radius_attr = get_user_radius_attribute(username)

        if not radius_attr:
            # هیچ اتربیوتی نداره → فقط سرعت جدید رو ست کن
            radius_attrs = get_rate_limit(new_speed)
            apply_user_radius_attrs(username, radius_attrs)
        else:
            group = radius_attr.get("Group")
            if group:
                rate_limit = get_rate_limit(speed=new_speed)
                radius_attrs = f"Group=\"{group}\"" + "\n" + rate_limit
                # باید گروه رو هم با سرعت جدید ست کنیم
                apply_user_radius_attrs(username, radius_attrs)
            else:
                radius_attrs = get_rate_limit(speed=new_speed)
                # گروه نداره → فقط سرعت رو ست کن
                apply_user_radius_attrs(username, radius_attrs)

        # حالا دوباره اتربیوت جدید رو بخون و در دیتابیس ذخیره کن
        updated_attr = get_user_radius_attribute(username)
        if updated_attr:
            actual_rate_limit = updated_attr.get("Rate-Limit").split("/")[0]
            save_applied_speed_to_db(order_id=order_id,
                                     applied_speed=actual_rate_limit)  # باید این تابع رو خودت ساخته باشی
        else:
            print(f"[!] Failed to fetch updated attributes for {username}")
