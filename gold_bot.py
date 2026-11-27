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

def get_data(interval="5m", period="1mo"):
    # Changed period to 1mo to ensure we get enough data
    df = yf.Ticker(SYMBOL).history(period=period, interval=interval).dropna()
    
    # Changed requirement from 60 to 20 candles
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

def get_hourly_trend():
    df = yf.Ticker(SYMBOL).history(period="1mo", interval="1h").dropna()
    if len(df) < 50:
        return "NEUTRAL"
    df["SMA20"] = df["Close"].rolling(20).mean()
    price = float(df["Close"].iloc[-1])
    sma = float(df["SMA20"].iloc[-1])
    return "BULLISH" if price > sma else "BEARISH"

def generate_signal(data_5m, hourly_trend):
    p = data_5m["price"]
    rsi = data_5m["rsi"]
    sma20 = data_5m["sma20"]
    sma50 = data_5m["sma50"]
    atr = data_5m["atr"]
    sup = data_5m["support"]
    res = data_5m["resistance"]
    
    if atr <= 0:
        return None
    
    if p > sma20 > sma50 and 45 <= rsi <= 65 and hourly_trend == "BULLISH":
        sl = round(p - 1.5 * atr, 2)
        tp1 = round(p + 2 * atr, 2)
        tp2 = round(p + 3.5 * atr, 2)
        rr = (tp2 - p) / (p - sl)
        if rr >= 2.0:
            return {"type": "🟢 BUY — Trend", "entry": p, "sl": sl, "tp1": tp1, "tp2": tp2, "rr": round(rr, 2),
                    "reason": f"5m + 1H bullish alignment. RSI {rsi}"}
    
    if p < sma20 < sma50 and 35 <= rsi <= 55 and hourly_trend == "BEARISH":
        sl = round(p + 1.5 * atr, 2)
        tp1 = round(p - 2 * atr, 2)
        tp2 = round(p - 3.5 * atr, 2)
        rr = (p - tp2) / (sl - p)
        if rr >= 2.0:
            return {"type": "🔴 SELL — Trend", "entry": p, "sl": sl, "tp1": tp1, "tp2": tp2, "rr": round(rr, 2),
                    "reason": f"5m + 1H bearish alignment. RSI {rsi}"}
    
    if p <= sup * 1.003 and rsi < 35 and hourly_trend != "BEARISH":
        sl = round(sup - 0.8 * atr, 2)
        tp1 = round((sup + res) / 2, 2)
        tp2 = round(res, 2)
        rr = (tp2 - p) / (p - sl)
        if rr >= 2.0:
            return {"type": "🟢 BUY — Support Bounce", "entry": p, "sl": sl, "tp1": tp1, "tp2": tp2, "rr": round(rr, 2),
                    "reason": f"Near support ${sup}. Oversold RSI {rsi}"}
    
    if p >= res * 0.997 and rsi > 65 and hourly_trend != "BULLISH":
        sl = round(res + 0.8 * atr, 2)
        tp1 = round((sup + res) / 2, 2)
        tp2 = round(sup, 2)
        rr = (p - tp2) / (sl - p)
        if rr >= 2.0:
            return {"type": "🔴 SELL — Resistance Reject", "entry": p, "sl": sl, "tp1": tp1, "tp2": tp2, "rr": round(rr, 2),
                    "reason": f"Near resistance ${res}. Overbought RSI {rsi}"}
    
    return None

def check_session_alerts():
    now = datetime.now(timezone.utc)
    hour = now.hour
    minute = now.minute
    
    if hour == 7 and 45 <= minute <= 50:
        return "🇬🇧 <b>LONDON SESSION OPENING SOON</b>\n\n⏰ 15 minutes until London market opens (1:30 PM IST)\n\n📋 Checklist:\n✅ Check economic calendar for GBP/EUR news\n✅ Review overnight price action\n✅ Identify key support/resistance levels\n✅ Be ready for volatility spike\n\n💡 London session = High liquidity, big moves possible"
    
    if hour == 12 and 45 <= minute <= 50:
        return "🇺🇸 <b>NEW YORK SESSION OPENING SOON</b>\n\n⏰ 15 minutes until NY market opens (6:30 PM IST)\n\n📋 Checklist:\n✅ Check USD news (NFP, CPI, Fed speeches)\n✅ Review London session trend\n✅ Identify key levels for NY overlap\n✅ Highest volatility time (6:30-10:30 PM IST)\n\n💡 London+NY overlap = Best trading opportunities"
    
    return None

def main():
    print("Gold bot starting...")
    
    session_alert = check_session_alerts()
    if session_alert:
        send_telegram(session_alert)
        print("Session alert sent")
        return
    
    data_5m = get_data("5m", "1mo")
    if not data_5m:
        send_telegram("⚠️ Gold bot: no market data")
        return
    
    hourly_trend = get_hourly_trend()
    signal = generate_signal(data_5m, hourly_trend)
    
    if signal:
        msg = f"""
🟡 <b>XAU/USD SIGNAL</b>

📌 <b>Current running price:</b> ${data_5m['price']}
🕒 Data time: {data_5m['time']}
📊 1H Trend: {hourly_trend}

{signal['type']}

💰 <b>Entry:</b> ${signal['entry']}
🛑 <b>Stop Loss:</b> ${signal['sl']}
🎯 <b>TP1:</b> ${signal['tp1']}
🎯 <b>TP2:</b> ${signal['tp2']}
⚖️ <b>R:R:</b> 1:{signal['rr']}

📊 RSI: {data_5m['rsi']}
📈 SMA20: {data_5m['sma20']}
📉 SMA50: {data_5m['sma50']}
🧱 Support: {data_5m['support']}
🧱 Resistance: {data_5m['resistance']}

💡 {signal['reason']}

⚠️ Confirm with your TradingView live price.
⚠️ Risk 1-2% only. Not financial advice.
"""
        send_telegram(msg)
        print("Signal sent")
    else:
        print(f"No signal. Price: ${data_5m['price']} | 1H: {hourly_trend} | RSI: {data_5m['rsi']}")

if __name__ == "__main__":
    main()
