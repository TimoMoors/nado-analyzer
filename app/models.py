"""
Data models for Nado Trading Setup Analyzer
"""
from datetime import datetime
from typing import Optional, List
from pydantic import BaseModel, Field
from enum import Enum


class TradingSignal(str, Enum):
    """Trading signal types"""
    STRONG_BUY = "strong_buy"
    BUY = "buy"
    NEUTRAL = "neutral"
    SELL = "sell"
    STRONG_SELL = "strong_sell"


class SetupQuality(str, Enum):
    """Quality rating for trading setups"""
    EXCELLENT = "excellent"
    GOOD = "good"
    AVERAGE = "average"
    POOR = "poor"


class MarketData(BaseModel):
    """Market data for a trading instrument"""
    symbol: str
    base_asset: str
    quote_asset: str
    mark_price: float
    index_price: float
    last_price: float
    bid_price: float
    ask_price: float
    spread: float
    spread_percent: float
    volume_24h: float
    open_interest: Optional[float] = None
    funding_rate: float
    next_funding_time: Optional[datetime] = None
    price_change_24h: float
    price_change_percent_24h: float
    high_24h: float
    low_24h: float
    timestamp: datetime = Field(default_factory=datetime.utcnow)


class TechnicalIndicators(BaseModel):
    """Technical analysis indicators"""
    # Moving Averages
    sma_20: Optional[float] = None
    sma_50: Optional[float] = None
    ema_12: Optional[float] = None
    ema_26: Optional[float] = None
    
    # Momentum
    rsi_14: Optional[float] = None
    macd: Optional[float] = None
    macd_signal: Optional[float] = None
    macd_histogram: Optional[float] = None
    
    # Volatility
    bollinger_upper: Optional[float] = None
    bollinger_middle: Optional[float] = None
    bollinger_lower: Optional[float] = None
    atr_14: Optional[float] = None
    
    # Trend
    adx_14: Optional[float] = None
    plus_di: Optional[float] = None
    minus_di: Optional[float] = None
    
    # Volume
    volume_sma_20: Optional[float] = None
    obv: Optional[float] = None


class FundingAnalysis(BaseModel):
    """Funding rate analysis"""
    current_rate: float
    predicted_rate: Optional[float] = None
    rate_trend: str  # "rising", "falling", "stable"
    annual_rate: float  # Annualized funding rate
    is_favorable_long: bool
    is_favorable_short: bool


class TradingSetup(BaseModel):
    """A complete trading setup analysis"""
    symbol: str
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    
    # Market data
    market_data: MarketData
    
    # Technical indicators
    indicators: TechnicalIndicators
    
    # Funding analysis
    funding_analysis: FundingAnalysis
    
    # Setup scoring
    overall_score: float = Field(ge=0, le=100, description="Overall setup quality score 0-100")
    setup_quality: SetupQuality
    signal: TradingSignal
    
    # Component scores
    trend_score: float = Field(ge=0, le=100)
    momentum_score: float = Field(ge=0, le=100)
    funding_score: float = Field(ge=0, le=100)
    liquidity_score: float = Field(ge=0, le=100)
    volatility_score: float = Field(ge=0, le=100)
    
    # Risk assessment
    risk_level: str  # "low", "medium", "high"
    suggested_leverage: int = Field(ge=1, le=20)
    suggested_stop_loss_percent: float
    suggested_take_profit_percent: float
    
    # Reasoning
    bullish_factors: List[str] = []
    bearish_factors: List[str] = []
    warnings: List[str] = []
    
    # Entry recommendations
    recommended_entry: Optional[float] = None
    recommended_stop_loss: Optional[float] = None
    recommended_take_profit: Optional[float] = None


class OHLCV(BaseModel):
    """OHLCV candlestick data"""
    timestamp: datetime
    open: float
    high: float
    low: float
    close: float
    volume: float


class OrderBook(BaseModel):
    """Order book snapshot"""
    symbol: str
    bids: List[tuple[float, float]]  # [(price, quantity), ...]
    asks: List[tuple[float, float]]  # [(price, quantity), ...]
    timestamp: datetime = Field(default_factory=datetime.utcnow)


class MarketSummary(BaseModel):
    """Summary of all markets"""
    total_markets: int
    total_volume_24h: float
    top_gainers: List[dict]
    top_losers: List[dict]
    highest_funding: List[dict]
    lowest_funding: List[dict]
    best_setups: List[TradingSetup]
    timestamp: datetime = Field(default_factory=datetime.utcnow)

