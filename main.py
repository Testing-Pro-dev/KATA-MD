"""
╔═══════════════════════════════╗
║   🔥 KATA-MD WhatsApp Bot     ║
║   Render Deploy Edition v2.0  ║
╚═══════════════════════════════╝
"""

import os
import time
import uuid
import logging
import requests
import yt_dlp
from pathlib import Path
from datetime import datetime
from flask import Flask, Response
import threading

# ─── Flask keep-alive (required for Render free tier) ────────────────────────
app = Flask(__name__)

@app.route("/")
def home():
    return "🔥 Kata-MD is Running!", 200

@app.route("/health")
def health():
    return {"status": "online", "bot": "Kata-MD v2.0"}, 200

def run_flask():
    port = int(os.environ.get("PORT", 8080))
    app.run(host="0.0.0.0", port=port)

# ─── Credentials (set these in Render environment variables) ─────────────────
INSTANCE_ID    = os.environ.get("GREEN_INSTANCE_ID", "7107575522")
INSTANCE_TOKEN = os.environ.get("GREEN_INSTANCE_TOKEN", "7376ec335b834afd9c4cd234d36c9901198f5950308c48e6a4")
BASE_URL       = f"https://api.green-api.com/waInstance{INSTANCE_ID}"

# ─── Bot Config ───────────────────────────────────────────────────────────────
BOT_NAME     = os.environ.get("BOT_NAME", "Kata-MD")
BOT_VERSION  = "v2.0"
OWNER_NUMBER = os.environ.get("OWNER_NUMBER", "27743266789")
OWNER_JID    = f"{OWNER_NUMBER}@c.us"
PREFIX       = os.environ.get("PREFIX", ".")
DOWNLOAD_DIR = Path("/tmp/downloads")
DOWNLOAD_DIR.mkdir(exist_ok=True)
MAX_FILE_MB  = 40

# ─── State ────────────────────────────────────────────────────────────────────
active_users = {}
banned_users = set()
bot_mode     = "public"
bot_pfp_url  = None

# ─── Logging ──────────────────────────────────────────────────────────────────
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger(__name__)

# ─── Green API ────────────────────────────────────────────────────────────────

def send_text(chat_id, text):
    url = f"{BASE_URL}/sendMessage/{INSTANCE_TOKEN}"
    try:
        requests.post(url, json={"chatId": chat_id, "message": text}, timeout=15)
    except Exception as e:
        log.error(f"send_text: {e}")

def send_image(chat_id, image_url, caption=""):
    url = f"{BASE_URL}/sendFileByUrl/{INSTANCE_TOKEN}"
    try:
        requests.post(url, json={
            "chatId": chat_id,
            "urlFile": image_url,
            "fileName": "image.jpg",
            "caption": caption
        }, timeout=30)
    except Exception as e:
        log.error(f"send_image: {e}")

def send_video(chat_id, file_path, caption=""):
    url = f"{BASE_URL}/sendFileByUpload/{INSTANCE_TOKEN}"
    try:
        with open(file_path, "rb") as f:
            requests.post(
                url,
                files={"file": (file_path.name, f, "video/mp4")},
                data={"chatId": chat_id, "caption": caption},
                timeout=120
            )
    except Exception as e:
        log.error(f"send_video: {e}")
        send_text(chat_id, f"❌ Could not send video: {str(e)[:100]}")

def send_audio(chat_id, file_path, caption=""):
    url = f"{BASE_URL}/sendFileByUpload/{INSTANCE_TOKEN}"
    try:
        with open(file_path, "rb") as f:
            requests.post(
                url,
                files={"file": (file_path.name, f, "audio/mpeg")},
                data={"chatId": chat_id, "caption": caption},
                timeout=120
            )
    except Exception as e:
        log.error(f"send_audio: {e}")
        send_text(chat_id, f"❌ Could not send audio: {str(e)[:100]}")

