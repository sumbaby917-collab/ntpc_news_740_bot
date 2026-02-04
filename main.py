import feedparser
import requests
import datetime
import os
import urllib.parse
import time
import json
import re
from html import escape, unescape

import google.generativeai as genai

# =========================
# 0) 基本設定
# =========================
TELEGRAM_TOKEN = os.getenv('TELEGRAM_TOKEN')
CHAT_ID = os.getenv('TELEGRAM_CHAT_ID')
GEMINI_KEY = os.getenv('GEMINI_API_KEY')

assert TELEGRAM_TOKEN, "缺少 TELEGRAM_TOKEN"
assert CHAT_ID, "缺少 TELEGRAM_CHAT_ID"

# Gemini
if GEMINI_KEY:
    genai.configure(api_key=GEMINI_KEY)

MODEL_CANDIDATES = [
    "models/gemini-2.5-flash",
    "models/gemini-2.5-pro",
]

# =========================
# 1) 查詢：新北優先 + 全國擴散
# =========================
QUERY_POOLS = {
    "交通政務": {
        "ntpc": "新北 (交通安全 OR 行人 OR 通學巷 OR 事故 OR 酒駕 OR 淡江大橋)",
        "national": "(交通安全 OR 行人安全 OR 通學巷 OR 事故 OR 酒駕 OR 路口改善)"
    },
    "教育業務": {
        "ntpc": "新北 (補習班 OR 未立案補習班 OR 課後照顧 OR 終身學習 OR 技職)",
        "national": "(補習班 OR 未立案補習班 OR 課後照顧 OR 終身學習 OR 技職)"
    },
}

# =========================
# 2) 更新信號（舊聞但有新進度才允許）
# =========================
UPDATE_HINTS = [
    "最新", "更新", "續", "再", "二度", "第三次", "追加", "加重", "擴大",
    "起訴", "判決", "裁定", "判刑", "移送", "勒令", "停業", "撤照",
    "再罰", "續罰", "累罰", "重罰", "稽查", "查獲", "開罰", "不怕罰"
]

NTPC_HINTS = [
    "新北", "新北市", "板橋", "新莊", "中和", "永和", "三重", "蘆洲",
    "新店", "土城", "樹林", "鶯歌", "三峽", "林口", "淡水", "汐止", "瑞芳",
    "侯友宜"
]

# =========================
# 3) Cache：跨次執行避免重複推播
# =========================
CACHE_FILE = "sent_cache.json"
CACHE_TTL_DAYS = 7  # 保留 7 天，避免一週內重複推播同一則

