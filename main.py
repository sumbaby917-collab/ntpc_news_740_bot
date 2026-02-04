name: Daily Report Bot

on:
  workflow_dispatch:
  schedule:
    # 每天台灣時間 07:40 = UTC 23:40（前一天）
    - cron: "40 23 * * *"

permissions:
  contents: read
  actions: read

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

      # ✅ 下載最近一次「成功」run 的 sent-cache artifact（抓不到也不讓 workflow 失敗）
      - name: Download previous sent cache (best-effort)
        continue-on-error: true
        env:
          GH_TOKEN: ${{ secrets.GITHUB_TOKEN }}
          REPO: ${{ github.repository }}
          WF_NAME: Daily Report Bot
          ART_NAME: sent-cache
        run: |
          echo "Finding latest successful run for workflow: $WF_NAME"
          RUN_ID=$(gh api -H "Accept: application/vnd.github+json" \
            "/repos/$REPO/actions/workflows" \
            --jq ".workflows[] | select(.name==\"$WF_NAME\") | .id" | head -n 1)

          echo "Workflow id: $RUN_ID"
          LAST_OK_RUN=$(gh api -H "Accept: application/vnd.github+json" \
            "/repos/$REPO/actions/workflows/$RUN_ID/runs?status=success&per_page=1" \
            --jq ".workflow_runs[0].id")

          if [ -z "$LAST_OK_RUN" ] || [ "$LAST_OK_RUN" = "null" ]; then
            echo "No successful runs found yet. Skip downloading cache."
            exit 0
          fi

          echo "Latest successful run id: $LAST_OK_RUN"
          gh run download "$LAST_OK_RUN" -n "$ART_NAME" -D . || true
          ls -la
          if [ -f sent_cache.json ]; then
            echo "sent_cache.json downloaded."
          else
            echo "sent_cache.json not found after download. Continue without cache."
          fi

      - name: Run bot
        env:
          TELEGRAM_TOKEN: ${{ secrets.TELEGRAM_TOKEN }}
          TELEGRAM_CHAT_ID: ${{ secrets.TELEGRAM_CHAT_ID }}
          GEMINI_API_KEY: ${{ secrets.GEMINI_API_KEY }}
        run: |
          python main.py

      # ✅ 無論前面是否成功下載 cache，都嘗試上傳新的 cache（有檔才上傳）
      - name: Upload sent cache artifact
        if: always()
        uses: actions/upload-artifact@v4
        with:
          name: sent-cache
          path: sent_cache.json
          if-no-files-found: ignore
          retention-days: 14