def receive_message():
    url = f"{BASE_URL}/receiveNotification/{INSTANCE_TOKEN}"
    try:
        r = requests.get(url, timeout=35)
        if r.status_code == 200 and r.text.strip() != "null":
            return r.json()
    except:
        pass
    return None

def delete_notification(receipt_id):
    url = f"{BASE_URL}/deleteNotification/{INSTANCE_TOKEN}/{receipt_id}"
    try:
        requests.delete(url, timeout=10)
    except:
        pass

def get_group_members(group_id):
    url = f"{BASE_URL}/getGroupData/{INSTANCE_TOKEN}"
    try:
        r = requests.post(url, json={"groupId": group_id}, timeout=15)
        return [p.get("id", "") for p in r.json().get("participants", [])]
    except:
        return []

def parse_incoming(notification):
    try:
        body      = notification.get("body", {})
        msg       = body.get("messageData", {})
        sender    = body.get("senderData", {})
        chat_id   = sender.get("chatId", "")
        sender_id = sender.get("sender", chat_id)
        name      = sender.get("senderName", sender_id)
        text      = (
            msg.get("textMessageData", {}).get("textMessage", "")
            or msg.get("extendedTextMessageData", {}).get("text", "")
            or ""
        )
        return chat_id, sender_id, name, text.strip()
    except:
        return "", "", "", ""

# ─── Download Helpers ─────────────────────────────────────────────────────────

def download_video(url):
    fid  = uuid.uuid4().hex[:10]
    tmpl = str(DOWNLOAD_DIR / f"{fid}.%(ext)s")
    opts = {
        "format": "best[ext=mp4]/best[ext=webm]/best",
        "outtmpl": tmpl,
        "quiet": True,
        "no_warnings": True,
        "noplaylist": True,
        "socket_timeout": 30,
        "retries": 2,
        "prefer_ffmpeg": False,
        "postprocessors": [],
    }
    try:
        with yt_dlp.YoutubeDL(opts) as ydl:
            info     = ydl.extract_info(url, download=True)
            filename = ydl.prepare_filename(info)
            p = Path(filename)
            if p.exists():
                return p, info.get("title", "Video")[:60]
            for f in DOWNLOAD_DIR.glob(f"{fid}.*"):
                return f, info.get("title", "Video")[:60]
        return None, "File not found."
    except Exception as e:
        return None, str(e)[:300]

def download_audio(url):
    fid  = uuid.uuid4().hex[:10]
    tmpl = str(DOWNLOAD_DIR / f"{fid}.%(ext)s")
    opts = {
        "format": "bestaudio/best",
        "outtmpl": tmpl,
        "quiet": True,
        "no_warnings": True,
        "noplaylist": True,
        "socket_timeout": 30,
        "retries": 2,
        "prefer_ffmpeg": False,
        "postprocessors": [],
    }
    try:
        with yt_dlp.YoutubeDL(opts) as ydl:
            info     = ydl.extract_info(url, download=True)
            filename = ydl.prepare_filename(info)
            p = Path(filename)
            if p.exists():
                return p, info.get("title", "Audio")[:60]
            for f in DOWNLOAD_DIR.glob(f"{fid}.*"):
                return f, info.get("title", "Audio")[:60]
        return None, "File not found."
    except Exception as e:
        return None, str(e)[:300]

def youtube_search(query):
    try:
        with yt_dlp.YoutubeDL({"quiet": True, "skip_download": True, "no_warnings": True}) as ydl:
            info = ydl.extract_info(f"ytsearch1:{query}", download=False)
            if info and info.get("entries"):
                e = info["entries"][0]
                return e.get("webpage_url") or f"https://youtu.be/{e['id']}", e.get("title", "")
    except Exception as e:
        log.error(f"search: {e}")
    return None, ""

# ─── Commands ─────────────────────────────────────────────────────────────────

