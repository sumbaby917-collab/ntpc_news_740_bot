import os
import json
import time
import datetime
import traceback
import urllib.parse
import re
import requests
import feedparser

# （可選）AI：Gemini（soft-fail）
try:
    import google.generativeai as genai
except Exception:
    genai = None

# =========================
# 基本設定
# =========================
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")
GEMINI_KEY = os.getenv("GEMINI_API_KEY")

CACHE_FILE = "sent_cache.json"
CACHE_TTL_DAYS = 7

# 每類最多幾則（新北、外縣市各自上限）
MAX_NTPC = 3
MAX_OTHER = 3

# =========================
# Cache
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
            json.dump(cache if isinstance(cache, dict) else {}, f, ensure_ascii=False, indent=2)
    except Exception:
        pass

def prune_cache(cache: dict):
    now = int(time.time())
    ttl = CACHE_TTL_DAYS * 86400
    for k in list(cache.keys()):
        ts = cache.get(k, {}).get("ts", 0)
        if ts and now - ts > ttl:
            cache.pop(k, None)

# =========================
# Telegram
# =========================
def send_telegram(text: str):
    if not TELEGRAM_TOKEN or not TELEGRAM_CHAT_ID:
        print("❌ Missing TELEGRAM_TOKEN or TELEGRAM_CHAT_ID")
        return False

    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    payload = {
        "chat_id": TELEGRAM_CHAT_ID,
        "text": text,
        "parse_mode": "HTML",
        "disable_web_page_preview": True
    }
    try:
        r = requests.post(url, data=payload, timeout=25)
        print("Telegram status:", r.status_code)
        if not r.ok:
            print("Telegram error:", r.text[:800])
            return False
        return True
    except Exception as e:
        print("Telegram exception:", type(e).__name__, str(e)[:200])
        return False

# =========================
# HTTP helper
# =========================
def safe_get(url):
    try:
        return requests.get(url, timeout=12, allow_redirects=True, headers={"User-Agent": "Mozilla/5.0"})
    except Exception as e:
        print("WARN safe_get:", type(e).__name__, str(e)[:120])
        return None

# =========================
# Google News → 原始新聞連結（盡量直達外站）
# =========================
def extract_external_url_from_html(html: str):
    if not html:
        return None
    # 優先抓 href="https://xxx" 且非 google 網域
    candidates = re.findall(r'href="(https?://[^"]+)"', html)
    for u in candidates:
        if any(bad in u for bad in ["news.google.com", "accounts.google.com", "policies.google.com", "support.google.com", "google.com"]):
            continue
        return u
    # 備援：抓 url= 參數
    m = re.search(r"[?&]url=(https?%3A%2F%2F[^&]+)", html)
    if m:
        return urllib.parse.unquote(m.group(1))
    return None

def resolve_to_canonical_url(url: str) -> str:
    if not url:
        return url
    r = safe_get(url)
    if not r:
        return url

    final_url = r.url
    # 已外站
    if "news.google.com" not in final_url:
        parsed = urllib.parse.urlparse(final_url)
        qs = urllib.parse.parse_qs(parsed.query)
        if "url" in qs and qs["url"]:
            return qs["url"][0]
        return final_url

    # 仍在 Google News：從 HTML 擷取外站
    ext = extract_external_url_from_html(r.text)
    return ext or final_url

# =========================
# RSS
# =========================
def fetch_entries(query: str, limit=12):
    q = urllib.parse.quote_plus(query)
    rss = f"https://news.google.com/rss/search?q={q}&hl=zh-TW&gl=TW&ceid=TW:zh-Hant"
    try:
        feed = feedparser.parse(rss)
        return (feed.entries or [])[:limit]
    except Exception as e:
        print("WARN feedparser:", type(e).__name__, str(e)[:120])
        return []

# =========================
# 新北辨識
# =========================
NTPC_HINTS = [
    "新北", "新北市", "侯友宜", "板橋", "新莊", "中和", "永和", "三重", "蘆洲",
    "新店", "土城", "樹林", "鶯歌", "三峽", "林口", "淡水", "汐止", "瑞芳", "泰山", "五股"
]

def is_ntpc(title: str) -> bool:
    t = title or ""
