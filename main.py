import json
import os
import io
import threading
from uuid import uuid4
from flask import Flask, request, jsonify, send_file, abort
from flask_cors import CORS
import requests
from io import BytesIO

from telegram import (
    Update, KeyboardButton, ReplyKeyboardMarkup, ReplyKeyboardRemove, ParseMode, Bot, InputFile
)
from telegram.ext import (
    Updater, CommandHandler, MessageHandler, Filters, ConversationHandler, CallbackContext
)
from telegram.error import TelegramError

import datetime

ID = os.getenv("ID")
BOT_TOKEN = os.getenv("BOT_TOKEN")
GROUP_CHAT_ID = os.getenv("GROUP_CHAT_ID")
DEBUG_USER_ID = os.getenv("DEBUG_USER_ID")
ADMIN = int(os.getenv("ADMIN"))



ASK_POST, ASK_TITLE, ASK_DESCRIPTION, ASK_PHOTO = range(4)
GET_JSON, = range(1)


# --- Flask App ---
app = Flask(__name__)
bot = Bot(token=BOT_TOKEN)
CORS(app, resources={r"/*": {"origins":["https://249-school.uz", "http://249-school.uz"]}})


# Allow only specific website to access this service
# ALLOWED_ORIGINS = ["249-school.uz"]
# CORS(app, origins=ALLOWED_ORIGINS)

# @app.before_request   
# def limit_origin():
#     origin = request.headers.get("Origin")
#     if origin not in ALLOWED_ORIGINS:
#         return jsonify({"error": "Origin not allowed"}), 403

@app.route("/")
def home():
    return "Use /get/<message_id> to fetch a message. Use POST /post to send a message."

@app.route("/get/<int:message_id>")
def get_message(message_id):
    try:
        fwd_msg = bot.forward_message(
            chat_id=DEBUG_USER_ID,
            from_chat_id=GROUP_CHAT_ID,
            message_id=message_id
        )

        response = {
            "message_id": fwd_msg.message_id,
            "date": fwd_msg.date.isoformat(),
            "content": json.loads(fwd_msg.text or fwd_msg.caption),
            "media": {}
        }

        media_fields = ["photo",]
        for media_type in media_fields:
            media = getattr(fwd_msg, media_type, None)
            if media:
                if media_type == "photo":
                    file_id = media[-1].file_id
                else:
                    file_id = media.file_id
                file = bot.get_file(file_id)
                response["media"] = {
                    "file_id": file.file_id,
                    "file_size": getattr(media, "file_size", None),
                    "mime_type": getattr(media, "mime_type", None),
                    "file_path": file.file_path,
                }

        return jsonify(response)

    except TelegramError as e:
        return jsonify({"error": e.message}), 400

@app.route("/get/all")
def get_all():
    try:
        id_msg = bot.forward_message(chat_id=DEBUG_USER_ID, from_chat_id=GROUP_CHAT_ID, message_id=ID)
        
        fwd_msg = bot.forward_message(
            chat_id=DEBUG_USER_ID,
            from_chat_id=GROUP_CHAT_ID,
            message_id= id_msg.text
        )

        # Check if there's a document attached
        if not fwd_msg.document:
            return jsonify({"error": "No document found in the message"}), 400

        # Ensure it is a .json file
        if not fwd_msg.document.file_name.endswith(".json"):
            return jsonify({"error": "The document is not a .json file"}), 400

        # Get the file and download its content
        file = bot.get_file(fwd_msg.document.file_id)
        file_content = file.download_as_bytearray()
        json_data = json.loads(file_content.decode("utf-8"))
        return jsonify(json_data)

    except TelegramError as e:
        return jsonify({"error": e.message}), 400
    except (json.JSONDecodeError, UnicodeDecodeError):
        return jsonify({"error": "Failed to parse the .json file"}), 400

@app.route("/get/img/<string:id>")
def get_img(id):
    try:
 
        # file = bot.get_file(path)
        # file_content = file.download_as_bytearray()
        # data = file_content
        file = bot.get_file(id)
        print(f"img:{file.file_path}")
        response = requests.get(file.file_path, stream=True)
        response.raise_for_status() # Raise an exception for bad status codes (4xx or 5xx)

        # Get the content type from the response headers
        content_type = response.headers.get('Content-Type')

        # Create a BytesIO object from the image content
        image_bytes = BytesIO(response.content)

        return send_file(image_bytes, mimetype=content_type, as_attachment=True, download_name= f"{id}.jpg")

    except requests.exceptions.RequestException as e:
        print(f"Error fetching image: {e}")
        abort(404, description="Image not found or unable to fetch from the provided URL.")
    except Exception as e:
        print(f"An unexpected error occurred: {e}")
        abort(500, description="An internal server error occurred.")


    except TelegramError as e:
        return jsonify({"error": e.message}), 400
    except (json.JSONDecodeError, UnicodeDecodeError):
        return jsonify({"error": "Failed to parse the .json file"}), 400


@app.route("/post", methods=["POST"])
def send_message():
    data = request.get_json()
    if not data:
        return jsonify({"error": "No JSON payload received."}), 400

    try:
        bot.send_message(chat_id=GROUP_CHAT_ID, text=data)

        return jsonify({"status": "Message sent"}), 200

    except TelegramError as e:
        return jsonify({"error": e.message}), 400

