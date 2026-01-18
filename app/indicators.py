"""
Technical Indicators Module

Includes:
- RSI (Relative Strength Index)
- MACD (Moving Average Convergence Divergence)
- Supertrend
- Moving Averages
- Bollinger Bands

No mock data - returns None when insufficient data.
"""
import pandas as pd
import numpy as np
from typing import List, Optional, Dict, Any
from datetime import datetime
import logging

from app.models import OHLCV, TechnicalIndicators

logger = logging.getLogger(__name__)


def calculate_rsi(closes: pd.Series, period: int = 14) -> Optional[float]:
    """Calculate RSI (Relative Strength Index)"""
    if len(closes) < period + 1:
        return None
    
    delta = closes.diff()
    gain = (delta.where(delta > 0, 0)).rolling(window=period).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(window=period).mean()
    
    rs = gain / loss
    rsi = 100 - (100 / (1 + rs))
    
    result = rsi.iloc[-1]
    return float(result) if pd.notna(result) else None


def calculate_macd(closes: pd.Series, fast: int = 12, slow: int = 26, signal: int = 9) -> Dict[str, Optional[float]]:
    """Calculate MACD (Moving Average Convergence Divergence)"""
    if len(closes) < slow + signal:
        return {"macd": None, "signal": None, "histogram": None}
    
    ema_fast = closes.ewm(span=fast, adjust=False).mean()
    ema_slow = closes.ewm(span=slow, adjust=False).mean()
    macd_line = ema_fast - ema_slow
    signal_line = macd_line.ewm(span=signal, adjust=False).mean()
    histogram = macd_line - signal_line
    
    return {
        "macd": float(macd_line.iloc[-1]) if pd.notna(macd_line.iloc[-1]) else None,
        "signal": float(signal_line.iloc[-1]) if pd.notna(signal_line.iloc[-1]) else None,
        "histogram": float(histogram.iloc[-1]) if pd.notna(histogram.iloc[-1]) else None
    }


def calculate_supertrend(df: pd.DataFrame, period: int = 10, multiplier: float = 3.0) -> Dict[str, Any]:
    """
    Calculate Supertrend indicator
    
    Supertrend = ATR-based trend following indicator
    - When price > Supertrend line = Bullish (green)
    - When price < Supertrend line = Bearish (red)
    
    Returns:
        - supertrend: Current supertrend value
        - direction: 1 (bullish) or -1 (bearish)
        - trend: "bullish" or "bearish"
    """
    if len(df) < period + 1:
        return {"supertrend": None, "direction": None, "trend": "tbd"}
    
    # Calculate ATR
    high_low = df['high'] - df['low']
    high_close = abs(df['high'] - df['close'].shift())
    low_close = abs(df['low'] - df['close'].shift())
    
    tr = pd.concat([high_low, high_close, low_close], axis=1).max(axis=1)
    atr = tr.rolling(window=period).mean()
    
    # Calculate basic upper and lower bands
    hl2 = (df['high'] + df['low']) / 2
    upper_band = hl2 + (multiplier * atr)
    lower_band = hl2 - (multiplier * atr)
    
    # Initialize supertrend
    supertrend = pd.Series(index=df.index, dtype=float)
    direction = pd.Series(index=df.index, dtype=int)
    
    # First value
    supertrend.iloc[period] = upper_band.iloc[period]
    direction.iloc[period] = -1
    
    # Calculate supertrend
    for i in range(period + 1, len(df)):
        if df['close'].iloc[i] > supertrend.iloc[i-1]:
            supertrend.iloc[i] = lower_band.iloc[i]
            direction.iloc[i] = 1
        elif df['close'].iloc[i] < supertrend.iloc[i-1]:
            supertrend.iloc[i] = upper_band.iloc[i]
            direction.iloc[i] = -1
        else:
            supertrend.iloc[i] = supertrend.iloc[i-1]
            direction.iloc[i] = direction.iloc[i-1]
            
            if direction.iloc[i] == 1 and lower_band.iloc[i] > supertrend.iloc[i]:
                supertrend.iloc[i] = lower_band.iloc[i]
            elif direction.iloc[i] == -1 and upper_band.iloc[i] < supertrend.iloc[i]:
                supertrend.iloc[i] = upper_band.iloc[i]
    
    current_supertrend = supertrend.iloc[-1]
    current_direction = direction.iloc[-1]
    
    return {
        "supertrend": float(current_supertrend) if pd.notna(current_supertrend) else None,
        "direction": int(current_direction) if pd.notna(current_direction) else None,
        "trend": "bullish" if current_direction == 1 else "bearish" if current_direction == -1 else "tbd"
    }


def calculate_ema(closes: pd.Series, period: int) -> Optional[float]:
    """Calculate Exponential Moving Average"""
    if len(closes) < period:
        return None
    
    ema = closes.ewm(span=period, adjust=False).mean()
    return float(ema.iloc[-1]) if pd.notna(ema.iloc[-1]) else None


def calculate_sma(closes: pd.Series, period: int) -> Optional[float]:
    """Calculate Simple Moving Average"""
    if len(closes) < period:
        return None
    
    sma = closes.rolling(window=period).mean()
    return float(sma.iloc[-1]) if pd.notna(sma.iloc[-1]) else None


