import feedparser, requests, datetime, os, urllib.parse, google.generativeai as genai

# 1. 讀取金鑰 (GitHub Secrets)
TELEGRAM_TOKEN = os.getenv('TELEGRAM_TOKEN')
CHAT_ID = os.getenv('TELEGRAM_CHAT_ID')
GEMINI_KEY = os.getenv('GEMINI_API_KEY')

# 2. 精確配置 (直接宣告完整字串，不透過任何變數)
if GEMINI_KEY:
    try:
        genai.configure(api_key=GEMINI_KEY)
        # 此處嚴禁修改，必須完整顯示：gemini-1.5-flash
        model = genai.GenerativeModel('gemini-1.5-flash')
    except:
        model = None
else:
    model = None

# 業務搜尋關鍵字
KEYWORDS = ["新北市 交通安全", "新北市 補習班", "新北市 終身學習"]

def get_ai_analysis(title):
    if not model: return "摘要：AI未配置。\n因應：請檢查設定。"
    prompt = f"針對新聞「{title}」，以新北官員口吻產出兩句摘要與一項建議。"
    try:
        # 直接執行內容生成
        response = model.generate_content(prompt)
        return response.text.strip() if response.text else "AI回應內容為空"
    except Exception as e:
        # 捕捉精確錯誤並顯示前 20 字，用於判斷 404
        return f"摘要：分析失敗。\n因應：持續監控。({str(e)[:20]})"

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
            report += f"📍 *新聞*：{entry.title}\n{get_ai_analysis(entry.title)}\n🔗 [原文連結]({entry.link})\n"
            report += "--------------------\n"
    return report

if __name__ == "__main__":
    final_report = generate_report()
    requests.post(f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage",
                  data={"chat_id": CHAT_ID, "text": final_report, "parse_mode": "Markdown", "disable_web_page_preview": True})
