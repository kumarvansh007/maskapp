from pyrogram import Client, filters
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton
import sqlite3
import re
import time

# ================== YOUR CREDENTIALS ==================

API_ID = int(os.environ["API_ID"])
API_HASH = os.environ["API_HASH"]
BOT_TOKEN = os.environ["BOT_TOKEN"]
# ======================================================

app = Client("anon_bot", api_id=API_ID, api_hash=API_HASH, bot_token=BOT_TOKEN)

# ================= DATABASE =================

conn = sqlite3.connect("database.db", check_same_thread=False)
cursor = conn.cursor()

cursor.execute("""
CREATE TABLE IF NOT EXISTS confessions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER,
    text TEXT,
    reports INTEGER DEFAULT 0,
    hidden INTEGER DEFAULT 0
)
""")

cursor.execute("""
CREATE TABLE IF NOT EXISTS reactions (
    confession_id INTEGER,
    user_id INTEGER,
    PRIMARY KEY (confession_id, user_id)
)
""")

cursor.execute("""
CREATE TABLE IF NOT EXISTS comments (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    confession_id INTEGER,
    user_id INTEGER,
    text TEXT
)
""")

cursor.execute("""
CREATE TABLE IF NOT EXISTS reports (
    confession_id INTEGER,
    user_id INTEGER,
    PRIMARY KEY (confession_id, user_id)
)
""")

conn.commit()

# ================= MEMORY STORAGE =================

user_states = {}
user_last_post_time = {}
user_comment_times = {}

# ================= START =================

@app.on_message(filters.command("start"))
async def start(client, message):
    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("📝 Post Confession", callback_data="post")],
        [InlineKeyboardButton("📖 Read Confessions", callback_data="read")]
    ])
    await message.reply("Welcome to Dark Mask Confession Bot 😈", reply_markup=keyboard)

# ================= BUTTON HANDLER =================

@app.on_callback_query()
async def buttons(client, callback_query):
    data = callback_query.data
    user_id = callback_query.from_user.id

    if data == "post":
        user_states[user_id] = {"action": "posting"}
        await callback_query.message.reply("Send your confession now.")

    elif data == "read":
        cursor.execute("SELECT * FROM confessions WHERE hidden=0 ORDER BY RANDOM() LIMIT 1")
        confession = cursor.fetchone()

        if confession:
            cid = confession[0]
            text = confession[2]

            cursor.execute("SELECT COUNT(*) FROM reactions WHERE confession_id=?", (cid,))
            reaction_count = cursor.fetchone()[0]

            cursor.execute("SELECT COUNT(*) FROM comments WHERE confession_id=?", (cid,))
            comment_count = cursor.fetchone()[0]

            keyboard = InlineKeyboardMarkup([
                [InlineKeyboardButton(f"❤️ {reaction_count}", callback_data=f"react_{cid}")],
                [InlineKeyboardButton(f"💬 {comment_count}", callback_data=f"comment_{cid}")],
                [InlineKeyboardButton("🚨 Report", callback_data=f"report_{cid}")],
                [InlineKeyboardButton("➡ Next", callback_data="read")]
            ])

            await callback_query.message.reply(f"#{cid}\n\n{text}", reply_markup=keyboard)
        else:
            await callback_query.message.reply("No confessions available.")

    elif data.startswith("react_"):
        cid = int(data.split("_")[1])

        cursor.execute("SELECT * FROM reactions WHERE confession_id=? AND user_id=?", (cid, user_id))
        if cursor.fetchone():
            await callback_query.answer("Already reacted ❤️", show_alert=True)
            return

        cursor.execute("INSERT INTO reactions VALUES (?,?)", (cid, user_id))
        conn.commit()

        cursor.execute("SELECT user_id FROM confessions WHERE id=?", (cid,))
        owner = cursor.fetchone()
        if owner and owner[0] != user_id:
            await app.send_message(owner[0], f"🔔 Confession #{cid} received a ❤️ reaction.")

        await callback_query.answer("❤️ Added")

    elif data.startswith("comment_"):
        cid = int(data.split("_")[1])
        user_states[user_id] = {"action": "commenting", "cid": cid}
        await callback_query.message.reply("Send your anonymous comment.")

    elif data.startswith("report_"):
        cid = int(data.split("_")[1])

        cursor.execute("SELECT * FROM reports WHERE confession_id=? AND user_id=?", (cid, user_id))
        if cursor.fetchone():
            await callback_query.answer("Already reported.", show_alert=True)
            return

        cursor.execute("INSERT INTO reports VALUES (?,?)", (cid, user_id))
        cursor.execute("UPDATE confessions SET reports = reports + 1 WHERE id=?", (cid,))
        conn.commit()

        cursor.execute("SELECT reports FROM confessions WHERE id=?", (cid,))
        reports = cursor.fetchone()[0]

        if reports >= 5:
            cursor.execute("UPDATE confessions SET hidden=1 WHERE id=?", (cid,))
            conn.commit()

        await callback_query.answer("🚨 Report submitted.")

# ================= MESSAGE HANDLER =================

@app.on_message(filters.text & ~filters.command("start"))
async def handle_text(client, message):
    user_id = message.from_user.id
    text = message.text
    text_lower = text.lower()

    # ===== FILTER =====
    bad_words = [
        "bc", "mc", "madarchod", "bhenchod",
        "fuck", "shit", "bitch",
        "randi", "chodu", "bhosda", "mkc",
        "chut", "lund"
    ]

    if any(word in text_lower for word in bad_words):
        await message.reply("❌ Inappropriate language not allowed.")
        return

    if "http://" in text_lower or "https://" in text_lower or "www." in text_lower:
        await message.reply("❌ Links not allowed.")
        return

    if "@" in text_lower:
        await message.reply("❌ Usernames not allowed.")
        return

    if re.search(r'\b\d{10,}\b', text_lower):
        await message.reply("❌ Phone numbers not allowed.")
        return

    if len(text) > 500:
        await message.reply("❌ Maximum 500 characters allowed.")
        return

    # ===== STATE HANDLING =====

    if user_id in user_states:
        state = user_states[user_id]

        if state["action"] == "posting":

            now = time.time()
            if user_id in user_last_post_time and now - user_last_post_time[user_id] < 120:
                await message.reply("⏳ Wait 2 minutes before posting again.")
                return

            user_last_post_time[user_id] = now

            cursor.execute("INSERT INTO confessions (user_id, text) VALUES (?,?)", (user_id, text))
            conn.commit()

            await message.reply("✅ Confession posted anonymously.")
            del user_states[user_id]

        elif state["action"] == "commenting":

            now = time.time()
            if user_id not in user_comment_times:
                user_comment_times[user_id] = []

            user_comment_times[user_id] = [t for t in user_comment_times[user_id] if now - t < 600]

            if len(user_comment_times[user_id]) >= 5:
                await message.reply("⏳ Max 5 comments per 10 minutes.")
                return

            user_comment_times[user_id].append(now)

            cid = state["cid"]

            cursor.execute("INSERT INTO comments (confession_id,user_id,text) VALUES (?,?,?)",
                           (cid, user_id, text))
            conn.commit()

            cursor.execute("SELECT user_id FROM confessions WHERE id=?", (cid,))
            owner = cursor.fetchone()

            if owner and owner[0] != user_id:
                await app.send_message(owner[0],
                    f"💬 Someone commented on confession #{cid}:\n\n{text}")

            await message.reply("💬 Comment posted anonymously.")
            del user_states[user_id]

    else:
        await message.reply("Use buttons to interact.")


app.run()
