import os
import requests
import pandas as pd
import numpy as np
from datetime import datetime, timezone, timedelta

BOT_TOKEN = os.environ.get("BOT_TOKEN")
CHAT_ID = os.environ.get("CHAT_ID")
API_KEY = os.environ.get("TWELVE_DATA_API")
SYMBOL = "XAU/USD"
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
            # If message is 'signal' and was sent in the last 15 minutes
            if text == 'signal' and (current_time - msg_date) < 900:
                return True
    except Exception as e:
        print(f"Command check error: {e}")
    return False

def get_realtime_quote():
    """Real-time price from Twelve Data."""
    try:
        url = f"https://api.twelvedata.com/quote?symbol={SYMBOL}&apikey={API_KEY}"
        r = requests.get(url, timeout=10).json()
        if 'close' in r and float(r['close']) > 0:
            return {
                "price": round(float(r['close']), 2),
                "open": round(float(r['open']), 2),
                "high": round(float(r['high']), 2),
                "low": round(float(r['low']), 2)
            }
    except Exception as e:
        print(f"Quote error: {e}")
    return None

def get_time_series():
    """Real-time 5-minute candles."""
    try:
        url = f"https://api.twelvedata.com/time_series?symbol={SYMBOL}&interval=5min&outputsize=100&apikey={API_KEY}"
        r = requests.get(url, timeout=10).json()
        if 'values' in r:
            df = pd.DataFrame(r['values'])
            df = df.rename(columns={'datetime': 'Time'})
            for col in ['open', 'high', 'low', 'close']:
                df[col] = pd.to_numeric(df[col])
            df = df.iloc[::-1].reset_index(drop=True)
            df['Time'] = pd.to_datetime(df['Time'])
            df = df.set_index('Time')
            return df
    except Exception as e:
        print(f"Time series error: {e}")
    return None

def build_indicators(df):
    if df is None or len(df) < 50:
        return None
    df['EMA9'] = df['close'].ewm(span=9, adjust=False).mean()
    df['EMA21'] = df['close'].ewm(span=21, adjust=False).mean()
    df['SMA50'] = df['close'].rolling(50).mean()
    
    delta = df['close'].diff()
    gain = delta.where(delta > 0, 0).rolling(14).mean()
    loss = -delta.where(delta < 0, 0).rolling(14).mean()
    df['RSI'] = 100 - (100 / (1 + gain / loss))
    
    high_low = df['high'] - df['low']
    high_close = np.abs(df['high'] - df['close'].shift())
    low_close = np.abs(df['low'] - df['close'].shift())
    df['ATR'] = pd.concat([high_low, high_close, low_close], axis=1).max(axis=1).rolling(14).mean()
    
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

def generate_signal(data):
    p = data["price"]; ema9 = data["ema9"]; ema21 = data["ema21"]
    sma50 = data["sma50"]; rsi = data["rsi"]; atr = data["atr"]
    sup = data["support"]; res = data["resistance"]
    
    if atr <= 0:
        return None

    # 1. BUY: Strong uptrend
    if p > ema21 > sma50 and ema9 > ema21 and rsi < 75:
        sl = round(p - 1.5 * atr, 2)
        tp1 = round(p + 2 * atr, 2); tp2 = round(p + 3.5 * atr, 2)
        rr = (tp2 - p) / (p - sl)
        if rr >= 1.5:
            return {"type": "🟢 BUY (Uptrend)", "entry": p, "sl": sl, "tp1": tp1, "tp2": tp2,
                    "rr": round(rr, 2), "reason": f"Price > EMA21 > SMA50. RSI {rsi}."}

    # 2. SELL: Strong downtrend
    if p < ema21 < sma50 and ema9 < ema21 and rsi > 25:
        sl = round(p + 1.5 * atr, 2)
        tp1 = round(p - 2 * atr, 2); tp2 = round(p - 3.5 * atr, 2)
        rr = (p - tp2) / (sl - p)
        if rr >= 1.5:
            return {"type": "🔴 SELL (Downtrend)", "entry": p, "sl": sl, "tp1": tp1, "tp2": tp2,
                    "rr": round(rr, 2), "reason": f"Price < EMA21 < SMA50. RSI {rsi}."}

    # 3. BUY: Support bounce
    if p <= sup * 1.002 and rsi < 35 and p > sma50:
        sl = round(sup - 0.8 * atr, 2)
        tp1 = round((sup + res) / 2, 2); tp2 = round(res, 2)
        rr = (tp2 - p) / (p - sl)
        if rr >= 2.0:
            return {"type": "🟢 BUY (Support Bounce)", "entry": p, "sl": sl, "tp1": tp1, "tp2": tp2,
                    "rr": round(rr, 2), "reason": f"Oversold at support ${sup}."}

    # 4. SELL: Resistance reject
    if p >= res * 0.998 and rsi > 65 and p < sma50:
        sl = round(res + 0.8 * atr, 2)
        tp1 = round((sup + res) / 2, 2); tp2 = round(sup, 2)
        rr = (p - tp2) / (sl - p)
        if rr >= 2.0:
            return {"type": "🔴 SELL (Resistance Reject)", "entry": p, "sl": sl, "tp1": tp1, "tp2": tp2,
                    "rr": round(rr, 2), "reason": f"Overbought at resistance ${res}."}

    return None

def main():
    print("Gold bot starting (real-time)...")
    current_time_ist = datetime.now(IST).strftime("%I:%M %p")

    # 1. Check if user typed "signal"
    if check_user_commands():
        quote = get_realtime_quote()
        if quote:
            msg = f"💰 <b>REAL-TIME Gold Price:</b> ${quote['price']}\n🕒 Time: {current_time_ist} IST\n📈 High: ${quote['high']} | 📉 Low: ${quote['low']}"
            send_telegram(msg)
        return

    # 2. Get real-time 5m candles
    df = get_time_series()
    data = build_indicators(df)
    if not data:
        print("No data available.")
        return

    # 3. Check for Entry Signals
    signal = generate_signal(data)
    
    if signal:
        msg = f"""
🟡 <b>XAU/USD ENTRY SIGNAL</b>

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
        print("Signal sent")
    else:
        # 4. Quiet 10-min update
        trend = "UP" if data['price'] > data['sma50'] else "DOWN"
        msg = f"💰 <b>Live Price:</b> ${data['price']} | RSI: {data['rsi']} | Trend: {trend}\n🕒 {current_time_ist} IST"
        send_telegram(msg)
        print("Update sent")

if __name__ == "__main__":
    main()
