import os, json, time, datetime, traceback, urllib.parse, requests, feedparser
from zoneinfo import ZoneInfo

# ======================
# 基本設定
# ======================
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID")

CACHE_FILE = "sent_cache.json"
CACHE_DAYS = 5

MAX_NTPC = 2
MAX_OTHER = 2
MIN_TOTAL = 3
TG_MAX = 3500

# ======================
# 台灣時間鎖（07:40-07:49 才自動送）
# ======================
def taipei_time_lock():
    """
    自動排程：只允許台灣時間 07:40～07:49 發送（10 分鐘容錯窗）
    並用 state/last_sent_date.txt 防止同日重複發送

    手動 workflow_dispatch：允許立即發送（用來測試）
    """
    tz = ZoneInfo("Asia/Taipei")
    now = datetime.datetime.now(tz)
    today = now.date().isoformat()

    # 容錯窗：07:40 - 07:49
    in_window = (now.hour == 7 and 40 <= now.minute <= 49)

    # GitHub event 名稱：schedule / workflow_dispatch / push...
    is_manual = os.getenv("GITHUB_EVENT_NAME") == "workflow_dispatch"
    if is_manual:
        return True

    state_file = os.path.join("state", "last_sent_date.txt")
    if os.path.exists(state_file):
        try:
            last = open(state_file, "r", encoding="utf-8").read().strip()
            if last == today:
                print("Already sent today. Exit.")
                return False
        except:
            pass

    if not in_window:
        print(f"Not in Taipei window. Now={now.isoformat()}. Exit.")
        return False

    # 進入窗口且尚未送出：先寫入狀態避免併發重複
    os.makedirs("state", exist_ok=True)
    with open(state_file, "w", encoding="utf-8") as f:
        f.write(today)
    return True

# ======================
# 工具
# ======================
def html(s):
    return (s or "").replace("&","&amp;").replace("<","&lt;").replace(">","&gt;").replace('"',"&quot;")

def load_cache():
    if os.path.exists(CACHE_FILE):
        try:
            return json.load(open(CACHE_FILE,"r",encoding="utf-8"))
        except:
            pass
    return {}

def save_cache(c):
    json.dump(c, open(CACHE_FILE,"w",encoding="utf-8"), ensure_ascii=False, indent=2)

def prune_cache(c):
    now = int(time.time())
    for k in list(c.keys()):
        if now - c[k].get("ts",0) > CACHE_DAYS * 86400:
            del c[k]

def tg_send(text):
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    return requests.post(url, data={
        "chat_id": TELEGRAM_CHAT_ID,
        "text": text,
        "parse_mode": "HTML",
        "disable_web_page_preview": True
    }, timeout=20)

def tg_send_chunked(msg):
    parts, buf = [], ""
    for p in msg.split("\n\n"):
        if len(buf) + len(p) < TG_MAX:
            buf += ("\n\n" + p if buf else p)
        else:
            parts.append(buf)
            buf = p
    if buf:
        parts.append(buf)

    for i, p in enumerate(parts, 1):
        tg_send((f"（{i}/{len(parts)}）\n" if len(parts) > 1 else "") + p)
        time.sleep(1)

# ======================
# 新聞處理
# ======================
NTPC_KEYS = ["新北","板橋","新莊","中和","永和","三重","蘆洲","新店","土城","林口","淡水","汐止","侯友宜"]
EXCLUDE_HOME = ["一氧化碳","中毒","瓦斯","猝死","家中","送醫","急診"]

def is_ntpc(t):
    return any(k in (t or "") for k in NTPC_KEYS)

def traffic_ok(t):
    t = t or ""
    return not any(x in t for x in EXCLUDE_HOME)

# ✅ 補教類「必含」關鍵字（沒有就不收）
TUTOR_MUST = [
    "補習班", "短期補習班", "補習教育", "補教",
    "課後照顧", "安親", "安親班", "課照",
    "才藝班", "語文短期補習班", "文理補習班"
]

# ✅ 補教類「排除」關鍵字（混入交通/警政/娛樂/折扣等）
TUTOR_EXCLUDE = [
    "派出所", "警方", "警分局", "警局", "交通", "行人", "路口", "公車", "捷運", "車禍",
    "棒球", "籃球", "羽球", "賽", "球隊", "演唱會", "影劇", "旅遊", "餐廳",
    "股市", "理財", "房市", "打折", "優惠", "Cheapo"
]

