import os
import logging
import threading
import base64
import requests as req
from flask import Flask
from telegram import Update
from telegram.ext import Application, MessageHandler, CommandHandler, filters, ContextTypes

# ── Logging ───────────────────────────────────────────────────────────────────
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# ── Config ────────────────────────────────────────────────────────────────────
TELEGRAM_TOKEN = os.environ["TELEGRAM_TOKEN"]
GEMINI_API_KEY  = os.environ["GEMINI_API_KEY"]
GEMINI_URL = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash:generateContent?key={GEMINI_API_KEY}"

# ── Flask keep-alive ──────────────────────────────────────────────────────────
flask_app = Flask(__name__)

@flask_app.route("/")
def home():
    return "Ботът работи! ✅"

def run_flask():
    port = int(os.environ.get("PORT", 8080))
    flask_app.run(host="0.0.0.0", port=port)

# ── Gemini via raw HTTP (no protobuf!) ────────────────────────────────────────
PROMPT = """Ти си асистент, който решава изпитни тестове на БЪЛГАРСКИ ЕЗИК.

Правила:
1. За въпроси с множествен избор (А/Б/В/Г или A/B/C/D) — отговаряй САМО с номера и буквата:
   1. А
   2. Б
   (без обяснение, освен ако не е поискано)

2. За въпроси с отворен отговор — давай кратък, точен отговор на БЪЛГАРСКИ.

3. Ако има изчисления — покажи накратко решението.

4. Ако не можеш да прочетеш нещо — напиши [неясно].

Реши ВСИЧКИ въпроси от теста на снимката:"""


def ask_gemini(image_bytes: bytes) -> str:
    image_b64 = base64.b64encode(image_bytes).decode("utf-8")
    payload = {
        "contents": [{
            "parts": [
                {"text": PROMPT},
                {"inline_data": {"mime_type": "image/jpeg", "data": image_b64}}
            ]
        }]
    }
    response = req.post(GEMINI_URL, json=payload, timeout=60)
    response.raise_for_status()
    data = response.json()
    return data["candidates"][0]["content"]["parts"][0]["text"].strip()

# ── Telegram handlers ─────────────────────────────────────────────────────────
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "👋 Здравей! Аз съм бот за решаване на изпити.\n\n"
        "📸 Изпрати ми снимка на теста и ще го реша веднага!\n\n"
        "✅ Работя с тестове на *български език*.",
        parse_mode="Markdown"
    )

async def handle_photo(update: Update, context: ContextTypes.DEFAULT_TYPE):
    thinking_msg = await update.message.reply_text("⏳ Анализирам теста, изчакай малко...")
    try:
        photo_file = await context.bot.get_file(update.message.photo[-1].file_id)
        image_bytes = await photo_file.download_as_bytearray()
        answer = ask_gemini(bytes(image_bytes))
        await thinking_msg.edit_text(
            f"📝 *Отговори:*\n\n{answer}",
            parse_mode="Markdown"
        )
    except Exception as e:
        logger.error(f"Error: {e}")
        await thinking_msg.edit_text(
            "❌ Нещо се обърка. Пробвай да изпратиш по-ясна снимка."
        )

async def handle_text(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "📸 Изпрати ми *снимка* на теста и ще го реша!\n"
        "Използвай /start за помощ.",
        parse_mode="Markdown"
    )

# ── Main ──────────────────────────────────────────────────────────────────────
def main():
    t = threading.Thread(target=run_flask, daemon=True)
    t.start()

    app = Application.builder().token(TELEGRAM_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.PHOTO, handle_photo))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_text))

    logger.info("Ботът стартира ✅")
    app.run_polling(drop_pending_updates=True)

if __name__ == "__main__":
    main()
