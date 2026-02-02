import feedparser, requests, datetime, os, urllib.parse, json

# 1. 讀取密鑰
TELEGRAM_TOKEN = os.getenv('TELEGRAM_TOKEN')
CHAT_ID = os.getenv('TELEGRAM_CHAT_ID')
GEMINI_KEY = os.getenv('GEMINI_API_KEY')

# 精準關鍵字：鎖定新北與全國交安動態
KEYWORDS = {
    "交通安全": "新北 交通安全 OR 台灣 交通新制",
    "補習班業務": "新北 補習班 OR 台灣 補教業務",
    "終身學習": "新北 終身學習 OR 台灣 社區大學"
}

def get_ai_analysis(title):
    if not GEMINI_KEY: return "偵錯：未偵測到金鑰"
    
    # 徹底解決版本衝突的核心：直接連線穩定版接口
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
        response = requests.post(url, headers=headers, json=payload, timeout=20)
        result = response.json()
        # 這是抓取 AI 回傳文字的最穩定寫法
        if 'candidates' in result and result['candidates']:
            return result['candidates'][0]['content']['parts'][0]['text'].strip()
        else:
            return "摘要：AI服務連線中，請參考原文連結。"
    except:
        return "摘要：網路連線稍慢，建議查看原文。"

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
            report += f"📍 *新聞*：{entry.title}\n摘要：{get_ai_analysis(entry.title)}\n🔗 [原文連結]({entry.link})\n"
            report += "--------------------\n"
    return report

if __name__ == "__main__":
    final_report = generate_report()
    # 確保傳送到 Telegram，關閉網頁預覽
    requests.post(f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage",
                  data={"chat_id": CHET_ID, "text": final_report, "parse_mode": "Markdown", "disable_web_page_preview": True})
