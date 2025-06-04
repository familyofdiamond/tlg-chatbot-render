import logging
import sqlite3
import os
from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, ContextTypes, filters

# Настройка логов
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Получаем токен и ID админа из переменных окружения
BOT_TOKEN = os.environ.get("BOT_TOKEN")
ADMIN_ID = os.environ.get("ADMIN_ID")

# Подключение к SQLite
conn = sqlite3.connect("chat_stats.db", check_same_thread=False)
cursor = conn.cursor()
cursor.execute("CREATE TABLE IF NOT EXISTS users (user_id INTEGER, username TEXT, message_count INTEGER)")
conn.commit()

# Команды
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Привет! Я бот для сбора статистики чата.")

async def setname(update: Update, context: ContextTypes.DEFAULT_TYPE):
    username = " ".join(context.args)
    user_id = update.effective_user.id
    if username:
        cursor.execute("UPDATE users SET username = ? WHERE user_id = ?", (username, user_id))
        conn.commit()
        await update.message.reply_text(f"Имя обновлено на: {username}")
    else:
        await update.message.reply_text("Пожалуйста, укажи имя: /setname <имя>")

async def stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    cursor.execute("SELECT username, message_count FROM users WHERE user_id = ?", (user_id,))
    result = cursor.fetchone()
    if result:
        await update.message.reply_text(f"Имя: {result[0] or 'не указано'}\nСообщений: {result[1]}")
    else:
        await update.message.reply_text("Нет данных по тебе.")

async def fullstats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if str(update.effective_user.id) != ADMIN_ID:
        await update.message.reply_text("Только для админа.")
        return
    cursor.execute("SELECT username, message_count FROM users ORDER BY message_count DESC")
    stats = cursor.fetchall()
    text = "\n".join([f"{u or 'Без имени'} — {c} сообщений" for u, c in stats])
    await update.message.reply_text(f"📊 Общая статистика:\n{text}")

async def count_messages(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    user_id = user.id
    username = user.username or user.full_name or "неизвестный"

    cursor.execute("SELECT message_count FROM users WHERE user_id = ?", (user_id,))
    result = cursor.fetchone()
    if result:
        cursor.execute("UPDATE users SET message_count = message_count + 1 WHERE user_id = ?", (user_id,))
    else:
        cursor.execute("INSERT INTO users (user_id, username, message_count) VALUES (?, ?, 1)", (user_id, username))
    conn.commit()

if __name__ == "__main__":
    app = ApplicationBuilder().token(BOT_TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("setname", setname))
    app.add_handler(CommandHandler("stats", stats))
    app.add_handler(CommandHandler("fullstats", fullstats))
    app.add_handler(MessageHandler(filters.TEXT & (~filters.COMMAND), count_messages))

    logger.info("Бот запущен...")
    app.run_polling()
