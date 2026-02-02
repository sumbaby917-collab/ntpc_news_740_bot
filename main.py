import feedparser, requests, datetime, os, urllib.parse, google.generativeai as genai

# 1. 讀取密鑰
TELEGRAM_TOKEN = os.getenv('TELEGRAM_TOKEN')
CHAT_ID = os.getenv('TELEGRAM_CHAT_ID')
GEMINI_KEY = os.getenv('GEMINI_API_KEY')

# 2. 初始化 AI
if GEMINI_KEY:
    try:
        genai.configure(api_key=GEMINI_KEY)
        model = genai.GenerativeModel('gemini-1.5-flash')
    except:
        model = None
else:
    model = None

# 調整後的擴大搜尋關鍵字：新北 + 全台
KEYWORDS = {
    "交通安全": "新北 交通安全 OR 台灣 交通安全",
    "補習班業務": "新北 補習班 OR 台灣 補習班稽查",
    "終身學習": "新北 終身學習 OR 社區大學 課程"
}

def get_ai_analysis(title):
    if not model: return "摘要：AI未配置。\n因應：請檢查金鑰。"
    # 提醒 AI 區分地區
    prompt = f"針對新聞「{title}」，以教育局官員口吻產出兩句摘要與一項建議。若為外縣市新聞，請分析其對新北的借鏡意義。請用繁體中文。"
    try:
        response = model.generate_content(prompt)
        return response.text.strip() if response.text else "AI回應為空"
    except Exception as e:
        return f"偵錯：{str(e)}"

def generate_report():
    report = f"📋 *教育輿情每日報告 (新北+全國) ({datetime.date.today()})*\n"
    report += "━━━━━━━━━━━━━━━━━━━━\n"
    for label, query in KEYWORDS.items():
        report += f"\n🔍 *分類：{label}*\n"
        # 搜尋最近 24 小時內的新聞
        safe_query = urllib.parse.quote(f"{query} when:24h")
        url = f"https://news.google.com/rss/search?q={safe_query}&hl=zh-TW&gl=TW&ceid=TW:zh-Hant"
        feed = feedparser.parse(url)
        
        if not feed.entries:
            report += "今日暫無相關新聞。\n"
            continue
            
        # 每個分類抓前 3 則，確保涵蓋面廣
        for entry in feed.entries[:3]:
            report += f"📍 *新聞*：{entry.title}\n{get_ai_analysis(entry.title)}\n🔗 [原文連結]({entry.link})\n"
            report += "--------------------\n"
    return report

if __name__ == "__main__":
    final_report = generate_report()
    requests.post(f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage",
                  data={"chat_id": CHAT_ID, "text": final_report, "parse_mode": "Markdown", "disable_web_page_preview": True})
