import logging
import asyncio
import aiohttp
import sqlite3
import pytz
from datetime import datetime, timedelta
from flask import Flask
from threading import Thread
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command
from aiogram.types import KeyboardButton, ReplyKeyboardMarkup
from aiogram.utils.keyboard import ReplyKeyboardBuilder
from apscheduler.schedulers.asyncio import AsyncIOScheduler

# --- SOZLAMALAR ---
TOKEN = "8579347386:AAHILzZJHV9GgYhugQklOVzhWGDpSy5LD6o"
ADMIN_ID = 5514492628
TASHKENT_TZ = pytz.timezone('Asia/Tashkent')

logging.basicConfig(level=logging.INFO)
bot = Bot(token=TOKEN)
dp = Dispatcher()
scheduler = AsyncIOScheduler(timezone=TASHKENT_TZ)

# --- VILOYATLAR ---
REGION_OFFSETS = {
    "Toshkent": 0, "Andijon": -10, "Farg'ona": -10, "Namangan": -8,
    "Guliston": 2, "Jizzax": 6, "Samarqand": 9, "Buxoro": 21,
    "Navoiy": 14, "Qarshi": 15, "Termiz": 7, "Urganch": 35, "Nukus": 38
}

PRAYER_DETAILS = {
    "Bomdod": "2 rakat sunnat, 2 rakat farz",
    "Peshin": "4 rakat sunnat, 4 rakat farz, 2 rakat sunnat",
    "Asr": "4 rakat farz",
    "Shom": "3 rakat farz, 2 rakat sunnat",
    "Xufton": "4 rakat farz, 2 rakat sunnat, 3 rakat vitr"
}

# Tezkorlik uchun xotira (Cache)
DAILY_CACHE = {}

# --- BAZA ---
def db_setup():
    with sqlite3.connect("namoz_pro.db") as conn:
        conn.execute("CREATE TABLE IF NOT EXISTS users (user_id INTEGER PRIMARY KEY, region TEXT)")
        conn.execute("CREATE TABLE IF NOT EXISTS times (date TEXT PRIMARY KEY, bomdod TEXT, quyosh TEXT, peshin TEXT, asr TEXT, shom TEXT, hufton TEXT)")

def db_query(query, params=(), fetch=False):
    with sqlite3.connect("namoz_pro.db") as conn:
        cursor = conn.execute(query, params)
        return cursor.fetchall() if fetch else conn.commit()

# --- YORDAMCHI FUNKSIYALAR ---
def adjust_time(time_str, offset_min):
    try:
        t = datetime.strptime(time_str, "%H:%M")
        return (t + timedelta(minutes=offset_min)).strftime("%H:%M")
    except: return time_str

async def update_cache():
    """Barcha viloyatlar vaqtini xotiraga yuklash (Tezlik siri)"""
    global DAILY_CACHE
    date_now = datetime.now(TASHKENT_TZ).strftime("%d.%m")
    res = db_query("SELECT * FROM times WHERE date=?", (date_now,), fetch=True)
    
    if res:
        r = res[0]
        for region, off in REGION_OFFSETS.items():
            DAILY_CACHE[region] = {
                "bomdod": adjust_time(r[1], off),
                "quyosh": adjust_time(r[2], off),
                "peshin": adjust_time(r[3], off),
                "asr": adjust_time(r[4], off),
                "shom": adjust_time(r[5], off),
                "hufton": adjust_time(r[6], off)
            }
        logging.info("Kesh yangilandi.")
    else:
        DAILY_CACHE = {}

async def get_weather(region):
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(f"https://wttr.in/{region}?format=%t+%C", timeout=3) as resp:
                return await resp.text() if resp.status == 200 else ""
    except: return ""

# --- WEB SERVER ---
app = Flask('')
@app.route('/')
def home(): return "OK"
def run_web(): app.run(host='0.0.0.0', port=8080)

# --- TUGMALAR ---
def get_main_kb():
    builder = ReplyKeyboardBuilder()
    for r in REGION_OFFSETS.keys():
        builder.add(KeyboardButton(text=r))
    builder.adjust(2)
    return builder.as_markup(resize_keyboard=True)

# --- HANDLERLAR ---

