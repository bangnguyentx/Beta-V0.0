import ccxt
import pandas as pd
import pandas_ta as ta

def get_market_signal(symbol="BTC/USDT", timeframe="15m"):
    """
    Trả về: Signal (BUY/SELL/NEUTRAL), Close Price, Indicators Info
    """
    exchange = ccxt.binance() # Public API
    try:
        # 1. Fetch Data
        bars = exchange.fetch_ohlcv(symbol, timeframe, limit=100)
        df = pd.DataFrame(bars, columns=['timestamp', 'open', 'high', 'low', 'close', 'volume'])
        
        # 2. Indicators
        df['rsi'] = df.ta.rsi(length=14)
        bb = df.ta.bbands(length=20, std=2)
        df = pd.concat([df, bb], axis=1)
        
        # 3. Physics Logic (Acceleration)
        df['delta'] = df['close'].diff()
        df['velocity'] = df['delta'].rolling(window=3).mean()
        df['accel'] = df['velocity'].diff()
        
        # Lấy nến đóng cửa gần nhất
        last = df.iloc[-1]
        close = last['close']
        rsi = last['rsi']
        accel = last['accel']
        lower_band = last['BBL_20_2.0']
        upper_band = last['BBU_20_2.0']

        # 4. Signal Logic
        signal = "NEUTRAL"
        
        # LONG: RSI < 30 + Giá thủng Band dưới + Gia tốc Dương (Đà giảm yếu đi)
        if rsi < 30 and close < lower_band and accel > 0:
            signal = "BUY"
            
        # SHORT: RSI > 70 + Giá thủng Band trên + Gia tốc Âm (Đà tăng yếu đi)
        elif rsi > 70 and close > upper_band and accel < 0:
            signal = "SELL"
            
        return signal, close, f"RSI:{rsi:.1f}|Accel:{accel:.2f}"
        
    except Exception as e:
        print(f"Error fetching data: {e}")
        return "ERROR", 0, str(e)