def calculate_bollinger_bands(closes: pd.Series, period: int = 20, std_dev: float = 2.0) -> Dict[str, Optional[float]]:
    """Calculate Bollinger Bands"""
    if len(closes) < period:
        return {"upper": None, "middle": None, "lower": None}
    
    middle = closes.rolling(window=period).mean()
    std = closes.rolling(window=period).std()
    upper = middle + (std * std_dev)
    lower = middle - (std * std_dev)
    
    return {
        "upper": float(upper.iloc[-1]) if pd.notna(upper.iloc[-1]) else None,
        "middle": float(middle.iloc[-1]) if pd.notna(middle.iloc[-1]) else None,
        "lower": float(lower.iloc[-1]) if pd.notna(lower.iloc[-1]) else None
    }


def calculate_atr(df: pd.DataFrame, period: int = 14) -> Optional[float]:
    """Calculate Average True Range"""
    if len(df) < period + 1:
        return None
    
    high_low = df['high'] - df['low']
    high_close = abs(df['high'] - df['close'].shift())
    low_close = abs(df['low'] - df['close'].shift())
    
    tr = pd.concat([high_low, high_close, low_close], axis=1).max(axis=1)
    atr = tr.rolling(window=period).mean()
    
    return float(atr.iloc[-1]) if pd.notna(atr.iloc[-1]) else None


def calculate_all_indicators(klines: List[OHLCV]) -> Dict[str, Any]:
    """
    Calculate all technical indicators from OHLCV data
    
    Returns dict with all indicator values (None if insufficient data)
    """
    if not klines or len(klines) < 10:
        return {
            "rsi_14": None,
            "macd": None,
            "macd_signal": None,
            "macd_histogram": None,
            "supertrend": None,
            "supertrend_direction": None,
            "supertrend_trend": "tbd",
            "ema_9": None,
            "ema_21": None,
            "sma_20": None,
            "sma_50": None,
            "bb_upper": None,
            "bb_middle": None,
            "bb_lower": None,
            "atr_14": None,
            "candle_count": len(klines) if klines else 0
        }
    
    # Convert to DataFrame
    df = pd.DataFrame([{
        'timestamp': k.timestamp,
        'open': k.open,
        'high': k.high,
        'low': k.low,
        'close': k.close,
        'volume': k.volume
    } for k in klines])
    
    df = df.sort_values('timestamp').reset_index(drop=True)
    closes = df['close']
    
    # Calculate all indicators
    rsi = calculate_rsi(closes, 14)
    macd_data = calculate_macd(closes, 12, 26, 9)
    supertrend_data = calculate_supertrend(df, 10, 3.0)
    bb_data = calculate_bollinger_bands(closes, 20, 2.0)
    
    return {
        "rsi_14": rsi,
        "macd": macd_data["macd"],
        "macd_signal": macd_data["signal"],
        "macd_histogram": macd_data["histogram"],
        "supertrend": supertrend_data["supertrend"],
        "supertrend_direction": supertrend_data["direction"],
        "supertrend_trend": supertrend_data["trend"],
        "ema_9": calculate_ema(closes, 9),
        "ema_21": calculate_ema(closes, 21),
        "sma_20": calculate_sma(closes, 20),
        "sma_50": calculate_sma(closes, 50),
        "bb_upper": bb_data["upper"],
        "bb_middle": bb_data["middle"],
        "bb_lower": bb_data["lower"],
        "atr_14": calculate_atr(df, 14),
        "candle_count": len(klines)
    }


def determine_signal_from_indicators(indicators: Dict[str, Any], current_price: float) -> Dict[str, Any]:
    """
    Determine trading signal from indicators
    
    Signal logic:
    - Supertrend direction is primary
    - RSI confirms overbought/oversold
    - MACD confirms momentum
    
    Returns signal: "bullish", "bearish", or "neutral"
    """
    signals = []
    score = 0
    reasons = []
    
    # Supertrend (weight: 40%)
    st_trend = indicators.get("supertrend_trend", "tbd")
    if st_trend == "bullish":
        score += 40
        signals.append("bullish")
        reasons.append("Supertrend bullish")
    elif st_trend == "bearish":
        score -= 40
        signals.append("bearish")
        reasons.append("Supertrend bearish")
    
    # RSI (weight: 30%)
    rsi = indicators.get("rsi_14")
    if rsi is not None:
        if rsi < 30:
            score += 30
            signals.append("bullish")
            reasons.append(f"RSI oversold ({rsi:.1f})")
        elif rsi > 70:
            score -= 30
            signals.append("bearish")
            reasons.append(f"RSI overbought ({rsi:.1f})")
        elif rsi < 45:
            score += 10
        elif rsi > 55:
            score -= 10
    
    # MACD (weight: 30%)
    macd = indicators.get("macd")
    macd_signal = indicators.get("macd_signal")
    if macd is not None and macd_signal is not None:
        if macd > macd_signal:
            score += 30
            signals.append("bullish")
            reasons.append("MACD bullish crossover")
        else:
            score -= 30
            signals.append("bearish")
            reasons.append("MACD bearish crossover")
    
    # EMA trend (bonus)
    ema_9 = indicators.get("ema_9")
    ema_21 = indicators.get("ema_21")
    if ema_9 is not None and ema_21 is not None:
        if ema_9 > ema_21:
            score += 10
            reasons.append("EMA 9 > 21 (uptrend)")
        else:
            score -= 10
            reasons.append("EMA 9 < 21 (downtrend)")
    
    # Determine final signal
    if score >= 50:
        signal = "bullish"
    elif score <= -50:
        signal = "bearish"
    else:
        signal = "neutral"
    
    # Check if we have enough data
    if indicators.get("supertrend_trend") == "tbd" and rsi is None and macd is None:
        signal = "tbd"
        reasons = ["Insufficient data for analysis"]
    
    return {
        "signal": signal,
        "score": score,
        "reasons": reasons
    }

