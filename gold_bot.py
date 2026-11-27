import os
import requests
import yfinance as yf
from datetime import datetime

# Get your secrets from GitHub
BOT_TOKEN = os.environ.get("BOT_TOKEN")
CHAT_ID = os.environ.get("CHAT_ID")

def send_telegram(text):
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
    data = {"chat_id": CHAT_ID, "text": text}
    try:
        r = requests.post(url, data=data, timeout=10)
        # This prints the result in the GitHub log so we can debug
        print(f"Telegram API Response: {r.status_code} - {r.text}") 
    except Exception as e:
        print(f"Network Error: {e}")

def main():
    print("🚀 Starting Test Bot...")
    
    # TEST 1: Simple connection check
    send_telegram("🚀 TEST 1: Your Gold Bot is connected to Telegram!")
    
    # TEST 2: Fetch live price
    try:
        ticker = yf.Ticker("XAUUSD=X")
        df = ticker.history(period="1d")
        
        if not df.empty:
            price = df['Close'].iloc[-1]
            send_telegram(f"📊 TEST 2: Live Gold Price is ${price:.2f}")
        else:
            send_telegram("❌ TEST 2: Could not fetch price data.")
    except Exception as e:
        send_telegram(f"❌ TEST 2 Error: {e}")

    print("✅ Test finished.")

if __name__ == "__main__":
    main()
