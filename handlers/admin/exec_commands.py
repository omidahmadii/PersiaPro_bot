"""
Handler: site_records.py — مدیریت رکوردهای Cloudflare برای سایت‌ها
این نسخه فقط مسئول اضافه‌کردن و حذف رکوردهای Cloudflare است.
اطلاعات سایت‌ها از env خوانده می‌شود (SITES_JSON)
"""

import os
import json
import asyncio
import aiohttp
from typing import Dict
from dotenv import load_dotenv
from aiogram import Router, F
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton

from config import ADMINS, CF_ZONE_ID, CF_EMAIL, CF_API_KEY, CF_RECORD_NAME

load_dotenv()
router = Router()

# Sites mapping (name -> ip)
try:
    SITES: Dict[str, str] = json.loads(os.getenv("SITES_JSON", "{}"))
except Exception:
    SITES = {}


# --- Helpers ---
async def is_admin(user_id: int) -> bool:
    return str(user_id) in [str(a) for a in ADMINS]


async def cf_list_records(name: str) -> list:
    """Return a list of all A records for a given name."""
    url = f"https://api.cloudflare.com/client/v4/zones/{CF_ZONE_ID}/dns_records?type=A&name={name}.persiapro.com"
    headers = {"X-Auth-Email": CF_EMAIL, "X-Auth-Key": CF_API_KEY, "Content-Type": "application/json"}
    async with aiohttp.ClientSession() as session:
        async with session.get(url, headers=headers) as resp:
            j = await resp.json()
            records = j.get("result", [])
            return [r.get("content") for r in records]


async def cf_add_record(name: str, content: str) -> dict:
    url = f"https://api.cloudflare.com/client/v4/zones/{CF_ZONE_ID}/dns_records"
    headers = {
        "X-Auth-Email": CF_EMAIL,
        "X-Auth-Key": CF_API_KEY,
        "Content-Type": "application/json",
    }
    data = {"type": "A", "name": name, "content": content, "proxied": False, "ttl": 60}
    async with aiohttp.ClientSession() as session:
        async with session.post(url, headers=headers, json=data) as resp:
            return await resp.json()


async def cf_get_record_id(name: str, content: str) -> str:
    url = f"https://api.cloudflare.com/client/v4/zones/{CF_ZONE_ID}/dns_records?type=A&name={name}.persiapro.com&content={content}"
    headers = {"X-Auth-Email": CF_EMAIL, "X-Auth-Key": CF_API_KEY, "Content-Type": "application/json"}
    async with aiohttp.ClientSession() as session:
        async with session.get(url, headers=headers) as resp:
            j = await resp.json()
            try:
                return j.get("result", [])[0].get("id")
            except Exception:
                return ""


async def cf_delete_record(record_id: str) -> dict:
    url = f"https://api.cloudflare.com/client/v4/zones/{CF_ZONE_ID}/dns_records/{record_id}"
    headers = {"X-Auth-Email": CF_EMAIL, "X-Auth-Key": CF_API_KEY, "Content-Type": "application/json"}
    async with aiohttp.ClientSession() as session:
        async with session.delete(url, headers=headers) as resp:
            return await resp.json()


def parse_cf_response(action: str, result: dict, site: str, ip: str) -> str:
    if not result:
        return f"⚠️ پاسخی از Cloudflare دریافت نشد."

    if result.get("success"):
        if action == "add":
            return f"✅ رکورد {site} با آی‌پی {ip} با موفقیت اضافه شد."
        elif action == "remove":
            return f"🗑 رکورد {site} با آی‌پی {ip} با موفقیت حذف شد."
    else:
        errors = result.get("errors", [])
        if errors:
            code = errors[0].get("code")
            msg = errors[0].get("message")
            if code == 81058:
                return f"⚠️ رکورد برای سایت {site} با آی‌پی {ip} از قبل وجود دارد."
            return f"❌ خطا هنگام انجام عملیات: {msg}"
        return f"❌ عملیات {action} برای سایت {site} با خطا مواجه شد."

    return f"⚠️ پاسخ نامشخص از Cloudflare: {result}"


# --- UI ---
@router.message(F.text == "🌐 مدیریت رکوردها")
async def records_menu(msg: Message):
    if not await is_admin(msg.from_user.id):
        return await msg.reply("دسترسی نداری عزیز 😅")

    keyboard = [[InlineKeyboardButton(text="📝 مشاهده رکوردهای فعلی", callback_data="cf_list_records")]]
    for site_name, ip in SITES.items():
        add_cb = f"cf_add__{site_name}"
        del_cb = f"cf_remove__{site_name}"
        label = f"{site_name} {ip}"
        keyboard.append([
            InlineKeyboardButton(text=label + " ➕", callback_data=add_cb),
            InlineKeyboardButton(text=label + " ➖", callback_data=del_cb)
        ])
    if not keyboard:
        keyboard.append([InlineKeyboardButton(text="(هیچ سایتی تنظیم نشده)", callback_data="noop")])
    kb = InlineKeyboardMarkup(inline_keyboard=keyboard)
    await msg.answer("🌐 مدیریت رکوردهای Cloudflare — انتخاب سایت:", reply_markup=kb)


@router.callback_query(F.data.startswith("cf_add__"))
async def cf_add_handler(call: CallbackQuery):
    await call.answer()
    site = call.data.split("__", 1)[1]
    ip = SITES.get(site)
    if not ip:
        return await call.message.answer("آی‌پی این سایت تنظیم نشده است.")

    name_to_use = os.getenv("CF_RECORD_NAME", "ov")
    res = await cf_add_record(name_to_use, ip)
    parsed = parse_cf_response("add", res, site, ip)
    await call.message.edit_text(parsed)


@router.callback_query(F.data.startswith("cf_remove__"))
async def cf_remove_handler(call: CallbackQuery):
    await call.answer()
    site = call.data.split("__", 1)[1]
    ip = SITES.get(site)
    if not ip:
        return await call.message.answer("آی‌پی این سایت تنظیم نشده است.")

    name_to_use = os.getenv("CF_RECORD_NAME", "ov")
    rec_id = await cf_get_record_id(name_to_use, ip)
    if not rec_id:
        return await call.message.edit_text(f"⚠️ رکوردی با نام {name_to_use} و آی‌پی {ip} پیدا نشد.")

    res = await cf_delete_record(rec_id)
    parsed = parse_cf_response("remove", res, site, ip)
    await call.message.edit_text(parsed)


@router.callback_query(F.data == "cf_list_records")
async def cf_list_current(call: CallbackQuery):
    await call.answer()
    name_to_use = os.getenv("CF_RECORD_NAME", "ov")
    ips = await cf_list_records(name_to_use)
    if not ips:
        msg = "هیچ رکورد فعالی پیدا نشد."
    else:
        msg = "رکوردهای فعال:\n" + "\n".join(ips)
    await call.message.edit_text(msg)

@router.callback_query(F.data == "noop")
async def noop(call: CallbackQuery):
    await call.answer("هیچ عملیاتی برای انجام وجود ندارد.", show_alert=True)


__all__ = ["router"]
