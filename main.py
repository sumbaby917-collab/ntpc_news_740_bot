import os
import json
import time
import datetime
import traceback
import urllib.parse
import re
import requests
import feedparser

try:
    import google.generativeai as genai
except Exception:
    genai = None

TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")
GEMINI_KEY = os.getenv("GEMINI_API_KEY")

CACHE_FILE = "sent_cache.json"
CACHE_TTL_DAYS = 5

# 每類：目標數量（保底至少會補到 MIN_TOTAL）
MAX_NTPC = 2
MAX_OTHER = 2
MIN_TOTAL = 3  # 每類至少 3 則（不足就不分欄補足）

TG_MAX_CHARS = 3500

def html_escape(s: str) -> str:
    if s is None:
        return ""
    return (s.replace("&", "&amp;")
             .replace("<", "&lt;")
             .replace(">", "&gt;")
             .replace("\"", "&quot;"))

def load_cache():
    try:
        if os.path.exists(CACHE_FILE):
            with open(CACHE_FILE, "r", encoding="utf-8") as f:
                d = json.load(f)
            return d if isinstance(d, dict) else {}
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

def send_telegram_once(text: str):
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
    r = requests.post(url, data=payload, timeout=25)
    print("Telegram status:", r.status_code)
    if not r.ok:
        print("Telegram error:", r.text[:900])
        return False
    return True

def send_telegram_chunked(full_text: str):
    parts = full_text.split("\n\n")
    chunks, buf = [], ""
    for p in parts:
        candidate = (buf + "\n\n" + p) if buf else p
        if len(candidate) <= TG_MAX_CHARS:
            buf = candidate
        else:
            if buf:
                chunks.append(buf)
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
        prefix = f"（第 {i}/{len(chunks)} 則）\n" if len(chunks) > 1 else ""
        ok_all = send_telegram_once(prefix + c) and ok_all
        time.sleep(1.2)
    return ok_all

def safe_get(url):
    try:
        return requests.get(url, timeout=12, allow_redirects=True, headers={"User-Agent": "Mozilla/5.0"})
    except Exception:
        return None

def extract_external_url_from_html(html: str):
    if not html:
        return None
    candidates = re.findall(r'href="(https?://[^"]+)"', html)
    for u in candidates:
        if any(bad in u for bad in ["news.google.com", "accounts.google.com", "policies.google.com", "support.google.com", "google.com"]):
            continue
        return u
    return None

def resolve_to_canonical_url(url: str) -> str:
    if not url:
        return url
    r = safe_get(url)
    if not r:
        return url
    final = r.url
    if "news.google.com" not in final:
        return final
    ext = extract_external_url_from_html(r.text)
    return ext or final

def fetch_entries(query: str, limit=24):
    q = urllib.parse.quote_plus(query)
    rss = f"https://news.google.com/rss/search?q={q}&hl=zh-TW&gl=TW&ceid=TW:zh-Hant"
    feed = feedparser.parse(rss)
    return (feed.entries or [])[:limit]

NTPC_HINTS = [
    "新北", "新北市", "侯友宜", "板橋", "新莊", "中和", "永和", "三重", "蘆洲",
    "新店", "土城", "樹林", "鶯歌", "三峽", "林口", "淡水", "汐止", "瑞芳", "泰山", "五股"
]

def is_ntpc(title: str) -> bool:
    t = title or ""
    return any(k in t for k in NTPC_HINTS)

# ❌ 排除你不想要的「居家/醫療事故」語意（可再擴）
TRAFFIC_EXCLUDE = ["一氧化碳", "中毒", "瓦斯", "猝死", "急診", "送醫", "家中", "居家"]

def is_traffic_relevant(title: str) -> bool:
    if any(x in (title or "") for x in TRAFFIC_EXCLUDE):
        return False
    return True

def rule_based_advice(category: str) -> str:
    if "交通" in category:
        return "建議以通學環境與事故熱點為治理單位，強化工程改善、違規執法與校園宣導之協同，並以KPI滾動追蹤成效。"
    if "終身" in category:
        return "建議以場域觸及與學習成效為核心，深化社大/樂齡與在地合作，建立課程品質與弱勢友善配套，提升續學率。"
    return "建議採風險導向稽查與資訊透明並進，鎖定未立案與重大爭議案件，強化跨機關聯稽與家長識別宣導，降低外溢風險。"

def ai_advice(category: str, ntpc_titles: list, other_titles: list) -> str:
    if (not GEMINI_KEY) or (genai is None):
        return rule_based_advice(category)
    try:
        genai.configure(api_key=GEMINI_KEY)
        model = genai.GenerativeModel("gemini-1.5-flash")
        titles_block = ""
        if ntpc_titles:
            titles_block += "【新北】\n" + "\n".join([f"- {t}" for t in ntpc_titles[:3]]) + "\n"
        if other_titles:
            titles_block += "【外縣市/全國】\n" + "\n".join([f"- {t}" for t in other_titles[:3]]) + "\n"
        prompt = (
            "你是新北市政府教育局政策治理幕僚。請產出2-3句行政因應建議，具體可執行、可跨局處協作。\n\n"
            f"類別：{category}\n{titles_block}"
        )
        resp = model.generate_content(prompt)
        if resp and getattr(resp, "text", None):
            return resp.text.strip()[:260]
        return rule_based_advice(category)
    except Exception as e:
        print("AI soft-fail:", type(e).__name__, str(e)[:120])
        return rule_based_advice(category)

