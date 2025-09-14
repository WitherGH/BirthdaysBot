# birthdaybot.py
import os, json
import datetime
import random
from datetime import time as dtime
from zoneinfo import ZoneInfo

from google.oauth2 import service_account
from googleapiclient.discovery import build

from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes

import telegram
print("PTB version:", getattr(telegram, "__version__", "unknown"))

# === ENV ===
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
CHAT_ID = os.getenv("CHAT_ID")                    # -100.... (ID групи)
SPREADSHEET_ID = os.getenv("SPREADSHEET_ID")     # ID гугл-таблиці
RANGE_NAME = "Лист1!A:C"                         # A: Ім'я, B: Дата YYYY-MM-DD, C: Віш-ліст

# Київський час + час дзвінка
TZ = ZoneInfo("Europe/Kyiv")
NOTIFY_TIME = dtime(hour=9, minute=0, tzinfo=TZ)

# --- Google Sheets auth ---
print("GOOGLE_CREDENTIALS:", os.getenv("GOOGLE_CREDENTIALS") is not None)
google_creds = json.loads(os.getenv("GOOGLE_CREDENTIALS"))
creds = service_account.Credentials.from_service_account_info(
    google_creds,
    scopes=["https://www.googleapis.com/auth/spreadsheets.readonly"]
)
service = build("sheets", "v4", credentials=creds)

MONTHS_UK = [
    "січня","лютого","березня","квітня","травня","червня",
    "липня","серпня","вересня","жовтня","листопада","грудня"
]

def format_date_uk(d: datetime.date) -> str:
    return f"{d.day} {MONTHS_UK[d.month - 1]}"

def next_birthday_date(bday: datetime.date, today: datetime.date) -> datetime.date:
    this_year = bday.replace(year=today.year)
    return this_year if this_year >= today else this_year.replace(year=today.year + 1)

# Шаблони
TEMPLATES_7D = [
    "📢 Через тиждень — {date} — святкує {name}. Виповниться {age}. Віш-ліст: {wishlist}\n(тільки ніхто нічого не бачив 🤫)",
    "🔔 За 7 днів {name}: {date}. {age} років. Список бажань: {wishlist}",
    "🗓️ {date} — у {name} ДН! Плануємо привітання! {age} років. Віш-ліст: {wishlist}"
]
TEMPLATES_3D = [
    "⏳ Залишилось 3 дні: {date} — {name}. {age}. Ідеї подарунків: {wishlist}",
    "🚀 3 дні до ДН {name} ({date}). {age} років. {wishlist}",
    "🧁 Уже скоро — {date}. {name}, {age} років. Ось віш-ліст: {wishlist}"
]
TEMPLATES_0D = [
    "🎂 Сьогодні — {date}. Вітаємо {name}! Виповнюється {age}! 🎉 Віш-ліст: {wishlist}",
    "🥳 Сьогодні святкує {name} ({date}) — {age}. Теплі слова та гіфки вітаються! Віш-ліст: {wishlist}",
    "🎉 День Х! {name}, {age} — вітаємо! Віш-ліст: {wishlist}"
]

def get_birthdays():
    res = service.spreadsheets().values().get(
        spreadsheetId=SPREADSHEET_ID, range=RANGE_NAME
    ).execute()
    return res.get("values", [])

def calculate_age(bday: datetime.date, ref_date: datetime.date) -> int:
    age = ref_date.year - bday.year
    if (ref_date.month, ref_date.day) < (bday.month, bday.day):
        age -= 1
    return age

def parse_row(row):
    name = row[0].strip() if len(row) > 0 else ""
    date_str = row[1].strip() if len(row) > 1 else ""
    wishlist = row[2].strip() if len(row) > 2 and row[2].strip() else "❌ не додано"
    return name, date_str, wishlist

# --- Щоденна перевірка ---
async def check_and_notify(context: ContextTypes.DEFAULT_TYPE):
    today = datetime.date.today()
    rows = get_birthdays()
    if not rows or len(rows) < 2:
        return

    for row in rows[1:]:
        name, date_str, wishlist = parse_row(row)
        if not name or not date_str:
            continue
        try:
            bday = datetime.datetime.strptime(date_str, "%Y-%m-%d").date()
        except ValueError:
            continue

        d_next = next_birthday_date(bday, today)
        delta = (d_next - today).days
        age = calculate_age(bday, d_next)
        date_txt = format_date_uk(d_next)

        if delta == 7:
            msg = random.choice(TEMPLATES_7D).format(name=name, date=date_txt, age=age, wishlist=wishlist)
            await context.bot.send_message(chat_id=CHAT_ID, text=msg)
        elif delta == 3:
            msg = random.choice(TEMPLATES_3D).format(name=name, date=date_txt, age=age, wishlist=wishlist)
            await context.bot.send_message(chat_id=CHAT_ID, text=msg)
        elif delta == 0:
            msg = random.choice(TEMPLATES_0D).format(name=name, date=date_txt, age=age, wishlist=wishlist)
            await context.bot.send_message(chat_id=CHAT_ID, text=msg)

# --- Команда /birthdays (топ-3) ---
async def birthdays_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    today = datetime.date.today()
    rows = get_birthdays()
    people = []

    if rows and len(rows) > 1:
        for row in rows[1:]:
            name, date_str, wishlist = parse_row(row)
            if not name or not date_str:
                continue
            try:
                bday = datetime.datetime.strptime(date_str, "%Y-%m-%d").date()
            except ValueError:
                continue

            d_next = next_birthday_date(bday, today)
            delta = (d_next - today).days
            age = calculate_age(bday, d_next)
            people.append((delta, name, d_next, age, wishlist))

    if not people:
        await update.message.reply_text("Найближчих днів народження поки не видно ✅")
        return

    people.sort(key=lambda x: x[0])
    top = people[:3]

    lines = []
    for i, (_, name, d_next, age, wishlist) in enumerate(top, start=1):
        lines.append(f"{i}) {format_date_uk(d_next)} — {name}, виповнюється {age}. Віш-ліст: {wishlist}")

    msg = "🎉 Найближчі дні народження (топ-3):\n\n" + "\n".join(lines) + "\n\nТільки не забудь 😉"
    await update.message.reply_text(msg)

# --- main ---
def main():
    app = Application.builder().token(TELEGRAM_TOKEN).build()
    app.add_handler(CommandHandler("birthdays", birthdays_command))

    # JobQueue (необхідно мати extras: [webhooks,job-queue] у requirements.txt)
    if app.job_queue is None:
        raise SystemExit("JobQueue недоступний. Додай у requirements: python-telegram-bot[webhooks,job-queue]==21.6")
    app.job_queue.run_daily(check_and_notify, time=NOTIFY_TIME, name="daily-birthdays")

    # Зовнішній URL для вебхука
    base_url = (
        os.getenv("PUBLIC_URL")
        or os.getenv("RENDER_EXTERNAL_URL")
        or (f"https://{os.getenv('RENDER_EXTERNAL_HOSTNAME')}" if os.getenv("RENDER_EXTERNAL_HOSTNAME") else None)
    )
    if not base_url:
        raise SystemExit("ERROR: Не знайдено URL для webhook. Додай PUBLIC_URL (https://<your-service>.onrender.com).")

    # Запуск вбудованого Tornado-вебсервера PTB + реєстрація вебхука
    app.run_webhook(
        listen="0.0.0.0",
        port=int(os.getenv("PORT", 8080)),
        url_path=TELEGRAM_TOKEN,
        webhook_url=f"{base_url}/{TELEGRAM_TOKEN}",
    )

if __name__ == "__main__":
    main()
