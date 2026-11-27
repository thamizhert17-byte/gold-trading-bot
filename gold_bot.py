import os
import requests
import pandas as pd
import numpy as np
from datetime import datetime, timezone, timedelta

# --- CONFIGURATION ---
BOT_TOKEN = os.environ.get("BOT_TOKEN")
CHAT_ID = os.environ.get("CHAT_ID")
API_KEY = os.environ.get("TWELVE_DATA_API")
SYMBOL = "XAU/USD"
IST = timezone(timedelta(hours=5, minutes=30))

# --- TELEGRAM SENDER ---
def send_telegram(message):
    if not BOT_TOKEN or not CHAT_ID:
        print("Error: Missing BOT_TOKEN or CHAT_ID")
        return
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
    payload = {"chat_id": CHAT_ID, "text": message, "parse_mode": "HTML"}
    try:
        r = requests.post(url, data=payload, timeout=15)
        if r.status_code != 200:
            print(f"Telegram API Error: {r.text}")
    except Exception as e:
        print(f"Telegram Network Error: {e}")

# --- COMMAND CHECKER (Prevents duplicate replies) ---
def check_user_commands():
    if not BOT_TOKEN: return False
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/getUpdates"
    try:
        r = requests.get(url, timeout=10).json()
        if r.get('ok') and r.get('result'):
            last_msg = r['result'][-1].get('message', {})
            text = last_msg.get('text', '').strip().lower()
            msg_date = last_msg.get('date', 0)
            current_time = int(datetime.now(timezone.utc).timestamp())
            # Only process if message is 'signal' and was sent in the last 8 minutes
            if text == 'signal' and (0 < (current_time - msg_date) < 480):
                return True
    except Exception as e:
        print(f"Command check error: {e}")
    return False

# --- DATA FETCHER (Robust error handling) ---
def get_realtime_data():
    if not API_KEY: 
        print("Error: Missing TWELVE_DATA_API key")
        return None
    try:
        url = f"https://api.twelvedata.com/time_series?symbol={SYMBOL}&interval=5min&outputsize=100&apikey={API_KEY}"
        r = requests.get(url, timeout=15).json()
        
        # Check for API errors/rate limits
        if r.get('code') and r.get('code') != 200:
            print(f"API Error: {r.get('message')}")
            return None
            
        if 'values' in r and len(r['values']) > 0:
            df = pd.DataFrame(r['values'])
            df = df.rename(columns={'datetime': 'Time'})
            for col in ['open', 'high', 'low', 'close']:
                df[col] = pd.to_numeric(df[col], errors='coerce')
            
            # Sort chronologically
            df = df.iloc[::-1].reset_index(drop=True)
            df['Time'] = pd.to_datetime(df['Time'])
            df = df.set_index('Time')
            df = df.dropna() # Remove any bad data rows
            return df
    except Exception as e:
        print(f"Data fetch error: {e}")
    return None

# --- INDICATOR BUILDER (Handles insufficient data) ---
def build_indicators(df):
    if df is None or len(df) < 50:
        return None # Not enough data to calculate SMA50/RSI reliably
        
    try:
        df['EMA9'] = df['close'].ewm(span=9, adjust=False).mean()
        df['EMA21'] = df['close'].ewm(span=21, adjust=False).mean()
        df['SMA50'] = df['close'].rolling(50).mean()
        
        delta = df['close'].diff()
        gain = delta.where(delta > 0, 0).rolling(14).mean()
        loss = -delta.where(delta < 0, 0).rolling(14).mean()
        rs = gain / loss.replace(0, np.nan)
        df['RSI'] = 100 - (100 / (1 + rs))
        
        high_low = df['high'] - df['low']
        high_close = np.abs(df['high'] - df['close'].shift())
        low_close = np.abs(df['low'] - df['close'].shift())
        df['ATR'] = pd.concat([high_low, high_close, low_close], axis=1).max(axis=1).rolling(14).mean()
        
        # Drop NaNs created by rolling windows
        df = df.dropna()
        if len(df) == 0: return None

        recent = df.tail(50)
        latest = df.iloc[-1]
        
        return {
            "price": round(float(latest['close']), 2),
            "ema9": round(float(latest['EMA9']), 2),
            "ema21": round(float(latest['EMA21']), 2),
            "sma50": round(float(latest['SMA50']), 2),
            "rsi": round(float(latest['RSI']), 2),
            "atr": round(float(latest['ATR']), 2),
            "support": round(float(recent['low'].min()), 2),
            "resistance": round(float(recent['high'].max()), 2)
        }
    except Exception as e:
        print(f"Indicator calculation error: {e}")
        return None

# --- TIME-BASED ALERTS (Wide windows to catch delayed GitHub runs) ---
def check_fundamental_alerts():
    now = datetime.now(IST)
    hour = now.hour
    minute = now.minute
    
    # London Open: 1:15 PM IST. Window: 1:10 PM to 1:20 PM.
    if hour == 13 and 10 <= minute <= 20:
        return "🇬🇧 <b>FUNDAMENTAL ALERT: LONDON OPEN</b>\n\n⏰ London session is active.\n\n📰 Check News:\n✅ GBP & EUR High Impact News\n✅ European Market Openings\n\n💡 High volatility expected."
    
    # NY Open: 6:15 PM IST. Window: 6:10 PM to 6:20 PM.
    if hour == 18 and 10 <= minute <= 20:
        return "🇺🇸 <b>FUNDAMENTAL ALERT: NEW YORK OPEN</b>\n\n⏰ NY session is active.\n\n📰 Check News:\n✅ USD High Impact News (NFP, CPI, Fed)\n✅ US Stock Market Open\n\n💡 Highest volatility of the day."
    
    return None

