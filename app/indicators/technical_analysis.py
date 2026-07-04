import numpy as np
import pandas as pd
from typing import Dict, Any, List

class TechnicalAnalysis:
    """
    Calculates technical indicators for stocks:
    SMA, EMA, ATR, RSI, MACD, Bollinger Bands, Support/Resistance, Pivot Points, VWAP, RVOL.
    """
    
    @staticmethod
    def calculate_all(historical_bars: List[Dict[str, Any]], current_quote: Dict[str, Any]) -> Dict[str, Any]:
        """
        Calculate all indicators.
        historical_bars is a list of daily bars sorted oldest to newest.
        current_quote contains current market data.
        """
        if not historical_bars or len(historical_bars) < 14:
            return {}

        # Convert to Pandas DataFrame
        df = pd.DataFrame(historical_bars)
        
        # Ensure correct datatypes
        df["close"] = df["close"].astype(float)
        df["high"] = df["high"].astype(float)
        df["low"] = df["low"].astype(float)
        df["open"] = df["open"].astype(float)
        df["volume"] = df["volume"].astype(float)

        current_price = float(current_quote.get("price", df["close"].iloc[-1]))
        current_volume = float(current_quote.get("volume", df["volume"].iloc[-1]))
        
        # Append current quote as latest row if it is a new trading day
        # For simplicity, we calculate metrics using the historical dataframe
        
        results = {}
        
        try:
            # 1. Moving Averages
            df["sma_20"] = df["close"].rolling(window=20).mean()
            df["sma_50"] = df["close"].rolling(window=50).mean()
            df["sma_200"] = df["close"].rolling(window=200).mean()
            
            # EMA
            df["ema_9"] = df["close"].ewm(span=9, adjust=False).mean()
            df["ema_20"] = df["close"].ewm(span=20, adjust=False).mean()
            df["ema_50"] = df["close"].ewm(span=50, adjust=False).mean()
            
            results["sma_20"] = df["sma_20"].iloc[-1]
            results["sma_50"] = df["sma_50"].iloc[-1] if len(df) >= 50 else df["sma_20"].iloc[-1]
            results["sma_200"] = df["sma_200"].iloc[-1] if len(df) >= 200 else df["sma_20"].iloc[-1]
            results["ema_9"] = df["ema_9"].iloc[-1]
            results["ema_20"] = df["ema_20"].iloc[-1]
            
            # 2. Average True Range (ATR-14)
            high_low = df["high"] - df["low"]
            high_cp = np.abs(df["high"] - df["close"].shift())
            low_cp = np.abs(df["low"] - df["close"].shift())
            tr = pd.concat([high_low, high_cp, low_cp], axis=1).max(axis=1)
            df["atr_14"] = tr.rolling(14).mean()
            results["atr_14"] = df["atr_14"].iloc[-1]

            # 3. Relative Strength Index (RSI-14)
            delta = df["close"].diff()
            gain = (delta.where(delta > 0, 0)).rolling(window=14).mean()
            loss = (-delta.where(delta < 0, 0)).rolling(window=14).mean()
            rs = gain / (loss + 1e-9)
            df["rsi_14"] = 100 - (100 / (1 + rs))
            results["rsi_14"] = df["rsi_14"].iloc[-1]

            # 4. MACD (12, 26, 9)
            exp1 = df["close"].ewm(span=12, adjust=False).mean()
            exp2 = df["close"].ewm(span=26, adjust=False).mean()
            df["macd"] = exp1 - exp2
            df["macd_signal"] = df["macd"].ewm(span=9, adjust=False).mean()
            results["macd"] = df["macd"].iloc[-1]
            results["macd_signal"] = df["macd_signal"].iloc[-1]

            # 5. Bollinger Bands (20, 2)
            df["bb_middle"] = df["sma_20"]
            df["bb_std"] = df["close"].rolling(20).std()
            df["bb_upper"] = df["bb_middle"] + (df["bb_std"] * 2)
            df["bb_lower"] = df["bb_middle"] - (df["bb_std"] * 2)
            results["bb_upper"] = df["bb_upper"].iloc[-1]
            results["bb_lower"] = df["bb_lower"].iloc[-1]

            # 6. Pivot Points (Floor) using previous day's metrics
            prev_high = df["high"].iloc[-1]
            prev_low = df["low"].iloc[-1]
            prev_close = df["close"].iloc[-1]
            
            pp = (prev_high + prev_low + prev_close) / 3.0
            r1 = (2 * pp) - prev_low
            s1 = (2 * pp) - prev_high
            r2 = pp + (prev_high - prev_low)
            s2 = pp - (prev_high - prev_low)
            
            results["pivot_point"] = pp
            results["resistance_1"] = r1
            results["support_1"] = s1
            results["resistance_2"] = r2
            results["support_2"] = s2

            # 7. Support & Resistance (Local channels)
            results["support"] = df["low"].rolling(14).min().iloc[-1]
            results["resistance"] = df["high"].rolling(14).max().iloc[-1]

            # 8. VWAP (Approximate Daily/Intraday)
            # VWAP = Sum(Typical Price * Volume) / Sum(Volume)
            df["typical_price"] = (df["high"] + df["low"] + df["close"]) / 3.0
            df["tp_vol"] = df["typical_price"] * df["volume"]
            # Intraday vwap resets, on daily bars we can take standard 14 period rolling
            results["vwap"] = df["tp_vol"].rolling(14).sum().iloc[-1] / (df["volume"].rolling(14).sum().iloc[-1] + 1e-9)

            # 9. Relative Volume (RVOL)
            # RVOL = Current Volume / 30-day Average Volume
            avg_vol_30 = df["volume"].rolling(30).mean().iloc[-1] if len(df) >= 30 else df["volume"].mean()
            results["avg_volume_30"] = avg_vol_30
            results["rvol"] = current_volume / (avg_vol_30 + 1e-9)
            
        except Exception as e:
            # Fallback values
            results["rvol"] = 1.0
            results["atr_14"] = current_price * 0.05  # 5% fallback
            results["rsi_14"] = 50.0
            results["vwap"] = current_price
            results["support"] = current_price * 0.95
            results["resistance"] = current_price * 1.05
            
        return results
