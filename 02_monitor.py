def run_monitor():
    print(f"🚀 Starting Monitor [{TABLE_NAME}]...")
    market_health = get_market_sentiment()
    
    # --- 1. ปรับ Query ให้ดึงข้อมูลมาดูทั้งหมดก่อนเพื่อความชัวร์ ---
    res = supabase.table(TABLE_NAME).select("*").execute()
    stocks = res.data
    
    if not stocks:
        print(f"⚠️ No data found in table '{TABLE_NAME}'. Please check your DB.")
        return

    print(f"🔍 Found {len(stocks)} stocks in DB. Starting analysis...")
    
    updates_count = 0
    error_count = 0

    for item in stocks:
        ticker = item['ticker']
        # กรองเฉพาะตัวที่ยังไม่ได้ขาย (ในระดับโค้ดจะแม่นยำกว่า)
        if item.get('status') == 'sold':
            continue

        region = 'TH' if '.BK' in ticker else 'US'
        if not market_health.get(region, True): continue

        try:
            stock = yf.Ticker(ticker)
            # ใช้ period="2d" บังคับดึงค่าใหม่
            hist = stock.history(period="2d")
            
            if len(hist) < 1: 
                print(f"   ❓ {ticker}: No price data found.")
                error_count += 1
                continue
            
            current_price = hist['Close'].iloc[-1]
            
            # --- 2. อัปเดตข้อมูลราคา ---
            update_payload = {
                "last_price": current_price,
                "last_update": datetime.datetime.now().isoformat()
            }
            
            # ตรวจสอบและตั้งค่า base_high หากยังไม่มี
            if not item.get('base_high') or item.get('base_high') == 0:
                # ดึง 1y เพื่อหา High
                full_hist = stock.history(period="1y")
                high_52w = full_hist['High'].max() if not full_hist.empty else current_price
                update_payload['base_high'] = high_52w
                update_payload['highest_price'] = current_price
            
            # --- 3. บันทึกกลับลง Database ---
            supabase.table(TABLE_NAME).update(update_payload).eq("id", item['id']).execute()
            updates_count += 1
            
            # พิมพ์บอกความคืบหน้าทุกๆ 10 ตัว
            if updates_count % 10 == 0:
                print(f"   ...processed {updates_count} tickers")

        except Exception as e:
            error_count += 1
            continue
            
    # --- 4. รายงานสรุปส่ง Discord ---
    summary = f"✅ **Monitor Scan Complete**\n"
    summary += f"• Total: {len(stocks)}\n"
    summary += f"• Updated: {updates_count}\n"
    summary += f"• Errors: {error_count}"
    
    print(f"\n{summary}")
    if IS_TEST_MODE:
        notify(summary)
