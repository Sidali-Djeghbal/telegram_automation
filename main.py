!pip install -q feedparser requests beautifulsoup4

import feedparser, requests, time, os
from getpass import getpass
from datetime import datetime
from bs4 import BeautifulSoup

# ====== Settings ======
RSS_URL = "https://rss.app/feeds/ns3Rql1vEE1hffmX.xml"
TELEGRAM_CHAT_ID = "-1002885691718"  # Sidali supergroup
CHECK_INTERVAL = 60
LAST_ID_FILE = "/content/last_fb_post.txt"
# =======================

TELEGRAM_BOT_TOKEN = getpass("أدخل توكن بوت تليغرام (سيبقى مخفيًا أثناء الكتابة): ").strip()

def load_last_id():
    return open(LAST_ID_FILE).read().strip() if os.path.exists(LAST_ID_FILE) else ""

def save_last_id(pid):
    open(LAST_ID_FILE, "w").write(pid)

def send_telegram_message(text, photo_url=None):
    """Send message with/without image — disables link preview"""
    if photo_url:
        caption = text[:1000]  # keep under Telegram caption limit
        url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendPhoto"
        payload = {
            "chat_id": TELEGRAM_CHAT_ID,
            "photo": photo_url,
            "caption": caption,
            "parse_mode": "Markdown"
        }
        r = requests.post(url, data=payload)
        if not r.ok:
            print("⚠️ خطأ في إرسال الصورة:", r.text)
        # send remainder if too long
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
            print("⚠️ خطأ في إرسال النص:", r.text)

print("✅ Bot started – checking Facebook RSS every", CHECK_INTERVAL, "seconds.")

last_id = load_last_id()
initial_sent = False

while True:
    try:
        feed = feedparser.parse(RSS_URL)
        if feed.entries:
            latest = feed.entries[0]
            post_id = latest.get("id", latest.get("link", ""))
            title = latest.get("title", "(بدون عنوان)")
            link = latest.get("link", "")
            summary_html = latest.get("summary", "")
            summary_text = BeautifulSoup(summary_html, "html.parser").get_text().strip()

            soup = BeautifulSoup(summary_html, "html.parser")
            img_tag = soup.find("img")
            img_url = img_tag["src"] if img_tag and "src" in img_tag.attrs else None

            message = f"📢 *منشور من صفحة المدرسة:*\n\n{title}\n\n{summary_text}\n\n🔗 {link}"

            # send latest post at startup
            if not initial_sent:
                send_telegram_message(message, photo_url=img_url)
                save_last_id(post_id)
                initial_sent = True
                print(datetime.now(), "✅ تم إرسال آخر منشور الحالي:", title)

            # check for new posts
            elif post_id != last_id:
                send_telegram_message(message, photo_url=img_url)
                save_last_id(post_id)
                print(datetime.now(), "✅ تم إرسال منشور جديد:", title)
                last_id = post_id

            else:
                print(datetime.now(), "— لا منشورات جديدة.")
        else:
            print(datetime.now(), "⚠️ لم يتم جلب أي منشورات من RSS.")
    except Exception as e:
        print(datetime.now(), "⚠️ خطأ:", e)

    time.sleep(CHECK_INTERVAL)
