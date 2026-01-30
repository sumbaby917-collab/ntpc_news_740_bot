import feedparser, requests, datetime, os, urllib.parse, google.generativeai as genai

# 1. 初始化設定 (從 GitHub Secrets 讀取)
TELEGRAM_TOKEN = os.getenv('TELEGRAM_TOKEN')
CHAT_ID = os.getenv('TELEGRAM_CHAT_ID')
GEMINI_KEY = os.getenv('GEMINI_API_KEY')

# 2. 設定模型 (嚴格校對模型名稱)
if GEMINI_KEY:
    try:
        genai.configure(api_key=GEMINI_KEY)
        # 此處引號內必須只有 17 個字元：gemini-1.5-flash
        model = genai.GenerativeModel('gemini-1.5-flash')
    except:
        model = None
else:
    model = None

# 業務關鍵字
KEYWORDS = ["新北市 交通安全", "新北市 補習班", "新北市 終身學習"]

def get_ai_analysis(title):
    if not model: return "摘要：AI未啟動。\n因應：請檢查設定。"
    prompt = f"針對新聞「{title}」，以官員口吻產出兩句摘要與一項建議。"
    try:
        response = model.generate_content(prompt)
        return response.text.strip() if response.text else "解析內容為空"
    except Exception as e:
        # 回傳精簡錯誤代碼以利最後確認
        return f"摘要：分析暫時中斷。\n因應：持續監控。({str(e)[:30]})"

def generate_report():
    report = f"📋 *教育局業務輿情每日報告 ({datetime.date.today()})*\n"
    report += "━━━━━━━━━━━━━━━━━━━━\n"
    for kw in KEYWORDS:
        report += f"\n🔍 *業務類別：{kw.replace('新北市 ', '')}*\n"
        # 修正網址空格問題
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