# --- Helper Functions ---
def load_json_data():
    try:
        id_msg = bot.forward_message(chat_id=DEBUG_USER_ID, from_chat_id=GROUP_CHAT_ID, message_id=ID)
        fwd_msg = bot.forward_message(chat_id=DEBUG_USER_ID, from_chat_id=GROUP_CHAT_ID, message_id=int(id_msg.text))
        if not fwd_msg.document or not fwd_msg.document.file_name.endswith(".json"):
            return []
        file = fwd_msg.document.get_file()
        content = file.download_as_bytearray()
        return json.loads(content.decode("utf-8"))
    except Exception as e:
        print("Error loading JSON:", e)
        return []

def update_json_file(data):
    json_str = json.dumps(data, indent=2)
    byte_stream = io.BytesIO(json_str.encode('utf-8'))
    byte_stream.name = "data.json"
    return byte_stream

# --- Telegram Bot Handlers ---
def start(update: Update, context: CallbackContext):
   if ADMIN == 0 or update.message.chat_id == ADMIN:
        keyboard = [[KeyboardButton("Да"), KeyboardButton("Нет")]]
        update.message.reply_text("Хотите опубликовать событие?",
        reply_markup=ReplyKeyboardMarkup(keyboard, one_time_keyboard=True)
        )
        return ASK_POST

def ask_post(update: Update, context: CallbackContext):
    if update.message.text.lower() == "да":
        update.message.reply_text("Отлично! Как называется мероприятие?", reply_markup=ReplyKeyboardRemove())
        return ASK_TITLE
    update.message.reply_text("Хорошо, событие не будет опубликовано.", reply_markup=ReplyKeyboardRemove())
    return ConversationHandler.END

def ask_title(update: Update, context: CallbackContext):
    context.user_data["title"] = update.message.text
    update.message.reply_text("Пожалуйста, дайте описание события.")
    return ASK_DESCRIPTION

def ask_description(update: Update, context: CallbackContext):
    context.user_data["description"] = update.message.text
    update.message.reply_text("Теперь, пожалуйста, отправьте фотографию (не как файл, а как изображение).")
    return ASK_PHOTO

def ask_photo(update: Update, context: CallbackContext):
    if not update.message.photo:
        update.message.reply_text("Это похоже на файл. Пожалуйста, отправьте это как фотографию.")
        return ASK_PHOTO

    photo_file = update.message.photo[-1].get_file()
    file_id = str(update.message.message_id)
    photo_path = f"photo_{file_id}.jpg"
    photo_file.download(photo_path)

    sent = context.bot.send_photo(
        chat_id=GROUP_CHAT_ID,
        photo=open(photo_path, 'rb'),
        caption=f"*{context.user_data['title']}*\n\n{context.user_data['description']}",
        parse_mode=ParseMode.MARKDOWN
    )

    events = load_json_data()
    new_event = {
        "t": context.user_data["title"],
        "d": context.user_data["description"],
        "i": sent.photo[-1].file_id,
        "w": datetime.datetime.now().strftime('%Y-%m-%d')
    }
    events.append(new_event)
    updated_json = update_json_file(events)
    new_json = context.bot.send_document(chat_id=GROUP_CHAT_ID, document=InputFile(updated_json))
    context.bot.edit_message_text(chat_id= GROUP_CHAT_ID, message_id = ID, text = new_json.message_id)
    update.message.reply_text("Событие успешно опубликовано!")
    os.remove(photo_path)
    return ConversationHandler.END

def cancel(update: Update, context: CallbackContext):
   if ADMIN == 0 or update.message.chat_id == ADMIN:
        update.message.reply_text("Создание мероприятия отменено.", reply_markup=ReplyKeyboardRemove())
        return ConversationHandler.END


# --- Start Telegram Bot in Thread ---
def help(update: Update, context: CallbackContext):
   if ADMIN == 0 or update.message.chat_id == ADMIN:
        update.message.reply_text("Чтобы опубликовать новое событие: /start\nЧтобы редактировать события: /edit")
def edit(update: Update, context: CallbackContext):
   if ADMIN == 0 or update.message.chat_id == ADMIN:
        update.message.reply_text(f"{load_json_data()}")
        return GET_JSON
def get_json(update: Update, context: CallbackContext):
    print(f"new value: {update.message.text}")
    new_json = context.bot.send_document(chat_id = GROUP_CHAT_ID, document= update_json_file(json.loads(update.message.text)))
    context.bot.edit_message_text(chat_id= GROUP_CHAT_ID, message_id = ID, text = new_json.message_id)
    update.message.reply_text("Успешно обновлено!")
    return ConversationHandler.END
    
def run_telegram_bot():
    updater = Updater(token=BOT_TOKEN, use_context=True)
    dp = updater.dispatcher
    
    conv_handler = ConversationHandler(
        entry_points=[CommandHandler("start", start)],
        states={
            ASK_POST: [MessageHandler(Filters.text & ~Filters.command, ask_post)],
            ASK_TITLE: [MessageHandler(Filters.text & ~Filters.command, ask_title)],
            ASK_DESCRIPTION: [MessageHandler(Filters.text & ~Filters.command, ask_description)],
            ASK_PHOTO: [MessageHandler(Filters.photo, ask_photo)],
        },
        fallbacks=[CommandHandler("cancel", cancel)],
    )
    edit_handler = ConversationHandler(
        entry_points=[CommandHandler("edit", edit)],
        states={
            GET_JSON: [MessageHandler(Filters.text & ~Filters.command, get_json)],

        },
        fallbacks=[CommandHandler("cancel", cancel)],
    )
    dp.add_handler(CommandHandler("help", help))

    dp.add_handler(conv_handler)
    dp.add_handler(edit_handler)

    updater.start_polling()
    updater.idle()

# --- Main ---
if __name__ == "__main__":
    threading.Thread(target=run_telegram_bot).start()
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
