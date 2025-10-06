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
    # Only load the last ID if the file exists
    return open(LAST_ID_FILE).read().strip() if os.path.exists(LAST_ID_FILE) else ""
def save_last_id(pid):
    # Save the latest processed post ID
    open(LAST_ID_FILE, "w").write(pid)
def send_telegram_message(text, photo_urls=None):
    # Use sendMediaGroup for multiple photos, or sendPhoto for one, or sendMessage for text-only
    
    # 1. Prepare the text message part (caption or standalone message)
    caption = text[:1000] # Telegram caption limit is 1024, keeping a buffer
    rest_of_text = text[1000:]
    
    if photo_urls:
        # If there are multiple photos, use sendMediaGroup
        if len(photo_urls) > 1:
            media = []
            # Add the first photo with the caption
            media.append({
                "type": "photo",
                "media": photo_urls[0],
                "caption": caption,
                "parse_mode": "Markdown"
            })
            # Add the rest of the photos without a caption
            for url in photo_urls[1:]:
                media.append({
                    "type": "photo",
                    "media": url
                })

            url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMediaGroup"
            payload = {
                "chat_id": TELEGRAM_CHAT_ID,
                "media": media
            }
            r = requests.post(url, json=payload) # Use json=payload for sendMediaGroup
            if not r.ok:
                print("⚠️ Error sending media group:", r.text)
                
        # If there's only one photo, use sendPhoto (original logic, slightly cleaned up)
        else: # len(photo_urls) == 1
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

        # Send the rest of the text if it was truncated for the caption
        if rest_of_text:
            requests.post(
                f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage",
                data={
                    "chat_id": TELEGRAM_CHAT_ID,
                    "text": rest_of_text,
                    "parse_mode": "Markdown",
                    "disable_web_page_preview": True
                }
            )
            
    # 2. Text-only message
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

def process_post(entry, last_id):
    """Processes a single post: extracts info, checks if it's new, and sends it."""
    post_id = entry.get("id", entry.get("link", ""))
    title = entry.get("title", "(No title)")
    link = entry.get("link", "")
    summary_html = entry.get("summary", "")
    
    # 1. Extract all images (Change 1 logic)
    soup = BeautifulSoup(summary_html, "html.parser")
    # Find ALL 'img' tags
    img_tags = soup.find_all("img")
    # Extract 'src' from all found tags
    img_urls = [tag["src"] for tag in img_tags if "src" in tag.attrs]
    
    # Prepare text
    summary_text = soup.get_text().strip()
    message = f"📢 New post from the school page:\n\n{title}\n\n{summary_text}\n\n🔗 {link}"
    
    # Check if the post is new
    if post_id and post_id != last_id:
        # Send post with all found images
        send_telegram_message(message, photo_urls=img_urls if img_urls else None)
        print(datetime.now(), f"✅ Sent new post ({len(img_urls)} photo(s)):", title)
        return True, post_id # Indicate a post was sent and its ID
    
    return False, last_id # Indicate no new post was sent

print("✅ Bot started – checking Facebook RSS every", CHECK_INTERVAL, "seconds.")
last_id = load_last_id()
print(f"Loaded last processed ID: {last_id}")

# --- Main loop logic modified for Change 2 ---
while True:
    try:
        feed = feedparser.parse(RSS_URL)
        if feed.entries:
            # We want to check up to the last 2 posts (Change 2)
            # Iterate backwards through the first two entries to process oldest-first
            # (or at least, the second-latest post before the latest one).
            # The range ensures we only check existing entries, up to a maximum of 2.
            
            # This list will hold the IDs of posts that were actually sent in this run
            sent_post_ids = [] 
            
            # Iterate through the last two entries in reverse order
            # feed.entries[1] (second-latest) then feed.entries[0] (latest)
            entries_to_check = feed.entries[:2]
            
            # Use reversed() to process the older post first, then the latest
            for entry in reversed(entries_to_check):
                is_new, new_last_id = process_post(entry, last_id)
                if is_new:
                    # If we sent a post, we update what will be the 'new' last_id
                    last_id = new_last_id
                    sent_post_ids.append(new_last_id)
                
            # If any posts were sent, save the ID of the LATEST one sent (which will be the one 
            # with the highest index in the original feed list, i.e., feed.entries[0])
            if sent_post_ids:
                # The latest sent ID is simply the current last_id after the loop
                save_last_id(last_id) 
            else:
                print(datetime.now(), "— No new posts found in the last two entries.")

        else:
            print(datetime.now(), "⚠️ No RSS posts found.")
            
    except Exception as e:
        print(datetime.now(), "⚠️ Error:", e)
        
    time.sleep(CHECK_INTERVAL)

from flask import Flask
import threading
app = Flask(__name__) # Corrected line: __name__ is a standard pattern
@app.route('/')
def home():
    return "Bot is running fine!"
def run_flask():
    app.run(host="0.0.0.0", port=10000)
# Start Flask in background thread
threading.Thread(target=run_flask).start()
