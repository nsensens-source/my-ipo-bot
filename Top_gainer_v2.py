import yfinance as yf
import pandas as pd
import requests
import os
import time

# ดึงค่าจาก GitHub Secrets
DISCORD_WEBHOOK_URL = os.getenv('DISCORD_WEBHOOK_TOPGAINER')

def get_sp500_tickers():
    url = 'https://en.wikipedia.org/wiki/List_of_S%26P_500_companies'
    headers = {'User-Agent': 'Mozilla/5.0'}
    try:
        response = requests.get(url, headers=headers)
        df = pd.read_html(response.text)[0]
        return df['Symbol'].str.replace('.', '-', regex=False).tolist()
    except Exception as e:
        print(f"Error fetching tickers: {e}")
        return []

def format_pct(current, previous):
    """คำนวณ % และใส่ 🟢 หุ้นขึ้น หรือ 🔴 หุ้นลง"""
    if pd.isna(current) or pd.isna(previous) or previous == 0: return "⚪0.0%"
    diff = ((current - previous) / previous) * 100
    emoji = "🟢" if diff >= 0 else "🔴"
    return f"{emoji}{abs(diff):.1f}%"

def main():
    print("🚀 กำลังดึงข้อมูลและคำนวณเทรนด์ 5 วันล่าสุด...")
    tickers = get_sp500_tickers()
    if not tickers: 
        print("ไม่สามารถดึงรายชื่อหุ้นได้")
        return

    # ดึงข้อมูลย้อนหลัง 12 วันเพื่อเผื่อวันหยุด
    data = yf.download(tickers, period="12d", interval="1d", group_by='ticker', threads=True)
    
    results = []
    for ticker in tickers:
        try:
            h = data[ticker]['Close'].dropna()
            if len(h) < 6: continue
            
            # ดึงราคาปิดปัจจุบันและเมื่อวาน
            curr = h.iloc[-1]
            prev = h.iloc[-2]
            today_pct_val = ((curr - prev) / prev) * 100
            
            # คำนวณประวัติ 4 วันก่อนหน้า (Day-1 ถึง Day-4) เรียงจากใหม่ไปเก่า
            d1 = format_pct(h.iloc[-2], h.iloc[-3])
            d2 = format_pct(h.iloc[-3], h.iloc[-4])
            d3 = format_pct(h.iloc[-4], h.iloc[-5])
            d4 = format_pct(h.iloc[-5], h.iloc[-6])
            
            results.append({
                'Ticker': ticker,
                'Price': curr,
                'Today': format_pct(curr, prev),
                'SortVal': today_pct_val,
                'History': f"{d1} {d2} {d3} {d4}"
            })
        except Exception as e:
            continue

    # จัดอันดับ Top 50
    if not results:
        print("ไม่มีข้อมูลหุ้นให้แสดงผล")
        return
        
    top_50 = pd.DataFrame(results).sort_values(by='SortVal', ascending=False).head(50)

    # ตรวจสอบ Webhook ก่อนส่ง
    if not DISCORD_WEBHOOK_URL:
        print("Error: ไม่พบ DISCORD_WEBHOOK_TOPGAINER ใน Environment Variables")
        print(top_50.head())
        return

    # --- ส่วนของการส่งเข้า Discord ---
    header = "🚀 **TOP 50 US GAINERS (5-DAY TREND %)** 🚀\n"
    table_header = f"
