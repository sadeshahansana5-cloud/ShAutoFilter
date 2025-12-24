import logging
import sqlite3
import uuid
import asyncio
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    ApplicationBuilder, ContextTypes, CommandHandler, MessageHandler, CallbackQueryHandler, filters,
)

# --- සැකසුම් (Configuration) ---
BOT_TOKEN = "ඔබේ_BOT_TOKEN_එක" 
ADMIN_ID = ඔබේ_TELEGRAM_ID_එක 
AUTHORIZED_GROUP_ID = ඔබේ_GROUP_ID_එක # -100 සමඟ ආරම්භ වන අංකය
DB_NAME = "bot_database.db"
RESULTS_PER_PAGE = 5
MAINTENANCE_MODE = False 

# අලුත් ගොනු තාවකාලිකව තබා ගැනීමට
pending_files = []

logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)

# --- Database functions ---
def init_db():
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute('''CREATE TABLE IF NOT EXISTS files 
                      (id TEXT PRIMARY KEY, file_id TEXT, file_name TEXT, file_type TEXT)''')
    cursor.execute('''CREATE TABLE IF NOT EXISTS users (user_id INTEGER PRIMARY KEY)''')
    conn.commit(); conn.close()

def add_user(user_id):
    conn = sqlite3.connect(DB_NAME); cursor = conn.cursor()
    cursor.execute("INSERT OR IGNORE INTO users VALUES (?)", (user_id,))
    conn.commit(); conn.close()

def get_all_users():
    conn = sqlite3.connect(DB_NAME); cursor = conn.cursor()
    cursor.execute("SELECT user_id FROM users")
    users = [row[0] for row in cursor.fetchall()]; conn.close()
    return users

def add_file(uid, f_id, f_name, f_type):
    conn = sqlite3.connect(DB_NAME); cursor = conn.cursor()
    cursor.execute("INSERT INTO files VALUES (?, ?, ?, ?)", (uid, f_id, f_name, f_type))
    conn.commit(); conn.close()

def search_in_db(query):
    conn = sqlite3.connect(DB_NAME); cursor = conn.cursor()
    cursor.execute("SELECT id, file_name FROM files WHERE file_name LIKE ?", ('%' + query + '%',))
    results = cursor.fetchall(); conn.close()
    return results

def get_file_by_id(uid):
    conn = sqlite3.connect(DB_NAME); cursor = conn.cursor()
    cursor.execute("SELECT file_id, file_name, file_type FROM files WHERE id = ?", (uid,))
    result = cursor.fetchone(); conn.close()
    return result

# --- Utility Functions ---
async def delete_msg(context, chat_id, message_id):
    await asyncio.sleep(600) # තත්පර 600 (විනාඩි 10)
    try: await context.bot.delete_message(chat_id=chat_id, message_id=message_id)
    except: pass

def get_readable_size(size_in_bytes):
    if not size_in_bytes: return "Unknown"
    for unit in ['B', 'KB', 'MB', 'GB']:
        if size_in_bytes < 1024: return f"{size_in_bytes:.2f} {unit}"
        size_in_bytes /= 1024

# --- Auto Broadcast for Updates ---
async def send_new_updates(context):
    global pending_files
    if len(pending_files) < 5: return
    users = get_all_users()
    msg_text = "✨ **NEW MOVIES ADDED!** ✨\n\n"
    for f in pending_files:
        msg_text += f"🎬 **Name:** {f['name']}\n⚖️ **Size:** {f['size']}\n\n"
    msg_text += "🔍 සෙවීමට අපගේ සමූහය (Group) භාවිතා කරන්න!\n🎬SH_Filte_Bot🎬"
    for u_id in users:
        try: await context.bot.send_message(chat_id=u_id, text=msg_text, parse_mode="Markdown")
        except: pass
    pending_files = []

# --- Security: Check Authorization ---
def is_authorized(update: Update):
    if update.effective_user.id == ADMIN_ID: return True
    if update.effective_chat.id == AUTHORIZED_GROUP_ID: return True
    return False

# --- Bot Handlers ---

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not is_authorized(update):
        await update.message.reply_text("❌ මාව භාවිතා කළ හැක්කේ අපගේ නිල සමූහය (Group) තුළ පමණි.")
        return
    
    user_id = update.effective_user.id
    add_user(user_id)
    keyboard = [
        [InlineKeyboardButton("📜 Commands", callback_data="list_cmd"), 
         InlineKeyboardButton("📊 Stats", callback_data="show_stats")],
        [InlineKeyboardButton("🔍 Help", callback_data="help_cmd")]
    ]
    text = "👋 සාදරයෙන් පිළිගනිමු!\nගොනු සෙවීමට නම Type කරන්න."
    if update.message: await update.message.reply_text(text, reply_markup=InlineKeyboardMarkup(keyboard))
    else: await update.callback_query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard))

