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
ADMIN_ID = os.environ.get("ADMIN_ID")  # как строка

if not BOT_TOKEN:
    raise RuntimeError("BOT_TOKEN не задан в окружении")

# DB
conn = sqlite3.connect("chat_stats.db", check_same_thread=False)
cursor = conn.cursor()
cursor.execute("""
CREATE TABLE IF NOT EXISTS users (
    user_id INTEGER PRIMARY KEY,
    username TEXT,
    message_count INTEGER DEFAULT 0,
    language TEXT DEFAULT 'ru',
    description TEXT DEFAULT ''
)
""")
conn.commit()

messages = {
    "ru": {
        "start": "👋 Привет! Я собираю статистику сообщений в группе. Нажми /menu, чтобы открыть меню.",
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
        "no_data": "Нет данных."
    },
    "en": {
        "start": "👋 Hi! I track chat stats. Type /menu to open the menu.",
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
        "no_data": "No data."
    }
}

def get_user_language(user_id):
    cursor.execute("SELECT language FROM users WHERE user_id = ?", (user_id,))
    row = cursor.fetchone()
    return row[0] if row else "ru"

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

async def delname(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    lang = get_user_language(user_id)
    cursor.execute("UPDATE users SET username = NULL WHERE user_id = ?", (user_id,))
    conn.commit()
    await update.message.reply_text(messages[lang]["delname_done"])

async def setdesc(update: Update, context: ContextTypes.DEFAULT_TYPE):
    lang = get_user_language(update.effective_user.id)
    description = " ".join(context.args)
    user_id = update.effective_user.id
    if description:
        cursor.execute("INSERT OR IGNORE INTO users (user_id) VALUES (?)", (user_id,))
        cursor.execute("UPDATE users SET description = ? WHERE user_id = ?", (description, user_id))
        conn.commit()
        await update.message.reply_text(f"✅ Описание обновлено: {description}")
    else:
        await update.message.reply_text(messages[lang]["desc_hint"])

async def deldesc(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    lang = get_user_language(user_id)
    cursor.execute("UPDATE users SET description = '' WHERE user_id = ?", (user_id,))
    conn.commit()
    await update.message.reply_text(messages[lang]["deldesc_done"])

async def stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    lang = get_user_language(user_id)
    cursor.execute("SELECT username, message_count, description FROM users WHERE user_id = ?", (user_id,))
    row = cursor.fetchone()
    if row:
        name = row[0] or "не указано"
        count = row[1]
        desc = row[2] or "—"
        msg = messages[lang]["stats"].format(name=name, count=count, desc=desc)
        await update.message.reply_text(msg)
    else:
        await update.message.reply_text(messages[lang]["no_data"])

async def fullstats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if str(update.effective_user.id) != ADMIN_ID:
        lang = get_user_language(update.effective_user.id)
        await update.message.reply_text(messages[lang]["only_admin"])
        return
    cursor.execute("SELECT username, message_count, description FROM users ORDER BY message_count DESC")
    stats_data = cursor.fetchall()
    text = "\n".join([f"{u or 'Без имени'} — {c} сообщений — {d or '—'}" for u, c, d in stats_data])
    await update.message.reply_text(f"📊 Общая статистика:\n{text}")

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
        [InlineKeyboardButton("🗑 Удалить имя", callback_data="delname")],
        [InlineKeyboardButton("🖊 Установить описание", callback_data="setdesc")],
        [InlineKeyboardButton("🗑 Удалить описание", callback_data="deldesc")],
        [InlineKeyboardButton("📬 Связаться с админом", callback_data="contact")],
        [InlineKeyboardButton("🌐 Язык: RU 🇷🇺", callback_data="lang_en") if lang == "ru"
         else InlineKeyboardButton("🌐 Language: EN 🇺🇸", callback_data="lang_ru")]
    ]
    await update.message.reply_text(
        messages[lang]["menu"],
        reply_markup=InlineKeyboardMarkup(keyboard)
    )

async def handle_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    user_id = query.from_user.id
    lang = get_user_language(user_id)
    await query.answer()

    if query.data == "stats":
        cursor.execute("SELECT username, message_count, description FROM users WHERE user_id = ?", (user_id,))
        row = cursor.fetchone()
        if row:
            name = row[0] or "не указано"
            count = row[1]
            desc = row[2] or "—"
            msg = messages[lang]["stats"].format(name=name, count=count, desc=desc)
            await query.message.reply_text(msg)

    elif query.data == "setname":
        await query.message.reply_text(messages[lang]["name_hint"])

    elif query.data == "delname":
        cursor.execute("UPDATE users SET username = NULL WHERE user_id = ?", (user_id,))
        conn.commit()
        await query.message.reply_text(messages[lang]["delname_done"])

    elif query.data == "setdesc":
        await query.message.reply_text(messages[lang]["desc_hint"])

    elif query.data == "deldesc":
        cursor.execute("UPDATE users SET description = '' WHERE user_id = ?", (user_id,))
        conn.commit()
        await query.message.reply_text(messages[lang]["deldesc_done"])

    elif query.data == "contact":
        admin_username = "your_admin_username"  # Замените
        await query.message.reply_text(messages[lang]["contact_admin"].format(admin_username=admin_username))

    elif query.data.startswith("lang_"):
        new_lang = query.data[-2:]
        cursor.execute("UPDATE users SET language = ? WHERE user_id = ?", (new_lang, user_id))
        conn.commit()
        await query.message.reply_text(messages[new_lang]["language_set"])

async def greet_user(update: Update, context: ContextTypes.DEFAULT_TYPE):
    for member in update.message.new_chat_members:
        user_id = member.id
        lang = get_user_language(user_id)
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

# FastAPI app
app = FastAPI()
application = ApplicationBuilder().token(BOT_TOKEN).build()

application.add_handler(CommandHandler("start", start))
application.add_handler(CommandHandler("setname", setname))
application.add_handler(CommandHandler("delname", delname))
application.add_handler(CommandHandler("setdesc", setdesc))
application.add_handler(CommandHandler("deldesc", deldesc))
application.add_handler(CommandHandler("stats", stats))
application.add_handler(CommandHandler("fullstats", fullstats))
application.add_handler(CommandHandler("menu", menu))
application.add_handler(CallbackQueryHandler(handle_callback))
application.add_handler(MessageHandler(filters.StatusUpdate.NEW_CHAT_MEMBERS, greet_user))
application.add_handler(MessageHandler(filters.TEXT & (~filters.COMMAND), count_messages))

@app.on_event("shutdown")
async def on_shutdown():
    await application.stop()
    await application.shutdown()
    logger.info("Бот остановлен")

@app.post("/webhook")
async def webhook_handler(request: Request):
    try:
        json_update = await request.json()
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid request body")

    update = Update.de_json(json_update, application.bot)
    await application.update_queue.put(update)
    return Response(status_code=200)
