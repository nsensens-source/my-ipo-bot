import yfinance as yf
import pandas as pd
import requests
import os
import time
import logging
import io

# ปิดการแจ้งเตือนขยะจาก yfinance
logging.getLogger('yfinance').setLevel(logging.CRITICAL)

# ดึงค่า Webhook
DISCORD_WEBHOOK_URL = 'https://discord.com/api/webhooks/1476755678931456062/LpfG3Eq5jgnOmW8-q2BhfGPAEK3Jd-YEbiaH2oJiEHis0B51mvkYILkKuIKbu3Y3yKc5'

# --- ตั้งค่าตัวกรองหุ้น (Filters) ---
TOP_N = 100                     # จำนวนหุ้น Top Gainer ที่ต้องการจัดอันดับ (เช่น 50 หรือ 100)
MIN_PRICE = 3.0                 # ราคาขั้นต่ำ 3 ดอลลาร์
MIN_DOLLAR_VOLUME = 15_000_000  # มูลค่าซื้อขายเฉลี่ยขั้นต่ำ 15 ล้านดอลลาร์/วัน

def get_all_us_tickers():
    """ดึงรายชื่อหุ้นทั้งหมดจาก SEC (ก.ล.ต. สหรัฐฯ) เพื่อสแกนทั้งตลาด 100%"""
    valid_tickers = set()
    headers = {'User-Agent': 'US_Stock_Scanner user@example.com'}
    url = "https://www.sec.gov/files/company_tickers.json"
    try:
        response = requests.get(url, headers=headers)
        for item in response.json().values():
            ticker = item['ticker'].replace('.', '-')
            # กรองเฉพาะหุ้นกระดานหลักที่มีสัญลักษณ์ไม่เกิน 4 ตัวอักษร
            if len(ticker) <= 4 or '-' in ticker:
                valid_tickers.add(ticker)
    except Exception as e:
        print(f"SEC Fetch Error: {e}")
        
    return list(valid_tickers)

def get_market_sectors():
    """ดึงข้อมูล Sector พื้นฐานจาก S&P 500, 400, 600 (ครอบคลุมหุ้นหลัก 1500 ตัว)"""
    sector_map = {}
    urls = [
        'https://en.wikipedia.org/wiki/List_of_S%26P_500_companies',
        'https://en.wikipedia.org/wiki/List_of_S%26P_400_companies',
        'https://en.wikipedia.org/wiki/List_of_S%26P_600_companies'
    ]
    headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)'}
    for url in urls:
        try:
            html = requests.get(url, headers=headers, timeout=10).text
            df = pd.read_html(io.StringIO(html))[0]
            
            # หาคอลัมน์ชื่อหุ้น
            ticker_col = None
            for col in ['Symbol', 'Ticker Symbol', 'Ticker']:
                if col in df.columns:
                    ticker_col = col
                    break
                    
            # หาคอลัมน์กลุ่มอุตสาหกรรม
            sector_col = None
            for col in ['GICS Sector', 'Sector']:
                if col in df.columns:
                    sector_col = col
                    break
                    
            if ticker_col and sector_col:
                mapping = dict(zip(df[ticker_col].astype(str).str.replace('.', '-', regex=False), df[sector_col]))
                sector_map.update(mapping)
        except Exception as e:
            print(f"Error fetching sectors from {url}: {e}")
    return sector_map

def format_pct(current, previous):
    """คำนวณ % และใส่ 🟢 หุ้นขึ้น หรือ 🔴 หุ้นลง"""
    if pd.isna(current) or pd.isna(previous) or previous == 0: return "⚪0.0%"
    diff = ((current - previous) / previous) * 100
    emoji = "🟢" if diff >= 0 else "🔴"
    return f"{emoji}{abs(diff):.1f}%"

