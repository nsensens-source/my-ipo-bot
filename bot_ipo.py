import os
import yfinance as yf
from supabase import create_client
import requests

# ดึงค่าจาก GitHub Secrets
supabase = create_client(os.getenv("SUPABASE_URL"), os.getenv("SUPABASE_KEY"))
DISCORD_URL = os.getenv("DISCORD_WEBHOOK")

def notify(msg):
    requests.post(DISCORD_URL, json={"content": msg})

def run_bot():
    # ดึงข้อมูลหุ้นจาก Supabase
    res = supabase.table("ipo_trades").select("*").neq("status", "sold").execute()
    stocks = res.data

    for item in stocks:
        ticker = item['ticker']
        # เช็คราคาและส่งแจ้งเตือนตาม Logic ที่เราคุยกันไว้...
        print(f"Checking {ticker}...")
        # (ใส่ Logic การเช็คราคาและแจ้งเตือนต่อจากตรงนี้ครับ)

if __name__ == "__main__":
    run_bot()
