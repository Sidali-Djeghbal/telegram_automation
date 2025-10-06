# facebook_to_telegram.py
import feedparser, requests, os
from datetime import datetime
from bs4 import BeautifulSoup
from flask import Flask

# ====== SETTINGS ======
RSS_URL = "https://rss.app/feeds/ns3Rql1vEE1hffmX.xml"
TELEGRAM_CHAT_ID = "-1003028783511"      # Group ID
TELEGRAM_THREAD_ID = 30                  # 🧵 Topic ID: "Departement news"
LAST_ID_FILE = "last_fb_post.txt"
# =======================

# ✅ Telegram token
TELEGRAM_BOT_TOKEN = "8031430256:AAEWkwTFw9iCf3jcYOptj351dZX7MjJ06ck"

# ====== CORE FUNCTIONS ======
def load_last_id():
    return open(LAST_ID_FILE).read().strip() if os.path.exists(LAST_ID_FILE) else ""

def save_last_id(pid):
    open(LAST_ID_FILE, "w").write(pid)

def send_telegram_message(text, photo_url=None):
    if not TELEGRAM_BOT_TOKEN:
        print("❌ TELEGRAM_BOT_TOKEN not found.")
        return

    base_url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}"

    if photo_url:
        caption = text[:1000]
        r = requests.post(
            f"{base_url}/sendPhoto",
            data={
                "chat_id": TELEGRAM_CHAT_ID,
                "message_thread_id": TELEGRAM_THREAD_ID,   # ✅ Send to topic
                "photo": photo_url,
                "caption": caption,
                "parse_mode": "Markdown",
            },
        )
        if not r.ok:
            print("⚠️ Error sending photo:", r.text)

        if len(text) > 1000:
            rest = text[1000:]
            requests.post(
                f"{base_url}/sendMessage",
                data={
                    "chat_id": TELEGRAM_CHAT_ID,
                    "message_thread_id": TELEGRAM_THREAD_ID,  # ✅ Send to same topic
                    "text": rest,
                    "parse_mode": "Markdown",
                    "disable_web_page_preview": True,
                },
            )
    else:
        r = requests.post(
            f"{base_url}/sendMessage",
            data={
                "chat_id": TELEGRAM_CHAT_ID,
                "message_thread_id": TELEGRAM_THREAD_ID,   # ✅ Send to topic
                "text": text,
                "parse_mode": "Markdown",
                "disable_web_page_preview": True,
            },
        )
        if not r.ok:
            print("⚠️ Error sending text:", r.text)

def check_facebook_feed():
    print(datetime.now(), "⏳ Checking Facebook RSS...")

    try:
        feed = feedparser.parse(RSS_URL)
        if not feed.entries:
            print("⚠️ No RSS posts found.")
            return "⚠️ No RSS posts found."

        latest = feed.entries[0]
        post_id = latest.get("id", latest.get("link", ""))
        title = latest.get("title", "(No title)")
        link = latest.get("link", "")
        summary_html = latest.get("summary", "")
        summary_text = BeautifulSoup(summary_html, "html.parser").get_text().strip()

        soup = BeautifulSoup(summary_html, "html.parser")
        img_tag = soup.find("img")
        img_url = img_tag["src"] if img_tag and "src" in img_tag.attrs else None

        message = f"📢 *New post from the school page:*\n\n{title}\n\n{summary_text}\n\n🔗 {link}"

        last_id = load_last_id()
        if post_id != last_id:
            send_telegram_message(message, photo_url=img_url)
            save_last_id(post_id)
            print(datetime.now(), "✅ Sent new post:", title)
            return f"✅ Sent new post: {title}"
        else:
            print(datetime.now(), "— No new posts.")
            return "— No new posts."
    except Exception as e:
        print(datetime.now(), "⚠️ Error:", e)
        return f"⚠️ Error: {e}"

# ====== FLASK APP ======
app = Flask(__name__)

@app.route('/')
def home():
    result = check_facebook_feed()
    return f"Bot checked feed. Result: {result}"

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=10000)
