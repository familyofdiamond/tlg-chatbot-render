import os
import sqlite3
import logging
import asyncio
from fastapi import FastAPI, Request, Response, HTTPException
from telegram import Update, InlineKeyboardMarkup, InlineKeyboardButton
from telegram.ext import (
    ApplicationBuilder, CommandHandler, MessageHandler,
    CallbackQueryHandler, ContextTypes, filters
)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

BOT_TOKEN = os.environ.get("BOT_TOKEN")
ADMIN_ID = os.environ.get("ADMIN_ID")
WEBHOOK_URL = os.environ.get("WEBHOOK_URL")

if not BOT_TOKEN or not WEBHOOK_URL:
    raise RuntimeError("BOT_TOKEN и WEBHOOK_URL должны быть заданы")

# --- DB setup ---
conn = sqlite3.connect("chat_stats.db", check_same_thread=False)
cursor = conn.cursor()

cursor.execute("""
CREATE TABLE IF NOT EXISTS users (
    user_id INTEGER,
    chat_id INTEGER,
    username TEXT,
    message_count INTEGER DEFAULT 0,
    language TEXT DEFAULT 'ru',
    description TEXT DEFAULT '',
    PRIMARY KEY (user_id, chat_id)
)
""")
conn.commit()

messages = {
    "ru": {
        "start": "👋 Привет! Я собираю статистику сообщений в группе. Нажми /menu.",
        "menu": "📋 Выберите действие:",
        "stats": "📊 Твоя статистика:\n\n👤 Имя: {name}\n💬 Сообщений: {count}\n📝 Описание: {desc}",
        "name_hint": "Напиши команду /setname <твоё имя>",
        "delname_done": "✅ Имя удалено.",
        "desc_hint": "Напиши команду /setdesc <твоё описание>",
        "deldesc_done": "✅ Описание удалено.",
        "welcome": "👋 Добро пожаловать, {name}!\nЯ собираю статистику по участникам.",
        "language_set": "Язык изменён на русский 🇷🇺",
        "contact_admin": "📨 Связь с админом: @{admin_username}",
        "only_admin": "⛔ Только для админа.",
        "no_data": "Нет данных.",
        "top": "🏆 Топ участников:\n\n{top_list}"
    },
    "en": {
        "start": "👋 Hi! I track chat stats. Type /menu.",
        "menu": "📋 Choose an option:",
        "stats": "📊 Your stats:\n\n👤 Name: {name}\n💬 Messages: {count}\n📝 Description: {desc}",
        "name_hint": "Type /setname <your name>",
        "delname_done": "✅ Name deleted.",
        "desc_hint": "Type /setdesc <your description>",
        "deldesc_done": "✅ Description deleted.",
        "welcome": "👋 Welcome, {name}!\nI collect group message stats.",
        "language_set": "Language set to English 🇺🇸",
        "contact_admin": "📨 Contact admin: @{admin_username}",
        "only_admin": "⛔ Admins only.",
        "no_data": "No data.",
        "top": "🏆 Top users:\n\n{top_list}"
    }
}

def get_user_language(user_id, chat_id):
    cursor.execute("SELECT language FROM users WHERE user_id=? AND chat_id=?", (user_id, chat_id))
    row = cursor.fetchone()
    return row[0] if row else "ru"

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    chat_id = update.effective_chat.id
    lang = get_user_language(user_id, chat_id)
    await update.message.reply_text(messages[lang]["start"])

async def setname(update: Update, context: ContextTypes.DEFAULT_TYPE):
    name = " ".join(context.args)
    user_id, chat_id = update.effective_user.id, update.effective_chat.id
    lang = get_user_language(user_id, chat_id)
    if name:
        cursor.execute("INSERT OR IGNORE INTO users (user_id, chat_id) VALUES (?, ?)", (user_id, chat_id))
        cursor.execute("UPDATE users SET username=? WHERE user_id=? AND chat_id=?", (name, user_id, chat_id))
        conn.commit()
        await update.message.reply_text(f"✅ Имя обновлено: {name}")
    else:
        await update.message.reply_text(messages[lang]["name_hint"])

