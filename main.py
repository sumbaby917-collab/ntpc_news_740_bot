import feedparser, requests, datetime, os, urllib.parse, json

# 1. 讀取環境變數 (請確保 GitHub Secrets 中的名稱完全一致)
TELEGRAM_TOKEN = os.getenv('TELEGRAM_TOKEN')
CHAT_ID = os.getenv('TELEGRAM_CHAT_ID')
GEMINI_KEY = os.getenv('GEMINI_API_KEY')

# 符合新北官員需求：新北核心為主，全國動態為輔
KEYWORDS = {
    "交通安全": "新北 交通安全 OR 台灣 交通新制",
    "補習班業務": "新北 補習班 OR 台灣 補教業務",
    "終身學習": "新北 終身學習 OR 台灣 社區大學"
}

def get_ai_analysis(title):
    if not GEMINI_KEY: 
        return "偵錯：未偵測到 API Key。"
    
    # 強制指定 v1 穩定版路徑，解決您遇到的 404/v1beta 問題
    url = f"https://generativelanguage.googleapis.com/v1/models/gemini-1.5-flash:generateContent?key={GEMINI_KEY}"
    
    headers = {'Content-Type': 'application/json'}
    payload = {
        "contents": [{
            "parts": [{
                "text": f"你是一位新北教育官員，請針對新聞「{title}」產出兩句摘要與一項建議。若是外縣市新聞，請分析對新北業務的借鏡價值。請用繁體中文。"
            }]
        }]
    }

    try:
        # 設定 10 秒超時，避免 GitHub Actions 枯等
        response = requests.post(url, headers=headers, json=payload, timeout=10)
        result = response.json()
        
        # 讀取 AI 回傳內容
        if 'candidates' in result:
            return result['candidates'][0]['content']['parts'][0]['text'].strip()
        else:
            error_msg = result.get('error', {}).get('message', '未知錯誤')
            return f"解析異常：{error_msg[:50]}"
    except Exception as e:
        return f"連線異常：{str(e)[:30]}"

def generate_report():
    report = f"📋 *教育輿情報告 (新北核心+全國動態) ({datetime.date.today()})*\n"
    report += "━━━━━━━━━━━━━━━━━━━━\n"
    
    for label, query in KEYWORDS.items():
        report += f"\n🔍 *分類：{label}*\n"
        # 搜尋最近 24 小時的新聞
        safe_query = urllib.parse.quote(f"{query} when:24h")
        rss_url = f"https://news.google.com/rss/search?q={safe_query}&hl=zh-TW&gl=TW&ceid=TW:zh-Hant"
        feed = feedparser.parse(rss_url)
        
        if not feed.entries:
            report += "今日暫無相關新聞。\n"
            continue
            
        # 每個類別抓取前 3 則最相關新聞
        for entry in feed.entries[:3]:
            report += f"📍 *新聞*：{entry.title}\n{get_ai_analysis(entry.title)}\n🔗 [原文連結]({entry.link})\n"
            report += "--------------------\n"
    return report

if __name__ == "__main__":
    final_report = generate_report()
    # 傳送到 Telegram
    requests.post(f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage",
                  data={
                      "chat_id": CHAT_ID, 
                      "text": final_report, 
                      "parse_mode": "Markdown", 
                      "disable_web_page_preview": True
                  })
