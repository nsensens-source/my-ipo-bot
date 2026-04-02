import yfinance as yf
import pandas as pd
import requests
import os
import time
import logging
import io

# ปิดการแจ้งเตือนขยะจาก yfinance
logging.getLogger('yfinance').setLevel(logging.CRITICAL)

# ดึงค่า Webhook จาก Environment Variable (ถ้ามี) หรือใช้ค่า URL ตรงๆ เป็น Fallback
DISCORD_WEBHOOK_URL = os.getenv(
    'DISCORD_WEBHOOK_TOPGAINER', 
    'https://discord.com/api/webhooks/1476755678931456062/LpfG3Eq5jgnOmW8-q2BhfGPAEK3Jd-YEbiaH2oJiEHis0B51mvkYILkKuIKbu3Y3yKc5'
)

# --- ตั้งค่าตัวกรองหุ้น (Filters) ---
TOP_N = 100                     # จำนวนหุ้น Top Gainer ที่ต้องการจัดอันดับ
MIN_PRICE = 3.0                 # ราคาขั้นต่ำ 3 ดอลลาร์
MIN_DOLLAR_VOLUME = 15_000_000  # มูลค่าซื้อขายเฉลี่ยขั้นต่ำ 15 ล้านดอลลาร์/วัน

# 📌 เพิ่มหุ้นที่ต้องการดูเป็นพิเศษ (Manual Watchlist) 
CUSTOM_WATCHLIST = ['LITE', 'AAOI', 'AAPL', 'TSLA', 'PLTR']

def get_all_us_tickers():
    """ดึงรายชื่อหุ้นทั้งหมดจาก SEC (ก.ล.ต. สหรัฐฯ) เพื่อสแกนทั้งตลาด 100%"""
    valid_tickers = set(CUSTOM_WATCHLIST)
    headers = {'User-Agent': 'US_Stock_Scanner user@example.com'}
    url = "https://www.sec.gov/files/company_tickers.json"
    try:
        response = requests.get(url, headers=headers)
        for item in response.json().values():
            ticker = item['ticker'].replace('.', '-')
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
            
            ticker_col = next((col for col in ['Symbol', 'Ticker Symbol', 'Ticker'] if col in df.columns), None)
            sector_col = next((col for col in ['GICS Sector', 'Sector'] if col in df.columns), None)
                    
            if ticker_col and sector_col:
                mapping = dict(zip(df[ticker_col].astype(str).str.replace('.', '-', regex=False), df[sector_col]))
                sector_map.update(mapping)
        except Exception as e:
            print(f"Error fetching sectors from {url}: {e}")
    return sector_map

def format_pct(current, previous, show_percent=True):
    """คำนวณ % และใส่ 🟢 หุ้นขึ้น หรือ 🔴 หุ้นลง (เลือกปิดเครื่องหมาย % ได้เพื่อลดพื้นที่)"""
    if pd.isna(current) or pd.isna(previous) or previous == 0: 
        return "⚪0.0%" if show_percent else "⚪0.0"
    diff = ((current - previous) / previous) * 100
    emoji = "🟢" if diff >= 0 else "🔴"
    return f"{emoji}{abs(diff):.1f}%" if show_percent else f"{emoji}{abs(diff):.1f}"

