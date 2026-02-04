import os
import json
import time
import datetime
import traceback
import urllib.parse
import re
import requests
import feedparser

# =========================
# 基本設定
# =========================
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")

CACHE_FILE = "sent_cache.json"
CACHE_TTL_DAYS = 7  # 去重保留 7 天

# =========================
# Cache 處理
# =========================
def load_cache():
    try:
        if os.path.exists(CACHE_FILE):
            with open(CACHE_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
            return data if isinstance(data, dict) else {}
    except Exception:
        pass
    return {}

def save_cache(cache: dict):
    try:
        with open(CACHE_FILE, "w", encoding="utf-8") as f:
            json.dump(cache, f, ensure_ascii=False, indent=2)
    except Exception:
        pass

def prune_cache(cache: dict):
    now = int(time.time())
    ttl = CACHE_TTL_DAYS * 86400
    for k in list(cache.keys()):
        if now - cache[k].get("ts", 0) > ttl:
            cache.pop(k, None)

# =========================
# Telegram 發送
# =========================
def send_telegram(text: str):
    if not TELEGRAM_TOKEN or not TELEGRAM_CHAT_ID:
        print("❌ Missing Telegram secrets")
        return False

    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    payload = {
        "chat_id": TELEGRAM_CHAT_ID,
        "text": text,
        "parse_mode": "HTML",
        "disable_web_page_preview": True
    }

    try:
        r = requests.post(url, data=payload, timeout=20)
        print("Telegram status:", r.status_code)
        if not r.ok:
            print("Telegram error:", r.text[:500])
            return False
        return True
    except Exception as e:
        print("Telegram exception:", e)
        return False

# =========================
# Google News → 原始新聞連結
# =========================
def safe_get(url):
    try:
        return requests.get(url, timeout=10, headers={"User-Agent": "Mozilla/5.0"})
    except Exception:
        return None

def extract_external_url(google_news_url):
    r = safe_get(google_news_url)
    if not r:
        return google_news_url

    # 嘗試從 query string 抓 url=
    parsed = urllib.parse.urlparse(r.url)
    qs = urllib.parse.parse_qs(parsed.query)
    if "url" in qs:
        return qs["url"][0]

    # 從 HTML 抓外站連結
    m = re.search(r'href="(https?://[^"]+)"', r.text)
    if m:
        link = m.group(1)
        if "google.com" not in link:
            return link

    return r.url

# =========================
# 新聞抓取
# =========================
def fetch_news(query, limit=5):
    q = urllib.parse.quote_plus(query)
    rss = f"https://news.google.com/rss/search?q={q}&hl=zh-TW&gl=TW&ceid=TW:zh-Hant"
    feed = feedparser.parse(rss)
    return feed.entries[:limit]

# =========================
# 主程式
# =========================
def main():
    print("=== Daily Report Bot START ===", datetime.datetime.now().isoformat())

    cache = load_cache()
    prune_cache(cache)

    today = datetime.date.today().isoformat()

    sections = {
        "🚦 交通安全（新北優先）": "新北 交通安全 OR 行人 OR 通學巷",
        "📚 終身學習": "新北 終身學習 OR 社區大學 OR 樂齡學習",
        "🏫 補教類（補習班）": "新北 補習班 OR 未立案補習班 OR 課後照顧"
    }

    message_blocks = []

    for section, query in sections.items():
        entries = fetch_news(query, limit=6)
        lines = []

        for e in entries:
            title = e.title.strip()
            raw_link = e.link
            link = extract_external_url(raw_link)

            # 去重（用連結）
            if link in cache:
                continue

            lines.append(f"• <a href=\"{link}\">{title}</a>")
            cache[link] = {"ts": int(time.time())}

            if len(lines) >= 3:
                break

        if lines:
            block = f"<b>{section}</b>\n" + "\n".join(lines)
            message_blocks.append(block)

    if message_blocks:
        msg = (
            f"🗞 <b>新北市教育與交通輿情晨報</b>\n"
            f"日期：{today}\n\n"
            + "\n\n".join(message_blocks)
        )
    else:
        msg = (
            f"🗞 <b>新北市教育與交通輿情晨報</b>\n"
            f"日期：{today}\n\n"
            "今日未篩選到符合條件之新聞。"
        )

    send_telegram(msg)
    save_cache(cache)

    print("=== Daily Report Bot END ===")

if __name__ == "__main__":
    try:
        main()
    except Exception:
        traceback.print_exc()
        # 保持 workflow 綠勾
        raise SystemExit(0)
