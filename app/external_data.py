"""
External Data Sources

Uses CryptoCompare's free API to fetch historical OHLCV data
for major cryptocurrencies to supplement Nado's limited historical data.

CryptoCompare works from cloud servers (unlike Binance which is geo-blocked).
"""
import httpx
import asyncio
from datetime import datetime, timedelta
from typing import List, Dict, Optional, Any
from collections import defaultdict
import logging

from app.models import OHLCV
from app.database import Candle, get_session

logger = logging.getLogger(__name__)

# Map Nado ticker to CryptoCompare symbols
CRYPTOCOMPARE_SYMBOL_MAP = {
    "BTC-PERP_USDT0": "BTC",
    "ETH-PERP_USDT0": "ETH",
    "SOL-PERP_USDT0": "SOL",
    "BNB-PERP_USDT0": "BNB",
    "XRP-PERP_USDT0": "XRP",
    "SUI-PERP_USDT0": "SUI",
    "AAVE-PERP_USDT0": "AAVE",
    "TAO-PERP_USDT0": "TAO",
    "XMR-PERP_USDT0": "XMR",
    "ZEC-PERP_USDT0": "ZEC",
    "LIT-PERP_USDT0": "LIT",
    "HYPE-PERP_USDT0": "HYPE",
    "PENGU-PERP_USDT0": "PENGU",
}

CRYPTOCOMPARE_API_URL = "https://min-api.cryptocompare.com/data/v2"


async def fetch_cryptocompare_hourly(
    symbol: str,
    limit: int = 200,
    to_currency: str = "USD"
) -> List[Dict[str, Any]]:
    """
    Fetch hourly OHLCV from CryptoCompare
    
    Free API: 100,000 calls/month, no auth required for basic data
    Returns up to 2000 hourly candles
    """
    async with httpx.AsyncClient(timeout=30.0) as client:
        try:
            response = await client.get(
                f"{CRYPTOCOMPARE_API_URL}/histohour",
                params={
                    "fsym": symbol,
                    "tsym": to_currency,
                    "limit": min(limit, 2000)
                }
            )
            response.raise_for_status()
            data = response.json()
            
            if data.get("Response") != "Success":
                logger.warning(f"CryptoCompare error for {symbol}: {data.get('Message')}")
                return []
            
            candles = data.get("Data", {}).get("Data", [])
            
            ohlcv_data = []
            for candle in candles:
                if candle.get("open", 0) > 0:  # Skip empty candles
                    ohlcv_data.append({
                        "timestamp": candle["time"],
                        "open": float(candle["open"]),
                        "high": float(candle["high"]),
                        "low": float(candle["low"]),
                        "close": float(candle["close"]),
                        "volume": float(candle.get("volumeto", 0))
                    })
            
            logger.info(f"Fetched {len(ohlcv_data)} hourly candles from CryptoCompare for {symbol}")
            return ohlcv_data
            
        except httpx.HTTPStatusError as e:
            logger.warning(f"CryptoCompare API error for {symbol}: {e}")
            return []
        except Exception as e:
            logger.warning(f"Error fetching CryptoCompare data for {symbol}: {e}")
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
            dt = datetime.utcfromtimestamp(ts)
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
            logger.info(f"Stored {stored} external 1h candles for {ticker_id}")
        
    except Exception as e:
        session.rollback()
        logger.error(f"Error storing external candles for {ticker_id}: {e}")
    finally:
        session.close()
    
    return stored


