"""
Data Collector Service

Fetches trades from Nado API and aggregates into OHLCV candles.
Stores in database for historical analysis.

Timeframes supported:
- 1h (hourly)
- 4h (4-hour)
- 12h (12-hour)
- 1d (daily)

No mock data - only real trades from the API.
"""
import asyncio
from datetime import datetime, timedelta
from typing import List, Dict, Optional, Any
from collections import defaultdict
import logging

from sqlalchemy import select, and_, desc
from sqlalchemy.dialects.sqlite import insert as sqlite_insert

from app.database import Candle, Trade, MarketSnapshot, get_session, get_async_session, init_db
from app.nado_client import get_nado_client
from app.models import OHLCV

logger = logging.getLogger(__name__)

# Timeframe configurations (in hours)
TIMEFRAMES = {
    "1h": 1,
    "4h": 4,
    "12h": 12,
    "1d": 24
}


class DataCollector:
    """
    Collects and stores historical price data from Nado
    
    Process:
    1. Fetch trades from Nado API
    2. Store raw trades in database
    3. Aggregate trades into OHLCV candles for each timeframe
    4. Store candles in database
    5. Store periodic market snapshots (funding, OI, etc.)
    """
    
    def __init__(self):
        self.client = None
        self._initialized = False
    
    async def initialize(self):
        """Initialize the data collector"""
        if self._initialized:
            return
        
        self.client = await get_nado_client()
        init_db()
        self._initialized = True
        logger.info("Data collector initialized")
    
    def _round_timestamp_to_timeframe(self, dt: datetime, timeframe: str) -> datetime:
        """Round a datetime to the start of its timeframe period"""
        hours = TIMEFRAMES.get(timeframe, 1)
        
        if timeframe == "1d":
            # Round to start of day (UTC)
            return dt.replace(hour=0, minute=0, second=0, microsecond=0)
        else:
            # Round to the nearest timeframe period
            hour = (dt.hour // hours) * hours
            return dt.replace(hour=hour, minute=0, second=0, microsecond=0)
    
    async def fetch_and_store_trades(self, ticker_id: str, limit: int = 1000, pages: int = 5) -> int:
        """
        Fetch trades from Nado API and store in database
        
        Uses pagination to fetch more historical trades.
        Fetches up to `pages` batches of `limit` trades each.
        
        Returns number of new trades stored
        """
        await self.initialize()
        
        session = get_session()
        total_new_trades = 0
        min_trade_id = None
        
        try:
            for page in range(pages):
                try:
                    # Fetch trades from API (with pagination via to_id)
                    trades_data = await self.client.get_trades(
                        ticker_id, 
                        limit=limit,
                        to_id=min_trade_id  # Get trades older than this ID
                    )
                    
                    if not trades_data:
                        logger.info(f"No more trades for {ticker_id} (page {page+1})")
                        break
                    
                    new_trades = 0
                    page_min_id = None
                    
                    for trade in trades_data:
                        trade_id = trade.get("trade_id")
                        if not trade_id:
                            continue
                        
                        # Track minimum trade_id for next page
                        if page_min_id is None or trade_id < page_min_id:
                            page_min_id = trade_id
                        
                        # Parse timestamp
                        ts = trade.get("timestamp", 0)
                        if ts > 1e10:  # milliseconds
                            ts = ts / 1000
                        
                        try:
                            trade_dt = datetime.fromtimestamp(ts)
                        except:
                            continue
                        
                        # Check if trade already exists
                        existing = session.query(Trade).filter(
                            and_(Trade.trade_id == trade_id, Trade.ticker_id == ticker_id)
                        ).first()
                        
                        if existing:
                            continue
                        
                        # Create new trade record
                        new_trade = Trade(
                            trade_id=trade_id,
                            ticker_id=ticker_id,
                            product_id=trade.get("product_id"),
                            price=float(trade.get("price", 0)),
                            base_filled=float(trade.get("base_filled", 0)),
                            quote_filled=float(trade.get("quote_filled", 0)),
                            trade_type=trade.get("trade_type"),
                            timestamp=trade_dt
                        )
                        
                        session.add(new_trade)
                        new_trades += 1
                    
                    session.commit()
                    total_new_trades += new_trades
                    
                    # Set min_trade_id for next page (get older trades)
                    if page_min_id:
                        min_trade_id = page_min_id - 1
                    else:
                        break
                    
                    # If we got fewer trades than limit, we've reached the end
                    if len(trades_data) < limit:
                        break
                    
                    # Small delay between pages
                    await asyncio.sleep(0.1)
                    
                except Exception as e:
                    logger.error(f"Error fetching page {page+1} for {ticker_id}: {e}")
                    break
            
            logger.info(f"Stored {total_new_trades} new trades for {ticker_id} ({pages} pages)")
            
        except Exception as e:
            session.rollback()
            logger.error(f"Error storing trades for {ticker_id}: {e}")
        finally:
            session.close()
        
        return total_new_trades
    
    async def aggregate_trades_to_candles(self, ticker_id: str, timeframe: str = "1h") -> int:
        """
        Aggregate stored trades into OHLCV candles for a specific timeframe
        
        Returns number of candles created/updated
        """
        await self.initialize()
        
        session = get_session()
        candles_updated = 0
        
        try:
            # Get all trades for this ticker, ordered by timestamp
            trades = session.query(Trade).filter(
                Trade.ticker_id == ticker_id
            ).order_by(Trade.timestamp).all()
            
            if not trades:
                logger.warning(f"No trades in database for {ticker_id}")
                return 0
            
            # Group trades by timeframe period
            candle_data = defaultdict(lambda: {
                "open": None, 
                "high": float('-inf'), 
                "low": float('inf'), 
                "close": None, 
                "volume": 0,
                "trade_count": 0,
                "first_ts": None,
                "last_ts": None
            })
            
            for trade in trades:
                if trade.price <= 0:
                    continue
                
                period_start = self._round_timestamp_to_timeframe(trade.timestamp, timeframe)
                candle = candle_data[period_start]
                
                # Track first and last trade timestamps
                if candle["first_ts"] is None or trade.timestamp < candle["first_ts"]:
                    candle["first_ts"] = trade.timestamp
                    candle["open"] = trade.price
                
                if candle["last_ts"] is None or trade.timestamp > candle["last_ts"]:
                    candle["last_ts"] = trade.timestamp
                    candle["close"] = trade.price
                
                # Update high/low
                if trade.price > candle["high"]:
                    candle["high"] = trade.price
                if trade.price < candle["low"]:
                    candle["low"] = trade.price
                
                # Accumulate volume
                candle["volume"] += abs(trade.quote_filled)
                candle["trade_count"] += 1
            
            # Store candles in database
            for period_start, data in candle_data.items():
                if data["open"] is None or data["high"] == float('-inf'):
                    continue
                
                # Check if candle exists
                existing = session.query(Candle).filter(
                    and_(
                        Candle.ticker_id == ticker_id,
                        Candle.timeframe == timeframe,
                        Candle.timestamp == period_start
                    )
                ).first()
                
                if existing:
                    # Update existing candle
                    existing.open = data["open"]
                    existing.high = data["high"]
                    existing.low = data["low"]
                    existing.close = data["close"]
                    existing.volume = data["volume"]
                    existing.trade_count = data["trade_count"]
                    existing.updated_at = datetime.utcnow()
                else:
                    # Create new candle
                    candle = Candle(
                        ticker_id=ticker_id,
                        timeframe=timeframe,
                        timestamp=period_start,
                        open=data["open"],
                        high=data["high"],
                        low=data["low"],
                        close=data["close"],
                        volume=data["volume"],
                        trade_count=data["trade_count"]
                    )
                    session.add(candle)
                
                candles_updated += 1
            
            session.commit()
            logger.info(f"Created/updated {candles_updated} {timeframe} candles for {ticker_id}")
            
        except Exception as e:
            session.rollback()
            logger.error(f"Error aggregating candles for {ticker_id}: {e}")
            raise
        finally:
            session.close()
        
        return candles_updated
    
    async def store_market_snapshot(self, ticker_id: str, contract_data: Dict[str, Any]) -> bool:
        """Store a market snapshot from contract data"""
        await self.initialize()
        
        session = get_session()
        
        try:
            snapshot = MarketSnapshot(
                ticker_id=ticker_id,
                product_id=contract_data.get("product_id"),
                last_price=contract_data.get("last_price"),
                mark_price=contract_data.get("mark_price"),
                index_price=contract_data.get("index_price"),
                funding_rate=contract_data.get("funding_rate"),
                open_interest=contract_data.get("open_interest"),
                volume_24h=contract_data.get("quote_volume"),
                price_change_24h=contract_data.get("price_change_percent_24h"),
                timestamp=datetime.utcnow()
            )
            
            session.add(snapshot)
            session.commit()
            return True
            
        except Exception as e:
            session.rollback()
            logger.error(f"Error storing snapshot for {ticker_id}: {e}")
            return False
        finally:
            session.close()
    
    async def collect_all_data(self, ticker_ids: Optional[List[str]] = None) -> Dict[str, int]:
        """
        Collect data for all markets (or specified list)
        
        1. Fetch and store trades
        2. Aggregate into all timeframes
        3. Store market snapshots
        
        Returns dict of ticker_id -> candles created
        """
        await self.initialize()
        
        results = {}
        
        # Get list of tickers if not provided
        if ticker_ids is None:
            contracts = await self.client.get_contracts()
            ticker_ids = list(contracts.keys())
        
        logger.info(f"Collecting data for {len(ticker_ids)} markets...")
        
        for ticker_id in ticker_ids:
            try:
                # Fetch and store trades (10 pages = up to 10K trades for better historical coverage)
                trades_count = await self.fetch_and_store_trades(ticker_id, limit=1000, pages=10)
                
                # Aggregate to all timeframes
                total_candles = 0
                for timeframe in TIMEFRAMES.keys():
                    candles = await self.aggregate_trades_to_candles(ticker_id, timeframe)
                    total_candles += candles
                
                # Store market snapshot
                contracts = await self.client.get_contracts(use_cache=True)
                if ticker_id in contracts:
                    await self.store_market_snapshot(ticker_id, contracts[ticker_id])
                
                results[ticker_id] = total_candles
                
                # Small delay to avoid rate limiting
                await asyncio.sleep(0.2)
                
            except Exception as e:
                logger.error(f"Error collecting data for {ticker_id}: {e}")
                results[ticker_id] = 0
        
        logger.info(f"Data collection complete. Processed {len(results)} markets.")
        return results
    
    def get_candles(
        self, 
        ticker_id: str, 
        timeframe: str = "1h", 
        limit: int = 100
    ) -> List[OHLCV]:
        """
        Get historical candles from database
        
        Returns list of OHLCV objects, most recent first
        """
        session = get_session()
        
        try:
            candles = session.query(Candle).filter(
                and_(
                    Candle.ticker_id == ticker_id,
                    Candle.timeframe == timeframe
                )
            ).order_by(desc(Candle.timestamp)).limit(limit).all()
            
            # Convert to OHLCV objects and reverse to oldest first
            result = [
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
            
            return result
            
        except Exception as e:
            logger.error(f"Error getting candles for {ticker_id}: {e}")
            return []
        finally:
            session.close()
    
    def get_candle_count(self, ticker_id: str, timeframe: str = "1h") -> int:
        """Get count of candles for a ticker/timeframe"""
        session = get_session()
        
        try:
            count = session.query(Candle).filter(
                and_(
                    Candle.ticker_id == ticker_id,
                    Candle.timeframe == timeframe
                )
            ).count()
            return count
        finally:
            session.close()
    
    def get_latest_candle(self, ticker_id: str, timeframe: str = "1h") -> Optional[Candle]:
        """Get the most recent candle for a ticker/timeframe"""
        session = get_session()
        
        try:
            candle = session.query(Candle).filter(
                and_(
                    Candle.ticker_id == ticker_id,
                    Candle.timeframe == timeframe
                )
            ).order_by(desc(Candle.timestamp)).first()
            return candle
        finally:
            session.close()
    
    def get_database_stats(self) -> Dict[str, Any]:
        """Get statistics about the database"""
        session = get_session()
        
        try:
            trade_count = session.query(Trade).count()
            candle_count = session.query(Candle).count()
            snapshot_count = session.query(MarketSnapshot).count()
            
            # Get unique tickers
            tickers = session.query(Candle.ticker_id).distinct().all()
            ticker_list = [t[0] for t in tickers]
            
            # Get candle counts by timeframe
            timeframe_counts = {}
            for tf in TIMEFRAMES.keys():
                count = session.query(Candle).filter(Candle.timeframe == tf).count()
                timeframe_counts[tf] = count
            
            return {
                "total_trades": trade_count,
                "total_candles": candle_count,
                "total_snapshots": snapshot_count,
                "tickers": ticker_list,
                "ticker_count": len(ticker_list),
                "candles_by_timeframe": timeframe_counts
            }
            
        finally:
            session.close()


# Singleton instance
_collector: Optional[DataCollector] = None


def get_data_collector() -> DataCollector:
    """Get or create the data collector instance"""
    global _collector
    if _collector is None:
        _collector = DataCollector()
    return _collector

