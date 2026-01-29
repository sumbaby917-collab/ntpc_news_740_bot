import feedparser, requests, datetime, os, google.generativeai as genai

# 讀取金鑰
TELEGRAM_TOKEN = os.getenv('TELEGRAM_TOKEN')
CHAT_ID = os.getenv('TELEGRAM_CHAT_ID')
genai.configure(api_key=os.getenv('GEMINI_API_KEY'))
model = genai.GenerativeModel('gemini-1.5-flash')

# 搜尋關鍵字
KEYWORDS = ["新北市 交通安全", "新北市 補習班", "新北市 終身學習"]

def get_ai_analysis(title):
    prompt = f"你是一位新北市教育局業務主管。針對新聞「{title}」，請產出『摘要：(兩句話)』與『因應：(行政作為)』。"
    try:
        response = model.generate_content(prompt)
        return response.text
    except:
        return "摘要：新聞處理中。\n因應：持續監控輿情。"

def generate_report():
    report = f"📋 *教育局業務輿情每日報告 ({datetime.date.today()})*\n"
    for kw in KEYWORDS:
        report += f"\n🔍 *業務類別：{kw.replace('新北市 ', '')}*\n"
        feed = feedparser.parse(f"https://news.google.com/rss/search?q={kw}+when:24h&hl=zh-TW&gl=TW&ceid=TW:zh-Hant")
        for entry in feed.entries[:2]:
            report += f"📍 *新聞*：{entry.title}\n{get_ai_analysis(entry.title)}\n🔗 [原文連結]({entry.link})\n"
    return report

# 發送到 Telegram
requests.post(f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage", 
              data={"chat_id": CHAT_ID, "text": generate_report(), "parse_mode": "Markdown", "disable_web_page_preview": True})