async def delname(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id, chat_id = update.effective_user.id, update.effective_chat.id
    lang = get_user_language(user_id, chat_id)
    cursor.execute("UPDATE users SET username=NULL WHERE user_id=? AND chat_id=?", (user_id, chat_id))
    conn.commit()
    await update.message.reply_text(messages[lang]["delname_done"])

async def setdesc(update: Update, context: ContextTypes.DEFAULT_TYPE):
    description = " ".join(context.args)
    user_id, chat_id = update.effective_user.id, update.effective_chat.id
    lang = get_user_language(user_id, chat_id)
    if description:
        cursor.execute("INSERT OR IGNORE INTO users (user_id, chat_id) VALUES (?, ?)", (user_id, chat_id))
        cursor.execute("UPDATE users SET description=? WHERE user_id=? AND chat_id=?", (description, user_id, chat_id))
        conn.commit()
        await update.message.reply_text(f"✅ Описание обновлено: {description}")
    else:
        await update.message.reply_text(messages[lang]["desc_hint"])

async def deldesc(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id, chat_id = update.effective_user.id, update.effective_chat.id
    lang = get_user_language(user_id, chat_id)
    cursor.execute("UPDATE users SET description='' WHERE user_id=? AND chat_id=?", (user_id, chat_id))
    conn.commit()
    await update.message.reply_text(messages[lang]["deldesc_done"])

async def stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id, chat_id = update.effective_user.id, update.effective_chat.id
    lang = get_user_language(user_id, chat_id)
    cursor.execute("SELECT username, message_count, description FROM users WHERE user_id=? AND chat_id=?", (user_id, chat_id))
    row = cursor.fetchone()
    if row:
        name = row[0] or "не указано"
        count = row[1]
        desc = row[2] or "—"
        await update.message.reply_text(messages[lang]["stats"].format(name=name, count=count, desc=desc))
    else:
        await update.message.reply_text(messages[lang]["no_data"])

async def top(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    user_id = update.effective_user.id
    lang = get_user_language(user_id, chat_id)
    cursor.execute("SELECT username, message_count FROM users WHERE chat_id=? ORDER BY message_count DESC LIMIT 10", (chat_id,))
    rows = cursor.fetchall()
    if not rows:
        await update.message.reply_text(messages[lang]["no_data"])
        return
    top_list = "\n".join([f"{i+1}. {u or '—'} — {c}" for i, (u, c) in enumerate(rows)])
    await update.message.reply_text(messages[lang]["top"].format(top_list=top_list))

async def count_messages(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    chat_id = update.effective_chat.id
    cursor.execute("INSERT OR IGNORE INTO users (user_id, chat_id, username) VALUES (?, ?, ?)", (user.id, chat_id, user.full_name))
    cursor.execute("UPDATE users SET message_count = message_count + 1 WHERE user_id=? AND chat_id=?", (user.id, chat_id))
    conn.commit()

async def menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id, chat_id = update.effective_user.id, update.effective_chat.id
    lang = get_user_language(user_id, chat_id)
    keyboard = [
        [InlineKeyboardButton("📈 Моя статистика", callback_data="stats")],
        [InlineKeyboardButton("🏆 Топ", callback_data="top")],
        [InlineKeyboardButton("📝 Указать имя", callback_data="setname")],
        [InlineKeyboardButton("🗑 Удалить имя", callback_data="delname")],
        [InlineKeyboardButton("🖊 Установить описание", callback_data="setdesc")],
        [InlineKeyboardButton("🗑 Удалить описание", callback_data="deldesc")],
        [InlineKeyboardButton("🌐 Язык: RU 🇷🇺" if lang == "ru" else "🌐 Language: EN 🇺🇸", callback_data="switch_lang")]
    ]
    await update.message.reply_text(messages[lang]["menu"], reply_markup=InlineKeyboardMarkup(keyboard))

async def handle_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    user_id, chat_id = query.from_user.id, query.message.chat.id
    lang = get_user_language(user_id, chat_id)

    if query.data == "stats":
        await stats(update, context)
    elif query.data == "top":
        await top(update, context)
    elif query.data == "setname":
        await query.message.reply_text(messages[lang]["name_hint"])
    elif query.data == "delname":
        await delname(update, context)
    elif query.data == "setdesc":
        await query.message.reply_text(messages[lang]["desc_hint"])
    elif query.data == "deldesc":
        await deldesc(update, context)
    elif query.data == "switch_lang":
        new_lang = "en" if lang == "ru" else "ru"
        cursor.execute("UPDATE users SET language=? WHERE user_id=? AND chat_id=?", (new_lang, user_id, chat_id))
        conn.commit()
        await query.message.reply_text(messages[new_lang]["language_set"])

async def greet_user(update: Update, context: ContextTypes.DEFAULT_TYPE):
    for member in update.message.new_chat_members:
        chat_id = update.effective_chat.id
        user_id = member.id
        cursor.execute("INSERT OR IGNORE INTO users (user_id, chat_id) VALUES (?, ?)", (user_id, chat_id))
        lang = get_user_language(user_id, chat_id)
        keyboard = [[InlineKeyboardButton("🚀 Начать", callback_data="stats")]]
        msg = await update.message.reply_text(
            messages[lang]["welcome"].format(name=member.full_name),
            reply_markup=InlineKeyboardMarkup(keyboard)
        )
        await asyncio.sleep(30)
        try:
            await msg.delete()
        except:
            pass

# --- FastAPI + Webhook ---
app = FastAPI()
application = ApplicationBuilder().token(BOT_TOKEN).build()

application.add_handler(CommandHandler("start", start))
application.add_handler(CommandHandler("setname", setname))
application.add_handler(CommandHandler("delname", delname))
application.add_handler(CommandHandler("setdesc", setdesc))
application.add_handler(CommandHandler("deldesc", deldesc))
application.add_handler(CommandHandler("stats", stats))
application.add_handler(CommandHandler("top", top))
application.add_handler(CommandHandler("menu", menu))
application.add_handler(CallbackQueryHandler(handle_callback))
application.add_handler(MessageHandler(filters.StatusUpdate.NEW_CHAT_MEMBERS, greet_user))
application.add_handler(MessageHandler(filters.TEXT & (~filters.COMMAND), count_messages))

@app.on_event("startup")
async def on_startup():
    await application.initialize()
    await application.start()
    await application.bot.set_webhook(f"{WEBHOOK_URL}/webhook")
    logger.info("Webhook установлен")

@app.on_event("shutdown")
async def on_shutdown():
    await application.stop()
    await application.shutdown()
    logger.info("Бот остановлен")

@app.post("/webhook")
async def webhook_handler(request: Request):
    json_update = await request.json()
    update = Update.de_json(json_update, application.bot)
    await application.update_queue.put(update)
    return Response(status_code=200)
