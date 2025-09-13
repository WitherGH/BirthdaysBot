import os, json
import datetime
from datetime import time as dtime
from zoneinfo import ZoneInfo

from google.oauth2 import service_account
from googleapiclient.discovery import build

from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes

# === ENV ===
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
CHAT_ID = os.getenv("CHAT_ID")
SPREADSHEET_ID = os.getenv("SPREADSHEET_ID")
RANGE_NAME = "Лист1!A:C"  # A - Ім'я, B - Дата (YYYY-MM-DD), C - Лінк

# Київський час
TZ = ZoneInfo("Europe/Kyiv")
NOTIFY_TIME = dtime(hour=9, minute=0, tzinfo=TZ)

print("GOOGLE_CREDENTIALS:", os.getenv("GOOGLE_CREDENTIALS") is not None)

# --- Google Sheets auth ---
google_creds = json.loads(os.getenv("GOOGLE_CREDENTIALS"))
creds = service_account.Credentials.from_service_account_info(
    google_creds,
    scopes=["https://www.googleapis.com/auth/spreadsheets.readonly"]
)
service = build("sheets", "v4", credentials=creds)

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

# --- Щоденна перевірка та розсилки ---
async def check_and_notify(context: ContextTypes.DEFAULT_TYPE):
    today = datetime.date.today()
    rows = get_birthdays()
    if not rows or len(rows) < 2:
        return

    for row in rows[1:]:  # пропускаємо заголовок
        if len(row) < 3:
            continue
        name, date_str, wishlist = row[0].strip(), row[1].strip(), row[2].strip()
        try:
            bday = datetime.datetime.strptime(date_str, "%Y-%m-%d").date()
        except ValueError:
            continue

        this_year = bday.replace(year=today.year)
        if this_year < today:
            this_year = this_year.replace(year=today.year + 1)

        delta = (this_year - today).days
        age = calculate_age(bday, this_year)

        if delta == 7:
            await context.bot.send_message(
                chat_id=CHAT_ID,
                text=(
                    f"📢 Через тиждень ({this_year}) у {name} день народження! 🎉\n"
                    f"Виповниться {age} років.\n"
                    f"Віш-ліст: {wishlist}\n"
                    f"Тільки ніхто нічого не бачив, тсссс 🤫"
                )
            )
        elif delta == 3:
            await context.bot.send_message(
                chat_id=CHAT_ID,
                text=(
                    f"⏳ Уже скоро ({this_year}), через 3 дні святкує {name}! 🥳\n"
                    f"Виповниться {age} років.\n"
                    f"Віш-ліст: {wishlist}\n"
                    f"👀"
                )
            )
        elif delta == 0:
            await context.bot.send_message(
                chat_id=CHAT_ID,
                text=(
                    f"🎂 Сьогодні ({this_year}) у {name} день народження! 🎉🥳\n"
                    f"Виповнюється {age} років! 🎊\n"
                    f"Всі вітаємо! 🥂\nВіш-ліст: {wishlist}"
                )
            )

# --- /birthdays ---
async def birthdays_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    today = datetime.date.today()
    rows = get_birthdays()
    upcoming = []

    if rows and len(rows) > 1:
        for row in rows[1:]:
            if len(row) < 3:
                continue
            name, date_str, wishlist = row[0].strip(), row[1].strip(), row[2].strip()
            try:
                bday = datetime.datetime.strptime(date_str, "%Y-%m-%d").date()
            except ValueError:
                continue

            this_year = bday.replace(year=today.year)
            if this_year < today:
                this_year = this_year.replace(year=today.year + 1)
            delta = (this_year - today).days
            age = calculate_age(bday, this_year)

            if delta <= 30:
                upcoming.append(f"🎉 {this_year} – {name}, {age} років\n🔗 {wishlist}")

    msg = (
        "📅 Найближчі дні народження:\n\n" + "\n\n".join(upcoming)
        if upcoming else "Найближчих днів народження впродовж місяця немає ✅"
    )
    await update.message.reply_text(msg)

# --- main / webhook ---
def main():
    app = Application.builder().token(TELEGRAM_TOKEN).build()
    app.add_handler(CommandHandler("birthdays", birthdays_command))

    # JobQueue (потрібен extras: [webhooks,job-queue])
    job_queue = app.job_queue
    if job_queue is None:
        print("ERROR: JobQueue недоступний. Додай у requirements.txt: python-telegram-bot[webhooks,job-queue]")
        raise SystemExit(1)
    job_queue.run_daily(check_and_notify, time=NOTIFY_TIME, name="daily-birthdays")

    # Базовий URL для webhook:
    # 1) PUBLIC_URL (рекомендовано створити самому, значення = повний https URL сервісу на Render)
    # 2) RENDER_EXTERNAL_URL (іноді доступний)
    # 3) RENDER_EXTERNAL_HOSTNAME (тоді будуємо https://<hostname>)
    base_url = (
        os.getenv("PUBLIC_URL")
        or os.getenv("RENDER_EXTERNAL_URL")
        or (f"https://{os.getenv('RENDER_EXTERNAL_HOSTNAME')}" if os.getenv("RENDER_EXTERNAL_HOSTNAME") else None)
    )
    print("PUBLIC_URL:", os.getenv("PUBLIC_URL"))
    print("RENDER_EXTERNAL_URL:", os.getenv("RENDER_EXTERNAL_URL"))
    print("RENDER_EXTERNAL_HOSTNAME:", os.getenv("RENDER_EXTERNAL_HOSTNAME"))
    print("Resolved base_url:", base_url)

    if not base_url:
        print(
            "ERROR: Не знайдено URL для webhook. "
            "Додай PUBLIC_URL зі значенням типу https://<your-service>.onrender.com у Environment."
        )
        raise SystemExit(1)

    # Запуск webhook-сервера PTB
    app.run_webhook(
        listen="0.0.0.0",
        port=int(os.getenv("PORT", 8080)),
        url_path=TELEGRAM_TOKEN,
        webhook_url=f"{base_url}/{TELEGRAM_TOKEN}",
    )

if __name__ == "__main__":
    main()
