name: IPO Bot Runner

on:
  schedule:
    - cron: '0 2,5,8 * * 1-5' # รันตามเวลาที่ต้องการ
  workflow_dispatch:

jobs:
  run-ipo-logic:
    runs-on: ubuntu-latest
    steps:
      # --- ส่วนที่ต้องเพิ่มเพื่อให้หาไฟล์เจอ ---
      - name: Checkout Repository Code
        uses: actions/checkout@v4 

      - name: Set up Python
        uses: actions/setup-python@v5
        with:
          python-version: '3.10'

      - name: Install Dependencies
        run: pip install yfinance pandas requests supabase

      - name: Execute Bot
        env:
          SUPABASE_URL: ${{ secrets.SUPABASE_URL }}
          SUPABASE_KEY: ${{ secrets.SUPABASE_KEY }}
          DISCORD_WEBHOOK: ${{ secrets.DISCORD_WEBHOOK }}
        # มั่นใจว่าใช้ชื่อไฟล์ bot_ipo.py ตามที่คุณยืนยัน
        run: python bot_ipo.py
