import feedparser, requests, time, os
from datetime import datetime
from bs4 import BeautifulSoup
import json
import re

# ====== SETTINGS ======
RSS_URL = "https://rss.app/feeds/ns3Rql1vEE1hffmX.xml"
# NEW SETTINGS for Topic/Thread:
TELEGRAM_CHAT_ID = "-1003028783511" # The ID of the supergroup/channel
TELEGRAM_THREAD_ID = 30           # The ID of the topic/thread within the chat
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

def escape_markdown(text):
    """
    Escapes the underscore (_) to prevent hashtags like #new_post from
    causing text to become incorrectly italic in Telegram Markdown.
    """
    return text.replace('_', '\\_') 

def send_telegram_message(text, photo_urls=None):
    # Fix 1: Escape the text to prevent hashtags from causing unclosed italics
    safe_text = escape_markdown(text)
    
    # Prepare the text message part (caption or standalone message)
    caption = safe_text[:1000] # Telegram caption limit is 1024, keeping a buffer
    rest_of_text = safe_text[1000:]
    
    # Telegram API parameters for thread support
    thread_params = {
        "chat_id": TELEGRAM_CHAT_ID,
        "message_thread_id": TELEGRAM_THREAD_ID, # ADDED thread ID
        "parse_mode": "Markdown",
    }
    
    if photo_urls:
        # Handle multiple images using sendMediaGroup
        
        # 1. Prepare media payload
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

        # 2. Send the media group
        url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMediaGroup"
        payload = thread_params.copy()
        payload["media"] = json.dumps(media)
        
        r = requests.post(url, data=payload) 
        if not r.ok:
            print("⚠️ Error sending media group:", r.text)
            
        # 3. Send the rest of the text if it was truncated
        if rest_of_text:
            requests.post(
                f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage",
                data={
                    "chat_id": TELEGRAM_CHAT_ID,
                    "text": rest_of_text,
                    "message_thread_id": TELEGRAM_THREAD_ID, # ADDED thread ID
                    "parse_mode": "Markdown",
                    "disable_web_page_preview": True
                }
            )
            
    # 2. Text-only message
    else:
        url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
        payload = thread_params.copy()
        payload["text"] = safe_text
        payload["disable_web_page_preview"] = True

        r = requests.post(url, data=payload)
        if not r.ok:
            print("⚠️ Error sending text:", r.text)

def process_post(entry, last_id):
    """Processes a single post: extracts info, checks if it's new, and sends it."""
    post_id = entry.get("id", entry.get("link", ""))
    title = entry.get("title", "(No title)")
    link = entry.get("link", "")
    summary_html = entry.get("summary", "")
    
    soup = BeautifulSoup(summary_html, "html.parser")
    
    # 1. Find all links and correctly format them for the message
    a_tags = soup.find_all("a")
    link_footer = ""
    
    for tag in a_tags:
        href = tag.get("href")
        link_text = tag.get_text().strip()
        
        # Append the full link to the message footer
        if href and "..." in link_text:
            # Reconstruct the link line
            link_footer += f"\n🔗 Link: {href}"
            # Remove the original truncated link text from the soup for clean summary text
            tag.extract()
        elif href:
             # Keep link for any other non-truncated link for consistency
            link_footer += f"\n🔗 Link: {href}"
            tag.extract()

    # 2. Extract ALL image URLs
    img_tags = soup.find_all("img")
    img_urls = [tag["src"] for tag in img_tags if "src" in tag.attrs]
    
    # Remove the img tags from the soup so they don't appear in the summary text
    for tag in img_tags:
        tag.extract()

    # Prepare text
    summary_text = soup.get_text().strip()
    
    # Assemble the final message
    message = f"📢 New post from the school page:\n\n{title}\n\n{summary_text}\n"
    # Add the main post link first, then the links extracted from the body
    message += f"\n🔗 Post URL: {link}"
    if link_footer:
        message += link_footer
    
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

# --- Main loop logic: check last two posts ---
while True:
    try:
        feed = feedparser.parse(RSS_URL)
        if feed.entries:
            sent_post_ids = [] 
            entries_to_check = feed.entries[:2]
            
            # Use reversed() to process the older post first, then the latest
            for entry in reversed(entries_to_check):
                is_new, new_last_id = process_post(entry, last_id)
                if is_new:
                    # If we sent a post, update what will be the 'new' last_id
                    last_id = new_last_id
                    sent_post_ids.append(new_last_id)
                
            # If any posts were sent, save the ID of the LATEST one sent
            if sent_post_ids:
                save_last_id(last_id) 
            else:
                print(datetime.now(), "— No new posts found in the last two entries.")

        else:
            print(datetime.now(), "⚠️ No RSS posts found.")
            
    except Exception as e:
        print(datetime.now(), "⚠️ Error:", e)
        
    time.sleep(CHECK_INTERVAL)

# --- Flask server remains unchanged ---
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
