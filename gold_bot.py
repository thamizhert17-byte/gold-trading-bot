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
            if text == 'signal':
                return True
    except Exception as e:
        print(f"Command check error: {e}")
    return False

def get_live_price():
    """Gets the absolute latest live price using a direct API to avoid Yahoo cache"""
    try:
        # Direct API for live price (bypasses Yahoo cache)
        r = requests.get("https://api.gold-api.com/price/XAU", timeout=5).json()
        if 'price' in r and r['price'] > 0:
            return round(float(r['price']), 2)
    except:
        pass
    
    # Fallback: Use yfinance download method (often fresher than .history)
    try:
        df = yf.download('GC=F', period='1d', interval='1m', progress=False)
        if not df.empty:
            return round(float(df['Close'].iloc[-1]), 2)
    except:
        pass
        
    return None

def get_15m_data():
    """Gets 15-minute data for efficient entry signals"""
    # Using download() instead of history() to avoid cache issues
    df = yf.download(SYMBOL, period='10d', interval='15m', progress=False).dropna()
    if len(df) < 50:
        return None
    
    df['EMA9'] = df['Close'].ewm(span=9, adjust=False).mean()
    df['EMA21'] = df['Close'].ewm(span=21, adjust=False).mean()
    
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
        "rsi": round(float(latest['RSI']), 2),
        "atr": round(float(latest['ATR']), 2)
    }

def generate_efficient_signal(data):
    p = data["price"]
    ema9 = data["ema9"]
    ema21 = data["ema21"]
    rsi = data["rsi"]
    atr = data["atr"]
    
    if atr <= 0:
        return None

    if ema9 > ema21 and p > ema9 and 50 < rsi < 75:
        sl = round(p - (1.5 * atr), 2)
        tp1 = round(p + (2.0 * atr), 2)
        tp2 = round(p + (3.0 * atr), 2)
        rr = (tp2 - p) / (p - sl)
        if rr >= 1.5:
            return {"type": "🟢 BUY", "entry": p, "sl": sl, "tp1": tp1, "tp2": tp2, "rr": round(rr, 2)}
    
    if ema9 < ema21 and p < ema9 and 25 < rsi < 50:
        sl = round(p + (1.5 * atr), 2)
        tp1 = round(p - (2.0 * atr), 2)
        tp2 = round(p - (3.0 * atr), 2)
        rr = (p - tp2) / (sl - p)
        if rr >= 1.5:
            return {"type": "🔴 SELL", "entry": p, "sl": sl, "tp1": tp1, "tp2": tp2, "rr": round(rr, 2)}
            
    return None

def main():
    print("Gold bot starting...")
    # This gets the EXACT current time in IST when the bot runs
    current_time_ist = datetime.now(IST).strftime("%I:%M %p") 
    
    # 1. Check if user typed "signal"
    if check_user_commands():
        price = get_live_price()
        if price:
            msg = f"💰 <b>Current Gold Price:</b> ${price}\n🕒 <b>Live Time:</b> {current_time_ist} IST"
            send_telegram(msg)
            print("Manual price check sent")
        else:
            send_telegram("⚠️ Could not fetch live price right now.")
        return
    
    # 2. Check for 15m Trading Signals
    data = get_15m_data()
    if not data:
        print("No 15m data available.")
        return
    
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
        # 3. No signal? Just send the exact current live price
        price = get_live_price()
        if price:
            msg = f"💰 <b>Current Gold Price:</b> ${price}\n🕒 <b>Live Time:</b> {current_time_ist} IST"
            send_telegram(msg)
            print("Auto price update sent")
        else:
            print("No signal and could not fetch live price.")

if __name__ == "__main__":
    main()
