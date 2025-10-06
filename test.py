import feedparser
import requests
import os
import logging
from datetime import datetime
from bs4 import BeautifulSoup
from flask import Flask, jsonify
from urllib.parse import urlparse

# ====== LOGGING SETUP ======
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# ====== SETTINGS ======
RSS_URL = "https://rss.app/feeds/ns3Rql1vEE1hffmX.xml"
TELEGRAM_CHAT_ID = "-4927693812"
TELEGRAM_THREAD_ID = None  # Set to None for regular chat (no topic)
LAST_ID_FILE = "last_fb_post.txt"
MAX_POSTS_PER_CHECK = 5  # Process up to 5 new posts at once

# ✅ Use environment variable for token (more secure)
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "8031430256:AAEWkwTFw9iCf3jcYOptj351dZX7MjJ06ck")

# ====== CORE FUNCTIONS ======
def load_last_id():
    """Load the last processed post ID from file."""
    try:
        if os.path.exists(LAST_ID_FILE):
            with open(LAST_ID_FILE, 'r') as f:
                return f.read().strip()
    except Exception as e:
        logger.error(f"Error loading last ID: {e}")
    return ""

def save_last_id(post_id):
    """Save the last processed post ID to file."""
    try:
        with open(LAST_ID_FILE, 'w') as f:
            f.write(post_id)
        logger.info(f"Saved last post ID: {post_id}")
    except Exception as e:
        logger.error(f"Error saving last ID: {e}")

def is_valid_image_url(url):
    """Validate if the URL is a proper image URL."""
    if not url:
        return False
    try:
        parsed = urlparse(url)
        if not parsed.scheme in ['http', 'https']:
            return False
        # Check if URL ends with common image extensions
        image_extensions = ('.jpg', '.jpeg', '.png', '.gif', '.webp')
        return any(parsed.path.lower().endswith(ext) for ext in image_extensions) or 'fbcdn' in url
    except Exception:
        return False

def escape_markdown(text):
    """Escape special characters for Telegram Markdown."""
    special_chars = ['_', '*', '[', ']', '(', ')', '~', '`', '>', '#', '+', '-', '=', '|', '{', '}', '.', '!']
    for char in special_chars:
        text = text.replace(char, '\\' + char)
    return text

def send_telegram_message(text, photo_url=None):
    """Send message to Telegram group/topic."""
    if not TELEGRAM_BOT_TOKEN:
        logger.error("TELEGRAM_BOT_TOKEN not found.")
        return False
    
    base_url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}"
    
    try:
        if photo_url and is_valid_image_url(photo_url):
            caption = text[:1000]  # Telegram caption limit
            
            payload = {
                "chat_id": TELEGRAM_CHAT_ID,
                "photo": photo_url,
                "caption": caption,
                "parse_mode": "Markdown",
            }
            if TELEGRAM_THREAD_ID:
                payload["message_thread_id"] = TELEGRAM_THREAD_ID
            
            response = requests.post(
                f"{base_url}/sendPhoto",
                data=payload,
                timeout=30
            )
            
            if not response.ok:
                logger.error(f"Error sending photo: {response.text}")
                # Fallback to text-only message
                return send_telegram_message(text, photo_url=None)
            
            # Send remaining text if caption was truncated
            if len(text) > 1000:
                rest_text = text[1000:]
                rest_payload = {
                    "chat_id": TELEGRAM_CHAT_ID,
                    "text": rest_text,
                    "parse_mode": "Markdown",
                    "disable_web_page_preview": True,
                }
                if TELEGRAM_THREAD_ID:
                    rest_payload["message_thread_id"] = TELEGRAM_THREAD_ID
                
                requests.post(
                    f"{base_url}/sendMessage",
                    data=rest_payload,
                    timeout=30
                )
        else:
            payload = {
                "chat_id": TELEGRAM_CHAT_ID,
                "text": text,
                "parse_mode": "Markdown",
                "disable_web_page_preview": True,
            }
            if TELEGRAM_THREAD_ID:
                payload["message_thread_id"] = TELEGRAM_THREAD_ID
            
            response = requests.post(
                f"{base_url}/sendMessage",
                data=payload,
                timeout=30
            )
            
            if not response.ok:
                logger.error(f"Error sending text: {response.text}")
                return False
        
        return True
    
    except requests.exceptions.RequestException as e:
        logger.error(f"Network error sending message: {e}")
        return False
    except Exception as e:
        logger.error(f"Unexpected error sending message: {e}")
        return False