def aggregate_to_higher_timeframes(
    ticker_id: str,
    hourly_data: List[Dict[str, Any]]
) -> Dict[str, int]:
    """
    Aggregate hourly data into 4h, 12h, and daily candles
    """
    if not hourly_data:
        return {"4h": 0, "12h": 0, "1d": 0}
    
    session = get_session()
    results = {"4h": 0, "12h": 0, "1d": 0}
    
    try:
        # Group by time periods
        candles_4h = defaultdict(lambda: {"open": None, "high": float('-inf'), "low": float('inf'), "close": None, "volume": 0, "first_ts": None, "last_ts": None})
        candles_12h = defaultdict(lambda: {"open": None, "high": float('-inf'), "low": float('inf'), "close": None, "volume": 0, "first_ts": None, "last_ts": None})
        candles_1d = defaultdict(lambda: {"open": None, "high": float('-inf'), "low": float('inf'), "close": None, "volume": 0, "first_ts": None, "last_ts": None})
        
        for candle in hourly_data:
            ts = candle["timestamp"]
            dt = datetime.utcfromtimestamp(ts)
            
            # 4h period
            period_4h = dt.replace(hour=(dt.hour // 4) * 4, minute=0, second=0, microsecond=0)
            _update_aggregated_candle(candles_4h[period_4h], candle)
            
            # 12h period
            period_12h = dt.replace(hour=(dt.hour // 12) * 12, minute=0, second=0, microsecond=0)
            _update_aggregated_candle(candles_12h[period_12h], candle)
            
            # Daily period
            period_1d = dt.replace(hour=0, minute=0, second=0, microsecond=0)
            _update_aggregated_candle(candles_1d[period_1d], candle)
        
        # Store aggregated candles
        results["4h"] = _store_aggregated_candles(session, ticker_id, "4h", candles_4h)
        results["12h"] = _store_aggregated_candles(session, ticker_id, "12h", candles_12h)
        results["1d"] = _store_aggregated_candles(session, ticker_id, "1d", candles_1d)
        
        session.commit()
        
        total = sum(results.values())
        if total > 0:
            logger.info(f"Stored {results} aggregated candles for {ticker_id}")
        
    except Exception as e:
        session.rollback()
        logger.error(f"Error aggregating candles for {ticker_id}: {e}")
    finally:
        session.close()
    
    return results


def _update_aggregated_candle(agg: Dict, candle: Dict):
    """Update aggregated candle with new data point"""
    ts = candle["timestamp"]
    
    if agg["first_ts"] is None or ts < agg["first_ts"]:
        agg["first_ts"] = ts
        agg["open"] = candle["open"]
    
    if agg["last_ts"] is None or ts > agg["last_ts"]:
        agg["last_ts"] = ts
        agg["close"] = candle["close"]
    
    agg["high"] = max(agg["high"], candle["high"])
    agg["low"] = min(agg["low"], candle["low"])
    agg["volume"] += candle["volume"]


def _store_aggregated_candles(session, ticker_id: str, timeframe: str, candles: Dict) -> int:
    """Store aggregated candles in database"""
    stored = 0
    
    for period, data in candles.items():
        if data["open"] is None or data["high"] == float('-inf'):
            continue
        
        existing = session.query(Candle).filter(
            Candle.ticker_id == ticker_id,
            Candle.timeframe == timeframe,
            Candle.timestamp == period
        ).first()
        
        if not existing:
            candle = Candle(
                ticker_id=ticker_id,
                timeframe=timeframe,
                timestamp=period,
                open=data["open"],
                high=data["high"],
                low=data["low"],
                close=data["close"],
                volume=data["volume"],
                trade_count=0
            )
            session.add(candle)
            stored += 1
    
    return stored


async def seed_historical_data(
    ticker_ids: Optional[List[str]] = None,
    limit: int = 200
) -> Dict[str, int]:
    """
    Seed historical data from CryptoCompare for major coins
    
    Fetches hourly candles and aggregates to 4h, 12h, daily.
    This provides enough data for indicator calculations.
    """
    results = {}
    
    if ticker_ids is None:
        ticker_ids = list(CRYPTOCOMPARE_SYMBOL_MAP.keys())
    
    logger.info(f"Seeding historical data for {len(ticker_ids)} tickers from CryptoCompare...")
    
    for ticker_id in ticker_ids:
        cc_symbol = CRYPTOCOMPARE_SYMBOL_MAP.get(ticker_id)
        
        if not cc_symbol:
            logger.debug(f"No CryptoCompare mapping for {ticker_id}")
            continue
        
        try:
            # Fetch hourly candles
            ohlcv_data = await fetch_cryptocompare_hourly(cc_symbol, limit=limit)
            
            if ohlcv_data:
                # Store 1h candles
                stored_1h = store_external_candles(ticker_id, ohlcv_data, "1h")
                results[ticker_id] = stored_1h
                
                # Aggregate to higher timeframes
                higher_tf = aggregate_to_higher_timeframes(ticker_id, ohlcv_data)
                results[f"{ticker_id}_4h"] = higher_tf["4h"]
                results[f"{ticker_id}_12h"] = higher_tf["12h"]
                results[f"{ticker_id}_1d"] = higher_tf["1d"]
            else:
                results[ticker_id] = 0
            
            # Rate limit: 50 calls/second for free tier
            await asyncio.sleep(0.1)
            
        except Exception as e:
            logger.error(f"Error seeding data for {ticker_id}: {e}")
            results[ticker_id] = 0
    
    total_1h = sum(v for k, v in results.items() if not any(k.endswith(x) for x in ["_4h", "_12h", "_1d"]))
    logger.info(f"Historical data seeding complete. Total 1h candles: {total_1h}")
    
    return results
