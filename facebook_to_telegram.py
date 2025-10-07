# bot.py — Telegram RSS to forum topic (chat -1003028783511, thread 30)

import os, time, json, sys, logging, threading
from datetime import datetime
import feedparser, requests
from bs4 import BeautifulSoup
from flask import Flask

# ===== SETTINGS =====
RSS_URL = os.getenv("RSS_URL", "https://rss.app/feeds/ns3Rql1vEE1hffmX.xml")

# Fixed chat & topic for Telegram
TELEGRAM_CHAT_ID = "-1003028783511"
TELEGRAM_THREAD_ID = 30

CHECK_INTERVAL = int(os.getenv("CHECK_INTERVAL", "600"))
LAST_ID_FILE = os.getenv("LAST_ID_FILE", "last_fb_post.txt")
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
PORT = int(os.getenv("PORT", "10000"))
DATABASE_URL = os.getenv("DATABASE_URL")  # optional: Render Postgres

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

session = requests.Session()
session.headers.update({"User-Agent": "rss-telegram-bot/1.0"})

# ---------- optional small DB fallback (Postgres) ----------
db_conn = None
def init_db():
    global db_conn
    if not DATABASE_URL:
        return
    try:
        import psycopg2
        db_conn = psycopg2.connect(DATABASE_URL, sslmode="require")
        with db_conn.cursor() as cur:
            cur.execute("""
            CREATE TABLE IF NOT EXISTS bot_kv (
                k TEXT PRIMARY KEY,
                v TEXT
            )""")
            db_conn.commit()
        logging.info("Connected to Postgres for persistent key-value storage.")
    except Exception:
        logging.exception("Could not init Postgres (will fallback to file storage).")

init_db()

def db_get(k):
    if not db_conn:
        return None
    with db_conn.cursor() as cur:
        cur.execute("SELECT v FROM bot_kv WHERE k=%s", (k,))
        r = cur.fetchone()
        return r[0] if r else None

def db_set(k, v):
    if not db_conn:
        return
    with db_conn.cursor() as cur:
        cur.execute("INSERT INTO bot_kv(k,v) VALUES(%s,%s) ON CONFLICT (k) DO UPDATE SET v=EXCLUDED.v", (k, v))
        db_conn.commit()

# ---------- file helpers ----------
def atomic_write(path, data):
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        f.write(data)
    os.replace(tmp, path)

def load_last_id():
    try:
        val = db_get("last_id")
        if val:
            return val
    except Exception:
        logging.exception("db_get failed")
    try:
        if os.path.exists(LAST_ID_FILE):
            with open(LAST_ID_FILE, "r", encoding="utf-8") as f:
                return f.read().strip()
    except Exception:
        logging.exception("Failed to load last id from file")
    return ""

def save_last_id(pid):
    try:
        if db_conn:
            db_set("last_id", pid)
            return
    except Exception:
        logging.exception("db_set failed")
    try:
        atomic_write(LAST_ID_FILE, pid)
    except Exception:
        logging.exception("Failed to save last id to file")

# ---------- telegram helper ----------
def escape_markdown(text):
    return text.replace('_', '\\_')

def send_telegram_message(text, photo_urls=None):
    if not TELEGRAM_BOT_TOKEN:
        logging.error("No TELEGRAM_BOT_TOKEN set")
        return False
    safe_text = escape_markdown(text)
    caption = safe_text[:900]
    rest = safe_text[900:]
    thread_params = {
        "chat_id": TELEGRAM_CHAT_ID,
        "message_thread_id": TELEGRAM_THREAD_ID,  # always send to topic 30
        "parse_mode": "Markdown",
    }

    try:
        if photo_urls:
            media = []
            for url in photo_urls[:10]:
                media.append({"type": "photo", "media": url})
            media[0]["caption"] = caption
            media[0]["parse_mode"] = "Markdown"
            payload = thread_params.copy()
            payload["media"] = json.dumps(media)
            r = session.post(f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMediaGroup",
                             data=payload, timeout=15)
            if not r.ok:
                logging.warning("sendMediaGroup failed: %s", r.text)
                session.post(f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage",
                             data={**thread_params, "text": safe_text, "disable_web_page_preview": True}, timeout=10)
            elif rest:
                session.post(f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage",
                             data={**thread_params, "text": rest, "disable_web_page_preview": True}, timeout=10)
        else:
            r = session.post(f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage",
                             data={**thread_params, "text": safe_text, "disable_web_page_preview": True}, timeout=10)
            if not r.ok:
                logging.warning("sendMessage failed: %s", r.text)
        return True
    except Exception:
        logging.exception("Telegram send error")
        return False

# ---------- processing ----------
def process_post(entry, last_id):
    post_id = entry.get("id", entry.get("link", ""))
    title = entry.get("title", "(No title)")
    link = entry.get("link", "")
    summary_html = entry.get("summary", "")
    soup = BeautifulSoup(summary_html, "html.parser")

    link_footer = ""
    for a in soup.find_all("a"):
        href = a.get("href")
        if href:
            link_footer += f"\n🔗 Link: {href}"
            a.extract()

    img_tags = soup.find_all("img")
    img_urls = [t.get("src") for t in img_tags if t.get("src")]
    for t in img_tags:
        t.extract()

    summary_text = soup.get_text().strip()
    message = f"📢 New post from the school page:\n\n{title}\n\n{summary_text}\n\n🔗 Post URL: {link}"
    if link_footer:
        message += link_footer

    if post_id and post_id != last_id:
        sent = send_telegram_message(message, photo_urls=img_urls if img_urls else None)
        if sent:
            logging.info("✅ Sent new post: %s (%d images)", title, len(img_urls))
            return True, post_id
    return False, last_id

def worker_loop():
    logging.info("Worker started; checking every %s seconds", CHECK_INTERVAL)
    last_id = load_last_id()
    logging.info("Loaded last id: %s", last_id)
    backoff = 1
    while True:
        try:
            resp = session.get(RSS_URL, timeout=20)
            resp.raise_for_status()
            feed = feedparser.parse(resp.content)
            if feed.entries:
                latest = feed.entries[0]
                is_new, new_id = process_post(latest, last_id)
                if is_new:
                    last_id = new_id
                    save_last_id(last_id)
                else:
                    logging.debug("No new posts")
            else:
                logging.warning("No feed entries")
            backoff = 1
        except Exception:
            logging.exception("Worker exception")
            backoff = min(300, backoff * 2)
        time.sleep(CHECK_INTERVAL if backoff == 1 else backoff)

# ---------- Flask ----------
app = Flask(__name__)

@app.route("/")
def home():
    return "Bot is running fine!"

_bg_thread_started = False
def maybe_start_background():
    global _bg_thread_started
    if _bg_thread_started:
        return
    if any(arg == "worker" for arg in sys.argv[1:]):
        return
    _bg_thread_started = True
    t = threading.Thread(target=worker_loop, daemon=True)
    t.start()
maybe_start_background()

if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "worker":
        worker_loop()
    else:
        app.run(host="0.0.0.0", port=PORT)
