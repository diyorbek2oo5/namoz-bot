import logging
import asyncio
import sqlite3
import pytz
import os
from io import BytesIO
from datetime import datetime, timedelta
from PIL import Image, ImageDraw, ImageFont
from aiogram import Bot, Dispatcher, types, F
from aiogram.filters import Command
from aiogram.types import KeyboardButton, BufferedInputFile
from aiogram.utils.keyboard import ReplyKeyboardBuilder

# --- SOZLAMALAR ---
TOKEN = "8579347386:AAHILzZJHV9GgYhugQklOVzhWGDpSy5LD6o"
ADMIN_ID = 5514492628
TASHKENT_TZ = pytz.timezone('Asia/Tashkent')

logging.basicConfig(level=logging.INFO)

# Viloyat farqlari
REGION_OFFSETS = {
    "Toshkent": 0, "Andijon": -10, "Farg'ona": -10, "Namangan": -8,
    "Guliston": 2, "Jizzax": 6, "Samarqand": 9, "Buxoro": 21,
    "Navoiy": 14, "Qarshi": 15, "Termiz": 7, "Urganch": 35, "Nukus": 38
}

# --- BAZA ---
def db_query(query, params=(), fetch=False):
    with sqlite3.connect("namoz_photo.db") as conn:
        cursor = conn.execute(query, params)
        return cursor.fetchall() if fetch else conn.commit()

def db_setup():
    db_query("CREATE TABLE IF NOT EXISTS users (user_id INTEGER PRIMARY KEY, region TEXT)")
    db_query("CREATE TABLE IF NOT EXISTS times (date TEXT PRIMARY KEY, b TEXT, p TEXT, a TEXT, s TEXT, h TEXT)")

# --- RASMGA YOZISH FUNKSIYASI ---
def create_prayer_image(region, date_str, times):
    try:
        img = Image.open("shablon.jpg")
        draw = ImageDraw.Draw(img)
        
        # Windowsda shrift yo'li (agar xato bersa buni o'zgartirish kerak)
        try:
            # Kompyuteringizda arial shrifti bo'lsa:
            font_path = "arial.ttf" 
            font_title = ImageFont.truetype(font_path, 65) # Viloyat uchun
            font_date = ImageFont.truetype(font_path, 35)  # Sana uchun
            font_time = ImageFont.truetype(font_path, 55)  # Vaqtlar uchun
        except:
            font_title = font_date = font_time = ImageFont.load_default()

        # 1. "YUQORI CHO'JA" yozuvini yopish va yangi viloyatni yozish
        # Koordinatalar shablonga moslangan
        draw.rectangle([300, 70, 750, 160], fill=(255, 255, 255)) # Oq bilan yopish
        draw.text((512, 115), region.upper(), fill=(14, 38, 101), font=font_title, anchor="mm")

        # 2. Sanani yozish
        draw.text((512, 260), date_str, fill=(0, 0, 0), font=font_date, anchor="mm")

        # 3. Vaqtlarni joylashtirish
        # Bomdod (Chap tepa)
        draw.text((250, 360), times['b'], fill="white", font=font_time, anchor="mm")
        # Peshin (O'ng tepa)
        draw.text((770, 360), times['p'], fill="white", font=font_time, anchor="mm")
        # Asr (Chap past)
        draw.text((250, 600), times['a'], fill="white", font=font_time, anchor="mm")
        # Shom (O'ng past)
        draw.text((770, 600), times['s'], fill="white", font=font_time, anchor="mm")
        # Xufton (Markaz past)
        draw.text((512, 825), times['h'], fill="white", font=font_time, anchor="mm")

        # 4. Pastdagi telegram manzilni o'chirish
        draw.rectangle([600, 930, 980, 990], fill=(255, 255, 255))

        bio = BytesIO()
        img.save(bio, 'JPEG')
        bio.seek(0)
        return bio
    except Exception as e:
        logging.error(f"Rasm yaratishda xato: {e}")
        return None

# --- BOT OBYEKTLARI ---
bot = Bot(token=TOKEN)
dp = Dispatcher()

@dp.message(Command("start"))
async def cmd_start(message: types.Message):
    builder = ReplyKeyboardBuilder()
    for r in REGION_OFFSETS.keys():
        builder.add(KeyboardButton(text=r))
    builder.adjust(2)
    await message.answer("✨ Assalomu alaykum! Viloyatingizni tanlang:", 
                         reply_markup=builder.as_markup(resize_keyboard=True))

@dp.message(Command("set"))
async def cmd_set(message: types.Message):
    if message.from_user.id != ADMIN_ID: return
    try:
        p = message.text.split() # /set 28.02 05:40 12:45 17:25 19:30 21:05
        if len(p) != 7:
            await message.answer("⚠️ Format: `/set 28.02 BOM PESH ASR SHOM XUF`")
            return
        db_query("INSERT OR REPLACE INTO times VALUES (?, ?, ?, ?, ?, ?)", (p[1], p[2], p[3], p[4], p[5], p[6]))
        await message.answer(f"✅ {p[1]} sanasi uchun vaqtlar saqlandi.")
    except Exception as e:
        await message.answer(f"Xato: {e}")

@dp.message(F.text.in_(REGION_OFFSETS.keys()))
async def handle_region(message: types.Message):
    region = message.text
    db_query("INSERT OR REPLACE INTO users (user_id, region) VALUES (?, ?)", (message.from_user.id, region))
    
    date_now = datetime.now(TASHKENT_TZ).strftime("%d.%m")
    res = db_query("SELECT * FROM times WHERE date=?", (date_now,), fetch=True)
    
    if not res:
        await message.answer("⚠️ Admin hali bugungi vaqtlarni kiritmadi.")
        return

    r = res[0]
    off = REGION_OFFSETS[region]
    
    def adj(t, m):
        return (datetime.strptime(t, "%H:%M") + timedelta(minutes=m)).strftime("%H:%M")

    times = {
        'b': adj(r[1], off), 'p': adj(r[2], off),
        'a': adj(r[3], off), 's': adj(r[4], off), 'h': adj(r[5], off)
    }

    # Bugungi sana o'zbekcha formatda
    date_full = datetime.now(TASHKENT_TZ).strftime("%d %B %Y")
    
    # Rasm tayyorlash
    photo_buffer = create_prayer_image(region, date_full, times)
    
    if photo_buffer:
        photo = BufferedInputFile(photo_buffer.read(), filename="namoz.jpg")
        await message.answer_photo(photo=photo, caption=f"📍 {region} viloyati namoz vaqtlari")
    else:
        await message.answer("❌ Xatolik: `shablon.jpg` fayli topilmadi yoki rasmda xato.")

async def main():
    db_setup()
    # Windowsda xatolik bermasligi uchun pollingni xavfsiz boshlash
    await dp.start_polling(bot, skip_updates=True)

if __name__ == '__main__':
    # Windows 10013 xatosini oldini olish uchun (Ba'zi tizimlarda kerak)
    if os.name == 'nt':
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    
    try:
        asyncio.run(main())
    except Exception as e:
        print(f"Bot to'xtadi: {e}")