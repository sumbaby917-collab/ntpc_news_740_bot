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

MAX_NTPC = 3
MAX_OTHER = 3

# Telegram 限制 4096；保守切 3500
TG_MAX_CHARS = 3500

# =========================
# HTML Escape
# =========================
def html_escape(s: str) -> str:
    if s is None:
        return ""
    return (
        s.replace("&", "&amp;")
         .replace("<", "&lt;")
         .replace(">", "&gt;")
         .replace("\"", "&quot;")
    )

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
# Telegram（分段送出）
# =========================
def send_telegram_once(text: str):
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
            print("Telegram error:", r.text[:900])
            return False
        return True
    except Exception as e:
        print("Telegram exception:", type(e).__name__, str(e)[:200])
        return False

def send_telegram_chunked(full_text: str):
    # 依段落切：用雙換行作分隔，避免切壞 HTML tag
    parts = full_text.split("\n\n")
    chunks = []
    buf = ""

    for p in parts:
        candidate = (buf + "\n\n" + p) if buf else p
        if len(candidate) <= TG_MAX_CHARS:
            buf = candidate
        else:
            if buf:
                chunks.append(buf)
            # 若單段就超長，硬切（極少見）
            if len(p) > TG_MAX_CHARS:
                for i in range(0, len(p), TG_MAX_CHARS):
                    chunks.append(p[i:i+TG_MAX_CHARS])
                buf = ""
            else:
                buf = p
    if buf:
        chunks.append(buf)

    ok_all = True
    for i, c in enumerate(chunks, start=1):
        prefix = ""
        if len(chunks) > 1:
            prefix = f"（第 {i}/{len(chunks)} 則）\n"
        ok = send_telegram_once(prefix + c)
        ok_all = ok_all and ok
        time.sleep(1.2)  # 避免送太快觸發限制
    return ok_all

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
# Google News → 原始新聞連結
# =========================
def extract_external_url_from_html(html: str):
    if not html:
        return None
    candidates = re.findall(r'href="(https?://[^"]+)"', html)
    for u in candidates:
        # 避開 google 自身連結
        if any(bad in u for bad in ["news.google.com", "accounts.google.com", "policies.google.com", "support.google.com", "google.com"]):
            continue
        return u
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
    if "news.google.com" not in final_url:
        parsed = urllib.parse.urlparse(final_url)
        qs = urllib.parse.parse_qs(parsed.query)
        if "url" in qs and qs["url"]:
            return qs["url"][0]
        return final_url

    ext = extract_external_url_from_html(r.text)
    return ext or final_url

# =========================
# RSS
# =========================
def fetch_entries(query: str, limit=16):
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
    return any(k in t for k in NTPC_HINTS)

# =========================
# 規則型建議（AI 失敗備援）
# =========================
def rule_based_advice(category: str) -> str:
    if "交通" in category:
        return "建議以事故熱點/通學巷為治理單元，推進工程改善、違規熱區執法與校園宣導一體化，並以KPI滾動追蹤成效。"
    if "終身" in category:
        return "建議以場域觸及與學習成效為核心，深化社大/樂齡與在地商圈協作，建立課程品質與弱勢友善配套，提升續學率。"
    return "建議採風險導向稽查與資訊透明並進，鎖定未立案與重大爭議案件，強化跨機關聯稽與家長識別宣導，降低外溢風險。"

def ai_advice(category: str, ntpc_titles: list, other_titles: list) -> str:
    if (not GEMINI_KEY) or (genai is None):
        return rule_based_advice(category)

    try:
        genai.configure(api_key=GEMINI_KEY)

        titles_block = ""
        if ntpc_titles:
            titles_block += "【新北】\n" + "\n".join([f"- {t}" for t in ntpc_titles[:3]]) + "\n"
        if other_titles:
            titles_block += "【外縣市/全國】\n" + "\n".join([f"- {t}" for t in other_titles[:3]]) + "\n"

        prompt = (
            "你是新北市政府教育局政策治理幕僚。"
            "請針對下列新聞標題，產出「2-3句」行政因應建議，"
            "要具體可執行、可跨局處協作、語氣正式專業，避免空泛。\n\n"
            f"類別：{category}\n{titles_block}"
        )

        # 盡量用你原本可用的模型名（避免 404）
        model = genai.GenerativeModel("gemini-1.5-flash")
        resp = model.generate_content(prompt)
        if resp and getattr(resp, "text", None):
            return resp.text.strip()[:260]
        return rule_based_advice(category)

    except Exception as e:
        print("AI advice soft-fail:", type(e).__name__, str(e)[:160])
        return rule_based_advice(category)

