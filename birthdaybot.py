import datetime
import os, json
from googleapiclient.discovery import build
from google.oauth2 import service_account
from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes
from datetime import time as dtime
from zoneinfo import ZoneInfo

# === Налаштування ===
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
CHAT_ID = os.getenv("CHAT_ID")
SPREADSHEET_ID = os.getenv("SPREADSHEET_ID")
PORT = int(os.getenv("PORT", 8443))  # Render дає PORT автоматично
RANGE_NAME = "Лист1!A:C"
TZ = ZoneInfo("Europe/Kyiv")
NOTIFY_TIME = dtime(hour=9, minute=0, tzinfo=TZ)

print("GOOGLE_CREDENTIALS:", os.getenv("GOOGLE_CREDENTIALS") is not None)

# Авторизація Google Sheets
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

# --- Щоденна перевірка ---
async def check_and_notify(context: ContextTypes.DEFAULT_TYPE):
    today = datetime.date.today()
    birthdays = get_birthdays()

    for row in birthdays[1:]:
        if len(row) < 3:
            continue
        name, date_str, wishlist = row[0], row[1], row[2]

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
                text=f"📢 Через тиждень ({this_year}) у {name} день народження! 🎉\n"
                     f"Йому/їй виповнюється {age} років.\n"
                     f"Віш-ліст: {wishlist}\n"
                     f"Тільки ніхто нічого не бачив, тсссс 🤫"
            )
        elif delta == 3:
            await context.bot.send_message(
                chat_id=CHAT_ID,
                text=f"⏳ Уже скоро ({this_year}), через 3 дні святкує {name}! 🥳\n"
                     f"Йому/їй виповнюється {age} років.\n"
                     f"Віш-ліст: {wishlist}\n"
                     f"👀"
            )
        elif delta == 0:
            await context.bot.send_message(
                chat_id=CHAT_ID,
                text=f"🎂 Сьогодні ({this_year}) у {name} день народження! 🎉🥳\n"
                     f"Виповнюється {age} років! 🎊\n"
                     f"Всі вітаємо! 🥂\nВіш-ліст: {wishlist}"
            )

# --- Команда /birthdays ---
async def birthdays_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    today = datetime.date.today()
    birthdays = get_birthdays()
    upcoming = []

    for row in birthdays[1:]:
        if len(row) < 3:
            continue
        name, date_str, wishlist = row[0], row[1], row[2]

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

    msg = "📅 Найближчі дні народження:\n\n" + "\n\n".join(upcoming) if upcoming \
          else "Найближчих днів народження впродовж місяця немає ✅"

    await update.message.reply_text(msg)

# --- Головний цикл ---
def main():
    app = Application.builder().token(TELEGRAM_TOKEN).build()
    app.add_handler(CommandHandler("birthdays", birthdays_command))

    # ✅ JobQueue (щоденні нагадування)
    job_queue = app.job_queue
    if job_queue is None:
        raise RuntimeError(
            'JobQueue недоступний. Додай у requirements.txt: python-telegram-bot[webhooks,job-queue]'
        )
    job_queue.run_daily(check_and_notify, time=NOTIFY_TIME, name="daily-birthdays")

    # ✅ Webhook URL з fallback
    base_url = os.getenv("RENDER_EXTERNAL_URL") or (
        f"https://{os.getenv('RENDER_EXTERNAL_HOSTNAME')}" if os.getenv('RENDER_EXTERNAL_HOSTNAME') else None
    )
    if not base_url:
        raise RuntimeError("Не знайдено RENDER_EXTERNAL_URL або RENDER_EXTERNAL_HOSTNAME у змінних середовища")

    app.run_webhook(
        listen="0.0.0.0",
        port=int(os.getenv("PORT", 8080)),
        url_path=TELEGRAM_TOKEN,
        webhook_url=f"{base_url}/{TELEGRAM_TOKEN}",
    )