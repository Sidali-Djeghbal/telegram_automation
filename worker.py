# bot.py — background Telegram notifier + web endpoint (for Render + cron-job)

import os, time, json, sys, logging, threading
from datetime import datetime
import feedparser, requests
from bs4 import BeautifulSoup
from flask import Flask

# ===== SETTINGS (can be overridden by env vars) =====
RSS_URL = os.getenv("RSS_URL", "https://rss.app/feeds/ns3Rql1vEE1hffmX.xml")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "-4927693812")  # your new chat ID
CHECK_INTERVAL = int(os.getenv("CHECK_INTERVAL", "3600"))
LAST_ID_FILE = os.getenv("LAST_ID_FILE", "last_fb_post.txt")
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
PORT = int(os.getenv("PORT", "10000"))
# ====================================================

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

session = requests.Session()
session.headers.update({"User-Agent": "rss-telegram-bot/1.0"})

def atomic_write(path, data):
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        f.write(data)
    os.replace(tmp, path)

def load_last_id():
    try:
        if os.path.exists(LAST_ID_FILE):
            with open(LAST_ID_FILE, "r", encoding="utf-8") as f:
                return f.read().strip()
    except Exception:
        logging.exception("Failed to load last id")
    return ""

def save_last_id(pid):
    try:
        atomic_write(LAST_ID_FILE, pid)
    except Exception:
        logging.exception("Failed to save last id")

def escape_markdown(text):
    return text.replace('_', '\\_')

def send_telegram_message(text, photo_urls=None):
    if not TELEGRAM_BOT_TOKEN:
        logging.error("No TELEGRAM_BOT_TOKEN set")
        return False

    safe_text = escape_markdown(text)
    caption = safe_text[:900]  # keep buffer
    rest = safe_text[900:]
    base_params = {
        "chat_id": TELEGRAM_CHAT_ID,
        "parse_mode": "Markdown",
    }

    try:
        if photo_urls:
            media = []
            for url in photo_urls[:10]:  # Telegram allows max 10
                media.append({"type": "photo", "media": url})
            media[0]["caption"] = caption
            media[0]["parse_mode"] = "Markdown"
            payload = base_params.copy()
            payload["media"] = json.dumps(media)

            r = session.post(f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMediaGroup",
                             data=payload, timeout=15)
            if not r.ok:
                logging.warning("sendMediaGroup failed: %s", r.text)
                session.post(f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage",
                             data={**base_params, "text": safe_text, "disable_web_page_preview": True}, timeout=10)
            elif rest:
                session.post(f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage",
                             data={**base_params, "text": rest, "disable_web_page_preview": True}, timeout=10)
        else:
            r = session.post(f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage",
                             data={**base_params, "text": safe_text, "disable_web_page_preview": True}, timeout=10)
            if not r.ok:
                logging.warning("sendMessage failed: %s", r.text)
        return True
    except Exception:
        logging.exception("Telegram send error")
        return False

def process_post(entry, last_id):
    post_id = entry.get("id", entry.get("link", ""))
    title = entry.get("title", "(No title)")
    link = entry.get("link", "")
    summary_html = entry.get("summary", "")

    soup = BeautifulSoup(summary_html, "html.parser")

    # collect links
    link_footer = ""
    for a in soup.find_all("a"):
        href = a.get("href")
        txt = a.get_text().strip()
        if href:
            link_footer += f"\n🔗 Link: {href}"
            a.extract()

    # images
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
            feed = feedparser.parse(RSS_URL)
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

# --- Flask ---
app = Flask(__name__)

@app.route("/")
def home():
    return "Bot is running fine!"

if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "worker":
        worker_loop()
    else:
        # default: start worker thread + flask (dev)
        t = threading.Thread(target=worker_loop, daemon=True)
        t.start()
        app.run(host="0.0.0.0", port=PORT)
