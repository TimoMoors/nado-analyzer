"""
Data models for TAO Subnet Analyzer

Models for Bittensor/TAO ecosystem analysis including:
- Subnet metrics and token data
- Validator performance and staking
- Investment signals and recommendations
"""
from datetime import datetime
from typing import Optional, List, Dict, Any
from pydantic import BaseModel, Field
from enum import Enum


class StakeSignal(str, Enum):
    """Staking recommendation signals"""
    STRONG_STAKE = "strong_stake"
    STAKE = "stake"
    HOLD = "hold"
    REDUCE = "reduce"
    AVOID = "avoid"


class InvestmentSignal(str, Enum):
    """Investment recommendation signals"""
    STRONG_BUY = "strong_buy"
    BUY = "buy"
    NEUTRAL = "neutral"
    SELL = "sell"
    STRONG_SELL = "strong_sell"


class SentimentLevel(str, Enum):
    """Fear & Greed sentiment levels"""
    EXTREME_FEAR = "extreme_fear"
    FEAR = "fear"
    NEUTRAL = "neutral"
    GREED = "greed"
    EXTREME_GREED = "extreme_greed"


class SubnetData(BaseModel):
    """Core subnet metrics from /api/subnet/latest/v1"""
    netuid: int
    name: Optional[str] = None
    symbol: Optional[str] = None
    
    # Network metrics
    emission: float = 0  # Current emission rate
    projected_emission: float = 0
    validators: int = 0
    active_validators: int = 0
    active_miners: int = 0
    max_neurons: int = 0
    active_keys: int = 0
    
    # Registration
    registration_cost: float = 0
    neuron_registration_cost: float = 0
    registration_allowed: bool = True
    
    # Flow metrics (in raw units, need to be converted)
    tao_flow: float = 0
    net_flow_1_day: float = 0
    net_flow_7_days: float = 0
    net_flow_30_days: float = 0
    
    # Timing
    tempo: int = 0
    immunity_period: int = 0
    
    # Owner info
    owner_address: Optional[str] = None
    
    timestamp: datetime = Field(default_factory=datetime.utcnow)


class SubnetPoolData(BaseModel):
    """Subnet token pool/market data from /api/dtao/pool/latest/v1"""
    netuid: int
    name: Optional[str] = None
    symbol: Optional[str] = None
    
    # Market metrics
    market_cap: float = 0
    liquidity: float = 0
    price: float = 0  # Price in TAO
    price_usd: Optional[float] = None
    
    # Price changes
    price_change_1_hour: Optional[float] = None
    price_change_1_day: Optional[float] = None
    price_change_1_week: Optional[float] = None
    price_change_1_month: Optional[float] = None
    market_cap_change_1_day: Optional[float] = None
    
    # Volume
    tao_volume_24h: float = 0
    tao_buy_volume_24h: float = 0
    tao_sell_volume_24h: float = 0
    buys_24h: int = 0
    sells_24h: int = 0
    buyers_24h: int = 0
    sellers_24h: int = 0
    
    # Sentiment
    fear_and_greed_index: Optional[float] = None
    fear_and_greed_sentiment: Optional[str] = None
    
    # Pool composition
    total_tao: float = 0
    total_alpha: float = 0
    alpha_staked: float = 0
    
    # Price range
    highest_price_24h: Optional[float] = None
    lowest_price_24h: Optional[float] = None
    
    timestamp: datetime = Field(default_factory=datetime.utcnow)


class ValidatorData(BaseModel):
    """Validator data from /api/validator/latest/v1"""
    hotkey: str
    coldkey: Optional[str] = None
    name: Optional[str] = None
    
    # Ranking
    rank: int = 0
    
    # Staking metrics
    stake: float = 0
    stake_24h_change: float = 0
    system_stake: float = 0
    validator_stake: float = 0
    dominance: float = 0
    
    # Nominators
    nominators: int = 0
    nominators_24h_change: int = 0
    
    # Returns
    apr: float = 0  # Current APR
    apr_7_day_average: float = 0
    apr_30_day_average: float = 0
    total_daily_return: float = 0
    validator_return: float = 0
    nominator_return_per_k: float = 0  # Return per 1000 TAO staked
    nominator_return_per_k_7_day_avg: float = 0
    nominator_return_per_k_30_day_avg: float = 0
    
    # Commission
    take: float = 0  # Validator's commission rate (0-1)
    
    # Emissions
    pending_emission: float = 0
    
    # Subnets (lists of netuid IDs)
    registrations: List[int] = []  # Subnets registered on
    permits: List[int] = []  # Subnets with validator permit
    
    timestamp: datetime = Field(default_factory=datetime.utcnow)