def send_to_discord(df, title, webhook_url):
    """ฟังก์ชันจัดการส่งข้อความเข้า Discord แบบตัดก้อนอัตโนมัติ"""
    if df.empty: return
    
    header = f"🎯 **{title}** 🎯\n"
    cb = "```" 
    table_header = f"{cb}text\n{'Ticker':<6} | {'Price':<7} | {'Today':<8} | D-1 to D-4 Trend\n"
    table_header += "-" * 60 + "\n"
    
    current_msg = header + table_header
    messages_to_send = []

    for _, row in df.iterrows():
        line = f"{row['Ticker']:<6} | {row['Price']:>7.2f} | {row['Today']:<8} | {row['History']}\n"
        
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
    print("🚀 เริ่มสแกนหุ้นทั้งตลาดสหรัฐฯ (Fully Automatic)...")
    tickers = get_all_us_tickers()
    
    if not tickers:
        print("ไม่สามารถดึงรายชื่อหุ้นได้")
        return
        
    print(f"พบรายชื่อหุ้นในระบบทั้งหมด {len(tickers)} ตัว")
    print("กำลังดาวน์โหลดข้อมูล (แบ่งเป็นรอบๆ เพื่อป้องกัน Yahoo บล็อก)...")

    results = []
    # ลด Chunk ลงมาเหลือ 100 เพื่อการันตีไม่ให้ Yahoo ทำข้อมูลหาย
    chunk_size = 100 
    
    for i in range(0, len(tickers), chunk_size):
        chunk = tickers[i:i + chunk_size]
        if len(chunk) == 1: chunk.append('AAPL')

        # โหลดข้อมูล
        data = yf.download(chunk, period="12d", interval="1d", threads=True, progress=False)
        
        if 'Close' not in data or len(data['Close']) < 6: continue
            
        close_data = data['Close']
        volume_data = data['Volume']
        
        # 🛡️ ล็อกวันที่จากแกนเวลา (Index) โดยตรง 
        try:
            d0 = close_data.index[-1] # วันล่าสุด
            d1 = close_data.index[-2] # 1 วันก่อน
            d2 = close_data.index[-3] # 2 วันก่อน
            d3 = close_data.index[-4]
            d4 = close_data.index[-5]
            d5 = close_data.index[-6]
        except IndexError:
            continue
        
        for ticker in chunk:
            try:
                if ticker not in close_data.columns: continue
                
                # ดึงราคาจากวันที่ถูกล็อกไว้เท่านั้น
                curr_price = close_data.loc[d0, ticker]
                prev_price = close_data.loc[d1, ticker]
                
                # ถ้าวันล่าสุดยังไม่มีราคา ให้ข้ามไปก่อน
                if pd.isna(curr_price) or pd.isna(prev_price): continue
                    
                # คำนวณ Volume เฉลี่ย 5 วัน
                avg_vol_5d = volume_data[ticker].tail(5).mean()
                if pd.isna(avg_vol_5d): continue
                
                # --- 🛡️ FILTER LOGIC ---
                if curr_price < MIN_PRICE: continue
                dollar_vol = curr_price * avg_vol_5d
                if dollar_vol < MIN_DOLLAR_VOLUME: continue
                # ------------------------
                
                today_pct_val = ((curr_price - prev_price) / prev_price) * 100
                
                # ดึง % ย้อนหลังด้วยวันที่ล็อกไว้เป๊ะๆ
                hist_1 = format_pct(close_data.loc[d1, ticker], close_data.loc[d2, ticker])
                hist_2 = format_pct(close_data.loc[d2, ticker], close_data.loc[d3, ticker])
                hist_3 = format_pct(close_data.loc[d3, ticker], close_data.loc[d4, ticker])
                hist_4 = format_pct(close_data.loc[d4, ticker], close_data.loc[d5, ticker])
                
                results.append({
                    'Ticker': ticker,
                    'Price': curr_price,
                    'Today': format_pct(curr_price, prev_price),
                    'SortVal': today_pct_val,
                    'History': f"{hist_1} {hist_2} {hist_3} {hist_4}"
                })
            except Exception:
                continue
                
        # พักให้ Yahoo หายใจ
        time.sleep(1)

    if not results:
        print("ไม่พบหุ้นที่ผ่านเกณฑ์")
        return
        
    all_df = pd.DataFrame(results)

    # จัดอันดับ Top N จากทั้งตลาด 100%
    top_gainers = all_df.sort_values(by='SortVal', ascending=False).head(TOP_N)
    
    if not DISCORD_WEBHOOK_URL:
        print("Error: ไม่พบ Webhook URL กรุณาตั้งค่า DISCORD_WEBHOOK_TOPGAINER")
        print(top_gainers.head())
        return

    # --- ดึงข้อมูล Sector สำหรับ Top N ---
    print(f"กำลังดึงข้อมูลอุตสาหกรรม (Sector) สำหรับหุ้น Top {TOP_N} ตัว (ระบบ 3 ชั้น กันบล็อก)...")
    
    # 1. โหลดข้อมูล Sector สำรองจาก S&P 1500 (เร็วและไม่โดนบล็อก 100%)
    sp1500_sectors = get_market_sectors()
    
    sectors = []
    
    # สร้าง Session เลียนแบบเบราว์เซอร์ปกติ
    session = requests.Session()
    session.headers.update({
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
    })
    
    for ticker in top_gainers['Ticker']:
        sector = 'Unknown'
        
        # วิธีที่ 1: ดึงจากฐานข้อมูล S&P 1500 ที่โหลดมา
        if ticker in sp1500_sectors:
            sector = sp1500_sectors[ticker]
        else:
            # วิธีที่ 2: ยิง API ไปที่ Yahoo Finance โดยตรง (หลบการบล็อกของไลบรารี yfinance)
            # แก้ไขบั๊ก URL มาร์กดาวน์
            try:
                url = f"[https://query2.finance.yahoo.com/v10/finance/quoteSummary/](https://query2.finance.yahoo.com/v10/finance/quoteSummary/){ticker}?modules=assetProfile"
                res = session.get(url, timeout=5)
                if res.status_code == 200:
                    data = res.json()
                    profile = data.get('quoteSummary', {}).get('result', [{}])[0].get('assetProfile', {})
                    sector = profile.get('sector', profile.get('industry', 'Unknown'))
            except Exception:
                pass
                
            # วิธีที่ 3: ใช้ yfinance เป็นด่านสุดท้าย
            if sector == 'Unknown':
                try:
                    info = yf.Ticker(ticker, session=session).info
                    sector = info.get('sector', info.get('industry', 'Unknown'))
                except Exception:
                    pass
            
            time.sleep(0.5) # พักเซิร์ฟเวอร์เฉพาะเวลาที่ยิง API สด
            
        sectors.append(sector)
        
    top_gainers['Sector'] = sectors
    
    # --- คำนวณ Sector Summary ---
    sector_msg_content = f"📊 **SECTOR TREND SUMMARY (จาก Top {TOP_N})** 📊\n"
    sector_msg_content += "-" * 55 + "\n"
    
    valid_sectors = top_gainers[top_gainers['Sector'] != 'Unknown']
    if not valid_sectors.empty:
        sector_summary = valid_sectors.groupby('Sector').agg(
            Count=('Ticker', 'count'),
            AvgChange=('SortVal', 'mean')
        ).reset_index().sort_values(by=['Count', 'AvgChange'], ascending=[False, False])
        
        for _, row in sector_summary.iterrows():
            avg_val = row['AvgChange']
            emoji = "🟢" if avg_val >= 0 else "🔴"
            sector_msg_content += f"🔹 **{row['Sector']}**: ติดอันดับ **{row['Count']}** ตัว | เฉลี่ยกลุ่ม {emoji}{abs(avg_val):.1f}%\n"
            
    # เพิ่มการแสดงหุ้นที่หา Sector ไม่เจอ เพื่อให้เห็นภาพรวมเต็ม 100 ตัว
    unknown_count = top_gainers[top_gainers['Sector'] == 'Unknown'].shape[0]
    if unknown_count > 0:
        sector_msg_content += f"\n🔸 **ไม่สามารถระบุกลุ่มได้ (Unknown / อื่นๆ)**: {unknown_count} ตัว\n"

    # --- ส่งเข้า Discord ---
    print(f"ส่งข้อมูล Top {TOP_N} Gainers (Automatic)...")
    title_top = f"TOP {TOP_N} GAINERS (Price > ${MIN_PRICE}, Avg Vol > ${MIN_DOLLAR_VOLUME/1_000_000}M)"
    send_to_discord(top_gainers, title_top, DISCORD_WEBHOOK_URL)
    
    print("ส่งข้อมูล Sector Summary...")
    requests.post(DISCORD_WEBHOOK_URL, json={"content": sector_msg_content})
        
    print("✅ สแกนทั้งตลาด ดึงกลุ่ม Sector และส่งเข้า Discord เรียบร้อย!")

if __name__ == "__main__":
    main()
