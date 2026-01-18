"""
Database setup for storing historical price data

Stores OHLCV candles for multiple timeframes:
- 1h (hourly)
- 4h (4-hour)
- 12h (12-hour) 
- 1d (daily)

No mock data - only real trades aggregated into candles.
"""
from datetime import datetime
from typing import Optional, List
from sqlalchemy import Column, Integer, String, Float, DateTime, UniqueConstraint, Index, create_engine
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker
import logging

from app.config import get_settings

logger = logging.getLogger(__name__)

Base = declarative_base()


class Candle(Base):
    """
    OHLCV candlestick data
    
    Stores real price data aggregated from trades.
    No mock/synthetic data allowed.
    """
    __tablename__ = "candles"
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    
    # Market identifier
    ticker_id = Column(String(50), nullable=False, index=True)
    product_id = Column(Integer, nullable=True)
    
    # Timeframe: "1h", "4h", "12h", "1d"
    timeframe = Column(String(10), nullable=False, index=True)
    
    # Candle timestamp (start of the period)
    timestamp = Column(DateTime, nullable=False, index=True)
    
    # OHLCV data
    open = Column(Float, nullable=False)
    high = Column(Float, nullable=False)
    low = Column(Float, nullable=False)
    close = Column(Float, nullable=False)
    volume = Column(Float, nullable=False, default=0)
    
    # Trade count in this candle
    trade_count = Column(Integer, nullable=False, default=0)
    
    # Metadata
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Unique constraint: one candle per ticker/timeframe/timestamp
    __table_args__ = (
        UniqueConstraint('ticker_id', 'timeframe', 'timestamp', name='uix_candle'),
        Index('ix_candle_lookup', 'ticker_id', 'timeframe', 'timestamp'),
    )
    
    def __repr__(self):
        return f"<Candle {self.ticker_id} {self.timeframe} {self.timestamp} O:{self.open} H:{self.high} L:{self.low} C:{self.close}>"


class Trade(Base):
    """
    Raw trade data from Nado API
    
    Stores individual trades for building candles.
    """
    __tablename__ = "trades"
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    
    # Trade identifiers
    trade_id = Column(Integer, nullable=False)
    ticker_id = Column(String(50), nullable=False, index=True)
    product_id = Column(Integer, nullable=True)
    
    # Trade data
    price = Column(Float, nullable=False)
    base_filled = Column(Float, nullable=False)
    quote_filled = Column(Float, nullable=False)
    trade_type = Column(String(10), nullable=True)  # "buy" or "sell"
    
    # Timestamp
    timestamp = Column(DateTime, nullable=False, index=True)
    
    # Metadata
    created_at = Column(DateTime, default=datetime.utcnow)
    
    __table_args__ = (
        UniqueConstraint('trade_id', 'ticker_id', name='uix_trade'),
        Index('ix_trade_lookup', 'ticker_id', 'timestamp'),
    )


class MarketSnapshot(Base):
    """
    Periodic snapshot of market data from contracts endpoint
    
    Stores funding rate, open interest, etc. over time.
    """
    __tablename__ = "market_snapshots"
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    
    ticker_id = Column(String(50), nullable=False, index=True)
    product_id = Column(Integer, nullable=True)
    
    # Price data
    last_price = Column(Float, nullable=True)
    mark_price = Column(Float, nullable=True)
    index_price = Column(Float, nullable=True)
    
    # Market data
    funding_rate = Column(Float, nullable=True)
    open_interest = Column(Float, nullable=True)
    volume_24h = Column(Float, nullable=True)
    price_change_24h = Column(Float, nullable=True)
    
    # Timestamp
    timestamp = Column(DateTime, nullable=False, index=True)
    
    __table_args__ = (
        Index('ix_snapshot_lookup', 'ticker_id', 'timestamp'),
    )


# Database engine and session
_engine = None
_async_engine = None
_SessionLocal = None
_AsyncSessionLocal = None


def get_database_url() -> str:
    """
    Get database URL from settings
    
    Handles both SQLite (local) and PostgreSQL (production)
    Render provides postgres:// but SQLAlchemy needs postgresql://
    """
    import os
    
    # Check for DATABASE_URL environment variable (Render sets this)
    db_url = os.environ.get("DATABASE_URL")
    
    if db_url:
        # Render uses postgres:// but SQLAlchemy needs postgresql://
        if db_url.startswith("postgres://"):
            db_url = db_url.replace("postgres://", "postgresql://", 1)
        return db_url
    
    # Fall back to settings (local development)
    settings = get_settings()
    return settings.database_url


def get_async_database_url() -> str:
    """Get async-compatible database URL"""
    db_url = get_database_url()
    
    if "postgresql://" in db_url:
        # Use asyncpg for PostgreSQL
        return db_url.replace("postgresql://", "postgresql+asyncpg://")
    elif "sqlite" in db_url and "aiosqlite" not in db_url:
        # Use aiosqlite for SQLite
        return db_url.replace("sqlite://", "sqlite+aiosqlite://")
    
    return db_url


def init_db():
    """Initialize the database (create tables)"""
    global _engine, _SessionLocal
    
    db_url = get_database_url()
    
    # For sync operations - remove async drivers
    sync_url = db_url.replace("+aiosqlite", "").replace("+asyncpg", "")
    
    _engine = create_engine(sync_url, echo=False)
    _SessionLocal = sessionmaker(bind=_engine)
    
    # Create all tables
    Base.metadata.create_all(bind=_engine)
    
    # Log without exposing credentials
    safe_url = sync_url.split("@")[-1] if "@" in sync_url else sync_url
    logger.info(f"Database initialized: ...{safe_url}")


async def init_async_db():
    """Initialize async database connection"""
    global _async_engine, _AsyncSessionLocal
    
    db_url = get_database_url()
    
    _async_engine = create_async_engine(db_url, echo=False)
    _AsyncSessionLocal = async_sessionmaker(
        bind=_async_engine,
        class_=AsyncSession,
        expire_on_commit=False
    )
    
    # Create tables using sync engine first
    init_db()
    
    logger.info("Async database initialized")


def get_session():
    """Get a sync database session"""
    if _SessionLocal is None:
        init_db()
    return _SessionLocal()


async def get_async_session() -> AsyncSession:
    """Get an async database session"""
    if _AsyncSessionLocal is None:
        await init_async_db()
    return _AsyncSessionLocal()


async def close_db():
    """Close database connections"""
    global _async_engine
    if _async_engine:
        await _async_engine.dispose()
        logger.info("Database connections closed")

