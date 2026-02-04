name: Daily Report Bot

on:
  workflow_dispatch:
  schedule:
    # 每天台灣時間 07:40 = UTC 23:40（前一天）
    - cron: "40 23 * * *"

jobs:
  run-report:
    runs-on: ubuntu-latest

    steps:
      - name: Checkout
        uses: actions/checkout@v4

      - name: Set up Python
        uses: actions/setup-python@v5
        with:
          python-version: "3.11"

      - name: Install dependencies
        run: |
          python -m pip install --upgrade pip
          pip install feedparser requests google-generativeai

      # ✅ 下載上一輪的 sent_cache artifact（若首次執行找不到也不會失敗）
      - name: Download previous sent cache artifact
        uses: dawidd6/action-download-artifact@v3
        with:
          github_token: ${{ secrets.GITHUB_TOKEN }}
          workflow: daily.yml
          name: sent-cache
          path: .
          if_no_artifact_found: ignore

      # （可選）列出目前 workspace 檔案，方便你 debug
      - name: Debug list files
        run: |
          ls -la
          if [ -f sent_cache.json ]; then echo "sent_cache.json exists"; else echo "sent_cache.json not found"; fi

      - name: Run bot
        env:
          TELEGRAM_TOKEN: ${{ secrets.TELEGRAM_TOKEN }}
          TELEGRAM_CHAT_ID: ${{ secrets.TELEGRAM_CHAT_ID }}
          GEMINI_API_KEY: ${{ secrets.GEMINI_API_KEY }}
        run: |
          python main.py

      # ✅ 上傳新的 sent_cache artifact，供下次 run 下載使用
      - name: Upload sent cache artifact
        uses: actions/upload-artifact@v4
        with:
          name: sent-cache
          path: sent_cache.json
          if-no-files-found: ignore
          retention-days: 14