def extract_post_data(entry):
    """Extract relevant data from RSS entry."""
    try:
        post_id = entry.get("id", entry.get("link", ""))
        title = entry.get("title", "(No title)")
        link = entry.get("link", "")
        
        summary_html = entry.get("summary", "")
        summary_text = BeautifulSoup(summary_html, "html.parser").get_text().strip()
        
        # Extract image URL
        soup = BeautifulSoup(summary_html, "html.parser")
        img_tag = soup.find("img")
        img_url = img_tag.get("src") if img_tag else None
        
        return {
            "id": post_id,
            "title": title,
            "link": link,
            "summary": summary_text,
            "image_url": img_url
        }
    except Exception as e:
        logger.error(f"Error extracting post data: {e}")
        return None

def check_facebook_feed():
    """Check Facebook RSS feed for new posts."""
    logger.info("⏳ Checking Facebook RSS feed...")
    
    try:
        feed = feedparser.parse(RSS_URL)
        
        if not feed.entries:
            logger.warning("⚠️ No RSS posts found.")
            return {"status": "warning", "message": "No RSS posts found."}
        
        last_id = load_last_id()
        new_posts = []
        
        # Collect new posts (up to MAX_POSTS_PER_CHECK)
        for entry in feed.entries[:MAX_POSTS_PER_CHECK]:
            post_data = extract_post_data(entry)
            if not post_data:
                continue
            
            if post_data["id"] == last_id:
                break  # Stop when we reach the last processed post
            
            new_posts.append(post_data)
        
        if not new_posts:
            logger.info("— No new posts.")
            return {"status": "success", "message": "No new posts."}
        
        # Send posts in reverse order (oldest first)
        sent_count = 0
        for post in reversed(new_posts):
            message = (
                f"📢 *New post from the school page:*\n\n"
                f"{post['title']}\n\n"
                f"{post['summary']}\n\n"
                f"🔗 {post['link']}"
            )
            
            if send_telegram_message(message, photo_url=post['image_url']):
                sent_count += 1
                logger.info(f"✅ Sent post: {post['title']}")
            else:
                logger.error(f"❌ Failed to send post: {post['title']}")
        
        # Save the ID of the most recent post
        if new_posts:
            save_last_id(new_posts[0]["id"])
        
        result_msg = f"✅ Sent {sent_count} new post(s)."
        logger.info(result_msg)
        return {"status": "success", "message": result_msg, "posts_sent": sent_count}
    
    except feedparser.FeedParserException as e:
        logger.error(f"⚠️ Feed parsing error: {e}")
        return {"status": "error", "message": f"Feed parsing error: {e}"}
    except Exception as e:
        logger.error(f"⚠️ Unexpected error: {e}")
        return {"status": "error", "message": f"Unexpected error: {e}"}

# ====== FLASK APP ======
app = Flask(__name__)

@app.route('/')
def home():
    """Home endpoint - triggers feed check."""
    result = check_facebook_feed()
    return jsonify(result)

@app.route('/health')
def health():
    """Health check endpoint."""
    return jsonify({
        "status": "healthy",
        "timestamp": datetime.now().isoformat(),
        "last_post_id": load_last_id()
    })

@app.route('/test')
def test():
    """Test endpoint - sends a test message."""
    test_message = "🧪 Test message from Facebook-to-Telegram bot"
    success = send_telegram_message(test_message)
    return jsonify({
        "status": "success" if success else "error",
        "message": "Test message sent" if success else "Failed to send test message"
    })

if __name__ == "__main__":
    logger.info("🚀 Starting Facebook-to-Telegram bot...")
    app.run(host="0.0.0.0", port=10000, debug=False)
