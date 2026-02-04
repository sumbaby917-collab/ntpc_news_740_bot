import feedparser, requests, datetime, os, urllib.parse, time, re
from html import escape
import google.generativeai as genai

TELEGRAM_TOKEN = os.getenv('TELEGRAM_TOKEN')
CHAT_ID = os.getenv('TELEGRAM_CHAT_ID')
GEMINI_KEY = os.getenv('GEMINI_API_KEY')

assert TELEGRAM_TOKEN, "缺少 TELEGRAM_TOKEN"
assert CHAT_ID, "缺少 TELEGRAM_CHAT_ID"

genai.configure(api_key=GEMINI_KEY)

MODEL_CANDIDATES = [
    "models/gemini-2.5-flash",
    "models/gemini-2.5-pro",
]

# -------------------------
# (A) 查詢：新北優先 + 全國擴散（每類別兩組）
# -------------------------
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

# -------------------------
# (B) 「允許舊聞」的更新信號（可依你業務再增補）
# -------------------------
UPDATE_HINTS = [
    "最新", "更新", "續", "再", "二度", "第三次", "追加", "加重", "擴大",
    "起訴", "判決", "裁定", "判刑", "移送", "勒令", "停業", "撤照",
    "再罰", "續罰", "累罰", "重罰", "稽查", "查獲", "開罰"
]

NTPC_HINTS = ["新北", "新北市", "板橋", "新莊", "中和", "永和", "三重", "蘆洲",
              "新店", "土城", "樹林", "鶯歌", "三峽", "林口", "淡水", "汐止", "瑞芳"]

# -------------------------
# (C) 時間判斷：預設只收 24h；舊聞需具更新信號才放行
# -------------------------
def get_entry_time_utc(entry):
    t = None
    if getattr(entry, "published_parsed", None):
        t = datetime.datetime.fromtimestamp(time.mktime(entry.published_parsed), tz=datetime.timezone.utc)
    elif getattr(entry, "updated_parsed", None):
        t = datetime.datetime.fromtimestamp(time.mktime(entry.updated_parsed), tz=datetime.timezone.utc)
    return t  # 可能為 None

def is_update_story(title: str) -> bool:
    return any(k in title for k in UPDATE_HINTS)

def is_recent_or_update(entry, hours=24) -> bool:
    t = get_entry_time_utc(entry)
    if t is None:
        # 沒時間戳：為避免漏報，先放行，但後面仍會靠去重與連結解析控制品質
        return True
    now = datetime.datetime.now(datetime.timezone.utc)
    age = now - t
    if age <= datetime.timedelta(hours=hours):
        return True
    # 超過 24h：只有標題顯示「更新/新進度」才放行
    return is_update_story(getattr(entry, "title", ""))

# -------------------------
# (D) 連結：確實導到原始新聞
# -------------------------
def resolve_final_url(url: str) -> str:
    try:
        r = requests.get(url, timeout=12, allow_redirects=True, headers={"User-Agent": "Mozilla/5.0"})
        final_url = r.url
        # 若 final_url 有帶 url= 參數（常見於聚合器），嘗試取出
        parsed = urllib.parse.urlparse(final_url)
        qs = urllib.parse.parse_qs(parsed.query)
        if "url" in qs and qs["url"]:
            return qs["url"][0]
        return final_url
    except Exception:
        return url

def get_best_link(entry):
    # 1) RSS source href
    if getattr(entry, "source", None) and getattr(entry.source, "href", None):
        return entry.source.href

    # 2) links 裡找非 news.google.com
    for l in getattr(entry, "links", []) or []:
        href = l.get("href")
        if href and "news.google.com" not in href:
            return href

    # 3) 最後用 entry.link 並嘗試跳轉解包
    return resolve_final_url(getattr(entry, "link", ""))

# -------------------------
# (E) 新北優先排序：新北 > 其他；再依時間新近度
# -------------------------
def is_ntpc_related(title: str) -> bool:
    return any(k in title for k in NTPC_HINTS)

def sort_key(entry):
    title = getattr(entry, "title", "")
    t = get_entry_time_utc(entry)
    # 新北優先：True 排前面 -> 用 0/1
    ntpc_rank = 0 if is_ntpc_related(title) else 1
    # 時間越新越前：沒有時間則略降權
    if t is None:
        time_rank = 999999
    else:
        now = datetime.datetime.now(datetime.timezone.utc)
        time_rank = int((now - t).total_seconds())
    return (ntpc_rank, time_rank)

# -------------------------
# (F) AI 摘要
# -------------------------
def get_ai_analysis(title):
    if not GEMINI_KEY:
        return "AI：尚未設定 GEMINI_API_KEY。"

    prompt = (
        f"請以新北市政府教育局政策治理視角，"
        f"針對新聞標題產出："
        f"（一）兩句重點摘要；（二）一項行政因應建議。"
        f"語氣正式、專業、可供局內簡報。\n"
        f"新聞標題：{title}"
    )

    last_error = None
    for model_id in MODEL_CANDIDATES:
        try:
            model = genai.GenerativeModel(model_id)
            response = model.generate_content(prompt)
            if response and getattr(response, "text", None):
                return response.text.strip()
        except Exception as e:
            last_error = e
            continue

    return f"AI：分析暫時無法產出（{type(last_error).__name__}）"

# -------------------------
# (G) 產生報告：每類別合併 ntpc+national，去重、過濾、排序，取前 3
# -------------------------
def fetch_entries(query: str):
    safe_query = urllib.parse.quote_plus(query)
    rss_url = f"https://news.google.com/rss/search?q={safe_query}&hl=zh-TW&gl=TW&ceid=TW:zh-Hant"
    feed = feedparser.parse(rss_url)
    return feed.entries or []

def generate_report():
    today = datetime.date.today().isoformat()
    report = f"📋 <b>教育輿情報告（新北優先＋全國動態）({today})</b>\n"
    report += "━━━━━━━━━━━━━━━━━━━━\n"

    for label, pools in QUERY_POOLS.items():
        report += f"\n🔍 <b>類別：{escape(label)}</b>\n"

        entries = []
        entries += fetch_entries(pools["ntpc"])
        entries += fetch_entries(pools["national"])

        if not entries:
            report += "今日暫無相關新聞。\n"
            continue

        # 1) 先做「新/更新」過濾
        entries = [e for e in entries if is_recent_or_update(e, hours=24)]

        if not entries:
            report += "近 24 小時（含更新進度）未篩選到符合條件之新聞。\n"
            continue

        # 2) 去重：用 title + link 粗略去重
        seen = set()
        uniq = []
        for e in entries:
            title = getattr(e, "title", "").strip()
            link = getattr(e, "link", "").strip()
            key = (title, link)
            if key in seen:
                continue
            seen.add(key)
            uniq.append(e)

        # 3) 新北優先 + 越新越前
        uniq.sort(key=sort_key)

        # 4) 取前 3
        picked = 0
        for entry in uniq:
            title = getattr(entry, "title", "").strip()
            link = get_best_link(entry)
            analysis = get_ai_analysis(title)

            report += f"📍 <b>新聞</b>：{escape(title)}\n"
            report += f"💡 {escape(analysis)}\n"
            report += f"🔗 <a href=\"{escape(link)}\">原文連結</a>\n"
            report += "--------------------\n"

            picked += 1
            if picked >= 3:
                break

        if picked == 0:
            report += "今日暫無可用新聞（已排除舊聞且無更新者）。\n"

    return report

if __name__ == "__main__":
    final_report = generate_report()
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
        print("Telegram error:", r.status_code, r.text)
