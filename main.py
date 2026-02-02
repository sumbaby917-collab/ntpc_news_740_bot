import feedparser, requests, datetime, os, urllib.parse, json

# 1. 讀取環境變數 (您的 Secret 設定已確認無誤)
TELEGRAM_TOKEN = os.getenv('TELEGRAM_TOKEN')
CHAT_ID = os.getenv('TELEGRAM_CHAT_ID')
GEMINI_KEY = os.getenv('GEMINI_API_KEY')

# 精準關鍵字：鎖定新北在地核心政務與交通動態
KEYWORDS = {
    "交通政務": "新北 交通安全 OR 侯友宜 視察 OR 淡江大橋 通車",
    "教育業務": "新北 補習班 OR 新北 終身學習 OR 技職統測 衝刺",
}

def get_ai_analysis(title):
    if not GEMINI_KEY: return "AI 設定檢查中。"
    
    # 【關鍵修正】強制路徑寫死在 v1，徹底解決截圖中的 v1beta 找不到模型問題
    url = f"https://generativelanguage.googleapis.com/v1/models/gemini-1.5-flash:generateContent?key={GEMINI_KEY}"
    headers = {'Content-Type': 'application/json'}
    payload = {
        "contents": [{"parts": [{"text": f"你是一位新北教育局官員，請針對新聞「{title}」產出兩句摘要與一項建議。若是外縣市新聞，請分析對新北業務的借鏡價值。請用繁體中文。"}]}]
    }

    try:
        # 設定 30 秒等待時間，對 AI 絕對充足
        response = requests.post(url, headers=headers, json=payload, timeout=30)
        result = response.json()
        
        # 深度提取文字內容，避開截圖中的 Meta 報錯文字
        if 'candidates' in result and len(result['candidates']) > 0:
            content = result['candidates'][0].get('content', {})
            parts = content.get('parts', [])
            if parts and 'text' in parts[0]:
                return parts[0]['text'].strip()
        
        # 如果 API 回傳其他格式的錯誤，顯示簡短提示
        if 'error' in result:
            return f"解析提示：{result['error'].get('message', 'AI 回應更新中')[:40]}"
            
        return "分析生成中，請點擊原文參閱。"
    except Exception as e:
        return f"連線異常：{str(e)[:15]}"

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
            # 調用強制路徑後的 AI 解析功能
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