# ✅ 查詢改成「更像你要的治理語意」
QUERY_POOLS = {
    "🚦 交通安全": {
        "ntpc": "新北 (行人 OR 通學巷 OR 路口 OR 斑馬線 OR 校園周邊 OR 交通執法 OR 道路工程 OR 事故)",
        "national": "(行人 OR 通學巷 OR 路口 OR 斑馬線 OR 校園周邊 OR 交通執法 OR 道路工程 OR 事故)"
    },
    "📚 終身學習": {
        "ntpc": "新北 (終身學習 OR 社區大學 OR 樂齡學習 OR 學習型城市 OR 公民課程)",
        "national": "(終身學習 OR 社區大學 OR 樂齡學習 OR 學習型城市 OR 公民課程)"
    },
    "🏫 補教類（補習班）": {
        "ntpc": "新北 (補習班 OR 未立案補習班 OR 補習班稽查 OR 消費爭議 OR 退費 OR 不當對待)",
        "national": "(補習班 OR 未立案補習班 OR 補習班稽查 OR 消費爭議 OR 退費 OR 不當對待)"
    }
}

def build_line(title: str, link: str) -> str:
    safe_title = html_escape(title)
    safe_link = html_escape(link) if link else ""
    return f'• <a href="{safe_link}">{safe_title}</a>' if safe_link else f"• {safe_title}"

def main():
    print("=== START ===", datetime.datetime.now().isoformat())
    cache = load_cache()
    prune_cache(cache)

    today = datetime.date.today().isoformat()
    blocks = []

    for category, pools in QUERY_POOLS.items():
        entries = fetch_entries(pools["ntpc"], limit=30) + fetch_entries(pools["national"], limit=30)

        ntpc_lines, other_lines = [], []
        ntpc_titles, other_titles = [], []
        fallback_lines, fallback_titles = [], []

        seen_local = set()

        for e in entries:
            title = (getattr(e, "title", "") or "").strip()
            raw_link = getattr(e, "link", "") or ""

            # 類別語意過濾（交通排除居家中毒）
            if "交通" in category and not is_traffic_relevant(title):
                continue

            link = resolve_to_canonical_url(raw_link)
            # 去重 key：優先用 link；沒有 link 才用 title
            key = link if link else title
            if not key or key in seen_local:
                continue
            seen_local.add(key)

            cache_key = link if link else f"title::{title}"
            if cache_key in cache:
                continue

            # 第一階段：分欄填滿
            if is_ntpc(title) and len(ntpc_lines) < MAX_NTPC:
                ntpc_lines.append(build_line(title, link))
                ntpc_titles.append(title)
                cache[cache_key] = {"ts": int(time.time())}
                continue

            if (not is_ntpc(title)) and len(other_lines) < MAX_OTHER:
                other_lines.append(build_line(title, link))
                other_titles.append(title)
                cache[cache_key] = {"ts": int(time.time())}
                continue

            # 第二階段：保底補足（不限新北/外縣市）
            if len(fallback_lines) < MIN_TOTAL:
                fallback_lines.append(build_line(title, link))
                fallback_titles.append(title)
                cache[cache_key] = {"ts": int(time.time())}

            # 提前停止條件：分欄都滿 + 保底也夠
            if len(ntpc_lines) >= MAX_NTPC and len(other_lines) >= MAX_OTHER and len(fallback_lines) >= MIN_TOTAL:
                break

        # 如果某一邊太少，用保底補足（避免空到不合理）
        # 先把保底分配到缺口
        def fill_missing(target_list, needed):
            while len(target_list) < needed and fallback_lines:
                target_list.append(fallback_lines.pop(0))

        fill_missing(ntpc_lines, 1)  # 至少 1
        fill_missing(other_lines, 1) # 至少 1

        advice = ai_advice(category, ntpc_titles, other_titles)

        block = f"<b>{html_escape(category)}</b>\n"
        block += "🟦 <b>新北</b>\n" + ("\n".join(ntpc_lines) if ntpc_lines else "（本輪未篩選到符合條件之新北新聞）") + "\n\n"
        block += "🟨 <b>外縣市／全國</b>\n" + ("\n".join(other_lines) if other_lines else "（本輪未篩選到符合條件之其他縣市/全國新聞）") + "\n\n"
        block += f"💡 <b>行政因應建議（soft-fail）</b>\n{html_escape(advice)}"
        blocks.append(block)

    header = f"🗞 <b>新北市教育與交通輿情晨報</b>\n日期：{today}"
    full_msg = header + "\n\n" + "\n\n".join(blocks)

    send_telegram_chunked(full_msg)
    save_cache(cache)
    print("=== END ===")

if __name__ == "__main__":
    try:
        main()
    except Exception:
        traceback.print_exc()
        raise SystemExit(0)
