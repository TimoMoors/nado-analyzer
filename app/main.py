"""
Nado Trading Setup Analyzer - FastAPI Backend

A comprehensive trading analysis tool for Nado perpetual markets.
Provides real-time market data, technical analysis, and trading setup recommendations.

API Documentation available at /docs
"""
import asyncio
from contextlib import asynccontextmanager
from datetime import datetime
from typing import List, Optional
import logging

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from apscheduler.schedulers.asyncio import AsyncIOScheduler

from app.config import get_settings
from app.models import TradingSetup, MarketData, MarketSummary, TradingSignal, SetupQuality, OHLCV
from app.nado_client import get_nado_client, NadoClient
from app.analyzer import get_analyzer, TradingAnalyzer
from app.data_collector import get_data_collector, DataCollector
from app.database import init_db
from app.indicators import calculate_all_indicators, determine_signal_from_indicators
from app.external_data import seed_historical_data

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Global state for caching
_cached_setups: List[TradingSetup] = []
_cached_market_summary: Optional[MarketSummary] = None
_last_update: Optional[datetime] = None


async def collect_historical_data():
    """Background task to collect and store historical data"""
    logger.info("Collecting historical data...")
    
    try:
        collector = get_data_collector()
        results = await collector.collect_all_data()
        
        total_candles = sum(results.values())
        logger.info(f"Historical data collection complete. Total candles: {total_candles}")
        
    except Exception as e:
        logger.error(f"Error collecting historical data: {e}")


async def seed_external_data():
    """Seed historical data from Binance for major coins"""
    logger.info("Seeding historical data from Binance...")
    
    try:
        results = await seed_historical_data(days=7)
        total_1h = sum(v for k, v in results.items() if not k.endswith("_4h"))
        total_higher = sum(v for k, v in results.items() if k.endswith("_4h"))
        logger.info(f"External data seeding complete. 1h candles: {total_1h}, Higher TF: {total_higher}")
        
        # Log individual results
        for ticker, count in sorted(results.items()):
            if count > 0 and not ticker.endswith("_4h"):
                logger.info(f"  {ticker}: {count} candles seeded")
        
    except Exception as e:
        logger.error(f"Error seeding external data: {e}", exc_info=True)


async def refresh_data():
    """Background task to refresh all market data and analysis"""
    global _cached_setups, _cached_market_summary, _last_update
    
    logger.info("Refreshing market data...")
    
    try:
        client = await get_nado_client()
        analyzer = get_analyzer()
        collector = get_data_collector()
        
        # Get all markets
        markets = await client.get_perpetual_markets()
        
        setups = []
        total_volume = 0.0
        
        for market in markets:
            # Nado API uses "ticker_id" field (e.g., "SOL-PERP_USDT0")
            symbol = market.get("ticker_id", market.get("symbol", ""))
            if not symbol:
                continue
            
            try:
                # Get market data from API
                market_data = await client.get_market_data(symbol)
                
                # Try to get klines from database first (more history)
                klines = collector.get_candles(symbol, timeframe="1h", limit=100)
                
                # If not enough data in DB, try API
                if len(klines) < 26:
                    api_klines = await client.get_klines(symbol, interval="1h", limit=100)
                    if len(api_klines) > len(klines):
                        klines = api_klines
                
                # Generate trading setup
                setup = await analyzer.analyze_market(market_data, klines)
                setups.append(setup)
                total_volume += market_data.volume_24h
                
            except Exception as e:
                logger.error(f"Error analyzing {symbol}: {e}")
                continue
        
        # Sort by score (best setups first)
        setups.sort(key=lambda x: x.overall_score, reverse=True)
        
        # Create market summary
        _cached_setups = setups
        _cached_market_summary = MarketSummary(
            total_markets=len(setups),
            total_volume_24h=total_volume,
            top_gainers=[
                {"symbol": s.symbol, "change": s.market_data.price_change_percent_24h}
                for s in sorted(setups, key=lambda x: x.market_data.price_change_percent_24h, reverse=True)[:3]
            ],
            top_losers=[
                {"symbol": s.symbol, "change": s.market_data.price_change_percent_24h}
                for s in sorted(setups, key=lambda x: x.market_data.price_change_percent_24h)[:3]
            ],
            highest_funding=[
                {"symbol": s.symbol, "rate": s.funding_analysis.current_rate}
                for s in sorted(setups, key=lambda x: x.funding_analysis.current_rate, reverse=True)[:3]
            ],
            lowest_funding=[
                {"symbol": s.symbol, "rate": s.funding_analysis.current_rate}
                for s in sorted(setups, key=lambda x: x.funding_analysis.current_rate)[:3]
            ],
            best_setups=setups[:5],
            timestamp=datetime.utcnow()
        )
        
        _last_update = datetime.utcnow()
        logger.info(f"Data refresh complete. Analyzed {len(setups)} markets.")
        
    except Exception as e:
        logger.error(f"Error refreshing data: {e}")