def cmd_menu(chat_id, prefix):
    menu_text = f"""╔━━━━━━━━━━━━━━━━━━━━━━╗
  🔥 *{BOT_NAME}* {BOT_VERSION} 🔥
  _The Dripped Out Bot_
╚━━━━━━━━━━━━━━━━━━━━━━╝

⚡ *Prefix:* `{prefix}`
🌐 *Mode:* `{bot_mode.upper()}`
👑 *Owner:* +{OWNER_NUMBER}

━━━━ 📥 *DOWNLOADER* ━━━━
{prefix}yt (link) — YouTube video
{prefix}fb (link) — Facebook video
{prefix}insta (link) — Instagram reel
{prefix}song (query) — Download song 🎵
{prefix}yt-search (query) mp3/mp4

━━━━ 🛠️ *TOOLS* ━━━━
{prefix}ping — Bot speed ms ⚡
{prefix}owner — Owner contact 👑
{prefix}runtime — Bot uptime ⏱️

━━━━ 👥 *GROUP* ━━━━
{prefix}tagall — Tag everyone 📢
{prefix}activeusers — Top users 📊

━━━━ 🔐 *OWNER ONLY* ━━━━
{prefix}public — Open to all users
{prefix}private — Owner only mode
{prefix}ban (number) — Ban user 🚫
{prefix}unban (number) — Unban user ✅
{prefix}setpfp (url) — Set bot pic 🖼️
{prefix}setprefix (symbol) — New prefix

━━━━━━━━━━━━━━━━━━━━━━━
🔥 *{BOT_NAME}* | Stay Dripped 💧"""
    if bot_pfp_url:
        send_image(chat_id, bot_pfp_url, caption=menu_text)
    else:
        send_text(chat_id, menu_text)

def cmd_ping(chat_id):
    start = time.time()
    send_text(chat_id, "🏓 *Pong!*")
    ms = round((time.time() - start) * 1000)
    send_text(chat_id, f"⚡ *{BOT_NAME} Speed*\n\n🚀 Response: *{ms}ms*\n✅ Status: *Online*\n🌐 Mode: *{bot_mode.upper()}*\n🔥 *Dripped & Ready*")

def cmd_runtime(chat_id, start_time):
    elapsed = int(time.time() - start_time)
    hrs  = elapsed // 3600
    mins = (elapsed % 3600) // 60
    secs = elapsed % 60
    send_text(chat_id, f"⏱️ *{BOT_NAME} Runtime*\n\n🕐 Uptime: *{hrs}h {mins}m {secs}s*\n✅ *Running Strong* 💪\n🔥 {BOT_NAME} never sleeps!")

def cmd_owner(chat_id):
    send_text(chat_id, f"👑 *{BOT_NAME} Owner*\n\n📱 +{OWNER_NUMBER}\n💬 wa.me/{OWNER_NUMBER}\n\n_Slide in for support_ 🔥")

def cmd_yt(chat_id, url):
    if not url:
        send_text(chat_id, f"❌ Send a YouTube link.\nExample: `{PREFIX}yt https://youtu.be/xxxxx`")
        return
    send_text(chat_id, "🔴 *YouTube* | Downloading... ⏬")
    file_path, title = download_video(url)
    if not file_path or not Path(str(file_path)).exists():
        send_text(chat_id, f"❌ Failed: {title}")
        return
    size_mb = Path(str(file_path)).stat().st_size / (1024 * 1024)
    if size_mb > MAX_FILE_MB:
        send_text(chat_id, f"⚠️ File too large ({size_mb:.1f}MB).")
        Path(str(file_path)).unlink(missing_ok=True)
        return
    send_video(chat_id, file_path, caption=f"🎬 *{title}*\n\n🔥 {BOT_NAME}")
    file_path.unlink(missing_ok=True)

