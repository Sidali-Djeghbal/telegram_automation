import feedparser, requests, time, os
from datetime import datetime
from bs4 import BeautifulSoup

# ====== SETTINGS ======
RSS_URL = "https://rss.app/feeds/ns3Rql1vEE1hffmX.xml"
TELEGRAM_CHAT_ID = "-1002885691718"  # your supergroup ID
CHECK_INTERVAL = 60
LAST_ID_FILE = "last_fb_post.txt"
# =======================

# ⚠️ REPLACE this with your bot token or set it as an environment variable in Render
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")

def load_last_id():
    return open(LAST_ID_FILE).read().strip() if os.path.exists(LAST_ID_FILE) else ""

def save_last_id(pid):
    open(LAST_ID_FILE, "w").write(pid)

def send_telegram_message(text, photo_url=None):
    if photo_url:
        caption = text[:1000]
        url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendPhoto"
        payload = {
            "chat_id": TELEGRAM_CHAT_ID,
            "photo": photo_url,
            "caption": caption,
            "parse_mode": "Markdown"
        }
        r = requests.post(url, data=payload)
        if not r.ok:
            print("⚠️ Error sending photo:", r.text)
        if len(text) > 1000:
            rest = text[1000:]
            requests.post(
                f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage",
                data={
                    "chat_id": TELEGRAM_CHAT_ID,
                    "text": rest,
                    "parse_mode": "Markdown",
                    "disable_web_page_preview": True
                }
            )
    else:
        url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
        payload = {
            "chat_id": TELEGRAM_CHAT_ID,
            "text": text,
            "parse_mode": "Markdown",
            "disable_web_page_preview": True
        }
        r = requests.post(url, data=payload)
        if not r.ok:
            print("⚠️ Error sending text:", r.text)

print("✅ Bot started – checking Facebook RSS every", CHECK_INTERVAL, "seconds.")

last_id = load_last_id()
initial_sent = False

while True:
    try:
        feed = feedparser.parse(RSS_URL)
        if feed.entries:
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

            if not initial_sent:
                send_telegram_message(message, photo_url=img_url)
                save_last_id(post_id)
                initial_sent = True
                print(datetime.now(), "✅ Sent current latest post:", title)

            elif post_id != last_id:
                send_telegram_message(message, photo_url=img_url)
                save_last_id(post_id)
                print(datetime.now(), "✅ Sent new post:", title)
                last_id = post_id
            else:
                print(datetime.now(), "— No new posts.")
        else:
            print(datetime.now(), "⚠️ No RSS posts found.")
    except Exception as e:
        print(datetime.now(), "⚠️ Error:", e)

    time.sleep(CHECK_INTERVAL)
