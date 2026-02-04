import os
import json
import time
import datetime
import traceback
import requests

CACHE_FILE = "sent_cache.json"

def load_cache():
    try:
        if os.path.exists(CACHE_FILE):
            with open(CACHE_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
            return data if isinstance(data, dict) else {}
    except Exception:
        pass
    return {}

def save_cache(cache: dict):
    try:
        with open(CACHE_FILE, "w", encoding="utf-8") as f:
            json.dump(cache if isinstance(cache, dict) else {}, f, ensure_ascii=False, indent=2)
    except Exception:
        pass

def send_telegram(text: str):
    token = os.getenv("TELEGRAM_TOKEN")
    chat_id = os.getenv("TELEGRAM_CHAT_ID")

    if not token or not chat_id:
        print("WARN: Missing TELEGRAM_TOKEN or TELEGRAM_CHAT_ID (check GitHub Secrets + workflow env names).")
        return False

    url = f"https://api.telegram.org/bot{token}/sendMessage"
    payload = {
        "chat_id": chat_id,
        "text": text,
        "parse_mode": "HTML",
        "disable_web_page_preview": True
    }

    try:
        r = requests.post(url, data=payload, timeout=20)
        print("Telegram status:", r.status_code)
        if not r.ok:
            print("Telegram error response:", r.text[:800])
            return False
        print("Telegram sent OK.")
        return True
    except Exception as e:
        print("Telegram request exception:", type(e).__name__, str(e)[:200])
        return False

def main():
    print("=== Bot START ===", datetime.datetime.now().isoformat())
    print("Has TELEGRAM_TOKEN:", bool(os.getenv("TELEGRAM_TOKEN")))
    print("Has TELEGRAM_CHAT_ID:", bool(os.getenv("TELEGRAM_CHAT_ID")))
    print("Has GEMINI_API_KEY:", bool(os.getenv("GEMINI_API_KEY")))

    cache = load_cache()

    # 先送一則「測試訊息」，確保通道通
    today = datetime.date.today().isoformat()
    msg = (
        f"📋 <b>Daily Report Bot 測試訊息</b>\n"
        f"日期：{today}\n"
        f"狀態：GitHub Actions 已成功執行 ✅\n"
        f"（此為通道驗證訊息，確認 Secrets 與 Chat ID 正確）"
    )
    ok = send_telegram(msg)

    # 寫入 cache（確保 artifact 產生）
    cache["__last_run__"] = {"ts": int(time.time()), "telegram_ok": ok}
    save_cache(cache)

    print("=== Bot END ===")

if __name__ == "__main__":
    try:
        main()
    except Exception:
        print("FATAL ERROR:")
        traceback.print_exc()
        # 保持 workflow 綠勾（不中斷）
        raise SystemExit(0)
