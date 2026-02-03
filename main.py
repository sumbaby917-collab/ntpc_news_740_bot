import feedparser, requests, datetime, os, urllib.parse
import google.generativeai as genai

# 1. 讀取環境變數 (您的 Secret 已確認運作正常)
TELEGRAM_TOKEN = os.getenv('TELEGRAM_TOKEN')
CHAT_ID = os.getenv('TELEGRAM_CHAT_ID')
GEMINI_KEY = os.getenv('GEMINI_API_KEY')

# 2. 設定 Gemini (強制使用官方最新穩定格式)
genai.configure(api_key=GEMINI_KEY)
model = genai.GenerativeModel('gemini-1.5-flash')

# 精準關鍵字：鎖定新北政務
KEYWORDS = {
    "交通政務": "新北 交通安全 OR 侯友宜 視察 OR 淡江大橋 通車",
    "教育業務": "新北 補習班 OR 新北 終身學習 OR 技職統測 衝刺",
}

def get_ai_analysis(title):
    if not GEMINI_KEY: return "AI 設定檢查中。"
    
    prompt = f"你是一位新北教育局官員，請針對新聞「{title}」產出兩句摘要與一項建議。若是外縣市新聞，請分析對新北業務的借鏡價值。請用繁體中文。"

    try:
        # 使用官方 SDK 最穩定的生成方式
        response = model.generate_content(prompt)
        if response and response.text:
            return response.text.strip()
        return "摘要：AI 生成中，請點擊原文參考。"
    except Exception as e:
        # 顯示具體錯誤，幫助我們做最後判斷
        return f"解析提示：服務連線中 ({str(e)[:20]})"

def generate_report():
    report = f"📋 *教育輿情報告 (新北核心+全國動態) ({datetime.date.today()})*\n"
    report += "━━━━━━━━━━━━━━━━━━━━\n"
    for label, query in KEYWORDS.items():
        report += f"\n🔍 *類別：{label}*\n"
        safe_query = urllib.parse.quote(f"{query} when:24h")
        rss_url = f"https://news.google.com/rss/search?q={safe_query}&hl=zh-TW&gl=TW&ceid=TW:zh-Hant"
        feed = feedparser.parse(rss_url)
        
        if not feed.entries:
            report += "今日暫無相關新聞。\n"
            continue
            
        for entry in feed.entries[:3]:
            analysis = get_ai_analysis(entry.title)
            report += f"📍 *新聞*：{entry.title}\n💡 {analysis}\n🔗 [原文連結]({entry.link})\n"
            report += "--------------------\n"
    return report

if __name__ == "__main__":
    final_report = generate_report()
    # 傳送到 Telegram，確保 Markdown 格式正確
    requests.post(f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage",
                  data={
                      "chat_id": CHAT_ID, 
                      "text": final_report, 
                      "parse_mode": "Markdown", 
                      "disable_web_page_preview": True
                  })
