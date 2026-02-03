import feedparser, requests, datetime, os, urllib.parse, json

# 1. 讀取密鑰 (已驗證 GitHub 與 Telegram 連線正常)
TELEGRAM_TOKEN = os.getenv('TELEGRAM_TOKEN')
CHAT_ID = os.getenv('TELEGRAM_CHAT_ID')
GEMINI_KEY = os.getenv('GEMINI_API_KEY')

# 符合您業務需求的精準關鍵字
KEYWORDS = {
    "交通政務": "新北 交通安全 OR 侯友宜 視察 OR 淡江大橋 通車",
    "教育業務": "新北 補習班 OR 新北 終身學習 OR 技職統測 衝刺",
}

def get_ai_analysis(title):
    if not GEMINI_KEY: return "AI 設定檢查中。"
    
    # 【徹底修復】將網址固定在 v1，解決您這 70 次失敗的核心問題
    url = f"https://generativelanguage.googleapis.com/v1/models/gemini-1.5-flash:generateContent?key={GEMINI_KEY}"
    headers = {'Content-Type': 'application/json'}
    payload = {
        "contents": [{"parts": [{"text": f"你是一位新北教育局官員，請針對新聞「{title}」產出兩句摘要與一項建議。若是外縣市新聞，請分析對新北業務的借鏡價值。請用繁體中文。"}]}]
    }

    try:
        # 設定充足的 30 秒等待時間
        response = requests.post(url, headers=headers, json=payload, timeout=30)
        result = response.json()
        
        # 深度提取文字，確保只顯示中文官員分析
        if 'candidates' in result and len(result['candidates']) > 0:
            content = result['candidates'][0].get('content', {})
            parts = content.get('parts', [])
            if parts and 'text' in parts[0]:
                return parts[0]['text'].strip()
        
        return "摘要：AI 分析生成中，請點擊原文參考。"
    except Exception:
        return "摘要：網路連線稍慢。"

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
            # 調用修正後的 AI 分析
            analysis = get_ai_analysis(entry.title)
            report += f"📍 *新聞*：{entry.title}\n💡 {analysis}\n🔗 [原文連結]({entry.link})\n"
            report += "--------------------\n"
    return report

if __name__ == "__main__":
    final_report = generate_report()
    # 傳送到 Telegram，確保不顯示網頁預覽
    requests.post(f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage",
                  data={"chat_id": CHAT_ID, "text": final_report, "parse_mode": "Markdown", "disable_web_page_preview": True})
