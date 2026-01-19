"""
External Data Sources

Uses Kraken's public API to fetch historical OHLCV data
for major cryptocurrencies to supplement Nado's limited historical data.

Kraken works from cloud servers (no geo-restrictions).
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

# Map Nado ticker to Kraken pairs
# Kraken uses XXBT for Bitcoin, XETH for Ethereum, etc.
KRAKEN_PAIR_MAP = {
    "BTC-PERP_USDT0": "XBTUSD",
    "ETH-PERP_USDT0": "ETHUSD",
    "SOL-PERP_USDT0": "SOLUSD",
    "XRP-PERP_USDT0": "XRPUSD",
    "AAVE-PERP_USDT0": "AAVEUSD",
    "XMR-PERP_USDT0": "XMRUSD",
    "ZEC-PERP_USDT0": "ZECUSD",
    "LIT-PERP_USDT0": "LITUSD",
    # BNB, SUI, TAO, HYPE, PENGU not on Kraken - will use defaults
}

KRAKEN_API_URL = "https://api.kraken.com/0/public"


async def fetch_kraken_ohlc(
    pair: str,
    interval: int = 60,  # 60 = 1 hour in minutes
    since: Optional[int] = None
) -> List[Dict[str, Any]]:
    """
    Fetch OHLC from Kraken
    
    Kraken OHLC format:
    [time, open, high, low, close, vwap, volume, count]
    
    interval: 1, 5, 15, 30, 60, 240, 1440, 10080, 21600
    """
    if since is None:
        # Get last 7 days
        since = int((datetime.utcnow() - timedelta(days=7)).timestamp())
    
    async with httpx.AsyncClient(timeout=30.0) as client:
        try:
            response = await client.get(
                f"{KRAKEN_API_URL}/OHLC",
                params={
                    "pair": pair,
                    "interval": interval,
                    "since": since
                }
            )
            response.raise_for_status()
            data = response.json()
            
            if data.get("error") and len(data["error"]) > 0:
                logger.warning(f"Kraken API error for {pair}: {data['error']}")
                return []
            
            result = data.get("result", {})
            
            # Find the data (key is the pair name which varies)
            candle_data = []
            for key, value in result.items():
                if key != "last" and isinstance(value, list):
                    candle_data = value
                    break
            
            ohlcv_data = []
            for candle in candle_data:
                # [time, open, high, low, close, vwap, volume, count]
                ohlcv_data.append({
                    "timestamp": int(candle[0]),
                    "open": float(candle[1]),
                    "high": float(candle[2]),
                    "low": float(candle[3]),
                    "close": float(candle[4]),
                    "volume": float(candle[6])
                })
            
            logger.info(f"Fetched {len(ohlcv_data)} candles from Kraken for {pair}")
            return ohlcv_data
            
        except httpx.HTTPStatusError as e:
            logger.warning(f"Kraken API HTTP error for {pair}: {e}")
            return []
        except Exception as e:
            logger.warning(f"Error fetching Kraken data for {pair}: {e}")
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
    days: int = 7
) -> Dict[str, int]:
    """
    Seed historical data from Kraken for major coins
    
    Fetches hourly candles and aggregates to 4h, 12h, daily.
    This provides enough data for indicator calculations.
    """
    results = {}
    
    if ticker_ids is None:
        ticker_ids = list(KRAKEN_PAIR_MAP.keys())
    
    logger.info(f"Seeding historical data for {len(ticker_ids)} tickers from Kraken...")
    
    since = int((datetime.utcnow() - timedelta(days=days)).timestamp())
    
    for ticker_id in ticker_ids:
        kraken_pair = KRAKEN_PAIR_MAP.get(ticker_id)
        
        if not kraken_pair:
            logger.debug(f"No Kraken mapping for {ticker_id}")
            continue
        
        try:
            # Fetch hourly candles (interval=60 minutes)
            ohlcv_data = await fetch_kraken_ohlc(kraken_pair, interval=60, since=since)
            
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
            
            # Rate limit: be nice to public API
            await asyncio.sleep(0.5)
            
        except Exception as e:
            logger.error(f"Error seeding data for {ticker_id}: {e}")
            results[ticker_id] = 0
    
    total_1h = sum(v for k, v in results.items() if not any(k.endswith(x) for x in ["_4h", "_12h", "_1d"]))
    logger.info(f"Historical data seeding complete. Total 1h candles: {total_1h}")
    
    return results
