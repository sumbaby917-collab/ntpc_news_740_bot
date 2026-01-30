import feedparser, requests, datetime, os, urllib.parse, google.generativeai as genai

# 1. 讀取金鑰 (GitHub Secrets)
TELEGRAM_TOKEN = os.getenv('TELEGRAM_TOKEN')
CHAT_ID = os.getenv('TELEGRAM_CHAT_ID')
GEMINI_KEY = os.getenv('GEMINI_API_KEY')

# 2. 配置 AI (強制使用穩定版 API 路徑)
if GEMINI_KEY:
    try:
        genai.configure(api_key=GEMINI_KEY)
        # 修正：不帶 models/ 前綴，讓 SDK 自動處理，並確認模型名稱純淨
        model = genai.GenerativeModel('gemini-1.5-flash')
    except Exception as e:
        model = None
        print(f"初始化失敗: {e}")
else:
    model = None

# 業務關鍵字
KEYWORDS = ["新北市 交通安全", "新北市 補習班", "新北市 終身學習"]

def get_ai_analysis(title):
    if not model: return "摘要：AI助理尚未就緒。\n因應：請檢查 API 設定。"
    # 提供明確的任務指令
    prompt = f"你是一位新北市政府官員。請針對新聞標題「{title}」，簡短提供：\n摘要：(兩句話內)\n因應：(一項具體行政作為)"
    try:
        # 呼叫生成內容
        response = model.generate_content(prompt)
        return response.text.strip() if response.text else "無法生成內容"
    except Exception as e:
        # 輸出關鍵錯誤訊息以利最後判斷
        return f"摘要：分析暫時中斷。\n因應：持續監控輿情。({str(e)[:40]})"

def generate_report():
    report = f"📋 *教育局業務輿情每日報告 ({datetime.date.today()})*\n"
    report += "━━━━━━━━━━━━━━━━━━━━\n"
    for kw in KEYWORDS:
        report += f"\n🔍 *業務類別：{kw.replace('新北市 ', '')}*\n"
        # 處理搜尋網址中的空格
        safe_kw = urllib.parse.quote(kw)
        url = f"https://news.google.com/rss/search?q={safe_kw}+when:24h&hl=zh-TW&gl=TW&ceid=TW:zh-Hant"
        feed = feedparser.parse(url)
        if not feed.entries:
            report += "今日暫無相關新聞。\n"
            continue
        # 每個類別取前 2 則新聞
        for entry in feed.entries[:2]:
            ai_content = get_ai_analysis(entry.title)
            report += f"📍 *新聞*：{entry.title}\n{ai_content}\n🔗 [原文連結]({entry.link})\n"
            report += "--------------------\n"
    return report

if __name__ == "__main__":
    final_report = generate_report()
    # 透過 Telegram Bot API 發送
    requests.post(
        f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage",
        data={"chat_id": CHAT_ID, "text": final_report, "parse_mode": "Markdown", "disable_web_page_preview": True}
    )
