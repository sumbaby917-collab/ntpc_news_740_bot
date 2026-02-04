import feedparser, requests, datetime, os, urllib.parse, time
from html import escape

import google.generativeai as genai

TELEGRAM_TOKEN = os.getenv('TELEGRAM_TOKEN')
CHAT_ID = os.getenv('TELEGRAM_CHAT_ID')
GEMINI_KEY = os.getenv('GEMINI_API_KEY')

assert TELEGRAM_TOKEN, "缺少 TELEGRAM_TOKEN"
assert CHAT_ID, "缺少 TELEGRAM_CHAT_ID"

genai.configure(api_key=GEMINI_KEY)
model = genai.GenerativeModel('gemini-1.5-flash')  # 若你帳號不支援會報錯，錯誤會在下方顯示

KEYWORDS = {
    "交通政務": "新北 (交通安全 OR 通學巷 OR 淡江大橋 OR 事故 OR 行人) ",
    "教育業務": "新北 (補習班 OR 終身學習 OR 課後照顧 OR 安親 OR 技職) ",
}

def get_best_link(entry):
    # 嘗試找非 news.google.com 的來源連結
    if hasattr(entry, "source") and entry.source and hasattr(entry.source, "href"):
        return entry.source.href
    if hasattr(entry, "links"):
        for l in entry.links:
            href = l.get("href")
            if href and "news.google.com" not in href:
                return href
    return entry.link

def within_last_hours(entry, hours=24):
    now = datetime.datetime.utcnow()
    t = None
    if hasattr(entry, "published_parsed") and entry.published_parsed:
        t = datetime.datetime.fromtimestamp(time.mktime(entry.published_parsed))
    elif hasattr(entry, "updated_parsed") and entry.updated_parsed:
        t = datetime.datetime.fromtimestamp(time.mktime(entry.updated_parsed))
    if not t:
        return True  # 沒時間戳就先放行
    return (now - t) <= datetime.timedelta(hours=hours)

def get_ai_analysis(title):
    if not GEMINI_KEY:
        return "AI：未偵測到 GEMINI_API_KEY。"
    prompt = f"你是一位新北教育局官員，請針對新聞「{title}」產出兩句摘要與一項建議。請用繁體中文。"
    try:
        resp = model.generate_content(prompt)
        return (resp.text or "").strip() or "AI：未產出文本。"
    except Exception as e:
        return f"AI：生成失敗（{type(e).__name__}：{e}）"

def generate_report():
    today = datetime.date.today().isoformat()
    report = f"📋 <b>教育輿情報告（新北核心＋全國動態）({today})</b>\n"
    report += "━━━━━━━━━━━━━━━━━━━━\n"

    for label, query in KEYWORDS.items():
        report += f"\n🔍 <b>類別：{escape(label)}</b>\n"

        safe_query = urllib.parse.quote_plus(query)
        rss_url = f"https://news.google.com/rss/search?q={safe_query}&hl=zh-TW&gl=TW&ceid=TW:zh-Hant"
        feed = feedparser.parse(rss_url)

        if not feed.entries:
            report += "今日暫無相關新聞。\n"
            continue

        seen = set()
        picked = 0
        for entry in feed.entries:
            if not within_last_hours(entry, 24):
                continue
            title = entry.title.strip()
            if title in seen:
                continue
            seen.add(title)

            url = get_best_link(entry)
            analysis = get_ai_analysis(title)

            report += f"📍 <b>新聞</b>：{escape(title)}\n"
            report += f"💡 {escape(analysis)}\n"
            report += f"🔗 <a href=\"{escape(url)}\">原文連結</a>\n"
            report += "--------------------\n"

            picked += 1
            if picked >= 3:
                break

        if picked == 0:
            report += "近24小時未篩到符合條件之新聞。\n"

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
    # 若失敗，印出原因方便你在 logs 直接看到
    if not r.ok:
        print("Telegram error:", r.status_code, r.text)