def cmd_fb(chat_id, url):
    if not url:
        send_text(chat_id, f"❌ Send a Facebook link.\nExample: `{PREFIX}fb https://fb.watch/xxxxx`")
        return
    send_text(chat_id, "📘 *Facebook* | Downloading... ⏬")
    file_path, title = download_video(url)
    if not file_path or not Path(str(file_path)).exists():
        send_text(chat_id, f"❌ Failed: {title}")
        return
    size_mb = Path(str(file_path)).stat().st_size / (1024 * 1024)
    if size_mb > MAX_FILE_MB:
        send_text(chat_id, f"⚠️ File too large ({size_mb:.1f}MB).")
        Path(str(file_path)).unlink(missing_ok=True)
        return
    send_video(chat_id, file_path, caption=f"📘 *{title}*\n\n🔥 {BOT_NAME}")
    file_path.unlink(missing_ok=True)

def cmd_insta(chat_id, url):
    if not url:
        send_text(chat_id, f"❌ Send an Instagram link.\nExample: `{PREFIX}insta https://instagram.com/reel/xxxxx`")
        return
    send_text(chat_id, "📸 *Instagram* | Downloading... ⏬")
    file_path, title = download_video(url)
    if not file_path or not Path(str(file_path)).exists():
        send_text(chat_id, f"❌ Failed: {title}")
        return
    size_mb = Path(str(file_path)).stat().st_size / (1024 * 1024)
    if size_mb > MAX_FILE_MB:
        send_text(chat_id, f"⚠️ File too large ({size_mb:.1f}MB).")
        Path(str(file_path)).unlink(missing_ok=True)
        return
    send_video(chat_id, file_path, caption=f"📸 *{title}*\n\n🔥 {BOT_NAME}")
    file_path.unlink(missing_ok=True)

def cmd_song(chat_id, query):
    if not query:
        send_text(chat_id, f"❌ Send a song name.\nExample: `{PREFIX}song Blinding Lights`")
        return
    send_text(chat_id, f"🎵 Searching: *{query}*...")
    url, title = youtube_search(query)
    if not url:
        send_text(chat_id, "❌ Song not found.")
        return
    send_text(chat_id, f"⏬ Downloading: *{title}*...")
    file_path, title = download_audio(url)
    if not file_path or not Path(str(file_path)).exists():
        send_text(chat_id, f"❌ Failed: {title}")
        return
    size_mb = Path(str(file_path)).stat().st_size / (1024 * 1024)
    if size_mb > MAX_FILE_MB:
        send_text(chat_id, f"⚠️ File too large ({size_mb:.1f}MB).")
        Path(str(file_path)).unlink(missing_ok=True)
        return
    send_audio(chat_id, file_path, caption=f"🎵 *{title}*\n\n🔥 {BOT_NAME}")
    file_path.unlink(missing_ok=True)

def cmd_yt_search(chat_id, args):
    if not args:
        send_text(chat_id, f"❌ Usage: `{PREFIX}yt-search <query> mp3` or `{PREFIX}yt-search <query> mp4`")
        return
    parts = args.rsplit(" ", 1)
    fmt   = "mp4"
    query = args
    if len(parts) == 2 and parts[1].lower() in ("mp3", "mp4"):
        query = parts[0]
        fmt   = parts[1].lower()
    send_text(chat_id, f"🔍 Searching: *{query}* [{fmt.upper()}]...")
    url, title = youtube_search(query)
    if not url:
        send_text(chat_id, "❌ No results found.")
        return
    send_text(chat_id, f"⏬ Downloading: *{title}*...")
    if fmt == "mp3":
        file_path, title = download_audio(url)
        if not file_path:
            send_text(chat_id, f"❌ Failed: {title}")
            return
        send_audio(chat_id, file_path, caption=f"🎵 *{title}*\n\n🔥 {BOT_NAME}")
    else:
        file_path, title = download_video(url)
        if not file_path:
            send_text(chat_id, f"❌ Failed: {title}")
            return
        send_video(chat_id, file_path, caption=f"🎬 *{title}*\n\n🔥 {BOT_NAME}")
    file_path.unlink(missing_ok=True)

