import feedparser, requests, datetime, os, urllib.parse, json

# 1. 讀取環境變數 (Secrets 已確認運作正常)
TELEGRAM_TOKEN = os.getenv('TELEGRAM_TOKEN')
CHAT_ID = os.getenv('TELEGRAM_CHAT_ID')
GEMINI_KEY = os.getenv('GEMINI_API_KEY')

# 符合新北官員需求之搜尋邏輯
KEYWORDS = {
    "交通安全": "新北 交通安全 OR 台灣 交通新制",
    "補習班業務": "新北 補習班 OR 台灣 補教法規",
    "終身學習": "新北 終身學習 OR 台灣 社區大學"
}

def get_ai_analysis(title):
    if not GEMINI_KEY: return "AI 金鑰未設定。"
    
    # 鎖定 v1 穩定路徑
    url = f"https://generativelanguage.googleapis.com/v1/models/gemini-1.5-flash:generateContent?key={GEMINI_KEY}"
    headers = {'Content-Type': 'application/json'}
    payload = {
        "contents": [{"parts": [{"text": f"你是一位新北教育官員，請針對新聞「{title}」產出兩句摘要與一項建議。若是外縣市新聞，請分析對新北業務的借鏡價值。請用繁體中文。"}]}]
    }

    try:
        # 設定 30 秒等待時間，對 AI 生成絕對充足
        response = requests.post(url, headers=headers, json=payload, timeout=30)
        result = response.json()
        
        # 【核心修正】深度解析 JSON 標籤，解決「分析生成中」的顯示問題
        if 'candidates' in result and result['candidates']:
            first_candidate = result['candidates'][0]
            if 'content' in first_candidate and 'parts' in first_candidate['content']:
                return first_candidate['content']['parts'][0]['text'].strip()
        
        # 偵錯：若回傳異常，顯示錯誤訊息
        if 'error' in result:
            return f"API 提示：{result['error'].get('message', '未知錯誤')[:50]}"
            
        return "AI 解析完成但格式不符。"
    except Exception as e:
        return f"連線異常：{str(e)[:20]}"

def generate_report():
    report = f"📋 *教育輿情報告 (新北核心+全國動態) ({datetime.date.today()})*\n"
    report += "━━━━━━━━━━━━━━━━━━━━\n"
    for label, query in KEYWORDS.items():
        report += f"\n🔍 *分類：{label}*\n"
        safe_query = urllib.parse.quote(f"{query} when:24h")
        rss_url = f"https://news.google.com/rss/search?q={safe_query}&hl=zh-TW&gl=TW&ceid=TW:zh-Hant"
        feed = feedparser.parse(rss_url)
        
        if not feed.entries:
            report += "今日暫無相關新聞。\n"
            continue
            
        for entry in feed.entries[:3]:
            # 調用優化後的解析功能
            analysis = get_ai_analysis(entry.title)
            report += f"📍 *新聞*：{entry.title}\n💡 {analysis}\n🔗 [原文連結]({entry.link})\n"
            report += "--------------------\n"
    return report

if __name__ == "__main__":
    final_report = generate_report()
    # 確保傳送到 Telegram，Markdown 格式正確且關閉網頁預覽
    requests.post(f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage",
                  data={
                      "chat_id": CHAT_ID, 
                      "text": final_report, 
                      "parse_mode": "Markdown", 
                      "disable_web_page_preview": True
                  })
