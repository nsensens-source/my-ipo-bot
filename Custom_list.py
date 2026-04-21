import yfinance as yf
import pandas as pd
import requests
import os
import time
import logging

# ปิดการแจ้งเตือนขยะจาก yfinance
logging.getLogger('yfinance').setLevel(logging.CRITICAL)

# ดึงค่า Webhook จาก Environment Variable หรือใช้ค่า URL ตรงๆ 
# (สามารถแยก Webhook ออกไปอีกห้องได้ถ้าต้องการ)
DISCORD_WEBHOOK_URL = os.getenv(
    'DISCORD_WEBHOOK_CUSTOM', 
    'https://discord.com/api/webhooks/1495670755101249576/eSXVxgg7MEmykrQ8gzJS88aRCEQRGCxuqJgfz4NyYN3nhgNXr-0eL2bY-nHCFrZ4IkXD'
)

# 📌 เพิ่มหุ้นที่ต้องการดูเฉพาะเจาะจงลงในนี้ได้เลย (ใส่ได้ไม่จำกัด)
CUSTOM_WATCHLIST = ['LITE', 'AAOI', 'AAPL', 'TSLA', 'PLTR', 'SNDK', 'MU', 'AXTI', 'BE', 'CRDO', 'ALAB','CIEN','PLTR','APLD','COHR','IREN','COMP','BWET','LQDA','HIMS'
                    'AMD', 'NVDA','LRCX','WDC','STX','KLAC','GLW','TSEM','QBTS','QUBT','RGTI','IONQ','CAR','SIVEF','POET','ONDS','NVTS','HUT']

def format_pct(current, previous, hide_pct=False):
    """คำนวณ % และใส่ 🟢 หุ้นขึ้น หรือ 🔴 หุ้นลง"""
    if pd.isna(current) or pd.isna(previous) or previous == 0: 
        return "⚪0.0" if hide_pct else "⚪0.0%"
    diff = ((current - previous) / previous) * 100
    emoji = "🟢" if diff >= 0 else "🔴"
    sym = "" if hide_pct else "%"
    return f"{emoji}{abs(diff):.1f}{sym}"

def send_to_discord(df, title, webhook_url, history_header="D-1 to D-10 Trend"):
    """ฟังก์ชันจัดการส่งข้อความเข้า Discord แบบกระชับ"""
    if df.empty: return
    
    header = f"🎯 **{title}** 🎯\n"
    cb = "```" 
    
    # ปรับช่องว่างให้ชิดที่สุด
    table_header = f"{cb}text\n{'Sym':<5}|{'Price':>7}|{'Today':<8}|{'10D Sum':<15}|{history_header}\n"
    table_header += "-" * 95 + "\n"
    
    current_msg = header + table_header
    messages_to_send = []

    for _, row in df.iterrows():
        ticker = str(row['Ticker'])[:5]
        line = f"{ticker:<5}|{row['Price']:>7.2f}|{row['Today']:<8}|{row['Sum10D']:<15}|{row['History']}\n"
        
        if len(current_msg) + len(line) > 1900:
            current_msg += f"{cb}" 
            messages_to_send.append(current_msg)
            current_msg = f"{cb}text\n" + line 
        else:
            current_msg += line

    if not current_msg.endswith(f"{cb}"):
        current_msg += f"{cb}"
        messages_to_send.append(current_msg)

    for msg in messages_to_send:
        requests.post(webhook_url, json={"content": msg})
        time.sleep(1)

