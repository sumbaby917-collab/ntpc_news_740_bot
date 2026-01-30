import feedparser, requests, datetime, os, urllib.parse, google.generativeai as genai

# 1. 初始化設定 (從 GitHub Secrets 讀取)
TELEGRAM_TOKEN = os.getenv('TELEGRAM_TOKEN')
CHAT_ID = os.getenv('TELEGRAM_CHAT_ID')
GEMINI_KEY = os.getenv('GEMINI_API_KEY')

# 2. 設定 AI 模型 (強制鎖定官方標準名稱)
if GEMINI_KEY:
    try:
        genai.configure(api_key=GEMINI_KEY)
        # 注意：引號內必須完全是 gemini-1.5-flash，不帶任何空格或點
        model = genai.GenerativeModel('gemini-1.5-flash')
    except:
        model = None
else:
    model = None

# 業務關鍵字
KEYWORDS = ["新北市 交通安全", "新北市 補習班", "新北市 終身學習"]

def get_ai_analysis(title):
    if not model: return "摘要：AI未配置。\n因應：請檢查設定。"
    # 提供明確的任務指令
    prompt = f"針對新聞標題「{title}」，以新北教育局官員口吻產出：\n摘要：(兩句話內)\n因應：(一項建議)"
    try:
        # 強制呼叫生成內容
        response = model.generate_content(prompt)
        return response.text.strip() if response.text else "解析內容為空"
    except Exception as e:
        # 只顯示前 15 個字，避免錯誤訊息太長干擾日誌
        return f"摘要：分析失敗。\n因應：持續監控。({str(e)[:15]})"

def generate_report():
    report = f"📋 *教育局業務輿情每日報告 ({datetime.date.today()})*\n"
    report += "━━━━━━━━━━━━━━━━━━━━\n"
    for kw in KEYWORDS:
        report += f"\n🔍 *業務類別：{kw.replace('新北市 ', '')}*\n"
        # 處理搜尋網址中的空格問題
        safe_kw = urllib.parse.quote(kw)
        url = f"https://news.google.com/rss/search?q={safe_kw}+when:24h&hl=zh-TW&gl=TW&ceid=TW:zh-Hant"
        feed = feedparser.parse(url)
        if not feed.entries:
            report += "今日暫無新聞。\n"
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