async def list_commands(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    cmd_text = (
        "📜 **Command List**\n\n"
        "👤 **User Commands:**\n"
        "▫️ /start - Bot ආරම්භ කිරීමට\n"
        "▫️ /id - ඔබේ ID එක ලබා ගැනීමට\n"
        "▫️ /info - Bot පිළිබඳ විස්තර\n"
        "▫️ /help - උදවු ලබා ගැනීමට\n\n"
        "⚙️ **Admin Commands:**\n"
        "▫️ /broadcast - පණිවිඩ යැවීමට\n"
        "▫️ /maintenance on/off - නඩත්තු මාදිලිය\n"
        "▫️ /stats - දත්ත පරීක්ෂාව"
    )
    keyboard = [[InlineKeyboardButton("🔙 Back", callback_data="back")]]
    await query.edit_message_text(cmd_text, reply_markup=InlineKeyboardMarkup(keyboard), parse_mode="Markdown")

async def index_files(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = update.message or update.channel_post
    if not msg: return

    f_id, f_name, f_type, f_size = None, "Unknown", None, 0
    if msg.document: f_id, f_name, f_type, f_size = msg.document.file_id, msg.document.file_name, 'doc', msg.document.file_size
    elif msg.video: f_id, f_name, f_type, f_size = msg.video.file_id, msg.video.file_name, 'video', msg.video.file_size
    
    if f_id:
        uid = str(uuid.uuid4())[:8]
        clean_name = msg.caption if msg.caption else f_name
        add_file(uid, f_id, clean_name, f_type)
        pending_files.append({'name': clean_name, 'size': get_readable_size(f_size)})
        if len(pending_files) >= 5: await send_new_updates(context)

async def search_files(update: Update, context: ContextTypes.DEFAULT_TYPE, page=0):
    if not is_authorized(update): return
    global MAINTENANCE_MODE
    if MAINTENANCE_MODE and update.effective_user.id != ADMIN_ID:
        await update.message.reply_text("⚠️ Bot දැනට අලුත්වැඩියා කටයුත්තක් සඳහා නතර කර ඇත.")
        return

    query_text = update.message.text.strip() if update.message else context.user_data.get('q')
    if not query_text or len(query_text) < 3: return
    context.user_data['q'] = query_text
    
    results = search_in_db(query_text)
    if not results: return

    start_idx, end_idx = page * RESULTS_PER_PAGE, (page + 1) * RESULTS_PER_PAGE
    keyboard = [[InlineKeyboardButton(f"📂 {res[1][:30]}", callback_data=f"get_{res[0]}")] for res in results[start_idx:end_idx]]
    nav = []
    if page > 0: nav.append(InlineKeyboardButton("⬅️ Back", callback_data=f"pg_{page-1}"))
    if end_idx < len(results): nav.append(InlineKeyboardButton("Next ➡️", callback_data=f"pg_{page+1}"))
    if nav: keyboard.append(nav)
    
    if update.callback_query: await update.callback_query.edit_message_text(f"🔎 '{query_text}' සඳහා ප්‍රතිඵල:", reply_markup=InlineKeyboardMarkup(keyboard))
    else: await update.message.reply_text(f"🔎 '{query_text}' සඳහා ප්‍රතිඵල:", reply_markup=InlineKeyboardMarkup(keyboard))

async def handle_callbacks(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    if query.data.startswith("pg_"): await search_files(update, context, page=int(query.data.split("_")[1]))
    elif query.data == "list_cmd": await list_commands(update, context)
    elif query.data == "back": await start(update, context)
    elif query.data == "show_stats":
        conn = sqlite3.connect(DB_NAME); cur = conn.cursor()
        cur.execute("SELECT COUNT(*) FROM files"); f_c = cur.fetchone()[0]
        cur.execute("SELECT COUNT(*) FROM users"); u_c = cur.fetchone()[0]; conn.close()
        await query.edit_message_text(f"📊 Stats:\nFiles: {f_c}\nUsers: {u_c}", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 Back", callback_data="back")]]))
    elif query.data.startswith("get_"):
        f = get_file_by_id(query.data.split("_")[1])
        if f:
            cap = f"🎬SH_Filte_Bot🎬\n\n🎥 **File:** {f[1]}"
            if f[2] == 'video': s = await context.bot.send_video(chat_id=query.from_user.id, video=f[0], caption=cap)
            else: s = await context.bot.send_document(chat_id=query.from_user.id, document=f[0], caption=cap)
            context.application.create_task(delete_msg(context, query.from_user.id, s.message_id))

# --- Public & Admin Commands ---

async def get_my_id(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(f"👤 ඔබේ Telegram ID: `{update.effective_user.id}`", parse_mode="Markdown")

async def bot_info(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("🤖 **Bot Information**\n\nName: SH Filter Bot\nAdmin: @YourUsername\nStatus: Online", parse_mode="Markdown")

async def set_maintenance(update: Update, context: ContextTypes.DEFAULT_TYPE):
    global MAINTENANCE_MODE
    if update.effective_user.id != ADMIN_ID: return
    mode = context.args[0].lower() if context.args else ""
    if mode == "on": MAINTENANCE_MODE = True; await update.message.reply_text("✅ Maintenance: ON")
    elif mode == "off": MAINTENANCE_MODE = False; await update.message.reply_text("✅ Maintenance: OFF")

async def broadcast(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.effective_user.id != ADMIN_ID: return
    msg = " ".join(context.args)
    if not msg: return
    for u_id in get_all_users():
        try: await context.bot.send_message(chat_id=u_id, text=msg)
        except: pass
    await update.message.reply_text("✅ Broadcast සම්පූර්ණයි.")

# --- Security: Block Add to Other Groups ---
async def check_new_chat(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if update.message.new_chat_members:
        for member in update.message.new_chat_members:
            if member.id == context.bot.id:
                if update.message.from_user.id != ADMIN_ID:
                    await update.message.chat.leave()

# --- Main ---
if __name__ == '__main__':
    init_db()
    app = ApplicationBuilder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("id", get_my_id))
    app.add_handler(CommandHandler("info", bot_info))
    app.add_handler(CommandHandler("maintenance", set_maintenance))
    app.add_handler(CommandHandler("broadcast", broadcast))
    app.add_handler(MessageHandler(filters.StatusUpdate.NEW_CHAT_MEMBERS, check_new_chat))
    app.add_handler(MessageHandler(filters.Document.ALL | filters.VIDEO | filters.AUDIO, index_files))
    app.add_handler(MessageHandler(filters.TEXT & (~filters.COMMAND), search_files))
    app.add_handler(CallbackQueryHandler(handle_callbacks))
    app.run_polling()
