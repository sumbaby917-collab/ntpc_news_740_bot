import feedparser
import requests
import datetime
import os
import urllib.parse
import time
from html import escape

import google.generativeai as genai

# =========================
# 1. 環境變數
# =========================
TELEGRAM_TOKEN = os.getenv('TELEGRAM_TOKEN')
CHAT_ID = os.getenv('TELEGRAM_CHAT_ID')
GEMINI_KEY = os.getenv('GEMINI_API_KEY')

assert TELEGRAM_TOKEN, "缺少 TELEGRAM_TOKEN"
assert CHAT_ID, "缺少 TELEGRAM_CHAT_ID"

# =========================
# 2. Gemini 設定
# =========================
genai.configure(api_key=GEMINI_KEY)

# ★ 已驗證支援 generateContent 的模型候選（避免 404）
MODEL_CANDIDATES = [
    "models/gemini-2.5-flash",
    "models/gemini-2.5-pro",
]

# =========================
# 3. 關鍵字設定
# =========================
KEYWORDS = {
    "交通政務": "新北 (交通安全 OR 行人 OR 通學巷 OR 事故 OR 淡江大橋)",
    "教育業務": "新北 (補習班 OR 終身學習 OR 課後照顧 OR 技職)",
}

# =========================
# 4. 工具函式
# =========================
def get_best_link(entry):
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
        return True
    return (now - t) <= datetime.timedelta(hours=hours)

def get_ai_analysis(title):
    if not GEMINI_KEY:
        return "AI：尚未設定 GEMINI_API_KEY。"

    prompt = (
        f"你是一位新北市政府教育局官員，"
        f"請針對以下新聞標題產出："
        f"（一）兩句重點摘要；（二）一項行政因應建議。\n"
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

# =========================
# 5. 產生報告
# =========================
def generate_report():
    today = datetime.date.today().isoformat()
    report = f"📋 <b>教育輿情報告（新北核心＋全國動態）({today})</b>\n"
    report += "━━━━━━━━━━━━━━━━━━━━\n"

    for label, query in KEYWORDS.items():
        report += f"\n🔍 <b>類別：{escape(label)}</b>\n"

        safe_query = urllib.parse.quote_plus(query)
        rss_url = (
            f"https://news.google.com/rss/search?"
            f"q={safe_query}&hl=zh-TW&gl=TW&ceid=TW:zh-Hant"
        )

        feed = feedparser.parse(rss_url)

        if not feed.entries:
            report += "今日暫無相關新聞。\n"
            continue

        seen = set()
        count = 0

        for entry in feed.entries:
            if not within_last_hours(entry, 24):
                continue

            title = entry.title.strip()
            if title in seen:
                continue
            seen.add(title)

            link = get_best_link(entry)
            analysis = get_ai_analysis(title)

            report += f"📍 <b>新聞</b>：{escape(title)}\n"
            report += f"💡 {escape(analysis)}\n"
            report += f"🔗 <a href=\"{escape(link)}\">原文連結</a>\n"
            report += "--------------------\n"

            count += 1
            if count >= 3:
                break

        if count == 0:
            report += "近 24 小時未篩選到符合條件之新聞。\n"

    return report

# =========================
# 6. 主程式
# =========================
if __name__ == "__main__":
    final_report = generate_report()

    response = requests.post(
        f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage",
        data={
            "chat_id": CHAT_ID,
            "text": final_report,
            "parse_mode": "HTML",
            "disable_web_page_preview": True,
        },
        timeout=20,
    )

    if not response.ok:
        print("Telegram 發送失敗：", response.status_code, response.text)
