import os
from pyrogram import Client, filters
from pyrogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from pytgcalls import PyTgCalls
from pytgcalls.types.input_stream import AudioPiped
from yt_dlp import YoutubeDL
from config import API_ID, API_HASH, BOT_TOKEN, OWNER_ID
import time

app = Client("musicbot", api_id=API_ID, api_hash=API_HASH, bot_token=BOT_TOKEN)
call = PyTgCalls(app)

queue = {}
DATA_DIR = "data"
USERS_FILE = os.path.join(DATA_DIR, "users.txt")
GROUPS_FILE = os.path.join(DATA_DIR, "groups.txt")
os.makedirs(DATA_DIR, exist_ok=True)

ydl_opts = {'format': 'bestaudio', 'quiet': True, 'no_warnings': True}


def save_id(file, id_):
    with open(file, "a+") as f:
        f.seek(0)
        ids = f.read().splitlines()
        if str(id_) not in ids:
            f.write(f"{id_}\n")


def get_audio(url):
    with YoutubeDL(ydl_opts) as ydl:
        info = ydl.extract_info(url, download=False)
        return info['url'], info['title'], info.get('duration', 0)


def format_now_playing(title, duration, user):
    return f"""**▶️ Started Streaming |**  
**▸ Title :** {title}  
**▸ Duration :** `{duration // 60}:{duration % 60:02d}` minutes  
**▸ Requested by :** {user}"""


def player_controls():
    return InlineKeyboardMarkup([
        [InlineKeyboardButton("⏮️", callback_data="prev"),
         InlineKeyboardButton("⏸️", callback_data="pause"),
         InlineKeyboardButton("⏭️", callback_data="skip")],
        [InlineKeyboardButton("Close", callback_data="close")]
    ])


@app.on_message(filters.command("start"))
async def start(_, message):
    save_id(USERS_FILE, message.from_user.id)
    if message.chat.type in ("group", "supergroup"):
        save_id(GROUPS_FILE, message.chat.id)
    await message.reply("Welcome to Music Bot! Use /play to stream music.")


@app.on_message(filters.command("play") & filters.group)
async def play_command(_, message):
    chat_id = message.chat.id
    save_id(GROUPS_FILE, chat_id)
    query = message.text.split(None, 1)[1] if len(message.command) > 1 else None
    if not query:
        return await message.reply("Give me a song name or link.")

    msg = await message.reply("Processing...")

    url, title, duration = get_audio(query)
    requester = message.from_user.mention

    if chat_id not in queue:
        queue[chat_id] = [(url, title, requester, duration)]
        await call.join_group_call(chat_id, AudioPiped(url))
        await msg.edit(
            format_now_playing(title, duration, requester),
            reply_markup=player_controls()
        )
    else:
        queue[chat_id].append((url, title, requester, duration))
        await msg.edit(f"Added to queue: **{title}**")


@app.on_message(filters.command("skip") & filters.group)
async def skip(_, message):
    user = message.from_user
    member = await app.get_chat_member(message.chat.id, user.id)
    if member.status not in ["administrator", "creator"]:
        return await message.reply("Only admins can skip.")

    chat_id = message.chat.id
    if chat_id in queue and len(queue[chat_id]) > 1:
        queue[chat_id].pop(0)
        url, title, requester, duration = queue[chat_id][0]
        await call.change_stream(chat_id, AudioPiped(url))
        await message.reply(f"⏭️ Skipped! Now playing: **{title}**")
    else:
        await message.reply("No song to skip or queue is empty.")


@app.on_message(filters.command("queue") & filters.group)
async def show_queue(_, message):
    chat_id = message.chat.id
    if chat_id not in queue or not queue[chat_id]:
        return await message.reply("Queue is empty.")
    text = "**Current Queue:**\n"
    for i, (_, title, user, _) in enumerate(queue[chat_id], 1):
        text += f"`{i}.` {title} | {user}\n"
    await message.reply(text)


@app.on_callback_query()
async def cb_handler(_, cb):
    data = cb.data
    chat_id = cb.message.chat.id
    if data == "skip":
        if chat_id in queue and len(queue[chat_id]) > 1:
            queue[chat_id].pop(0)
            url, title, requester, duration = queue[chat_id][0]
            await call.change_stream(chat_id, AudioPiped(url))
            await cb.message.edit(
                format_now_playing(title, duration, requester),
                reply_markup=player_controls()
            )
        else:
            await cb.message.reply("No more songs in queue.")
    elif data == "pause":
        await call.pause_stream(chat_id)
        await cb.message.reply("Paused.")
    elif data == "resume":
        await call.resume_stream(chat_id)
        await cb.message.reply("Resumed.")
    elif data == "close":
        await cb.message.delete()


@app.on_message(filters.command("stop") & filters.group)
async def stop(_, message):
    chat_id = message.chat.id
    await call.leave_group_call(chat_id)
    queue.pop(chat_id, None)
    await message.reply("Stopped playback.")


@app.on_message(filters.command("ping"))
async def ping(_, message):
    start = time.time()
    msg = await message.reply("Pinging...")
    end = time.time()
    await msg.edit(f"Pong! `{round((end-start)*1000)}ms`")


@app.on_message(filters.command("broadcast") & filters.user(OWNER_ID))
async def broadcast(_, message):
    if len(message.command) < 2:
        return await message.reply("Usage: /broadcast <message>")
    text = message.text.split(None, 1)[1]
    count = 0
    async for dialog in app.iter_dialogs():
        if dialog.chat.type in ("group", "supergroup"):
            try:
                await app.send_message(dialog.chat.id, text)
                count += 1
            except:
                continue
    await message.reply(f"Broadcast sent to {count} groups.")


@app.on_message(filters.command("data") & filters.user(OWNER_ID))
async def get_data(_, message):
    await message.reply_document(USERS_FILE, caption="User IDs")
    await message.reply_document(GROUPS_FILE, caption="Group IDs")


call.start()
app.run()