# --- SIGNAL GENERATOR (Strict logic, zero-division protection) ---
def generate_perfect_signal(data):
    p = data["price"]; ema9 = data["ema9"]; ema21 = data["ema21"]
    sma50 = data["sma50"]; rsi = data["rsi"]; atr = data["atr"]
    sup = data["support"]; res = data["resistance"]
    
    # Protect against dead markets or bad data
    if atr <= 0 or atr > 20 or np.isnan(rsi):
        return None

    # 1. TREND FOLLOWING (Wider SL: 2.0 ATR)
    if p > ema21 > sma50 and ema9 > ema21 and 45 < rsi < 70:
        sl = round(p - 2.0 * atr, 2)  
        tp1 = round(p + 2.5 * atr, 2) 
        tp2 = round(p + 4.0 * atr, 2)
        risk = p - sl
        if risk > 0:
            rr = (tp2 - p) / risk
            if rr >= 2.0:
                return {"type": "🟢 BUY (UpTrend)", "entry": p, "sl": sl, "tp1": tp1, "tp2": tp2,
                        "rr": round(rr, 2), "reason": f"Strong Uptrend. RSI {rsi}."}

    if p < ema21 < sma50 and ema9 < ema21 and 30 < rsi < 55:
        sl = round(p + 2.0 * atr, 2)  
        tp1 = round(p - 2.5 * atr, 2)
        tp2 = round(p - 4.0 * atr, 2)
        risk = sl - p
        if risk > 0:
            rr = (p - tp2) / risk
            if rr >= 2.0:
                return {"type": "🔴 SELL (Downtrend)", "entry": p, "sl": sl, "tp1": tp1, "tp2": tp2,
                        "rr": round(rr, 2), "reason": f"Strong Downtrend. RSI {rsi}."}

    # 2. REVERSAL (Wider SL: 1.0 ATR)
    if p <= sup * 1.002 and rsi < 30 and p > sma50:
        sl = round(sup - 1.0 * atr, 2)  
        tp1 = round((sup + res) / 2, 2); tp2 = round(res, 2)
        risk = p - sl
        if risk > 0:
            rr = (tp2 - p) / risk
            if rr >= 2.5:
                return {"type": "🟢 BUY (Reversal)", "entry": p, "sl": sl, "tp1": tp1, "tp2": tp2,
                        "rr": round(rr, 2), "reason": f"Oversold at Support ${sup}."}

    if p >= res * 0.998 and rsi > 70 and p < sma50:
        sl = round(res + 1.0 * atr, 2)  
        tp1 = round((sup + res) / 2, 2); tp2 = round(sup, 2)
        risk = sl - p
        if risk > 0:
            rr = (p - tp2) / risk
            if rr >= 2.5:
                return {"type": "🔴 SELL (Reversal)", "entry": p, "sl": sl, "tp1": tp1, "tp2": tp2,
                        "rr": round(rr, 2), "reason": f"Overbought at Resistance ${res}."}

    return None

# --- MAIN EXECUTION ---
def main():
    print("Gold Bot Master Plan Active...")
    current_time_ist = datetime.now(IST).strftime("%I:%M %p")

    # 1. USER COMMAND
    if check_user_commands():
        df = get_realtime_data()
        data = build_indicators(df)
        if data:
            trend = "UP" if data['price'] > data['sma50'] else "DOWN"
            msg = f"💰 <b>REAL-TIME PRICE:</b> ${data['price']}\n🕒 Time: {current_time_ist} IST\n📊 RSI: {data['rsi']} | Trend: {trend}"
            send_telegram(msg)
        else:
            send_telegram("⚠️ Could not fetch live data right now.")
        return

    # 2. FUNDAMENTAL ALERTS
    alert = check_fundamental_alerts()
    if alert:
        send_telegram(alert)
        print("Fundamental alert sent")
        return

    # 3. GET DATA & CHECK SIGNALS
    df = get_realtime_data()
    data = build_indicators(df)
    
    if not data:
        print("No valid data available.")
        return

    signal = generate_perfect_signal(data)
    
    if signal:
        msg = f"""
🟡 <b>XAU/USD PERFECT ENTRY</b>

{signal['type']}
💰 <b>Entry:</b> ${signal['entry']}
🛑 <b>SL:</b> ${signal['sl']}
🎯 <b>TP1:</b> ${signal['tp1']}
🎯 <b>TP2:</b> ${signal['tp2']}
⚖️ <b>R:R:</b> 1:{signal['rr']}

📊 RSI: {data['rsi']} | Support: ${data['support']} | Resistance: ${data['resistance']}
🕒 Time: {current_time_ist} IST
⚠️ Verify on TradingView. Risk 1-2%.
"""
        send_telegram(msg)
        print("Perfect signal sent")
    else:
        # 4. QUIET UPDATE (Forgiving time window: :00-:05 and :30-:35 to handle GitHub delays)
        now_min = datetime.now(IST).minute
        if now_min <= 5 or (30 <= now_min <= 35):
            trend = "UP" if data['price'] > data['sma50'] else "DOWN"
            msg = f"📊 <b>Live Update:</b> ${data['price']} | RSI: {data['rsi']} | Trend: {trend}\n🕒 {current_time_ist} IST"
            send_telegram(msg)
            print("30-min update sent")
        else:
            print("No signal. Bot sleeping.")

if __name__ == "__main__":
    main()