def tutoring_ok(title: str) -> bool:
    t = title or ""
    if not any(k in t for k in TUTOR_MUST):
        return False
    if any(x in t for x in TUTOR_EXCLUDE):
        return False
    return True

def fetch(q, n=30):
    rss = f"https://news.google.com/rss/search?q={urllib.parse.quote_plus(q)}&hl=zh-TW&gl=TW&ceid=TW:zh-Hant"
    return feedparser.parse(rss).entries[:n]

def real_link(u):
    try:
        r = requests.get(u, timeout=10, headers={"User-Agent":"Mozilla/5.0"})
        return r.url
    except:
        return u

def line(t, l):
    return f'• <a href="{html(l)}">{html(t)}</a>'

# ======================
# 類別設定
# ======================
CATS = {
    "🚦 交通安全": {
        "ntpc": "新北 (交通事故 OR 行人 OR 公車 OR 機車 OR 路口 OR 通學巷 OR 斑馬線)",
        "all":  "(交通事故 OR 行人 OR 公車 OR 機車 OR 路口 OR 通學巷 OR 斑馬線)"
    },
    "📚 終身學習": {
        "ntpc": "新北 (終身學習 OR 社區大學 OR 樂齡學習 OR 學習活動 OR 成果)",
        "all":  "(終身學習 OR 社區大學 OR 樂齡學習 OR 學習活動 OR 成果)"
    },
    "🏫 補教類（補習班）": {
        "ntpc": "新北 (補習班 OR 短期補習班 OR 補習教育 OR 課後照顧 OR 安親班 OR 才藝班 OR 退費 OR 稽查 OR 未立案)",
        "all":  "(補習班 OR 短期補習班 OR 補習教育 OR 課後照顧 OR 安親班 OR 才藝班 OR 退費 OR 稽查 OR 未立案)"
    }
}

def advice(cat):
    if "交通" in cat:
        return "建議以事故樣態與熱點作預警指標，提早盤點工程與執法改善空間，降低風險累積。"
    if "終身" in cat:
        return "建議以參與觸及與學習成效為核心，強化社大/樂齡與在地資源串接，提升續學率與品質一致性。"
    return "建議以風險導向稽查與資訊透明並進，聚焦未立案、退費與不當對待等高關注議題，強化跨機關聯稽與家長辨識宣導。"

# ======================
# 主程式
# ======================
def main():
    # ✅ 台灣 07:40 時間鎖（排程必準時、同日不重複）
    if not taipei_time_lock():
        return

    cache = load_cache()
    prune_cache(cache)

    today = datetime.date.today().isoformat()
    blocks = []

    for cat, qs in CATS.items():
        ents = fetch(qs["ntpc"]) + fetch(qs["all"])
        ntpc, other, fill = [], [], []
        seen = set()

        for e in ents:
            t = (e.title or "").strip()

            # 類別專屬過濾
            if "交通" in cat and not traffic_ok(t):
                continue
            if "補教類" in cat and not tutoring_ok(t):
                continue

            l = real_link(e.link)
            k = l or t
            if not k or k in seen or k in cache:
                continue

            seen.add(k)
            cache[k] = {"ts": int(time.time())}

            if is_ntpc(t) and len(ntpc) < MAX_NTPC:
                ntpc.append(line(t, l))
                continue
            if (not is_ntpc(t)) and len(other) < MAX_OTHER:
                other.append(line(t, l))
                continue
            if len(fill) < MIN_TOTAL:
                fill.append(line(t, l))

        # 保底：避免空欄（補教仍受 tutoring_ok 限制，不會亂補）
        if not ntpc and fill:
            ntpc.append(fill.pop(0))
        if not other and fill:
            other.append(fill.pop(0))

        blocks.append(
            f"<b>{cat}</b>\n"
            f"🟦 <b>新北</b>\n{chr(10).join(ntpc) if ntpc else '（本日無）'}\n\n"
            f"🟨 <b>外縣市／全國</b>\n{chr(10).join(other) if other else '（本日無）'}\n\n"
            f"💡 <b>行政因應建議</b>\n{advice(cat)}"
        )

    msg = f"🗞 <b>新北市教育與交通輿情晨報</b>\n日期：{today}\n\n" + "\n\n".join(blocks)
    tg_send_chunked(msg)
    save_cache(cache)

if __name__ == "__main__":
    try:
        main()
    except:
        traceback.print_exc()
        # 不讓 workflow 直接紅燈（以免你誤判系統壞掉），但仍保留 log
        raise SystemExit(0)
