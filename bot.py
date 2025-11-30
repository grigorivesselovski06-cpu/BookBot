from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ApplicationBuilder, CommandHandler, ContextTypes, CallbackQueryHandler, MessageHandler, filters
import gspread
from oauth2client.service_account import ServiceAccountCredentials
import json
import os

# --- Telegram bot token ---
BOT_TOKEN = os.environ.get("BOT_TOKEN")  # safer to set via env var

# --- Google Sheets setup ---
def get_sheet():
    scope = [
        "https://spreadsheets.google.com/feeds",
        "https://www.googleapis.com/auth/spreadsheets",
        "https://www.googleapis.com/auth/drive.file",
        "https://www.googleapis.com/auth/drive"
    ]

    keyfile_dict = json.loads(os.environ.get("GOOGLE_CREDS_JSON"))
    creds = ServiceAccountCredentials.from_json_keyfile_dict(keyfile_dict, scope)

    client = gspread.authorize(creds)
    sheet = client.open("Coach_Grigori_Bookings").sheet1
    return sheet

def get_available_slots(date):
    sheet = get_sheet()
    all_records = sheet.get_all_records()
    free_slots = [row['Time'] for row in all_records if row['Date'] == date and row['Player'] == ""]
    return free_slots

def mark_slot_booked(date, time, player_name):
    sheet = get_sheet()
    all_records = sheet.get_all_records()
    for i, row in enumerate(all_records, start=2):
        if row['Date'] == date and row['Time'] == time:
            sheet.update_cell(i, 3, player_name)
            break

def get_user_bookings(player_name):
    sheet = get_sheet()
    all_records = sheet.get_all_records()
    bookings = [(row['Date'], row['Time']) for row in all_records if row['Player'] == player_name]
    return bookings

def cancel_booking(date, time, player_name):
    sheet = get_sheet()
    all_records = sheet.get_all_records()
    for i, row in enumerate(all_records, start=2):
        if row['Date'] == date and row['Time'] == time and row['Player'] == player_name:
            sheet.update_cell(i, 3, "")
            break

# --- NEW: Name setter ---
async def setname(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if len(context.args) == 0:
        await update.message.reply_text("Please enter your full name, for example:\n\n/setname John Smith")
        return

    real_name = " ".join(context.args)
    context.user_data["real_name"] = real_name

    await update.message.reply_text(f"✅ Your name has been saved as: *{real_name}*\n\nThis name will be used for all bookings.", parse_mode="Markdown")

def get_saved_name(context):
    return context.user_data.get("real_name", None)

# --- Telegram handlers ---
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    intro_text = (
        "👋 *Welcome!*\n\n"
        "Before booking, please set your real name:\n"
        "👉 /setname Your Name\n\n"
        "📌 *Commands:*\n"
        "• /book - Book a session\n"
        "• /mybookings - View booked sessions\n"
        "• /cancel - Cancel a session"
    )
    await update.message.reply_text(intro_text, parse_mode="Markdown")

async def book(update: Update, context: ContextTypes.DEFAULT_TYPE):

    # check if user set their real name
    real_name = get_saved_name(context)
    if not real_name:
        await update.message.reply_text("❗ Please set your name first using:\n/setname Your Name")
        return

    sheet = get_sheet()
    records = sheet.get_all_records()
    dates = sorted(set(row['Date'] for row in records))
    if not dates:
        await update.message.reply_text("No available dates right now.")
        return

    keyboard = [[InlineKeyboardButton(date, callback_data=f"date:{date}")] for date in dates]
    await update.message.reply_text("Choose a date:", reply_markup=InlineKeyboardMarkup(keyboard))

async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    real_name = get_saved_name(context)
    if not real_name:
        await update.message.reply_text("❗ Please set your name first:\n/setname Your Name")
        return

    bookings = get_user_bookings(real_name)

    if not bookings:
        await update.message.reply_text("❌ You have no booked sessions to cancel.")
        return

    keyboard = [
        [InlineKeyboardButton(f"{date} — {time}", callback_data=f"cancel:{date}:{time}")]
        for date, time in bookings
    ]
    await update.message.reply_text("Select a booking to cancel:", reply_markup=InlineKeyboardMarkup(keyboard))

async def mybookings(update: Update, context: ContextTypes.DEFAULT_TYPE):
    real_name = get_saved_name(context)
    if not real_name:
        await update.message.reply_text("❗ Please set your name first:\n/setname Your Name")
        return

    bookings = get_user_bookings(real_name)

    if not bookings:
        await update.message.reply_text("📘 You have no current bookings.")
        return

    keyboard = [
        [InlineKeyboardButton(f"{date} — {time}", callback_data=f"cancel:{date}:{time}")]
        for date, time in bookings
    ]
    await update.message.reply_text(
        "📘 Here are your bookings:\n\nTap any booking to cancel it:",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )

async def handle_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data

    real_name = get_saved_name(context)
    if not real_name:
        await query.edit_message_text("❗ Please set your name first:\n/setname Your Name")
        return

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
        mark_slot_booked(date, time, real_name)
        await query.edit_message_text(f"✅ Booked {date} at {time} for {real_name}")

    elif data.startswith("cancel:"):
        _, date, time = data.split(":", 2)
        cancel_booking(date, time, real_name)
        await query.edit_message_text(f"❎ Session on {date} at {time} cancelled.")

# --- Main ---
app = ApplicationBuilder().token(BOT_TOKEN).build()
app.add_handler(CommandHandler("start", start))
app.add_handler(CommandHandler("setname", setname))
app.add_handler(CommandHandler("book", book))
app.add_handler(CommandHandler("cancel", cancel))
app.add_handler(CommandHandler("mybookings", mybookings))
app.add_handler(CallbackQueryHandler(handle_callback))
app.run_polling()
