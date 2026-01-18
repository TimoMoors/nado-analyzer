"""
External Data Sources

Uses Binance's public API to fetch historical OHLCV data
for major cryptocurrencies to supplement Nado's limited historical data.

This provides enough data for indicator calculations when Nado
hasn't collected enough trades yet.
"""
import httpx
import asyncio
from datetime import datetime, timedelta
from typing import List, Dict, Optional, Any
import logging

from app.models import OHLCV
from app.database import Candle, get_session

logger = logging.getLogger(__name__)

# Map Nado ticker to Binance symbols
BINANCE_SYMBOL_MAP = {
    "BTC-PERP_USDT0": "BTCUSDT",
    "ETH-PERP_USDT0": "ETHUSDT",
    "SOL-PERP_USDT0": "SOLUSDT",
    "BNB-PERP_USDT0": "BNBUSDT",
    "XRP-PERP_USDT0": "XRPUSDT",
    "SUI-PERP_USDT0": "SUIUSDT",
    "AAVE-PERP_USDT0": "AAVEUSDT",
    "TAO-PERP_USDT0": "TAOUSDT",
    "PENGU-PERP_USDT0": "PENGUUSDT",
    "HYPE-PERP_USDT0": "HYPEUSDT",
    "XMR-PERP_USDT0": "XMRUSDT",
    "ZEC-PERP_USDT0": "ZECUSDT",
    "LIT-PERP_USDT0": "LITUSDT",
}

BINANCE_API_URL = "https://api.binance.com/api/v3"


async def fetch_binance_klines(
    symbol: str,
    interval: str = "1h",
    limit: int = 200
) -> List[Dict[str, Any]]:
    """
    Fetch OHLCV klines from Binance
    
    Binance kline format:
    [
      open_time, open, high, low, close, volume,
      close_time, quote_volume, trades, taker_buy_base, taker_buy_quote, ignore
    ]
    """
    async with httpx.AsyncClient(timeout=30.0) as client:
        try:
            response = await client.get(
                f"{BINANCE_API_URL}/klines",
                params={
                    "symbol": symbol,
                    "interval": interval,
                    "limit": limit
                }
            )
            response.raise_for_status()
            data = response.json()
            
            ohlcv_data = []
            for candle in data:
                ohlcv_data.append({
                    "timestamp": candle[0] / 1000,  # Convert ms to seconds
                    "open": float(candle[1]),
                    "high": float(candle[2]),
                    "low": float(candle[3]),
                    "close": float(candle[4]),
                    "volume": float(candle[5])
                })
            
            logger.info(f"Fetched {len(ohlcv_data)} klines from Binance for {symbol}")
            return ohlcv_data
            
        except httpx.HTTPStatusError as e:
            logger.warning(f"Binance API error for {symbol}: {e}")
            return []
        except Exception as e:
            logger.warning(f"Error fetching Binance data for {symbol}: {e}")
            return []


def store_external_candles(
    ticker_id: str,
    ohlcv_data: List[Dict[str, Any]],
    timeframe: str = "1h"
) -> int:
    """
    Store external OHLCV data in the database
    
    Only stores if candle doesn't exist yet (doesn't overwrite Nado data)
    """
    if not ohlcv_data:
        return 0
    
    session = get_session()
    stored = 0
    
    try:
        for candle_data in ohlcv_data:
            ts = candle_data["timestamp"]
            
            # Round timestamp to hour boundary
            dt = datetime.fromtimestamp(ts)
            dt = dt.replace(minute=0, second=0, microsecond=0)
            
            # Check if candle exists
            existing = session.query(Candle).filter(
                Candle.ticker_id == ticker_id,
                Candle.timeframe == timeframe,
                Candle.timestamp == dt
            ).first()
            
            if existing:
                continue
            
            # Store new candle
            candle = Candle(
                ticker_id=ticker_id,
                timeframe=timeframe,
                timestamp=dt,
                open=candle_data["open"],
                high=candle_data["high"],
                low=candle_data["low"],
                close=candle_data["close"],
                volume=candle_data["volume"],
                trade_count=0  # External data marker
            )
            session.add(candle)
            stored += 1
        
        session.commit()
        if stored > 0:
            logger.info(f"Stored {stored} external candles for {ticker_id}")
        
    except Exception as e:
        session.rollback()
        logger.error(f"Error storing external candles for {ticker_id}: {e}")
    finally:
        session.close()
    
    return stored


async def seed_historical_data(
    ticker_ids: Optional[List[str]] = None, 
    days: int = 7
) -> Dict[str, int]:
    """
    Seed historical data from Binance for major coins
    
    This fills in historical candles that Nado doesn't have,
    allowing indicators to be calculated immediately.
    
    Fetches 200 hourly candles (~8 days) for each supported coin.
    """
    results = {}
    
    if ticker_ids is None:
        ticker_ids = list(BINANCE_SYMBOL_MAP.keys())
    
    logger.info(f"Seeding historical data for {len(ticker_ids)} tickers...")
    
    for ticker_id in ticker_ids:
        binance_symbol = BINANCE_SYMBOL_MAP.get(ticker_id)
        
        if not binance_symbol:
            logger.debug(f"No Binance mapping for {ticker_id}")
            continue
        
        try:
            # Fetch hourly klines (200 = ~8 days of data)
            ohlcv_data = await fetch_binance_klines(
                binance_symbol, 
                interval="1h", 
                limit=200
            )
            
            if ohlcv_data:
                stored = store_external_candles(ticker_id, ohlcv_data, "1h")
                results[ticker_id] = stored
                
                # Also create 4h candles by aggregating
                stored_4h = aggregate_and_store_higher_timeframes(ticker_id, ohlcv_data)
                results[f"{ticker_id}_4h"] = stored_4h
            else:
                results[ticker_id] = 0
            
            # Small delay to be nice to Binance API
            await asyncio.sleep(0.2)
            
        except Exception as e:
            logger.error(f"Error seeding data for {ticker_id}: {e}")
            results[ticker_id] = 0
    
    total = sum(v for k, v in results.items() if not k.endswith("_4h"))
    logger.info(f"Historical data seeding complete. Total 1h candles stored: {total}")
    
    return results


