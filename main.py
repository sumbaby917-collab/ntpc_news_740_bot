import os, json, time, datetime, traceback, urllib.parse, re, requests, feedparser

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
# 工具
# ======================
def html(s):
    return (s or "").replace("&","&amp;").replace("<","&lt;").replace(">","&gt;").replace('"',"&quot;")

def load_cache():
    if os.path.exists(CACHE_FILE):
        try:
            return json.load(open(CACHE_FILE,"r",encoding="utf-8"))
        except: pass
    return {}

def save_cache(c):
    json.dump(c, open(CACHE_FILE,"w",encoding="utf-8"), ensure_ascii=False, indent=2)

def prune_cache(c):
    now = int(time.time())
    for k in list(c.keys()):
        if now - c[k].get("ts",0) > CACHE_DAYS*86400:
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
        if len(buf)+len(p) < TG_MAX:
            buf += ("\n\n"+p if buf else p)
        else:
            parts.append(buf); buf=p
    if buf: parts.append(buf)
    for i,p in enumerate(parts,1):
        tg_send((f"（{i}/{len(parts)}）\n" if len(parts)>1 else "") + p)
        time.sleep(1)

# ======================
# 新聞處理
# ======================
NTPC_KEYS = ["新北","板橋","新莊","中和","永和","三重","蘆洲","新店","土城","林口","淡水","汐止","侯友宜"]
EXCLUDE_HOME = ["一氧化碳","中毒","瓦斯","猝死","家中","送醫"]

def is_ntpc(t): return any(k in t for k in NTPC_KEYS)
def traffic_ok(t): return not any(x in t for x in EXCLUDE_HOME)

def fetch(q, n=30):
    rss = f"https://news.google.com/rss/search?q={urllib.parse.quote_plus(q)}&hl=zh-TW&gl=TW&ceid=TW:zh-Hant"
    return feedparser.parse(rss).entries[:n]

def real_link(u):
    try:
        r = requests.get(u, timeout=10, headers={"User-Agent":"Mozilla/5.0"})
        return r.url
    except: return u

def line(t,l): return f'• <a href="{html(l)}">{html(t)}</a>'

# ======================
# 類別設定（A+B+C）
# ======================
CATS = {
 "🚦 交通安全": {
   "ntpc": "新北 (交通事故 OR 行人 OR 公車 OR 機車 OR 路口 OR 通學巷)",
   "all":  "(交通事故 OR 行人 OR 公車 OR 機車 OR 路口 OR 通學巷)"
 },
 "📚 終身學習": {
   "ntpc": "新北 (終身學習 OR 社區大學 OR 樂齡學習 OR 學習活動 OR 成果)",
   "all":  "(終身學習 OR 社區大學 OR 樂齡學習 OR 學習活動)"
 },
 "🏫 補教類（補習班）": {
   "ntpc": "新北 (補習班 OR 退費 OR 爭議 OR 稽查 OR 倒閉)",
   "all":  "(補習班 OR 退費 OR 爭議 OR 稽查 OR 倒閉)"
 }
}

def advice(cat):
    if "交通" in cat:
        return "建議以事故樣態與熱點為預警指標，提早盤點工程與執法改善空間，避免風險累積。"
    if "終身" in cat:
        return "建議持續盤點市府推動之終身學習活動與參與成效，作為後續政策深化與資源配置依據。"
    return "建議持續關注補教產業動態與家長關注議題，及早掌握潛在風險並強化資訊揭露。"

# ======================
# 主程式
# ======================
def main():
    cache = load_cache(); prune_cache(cache)
    today = datetime.date.today().isoformat()
    blocks=[]

    for cat,qs in CATS.items():
        ents = fetch(qs["ntpc"]) + fetch(qs["all"])
        ntpc, other, fill = [], [], []
        seen=set()

        for e in ents:
            t=e.title.strip()
            if "交通" in cat and not traffic_ok(t): continue
            l=real_link(e.link)
            k=l or t
            if k in seen or k in cache: continue
            seen.add(k); cache[k]={"ts":int(time.time())}

            if is_ntpc(t) and len(ntpc)<MAX_NTPC:
                ntpc.append(line(t,l)); continue
            if not is_ntpc(t) and len(other)<MAX_OTHER:
                other.append(line(t,l)); continue
            if len(fill)<MIN_TOTAL:
                fill.append(line(t,l))

        if not ntpc and fill: ntpc.append(fill.pop(0))
        if not other and fill: other.append(fill.pop(0))

        blocks.append(
            f"<b>{cat}</b>\n"
            f"🟦 <b>新北</b>\n{chr(10).join(ntpc) if ntpc else '（本日無）'}\n\n"
            f"🟨 <b>外縣市／全國</b>\n{chr(10).join(other) if other else '（本日無）'}\n\n"
            f"💡 <b>行政因應建議</b>\n{advice(cat)}"
        )

    msg = f"🗞 <b>新北市教育與交通輿情晨報</b>\n日期：{today}\n\n" + "\n\n".join(blocks)
    tg_send_chunked(msg)
    save_cache(cache)

if __name__=="__main__":
    try: main()
    except: traceback.print_exc()
