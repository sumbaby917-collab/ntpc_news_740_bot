import feedparser, requests, datetime, os, urllib.parse, google.generativeai as genai

# 1. 讀取密鑰
TELEGRAM_TOKEN = os.getenv('TELEGRAM_TOKEN')
CHAT_ID = os.getenv('TELEGRAM_CHAT_ID')
GEMINI_KEY = os.getenv('GEMINI_API_KEY')

# 2. 初始化 AI (強制指定穩定版 REST 通道，解決 404 問題)
if GEMINI_KEY:
    try:
        # 關鍵修正：加入 transport='rest' 鎖定連線路徑
        genai.configure(api_key=GEMINI_KEY, transport='rest')
        model = genai.GenerativeModel('gemini-1.5-flash')
    except:
        model = None
else:
    model = None

# 符合您的最新需求：新北為主，全國為輔
KEYWORDS = {
    "交通安全": "新北 交通安全 OR 台灣 交通新制",
    "補習班業務": "新北 補習班 OR 台灣 補習班稽查",
    "終身學習": "新北 終身學習 OR 台灣 社區大學"
}

def get_ai_analysis(title):
    if not model: return "摘要：AI未就緒。\n建議：請確認密鑰設定。"
    # 提醒 AI 扮演新北官員，並分析全國借鏡意義
    prompt = f"你是一位新北教育官員，請針對新聞「{title}」產出兩句摘要與一項建議。若是外縣市新聞，請分析對新北業務的借鏡價值。請用繁體中文。"
    try:
        response = model.generate_content(prompt)
        return response.text.strip() if response.text else "解析成功但無回傳"
    except Exception as e:
        return f"診斷訊息：{str(e)[:50]}"

def generate_report():
    report = f"📋 *教育輿情報告 (新北+全國) ({datetime.date.today()})*\n"
    report += "━━━━━━━━━━━━━━━━━━━━\n"
    for label, query in KEYWORDS.items():
        report += f"\n🔍 *類別：{label}*\n"
        safe_query = urllib.parse.quote(f"{query} when:24h")
        url = f"https://news.google.com/rss/search?q={safe_query}&hl=zh-TW&gl=TW&ceid=TW:zh-Hant"
        feed = feedparser.parse(url)
        
        if not feed.entries:
            report += "今日暫無相關新聞。\n"
            continue
            
        for entry in feed.entries[:3]:
            report += f"📍 *新聞*：{entry.title}\n{get_ai_analysis(entry.title)}\n🔗 [原文連結]({entry.link})\n"
            report += "--------------------\n"
    return report

if __name__ == "__main__":
    final_report = generate_report()
    requests.post(f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage",
                  data={"chat_id": CH_ID, "text": final_report, "parse_mode": "Markdown", "disable_web_page_preview": True})