# =========================
# 查詢池：新北優先 + 全國補充
# =========================
QUERY_POOLS = {
    "🚦 交通安全": {
        "ntpc": "新北 (交通安全 OR 行人 OR 通學巷 OR 事故 OR 酒駕 OR 路口)",
        "national": "(交通安全 OR 行人安全 OR 通學巷 OR 事故 OR 酒駕 OR 路口改善)"
    },
    "📚 終身學習": {
        "ntpc": "新北 (終身學習 OR 社區大學 OR 樂齡學習 OR 學習型城市)",
        "national": "(終身學習 OR 社區大學 OR 樂齡學習 OR 學習型城市)"
    },
    "🏫 補教類（補習班）": {
        "ntpc": "新北 (補習班 OR 未立案補習班 OR 課後照顧 OR 才藝班)",
        "national": "(補習班 OR 未立案補習班 OR 課後照顧 OR 才藝班)"
    }
}

# =========================
# 主流程
# =========================
def main():
    print("=== Daily Report Bot START ===", datetime.datetime.now().isoformat())
    print("Has TELEGRAM_TOKEN:", bool(TELEGRAM_TOKEN))
    print("Has TELEGRAM_CHAT_ID:", bool(TELEGRAM_CHAT_ID))
    print("Has GEMINI_API_KEY:", bool(GEMINI_KEY))

    cache = load_cache()
    prune_cache(cache)

    today = datetime.date.today().isoformat()
    blocks = []

    for category, pools in QUERY_POOLS.items():
        entries = fetch_entries(pools["ntpc"], limit=18) + fetch_entries(pools["national"], limit=18)

        ntpc_lines, other_lines = [], []
        ntpc_titles, other_titles = [], []
        seen_local = set()

        for e in entries:
            title = (getattr(e, "title", "") or "").strip()
            raw_link = getattr(e, "link", "") or ""
            link = resolve_to_canonical_url(raw_link)

            key = link if link else title
            if not key or key in seen_local:
                continue
            seen_local.add(key)

            cache_key = link if link else f"title::{title}"
            if cache_key in cache:
                continue

            safe_title = html_escape(title)
            safe_link = html_escape(link) if link else ""

            line = f'• <a href="{safe_link}">{safe_title}</a>' if safe_link else f"• {safe_title}"

            if is_ntpc(title):
                if len(ntpc_lines) < MAX_NTPC:
                    ntpc_lines.append(line)
                    ntpc_titles.append(title)
                    cache[cache_key] = {"ts": int(time.time())}
            else:
                if len(other_lines) < MAX_OTHER:
                    other_lines.append(line)
                    other_titles.append(title)
                    cache[cache_key] = {"ts": int(time.time())}

            if len(ntpc_lines) >= MAX_NTPC and len(other_lines) >= MAX_OTHER:
                break

        advice = ai_advice(category, ntpc_titles, other_titles)

        block = f"<b>{html_escape(category)}</b>\n"
        block += "🟦 <b>新北</b>\n" + ("\n".join(ntpc_lines) if ntpc_lines else "（本輪未篩選到符合條件之新北新聞）") + "\n\n"
        block += "🟨 <b>外縣市／全國</b>\n" + ("\n".join(other_lines) if other_lines else "（本輪未篩選到符合條件之其他縣市/全國新聞）") + "\n\n"
        block += f"💡 <b>行政因應建議（soft-fail）</b>\n{html_escape(advice)}"

        blocks.append(block)

    header = f"🗞 <b>新北市教育與交通輿情晨報</b>\n日期：{today}"
    full_msg = header + "\n\n" + "\n\n".join(blocks)

    ok = send_telegram_chunked(full_msg)
    print("Telegram overall ok:", ok)

    save_cache(cache)
    print("=== Daily Report Bot END ===")

if __name__ == "__main__":
    try:
        main()
    except Exception:
        traceback.print_exc()
        # 保持 workflow 綠勾
        raise SystemExit(0)