def cmd_tagall(chat_id):
    if "@g.us" not in chat_id:
        send_text(chat_id, "❌ Groups only!")
        return
    send_text(chat_id, "📢 Fetching members...")
    members = get_group_members(chat_id)
    if not members:
        send_text(chat_id, "❌ Could not fetch members.")
        return
    tags = ""
    for i, m in enumerate(members, 1):
        number = m.replace("@c.us", "").replace("@g.us", "")
        tags += f"{i}. @{number}\n"
    send_text(chat_id, f"📢 *Tagging {len(members)} members:*\n\n{tags}\n🔥 {BOT_NAME}")

def cmd_active_users(chat_id):
    if not active_users:
        send_text(chat_id, "📊 No active users yet.")
        return
    sorted_users = sorted(active_users.items(), key=lambda x: x[1]["count"], reverse=True)[:10]
    medals = ["🥇","🥈","🥉","4️⃣","5️⃣","6️⃣","7️⃣","8️⃣","9️⃣","🔟"]
    text = f"📊 *Top Users — {BOT_NAME}*\n\n"
    for i, (uid, data) in enumerate(sorted_users):
        text += f"{medals[i]} {data['name']} — *{data['count']}* cmds\n"
    text += f"\n🔥 {BOT_NAME}"
    send_text(chat_id, text)

def cmd_ban(chat_id, args, sender_id):
    if sender_id != OWNER_JID:
        send_text(chat_id, "❌ Owner only!")
        return
    number = args.strip().replace("+", "").replace(" ", "")
    if not number:
        send_text(chat_id, "❌ Usage: `.ban 27xxxxxxxxx`")
        return
    banned_users.add(f"{number}@c.us")
    send_text(chat_id, f"🚫 *Banned!*\n+{number} banned from {BOT_NAME}.")

def cmd_unban(chat_id, args, sender_id):
    if sender_id != OWNER_JID:
        send_text(chat_id, "❌ Owner only!")
        return
    number = args.strip().replace("+", "").replace(" ", "")
    if not number:
        send_text(chat_id, "❌ Usage: `.unban 27xxxxxxxxx`")
        return
    banned_users.discard(f"{number}@c.us")
    send_text(chat_id, f"✅ *Unbanned!*\n+{number} can use {BOT_NAME} again.")

def cmd_set_mode(chat_id, mode, sender_id):
    global bot_mode
    if sender_id != OWNER_JID:
        send_text(chat_id, "❌ Owner only!")
        return
    bot_mode = mode
    emoji = "🌐" if mode == "public" else "🔒"
    send_text(chat_id, f"{emoji} *{BOT_NAME} is now {mode.upper()}!*\n\n"
              + ("✅ All users can use the bot." if mode == "public"
                 else "🔐 Only owner can use the bot."))

def cmd_setpfp(chat_id, url, sender_id):
    global bot_pfp_url
    if sender_id != OWNER_JID:
        send_text(chat_id, "❌ Owner only!")
        return
    if not url:
        send_text(chat_id, "❌ Usage: `.setpfp https://image-url.jpg`")
        return
    bot_pfp_url = url.strip()
    send_text(chat_id, f"🖼️ *Bot pic updated!*\nShows with `.menu` now. 🔥")

def cmd_setprefix(chat_id, new_prefix, sender_id, current_prefix):
    if sender_id != OWNER_JID:
        send_text(chat_id, "❌ Owner only!")
        return current_prefix
    if not new_prefix:
        send_text(chat_id, f"❌ Usage: `{current_prefix}setprefix !`")
        return current_prefix
    new_prefix = new_prefix.strip()[0]
    send_text(chat_id, f"✅ Prefix: `{current_prefix}` → `{new_prefix}`\nExample: `{new_prefix}menu`")
    return new_prefix

def track_user(sender_id, name):
    if sender_id not in active_users:
        active_users[sender_id] = {"name": name, "count": 0, "last_seen": ""}
    active_users[sender_id]["count"] += 1
    active_users[sender_id]["last_seen"] = datetime.now().strftime("%H:%M")
    active_users[sender_id]["name"] = name

