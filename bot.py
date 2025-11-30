from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ApplicationBuilder, CommandHandler, ContextTypes, CallbackQueryHandler
import gspread
from oauth2client.service_account import ServiceAccountCredentials

# --- Telegram bot token ---
BOT_TOKEN = "YOUR_BOT_TOKEN"

# --- Google Sheets setup ---
def get_sheet():
    scope = [
        "https://spreadsheets.google.com/feeds",
        "https://www.googleapis.com/auth/spreadsheets",
        "https://www.googleapis.com/auth/drive.file",
        "https://www.googleapis.com/auth/drive"
    ]
    creds = ServiceAccountCredentials.from_json_keyfile_name("credentials.json", scope)
    client = gspread.authorize(creds)
    sheet = client.open("Coach_Grigori_Bookings").sheet1
    return sheet

def get_available_slots(date):
    sheet = get_sheet()
    all_records = sheet.get_all_records()
    return [row['Time'] for row in all_records if row['Date'] == date and row['Player'] == ""]

def mark_slot_booked(date, time, player_name):
    sheet = get_sheet()
    all_records = sheet.get_all_records()
    for i, row in enumerate(all_records, start=2):
        if str(row['Date']).strip() == str(date).strip() and str(row['Time']).strip() == str(time).strip():
            sheet.update_cell(i, 3, player_name)
            break

def get_user_bookings(player_name):
    sheet = get_sheet()
    all_records = sheet.get_all_records()
    return [
        (row['Date'], row['Time'])
        for row in all_records
        if row['Player'] == player_name
    ]

# --- FIXED cancel_booking ---
def cancel_booking(date, time):
    sheet = get_sheet()
    all_records = sheet.get_all_records()
    for i, row in enumerate(all_records, start=2):
        sheet_date = str(row['Date']).strip()
        sheet_time = str(row['Time']).strip()
        if sheet_date == str(date).strip() and sheet_time == str(time).strip():
            sheet.update_cell(i, 3, "")
            return True
    return False

# --- Telegram handlers ---
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    intro_text = (
        "👋 *Welcome to your Personal Practice Booking Bot!*\n\n"
        "This bot helps you schedule, view, and cancel basketball practice sessions with Coach Grigori.\n\n"
        "📌 *Available Commands:*\n"
        "• /book - Schedule a new practice 🏀\n"
        "• /mybookings - View your booked sessions 📘\n"
        "• /cancel - Cancel a booking ❎\n\n"
        "⏳ The bot may take a few seconds to process your request.\n"
        "Let's get you on the court! 💪"
    )
    await context.bot.send_message(chat_id=update.effective_chat.id, text=intro_text, parse_mode="Markdown")

async def book(update: Update, context: ContextTypes.DEFAULT_TYPE):
    sheet = get_sheet()
    records = sheet.get_all_records()
    dates = sorted(set(row['Date'] for row in records))
    if not dates:
        await update.message.reply_text("No available dates right now.")
        return
    keyboard = [[InlineKeyboardButton(date, callback_data=f"date:{date}")] for date in dates]
    await update.message.reply_text("Choose a date:", reply_markup=InlineKeyboardMarkup(keyboard))

async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.message.from_user.first_name
    bookings = get_user_bookings(user)
    if not bookings:
        await update.message.reply_text("❌ You have no booked sessions to cancel.")
        return
    keyboard = [[InlineKeyboardButton(f"{date} — {time}", callback_data=f"cancel:{date}:{time}")] for date, time in bookings]
    await update.message.reply_text("Select a booking to cancel:", reply_markup=InlineKeyboardMarkup(keyboard))

async def mybookings(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.message.from_user.first_name
    bookings = get_user_bookings(user)
    if not bookings:
        await update.message.reply_text("📘 You have no current bookings.")
        return
    keyboard = [[InlineKeyboardButton(f"{date} — {time}", callback_data=f"cancel:{date}:{time}")] for date, time in bookings]
    await update.message.reply_text("📘 Here are your bookings:\n\nTap any booking below to cancel it:", reply_markup=InlineKeyboardMarkup(keyboard))

async def handle_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data

    if data.startswith("date:"):
        date = data.split(":", 1)[1]
        times = get_available_slots(date)
        if not times:
            await query.edit_message_text("Sorry, no slots available on this date.")
            return
        keyboard = [[InlineKeyboardButton(t, callback_data=f"time:{date}:{t}")] for t in times]
        await query.edit_message_text(f"Choose a time for {date}:", reply_markup=InlineKeyboardMarkup(keyboard))

    elif data.startswith("time:"):
        _, date, time = data.split(":", 2)
        user = query.from_user.first_name
        mark_slot_booked(date, time, user)
        await query.edit_message_text(f"Booked {date} at {time} for {user} ✅")

    elif data.startswith("cancel:"):
        _, date, time = data.split(":", 2)
        success = cancel_booking(date, time)
        if success:
            await query.edit_message_text(f"❎ Your session on {date} at {time} was cancelled.")
        else:
            await query.edit_message_text(f"⚠️ Failed to cancel booking on {date} at {time}. Please check the schedule.")

# --- Main ---
app = ApplicationBuilder().token(BOT_TOKEN).build()
app.add_handler(CommandHandler("start", start))
app.add_handler(CommandHandler("book", book))
app.add_handler(CommandHandler("cancel", cancel))
app.add_handler(CommandHandler("mybookings", mybookings))
app.add_handler(CallbackQueryHandler(handle_callback))
app.run_polling()
