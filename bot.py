from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    ApplicationBuilder, CommandHandler, ContextTypes, CallbackQueryHandler,
    ConversationHandler, MessageHandler, filters
)
import gspread
from oauth2client.service_account import ServiceAccountCredentials
import json
import os

# --- Telegram bot token ---
BOT_TOKEN = os.environ.get("BOT_TOKEN")

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
    return [row['Time'] for row in all_records if row['Date'] == date and row['Player'] == ""]

def mark_slot_booked(date, time, player_name):
    sheet = get_sheet()
    all_records = sheet.get_all_records()
    for i, row in enumerate(all_records, start=2):
        if row['Date'] == date and row['Time'] == time:
            sheet.update_cell(i, 3, player_name)
            break

def get_user_bookings(name):
    sheet = get_sheet()
    all_records = sheet.get_all_records()
    return [(row['Date'], row['Time']) for row in all_records if row['Player'] == name]

def cancel_booking(date, time, player_name):
    sheet = get_sheet()
    all_records = sheet.get_all_records()
    for i, row in enumerate(all_records, start=2):
        if row['Date'] == date and row['Time'] == time and row['Player'] == player_name:
            sheet.update_cell(i, 3, "")
            break


# --- Conversation states ---
CHOOSE_DATE, CHOOSE_TIME, ENTER_NAME, ENTER_CANCEL_NAME = range(4)


# --- /start ---
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
    await update.message.reply_text(intro_text, parse_mode="Markdown")


# --- BOOKING FLOW ---
async def book(update: Update, context: ContextTypes.DEFAULT_TYPE):
    sheet = get_sheet()
    records = sheet.get_all_records()
    dates = sorted(set(row['Date'] for row in records))

    if not dates:
        await update.message.reply_text("No available dates right now.")
        return ConversationHandler.END

    keyboard = [[InlineKeyboardButton(date, callback_data=f"date:{date}")] for date in dates]
    await update.message.reply_text("Choose a date:", reply_markup=InlineKeyboardMarkup(keyboard))
    return CHOOSE_DATE


async def handle_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data

    # --- BOOKING: Choose time ---
    if data.startswith("date:"):
        date = data.split(":", 1)[1]
        times = get_available_slots(date)

        if not times:
            await query.edit_message_text("Sorry, no slots available on this date.")
            return ConversationHandler.END

        keyboard = [[InlineKeyboardButton(t, callback_data=f"time:{date}:{t}")] for t in times]
        await query.edit_message_text(f"Choose a time for {date}:", reply_markup=InlineKeyboardMarkup(keyboard))
        return CHOOSE_TIME

    # --- BOOKING: Ask name ---
    if data.startswith("time:"):
        _, date, time = data.split(":", 2)
        context.user_data['booking_date'] = date
        context.user_data['booking_time'] = time
        await query.edit_message_text(f"You selected {date} at {time}.\n\nPlease type your full name:")
        return ENTER_NAME

    # --- CANCEL: Confirm cancellation ---
    if data.startswith("cancel:"):
        _, date, time, name = data.split(":", 3)
        cancel_booking(date, time, name)
        await query.edit_message_text(f"❎ Cancelled: {date} at {time} for {name}")
        return ConversationHandler.END


async def enter_name(update: Update, context: ContextTypes.DEFAULT_TYPE):
    name = update.message.text
    date = context.user_data["booking_date"]
    time = context.user_data["booking_time"]

    mark_slot_booked(date, time, name)

    await update.message.reply_text(f"✅ Booking confirmed for {name} on {date} at {time}!")
    context.user_data.clear()
    return ConversationHandler.END


# --- CANCEL FLOW ---
async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Please enter the name you used to book:")
    return ENTER_CANCEL_NAME


async def cancel_choose(update: Update, context: ContextTypes.DEFAULT_TYPE):
    name = update.message.text
    context.user_data["cancel_name"] = name

    bookings = get_user_bookings(name)

    if not bookings:
        await update.message.reply_text("❌ No bookings found under that name.")
        return ConversationHandler.END

    keyboard = [
        [InlineKeyboardButton(f"{date} — {time}", callback_data=f"cancel:{date}:{time}:{name}")]
        for date, time in bookings
    ]

    await update.message.reply_text(
        "Select a session to cancel:",
        reply_markup=InlineKeyboardMarkup(keyboard)
    )

    return ConversationHandler.END


# --- MY BOOKINGS FLOW ---
async def mybookings(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Please enter the name you used for booking:")
    return ENTER_CANCEL_NAME  # reuse same flow


# --- MAIN APPLICATION ---
app = ApplicationBuilder().token(BOT_TOKEN).build()

# Booking handler
booking_handler = ConversationHandler(
    entry_points=[CommandHandler("book", book)],
    states={
        CHOOSE_DATE: [CallbackQueryHandler(handle_callback, pattern="^date:")],
        CHOOSE_TIME: [CallbackQueryHandler(handle_callback, pattern="^time:")],
        ENTER_NAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, enter_name)],
    },
    fallbacks=[]
)

# Cancel + Mybookings share the same name-input flow
cancel_handler = ConversationHandler(
    entry_points=[CommandHandler("cancel", cancel), CommandHandler("mybookings", mybookings)],
    states={
        ENTER_CANCEL_NAME: [MessageHandler(filters.TEXT & ~filters.COMMAND, cancel_choose)],
    },
    fallbacks=[]
)

app.add_handler(CommandHandler("start", start))
app.add_handler(booking_handler)
app.add_handler(cancel_handler)
app.add_handler(CallbackQueryHandler(handle_callback, pattern="^cancel:"))

app.run_polling()