@dp.message(Command("start"))
async def cmd_start(message: types.Message):
    await message.answer("✨ <b>Assalomu alaykum!</b>\nHudud tanlang:", reply_markup=get_main_kb(), parse_mode="HTML")

@dp.message(Command("set"))
async def cmd_set(message: types.Message):
    if message.from_user.id != ADMIN_ID: return
    try:
        p = message.text.split()
        if len(p) != 8:
            await message.answer("⚠️ Format: `/set 28.02 05:30 06:50 12:40 16:15 18:25 19:45`", parse_mode="Markdown")
            return
        db_query("INSERT OR REPLACE INTO times VALUES (?, ?, ?, ?, ?, ?, ?)", (p[1], p[2], p[3], p[4], p[5], p[6], p[7]))
        await update_cache() # Keshni darhol yangilash
        await message.answer(f"✅ <b>Toshkent vaqtlari saqlandi!</b>\nBarcha hududlar keshi yangilandi.", parse_mode="HTML")
    except Exception as e: await message.answer(f"Xato: {e}")

@dp.message(Command("sent"))
async def cmd_broadcast(message: types.Message):
    if message.from_user.id != ADMIN_ID: return
    text = message.text.replace("/sent", "").strip()
    if not text:
        await message.answer("⚠️ Yuborish uchun matn yozing: `/sent Xabar`", parse_mode="Markdown")
        return
    
    users = db_query("SELECT user_id FROM users", fetch=True)
    count = 0
    for u in users:
        try:
            await bot.send_message(u[0], text)
            count += 1
            await asyncio.sleep(0.05) # Telegram bloklamasligi uchun
        except: pass
    await message.answer(f"📢 Xabar {count} ta foydalanuvchiga yuborildi.")

@dp.message(F.text.in_(REGION_OFFSETS.keys()))
async def show_times(message: types.Message):
    region = message.text
    db_query("INSERT OR REPLACE INTO users (user_id, region) VALUES (?, ?)", (message.from_user.id, region))
    
    data = DAILY_CACHE.get(region)
    if not data:
        await message.answer("⚠️ Bugun uchun vaqtlar kiritilmagan.")
        return

    weather = await get_weather(region)
    text = (f"📍 <b>Hudud: {region}</b>\n"
            f"🌡 Ob-havo: {weather}\n\n"
            f"🏙 Bomdod: <b>{data['bomdod']}</b>\n"
            f"🌅 Quyosh: <b>{data['quyosh']}</b>\n"
            f"☀️ Peshin: <b>{data['peshin']}</b>\n"
            f"🌇 Asr: <b>{data['asr']}</b>\n"
            f"🌆 Shom: <b>{data['shom']}</b>\n"
            f"🌃 Xufton: <b>{data['hufton']}</b>\n\n"
            f"📅 {datetime.now(TASHKENT_TZ).strftime('%d.%m.%Y')}")
    await message.answer(text, parse_mode="HTML")

# --- ESLATMA TIZIMI ---
async def check_reminders():
    now_str = (datetime.now(TASHKENT_TZ) + timedelta(minutes=5)).strftime("%H:%M")
    prayer_names = {"bomdod":"Bomdod", "peshin":"Peshin", "asr":"Asr", "shom":"Shom", "hufton":"Xufton"}

    for region, times in DAILY_CACHE.items():
        for key, val in times.items():
            if key in prayer_names and val == now_str:
                rakatlar = PRAYER_DETAILS.get(prayer_names[key], "")
                users = db_query("SELECT user_id FROM users WHERE region=?", (region,), fetch=True)
                for u in users:
                    try: 
                        await bot.send_message(u[0], f"🔔 <b>{prayer_names[key]}</b> vaqtiga 5 daqiqa qoldi!\n📍 {region}\n\n📖 {rakatlar}", parse_mode="HTML")
                    except: pass

async def main():
    db_setup()
    await update_cache()
    scheduler.add_job(update_cache, 'cron', hour=0, minute=1)
    scheduler.add_job(check_reminders, 'interval', minutes=1)
    scheduler.start()
    await dp.start_polling(bot)

if __name__ == '__main__':
    Thread(target=run_web).start()
    asyncio.run(main())