import os
import requests
import yfinance as yf
import pandas as pd
import numpy as np
from datetime import datetime, timezone, timedelta

BOT_TOKEN = os.environ.get("BOT_TOKEN")
CHAT_ID = os.environ.get("CHAT_ID")
SYMBOL = "GC=F"
IST = timezone(timedelta(hours=5, minutes=30))

def send_telegram(message):
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
    payload = {"chat_id": CHAT_ID, "text": message, "parse_mode": "HTML"}
    try:
        r = requests.post(url, data=payload, timeout=15)
        print(f"Telegram: {r.status_code}")
    except Exception as e:
        print(f"Telegram error: {e}")

def check_user_commands():
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/getUpdates"
    try:
        r = requests.get(url, timeout=10).json()
        if r.get('ok') and r.get('result'):
            last_msg = r['result'][-1].get('message', {})
            text = last_msg.get('text', '').strip().lower()
            msg_date = last_msg.get('date', 0)
            current_time = int(datetime.now(timezone.utc).timestamp())
            if text == 'signal' and (current_time - msg_date) < 2100:
                return True
    except Exception as e:
        print(f"Command check error: {e}")
    return False

def get_live_price():
    """Fast price check using API only. No heavy downloads."""
    try:
        r = requests.get("https://api.gold-api.com/price/XAU", timeout=5).json()
        if 'price' in r and r['price'] > 0:
            return round(float(r['price']), 2)
    except:
        pass
    return None

def get_15m_data():
    """Gets 15-minute data. This is fast and reliable."""
    try:
        df = yf.download(SYMBOL, period='5d', interval='15m', progress=False, timeout=10).dropna()
        if len(df) < 20:
            return None
        
        df['EMA9'] = df['Close'].ewm(span=9, adjust=False).mean()
        df['EMA21'] = df['Close'].ewm(span=21, adjust=False).mean()
        df['SMA50'] = df['Close'].rolling(50).mean()
        
        delta = df['Close'].diff()
        gain = delta.where(delta > 0, 0).rolling(14).mean()
        loss = -delta.where(delta < 0, 0).rolling(14).mean()
        df['RSI'] = 100 - (100 / (1 + gain / loss))
        
        high_low = df['High'] - df['Low']
        high_close = np.abs(df['High'] - df['Close'].shift())
        low_close = np.abs(df['Low'] - df['Close'].shift())
        df['ATR'] = pd.concat([high_low, high_close, low_close], axis=1).max(axis=1).rolling(14).mean()
        
        latest = df.iloc[-1]
        return {
            "price": round(float(latest['Close']), 2),
            "ema9": round(float(latest['EMA9']), 2),
            "ema21": round(float(latest['EMA21']), 2),
            "sma50": round(float(latest['SMA50']), 2),
            "rsi": round(float(latest['RSI']), 2),
            "atr": round(float(latest['ATR']), 2)
        }
    except Exception as e:
        print(f"Data error: {e}")
        return None

def generate_efficient_signal(data):
    p = data["price"]
    ema9 = data["ema9"]
    ema21 = data["ema21"]
    sma50 = data["sma50"]
    rsi = data["rsi"]
    atr = data["atr"]
    
    if atr <= 0:
        return None

    # BUY: Strong Uptrend
    if p > ema21 > sma50 and rsi < 80:
        sl = round(p - (1.5 * atr), 2)
        tp1 = round(p + (2.0 * atr), 2)
        tp2 = round(p + (3.0 * atr), 2)
        rr = (tp2 - p) / (p - sl)
        if rr >= 1.5:
            return {"type": "🟢 BUY (Trend)", "entry": p, "sl": sl, "tp1": tp1, "tp2": tp2, "rr": round(rr, 2)}
    
    # SELL: Strong Downtrend
    if p < ema21 < sma50 and rsi > 20:
        sl = round(p + (1.5 * atr), 2)
        tp1 = round(p - (2.0 * atr), 2)
        tp2 = round(p - (3.0 * atr), 2)
        rr = (p - tp2) / (sl - p)
        if rr >= 1.5:
            return {"type": "🔴 SELL (Trend)", "entry": p, "sl": sl, "tp1": tp1, "tp2": tp2, "rr": round(rr, 2)}
            
    return None

def main():
    print("Gold bot starting...")
    current_time_ist = datetime.now(IST).strftime("%I:%M %p") 
    
    # 1. Check if user typed "signal"
    if check_user_commands():
        price = get_live_price()
        # If API fails, we don't hang. We just say checking data.
        if not price:
            data = get_15m_data()
            if data: price = data['price']
            
        if price:
            msg = f"💰 <b>Current Gold Price:</b> ${price}\n🕒 <b>Live Time:</b> {current_time_ist} IST"
            send_telegram(msg)
            print("Manual price check sent")
        return
    
    # 2. Get 15m Data (Fast & Reliable)
    data = get_15m_data()
    if not data:
        print("No 15m data available.")
        return
    
    # 3. Check for Signals
    signal = generate_efficient_signal(data)
    
    if signal:
        msg = f"""
🟡 <b>XAU/USD ENTRY SIGNAL</b>

{signal['type']}
💰 <b>Entry:</b> ${signal['entry']}
🛑 <b>Stop Loss:</b> ${signal['sl']}
🎯 <b>TP1:</b> ${signal['tp1']}
🎯 <b>TP2:</b> ${signal['tp2']}
⚖️ <b>R:R:</b> 1:{signal['rr']}

📊 RSI: {data['rsi']} | 15m Trend Active
🕒 <b>Time:</b> {current_time_ist} IST
⚠️ Confirm with TradingView. Risk 1-2%.
"""
        send_telegram(msg)
        print("Trading signal sent")
    else:
        # 4. No signal? Send the price from the 15m data (it's fresh enough)
        price = data['price']
        msg = f"💰 <b>Current Gold Price:</b> ${price}\n🕒 <b>Live Time:</b> {current_time_ist} IST"
        send_telegram(msg)
        print("Auto price update sent")

if __name__ == "__main__":
    main()
