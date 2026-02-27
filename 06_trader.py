import os
import yfinance as yf
from supabase import create_client
import requests
import datetime
import time
import pandas as pd

# --- ⚙️ CONFIGURATION ---
print("💰 [TRADER] Wake up & Initializing...")
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_KEY")
DISCORD_URL = os.getenv("DISCORD_WEBHOOK_TRADER")

supabase = create_client(SUPABASE_URL, SUPABASE_KEY)

IS_TEST_MODE = os.getenv("TEST_MODE", "Off").strip().lower() == "on"
TABLE_TRADES = "ipo_trades_uat" if IS_TEST_MODE else "ipo_trades"
TABLE_HISTORY = "trade_history"

def notify(msg):
    prefix = "🧪 [TEST-TRADER] " if IS_TEST_MODE else "💵 [REAL-TRADER] "
    try:
        requests.post(DISCORD_URL, json={"content": prefix + msg})
    except: pass

def get_realtime_price(ticker):
    """ดึงราคาล่าสุดแบบ Real-time (Re-quote)"""
    try:
        stock = yf.Ticker(ticker)
        # ใช้ 1d, 1m เพื่อเอา candle ล่าสุด
        data = stock.history(period="1d", interval="1m")
        if data.empty:
            # ถ้าดึง intraday ไม่ได้ (เช่น ตลาดปิด) ให้เอาล่าสุดของวัน
            data = stock.history(period="1d")
        
        if data.empty: return None
        return float(data['Close'].iloc[-1])
    except:
        return None

def execute_trade():
    print(f"🚀 Trader Process Started on tables: {TABLE_TRADES} & {TABLE_HISTORY}")
    
    # 1. หาหุ้นที่รอคิวซื้อ (Signal Buy)
    res_buy = supabase.table(TABLE_TRADES).select("*").eq("status", "signal_buy").execute()
    buy_queue = res_buy.data or []
    
    # 2. หาหุ้นที่รอคิวขาย (Signal Sell)
    res_sell = supabase.table(TABLE_TRADES).select("*").eq("status", "signal_sell").execute()
    sell_queue = res_sell.data or []

    if not buy_queue and not sell_queue:
        print("💤 No signals found. Trader is going back to sleep.")
        return

    print(f"🔔 Signals Found! Buy: {len(buy_queue)} | Sell: {len(sell_queue)}")

    # --- 🔵 PROCESS BUY SIGNALS ---
    for item in buy_queue:
        ticker = item['ticker']
        print(f"🛒 Executing BUY: {ticker}...", end=" ")
        
        real_price = get_realtime_price(ticker)
        if not real_price:
            print("❌ Failed to fetch price. Skip.")
            continue

        # บันทึกลง Trade History
        trade_record = {
            "ticker": ticker,
            "market_type": item.get('market_type'),
            "buy_price": real_price,
            "buy_date": datetime.datetime.now().isoformat(),
            "status": "OPEN",
            "note": "Breakout Buy Signal"
        }
        supabase.table(TABLE_HISTORY).insert(trade_record).execute()

        # อัปเดตสถานะใน Watchlist ว่า "ถือของแล้ว" (holding)
        supabase.table(TABLE_TRADES).update({
            "status": "holding",
            "buy_price": real_price, # อัปเดตราคาทุนจริง
            "last_update": datetime.datetime.now().isoformat()
        }).eq("id", item['id']).execute()
        
        print(f"✅ DONE @ {real_price:.2f}")
        notify(f"🛒 **EXECUTED BUY**: {ticker}\nPrice: {real_price:.2f}")
        time.sleep(1)

    # --- 🔴 PROCESS SELL SIGNALS ---
    for item in sell_queue:
        ticker = item['ticker']
        print(f"💰 Executing SELL: {ticker}...", end=" ")
        
        real_price = get_realtime_price(ticker)
        if not real_price:
            print("❌ Failed to fetch price. Skip.")
            continue

        # คำนวณกำไร/ขาดทุน
        buy_price = item.get('buy_price') or real_price # กันเหนียวถ้าไม่มี buy_price
        profit_amount = real_price - buy_price
        profit_pct = (profit_amount / buy_price) * 100

        # ปิดรายการใน Trade History (หา record ล่าสุดที่ยัง OPEN ของตัวนี้)
        # Note: ในทางปฏิบัติเราควร link ID แต่เพื่อความง่าย เราจะหาตัวล่าสุดที่ OPEN
        history_res = supabase.table(TABLE_HISTORY)\
            .select("id")\
            .eq("ticker", ticker)\
            .eq("status", "OPEN")\
            .order("buy_date", desc=True)\
            .limit(1).execute()
        
        if history_res.data:
            trade_id = history_res.data[0]['id']
            supabase.table(TABLE_HISTORY).update({
                "sell_price": real_price,
                "sell_date": datetime.datetime.now().isoformat(),
                "profit_amount": profit_amount,
                "profit_pct": profit_pct,
                "status": "CLOSED",
                "note": "Signal Sell (TP/SL)"
            }).eq("id", trade_id).execute()
        else:
            # กรณีไม่เจอประวัติเก่า (อาจจะซื้อก่อนมีระบบนี้) ให้ insert ใหม่แบบจบในตัว
            supabase.table(TABLE_HISTORY).insert({
                "ticker": ticker,
                "buy_price": buy_price,
                "sell_price": real_price,
                "sell_date": datetime.datetime.now().isoformat(),
                "profit_pct": profit_pct,
                "status": "CLOSED",
                "note": "Force Close (No Open Record)"
            }).execute()

        # อัปเดตสถานะใน Watchlist กลับเป็น watching หรือ sold
        supabase.table(TABLE_TRADES).update({
            "status": "sold", # หรือ watching ถ้าอยากเล่นรอบใหม่
            "sell_price": real_price,
            "last_update": datetime.datetime.now().isoformat()
        }).eq("id", item['id']).execute()

        print(f"✅ SOLD @ {real_price:.2f} ({profit_pct:+.2f}%)")
        notify(f"💰 **EXECUTED SELL**: {ticker}\nPrice: {real_price:.2f}\nP/L: {profit_pct:+.2f}%")
        time.sleep(1)

if __name__ == "__main__":
    execute_trade()
