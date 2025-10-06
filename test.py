import feedparser, requests, time, os
from datetime import datetime
from bs4 import BeautifulSoup
# ====== SETTINGS ======
RSS_URL = "https://rss.app/feeds/ns3Rql1vEE1hffmX.xml"
TELEGRAM_CHAT_ID = "-4927693812"
CHECK_INTERVAL = 3600
LAST_ID_FILE = "last_fb_post.txt"
# =======================
# ⚠️ REPLACE this with your bot token or set it as an environment variable in Render
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")

def load_last_id():
    return open(LAST_ID_FILE).read().strip() if os.path.exists(LAST_ID_FILE) else ""

def save_last_id(pid):
    open(LAST_ID_FILE, "w").write(pid)

def extract_all_images(summary_html):
    """Extract all image URLs from the post HTML"""
    soup = BeautifulSoup(summary_html, "html.parser")
    img_tags = soup.find_all("img")
    return [img["src"] for img in img_tags if img.get("src")]

def send_telegram_message(text, photo_urls=None):
    if photo_urls and len(photo_urls) > 0:
        # Send first photo with caption
        caption = text[:1000]
        url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendPhoto"
        payload = {
            "chat_id": TELEGRAM_CHAT_ID,
            "photo": photo_urls[0],
            "caption": caption,
            "parse_mode": "Markdown"
        }
        r = requests.post(url, data=payload)
        if not r.ok:
            print("⚠️ Error sending photo:", r.text)
        
        # Send remaining photos without caption
        for photo_url in photo_urls[1:]:
            payload = {
                "chat_id": TELEGRAM_CHAT_ID,
                "photo": photo_url
            }
            r = requests.post(url, data=payload)
            if not r.ok:
                print("⚠️ Error sending additional photo:", r.text)
        
        # Send remaining text if caption was truncated
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
            # Get last two posts
            posts_to_process = feed.entries[:2]
            
            if not initial_sent:
                # Send last two posts on startup
                for post in reversed(posts_to_process):
                    post_id = post.get("id", post.get("link", ""))
                    title = post.get("title", "(No title)")
                    link = post.get("link", "")
                    summary_html = post.get("summary", "")
                    summary_text = BeautifulSoup(summary_html, "html.parser").get_text().strip()
                    
                    # Extract all images
                    img_urls = extract_all_images(summary_html)
                    
                    message = f"📢 *New post from the school page:*\n\n{title}\n\n{summary_text}\n\n🔗 {link}"
                    send_telegram_message(message, photo_urls=img_urls)
                    print(datetime.now(), "✅ Sent post:", title)
                
                # Save the latest post ID
                save_last_id(posts_to_process[0].get("id", posts_to_process[0].get("link", "")))
                initial_sent = True
                last_id = posts_to_process[0].get("id", posts_to_process[0].get("link", ""))
            else:
                # Check for new posts
                latest = posts_to_process[0]
                post_id = latest.get("id", latest.get("link", ""))
                
                if post_id != last_id:
                    title = latest.get("title", "(No title)")
                    link = latest.get("link", "")
                    summary_html = latest.get("summary", "")
                    summary_text = BeautifulSoup(summary_html, "html.parser").get_text().strip()
                    
                    # Extract all images
                    img_urls = extract_all_images(summary_html)
                    
                    message = f"📢 *New post from the school page:*\n\n{title}\n\n{summary_text}\n\n🔗 {link}"
                    send_telegram_message(message, photo_urls=img_urls)
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

from flask import Flask
import threading

app = Flask(__name__)

@app.route('/')
def home():
    return "Bot is running fine!"

def run_flask():
    app.run(host="0.0.0.0", port=10000)

# Start Flask in background thread
threading.Thread(target=run_flask).start()
