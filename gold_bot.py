import os
import requests
import yfinance as yf
import pandas as pd
import numpy as np
from datetime import datetime, timezone

BOT_TOKEN = os.environ.get("BOT_TOKEN")
CHAT_ID = os.environ.get("CHAT_ID")
SYMBOL = "GC=F"

def send_telegram(message):
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
    payload = {"chat_id": CHAT_ID, "text": message, "parse_mode": "HTML"}
    try:
        r = requests.post(url, data=payload, timeout=15)
        print(f"Telegram: {r.status_code}")
    except Exception as e:
        print(f"Telegram error: {e}")

def check_user_commands():
    """Checks if the user typed 'signal' in the bot recently"""
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

def get_data():
    df = yf.Ticker(SYMBOL).history(period="1mo", interval="1h").dropna()
    if len(df) < 20:
        return None
    
    df["SMA20"] = df["Close"].rolling(20).mean()
    df["SMA50"] = df["Close"].rolling(50).mean()
    
    delta = df["Close"].diff()
    gain = delta.where(delta > 0, 0).rolling(14).mean()
    loss = -delta.where(delta < 0, 0).rolling(14).mean()
    df["RSI"] = 100 - (100 / (1 + gain / loss))
    
    high_low = df["High"] - df["Low"]
    high_close = np.abs(df["High"] - df["Close"].shift())
    low_close = np.abs(df["Low"] - df["Close"].shift())
    df["ATR"] = pd.concat([high_low, high_close, low_close], axis=1).max(axis=1).rolling(14).mean()
    
    recent = df.tail(50)
    return {
        "price": round(float(df["Close"].iloc[-1]), 2),
        "sma20": round(float(df["SMA20"].iloc[-1]), 2),
        "sma50": round(float(df["SMA50"].iloc[-1]), 2),
        "rsi": round(float(df["RSI"].iloc[-1]), 2),
        "atr": round(float(df["ATR"].iloc[-1]), 2),
        "support": round(float(recent["Low"].min()), 2),
        "resistance": round(float(recent["High"].max()), 2),
        "time": df.index[-1].strftime("%Y-%m-%d %H:%M UTC")
    }

def get_daily_trend():
    df = yf.Ticker(SYMBOL).history(period="3mo", interval="1d").dropna()
    if len(df) < 20:
        return "NEUTRAL"
    df["SMA20"] = df["Close"].rolling(20).mean()
    price = float(df["Close"].iloc[-1])
    sma = float(df["SMA20"].iloc[-1])
    return "BULLISH" if price > sma else "BEARISH"

def generate_signal(data, daily_trend):
    p = data["price"]
    rsi = data["rsi"]
    sma20 = data["sma20"]
    atr = data["atr"]
    sup = data["support"]
    res = data["resistance"]
    
    if atr <= 0:
        return None
    
    if p > sma20 and rsi < 60 and daily_trend == "BULLISH":
        sl = round(p - 1.5 * atr, 2)
        tp1 = round(p + 2 * atr, 2)
        tp2 = round(p + 3 * atr, 2)
        rr = (tp2 - p) / (p - sl)
        if rr >= 1.5:
            return {"type": "🟢 BUY", "entry": p, "sl": sl, "tp1": tp1, "tp2": tp2, "rr": round(rr, 2),
                    "reason": f"1H Trend Bullish. RSI {rsi}. Support: {sup}"}
    
    if p < sma20 and rsi > 40 and daily_trend == "BEARISH":
        sl = round(p + 1.5 * atr, 2)
        tp1 = round(p - 2 * atr, 2)
        tp2 = round(p - 3 * atr, 2)
        rr = (p - tp2) / (sl - p)
        if rr >= 1.5:
            return {"type": "🔴 SELL", "entry": p, "sl": sl, "tp1": tp1, "tp2": tp2, "rr": round(rr, 2),
                    "reason": f"1H Trend Bearish. RSI {rsi}. Resistance: {res}"}
    
    return None

def check_session_alerts():
    now = datetime.now(timezone.utc)
    hour = now.hour
    minute = now.minute
    
    if hour == 7 and minute == 30:
        return "🇬🇧 <b>LONDON SESSION OPENING SOON</b>\n\n⏰ 30 mins to London Open (1:30 PM IST)\n\n📋 Checklist:\n✅ Check GBP/EUR news\n✅ Review overnight levels\n✅ Get ready for volatility!"
    
    if hour == 12 and minute == 30:
        return "🇺🇸 <b>NEW YORK SESSION OPENING SOON</b>\n\n⏰ 30 mins to NY Open (6:30 PM IST)\n\n📋 Checklist:\n✅ Check USD news\n✅ Review London trend\n✅ Highest volatility time!"
    
    return None

def main():
    print("Gold bot starting...")
    
    # 1. Check for scheduled session alerts
    session_alert = check_session_alerts()
    if session_alert:
        send_telegram(session_alert)
        print("Session alert sent")
        return
    
    # 2. Check if user typed "signal" in Telegram
    if check_user_commands():
        data = get_data()
        if data:
            msg = f"🤖 <b>Bot Status: ALIVE</b>\n\n📌 <b>Current Live Price:</b> ${data['price']}\n📊 Daily Trend: {get_daily_trend()}\n🕒 Data Time: {data['time']}\n\n✅ System is working perfectly."
            send_telegram(msg)
            print("User command 'signal' processed")
        return
    
    # 3. Get market data for auto-updates
    data = get_data()
    if not data:
        print("No market data available right now.")
        return
    
    daily_trend = get_daily_trend()
    
    # 4. Check for trading signals
    signal = generate_signal(data, daily_trend)
    
    if signal:
        msg = f"""
🟡 <b>XAU/USD SIGNAL (1H Timeframe)</b>

📌 <b>Current Price:</b> ${data['price']}
🕒 Data Time: {data['time']}
📊 Daily Trend: {daily_trend}

{signal['type']}

💰 <b>Entry:</b> ${signal['entry']}
🛑 <b>Stop Loss:</b> ${signal['sl']}
🎯 <b>TP1:</b> ${signal['tp1']}
🎯 <b>TP2:</b> ${signal['tp2']}
⚖️ <b>R:R:</b> 1:{signal['rr']}

💡 {signal['reason']}

⚠️ Confirm with TradingView. Risk 1-2%.
"""
        send_telegram(msg)
        print("Signal sent")
    else:
        # 5. Send regular 30-minute price update
        msg = f"""
📊 <b>XAU/USD UPDATE</b>

📌 <b>Current Price:</b> ${data['price']}
📈 SMA20: {data['sma20']}
📉 SMA50: {data['sma50']}
📊 RSI: {data['rsi']}
🧱 Support: {data['support']}
🧱 Resistance: {data['resistance']}
📊 Daily Trend: {daily_trend}

⏰ Time: {data['time']}
"""
        send_telegram(msg)
        print("Price update sent")

if __name__ == "__main__":
    main()
