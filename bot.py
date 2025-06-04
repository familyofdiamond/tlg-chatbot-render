import logging
import sqlite3
import os
import asyncio
from telegram import (
    Update, InlineKeyboardMarkup, InlineKeyboardButton
)
from telegram.ext import (
    ApplicationBuilder, CommandHandler, MessageHandler,
    CallbackQueryHandler, ContextTypes, filters
)

# Лог
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Окружение
BOT_TOKEN = os.environ.get("BOT_TOKEN")
ADMIN_ID = os.environ.get("ADMIN_ID")  # Строка с ID админа

# БД
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

# Языковые шаблоны
messages = {
    "ru": {
        "start": "👋 Привет! Я собираю статистику сообщений в группе. Нажми /menu, чтобы открыть меню.",
        "menu": "📋 Выберите действие:",
        "stats": "📊 Твоя статистика:\n\n👤 Имя: {name}\n💬 Сообщений: {count}\n📝 Описание: {desc}",
        "name_hint": "Напиши команду /setname <твоё имя>",
        "desc_hint": "Напиши команду /setdesc <текст описания>",
        "welcome": "👋 Добро пожаловать, {name}!\nЯ собираю статистику по участникам.",
        "language_set": "Язык изменён на русский 🇷🇺",
        "contact_admin": "📨 Связь с админом: @{admin_username}",
        "delname_done": "✅ Имя удалено.",
        "deldesc_done": "✅ Описание удалено.",
    },
    "en": {
        "start": "👋 Hi! I track chat stats. Type /menu to open the menu.",
        "menu": "📋 Choose an option:",
        "stats": "📊 Your stats:\n\n👤 Name: {name}\n💬 Messages: {count}\n📝 Description: {desc}",
        "name_hint": "Type /setname <your name>",
        "desc_hint": "Type /setdesc <description text>",
        "welcome": "👋 Welcome, {name}!\nI collect group message stats.",
        "language_set": "Language set to English 🇺🇸",
        "contact_admin": "📨 Contact admin: @{admin_username}",
        "delname_done": "✅ Name deleted.",
        "deldesc_done": "✅ Description deleted.",
    }
}

# Получение языка
def get_user_language(user_id):
    cursor.execute("SELECT language FROM users WHERE user_id = ?", (user_id,))
    row = cursor.fetchone()
    return row[0] if row else "ru"

# Установить язык
async def set_language(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    lang = context.args[0].lower() if context.args else "ru"
    if lang not in ["ru", "en"]:
        await update.message.reply_text("Available languages: ru, en")
        return
    cursor.execute("INSERT OR IGNORE INTO users (user_id) VALUES (?)", (user_id,))
    cursor.execute("UPDATE users SET language = ? WHERE user_id = ?", (lang, user_id))
    conn.commit()
    await update.message.reply_text(messages[lang]["language_set"])

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

async def delname(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    lang = get_user_language(user_id)
    cursor.execute("UPDATE users SET username = NULL WHERE user_id = ?", (user_id,))
    conn.commit()
    await update.message.reply_text(messages[lang]["delname_done"])

async def setdesc(update: Update, context: ContextTypes.DEFAULT_TYPE):
    lang = get_user_language(update.effective_user.id)
    user_id = update.effective_user.id
    desc = " ".join(context.args)
    if not desc:
        await update.message.reply_text(messages[lang]["desc_hint"])
        return
    cursor.execute("INSERT OR IGNORE INTO users (user_id) VALUES (?)", (user_id,))
    cursor.execute("UPDATE users SET description = ? WHERE user_id = ?", (desc, user_id))
    conn.commit()
    await update.message.reply_text(f"✅ Описание обновлено: {desc}")

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
        await update.message.reply_text("Нет данных.")

async def fullstats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if str(update.effective_user.id) != ADMIN_ID:
        await update.message.reply_text("⛔ Только для админа.")
        return
    cursor.execute("SELECT username, message_count, description FROM users ORDER BY message_count DESC")
    stats = cursor.fetchall()
    text = "\n".join([f"{u or 'Без имени'} — {c} сообщений — {d or '—'}" for u, c, d in stats])
    await update.message.reply_text(f"📊 Общая статистика:\n{text}")

async def count_messages(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    cursor.execute("INSERT OR IGNORE INTO users (user_id, username) VALUES (?, ?)", (user.id, user.full_name))
    cursor.execute("UPDATE users SET message_count = message_count + 1 WHERE user_id = ?", (user.id,))
    conn.commit()

# Меню
async def menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    lang = get_user_language(update.effective_user.id)
    keyboard = [
        [InlineKeyboardButton("📈 Моя статистика", callback_data="stats")],
        [InlineKeyboardButton("📝 Указать имя", callback_data="setname")],
        [InlineKeyboardButton("📝 Указать описание", callback_data="setdesc")],
        [InlineKeyboardButton("🗑️ Удалить имя", callback_data="delname")],
        [InlineKeyboardButton("🗑️ Удалить описание", callback_data="deldesc")],
        [InlineKeyboardButton("📬 Связаться с админом", callback_data="contact")],
        [InlineKeyboardButton("🌐 Язык: RU 🇷🇺", callback_data="lang_en") if lang == "ru"
         else InlineKeyboardButton("🌐 Language: EN 🇺🇸", callback_data="lang_ru")]
    ]
    await update.message.reply_text(
        messages[lang]["menu"],
        reply_markup=InlineKeyboardMarkup(keyboard)
    )

# Обработка кнопок
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

    elif query.data == "setdesc":
        await query.message.reply_text(messages[lang]["desc_hint"])

    elif query.data == "delname":
        cursor.execute("UPDATE users SET username = NULL WHERE user_id = ?", (user_id,))
        conn.commit()
        await query.message.reply_text(messages[lang]["delname_done"])

    elif query.data == "deldesc":
        cursor.execute("UPDATE users SET description = '' WHERE user_id = ?", (user_id,))
        conn.commit()
        await query.message.reply_text(messages[lang]["deldesc_done"])

    elif query.data == "contact":
        admin_username