class MetagraphEntry(BaseModel):
    """Individual miner/validator entry from /api/metagraph/latest/v1"""
    netuid: int
    uid: int
    hotkey: str
    coldkey: Optional[str] = None
    
    # Performance metrics
    stake: float = 0
    trust: float = 0
    validator_trust: float = 0
    consensus: float = 0
    incentive: float = 0
    dividends: float = 0
    emission: float = 0
    
    # Daily rewards
    daily_reward: float = 0
    daily_mining_tao: float = 0
    daily_validating_tao: float = 0
    daily_total_rewards_as_tao: float = 0
    
    # Status
    active: bool = True
    validator_permit: bool = False
    is_immunity_period: bool = False
    rank: int = 0
    
    timestamp: datetime = Field(default_factory=datetime.utcnow)


class StakeRecommendation(BaseModel):
    """Staking recommendation for a validator"""
    validator_hotkey: str
    validator_name: Optional[str] = None
    validator_rank: int = 0
    
    # Signal
    signal: StakeSignal
    score: float = Field(ge=0, le=100)  # 0-100 score
    
    # Key metrics
    apr: float = 0
    apr_7_day_avg: float = 0
    apr_30_day_avg: float = 0
    take_rate: float = 0  # Commission
    nominator_return_per_k: float = 0
    
    # Growth indicators
    stake_24h_change: float = 0
    nominators_24h_change: int = 0
    
    # Risk factors
    stake_concentration: float = 0  # Dominance
    nominator_count: int = 0
    
    # Reasoning
    bullish_factors: List[str] = []
    bearish_factors: List[str] = []
    warnings: List[str] = []
    
    timestamp: datetime = Field(default_factory=datetime.utcnow)


class SubnetInvestmentScore(BaseModel):
    """Investment analysis for a subnet token"""
    netuid: int
    name: Optional[str] = None
    symbol: Optional[str] = None
    
    # Signal
    signal: InvestmentSignal
    overall_score: float = Field(ge=0, le=100)
    
    # Component scores
    momentum_score: float = Field(ge=0, le=100)  # Price momentum
    flow_score: float = Field(ge=0, le=100)  # TAO flow momentum
    emission_score: float = Field(ge=0, le=100)  # Emission attractiveness
    liquidity_score: float = Field(ge=0, le=100)  # Trading liquidity
    sentiment_score: float = Field(ge=0, le=100)  # Fear & Greed
    network_health_score: float = Field(ge=0, le=100)  # Active validators/miners
    
    # Market data
    market_cap: float = 0
    price: float = 0
    price_change_24h: Optional[float] = None
    price_change_7d: Optional[float] = None
    volume_24h: float = 0
    
    # Flow data
    emission: float = 0
    net_flow_7d: float = 0
    
    # Sentiment
    fear_and_greed_index: Optional[float] = None
    fear_and_greed_sentiment: Optional[str] = None
    
    # Network
    active_validators: int = 0
    active_miners: int = 0
    
    # Reasoning
    bullish_factors: List[str] = []
    bearish_factors: List[str] = []
    warnings: List[str] = []
    
    timestamp: datetime = Field(default_factory=datetime.utcnow)


class TAOMarketSummary(BaseModel):
    """Summary of the TAO ecosystem"""
    total_subnets: int = 0
    total_validators: int = 0
    total_market_cap: float = 0
    total_liquidity: float = 0
    
    # Top performers
    top_subnets_by_emission: List[Dict[str, Any]] = []
    top_subnets_by_market_cap: List[Dict[str, Any]] = []
    top_subnets_by_flow: List[Dict[str, Any]] = []
    
    # Best opportunities
    best_stake_recommendations: List[StakeRecommendation] = []
    best_investment_scores: List[SubnetInvestmentScore] = []
    
    # Market sentiment
    average_fear_greed: Optional[float] = None
    bullish_subnets: int = 0
    bearish_subnets: int = 0
    neutral_subnets: int = 0
    
    timestamp: datetime = Field(default_factory=datetime.utcnow)
