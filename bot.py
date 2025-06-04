import os
import logging
import sqlite3
import asyncio
from fastapi import FastAPI, Request
from telegram import Update, InlineKeyboardMarkup, InlineKeyboardButton
from telegram.ext import (
    Application, CommandHandler, MessageHandler,
    CallbackQueryHandler, ContextTypes, filters
)

# Логирование
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Переменные окружения
BOT_TOKEN = os.environ.get("BOT_TOKEN")
ADMIN_ID = os.environ.get("ADMIN_ID")
WEBHOOK_URL = os.environ.get("WEBHOOK_URL")  # Пример: https://your-app.onrender.com

# БД
conn = sqlite3.connect("chat_stats.db", check_same_thread=False)
cursor = conn.cursor()
cursor.execute("""CREATE TABLE IF NOT EXISTS users (
    user_id INTEGER PRIMARY KEY,
    username TEXT,
    message_count INTEGER DEFAULT 0,
    language TEXT DEFAULT 'ru'
)""")
conn.commit()

# Языковые сообщения
messages = {
    "ru": {
        "start": "👋 Привет! Я собираю статистику сообщений в группе. Нажми /menu, чтобы открыть меню.",
        "menu": "📋 Выберите действие:",
        "stats": "📊 Твоя статистика:\n\n👤 Имя: {name}\n💬 Сообщений: {count}",
        "name_hint": "Напиши команду /setname <твоё имя>",
        "welcome": "👋 Добро пожаловать, {name}!",
        "language_set": "Язык изменён на русский 🇷🇺",
        "contact_admin": "📨 Связь с админом: @{admin_username}",
    },
    "en": {
        "start": "👋 Hi! I track chat stats. Type /menu to open the menu.",
        "menu": "📋 Choose an option:",
        "stats": "📊 Your stats:\n\n👤 Name: {name}\n💬 Messages: {count}",
        "name_hint": "Type /setname <your name>",
        "welcome": "👋 Welcome, {name}!",
        "language_set": "Language set to English 🇺🇸",
        "contact_admin": "📨 Contact admin: @{admin_username}",
    }
}

# Получить язык пользователя
def get_user_language(user_id):
    cursor.execute("SELECT language FROM users WHERE user_id = ?", (user_id,))
    row = cursor.fetchone()
    return row[0] if row else "ru"

# Команды
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    lang = get_user_language(update.effective_user.id)
    await update.message.reply_text(messages[lang]["start"])

async def setname(update: Update, context: ContextTypes.DEFAULT_TYPE):
    lang = get_user_language(update.effective_user.id)
    name = " ".join(context.args)
    user_id = update.effective_user.id
    if name:
        cursor.execute("INSERT OR IGNORE INTO users (user_id) VALUES (?)", (user_id,))
        cursor.execute("UPDATE users SET username = ? WHERE user_id = ?", (name, user_id))
        conn.commit()
        await update.message.reply_text(f"✅ Имя обновлено: {name}")
    else:
        await update.message.reply_text(messages[lang]["name_hint"])

async def stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    lang = get_user_language(user_id)
    cursor.execute("SELECT username, message_count FROM users WHERE user_id = ?", (user_id,))
    row = cursor.fetchone()
    if row:
        name = row[0] or "не указано"
        count = row[1]
        msg = messages[lang]["stats"].format(name=name, count=count)
        await update.message.reply_text(msg)
    else:
        await update.message.reply_text("Нет данных.")

async def count_messages(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    cursor.execute("INSERT OR IGNORE INTO users (user_id, username) VALUES (?, ?)", (user.id, user.full_name))
    cursor.execute("UPDATE users SET message_count = message_count + 1 WHERE user_id = ?", (user.id,))
    conn.commit()

async def menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    lang = get_user_language(update.effective_user.id)
    keyboard = [
        [InlineKeyboardButton("📈 Моя статистика", callback_data="stats")],
        [InlineKeyboardButton("📝 Указать имя", callback_data="setname")],
        [InlineKeyboardButton("📬 Связаться с админом", callback_data="contact")],
        [InlineKeyboardButton("🌐 Язык: RU 🇷🇺", callback_data="lang_en") if lang == "ru"
         else InlineKeyboardButton("🌐 Language: EN 🇺🇸", callback_data="lang_ru")]
    ]
    await update.message.reply_text(messages[lang]["menu"], reply_markup=InlineKeyboardMarkup(keyboard))

async def handle_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user_id = query.from_user.id
    lang = get_user_language(user_id)

    if query.data == "stats":
        cursor.execute("SELECT username, message_count FROM users WHERE user_id = ?", (user_id,))
        row = cursor.fetchone()
        if row:
            name = row[0] or "не указано"
            count = row[1]
            await query.message.reply_text(messages[lang]["stats"].format(name=name, count=count))
    elif query.data == "setname":
        await query.message.reply_text(messages[lang]["name_hint"])
    elif query.data == "contact":
        admin_username = "your_admin_username"  # Замените на актуальное имя
        await query.message.reply_text(messages[lang]["contact_admin"].format(admin_username=admin_username))
    elif query.data.startswith("lang_"):
        new_lang = query.data[-2:]
        cursor.execute("UPDATE users SET language = ? WHERE user_id = ?", (new_lang, user_id))
        conn.commit()
        await query.message.reply_text(messages[new_lang]["language_set"])

async def greet_user(update: Update, context: ContextTypes.DEFAULT_TYPE):
    for member in update.message.new_chat_members:
        lang = get_user_language(member.id)
        msg = await update.message.reply_text(
            messages[lang]["welcome"].format(name=member.full_name)
        )
        await asyncio.sleep(30)
        try:
            await msg.delete()
        except:
            pass

# === Webhook через FastAPI ===

bot_app = FastAPI()
application = Application.builder().token(BOT_TOKEN).build()

application.add_handler(CommandHandler("start", start))
application.add_handler(CommandHandler("setname", setname))
application.add_handler(CommandHandler("stats", stats))
application.add_handler(CommandHandler("menu", menu))
application.add_handler(CallbackQueryHandler(handle_callback))
application.add_handler(MessageHandler(filters.TEXT & (~filters.COMMAND), count_messages))
application.add_handler(MessageHandler(filters.StatusUpdate.NEW_CHAT_MEMBERS, greet_user))

@bot_app.on_event("startup")
async def on_startup():
    await application.initialize()
    await application.start()
    await application.bot.set_webhook(url=WEBHOOK_URL)
    logging.info("Webhook установлен")

@bot_app.post("/")
async def receive_update(request: Request):
    data = await request.json()
    update = Update.de_json(data, application.bot)
    await application.process_update(update)
    return {"ok": True}