def send_to_discord(df, title, webhook_url, history_header="D-1 to D-10"):
    """ฟังก์ชันจัดการส่งข้อความเข้า Discord แบบตัดก้อนอัตโนมัติ"""
    if df.empty: return
    
    header = f"🎯 **{title}** 🎯\n"
    cb = "```" 
    # บีบตารางให้แคบลง ตัดเว้นวรรคที่ไม่จำเป็นออก
    table_header = f"{cb}text\n{'Sym':<5}|{'Price':>7}|{'Today':<8}|{'10D Sum':<16}|{history_header}\n"
    table_header += "-" * 105 + "\n"
    
    current_msg = header + table_header
    messages_to_send = []

    for _, row in df.iterrows():
        # จัดรูปแบบบรรทัดให้แนบชิดกันมากขึ้น
        line = f"{row['Ticker']:<5}|{row['Price']:>7.2f}|{row['Today']:<8}|{row['Sum10D']:<16}|{row['History']}\n"
        
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
    chunk_size = 100 
    
    for i in range(0, len(tickers), chunk_size):
        chunk = tickers[i:i + chunk_size]
        if len(chunk) == 1: chunk.append('AAPL')

        # โหลดข้อมูลย้อนหลัง 20 วัน
        data = yf.download(chunk, period="20d", interval="1d", threads=True, progress=False)
        
        if 'Close' not in data or len(data['Close']) < 12: continue
            
        close_data = data['Close']
        volume_data = data['Volume']
        
        # 🛡️ ล็อกวันที่จากแกนเวลา (Index) ดึง 12 วันทำการล่าสุด
        try:
            global_dates = close_data.index[-12:]
        except IndexError:
            continue
        
        for ticker in chunk:
            try:
                if ticker not in close_data.columns: continue
                
                curr_price = close_data.loc[global_dates[-1], ticker]
                prev_price = close_data.loc[global_dates[-2], ticker]
                
                if pd.isna(curr_price) or pd.isna(prev_price): continue
                    
                avg_vol_5d = volume_data[ticker].tail(5).mean()
                if pd.isna(avg_vol_5d): continue
                
                # --- 🛡️ FILTER LOGIC ---
                is_watchlist = ticker in CUSTOM_WATCHLIST
                if not is_watchlist:
                    if curr_price < MIN_PRICE: continue
                    dollar_vol = curr_price * avg_vol_5d
                    if dollar_vol < MIN_DOLLAR_VOLUME: continue
                # ------------------------
                
                today_pct_val = ((curr_price - prev_price) / prev_price) * 100

                # --- 🎯 คำนวณ สรุป 10 วันหลังสุด ---
                up_days = 0
                down_days = 0
                for j in range(1, 11): 
                    curr_h = close_data.loc[global_dates[-j], ticker]
                    prev_h = close_data.loc[global_dates[-(j+1)], ticker]
                    if curr_h > prev_h: up_days += 1
                    elif curr_h < prev_h: down_days += 1
                
                price_10d_ago = close_data.loc[global_dates[-11], ticker]
                
                # บีบช่องว่างออก (ไม่เคาะวรรคระหว่าง 🟢 กับ 🔴)
                sum10d_str = f"🟢{up_days}🔴{down_days}({format_pct(curr_price, price_10d_ago)})"
                
                # --- ดึง % ย้อนหลัง 10 วันรายวัน ---
                history_pcts = []
                valid_history = True
                for j in range(2, 12):
                    curr_hist = close_data.loc[global_dates[-j], ticker]
                    prev_hist = close_data.loc[global_dates[-(j+1)], ticker]
                    if pd.isna(curr_hist) or pd.isna(prev_hist):
                        valid_history = False
                        break
                    # ตั้งค่า show_percent=False เพื่อลดเครื่องหมาย % ประหยัดพื้นที่
                    history_pcts.append(format_pct(curr_hist, prev_hist, show_percent=False))
                
                if not valid_history: continue
                
                results.append({
                    'Ticker': ticker,
                    'Price': curr_price,
                    'Today': format_pct(curr_price, prev_price),
                    'SortVal': today_pct_val,
                    'Sum10D': sum10d_str,
                    'History': " ".join(history_pcts),
                    'IsWatchlist': is_watchlist
                })
            except Exception:
                continue
                
        time.sleep(1)

    if not results:
        print("ไม่พบหุ้นที่ผ่านเกณฑ์")
        return
        
    all_df = pd.DataFrame(results)

    top_gainers = all_df.sort_values(by='SortVal', ascending=False).head(TOP_N)
    watchlist_df = all_df[all_df['IsWatchlist']].sort_values(by='SortVal', ascending=False)
    
    if not DISCORD_WEBHOOK_URL:
        print("Error: ไม่พบ Webhook URL")
        return

    # --- ดึงข้อมูล Sector สำหรับ Top N ---
    print(f"กำลังดึงข้อมูลอุตสาหกรรม (Sector) สำหรับหุ้น Top {TOP_N} ตัว (ระบบ 3 ชั้น กันบล็อก)...")
    sp1500_sectors = get_market_sectors()
    sectors = []
    
    session = requests.Session()
    session.headers.update({
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
    })
    
    for ticker in top_gainers['Ticker']:
        sector = 'Unknown'
        if ticker in sp1500_sectors:
            sector = sp1500_sectors[ticker]
        else:
            try:
                url = f"[https://query2.finance.yahoo.com/v10/finance/quoteSummary/](https://query2.finance.yahoo.com/v10/finance/quoteSummary/){ticker}?modules=assetProfile"
                res = session.get(url, timeout=5)
                if res.status_code == 200:
                    profile = res.json().get('quoteSummary', {}).get('result', [{}])[0].get('assetProfile', {})
                    sector = profile.get('sector', profile.get('industry', 'Unknown'))
            except Exception:
                pass
                
            if sector == 'Unknown':
                try:
                    info = yf.Ticker(ticker, session=session).info
                    sector = info.get('sector', info.get('industry', 'Unknown'))
                except Exception:
                    pass
            time.sleep(0.5) 
            
        sectors.append(sector)
        
    top_gainers = top_gainers.copy()
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
            
    unknown_count = top_gainers[top_gainers['Sector'] == 'Unknown'].shape[0]
    if unknown_count > 0:
        sector_msg_content += f"\n🔸 **ไม่สามารถระบุกลุ่มได้ (Unknown / อื่นๆ)**: {unknown_count} ตัว\n"

    # --- ส่งข้อความเข้า Discord ---
    print(f"ส่งข้อมูล Top {TOP_N} Gainers...")
    title_top = f"TOP {TOP_N} GAINERS (Price > ${MIN_PRICE}, Avg Vol > ${MIN_DOLLAR_VOLUME/1_000_000}M)"
    send_to_discord(top_gainers, title_top, DISCORD_WEBHOOK_URL)
    
    print("ส่งข้อมูล Watchlist Update...")
    title_watch = "📌 CUSTOM WATCHLIST UPDATE"
    send_to_discord(watchlist_df, title_watch, DISCORD_WEBHOOK_URL)
    
    print("ส่งข้อมูล Sector Summary...")
    requests.post(DISCORD_WEBHOOK_URL, json={"content": sector_msg_content})
        
    print("✅ สแกนทั้งตลาด ดึงกลุ่ม Sector และส่งเข้า Discord เรียบร้อย!")

if __name__ == "__main__":
    main()
