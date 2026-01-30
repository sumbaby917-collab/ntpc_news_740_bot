import feedparser, requests, datetime, os, urllib.parse, google.generativeai as genai

# 1. 讀取密鑰與設定
TELEGRAM_TOKEN = os.getenv('TELEGRAM_TOKEN')
CHAT_ID = os.getenv('TELEGRAM_CHAT_ID')
GEMINI_KEY = os.getenv('GEMINI_API_KEY')

# 2. 精確配置 AI 模型 (鎖定穩定路徑)
if GEMINI_KEY:
    try:
        genai.configure(api_key=GEMINI_KEY)
        # 直接使用官方定義的模型名稱，避免帶入 API 版本的變數干擾
        model = genai.GenerativeModel('gemini-1.5-flash')
    except:
        model = None
else:
    model = None

# 業務關鍵字
KEYWORDS = ["新北市 交通安全", "新北市 補習班", "新北市 終身學習"]

def get_ai_analysis(title):
    if not model: return "摘要：AI助理配置未完成。\n因應：請檢查設定環境。"
    prompt = f"針對新聞「{title}」，以新北教育局業務主管口吻產出兩句摘要與一項具體行政建議。"
    try:
        # 呼叫生成內容，不帶額外版本參數
        response = model.generate_content(prompt)
        return response.text.strip() if response.text else "解析內容暫無回應"
    except Exception as e:
        # 若失敗則輸出縮短後的報錯，用於最後確認
        return f"摘要：分析暫時中斷。\n因應：持續監控。({str(e)[:35]})"

def generate_report():
    report = f"📋 *教育局業務輿情每日報告 ({datetime.date.today()})*\n"
    report += "━━━━━━━━━━━━━━━━━━━━\n"
    for kw in KEYWORDS:
        report += f"\n🔍 *業務類別：{kw.replace('新北市 ', '')}*\n"
        # 修正搜尋網址中的空格問題
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
    requests.post(
        f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage",
        data={"chat_id": CHAT_ID, "text": final_report, "parse_mode": "Markdown", "disable_web_page_preview": True}
    )