def load_cache():
    try:
        with open(CACHE_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
        # data: { "url": {"ts": epoch}, ... }
        if not isinstance(data, dict):
            return {}
        return data
    except Exception:
        return {}

def save_cache(cache: dict):
    try:
        with open(CACHE_FILE, "w", encoding="utf-8") as f:
            json.dump(cache, f, ensure_ascii=False, indent=2)
    except Exception:
        # 寫入失敗也不影響主流程
        pass

def prune_cache(cache: dict):
    now = int(time.time())
    ttl = CACHE_TTL_DAYS * 86400
    keys = list(cache.keys())
    for k in keys:
        ts = cache.get(k, {}).get("ts", 0)
        if now - ts > ttl:
            cache.pop(k, None)

def cache_seen(cache: dict, canonical_url: str) -> bool:
    if not canonical_url:
        return False
    return canonical_url in cache

def cache_mark(cache: dict, canonical_url: str):
    if not canonical_url:
        return
    cache[canonical_url] = {"ts": int(time.time())}

# =========================
# 4) 基礎工具：安全 request（避免 workflow 變紅）
# =========================
def safe_get(url: str, timeout=12):
    try:
        return requests.get(
            url,
            timeout=timeout,
            allow_redirects=True,
            headers={"User-Agent": "Mozilla/5.0"}
        )
    except Exception as e:
        print("WARN safe_get failed:", type(e).__name__, str(e)[:120])
        return None

# =========================
# 5) 時間判斷：近 24h 或（舊聞但標題顯示有更新）
# =========================
def get_entry_time_utc(entry):
    t = None
    try:
        if getattr(entry, "published_parsed", None):
            t = datetime.datetime.fromtimestamp(
                time.mktime(entry.published_parsed),
                tz=datetime.timezone.utc
            )
        elif getattr(entry, "updated_parsed", None):
            t = datetime.datetime.fromtimestamp(
                time.mktime(entry.updated_parsed),
                tz=datetime.timezone.utc
            )
    except Exception:
        return None
    return t

def is_update_story(title: str) -> bool:
    return any(k in (title or "") for k in UPDATE_HINTS)

def is_recent_or_update(entry, hours=24) -> bool:
    t = get_entry_time_utc(entry)
    if t is None:
        return True
    now = datetime.datetime.now(datetime.timezone.utc)
    age = now - t
    if age <= datetime.timedelta(hours=hours):
        return True
    return is_update_story(getattr(entry, "title", ""))

# =========================
# 6) Google News 連結解包：確實取到外站原文
# =========================
def extract_external_url_from_google_news_html(html: str):
    if not html:
        return None
    html = unescape(html)

    # 優先抓 href="https://xxx" 且非 google 網域
    candidates = re.findall(r'href="(https?://[^"]+)"', html)
    for u in candidates:
        if any(bad in u for bad in [
            "news.google.com", "accounts.google.com", "policies.google.com",
            "support.google.com", "google.com"
        ]):
            continue
        return u

    # 備援：抓 url= 參數
    m = re.search(r"[?&]url=(https?%3A%2F%2F[^&]+)", html)
    if m:
        return urllib.parse.unquote(m.group(1))
    return None

def resolve_to_canonical_news_url(url: str) -> str:
    if not url:
        return url

    r = safe_get(url)
    if not r:
        return url

    final_url = r.url

    # 若已經是外站
    if "news.google.com" not in final_url:
        parsed = urllib.parse.urlparse(final_url)
        qs = urllib.parse.parse_qs(parsed.query)
        if "url" in qs and qs["url"]:
            return qs["url"][0]
        return final_url

    # 還停在 Google News：從 HTML 抓外站
    ext = extract_external_url_from_google_news_html(r.text)
    if ext:
        return ext

    return final_url

def get_best_link(entry) -> str:
    # 1) source.href 若是外站
    if getattr(entry, "source", None) and getattr(entry.source, "href", None):
        href = entry.source.href
        if href and "news.google.com" not in href:
            return href

    # 2) links 內找外站
    for l in getattr(entry, "links", []) or []:
        href = l.get("href")
        if href and "news.google.com" not in href:
            return href

    # 3) entry.link 解包
    return resolve_to_canonical_news_url(getattr(entry, "link", ""))

# =========================
# 7) 去重：canonical URL 優先；標題規範化備援
# =========================
def normalize_title(title: str) -> str:
    t = (title or "").strip()
    # 去掉常見尾綴來源
    t = re.split(
        r"\s*[-｜|]\s*(?:聯合新聞網|udn|鏡週刊|中時|中國時報|自由時報|ETtoday|TVBS|三立|Yahoo|NOWnews|CTWANT|風傳媒|工商時報|太報).*$",
        t,
        maxsplit=1
    )[0]
    t = re.sub(r"\s+", " ", t)
    return t

def dedupe_key(entry):
    title = getattr(entry, "title", "") or ""
    canonical = get_best_link(entry) or ""
    if canonical and "news.google.com" not in canonical:
        return ("url", canonical)
    return ("title", normalize_title(title))

# =========================
# 8) 新北優先排序：新北在前，其次時間新近度
# =========================
def is_ntpc_related(title: str) -> bool:
    return any(k in (title or "") for k in NTPC_HINTS)

def sort_key(entry):
    title = getattr(entry, "title", "") or ""
    t = get_entry_time_utc(entry)
    ntpc_rank = 0 if is_ntpc_related(title) else 1
    if t is None:
        time_rank = 999999999
    else:
        now = datetime.datetime.now(datetime.timezone.utc)
        time_rank = int((now - t).total_seconds())
    return (ntpc_rank, time_rank)

# =========================
# 9) AI 摘要（soft-fail，AI 壞了也不影響晨報）
# =========================
def get_ai_analysis(title: str) -> str:
    if not GEMINI_KEY:
        return "（AI）未設定 GEMINI_API_KEY，暫以人工判讀為主。"

    prompt = (
        "請以新北市政府教育局政策治理視角，"
        "針對新聞標題產出："
        "（一）兩句重點摘要；（二）一項行政因應建議。"
        "語氣正式、專業、可供局內簡報。\n"
        f"新聞標題：{title}"
    )

    last_error = None
    for model_id in MODEL_CANDIDATES:
        try:
            model = genai.GenerativeModel(model_id)
            resp = model.generate_content(prompt)
            if resp and getattr(resp, "text", None):
                return resp.text.strip()
        except Exception as e:
            last_error = e
            continue

    # AI 失敗不讓流程中斷
    return f"（AI）暫時無法產出，系統將持續重試（{type(last_error).__name__}）。"

# =========================
# 10) RSS 抓取
# =========================
def fetch_entries(query: str):
    safe_query = urllib.parse.quote_plus(query)
    rss_url = f"https://news.google.com/rss/search?q={safe_query}&hl=zh-TW&gl=TW&ceid=TW:zh-Hant"
    try:
        feed = feedparser.parse(rss_url)
        return feed.entries or []
    except Exception as e:
        print("WARN feedparser failed:", type(e).__name__, str(e)[:120])
        return []

# =========================
# 11) 產生報告：新北優先、全國補足、去重、跨日不重複、取前3
# =========================
def generate_report():
    today = datetime.date.today().isoformat()
    report = f"📋 <b>教育輿情報告（新北優先＋全國動態）({today})</b>\n"
    report += "━━━━━━━━━━━━━━━━━━━━\n"

    cache = load_cache()
    prune_cache(cache)

    for label, pools in QUERY_POOLS.items():
        report += f"\n🔍 <b>類別：{escape(label)}</b>\n"

        entries = []
        entries += fetch_entries(pools["ntpc"])
        entries += fetch_entries(pools["national"])

        if not entries:
            report += "今日暫無相關新聞。\n"
            continue

        # 1) 新/更新過濾
        entries = [e for e in entries if is_recent_or_update(e, hours=24)]
        if not entries:
            report += "近 24 小時（含更新進度）未篩選到符合條件之新聞。\n"
            continue

        # 2) 去重（同 run）
        seen = set()
        uniq = []
        for e in entries:
            k = dedupe_key(e)
            if k in seen:
                continue
            seen.add(k)
            uniq.append(e)

        # 3) 新北優先 + 越新越前
        uniq.sort(key=sort_key)

        # 4) 跨日/跨 run 不重複（以 canonical url 為準）
        picked = 0
        for e in uniq:
            title = (getattr(e, "title", "") or "").strip()
            canonical = get_best_link(e)

            # canonical 取不到時仍可出，但無法進 cache 去重
            if canonical and cache_seen(cache, canonical):
                continue

            analysis = get_ai_analysis(title)
            link = canonical or getattr(e, "link", "")

            report += f"📍 <b>新聞</b>：{escape(title)}\n"
            report += f"💡 {escape(analysis)}\n"
            report += f"🔗 <a href=\"{escape(link)}\">原文連結</a>\n"
            report += "--------------------\n"

            if canonical:
                cache_mark(cache, canonical)

            picked += 1
            if picked >= 3:
                break

        if picked == 0:
            report += "今日暫無可推播新聞（已排除重複或舊聞且無更新者）。\n"

    save_cache(cache)
    return report

# =========================
# 12) 主程式：Telegram 發送（soft-fail）
# =========================
if __name__ == "__main__":
    final_report = generate_report()

    try:
        r = requests.post(
            f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage",
            data={
                "chat_id": CHAT_ID,
                "text": final_report,
                "parse_mode": "HTML",
                "disable_web_page_preview": True
            },
            timeout=20
        )
        if not r.ok:
            print("Telegram 發送失敗：", r.status_code, r.text)
    except Exception as e:
        print("WARN Telegram request failed:", type(e).__name__, str(e)[:120])
