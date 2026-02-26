import logging
import asyncio
import aiohttp
import sqlite3
import pytz
from datetime import datetime, timedelta
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

# Islomapi.uz uchun hududlar ro'yxati
REGIONS = [
    "Toshkent", "Andijon", "Buxoro", "Guliston", "Jizzax", "Zarafshon",
    "Qarshi", "Navoiy", "Namangan", "Nukus", "Samarqand", "Termiz",
    "Urganch", "Farg'ona", "Xiva"
]

PRAYER_CACHE = {}

# --- BAZA BILAN ISHLASH ---
def init_db():
    with sqlite3.connect("bot_users.db") as conn:
        conn.execute("CREATE TABLE IF NOT EXISTS users (user_id INTEGER PRIMARY KEY, region TEXT)")
        conn.commit()

def db_query(query, params=(), fetch=False):
    with sqlite3.connect("bot_users.db") as conn:
        cursor = conn.execute(query, params)
        if fetch: return cursor.fetchall()
        conn.commit()

# --- API ORQALI VAQTLARNI OLISH ---
async def fetch_prayer_times(region):
    url = f"https://islomapi.uz/api/present/day?region={region}"
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(url, timeout=10) as response:
                if response.status == 200:
                    data = await response.json()
                    return data['times']
    except Exception as e:
        logging.error(f"API Error ({region}): {e}")
    return None

async def update_all_cache():
    for region in REGIONS:
        data = await fetch_prayer_times(region)
        if data:
            PRAYER_CACHE[region] = data
        await asyncio.sleep(0.5)

# --- KLAVIATURA ---
def get_main_keyboard():
    builder = ReplyKeyboardBuilder()
    for r in REGIONS:
        builder.add(KeyboardButton(text=r))
    builder.adjust(2)
    return builder.as_markup(resize_keyboard=True)

# --- HANDLERLAR ---

@dp.message(Command("start"))
async def cmd_start(message: types.Message):
    db_query("INSERT OR IGNORE INTO users (user_id, region) VALUES (?, ?)", (message.from_user.id, "Toshkent"))
    await message.answer(
        f"✨ <b>Assalomu alaykum {message.from_user.full_name}!</b>\n\n"
        "Namoz vaqtlari botiga xush kelibsiz. Hududni tanlang:",
        reply_markup=get_main_keyboard(),
        parse_mode="HTML"
    )

# Admin uchun statistika
@dp.message(Command("stat"), F.from_user.id == ADMIN_ID)
async def cmd_stat(message: types.Message):
    users = db_query("SELECT COUNT(*) FROM users", fetch=True)
    await message.answer(f"👥 Foydalanuvchilar soni: {users[0][0]} ta")

# Admin uchun reklama tarqatish: /send [xabar]
@dp.message(Command("send"), F.from_user.id == ADMIN_ID)
async def cmd_send(message: types.Message):
    if not message.reply_to_message:
        await message.answer("Biron bir xabarga reply qilib /send deb yozing!")
        return
    
    users = db_query("SELECT user_id FROM users", fetch=True)
    count = 0
    for user in users:
        try:
            await bot.copy_message(chat_id=user[0], from_chat_id=message.chat.id, message_id=message.reply_to_message.message_id)
            count += 1
            await asyncio.sleep(0.05) # Spamdan himoya
        except:
            pass
    await message.answer(f"✅ Xabar {count} ta foydalanuvchiga yuborildi.")

@dp.message(F.text.in_(REGIONS))
async def set_region(message: types.Message):
    region = message.text
    db_query("INSERT OR REPLACE INTO users (user_id, region) VALUES (?, ?)", (message.from_user.id, region))
    
    times = await fetch_prayer_times(region)
    if times:
        text = (f"📍 <b>{region}</b> (Bugun)\n\n"
                f"🏙 Bomdod: {times['tong_saharlik']}\n"
                f"🌅 Quyosh: {times['quyosh']}\n"
                f"☀️ Peshin: {times['peshin']}\n"
                f"🌇 Asr: {times['asr']}\n"
                f"🌆 Shom (Iftor): {times['shom_iftor']}\n"
                f"🌃 Xufton: {times['hufton']}")
        await message.answer(text, parse_mode="HTML")

# --- ESLATMA (REMINDER) ---
async def check_reminders():
    # 5 daqiqa qolganini tekshirish
    now_plus_5 = (datetime.now(TASHKENT_TZ) + timedelta(minutes=5)).strftime("%H:%M")
    names = {"tong_saharlik":"Bomdod", "peshin":"Peshin", "asr":"Asr", "shom_iftor":"Shom", "hufton":"Xufton"}
    
    # Keshda ma'lumot bo'lmasa, yangilab olamiz
    if not PRAYER_CACHE:
        await update_all_cache()

    for reg, times in PRAYER_CACHE.items():
        for key, t in times.items():
            if key in names and t == now_plus_5:
                users = db_query("SELECT user_id FROM users WHERE region=?", (reg,), fetch=True)
                for u in users:
                    try:
                        await bot.send_message(u[0], f"🔔 <b>{names[key]}</b> namoziga 5 daqiqa qoldi! ({reg})", parse_mode="HTML")
                    except:
                        pass

async def main():
    init_db()
    await update_all_cache()
    
    # Har kuni tunda keshni yangilash
    scheduler.add_job(update_all_cache, 'cron', hour=0, minute=1)
    # Har daqiqada vaqtni tekshirish
    scheduler.add_job(check_reminders, 'interval', minutes=1)
    
    scheduler.start()
    await dp.start_polling(bot)

if __name__ == '__main__':
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        logging.info("Bot to'xtatildi")