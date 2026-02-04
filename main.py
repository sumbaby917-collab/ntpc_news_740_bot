import re, urllib.parse, requests
from html import unescape

def normalize_title(title: str) -> str:
    """去掉常見媒體尾綴、符號差異，提升標題等價性去重"""
    t = (title or "").strip()
    # 去掉常見來源尾巴： - 聯合新聞網、｜鏡週刊、| 中時新聞網 等
    t = re.split(r"\s*[-｜|]\s*(?:聯合新聞網|udn|鏡週刊|中時|中國時報|自由時報|ETtoday|TVBS|三立|Yahoo|yahoo|NOWnews|CTWANT|風傳媒|工商時報|太報).*$", t, maxsplit=1)[0]
    # 去掉多餘空白與全半形差異
    t = re.sub(r"\s+", " ", t)
    return t

def extract_external_url_from_google_news_html(html: str) -> str | None:
    """
    從 Google News article HTML 內容抓外站原文連結。
    規則：找第一個「看起來像外站新聞」的 https:// 連結，排除 google 相關網域。
    """
    if not html:
        return None

    html = unescape(html)

    # 常見外站連結會以 https:// 開頭
    candidates = re.findall(r'href="(https?://[^"]+)"', html)
    for url in candidates:
        if any(bad in url for bad in ["news.google.com", "accounts.google.com", "policies.google.com", "support.google.com", "google.com"]):
            continue
        # 避免抓到分享/追蹤等雜鏈結：可依需要再加條件
        return url

    # 有些頁面會把外站放在 url= 參數中
    m = re.search(r"[?&]url=(https?%3A%2F%2F[^&]+)", html)
    if m:
        return urllib.parse.unquote(m.group(1))

    return None

def resolve_to_canonical_news_url(url: str) -> str:
    """
    目標：把 Google News 包裝連結解包成真正新聞站台連結
    - 若本來就不是 news.google.com，直接回傳（或做一次 redirect final）
    - 若是 news.google.com，抓 HTML 並解析外站連結
    """
    if not url:
        return url

    try:
        r = requests.get(url, timeout=12, allow_redirects=True, headers={"User-Agent": "Mozilla/5.0"})
        final_url = r.url

        # 1) 已經是外站，直接回傳
        if "news.google.com" not in final_url:
            # 部分聚合器會在 query 裡帶 url=
            parsed = urllib.parse.urlparse(final_url)
            qs = urllib.parse.parse_qs(parsed.query)
            if "url" in qs and qs["url"]:
                return qs["url"][0]
            return final_url

        # 2) 還停在 news.google.com：從 HTML 抓外站
        ext = extract_external_url_from_google_news_html(r.text)
        if ext:
            return ext

        # 3) 仍失敗：至少回傳可打開的 final_url
        return final_url

    except Exception:
        return url

def get_best_link(entry) -> str:
    """
    優先順序：
    1) entry.source.href（若是外站）
    2) entry.links 中非 news.google.com
    3) entry.link 解包成 canonical 外站
    """
    if getattr(entry, "source", None) and getattr(entry.source, "href", None):
        href = entry.source.href
        if "news.google.com" not in href:
            return href

    for l in getattr(entry, "links", []) or []:
        href = l.get("href")
        if href and "news.google.com" not in href:
            return href

    return resolve_to_canonical_news_url(getattr(entry, "link", ""))

def dedupe_key(entry) -> tuple:
    """
    去重 key：
    - 先用 canonical 外站 URL（最可靠）
    - 再用 normalize_title（備援）
    """
    title = getattr(entry, "title", "") or ""
    canonical = get_best_link(entry) or ""
    if canonical and "news.google.com" not in canonical:
        # 只要拿到外站 canonical，就用它當唯一鍵
        return ("url", canonical)
    return ("title", normalize_title(title))