# Scheduler for background data refresh
scheduler = AsyncIOScheduler()


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan handler"""
    settings = get_settings()
    
    # Initialize database
    logger.info("Initializing database...")
    init_db()
    
    # Seed historical data from CoinGecko (for major coins)
    # This provides enough data for indicators immediately
    logger.info("Seeding historical data from external sources...")
    await seed_external_data()
    
    # Collect fresh data from Nado
    logger.info("Collecting initial historical data from Nado...")
    await collect_historical_data()
    
    # Initial analysis
    await refresh_data()
    
    # Start scheduler
    # Refresh market analysis every minute
    scheduler.add_job(
        refresh_data, 
        'interval', 
        seconds=settings.data_refresh_interval,
        id='refresh_data'
    )
    
    # Collect historical data every hour (on the hour)
    scheduler.add_job(
        collect_historical_data,
        'cron',
        minute=0,  # Run at the start of every hour
        id='collect_data_hourly'
    )
    
    # Also collect every 15 minutes for faster initial data buildup
    scheduler.add_job(
        collect_historical_data,
        'interval',
        minutes=15,
        id='collect_data_interval'
    )
    
    scheduler.start()
    logger.info(f"Scheduler started. Analysis: {settings.data_refresh_interval}s, Data collection: every hour + every 15min")
    
    yield
    
    # Cleanup
    scheduler.shutdown()
    client = await get_nado_client()
    await client.close()


# Create FastAPI app
app = FastAPI(
    title="Nado Trading Setup Analyzer",
    description="""
    A comprehensive trading analysis tool for Nado perpetual markets.
    
    ## Features
    - Real-time market data from Nado DEX
    - Technical analysis (RSI, MACD, Bollinger Bands, Moving Averages)
    - Funding rate analysis
    - Trading setup scoring and recommendations
    - Risk management suggestions
    
    ## Data Sources
    - Nado Gateway API for real-time orderbook
    - Nado Archive API for historical data
    
    Reference: https://docs.nado.xyz/developer-resources/api/v2
    """,
    version="1.0.0",
    lifespan=lifespan
)

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ==================== API Endpoints ====================

@app.get("/api/health")
async def health_check():
    """Health check endpoint"""
    return {
        "status": "healthy",
        "last_update": _last_update.isoformat() if _last_update else None,
        "markets_loaded": len(_cached_setups)
    }


@app.get("/api/summary", response_model=MarketSummary)
async def get_market_summary():
    """
    Get market summary with top movers and best setups
    
    Returns overview of all markets including:
    - Total volume
    - Top gainers/losers
    - Highest/lowest funding rates
    - Best trading setups
    """
    if _cached_market_summary is None:
        raise HTTPException(status_code=503, detail="Data not yet loaded")
    return _cached_market_summary


@app.get("/api/setups", response_model=List[TradingSetup])
async def get_all_setups(
    signal: Optional[TradingSignal] = Query(None, description="Filter by trading signal"),
    quality: Optional[SetupQuality] = Query(None, description="Filter by setup quality"),
    min_score: float = Query(0, ge=0, le=100, description="Minimum overall score"),
    max_score: float = Query(100, ge=0, le=100, description="Maximum overall score"),
    limit: int = Query(20, ge=1, le=100, description="Maximum number of results")
):
    """
    Get all trading setups with optional filtering
    
    Filter options:
    - signal: Filter by trading signal (strong_buy, buy, neutral, sell, strong_sell)
    - quality: Filter by setup quality (excellent, good, average, poor)
    - min_score/max_score: Filter by overall score range
    - limit: Maximum number of results
    """
    if not _cached_setups:
        raise HTTPException(status_code=503, detail="Data not yet loaded")
    
    filtered = _cached_setups
    
    # Apply filters
    if signal:
        filtered = [s for s in filtered if s.signal == signal]
    if quality:
        filtered = [s for s in filtered if s.setup_quality == quality]
    
    filtered = [s for s in filtered if min_score <= s.overall_score <= max_score]
    
    return filtered[:limit]


@app.get("/api/setups/{symbol}", response_model=TradingSetup)
async def get_setup_by_symbol(symbol: str):
    """
    Get trading setup for a specific symbol
    
    Returns detailed analysis including:
    - Market data (price, volume, spread)
    - Technical indicators
    - Funding analysis
    - Component scores
    - Risk parameters
    - Bullish/bearish factors
    """
    symbol = symbol.upper()
    
    setup = next((s for s in _cached_setups if s.symbol == symbol), None)
    
    if setup is None:
        raise HTTPException(status_code=404, detail=f"Symbol {symbol} not found")
    
    return setup


@app.get("/api/markets")
async def get_markets():
    """
    Get list of all available perpetual markets
    
    Returns basic market info for each trading pair
    """
    if not _cached_setups:
        raise HTTPException(status_code=503, detail="Data not yet loaded")
    
    return [
        {
            "symbol": s.symbol,
            "base_asset": s.market_data.base_asset,
            "quote_asset": s.market_data.quote_asset,
            "last_price": s.market_data.last_price,
            "price_change_24h": s.market_data.price_change_percent_24h,
            "volume_24h": s.market_data.volume_24h,
            "funding_rate": s.funding_analysis.current_rate,
            "overall_score": s.overall_score,
            "signal": s.signal.value,
            "quality": s.setup_quality.value
        }
        for s in _cached_setups
    ]


@app.get("/api/best-setups")
async def get_best_setups(
    direction: str = Query("long", enum=["long", "short", "any"]),
    limit: int = Query(5, ge=1, le=20)
):
    """
    Get the best trading setups
    
    Parameters:
    - direction: "long" for buy setups, "short" for sell setups, "any" for both
    - limit: Number of setups to return
    """
    if not _cached_setups:
        raise HTTPException(status_code=503, detail="Data not yet loaded")
    
    filtered = _cached_setups
    
    if direction == "long":
        filtered = [s for s in filtered if s.signal in [TradingSignal.BUY, TradingSignal.STRONG_BUY]]
    elif direction == "short":
        filtered = [s for s in filtered if s.signal in [TradingSignal.SELL, TradingSignal.STRONG_SELL]]
    
    # Sort by score
    filtered.sort(key=lambda x: x.overall_score, reverse=True)
    
    return [
        {
            "symbol": s.symbol,
            "signal": s.signal.value,
            "quality": s.setup_quality.value,
            "overall_score": s.overall_score,
            "price": s.market_data.last_price,
            "funding_rate": s.funding_analysis.current_rate,
            "suggested_entry": s.recommended_entry,
            "suggested_stop_loss": s.recommended_stop_loss,
            "suggested_take_profit": s.recommended_take_profit,
            "suggested_leverage": s.suggested_leverage,
            "risk_level": s.risk_level,
            "bullish_factors": s.bullish_factors[:3],
            "bearish_factors": s.bearish_factors[:3],
            "warnings": s.warnings
        }
        for s in filtered[:limit]
    ]


@app.get("/api/funding-opportunities")
async def get_funding_opportunities(
    favorable_for: str = Query("long", enum=["long", "short"]),
    limit: int = Query(5, ge=1, le=20)
):
    """
    Find funding rate arbitrage opportunities
    
    Returns markets with favorable funding rates for the specified direction.
    - Long: Negative funding (longs get paid)
    - Short: Positive funding (shorts get paid)
    """
    if not _cached_setups:
        raise HTTPException(status_code=503, detail="Data not yet loaded")
    
    if favorable_for == "long":
        # Sort by most negative funding (best for longs)
        sorted_setups = sorted(_cached_setups, key=lambda x: x.funding_analysis.current_rate)
        filtered = [s for s in sorted_setups if s.funding_analysis.is_favorable_long]
    else:
        # Sort by most positive funding (best for shorts)
        sorted_setups = sorted(_cached_setups, key=lambda x: x.funding_analysis.current_rate, reverse=True)
        filtered = [s for s in sorted_setups if s.funding_analysis.is_favorable_short]
    
    return [
        {
            "symbol": s.symbol,
            "funding_rate": s.funding_analysis.current_rate,
            "annual_rate": s.funding_analysis.annual_rate,
            "rate_trend": s.funding_analysis.rate_trend,
            "price": s.market_data.last_price,
            "volume_24h": s.market_data.volume_24h
        }
        for s in filtered[:limit]
    ]


@app.post("/api/refresh")
async def trigger_refresh():
    """
    Manually trigger data refresh
    
    Use sparingly - data automatically refreshes on schedule
    """
    await refresh_data()
    return {"status": "refresh_complete", "timestamp": datetime.utcnow().isoformat()}


@app.get("/api/database/stats")
async def get_database_stats():
    """
    Get database statistics
    
    Shows count of trades, candles, and snapshots stored
    """
    collector = get_data_collector()
    stats = collector.get_database_stats()
    return stats


@app.get("/api/database/info")
async def get_database_info():
    """
    Get database connection info (for debugging)
    """
    import os
    from app.database import get_database_url
    
    db_url = get_database_url()
    is_postgres = "postgresql" in db_url
    is_sqlite = "sqlite" in db_url
    
    # Don't expose full URL with credentials
    if "@" in db_url:
        safe_url = "postgresql://***@" + db_url.split("@")[-1]
    else:
        safe_url = db_url
    
    return {
        "database_type": "PostgreSQL" if is_postgres else "SQLite",
        "connection": safe_url,
        "env_var_set": os.environ.get("DATABASE_URL") is not None,
        "persistent": is_postgres,  # SQLite on Render is NOT persistent
        "note": "PostgreSQL is persistent, SQLite resets on each deploy" if not is_postgres else "Using persistent PostgreSQL"
    }


@app.post("/api/database/seed")
async def trigger_seed():
    """
    Manually trigger historical data seeding from Binance
    """
    await seed_external_data()
    
    collector = get_data_collector()
    stats = collector.get_database_stats()
    
    return {
        "status": "seeding_complete",
        "timestamp": datetime.utcnow().isoformat(),
        "stats": stats
    }


@app.get("/api/test/binance")
async def test_binance_fetch():
    """
    Test direct Binance API fetch (for debugging)
    """
    import httpx
    
    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.get(
                "https://api.binance.com/api/v3/klines",
                params={"symbol": "BTCUSDT", "interval": "1h", "limit": 10}
            )
            response.raise_for_status()
            data = response.json()
            
            return {
                "status": "success",
                "candles_fetched": len(data),
                "first_candle": {
                    "timestamp": data[0][0] if data else None,
                    "open": data[0][1] if data else None,
                    "close": data[0][4] if data else None
                } if data else None,
                "last_candle": {
                    "timestamp": data[-1][0] if data else None,
                    "open": data[-1][1] if data else None,
                    "close": data[-1][4] if data else None
                } if data else None
            }
    except Exception as e:
        return {
            "status": "error",
            "error": str(e),
            "error_type": type(e).__name__
        }


@app.post("/api/test/seed-btc")
async def test_seed_btc():
    """
    Test seeding just BTC (for debugging)
    """
    from app.external_data import fetch_binance_klines, store_external_candles, aggregate_and_store_higher_timeframes
    
    results = {}
    
    try:
        # Fetch from Binance
        ohlcv = await fetch_binance_klines("BTCUSDT", interval="1h", limit=200)
        results["fetched_candles"] = len(ohlcv)
        
        if ohlcv:
            results["first_candle"] = ohlcv[0]
            results["last_candle"] = ohlcv[-1]
            
            # Try to store
            stored_1h = store_external_candles("BTC-PERP_USDT0", ohlcv, "1h")
            results["stored_1h"] = stored_1h
            
            # Aggregate to higher TFs
            stored_higher = aggregate_and_store_higher_timeframes("BTC-PERP_USDT0", ohlcv)
            results["stored_higher_tf"] = stored_higher
        
        # Check final count
        collector = get_data_collector()
        btc_candles = collector.get_candles("BTC-PERP_USDT0", "1h", 200)
        results["final_1h_count"] = len(btc_candles)
        
        return {"status": "success", "results": results}
        
    except Exception as e:
        import traceback
        return {
            "status": "error", 
            "error": str(e),
            "traceback": traceback.format_exc()
        }


@app.post("/api/database/collect")
async def trigger_data_collection():
    """
    Manually trigger historical data collection
    
    Fetches trades from Nado API and aggregates into candles for all timeframes.
    This can take a few minutes depending on the number of markets.
    """
    await collect_historical_data()
    
    collector = get_data_collector()
    stats = collector.get_database_stats()
    
    return {
        "status": "collection_complete",
        "timestamp": datetime.utcnow().isoformat(),
        "stats": stats
    }


@app.get("/api/candles/{ticker_id}")
async def get_candles(
    ticker_id: str,
    timeframe: str = Query("1h", enum=["1h", "4h", "12h", "1d"]),
    limit: int = Query(100, ge=1, le=500)
):
    """
    Get historical candles for a specific market
    
    Timeframes: 1h (hourly), 4h (4-hour), 12h (12-hour), 1d (daily)
    """
    collector = get_data_collector()
    candles = collector.get_candles(ticker_id.upper(), timeframe, limit)
    
    if not candles:
        return {
            "ticker_id": ticker_id,
            "timeframe": timeframe,
            "count": 0,
            "candles": [],
            "message": "No candles available - data collection may still be in progress"
        }
    
    return {
        "ticker_id": ticker_id,
        "timeframe": timeframe,
        "count": len(candles),
        "candles": [
            {
                "timestamp": c.timestamp.isoformat(),
                "open": c.open,
                "high": c.high,
                "low": c.low,
                "close": c.close,
                "volume": c.volume
            }
            for c in candles
        ]
    }


@app.get("/api/signals/{ticker_id}")
async def get_multi_timeframe_signals(ticker_id: str):
    """
    Get trading signals for all timeframes (1h, 4h, 12h, 1d) for a specific market
    
    Returns indicators and signal for each timeframe:
    - RSI, MACD, Supertrend
    - Signal: bullish, bearish, or neutral
    - Confluence score across timeframes
    """
    collector = get_data_collector()
    ticker_id = ticker_id.upper()
    timeframes = ["1h", "4h", "12h", "1d"]
    
    # Get current price from cached setups
    current_price = 0.0
    setup = next((s for s in _cached_setups if s.symbol == ticker_id), None)
    if setup:
        current_price = setup.market_data.last_price
    
    result = {
        "ticker_id": ticker_id,
        "current_price": current_price,
        "timeframes": {},
        "confluence": {
            "bullish_count": 0,
            "bearish_count": 0,
            "neutral_count": 0,
            "overall_signal": "neutral",
            "score": 0
        }
    }
    
    bullish_count = 0
    bearish_count = 0
    neutral_count = 0
    total_score = 0
    
    for tf in timeframes:
        candles = collector.get_candles(ticker_id, tf, limit=100)
        
        if not candles:
            result["timeframes"][tf] = {
                "signal": "tbd",
                "score": 0,
                "reasons": ["Insufficient data"],
                "indicators": {
                    "rsi_14": None,
                    "macd": None,
                    "macd_signal": None,
                    "supertrend": None,
                    "supertrend_trend": "tbd",
                    "ema_9": None,
                    "ema_21": None,
                    "candle_count": 0
                }
            }
            continue
        
        # Convert candles to OHLCV format
        ohlcv_data = [
            OHLCV(
                timestamp=c.timestamp,
                open=c.open,
                high=c.high,
                low=c.low,
                close=c.close,
                volume=c.volume
            )
            for c in candles
        ]
        
        # Calculate indicators
        indicators = calculate_all_indicators(ohlcv_data)
        
        # Determine signal
        signal_data = determine_signal_from_indicators(indicators, current_price)
        
        result["timeframes"][tf] = {
            "signal": signal_data["signal"],
            "score": signal_data["score"],
            "reasons": signal_data["reasons"],
            "indicators": {
                "rsi_14": indicators.get("rsi_14"),
                "macd": indicators.get("macd"),
                "macd_signal": indicators.get("macd_signal"),
                "macd_histogram": indicators.get("macd_histogram"),
                "supertrend": indicators.get("supertrend"),
                "supertrend_direction": indicators.get("supertrend_direction"),
                "supertrend_trend": indicators.get("supertrend_trend"),
                "ema_9": indicators.get("ema_9"),
                "ema_21": indicators.get("ema_21"),
                "sma_20": indicators.get("sma_20"),
                "bb_upper": indicators.get("bb_upper"),
                "bb_lower": indicators.get("bb_lower"),
                "atr_14": indicators.get("atr_14"),
                "candle_count": indicators.get("candle_count", 0)
            }
        }
        
        # Count for confluence
        if signal_data["signal"] == "bullish":
            bullish_count += 1
            total_score += signal_data["score"]
        elif signal_data["signal"] == "bearish":
            bearish_count += 1
            total_score -= abs(signal_data["score"])
        else:
            neutral_count += 1
    
    # Calculate confluence
    result["confluence"]["bullish_count"] = bullish_count
    result["confluence"]["bearish_count"] = bearish_count
    result["confluence"]["neutral_count"] = neutral_count
    result["confluence"]["score"] = total_score
    
    if bullish_count >= 3:
        result["confluence"]["overall_signal"] = "strong_bullish"
    elif bullish_count >= 2 and bearish_count == 0:
        result["confluence"]["overall_signal"] = "bullish"
    elif bearish_count >= 3:
        result["confluence"]["overall_signal"] = "strong_bearish"
    elif bearish_count >= 2 and bullish_count == 0:
        result["confluence"]["overall_signal"] = "bearish"
    else:
        result["confluence"]["overall_signal"] = "neutral"
    
    return result


@app.get("/api/signals")
async def get_all_multi_timeframe_signals():
    """
    Get multi-timeframe signals for all markets
    
    Returns a summary of signals across all timeframes for each market
    """
    collector = get_data_collector()
    timeframes = ["1h", "4h", "12h", "1d"]
    
    results = []
    
    for setup in _cached_setups:
        ticker_id = setup.symbol
        current_price = setup.market_data.last_price
        
        market_signals = {
            "ticker_id": ticker_id,
            "current_price": current_price,
            "price_change_24h": setup.market_data.price_change_percent_24h,
            "timeframes": {}
        }
        
        bullish_count = 0
        bearish_count = 0
        
        for tf in timeframes:
            candles = collector.get_candles(ticker_id, tf, limit=100)
            
            if not candles or len(candles) < 10:
                market_signals["timeframes"][tf] = {
                    "signal": "tbd",
                    "supertrend": "tbd"
                }
                continue
            
            # Convert candles to OHLCV format
            ohlcv_data = [
                OHLCV(
                    timestamp=c.timestamp,
                    open=c.open,
                    high=c.high,
                    low=c.low,
                    close=c.close,
                    volume=c.volume
                )
                for c in candles
            ]
            
            # Calculate indicators
            indicators = calculate_all_indicators(ohlcv_data)
            signal_data = determine_signal_from_indicators(indicators, current_price)
            
            market_signals["timeframes"][tf] = {
                "signal": signal_data["signal"],
                "supertrend": indicators.get("supertrend_trend", "tbd"),
                "rsi": indicators.get("rsi_14"),
                "score": signal_data["score"]
            }
            
            if signal_data["signal"] == "bullish":
                bullish_count += 1
            elif signal_data["signal"] == "bearish":
                bearish_count += 1
        
        # Overall confluence
        if bullish_count >= 3:
            market_signals["overall_signal"] = "strong_bullish"
        elif bullish_count >= 2 and bearish_count == 0:
            market_signals["overall_signal"] = "bullish"
        elif bearish_count >= 3:
            market_signals["overall_signal"] = "strong_bearish"
        elif bearish_count >= 2 and bullish_count == 0:
            market_signals["overall_signal"] = "bearish"
        else:
            market_signals["overall_signal"] = "neutral"
        
        market_signals["bullish_count"] = bullish_count
        market_signals["bearish_count"] = bearish_count
        
        results.append(market_signals)
    
    # Sort by confluence (most bullish or bearish first)
    results.sort(key=lambda x: abs(x.get("bullish_count", 0) - x.get("bearish_count", 0)), reverse=True)
    
    return results


# ==================== Static Files (Frontend) ====================

# Mount static files directory
app.mount("/static", StaticFiles(directory="static"), name="static")


@app.get("/")
async def serve_frontend():
    """Serve the frontend application"""
    return FileResponse("static/index.html")


# ==================== Main Entry Point ====================

if __name__ == "__main__":
    import uvicorn
    settings = get_settings()
    uvicorn.run(
        "app.main:app",
        host=settings.host,
        port=settings.port,
        reload=settings.debug
    )