def aggregate_and_store_higher_timeframes(
    ticker_id: str,
    hourly_data: List[Dict[str, Any]]
) -> int:
    """
    Aggregate hourly data into 4h, 12h, and daily candles
    """
    from collections import defaultdict
    
    if not hourly_data:
        return 0
    
    session = get_session()
    stored = 0
    
    try:
        # Group by 4-hour periods
        candles_4h = defaultdict(lambda: {"open": None, "high": float('-inf'), "low": float('inf'), "close": None, "volume": 0, "first_ts": None})
        candles_12h = defaultdict(lambda: {"open": None, "high": float('-inf'), "low": float('inf'), "close": None, "volume": 0, "first_ts": None})
        candles_1d = defaultdict(lambda: {"open": None, "high": float('-inf'), "low": float('inf'), "close": None, "volume": 0, "first_ts": None})
        
        for candle in hourly_data:
            dt = datetime.fromtimestamp(candle["timestamp"])
            
            # 4h period
            period_4h = dt.replace(hour=(dt.hour // 4) * 4, minute=0, second=0, microsecond=0)
            agg = candles_4h[period_4h]
            if agg["first_ts"] is None or candle["timestamp"] < agg["first_ts"]:
                agg["first_ts"] = candle["timestamp"]
                agg["open"] = candle["open"]
            if candle["timestamp"] > (agg.get("last_ts") or 0):
                agg["last_ts"] = candle["timestamp"]
                agg["close"] = candle["close"]
            agg["high"] = max(agg["high"], candle["high"])
            agg["low"] = min(agg["low"], candle["low"])
            agg["volume"] += candle["volume"]
            
            # 12h period
            period_12h = dt.replace(hour=(dt.hour // 12) * 12, minute=0, second=0, microsecond=0)
            agg = candles_12h[period_12h]
            if agg["first_ts"] is None or candle["timestamp"] < agg["first_ts"]:
                agg["first_ts"] = candle["timestamp"]
                agg["open"] = candle["open"]
            if candle["timestamp"] > (agg.get("last_ts") or 0):
                agg["last_ts"] = candle["timestamp"]
                agg["close"] = candle["close"]
            agg["high"] = max(agg["high"], candle["high"])
            agg["low"] = min(agg["low"], candle["low"])
            agg["volume"] += candle["volume"]
            
            # Daily period
            period_1d = dt.replace(hour=0, minute=0, second=0, microsecond=0)
            agg = candles_1d[period_1d]
            if agg["first_ts"] is None or candle["timestamp"] < agg["first_ts"]:
                agg["first_ts"] = candle["timestamp"]
                agg["open"] = candle["open"]
            if candle["timestamp"] > (agg.get("last_ts") or 0):
                agg["last_ts"] = candle["timestamp"]
                agg["close"] = candle["close"]
            agg["high"] = max(agg["high"], candle["high"])
            agg["low"] = min(agg["low"], candle["low"])
            agg["volume"] += candle["volume"]
        
        # Store 4h candles
        for period, data in candles_4h.items():
            if data["open"] is None:
                continue
            existing = session.query(Candle).filter(
                Candle.ticker_id == ticker_id,
                Candle.timeframe == "4h",
                Candle.timestamp == period
            ).first()
            if not existing:
                candle = Candle(
                    ticker_id=ticker_id, timeframe="4h", timestamp=period,
                    open=data["open"], high=data["high"], low=data["low"],
                    close=data["close"], volume=data["volume"], trade_count=0
                )
                session.add(candle)
                stored += 1
        
        # Store 12h candles
        for period, data in candles_12h.items():
            if data["open"] is None:
                continue
            existing = session.query(Candle).filter(
                Candle.ticker_id == ticker_id,
                Candle.timeframe == "12h",
                Candle.timestamp == period
            ).first()
            if not existing:
                candle = Candle(
                    ticker_id=ticker_id, timeframe="12h", timestamp=period,
                    open=data["open"], high=data["high"], low=data["low"],
                    close=data["close"], volume=data["volume"], trade_count=0
                )
                session.add(candle)
                stored += 1
        
        # Store daily candles
        for period, data in candles_1d.items():
            if data["open"] is None:
                continue
            existing = session.query(Candle).filter(
                Candle.ticker_id == ticker_id,
                Candle.timeframe == "1d",
                Candle.timestamp == period
            ).first()
            if not existing:
                candle = Candle(
                    ticker_id=ticker_id, timeframe="1d", timestamp=period,
                    open=data["open"], high=data["high"], low=data["low"],
                    close=data["close"], volume=data["volume"], trade_count=0
                )
                session.add(candle)
                stored += 1
        
        session.commit()
        if stored > 0:
            logger.info(f"Stored {stored} aggregated candles (4h/12h/1d) for {ticker_id}")
        
    except Exception as e:
        session.rollback()
        logger.error(f"Error aggregating candles for {ticker_id}: {e}")
    finally:
        session.close()
    
    return stored
