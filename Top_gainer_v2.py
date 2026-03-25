def get_sp500_tickers():
    url = 'https://en.wikipedia.org/wiki/List_of_S%26P_500_companies'
    headers = {'User-Agent': 'Mozilla/5.0'}
    try:
        response = requests.get(url, headers=headers)
        df = pd.read_html(response.text)[0]
        return df['Symbol'].str.replace('.', '-', regex=False).tolist()
    except: return []

def format_change(current, previous):
    """คำนวณ % และคืนค่าพร้อม Emoji วงกลม"""
    if previous == 0: return "⚪0.0%"
    diff = ((current - previous) / previous) * 100
    emoji = "🟢" if diff >= 0 else "🔴"
    return f"{emoji}{abs(diff):.1f}%"

def main():
    print("🚀 วิเคราะห์หุ้น US และสร้าง Report แบบเน้นเทรนด์สี...")
    tickers = get_sp500_tickers()
    if not tickers: return

    # ดึงข้อมูลย้อนหลัง 12 วันเพื่อให้ได้วันทำการครบ 6 ช่วง (เพื่อคำนวณ % ของ 5 วันล่าสุด)
    data = yf.download(tickers, period="12d", interval="1d", group_by='ticker', threads=True)
    
    all_results = []
    for ticker in tickers:
        try:
            h = data[ticker]['Close'].dropna().tail(6)
            if len(h) < 6: continue
            
            # คำนวณ % รายวันย้อนหลัง 5 วัน (เรียงจาก Today ถอยหลังไป)
            daily_stats = []
            for i in range(1, 6):
                # เทียบราคาปิดวันนั้น กับ วันก่อนหน้า
                stat = format_change(h.iloc[-i], h.iloc[-(i+1)])
                daily_stats.append(stat)

            # ใช้ % วันนี้ (index 0 ใน daily_stats) เป็นตัวตัดสิน Top Gainer
            today_pct_val = ((h.iloc[-1] - h.iloc[-2]) / h.iloc[-2]) * 100

            all_results.append({
                'Ticker': ticker,
                'Price': h.iloc[-1],
                'TodayVal': today_pct_val,
                'History': daily_stats # [Today, D-1, D-2, D-3, D-4]
            })
        except: continue

    # เลือก Top 50
    df = pd.DataFrame(all_results)
    top_50 = df.sort_values(by='TodayVal', ascending=False).head(50)

    # สร้าง Message
    header = "🚀 **TOP 50 US GAINERS (5-DAY TREND)** 🚀\n"
    table_header = f"{'Ticker':<7} | {'Price':<7} | {'Today':<7} | {'History (New -> Old)':<25}\n"
    sep = "-" * 65 + "\n"
    
    current_batch = ""
    for _, row in top_50.iterrows():
        # รวมประวัติ Day-1 ถึง Day-4 เข้าด้วยกัน
        hist_str = " ".join(row['History'][1:]) 
        line = f"{row['Ticker']:<7} | {row['Price']:>7.2f} | {row['History'][0]:<7} | {hist_str}\n"
        
        # คุมความยาว Discord Message
        if len(header + "```\n" + current_batch + line + "```") > 1900:
            msg = header + "```\n" + table_header + sep + current_batch + "```"
            requests.post(DISCORD_WEBHOOK_URL, json={"content": msg})
            current_batch = line
            header = "" 
        else:
            current_batch += line

    if current_batch:
        msg = header + "```\n" + (table_header if header else "") + sep + current_batch + "```"
        requests.post(DISCORD_WEBHOOK_URL, json={"content": msg})

if __name__ == "__main__":
    main()
