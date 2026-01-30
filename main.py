import feedparser, requests, datetime, os, urllib.parse, google.generativeai as genai

# 1. 初始化設定 (從 GitHub Secrets 讀取)
TELEGRAM_TOKEN = os.getenv('TELEGRAM_TOKEN')
CHAT_ID = os.getenv('TELEGRAM_CHAT_ID')
GEMINI_KEY = os.getenv('GEMINI_API_KEY')

# 2. 設定 AI 模型 (嚴格修正模型名稱)
if GEMINI_KEY:
    try:
        genai.configure(api_key=GEMINI_KEY)
        # 這裡必須只有名稱，不能有 is 或其他空格
        model = genai.GenerativeModel('gemini-1.5-flash')
    except Exception as e:
        model = None
        print(f"AI 配置失敗: {e}")
else:
    model = None

# 業務關鍵字
KEYWORDS = ["新北市 交通安全", "新北市 補習班", "新北市 終身學習"]

def get_ai_analysis(title):
    if not model:
        return "摘要：AI未啟動。\n因應：請檢查 API 設定。"
    
    prompt = f"你是一位新北市教育局官員。針對新聞「{title}」，請簡潔產出：\n摘要：(兩句話)\n因應：(行政具體作為)"
    
    try:
        response = model.generate_content(prompt)
        if response and response.text:
            return response.text.strip()
        return "摘要：模型未回傳文字。\n因應：請手動檢視新聞內容。"
    except Exception as e:
        # 這裡會捕捉模型名稱是否正確
        return f"摘要：分析失敗。\n因應：持續監控輿情。({str(e)[:40]})"

def generate_report():
    report = f"📋 *教育局業務輿情每日報告 ({datetime.date.today()})*\n"
    report += "━━━━━━━━━━━━━━━━━━━━\n"
    
    for kw in KEYWORDS:
        report += f"\n🔍 *業務類別：{kw.replace('新北市 ', '')}*\n"
        safe_kw = urllib.parse.quote(kw)
        url = f"https://news.google.com/rss/search?q={safe_kw}+when:24h&hl=zh-TW&gl=TW&ceid=TW:zh-Hant"
        feed = feedparser.parse(url)
        
        if not feed.entries:
            report += "今日暫無相關新聞。\n"
            continue
            
        for entry in feed.entries[:2]:
            ai_content = get_ai_analysis(entry.title)
            report += f"📍 *新聞*：{entry.title}\n{ai_content}\n🔗 [原文連結]({entry.link})\n"
            report += "--------------------\n"
    return report

# 3. 發送至 Telegram
if __name__ == "__main__":
    final_report = generate_report()
    requests.post(
        f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage",
        data={"chat_id": CHAT_ID, "text": final_report, "parse_mode": "Markdown", "disable_web_page_preview": True}
    )
