"""
Trading Setup Analyzer - Price Action Based

Core Philosophy:
- Price action is king - base all setups on actual price movement
- Use RSI, MACD, Volume as CONFIRMATION only (secondary signals)
- Look for CONFLUENCE - multiple factors agreeing = high probability
- Entry around support to minimize downside risk
- Only show high probability setups (don't overcomplicate)
- No mock data - show "tbd" when data unavailable

Reference: https://docs.nado.xyz/funding-rates
"""
import pandas as pd
import numpy as np
from typing import List, Optional, Tuple, Dict
from datetime import datetime
import logging

from app.models import (
    MarketData, TechnicalIndicators, FundingAnalysis, TradingSetup,
    TradingSignal, SetupQuality, OHLCV
)
from app.config import get_settings

logger = logging.getLogger(__name__)


class TradingAnalyzer:
    """
    Price Action Based Trading Analyzer
    
    Signal Hierarchy:
    1. PRIMARY: Price Action (support/resistance, trend, price structure)
    2. SECONDARY: Indicator Confluence (RSI, MACD, Volume)
    3. TERTIARY: Funding Rate (cost of carry)
    
    Only generates signals when:
    - Clear price action setup exists
    - At least 2 confirming indicators align (confluence)
    - Risk/reward is favorable (entry near support)
    """
    
    def __init__(self):
        self.settings = get_settings()
    
    def calculate_technical_indicators(self, klines: List[OHLCV]) -> TechnicalIndicators:
        """
        Calculate technical indicators from OHLCV data
        
        Returns empty indicators (tbd) if insufficient data - NO MOCK DATA
        """
        if not klines or len(klines) < 26:
            logger.info(f"Insufficient kline data ({len(klines) if klines else 0} candles) - indicators will show 'tbd'")
            return TechnicalIndicators()
        
        # Convert to DataFrame
        df = pd.DataFrame([{
            'timestamp': k.timestamp,
            'open': k.open,
            'high': k.high,
            'low': k.low,
            'close': k.close,
            'volume': k.volume
        } for k in klines])
        
        df = df.sort_values('timestamp').reset_index(drop=True)
        
        try:
            indicators = TechnicalIndicators()
            
            # RSI (14) - Momentum indicator
            if len(df) >= 14:
                delta = df['close'].diff()
                gain = (delta.where(delta > 0, 0)).rolling(window=14).mean()
                loss = (-delta.where(delta < 0, 0)).rolling(window=14).mean()
                rs = gain / loss
                rsi = 100 - (100 / (1 + rs))
                if pd.notna(rsi.iloc[-1]):
                    indicators.rsi_14 = float(rsi.iloc[-1])
            
            # MACD (12, 26, 9) - Trend/Momentum
            if len(df) >= 26:
                ema_12 = df['close'].ewm(span=12, adjust=False).mean()
                ema_26 = df['close'].ewm(span=26, adjust=False).mean()
                macd_line = ema_12 - ema_26
                signal_line = macd_line.ewm(span=9, adjust=False).mean()
                
                if pd.notna(macd_line.iloc[-1]):
                    indicators.macd = float(macd_line.iloc[-1])
                if pd.notna(signal_line.iloc[-1]):
                    indicators.macd_signal = float(signal_line.iloc[-1])
                if pd.notna(macd_line.iloc[-1]) and pd.notna(signal_line.iloc[-1]):
                    indicators.macd_histogram = float(macd_line.iloc[-1] - signal_line.iloc[-1])
                
                indicators.ema_12 = float(ema_12.iloc[-1]) if pd.notna(ema_12.iloc[-1]) else None
                indicators.ema_26 = float(ema_26.iloc[-1]) if pd.notna(ema_26.iloc[-1]) else None
            
            # Simple Moving Averages
            if len(df) >= 20:
                sma_20 = df['close'].rolling(window=20).mean().iloc[-1]
                if pd.notna(sma_20):
                    indicators.sma_20 = float(sma_20)
            
            if len(df) >= 50:
                sma_50 = df['close'].rolling(window=50).mean().iloc[-1]
                if pd.notna(sma_50):
                    indicators.sma_50 = float(sma_50)
            
            # Volume SMA (for volume confirmation)
            if len(df) >= 20:
                vol_sma = df['volume'].rolling(window=20).mean().iloc[-1]
                if pd.notna(vol_sma):
                    indicators.volume_sma_20 = float(vol_sma)
            
            # Bollinger Bands (for volatility and support/resistance)
            if len(df) >= 20:
                bb_middle = df['close'].rolling(window=20).mean().iloc[-1]
                bb_std = df['close'].rolling(window=20).std().iloc[-1]
                if pd.notna(bb_middle) and pd.notna(bb_std):
                    indicators.bollinger_middle = float(bb_middle)
                    indicators.bollinger_upper = float(bb_middle + (bb_std * 2))
                    indicators.bollinger_lower = float(bb_middle - (bb_std * 2))
            
            # ATR (14) - for stop loss calculation
            if len(df) >= 14:
                high_low = df['high'] - df['low']
                high_close = abs(df['high'] - df['close'].shift())
                low_close = abs(df['low'] - df['close'].shift())
                tr = pd.concat([high_low, high_close, low_close], axis=1).max(axis=1)
                atr = tr.rolling(window=14).mean().iloc[-1]
                if pd.notna(atr):
                    indicators.atr_14 = float(atr)
            
            return indicators
            
        except Exception as e:
            logger.error(f"Error calculating indicators: {e}")
            return TechnicalIndicators()
    
    def identify_support_resistance(
        self, 
        klines: List[OHLCV], 
        current_price: float
    ) -> Dict[str, Optional[float]]:
        """
        Identify key support and resistance levels from price action
        
        Uses swing highs/lows and recent price structure
        """
        result = {
            "nearest_support": None,
            "nearest_resistance": None,
            "distance_to_support_pct": None,
            "distance_to_resistance_pct": None,
            "at_support": False,
            "at_resistance": False
        }
        
        if not klines or len(klines) < 10:
            return result
        
        try:
            lows = [k.low for k in klines]
            highs = [k.high for k in klines]
            
            # Find swing lows (potential support)
            supports = []
            for i in range(2, len(lows) - 2):
                if lows[i] < lows[i-1] and lows[i] < lows[i-2] and \
                   lows[i] < lows[i+1] and lows[i] < lows[i+2]:
                    supports.append(lows[i])
            
            # Find swing highs (potential resistance)
            resistances = []
            for i in range(2, len(highs) - 2):
                if highs[i] > highs[i-1] and highs[i] > highs[i-2] and \
                   highs[i] > highs[i+1] and highs[i] > highs[i+2]:
                    resistances.append(highs[i])
            
            # Also add recent lows/highs
            recent_low = min(lows[-10:])
            recent_high = max(highs[-10:])
            supports.append(recent_low)
            resistances.append(recent_high)
            
            # Find nearest support below current price
            supports_below = [s for s in supports if s < current_price]
            if supports_below:
                result["nearest_support"] = max(supports_below)
                result["distance_to_support_pct"] = ((current_price - result["nearest_support"]) / current_price) * 100
                # Consider "at support" if within 1.5% of support
                result["at_support"] = result["distance_to_support_pct"] < 1.5
            
            # Find nearest resistance above current price
            resistances_above = [r for r in resistances if r > current_price]
            if resistances_above:
                result["nearest_resistance"] = min(resistances_above)
                result["distance_to_resistance_pct"] = ((result["nearest_resistance"] - current_price) / current_price) * 100
                # Consider "at resistance" if within 1.5% of resistance
                result["at_resistance"] = result["distance_to_resistance_pct"] < 1.5
            
        except Exception as e:
            logger.error(f"Error identifying support/resistance: {e}")
        
        return result
    
    def analyze_price_action(
        self, 
        klines: List[OHLCV], 
        market_data: MarketData
    ) -> Dict[str, any]:
        """
        PRIMARY SIGNAL: Analyze price action for trade setup
        
        Looks for:
        - Trend direction (higher highs/lows or lower highs/lows)
        - Price near support (good entry) or resistance (caution)
        - Recent price momentum
        """
        result = {
            "trend": "tbd",  # "bullish", "bearish", "sideways", "tbd"
            "trend_strength": "tbd",  # "strong", "moderate", "weak", "tbd"
            "price_position": "tbd",  # "at_support", "at_resistance", "mid_range", "tbd"
            "momentum": "tbd",  # "positive", "negative", "neutral", "tbd"
            "setup_type": None,  # "long_support_bounce", "short_resistance_rejection", etc.
            "is_actionable": False,
            "signals": []
        }
        
        if not klines or len(klines) < 10:
            return result
        
        current_price = market_data.last_price
        
        try:
            # Get support/resistance
            sr_levels = self.identify_support_resistance(klines, current_price)
            
            # Determine trend from price structure
            recent_closes = [k.close for k in klines[-20:]] if len(klines) >= 20 else [k.close for k in klines]
            
            if len(recent_closes) >= 10:
                first_half_avg = sum(recent_closes[:len(recent_closes)//2]) / (len(recent_closes)//2)
                second_half_avg = sum(recent_closes[len(recent_closes)//2:]) / (len(recent_closes)//2)
                
                pct_change = ((second_half_avg - first_half_avg) / first_half_avg) * 100
                
                if pct_change > 3:
                    result["trend"] = "bullish"
                    result["trend_strength"] = "strong" if pct_change > 6 else "moderate"
                elif pct_change < -3:
                    result["trend"] = "bearish"
                    result["trend_strength"] = "strong" if pct_change < -6 else "moderate"
                else:
                    result["trend"] = "sideways"
                    result["trend_strength"] = "weak"
            
            # Price position relative to support/resistance
            if sr_levels["at_support"]:
                result["price_position"] = "at_support"
                result["signals"].append("Price at support level - potential bounce zone")
            elif sr_levels["at_resistance"]:
                result["price_position"] = "at_resistance"
                result["signals"].append("Price at resistance level - potential rejection zone")
            else:
                result["price_position"] = "mid_range"
            
            # Recent momentum (last 5 candles)
            if len(klines) >= 5:
                recent_change = ((klines[-1].close - klines[-5].close) / klines[-5].close) * 100
                if recent_change > 1:
                    result["momentum"] = "positive"
                elif recent_change < -1:
                    result["momentum"] = "negative"
                else:
                    result["momentum"] = "neutral"
            
            # Identify actionable setups
            # LONG: Bullish trend + price at support + positive/neutral momentum
            if result["trend"] == "bullish" and result["price_position"] == "at_support":
                result["setup_type"] = "long_support_bounce"
                result["is_actionable"] = True
                result["signals"].append("SETUP: Long at support in bullish trend")
            
            # LONG: Sideways + price at support (range trade)
            elif result["trend"] == "sideways" and result["price_position"] == "at_support":
                result["setup_type"] = "long_range_support"
                result["is_actionable"] = True
                result["signals"].append("SETUP: Long at range support")
            
            # SHORT: Bearish trend + price at resistance + negative/neutral momentum
            elif result["trend"] == "bearish" and result["price_position"] == "at_resistance":
                result["setup_type"] = "short_resistance_rejection"
                result["is_actionable"] = True
                result["signals"].append("SETUP: Short at resistance in bearish trend")
            
            # SHORT: Sideways + price at resistance (range trade)
            elif result["trend"] == "sideways" and result["price_position"] == "at_resistance":
                result["setup_type"] = "short_range_resistance"
                result["is_actionable"] = True
                result["signals"].append("SETUP: Short at range resistance")
            
            # Store support/resistance for risk calculation
            result["support"] = sr_levels["nearest_support"]
            result["resistance"] = sr_levels["nearest_resistance"]
            result["distance_to_support_pct"] = sr_levels["distance_to_support_pct"]
            result["distance_to_resistance_pct"] = sr_levels["distance_to_resistance_pct"]
            
        except Exception as e:
            logger.error(f"Error analyzing price action: {e}")
        
        return result
    
    def analyze_indicator_confluence(
        self, 
        indicators: TechnicalIndicators,
        market_data: MarketData,
        price_action: Dict
    ) -> Dict[str, any]:
        """
        SECONDARY SIGNAL: Check indicator confluence
        
        Only confirms if RSI, MACD, and Volume agree with price action setup.
        Requires at least 2/3 indicators to confirm for a valid signal.
        """
        result = {
            "rsi_signal": "tbd",
            "macd_signal": "tbd", 
            "volume_signal": "tbd",
            "confluence_count": 0,
            "has_confluence": False,
            "confirming_signals": [],
            "conflicting_signals": []
        }
        
        setup_type = price_action.get("setup_type") or ""
        is_long_setup = setup_type.startswith("long")
        is_short_setup = setup_type.startswith("short")
        
        if not is_long_setup and not is_short_setup:
            return result
        
        # RSI Analysis
        if indicators.rsi_14 is not None:
            if is_long_setup:
                if indicators.rsi_14 < 35:
                    result["rsi_signal"] = "confirms"
                    result["confluence_count"] += 1
                    result["confirming_signals"].append(f"RSI oversold ({indicators.rsi_14:.1f}) - good for long")
                elif indicators.rsi_14 > 70:
                    result["rsi_signal"] = "conflicts"
                    result["conflicting_signals"].append(f"RSI overbought ({indicators.rsi_14:.1f}) - caution for long")
                else:
                    result["rsi_signal"] = "neutral"
            elif is_short_setup:
                if indicators.rsi_14 > 65:
                    result["rsi_signal"] = "confirms"
                    result["confluence_count"] += 1
                    result["confirming_signals"].append(f"RSI overbought ({indicators.rsi_14:.1f}) - good for short")
                elif indicators.rsi_14 < 30:
                    result["rsi_signal"] = "conflicts"
                    result["conflicting_signals"].append(f"RSI oversold ({indicators.rsi_14:.1f}) - caution for short")
                else:
                    result["rsi_signal"] = "neutral"
        
        # MACD Analysis
        if indicators.macd is not None and indicators.macd_signal is not None:
            macd_bullish = indicators.macd > indicators.macd_signal
            macd_histogram_positive = (indicators.macd_histogram or 0) > 0
            
            if is_long_setup:
                if macd_bullish or macd_histogram_positive:
                    result["macd_signal"] = "confirms"
                    result["confluence_count"] += 1
                    result["confirming_signals"].append("MACD bullish - confirms long")
                else:
                    result["macd_signal"] = "conflicts"
                    result["conflicting_signals"].append("MACD bearish - conflicts with long")
            elif is_short_setup:
                if not macd_bullish or not macd_histogram_positive:
                    result["macd_signal"] = "confirms"
                    result["confluence_count"] += 1
                    result["confirming_signals"].append("MACD bearish - confirms short")
                else:
                    result["macd_signal"] = "conflicts"
                    result["conflicting_signals"].append("MACD bullish - conflicts with short")
        
        # Volume Analysis (compare current to average)
        if indicators.volume_sma_20 is not None and market_data.volume_24h > 0:
            # High volume on setup = more conviction
            # We don't have current candle volume, so we use 24h volume as proxy
            # This is a simplified check
            if market_data.volume_24h > 100000:  # Minimum volume threshold
                result["volume_signal"] = "confirms"
                result["confluence_count"] += 1
                result["confirming_signals"].append("Adequate volume for trade execution")
            else:
                result["volume_signal"] = "weak"
                result["conflicting_signals"].append("Low volume - may have slippage")
        
        # Need at least 2 confirming signals for confluence
        result["has_confluence"] = result["confluence_count"] >= 2
        
        return result
    
    def analyze_funding_rate(
        self, 
        current_rate: float, 
        setup_direction: str
    ) -> FundingAnalysis:
        """
        TERTIARY SIGNAL: Funding rate analysis
        
        Positive rate = longs pay shorts (expensive to be long)
        Negative rate = shorts pay longs (expensive to be short)
        """
        annual_rate = current_rate * 24 * 365 * 100
        
        is_favorable_long = current_rate <= 0
        is_favorable_short = current_rate >= 0
        
        # Determine if funding helps or hurts the setup
        if setup_direction == "long":
            rate_trend = "favorable" if is_favorable_long else "unfavorable"
        elif setup_direction == "short":
            rate_trend = "favorable" if is_favorable_short else "unfavorable"
        else:
            rate_trend = "neutral"
        
        return FundingAnalysis(
            current_rate=current_rate,
            predicted_rate=None,  # tbd
            rate_trend=rate_trend,
            annual_rate=annual_rate,
            is_favorable_long=is_favorable_long,
            is_favorable_short=is_favorable_short
        )
    
    def calculate_risk_reward(
        self,
        current_price: float,
        support: Optional[float],
        resistance: Optional[float],
        setup_type: Optional[str],
        atr: Optional[float]
    ) -> Dict[str, any]:
        """
        Calculate risk management parameters
        
        - Entry: Current price (ideally at support for longs)
        - Stop Loss: Below support (for longs) or above resistance (for shorts)
        - Take Profit: Based on risk:reward ratio (minimum 2:1)
        """
        result = {
            "entry": current_price,
            "stop_loss": None,
            "take_profit": None,
            "risk_percent": None,
            "reward_percent": None,
            "risk_reward_ratio": None,
            "position_risk": "tbd",
            "suggested_leverage": 1
        }
        
        if not setup_type:
            return result
        
        is_long = setup_type.startswith("long")
        
        # Calculate stop loss
        if is_long and support:
            # Stop below support (with small buffer)
            result["stop_loss"] = support * 0.995
            result["risk_percent"] = ((current_price - result["stop_loss"]) / current_price) * 100
            
            # Take profit at resistance or 2:1 R:R
            if resistance:
                result["take_profit"] = resistance * 0.995
            else:
                # If no resistance, use 2:1 R:R
                result["take_profit"] = current_price * (1 + (result["risk_percent"] * 2 / 100))
            
            result["reward_percent"] = ((result["take_profit"] - current_price) / current_price) * 100
            
        elif not is_long and resistance:
            # Stop above resistance (with small buffer)
            result["stop_loss"] = resistance * 1.005
            result["risk_percent"] = ((result["stop_loss"] - current_price) / current_price) * 100
            
            # Take profit at support or 2:1 R:R
            if support:
                result["take_profit"] = support * 1.005
            else:
                result["take_profit"] = current_price * (1 - (result["risk_percent"] * 2 / 100))
            
            result["reward_percent"] = ((current_price - result["take_profit"]) / current_price) * 100
        
        # Use ATR for stop loss if no S/R available
        elif atr:
            atr_multiplier = 1.5
            if is_long:
                result["stop_loss"] = current_price - (atr * atr_multiplier)
                result["take_profit"] = current_price + (atr * atr_multiplier * 2)
            else:
                result["stop_loss"] = current_price + (atr * atr_multiplier)
                result["take_profit"] = current_price - (atr * atr_multiplier * 2)
            
            result["risk_percent"] = (atr * atr_multiplier / current_price) * 100
            result["reward_percent"] = (atr * atr_multiplier * 2 / current_price) * 100
        
        # Calculate R:R ratio
        if result["risk_percent"] and result["reward_percent"] and result["risk_percent"] > 0:
            result["risk_reward_ratio"] = result["reward_percent"] / result["risk_percent"]
        
        # Determine position risk level
        if result["risk_percent"]:
            if result["risk_percent"] < 2:
                result["position_risk"] = "low"
                result["suggested_leverage"] = min(10, int(5 / result["risk_percent"])) if result["risk_percent"] > 0 else 5
            elif result["risk_percent"] < 5:
                result["position_risk"] = "medium"
                result["suggested_leverage"] = min(5, int(3 / result["risk_percent"])) if result["risk_percent"] > 0 else 3
            else:
                result["position_risk"] = "high"
                result["suggested_leverage"] = 2
        
        # Cap leverage at reasonable levels
        result["suggested_leverage"] = max(1, min(10, result["suggested_leverage"]))
        
        return result
    
    def determine_signal_and_quality(
        self,
        price_action: Dict,
        confluence: Dict,
        risk_reward: Dict
    ) -> Tuple[TradingSignal, SetupQuality, float]:
        """
        Determine final trading signal based on all factors
        
        HIGH PROBABILITY ONLY:
        - Must have actionable price action setup
        - Must have indicator confluence (2+ confirming)
        - Must have acceptable R:R ratio (>= 1.5)
        """
        # Default: No setup
        if not price_action.get("is_actionable"):
            return TradingSignal.NEUTRAL, SetupQuality.POOR, 30.0
        
        # Check confluence
        if not confluence.get("has_confluence"):
            return TradingSignal.NEUTRAL, SetupQuality.AVERAGE, 45.0
        
        # Check R:R
        rr_ratio = risk_reward.get("risk_reward_ratio")
        if rr_ratio is None or rr_ratio < 1.5:
            return TradingSignal.NEUTRAL, SetupQuality.AVERAGE, 50.0
        
        # Calculate score
        score = 50.0
        
        # Price action contributes up to 30 points
        if price_action.get("trend_strength") == "strong":
            score += 15
        elif price_action.get("trend_strength") == "moderate":
            score += 10
        
        if price_action.get("price_position") in ["at_support", "at_resistance"]:
            score += 15
        
        # Confluence contributes up to 30 points (10 per confirming indicator)
        score += confluence.get("confluence_count", 0) * 10
        
        # R:R contributes up to 20 points
        if rr_ratio:
            if rr_ratio >= 3:
                score += 20
            elif rr_ratio >= 2:
                score += 15
            elif rr_ratio >= 1.5:
                score += 10
        
        # Subtract for conflicts
        score -= len(confluence.get("conflicting_signals", [])) * 5
        
        # Cap score
        score = max(0, min(100, score))
        
        # Determine signal
        setup_type = price_action.get("setup_type", "")
        is_long = setup_type.startswith("long")
        
        if score >= 75:
            signal = TradingSignal.STRONG_BUY if is_long else TradingSignal.STRONG_SELL
            quality = SetupQuality.EXCELLENT
        elif score >= 65:
            signal = TradingSignal.BUY if is_long else TradingSignal.SELL
            quality = SetupQuality.GOOD
        elif score >= 55:
            signal = TradingSignal.BUY if is_long else TradingSignal.SELL
            quality = SetupQuality.AVERAGE
        else:
            signal = TradingSignal.NEUTRAL
            quality = SetupQuality.POOR
        
        return signal, quality, score
    
    async def analyze_market(
        self, 
        market_data: MarketData, 
        klines: List[OHLCV],
        historical_funding: Optional[List[float]] = None
    ) -> TradingSetup:
        """
        Generate a complete trading setup analysis
        
        Process:
        1. Calculate technical indicators (if data available, else tbd)
        2. Analyze price action (PRIMARY signal)
        3. Check indicator confluence (SECONDARY signal)
        4. Analyze funding rate (TERTIARY consideration)
        5. Calculate risk/reward
        6. Generate final signal only if high probability
        """
        # Step 1: Calculate indicators
        indicators = self.calculate_technical_indicators(klines)
        
        # Step 2: Analyze price action (PRIMARY)
        price_action = self.analyze_price_action(klines, market_data)
        
        # Step 3: Check indicator confluence (SECONDARY)
        confluence = self.analyze_indicator_confluence(indicators, market_data, price_action)
        
        # Step 4: Analyze funding rate
        setup_type = price_action.get("setup_type") or ""
        setup_direction = "long" if setup_type.startswith("long") else \
                         "short" if setup_type.startswith("short") else "none"
        funding = self.analyze_funding_rate(market_data.funding_rate, setup_direction)
        
        # Step 5: Calculate risk/reward
        risk_reward = self.calculate_risk_reward(
            current_price=market_data.last_price,
            support=price_action.get("support"),
            resistance=price_action.get("resistance"),
            setup_type=price_action.get("setup_type"),
            atr=indicators.atr_14
        )
        
        # Step 6: Determine final signal
        signal, quality, score = self.determine_signal_and_quality(
            price_action, confluence, risk_reward
        )
        
        # Compile factors
        bullish_factors = []
        bearish_factors = []
        warnings = []
        
        # Price action signals
        for sig in price_action.get("signals", []):
            if "long" in sig.lower() or "support" in sig.lower() or "bullish" in sig.lower():
                bullish_factors.append(sig)
            elif "short" in sig.lower() or "resistance" in sig.lower() or "bearish" in sig.lower():
                bearish_factors.append(sig)
        
        # Confluence signals
        for sig in confluence.get("confirming_signals", []):
            if "long" in sig.lower() or "bullish" in sig.lower() or "oversold" in sig.lower():
                bullish_factors.append(sig)
            else:
                bearish_factors.append(sig)
        
        for sig in confluence.get("conflicting_signals", []):
            warnings.append(f"⚠️ {sig}")
        
        # Funding consideration
        if funding.is_favorable_long and setup_direction == "long":
            bullish_factors.append(f"Funding favorable for longs ({funding.current_rate*100:.4f}%)")
        elif funding.is_favorable_short and setup_direction == "short":
            bearish_factors.append(f"Funding favorable for shorts ({funding.current_rate*100:.4f}%)")
        elif setup_direction == "long" and not funding.is_favorable_long:
            warnings.append(f"⚠️ Paying funding to hold long ({funding.current_rate*100:.4f}%/hr)")
        elif setup_direction == "short" and not funding.is_favorable_short:
            warnings.append(f"⚠️ Paying funding to hold short ({funding.current_rate*100:.4f}%/hr)")
        
        # R:R warning
        if risk_reward.get("risk_reward_ratio") and risk_reward["risk_reward_ratio"] < 2:
            warnings.append(f"⚠️ R:R ratio below 2:1 ({risk_reward['risk_reward_ratio']:.2f})")
        
        # Volume warning
        if market_data.volume_24h < 100000:
            warnings.append("⚠️ Low 24h volume - may experience slippage")
        
        # Component scores (simplified)
        trend_score = 70 if price_action.get("is_actionable") else 40
        momentum_score = 70 if confluence.get("has_confluence") else 40
        funding_score = 70 if funding.rate_trend == "favorable" else 50
        liquidity_score = 70 if market_data.volume_24h > 500000 else 50
        volatility_score = 50  # Neutral by default
        
        return TradingSetup(
            symbol=market_data.symbol,
            timestamp=datetime.utcnow(),
            market_data=market_data,
            indicators=indicators,
            funding_analysis=funding,
            overall_score=score,
            setup_quality=quality,
            signal=signal,
            trend_score=trend_score,
            momentum_score=momentum_score,
            funding_score=funding_score,
            liquidity_score=liquidity_score,
            volatility_score=volatility_score,
            risk_level=risk_reward.get("position_risk", "tbd"),
            suggested_leverage=risk_reward.get("suggested_leverage", 1),
            suggested_stop_loss_percent=risk_reward.get("risk_percent") or 0,
            suggested_take_profit_percent=risk_reward.get("reward_percent") or 0,
            bullish_factors=bullish_factors,
            bearish_factors=bearish_factors,
            warnings=warnings,
            recommended_entry=risk_reward.get("entry"),
            recommended_stop_loss=risk_reward.get("stop_loss"),
            recommended_take_profit=risk_reward.get("take_profit")
        )


# Singleton instance
_analyzer: Optional[TradingAnalyzer] = None


def get_analyzer() -> TradingAnalyzer:
    """Get or create the analyzer instance"""
    global _analyzer
    if _analyzer is None:
        _analyzer = TradingAnalyzer()
    return _analyzer
