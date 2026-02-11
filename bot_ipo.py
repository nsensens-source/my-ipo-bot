import os
import yfinance as yf
from supabase import create_client
import requests
from datetime import datetime

# 1. การตั้งค่าการเชื่อมต่อ (ดึงจาก GitHub Secrets)
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")
DISCORD_URL = os.getenv("DISCORD_WEBHOOK")

supabase = create_client(SUPABASE_URL, SUPABASE_KEY)

def notify(msg):
    """ส่งข้อความแจ้งเตือนเข้า Discord"""
    if DISCORD_URL:
        requests.post(DISCORD_URL, json={"content": msg})
    print(msg)

def run_bot():
    """ฟังก์ชันหลักสำหรับตรวจเช็คราคาและรันกลยุทธ์เทรด"""
    # ดึงหุ้นที่ยังไม่ถูกขาย (Status: watching หรือ bought)
    res = supabase.table("ipo_trades").select("*").neq("status", "sold").execute()
    stocks = res.
