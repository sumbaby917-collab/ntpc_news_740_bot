import feedparser, requests, datetime, os, urllib.parse, google.generativeai as genai

# 1. 初始化 (從 GitHub Secrets 讀取)
TELEGRAM_TOKEN = os.getenv('TELEGRAM_TOKEN')
CHAT_ID = os.getenv('TELEGRAM_CHAT_ID')
GEMINI_KEY = os.getenv('GEMINI_API_KEY')

# 2. 設定模型 (嚴格鎖定官方字串)
def setup_model():
    if not GEMINI_KEY: return None
    try:
        genai.configure(api_key=GEMINI_KEY)
        # 直接指定完整名稱，確保不被截斷
        return genai.GenerativeModel('gemini-1.5-flash')
    except:
        return None

model = setup_model()
KEYWORDS = ["新北市 交通安全", "新北市 補習班", "新北市 終身學習"]

def get_ai_analysis(title):
    if not model: return "摘要：AI未配置。\n因應：請檢查設定。"
    prompt = f"針對新聞「{title}」，以官員口吻產出：摘要(兩句)與因應建議。"
    try:
        response = model.generate_content(prompt)
        return response.text.strip() if response.text else "解析內容為空"
    except Exception as e:
        # 顯示完整錯誤以便最後判斷
        return f"摘要：分析失敗。\n因應：持續監控。({str(e)})"

def generate_report():
    report = f"📋 *教育局業務輿情每日報告 ({datetime.date.today()})*\n"
    report += "━━━━━━━━━━━━━━━━━━━━\n"
    for kw in KEYWORDS:
        report += f"\n🔍 *業務類別：{kw.replace('新北市 ', '')}*\n"
        safe_kw = urllib.parse.quote(kw)
        url = f"https://news.google.com/rss/search?q={safe_kw}+when:24h&hl=zh-TW&gl=TW&ceid=TW:zh-Hant"
        feed = feedparser.parse(url)
        if not feed.entries:
            report += "今日暫無新聞。\n"
            continue
        for entry in feed.entries[:2]:
            ai_content = get_ai_analysis(entry.title)
            report += f"📍 *新聞*：{entry.title}\n{ai_content}\n🔗 [原文連結]({entry.link})\n"
            report += "--------------------\n"
    return report

if __name__ == "__main__":
    final_report = generate_report()
    requests.post(f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage",
                  data={"chat_id": CHAT_ID, "text": final_report, "parse_mode": "Markdown", "disable_web_page_preview": True})