def main():
    print("🚀 เริ่มดึงข้อมูลเฉพาะหุ้นใน Custom Watchlist...")
    
    # ลบชื่อหุ้นที่ซ้ำกันออก (ถ้ามี)
    tickers = list(set(CUSTOM_WATCHLIST))
    
    if not tickers:
        print("ไม่พบรายชื่อหุ้นใน Watchlist กรุณาเพิ่มชื่อหุ้นลงในตัวแปร CUSTOM_WATCHLIST")
        return
        
    print(f"พบรายชื่อหุ้นที่ต้องการดึงข้อมูล {len(tickers)} ตัว")

    # ป้องกันบั๊กของ yfinance กรณีดึงหุ้นตัวเดียวแล้ว Dataframe Format เปลี่ยน
    if len(tickers) == 1: 
        tickers.append('SPY') 

    # โหลดข้อมูลย้อนหลัง
    data = yf.download(tickers, period="20d", interval="1d", threads=True, progress=False)
    
    if 'Close' not in data or len(data['Close']) < 12: 
        print("ดึงข้อมูลจาก Yahoo Finance ไม่สำเร็จ")
        return
        
    close_data = data['Close']
    
    try:
        global_dates = close_data.index[-12:]
    except IndexError:
        print("ข้อมูลวันที่ไม่ครบถ้วน")
        return
        
    results = []
    
    for ticker in tickers:
        # ข้าม SPY ที่เราใส่ไปกันบั๊ก (ถ้ามันไม่ได้อยู่ใน List จริงๆ)
        if ticker == 'SPY' and 'SPY' not in CUSTOM_WATCHLIST:
            continue
            
        try:
            if ticker not in close_data.columns: continue
            
            curr_price = close_data.loc[global_dates[-1], ticker]
            prev_price = close_data.loc[global_dates[-2], ticker]
            
            if pd.isna(curr_price) or pd.isna(prev_price): continue
            
            # ไม่ต้องกรองราคาและโวลุ่ม เพราะเป็นหุ้นที่เราเลือกมาเอง
            today_pct_val = ((curr_price - prev_price) / prev_price) * 100

            up_days = 0
            down_days = 0
            for j in range(1, 11): 
                curr_h = close_data.loc[global_dates[-j], ticker]
                prev_h = close_data.loc[global_dates[-(j+1)], ticker]
                if curr_h > prev_h: up_days += 1
                elif curr_h < prev_h: down_days += 1
            
            price_10d_ago = close_data.loc[global_dates[-11], ticker]
            sum10d_str = f"🟢{up_days}🔴{down_days}({format_pct(curr_price, price_10d_ago)})"
            
            history_pcts = []
            valid_history = True
            for j in range(2, 12):
                curr_hist = close_data.loc[global_dates[-j], ticker]
                prev_hist = close_data.loc[global_dates[-(j+1)], ticker]
                if pd.isna(curr_hist) or pd.isna(prev_hist):
                    valid_history = False
                    break
                # ซ่อนเครื่องหมาย % ประหยัดที่
                history_pcts.append(format_pct(curr_hist, prev_hist, hide_pct=True))
            
            if not valid_history: continue
            
            results.append({
                'Ticker': ticker,
                'Price': curr_price,
                'Today': format_pct(curr_price, prev_price),
                'AbsSortVal': abs(today_pct_val),
                'Sum10D': sum10d_str,
                'History': "".join(history_pcts)
            })
        except Exception as e:
            print(f"Error processing {ticker}: {e}")
            continue

    if not results:
        print("ไม่สามารถคำนวณข้อมูลหุ้นใดๆ ได้")
        return
        
    # จัดเรียงตามเปอร์เซ็นต์การขยับ (Mover) จากมากไปน้อย
    watchlist_df = pd.DataFrame(results).sort_values(by='AbsSortVal', ascending=False)
    
    if not DISCORD_WEBHOOK_URL:
        print("Error: ไม่พบ Webhook URL")
        return

    print("กำลังส่งข้อมูล Watchlist Update เข้า Discord...")
    title_watch = f"📌 CUSTOM WATCHLIST UPDATE ({len(results)} Symbols)"
    send_to_discord(watchlist_df, title_watch, DISCORD_WEBHOOK_URL, history_header="D-1 to D-10 Trend")
    
    print("✅ ทำงานเสร็จสมบูรณ์!")

if __name__ == "__main__":
    main()
