import feedparser, requests, datetime, os, urllib.parse, google.generativeai as genai

# 1. 讀取環境變數 (請確認 GitHub Secrets 有 GEMINI_API_KEY)
TELEGRAM_TOKEN = os.getenv('TELEGRAM_TOKEN')
CHAT_ID = os.getenv('TELEGRAM_CHAT_ID')
GEMINI_KEY = os.getenv('GEMINI_API_KEY')

# 2. 初始化 AI (手寫官方完整字串，絕不使用變數代入)
if GEMINI_KEY:
    try:
        genai.configure(api_key=GEMINI_KEY)
        # 此行引號內嚴禁任何空格或贅字
        model = genai.GenerativeModel('gemini-1.5-flash')
    except:
        model = None
else:
    model = None

# 業務關鍵字
KEYWORDS = ["新北市 交通安全", "新北市 補習班", "新北市 終身學習"]

def get_ai_analysis(title):
    if not model: return "摘要：AI未配置。\n因應：請檢查金鑰。"
    prompt = f"你是一位新北官員，請針對「{title}」產出兩句摘要與一項行政建議。"
    try:
        response = model.generate_content(prompt)
        return response.text.strip() if response.text else "解析內容為空"
    except Exception as e:
        # 只顯示前 15 個字，用於抓出是否還有 404 字眼
        return f"摘要：分析失敗。\n因應：持續監控。({str(e)[:15]})"

def generate_report():
    report = f"📋 *教育局輿情報告 ({datetime.date.today()})*\n"
    report += "━━━━━━━━━━━━━━━━━━━━\n"
    for kw in KEYWORDS:
        report += f"\n🔍 *業務：{kw.replace('新北市 ', '')}*\n"
        url = f"https://news.google.com/rss/search?q={urllib.parse.quote(kw)}+when:24h&hl=zh-TW&gl=TW&ceid=TW:zh-Hant"
        feed = feedparser.parse(url)
        if not feed.entries:
            report += "今日暫無新聞。\n"
            continue
        for entry in feed.entries[:2]:
            report += f"📍 *新聞*：{entry.title}\n{get_ai_analysis(entry.title)}\n🔗 [原文連結]({entry.link})\n"
            report += "--------------------\n"
    return report

if __name__ == "__main__":
    final_report = generate_report()
    requests.post(f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage",
                  data={"chat_id": CHAT_ID, "text": final_report, "parse_mode": "Markdown", "disable_web_page_preview": True})
