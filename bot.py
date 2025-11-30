from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ApplicationBuilder, CommandHandler, ContextTypes, CallbackQueryHandler, MessageHandler, filters
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
    return [row["Time"] for row in all_records if row["Date"] == date and row["Player"] == ""]

def mark_slot_booked(date, time, player_name):
    sheet = get_sheet()
    all_records = sheet.get_all_records()
    for i, row in enumerate(all_records, start=2):
        if row["Date"] == date and row["Time"] == time:
            sheet.update_cell(i, 3, player_name)
            break

def get_user_bookings(player_name):
    sheet = get_sheet()
    all_records = sheet.get_all_records()
    return [(row["Date"], row["Time"]) for row in all_records if row["Player"] == player_name]

def cancel_booking(date, time, player_name):
    sheet = get_sheet()
    all_records = sheet.get_all_records()
    for i, row in enumerate(all_records, start=2):
        if row["Date"] == date and row["Time"] == time and row["Player"] == player_name:
            sheet.update_cell(i, 3, "")
            break


# --- Telegram handlers ---
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
       "👋 *Welcome to your Personal Practice Booking Bot!*\n\n"
        "This bot helps you schedule, view, and cancel basketball practice sessions with Coach Grigori.\n\n"
        "📌 *Available Commands:*\n"
        "• /book - Schedule a new practice 🏀\n"
        "• /mybookings - View your booked sessions 📘\n"
        "• /cancel - Cancel a booking ❎\n\n"
        "⏳ The bot may take a few seconds to process your request.\n"
        "Let's get you on the court! 💪"
    )


async def book(update: Update, context: ContextTypes.DEFAULT_TYPE):
    sheet = get_sheet()
    records = sheet.get_all_records()

    dates = sorted(set(row["Date"] for row in records))
    if not dates:
        await update.message.reply_text("No available dates right now.")
        return

    keyboard = [
        [InlineKeyboardButton(date, callback_data=f"date:{date}")]
        for date in dates
    ]

    await update.message.reply_text("Choose a date:", reply_markup=InlineKeyboardMarkup(keyboard))


async def mybookings(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Please type the name to search bookings for:")
    context.user_data["awaiting_check_name"] = True


async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Please type the name used for the booking you want to cancel:")
    context.user_data["awaiting_cancel_name"] = True


async def handle_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    data = query.data

    if data.startswith("date:"):
        date = data.split(":", 1)[1]
        times = get_available_slots(date)

        if not times:
            await query.edit_message_text("No free slots on this date.")
            return

        keyboard = [
            [InlineKeyboardButton(t, callback_data=f"time:{date}:{t}")]
            for t in times
        ]

        await query.edit_message_text(f"Choose a time for {date}:", reply_markup=InlineKeyboardMarkup(keyboard))

    elif data.startswith("time:"):
        _, date, time = data.split(":", 2)

        context.user_data["pending_date"] = date
        context.user_data["pending_time"] = time
        context.user_data["awaiting_player_name"] = True

        await query.edit_message_text(
            f"You selected {date} at {time}.\n\n"
            "👉 Please type the *player name* to complete the booking:"
        )


async def cancel_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    _, date, time, name = query.data.split(":", 3)
    cancel_booking(date, time, name)

    await query.edit_message_text(
        f"❎ Booking on {date} at {time} for {name} has been cancelled."
    )


async def text_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.strip()

    # Handle booking name input
    if context.user_data.get("awaiting_player_name"):
        date = context.user_data["pending_date"]
        time = context.user_data["pending_time"]

        mark_slot_booked(date, time, text)

        await update.message.reply_text(
            f"✅ Booking confirmed!\n\n"
            f"📅 Date: {date}\n"
            f"⏰ Time: {time}\n"
            f"👤 Player: {text}"
        )

        context.user_data.clear()
        return

    # Handle searching bookings
    if context.user_data.get("awaiting_check_name"):
        name = text
        bookings = get_user_bookings(name)

        if not bookings:
            await update.message.reply_text("No bookings found.")
        else:
            msg = "📘 Bookings for " + name + ":\n\n"
            for d, t in bookings:
                msg += f"• {d} — {t}\n"
            await update.message.reply_text(msg)

        context.user_data.clear()
        return

    # Handle cancel search name
    if context.user_data.get("awaiting_cancel_name"):
        name = text
        bookings = get_user_bookings(name)

        if not bookings:
            await update.message.reply_text("No bookings found.")
            context.user_data.clear()
            return

        keyboard = [
            [InlineKeyboardButton(f"{d} — {t}", callback_data=f"cancel:{d}:{t}:{name}")]
            for d, t in bookings
        ]

        await update.message.reply_text(
            "Select the booking to cancel:",
            reply_markup=InlineKeyboardMarkup(keyboard)
        )

        context.user_data.clear()
        return


# --- Main ---
app = ApplicationBuilder().token(BOT_TOKEN).build()
app.add_handler(CommandHandler("start", start))
app.add_handler(CommandHandler("book", book))
app.add_handler(CommandHandler("mybookings", mybookings))
app.add_handler(CommandHandler("cancel", cancel))

app.add_handler(CallbackQueryHandler(handle_callback, pattern="^(date:|time:)"))
app.add_handler(CallbackQueryHandler(cancel_handler, pattern="^cancel:"))

app.add_handler(MessageHandler(filters.ALL & ~filters.COMMAND, text_handler))

app.run_polling()

