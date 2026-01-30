import feedparser, requests, datetime, os, urllib.parse, google.generativeai as genai

# 1. 初始化設定 (從 GitHub Secrets 讀取)
TELEGRAM_TOKEN = os.getenv('TELEGRAM_TOKEN')
CHAT_ID = os.getenv('TELEGRAM_CHAT_ID')
GEMINI_KEY = os.getenv('GEMINI_API_KEY')

# 2. 設定 AI 模型 (修正 404 models 錯誤)
if GEMINI_KEY:
    try:
        genai.configure(api_key=GEMINI_KEY)
        # 確保模型名稱完全正確
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
    
    # 簡化 Prompt 確保穩定輸出
    prompt = f"請針對這則新聞標題撰寫摘要與因應建議。\n標題：{title}\n格式：\n摘要：(兩句話)\n因應：(具體作為)"
    
    try:
        response = model.generate_content(prompt)
        if response and response.text:
            return response.text.strip()
        return "摘要：模型回傳空白。\n因應：請檢查搜尋結果。"
    except Exception as e:
        # 如果失敗，回報錯誤代碼幫助除錯
        return f"摘要：分析失敗。\n因應：持續監控。({str(e)[:30]})"

def generate_report():
    report = f"📋 *教育局業務輿情每日報告 ({datetime.date.today()})*\n"
    report += "━━━━━━━━━━━━━━━━━━━━\n"
    
    for kw in KEYWORDS:
        report += f"\n🔍 *業務類別：{kw.replace('新北市 ', '')}*\n"
        # 處理網址空格編碼
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
