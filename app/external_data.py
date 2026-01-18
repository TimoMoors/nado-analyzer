"""
External Data Sources

Uses CoinGecko's free API to fetch historical OHLCV data
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

# Map Nado ticker to CoinGecko IDs
COINGECKO_ID_MAP = {
    "BTC-PERP_USDT0": "bitcoin",
    "ETH-PERP_USDT0": "ethereum",
    "SOL-PERP_USDT0": "solana",
    "BNB-PERP_USDT0": "binancecoin",
    "XRP-PERP_USDT0": "ripple",
    "SUI-PERP_USDT0": "sui",
    "AAVE-PERP_USDT0": "aave",
    "TAO-PERP_USDT0": "bittensor",
    "PENGU-PERP_USDT0": "pudgy-penguins",
    "HYPE-PERP_USDT0": "hyperliquid",
    "XMR-PERP_USDT0": "monero",
    "ZEC-PERP_USDT0": "zcash",
}

# CoinGecko free API rate limit: 10-30 calls/minute
# We'll be conservative with delays
COINGECKO_API_URL = "https://api.coingecko.com/api/v3"


async def fetch_coingecko_ohlcv(
    coingecko_id: str,
    days: int = 7,
    vs_currency: str = "usd"
) -> List[Dict[str, Any]]:
    """
    Fetch OHLCV data from CoinGecko
    
    CoinGecko provides market_chart data with:
    - prices: [[timestamp, price], ...]
    - market_caps: [[timestamp, cap], ...]
    - total_volumes: [[timestamp, volume], ...]
    
    For hourly data, use days <= 90
    """
    async with httpx.AsyncClient(timeout=30.0) as client:
        try:
            # For hourly data, use OHLC endpoint
            response = await client.get(
                f"{COINGECKO_API_URL}/coins/{coingecko_id}/ohlc",
                params={
                    "vs_currency": vs_currency,
                    "days": days
                }
            )
            response.raise_for_status()
            data = response.json()
            
            # OHLC returns: [[timestamp, open, high, low, close], ...]
            ohlcv_data = []
            for candle in data:
                if len(candle) >= 5:
                    ohlcv_data.append({
                        "timestamp": candle[0] / 1000,  # Convert ms to seconds
                        "open": candle[1],
                        "high": candle[2],
                        "low": candle[3],
                        "close": candle[4],
                        "volume": 0  # OHLC endpoint doesn't include volume
                    })
            
            logger.info(f"Fetched {len(ohlcv_data)} OHLCV candles from CoinGecko for {coingecko_id}")
            return ohlcv_data
            
        except httpx.HTTPStatusError as e:
            logger.error(f"CoinGecko API error for {coingecko_id}: {e}")
            return []
        except Exception as e:
            logger.error(f"Error fetching CoinGecko data for {coingecko_id}: {e}")
            return []


async def get_coingecko_market_chart(
    coingecko_id: str,
    days: int = 7,
    vs_currency: str = "usd"
) -> List[Dict[str, Any]]:
    """
    Get market chart data which includes volume
    
    For days <= 1: returns 5-minute data
    For days 2-90: returns hourly data
    For days > 90: returns daily data
    """
    async with httpx.AsyncClient(timeout=30.0) as client:
        try:
            response = await client.get(
                f"{COINGECKO_API_URL}/coins/{coingecko_id}/market_chart",
                params={
                    "vs_currency": vs_currency,
                    "days": days,
                    "interval": "hourly" if days <= 90 else "daily"
                }
            )
            response.raise_for_status()
            data = response.json()
            
            prices = data.get("prices", [])
            volumes = data.get("total_volumes", [])
            
            # Match prices with volumes by timestamp
            volume_map = {int(v[0]): v[1] for v in volumes}
            
            # Convert to OHLCV format (prices are just close prices)
            ohlcv_data = []
            for i, price_data in enumerate(prices):
                ts = int(price_data[0])
                price = price_data[1]
                volume = volume_map.get(ts, 0)
                
                ohlcv_data.append({
                    "timestamp": ts / 1000,
                    "open": price,  # Using close as open (approximation)
                    "high": price * 1.001,  # Small range approximation
                    "low": price * 0.999,
                    "close": price,
                    "volume": volume
                })
            
            logger.info(f"Fetched {len(ohlcv_data)} market chart points from CoinGecko for {coingecko_id}")
            return ohlcv_data
            
        except Exception as e:
            logger.error(f"Error fetching market chart for {coingecko_id}: {e}")
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
                trade_count=0  # External data
            )
            session.add(candle)
            stored += 1
        
        session.commit()
        logger.info(f"Stored {stored} external candles for {ticker_id}")
        
    except Exception as e:
        session.rollback()
        logger.error(f"Error storing external candles for {ticker_id}: {e}")
    finally:
        session.close()
    
    return stored


async def seed_historical_data(ticker_ids: Optional[List[str]] = None, days: int = 7) -> Dict[str, int]:
    """
    Seed historical data from CoinGecko for major coins
    
    This fills in historical candles that Nado doesn't have,
    allowing indicators to be calculated immediately.
    """
    results = {}
    
    if ticker_ids is None:
        ticker_ids = list(COINGECKO_ID_MAP.keys())
    
    for ticker_id in ticker_ids:
        coingecko_id = COINGECKO_ID_MAP.get(ticker_id)
        
        if not coingecko_id:
            logger.debug(f"No CoinGecko mapping for {ticker_id}")
            continue
        
        try:
            # Fetch OHLC data (better quality than market chart for trading)
            ohlcv_data = await fetch_coingecko_ohlcv(coingecko_id, days=days)
            
            if ohlcv_data:
                stored = store_external_candles(ticker_id, ohlcv_data, "1h")
                results[ticker_id] = stored
            else:
                # Fallback to market chart
                ohlcv_data = await get_coingecko_market_chart(coingecko_id, days=days)
                stored = store_external_candles(ticker_id, ohlcv_data, "1h")
                results[ticker_id] = stored
            
            # Rate limit: wait between requests
            await asyncio.sleep(1.5)
            
        except Exception as e:
            logger.error(f"Error seeding data for {ticker_id}: {e}")
            results[ticker_id] = 0
    
    total = sum(results.values())
    logger.info(f"Historical data seeding complete. Total candles stored: {total}")
    
    return results


def get_external_candles(
    ticker_id: str, 
    timeframe: str = "1h", 
    limit: int = 100
) -> List[OHLCV]:
    """
    Get candles from database (includes both Nado and external data)
    """
    from sqlalchemy import desc, and_
    
    session = get_session()
    
    try:
        candles = session.query(Candle).filter(
            and_(
                Candle.ticker_id == ticker_id,
                Candle.timeframe == timeframe
            )
        ).order_by(desc(Candle.timestamp)).limit(limit).all()
        
        return [
            OHLCV(
                timestamp=c.timestamp,
                open=c.open,
                high=c.high,
                low=c.low,
                close=c.close,
                volume=c.volume
            )
            for c in reversed(candles)
        ]
        
    finally:
        session.close()