def handle(chat_id, sender_id, name, text, prefix, start_time):
    global bot_mode
    if not text.lower().startswith(prefix):
        return prefix
    if sender_id in banned_users:
        send_text(chat_id, f"🚫 You are banned from *{BOT_NAME}*.")
        return prefix
    if bot_mode == "private" and sender_id != OWNER_JID:
        send_text(chat_id, f"🔒 *{BOT_NAME}* is in *PRIVATE* mode.")
        return prefix
    track_user(sender_id, name)
    body  = text[len(prefix):].strip()
    parts = body.split(" ", 1)
    cmd   = parts[0].lower()
    args  = parts[1].strip() if len(parts) > 1 else ""
    log.info(f"CMD [{chat_id}] {name}: {prefix}{cmd} {args[:40]}")
    if cmd == "menu":
        cmd_menu(chat_id, prefix)
    elif cmd == "owner":
        cmd_owner(chat_id)
    elif cmd == "ping":
        cmd_ping(chat_id)
    elif cmd == "runtime":
        cmd_runtime(chat_id, start_time)
    elif cmd == "yt":
        cmd_yt(chat_id, args)
    elif cmd == "fb":
        cmd_fb(chat_id, args)
    elif cmd == "insta":
        cmd_insta(chat_id, args)
    elif cmd == "song":
        cmd_song(chat_id, args)
    elif cmd in ("yt-search", "ytsearch"):
        cmd_yt_search(chat_id, args)
    elif cmd == "tagall":
        cmd_tagall(chat_id)
    elif cmd in ("activeusers", "active"):
        cmd_active_users(chat_id)
    elif cmd == "ban":
        cmd_ban(chat_id, args, sender_id)
    elif cmd == "unban":
        cmd_unban(chat_id, args, sender_id)
    elif cmd == "public":
        cmd_set_mode(chat_id, "public", sender_id)
    elif cmd == "private":
        cmd_set_mode(chat_id, "private", sender_id)
    elif cmd == "setpfp":
        cmd_setpfp(chat_id, args, sender_id)
    elif cmd == "setprefix":
        return cmd_setprefix(chat_id, args, sender_id, prefix)
    else:
        send_text(chat_id, f"❓ Unknown: `{prefix}{cmd}`\nType `{prefix}menu` for commands. 🔥")
    return prefix

# ─── Bot Loop ─────────────────────────────────────────────────────────────────

def bot_loop():
    prefix     = PREFIX
    start_time = time.time()
    log.info(f"🔥 {BOT_NAME} {BOT_VERSION} is running!")
    send_text(OWNER_JID, f"╔═══════════════════════╗\n  🔥 *{BOT_NAME} {BOT_VERSION} Online!*\n╚═══════════════════════╝\n\n⚡ Prefix: `{prefix}`\n🌐 Mode: PUBLIC\n☁️ Hosted on Render\n\nType `{prefix}menu` to get started!\n_Stay Dripped_ 💧")
    while True:
        try:
            notification = receive_message()
            if not notification:
                time.sleep(0.3)
                continue
            receipt_id = notification.get("receiptId")
            msg_type   = notification.get("body", {}).get("messageData", {}).get("typeMessage", "")
            if msg_type in ("textMessage", "extendedTextMessage"):
                chat_id, sender_id, name, text = parse_incoming(notification)
                if chat_id and text:
                    prefix = handle(chat_id, sender_id, name, text, prefix, start_time)
            if receipt_id:
                delete_notification(receipt_id)
        except Exception as e:
            log.error(f"Error: {e}")
            time.sleep(2)

# ─── Entry Point ──────────────────────────────────────────────────────────────

if __name__ == "__main__":
    # Run bot in background thread
    bot_thread = threading.Thread(target=bot_loop, daemon=True)
    bot_thread.start()
    # Run Flask in main thread (required for Render)
    run_flask()
