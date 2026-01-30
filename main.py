import feedparser, requests, datetime, os, urllib.parse, google.generativeai as genai

# 1. 讀取並確認金鑰
api_key = os.getenv('GEMINI_API_KEY')
TELEGRAM_TOKEN = os.getenv('TELEGRAM_TOKEN')
CHAT_ID = os.getenv('TELEGRAM_CHAT_ID')

if api_key:
    genai.configure(api_key=api_key)
    # 使用 1.5-flash 模型，速度最快且免費額度高
    model = genai.GenerativeModel('gemini-1.5-flash')
else:
    model = None

# 2. 業務搜尋關鍵字
KEYWORDS = ["新北市 交通安全", "新北市 補習班", "新北市 終身學習"]

def get_ai_analysis(title):
    if not model:
        return "摘要：API未設定。\n因應：請檢查系統環境。"
    
    # 強化指令，要求 AI 必須產出內容
    prompt = f"你現在是新北市教育局官員。針對新聞標題「{title}」，請直接產出兩行文字：一行是兩句話的『摘要』，一行是具體的『因應作為』。不要有其他廢話。"
    
    try:
        response = model.generate_content(prompt)
        # 確保有抓到文字
        if response and response.text:
            return response.text.strip()
        return "摘要：分析模型暫無回應。\n因應：已報請資訊人員維護。"
    except Exception as e:
        return f"摘要：分析過程發生錯誤。\n因應：持續監控輿情發展。({str(e)[:20]})"

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

# 3. 執行發送
if __name__ == "__main__":
    final_report = generate_report()
    requests.post(
        f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage",
        data={"chat_id": CHAT_ID, "text": final_report, "parse_mode": "Markdown", "disable_web_page_preview": True}
    )
