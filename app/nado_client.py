"""
Nado API Client - Fetches market data from Nado DEX

Based on Nado's API documentation:
https://docs.nado.xyz/developer-resources/api

Endpoints (Ink Mainnet):
- Gateway REST: https://gateway.prod.nado.xyz/v1
- Gateway V2: https://gateway.prod.nado.xyz/v2
- Archive (Indexer) V2: https://archive.prod.nado.xyz/v2
"""
import httpx
import asyncio
from datetime import datetime, timedelta
from typing import Optional, List, Dict, Any
import logging

from app.config import get_settings
from app.models import MarketData, OHLCV, OrderBook

logger = logging.getLogger(__name__)


class NadoClient:
    """
    Client for interacting with Nado DEX API
    
    Nado API structure:
    - Gateway: real-time orderbook, trading execution
    - Archive (Indexer): historical data, contracts, tickers, trades
    """
    
    def __init__(self):
        self.settings = get_settings()
        # Use the correct Nado mainnet endpoints
        self.gateway_url = f"{self.settings.nado_gateway_url}/v2"
        self.archive_url = f"{self.settings.nado_archive_url}/v2"
        self._client: Optional[httpx.AsyncClient] = None
        self._contracts_cache: Optional[Dict[str, Any]] = None
        self._cache_time: Optional[datetime] = None
        
    async def __aenter__(self):
        self._client = httpx.AsyncClient(timeout=30.0)
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        if self._client:
            await self._client.aclose()
    
    @property
    def client(self) -> httpx.AsyncClient:
        if self._client is None:
            self._client = httpx.AsyncClient(timeout=30.0)
        return self._client
    
    async def close(self):
        """Close the HTTP client"""
        if self._client:
            await self._client.aclose()
            self._client = None
    
    # ==================== Archive (Indexer) Endpoints ====================
    
    async def get_contracts(self, use_cache: bool = True) -> Dict[str, Any]:
        """
        Get all contracts (perpetual markets) from Nado
        
        This is the main endpoint that returns all perpetual markets with:
        - product_id, ticker_id
        - last_price, mark_price, index_price
        - funding_rate, open_interest
        - volume, price change
        
        Endpoint: GET /v2/contracts
        """
        # Use cache if available and fresh (less than 30 seconds old)
        if use_cache and self._contracts_cache and self._cache_time:
            if (datetime.utcnow() - self._cache_time).total_seconds() < 30:
                return self._contracts_cache
        
        try:
            response = await self.client.get(f"{self.archive_url}/contracts")
            response.raise_for_status()
            data = response.json()
            
            # Cache the result
            self._contracts_cache = data
            self._cache_time = datetime.utcnow()
            
            logger.info(f"Fetched {len(data)} contracts from Nado API")
            return data
            
        except httpx.HTTPStatusError as e:
            logger.error(f"HTTP error fetching contracts: {e}")
            raise
        except Exception as e:
            logger.error(f"Error fetching contracts: {e}")
            raise
    
    async def get_perpetual_markets(self) -> List[Dict[str, Any]]:
        """
        Get all available perpetual markets
        
        Returns list of perpetual trading contracts with full market data
        """
        contracts = await self.get_contracts()
        
        # Convert dict to list of markets, filtering for perpetuals only
        markets = []
        for ticker_id, contract in contracts.items():
            if contract.get("product_type") == "perpetual":
                contract["ticker_id"] = ticker_id  # Ensure ticker_id is in the dict
                markets.append(contract)
        
        return markets
    
    async def get_ticker(self, ticker_id: str) -> Dict[str, Any]:
        """
        Get ticker data for a specific symbol
        
        The contracts endpoint already contains ticker data, so we use that
        """
        contracts = await self.get_contracts()
        
        if ticker_id in contracts:
            return contracts[ticker_id]
        
        # Try with different format if not found
        # User might pass "SOLUSDT0" but API uses "SOL-PERP_USDT0"
        for key, contract in contracts.items():
            if ticker_id.replace("-PERP_", "").replace("_", "") in key.replace("-PERP_", "").replace("_", ""):
                return contract
        
        raise ValueError(f"Ticker {ticker_id} not found")
    
    async def get_all_tickers(self) -> List[Dict[str, Any]]:
        """Get ticker data for all markets"""
        return await self.get_perpetual_markets()
    
    async def get_orderbook(self, ticker_id: str, depth: int = 20) -> OrderBook:
        """
        Get order book for a symbol
        
        Endpoint: GET /v2/orderbook?ticker_id={ticker_id}&depth={depth}
        """
        try:
            response = await self.client.get(
                f"{self.archive_url}/orderbook",
                params={"ticker_id": ticker_id, "depth": depth}
            )
            response.raise_for_status()
            data = response.json()
            
            return OrderBook(
                symbol=ticker_id,
                bids=[(float(b["price"]), float(b["quantity"])) for b in data.get("bids", [])],
                asks=[(float(a["price"]), float(a["quantity"])) for a in data.get("asks", [])],
                timestamp=datetime.utcnow()
            )
        except Exception as e:
            logger.warning(f"Error fetching orderbook for {ticker_id}: {e}")
            # Return empty orderbook on error
            return OrderBook(
                symbol=ticker_id,
                bids=[],
                asks=[],
                timestamp=datetime.utcnow()
            )
    
    async def get_funding_rate(self, ticker_id: str) -> Dict[str, Any]:
        """
        Get current funding rate for a perpetual
        
        Funding rate is included in the contracts data
        """
        contracts = await self.get_contracts()
        
        if ticker_id in contracts:
            contract = contracts[ticker_id]
            return {
                "ticker_id": ticker_id,
                "funding_rate": contract.get("funding_rate", 0),
                "next_funding_time": contract.get("next_funding_rate_timestamp"),
            }
        
        return {"ticker_id": ticker_id, "funding_rate": 0}
    
    async def get_trades(
        self, 
        ticker_id: str, 
        limit: int = 100,
        to_id: Optional[int] = None,
        from_id: Optional[int] = None
    ) -> List[Dict[str, Any]]:
        """
        Get recent trades for a symbol
        
        Endpoint: GET /v2/trades?ticker_id={ticker_id}&limit={limit}
        
        Pagination:
        - to_id: Get trades older than this trade_id
        - from_id: Get trades newer than this trade_id
        """
        try:
            params = {"ticker_id": ticker_id, "limit": limit}
            
            # Add pagination parameters if provided
            if to_id is not None:
                params["to_id"] = to_id
            if from_id is not None:
                params["from_id"] = from_id
            
            response = await self.client.get(
                f"{self.archive_url}/trades",
                params=params
            )
            response.raise_for_status()
            return response.json()
        except Exception as e:
            logger.error(f"Error fetching trades for {ticker_id}: {e}")
            return []
    
    async def get_klines(
        self, 
        ticker_id: str, 
        interval: str = "1h",
        limit: int = 100,
        start_time: Optional[datetime] = None,
        end_time: Optional[datetime] = None
    ) -> List[OHLCV]:
        """
        Get historical price data by aggregating recent trades into OHLCV candles
        
        Note: Nado's /v2/candlesticks endpoint doesn't exist, so we build 
        OHLCV from trades. This gives us limited history but real data.
        
        If insufficient trades, returns empty list (shows 'tbd' in UI - no mock data)
        """
        try:
            # Fetch recent trades (max 1000 typically)
            trades = await self.get_trades(ticker_id, limit=500)
            
            if not trades or len(trades) < 10:
                logger.info(f"Insufficient trades for {ticker_id} to build OHLCV - returning empty")
                return []
            
            # Group trades into hourly candles
            from collections import defaultdict
            
            candles = defaultdict(lambda: {"open": None, "high": 0, "low": float('inf'), "close": None, "volume": 0, "trades": []})
            
            for trade in trades:
                ts = trade.get("timestamp", 0)
                if ts > 1e10:  # milliseconds
                    ts = ts / 1000
                
                # Round to hour
                dt = datetime.fromtimestamp(ts)
                hour_key = dt.replace(minute=0, second=0, microsecond=0)
                
                price = float(trade.get("price", 0))
                volume = abs(float(trade.get("quote_filled", 0)))
                
                if price <= 0:
                    continue
                
                candle = candles[hour_key]
                candle["trades"].append((ts, price))
                candle["volume"] += volume
                
                if candle["high"] < price:
                    candle["high"] = price
                if candle["low"] > price:
                    candle["low"] = price
            
            # Build OHLCV list
            klines = []
            for hour_key in sorted(candles.keys()):
                candle = candles[hour_key]
                if not candle["trades"]:
                    continue
                
                # Sort trades by timestamp
                sorted_trades = sorted(candle["trades"], key=lambda x: x[0])
                candle["open"] = sorted_trades[0][1]
                candle["close"] = sorted_trades[-1][1]
                
                # Skip candles with invalid data
                if candle["high"] == 0 or candle["low"] == float('inf'):
                    continue
                
                klines.append(OHLCV(
                    timestamp=hour_key,
                    open=candle["open"],
                    high=candle["high"],
                    low=candle["low"],
                    close=candle["close"],
                    volume=candle["volume"]
                ))
            
            # Return most recent candles (limit)
            klines = klines[-limit:] if len(klines) > limit else klines
            
            logger.info(f"Built {len(klines)} OHLCV candles for {ticker_id} from trades")
            return klines
            
        except Exception as e:
            logger.warning(f"Error building klines for {ticker_id}: {e}")
            return []  # No mock data - return empty
    
    
    # ==================== Comprehensive Data Fetch ====================
    
    async def get_market_data(self, ticker_id: str) -> MarketData:
        """
        Get comprehensive market data for a symbol
        
        Uses the contracts endpoint which has all the data we need
        """
        contracts = await self.get_contracts()
        
        if ticker_id not in contracts:
            raise ValueError(f"Ticker {ticker_id} not found in contracts")
        
        contract = contracts[ticker_id]
        
        # Get orderbook for bid/ask spread
        orderbook = await self.get_orderbook(ticker_id, depth=5)
        
        # Extract data from contract
        last_price = float(contract.get("last_price", 0))
        mark_price = float(contract.get("mark_price", last_price))
        index_price = float(contract.get("index_price", last_price))
        
        # Calculate bid/ask from orderbook - no estimation/mock data
        if orderbook.bids and orderbook.asks:
            bid_price = orderbook.bids[0][0]
            ask_price = orderbook.asks[0][0]
        else:
            # tbd - orderbook data not available
            bid_price = 0
            ask_price = 0
        
        spread = ask_price - bid_price
        spread_percent = (spread / last_price * 100) if last_price else 0
        
        # Parse base and quote from ticker_id (e.g., "SOL-PERP_USDT0")
        parts = ticker_id.split("-PERP_")
        base_asset = parts[0] if parts else ticker_id
        quote_asset = parts[1] if len(parts) > 1 else "USDT0"
        
        return MarketData(
            symbol=ticker_id,
            base_asset=base_asset,
            quote_asset=quote_asset,
            mark_price=mark_price,
            index_price=index_price,
            last_price=last_price,
            bid_price=bid_price,
            ask_price=ask_price,
            spread=spread,
            spread_percent=spread_percent,
            volume_24h=float(contract.get("quote_volume", 0)),
            open_interest=float(contract.get("open_interest", 0)),
            funding_rate=float(contract.get("funding_rate", 0)),
            price_change_24h=0,  # tbd - not available from API
            price_change_percent_24h=float(contract.get("price_change_percent_24h", 0)),
            high_24h=0,  # tbd - not available from contracts endpoint
            low_24h=0,   # tbd - not available from contracts endpoint
            timestamp=datetime.utcnow()
        )


# Singleton instance
_client: Optional[NadoClient] = None


async def get_nado_client() -> NadoClient:
    """Get or create the Nado client instance"""
    global _client
    if _client is None:
        _client = NadoClient()
    return _client
