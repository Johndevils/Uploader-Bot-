import os
import asyncio
from flask import Flask, request, render_template_string
from pymongo import MongoClient
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.constants import ChatAction
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    CallbackQueryHandler,
    ContextTypes,
)
from threading import Thread

# MongoDB Setup with URI support
MONGODB_URI = os.getenv("MONGODB_URI", "mongodb://localhost:27017/")
mongo_client = MongoClient(MONGODB_URI)
db = mongo_client["telegram_bot"]
collection = db["user_data"]

# Flask Web Server
flask_app = Flask(__name__)

HTML_FORM = '''
<!DOCTYPE html>
<html>
<head>
    <title>Arsynox Store</title>
    <style>
        body { font-family: Arial, sans-serif; text-align: center; margin-top: 50px; }
        input, textarea, button, select { padding: 10px; margin: 10px; width: 80%; max-width: 400px; }
        button { background-color: #4CAF50; color: white; border: none; cursor: pointer; }
    </style>
</head>
<body>
    <h1>Arsynox Store</h1>
    <form action="/upload" method="post">
        <input type="text" name="user_id" placeholder="User ID" required><br>
        <textarea name="content" placeholder="Text or File ID" required></textarea><br>
        <select name="type">
            <option value="text">Text</option>
            <option value="photo">Photo</option>
        </select><br>
        <button type="submit">Upload</button>
    </form>
</body>
</html>
'''

@flask_app.route("/upload", methods=["GET", "POST"])
def upload():
    if request.method == "GET":
        return render_template_string(HTML_FORM)

    user_id = request.form.get("user_id")
    content = request.form.get("content")
    data_type = request.form.get("type", "text")

    if not user_id or not content:
        return {"error": "Missing user_id or content"}, 400

    collection.update_one(
        {"user_id": int(user_id)},
        {"$set": {"type": data_type, "content": content}},
        upsert=True
    )
    return {"status": "success"}, 200


# Telegram Bot Handlers

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Welcome! Use /store to save and /get to retrieve your content.")

async def show_star_progress_bar(context, chat_id, message_text="Uploading"):
    progress_states = [
        "[☆☆☆☆☆☆☆☆☆☆] 0%",
        "[★★☆☆☆☆☆☆☆☆] 20%",
        "[★★★★☆☆☆☆☆☆] 40%",
        "[★★★★★★☆☆☆☆] 60%",
        "[★★★★★★★★☆☆] 80%",
        "[★★★★★★★★★★] 100%"
    ]
    msg = await context.bot.send_message(chat_id, f"{message_text}: {progress_states[0]}")
    for state in progress_states[1:]:
        await asyncio.sleep(0.4)
        await msg.edit_text(f"{message_text}: {state}")
    return msg

async def store_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id
    await update.message.chat.send_action(ChatAction.TYPING)

    # Show simulated progress bar
    progress_msg = await show_star_progress_bar(context, update.effective_chat.id)

    if update.message.reply_to_message and update.message.reply_to_message.photo:
        photo_file_id = update.message.reply_to_message.photo[-1].file_id
        collection.update_one(
            {"user_id": user_id},
            {"$set": {"type": "photo", "content": photo_file_id}},
            upsert=True
        )
    else:
        text = ' '.join(context.args)
        if not text:
            await progress_msg.edit_text("Please provide text to store after /store or reply to an image.")
            return
        collection.update_one(
            {"user_id": user_id},
            {"$set": {"type": "text", "content": text}},
            upsert=True
        )

    keyboard = InlineKeyboardMarkup([[InlineKeyboardButton("✅ Confirm", callback_data="confirm_store")]])
    await progress_msg.edit_text("Stored successfully!", reply_markup=keyboard)

async def get_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.message.from_user.id
    record = collection.find_one({"user_id": user_id})
    if not record:
        await update.message.reply_text("No data found. Use /store to save something first.")
        return

    if record["type"] == "text":
        await update.message.chat.send_action(ChatAction.TYPING)
        await update.message.reply_text(
            f"Your saved text:\n{record['content']}",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("↩ Back", callback_data="back")]])
        )
    elif record["type"] == "photo":
        await update.message.chat.send_action(ChatAction.UPLOAD_PHOTO)
        await update.message.reply_photo(
            record["content"],
            caption="Your saved image:",
            reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("↩ Back", callback_data="back")]])
        )

async def button_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()

    if query.data == "confirm_store":
        await query.edit_message_text("✔️ Your data is stored!")
    elif query.data == "back":
        await query.edit_message_text("Use /get or /store to interact again.")

# Bot Initialization
async def main():
    TOKEN = os.getenv("BOT_TOKEN")
    application = ApplicationBuilder().token(TOKEN).build()

    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("store", store_command))
    application.add_handler(CommandHandler("get", get_command))
    application.add_handler(CallbackQueryHandler(button_handler))

    print("Bot is running...")
    await application.run_polling()

if __name__ == '__main__':
    Thread(target=lambda: flask_app.run(host='0.0.0.0', port=5000)).start()
    asyncio.run(main())
