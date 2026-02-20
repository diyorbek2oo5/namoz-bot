import os
import logging
import asyncio
import aiohttp
import sqlite3
import pytz
from datetime import datetime, timedelta
from bs4 import BeautifulSoup
from flask import Flask
from threading import Thread
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command
from aiogram.types import KeyboardButton
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

# Islom.uz ID raqamlari
REGION_IDS = {
    "Toshkent": 27, "Andijon": 1, "Buxoro": 4, "Guliston": 5,
    "Jizzax": 9, "Zarafshon": 10, "Qarshi": 11, "Navoiy": 16,
    "Namangan": 15, "Nukus": 18, "Samarqand": 21, "Termiz": 25,
    "Urganch": 28, "Farg'ona": 32
}

PRAYER_CACHE = {}

# --- WEB SERVER (Render uchun) ---
app = Flask('')

@app.route('/')
def home():
    return "Bot is running!"

def run_web():
    app.run(host='0.0.0.0', port=8080)

# --- BAZA ---
def db_query(query, params=(), fetch=False):
    with sqlite3.connect("bot_users.db") as conn:
        cursor = conn.execute(query, params)
        if fetch: return cursor.fetchall()
        conn.commit()

# --- SCRAPING (islom.uz) ---
async def fetch_prayer_times(region_name):
    region_id = REGION_IDS.get(region_name)
    url = f"https://islom.uz/vaqtlar?region={region_id}"
    headers = {'User-Agent': 'Mozilla/5.0'}
    try:
        async with aiohttp.ClientSession(headers=headers) as session:
            async with session.get(url, timeout=15) as response:
                if response.status == 200:
                    html = await response.text()
                    soup = BeautifulSoup(html, 'html.parser')
                    times_tags = soup.find_all('div', class_='p_v_t')
                    if len(times_tags) >= 6:
                        return {
                            "tong_saharlik": times_tags[0].text.strip(),
                            "quyosh": times_tags[1].text.strip(),
                            "peshin": times_tags[2].text.strip(),
                            "asr": times_tags[3].text.strip(),
                            "shom_iftor": times_tags[4].text.strip(),
                            "hufton": times_tags[5].text.strip()
                        }
    except Exception as e:
        logging.error(f"Error {region_name}: {e}")
    return None

async def update_all_cache():
    for region in REGION_IDS.keys():
        data = await fetch_prayer_times(region)
        if data: PRAYER_CACHE[region] = data
        await asyncio.sleep(1)

# --- HANDLERLAR ---
def get_main_keyboard():
    builder = ReplyKeyboardBuilder()
    for r in REGION_IDS.keys():
        builder.add(KeyboardButton(text=r))
    builder.adjust(2)
    return builder.as_markup(resize_keyboard=True)

@dp.message(Command("start"))
async def cmd_start(message: types.Message):
    db_query("INSERT OR IGNORE INTO users (user_id, region) VALUES (?, ?)", (message.from_user.id, "Toshkent"))
    await message.answer("✨ <b>Assalomu alaykum!</b>\nHududni tanlang:", reply_markup=get_main_keyboard(), parse_mode="HTML")

@dp.message(F.text.in_(REGION_IDS.keys()))
async def set_region(message: types.Message):
    region = message.text
    db_query("INSERT OR REPLACE INTO users (user_id, region) VALUES (?, ?)", (message.from_user.id, region))
    times = PRAYER_CACHE.get(region) or await fetch_prayer_times(region)
    if times:
        PRAYER_CACHE[region] = times
        text = f"📍 <b>{region}</b>\n\n🏙 Bomdod: {times['tong_saharlik']}\n🌅 Quyosh: {times['quyosh']}\n☀️ Peshin: {times['peshin']}\n🌇 Asr: {times['asr']}\n🌆 Shom: {times['shom_iftor']}\n🌃 Xufton: {times['hufton']}"
        await message.answer(text, parse_mode="HTML")

# --- REMINDER ---
async def check_reminders():
    now = datetime.now(TASHKENT_TZ).strftime("%H:%M")
    remind_at = (datetime.now(TASHKENT_TZ) + timedelta(minutes=5)).strftime("%H:%M")
    names = {"tong_saharlik":"Bomdod", "peshin":"Peshin", "asr":"Asr", "shom_iftor":"Shom", "hufton":"Xufton"}
    
    for reg, times in PRAYER_CACHE.items():
        for key, t in times.items():
            if key in names and t == remind_at:
                users = db_query("SELECT user_id FROM users WHERE region=?", (reg,), fetch=True)
                for u in users:
                    try: await bot.send_message(u[0], f"🔔 {names[key]}ga 5 daqiqa qoldi ({reg})")
                    except: pass

async def main():
    db_query("CREATE TABLE IF NOT EXISTS users (user_id INTEGER PRIMARY KEY, region TEXT)")
    asyncio.create_task(update_all_cache())
    scheduler.add_job(update_all_cache, 'cron', hour=0, minute=1)
    scheduler.add_job(check_reminders, 'interval', minutes=1)
    scheduler.start()
    await dp.start_polling(bot)

if __name__ == '__main__':
    Thread(target=run_web).start() # Web serverni alohida oqimda ishga tushirish
    asyncio.run(main())