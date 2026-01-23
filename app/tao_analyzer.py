"""
TAO Subnet Analyzer

Analyzes Bittensor/TAO ecosystem data to generate:
1. Stake Recommendations - Best validators to stake with
2. Investment Scores - Best subnet tokens to invest in

Scoring Philosophy:
- Combine multiple metrics for robust signals
- Weight recent performance higher
- Consider both returns and risk factors
- Flag warnings for unusual conditions
"""
from datetime import datetime
from typing import List, Dict, Optional, Tuple
import logging

from app.tao_models import (
    SubnetData, SubnetPoolData, ValidatorData,
    StakeRecommendation, SubnetInvestmentScore,
    StakeSignal, InvestmentSignal, TAOMarketSummary
)

logger = logging.getLogger(__name__)

# Conversion factor for raw TAO values (9 decimal places)
TAO_DECIMALS = 1e9


class TaoAnalyzer:
    """
    Analyzer for TAO ecosystem stake and investment recommendations
    
    Scoring System:
    
    STAKE RECOMMENDATIONS (0-100):
    - APR Score (35%): Higher APR = better
    - APR Stability (20%): Consistent returns over 7d/30d
    - Take Rate (15%): Lower commission = more for nominators
    - Growth (15%): Positive stake/nominator growth
    - Trust (15%): Number of nominators (diversification)
    
    INVESTMENT SCORES (0-100):
    - Momentum (25%): Price changes 1d/7d
    - Flow (20%): Net TAO flow (positive = growth)
    - Emission (20%): Higher emission = more rewards
    - Liquidity (15%): Easier to trade
    - Sentiment (10%): Fear & Greed index
    - Network Health (10%): Active validators/miners
    """
    
    def __init__(self):
        pass
    
    # ==================== Stake Recommendations ====================
    
    def calculate_stake_score(self, validator: ValidatorData) -> Tuple[float, StakeSignal, List[str], List[str], List[str]]:
        """
        Calculate stake recommendation score for a validator
        
        Returns: (score, signal, bullish_factors, bearish_factors, warnings)
        """
        score = 50.0  # Start neutral
        bullish = []
        bearish = []
        warnings = []
        
        # 1. APR Score (35% weight) - Higher APR is better
        apr_score = 0
        if validator.apr > 0:
            # APR typically ranges from 5% to 25% annualized
            # Normalize to 0-100 scale
            apr_pct = validator.apr * 100  # Convert to percentage
            apr_score = min(100, (apr_pct / 25) * 100)  # Cap at 25% APR = 100
            
            if apr_pct >= 18:
                bullish.append(f"Excellent APR: {apr_pct:.2f}%")
            elif apr_pct >= 12:
                bullish.append(f"Good APR: {apr_pct:.2f}%")
            elif apr_pct < 8:
                bearish.append(f"Low APR: {apr_pct:.2f}%")
        else:
            bearish.append("No APR data available")
            warnings.append("⚠️ Missing APR data")
        
        # 2. APR Stability Score (20% weight)
        stability_score = 50  # Default neutral
        if validator.apr > 0 and validator.apr_7_day_average > 0:
            # Compare current APR to 7-day average
            apr_diff = abs(validator.apr - validator.apr_7_day_average) / validator.apr_7_day_average
            if apr_diff < 0.05:  # Less than 5% variance
                stability_score = 90
                bullish.append("Very stable APR (low variance)")
            elif apr_diff < 0.15:  # Less than 15% variance
                stability_score = 70
            elif apr_diff > 0.30:  # More than 30% variance
                stability_score = 30
                warnings.append("⚠️ High APR variance - returns may be inconsistent")
        
        # 3. Take Rate Score (15% weight) - Lower is better
        take_score = 50
        if validator.take is not None:
            take_pct = validator.take * 100
            if take_pct <= 9:
                take_score = 100
                bullish.append(f"Low commission: {take_pct:.1f}%")
            elif take_pct <= 12:
                take_score = 80
            elif take_pct <= 18:
                take_score = 50
            else:
                take_score = 20
                bearish.append(f"High commission: {take_pct:.1f}%")
        
        # 4. Growth Score (15% weight)
        growth_score = 50
        
        # Stake growth
        if validator.stake > 0 and validator.stake_24h_change != 0:
            stake_change_pct = (validator.stake_24h_change / validator.stake) * 100
            if stake_change_pct > 1:
                growth_score += 25
                bullish.append(f"Stake growing: +{stake_change_pct:.2f}% (24h)")
            elif stake_change_pct < -1:
                growth_score -= 25
                bearish.append(f"Stake declining: {stake_change_pct:.2f}% (24h)")
        
        # Nominator growth
        if validator.nominators_24h_change > 10:
            growth_score += 25
            bullish.append(f"Nominators increasing: +{validator.nominators_24h_change}")
        elif validator.nominators_24h_change < -10:
            growth_score -= 25
            bearish.append(f"Nominators decreasing: {validator.nominators_24h_change}")
        
        growth_score = max(0, min(100, growth_score))
        
        # 5. Trust Score (15% weight) - Based on nominator count
        trust_score = 50
        if validator.nominators >= 5000:
            trust_score = 100
            bullish.append(f"Highly trusted: {validator.nominators:,} nominators")
        elif validator.nominators >= 1000:
            trust_score = 80
            bullish.append(f"Well trusted: {validator.nominators:,} nominators")
        elif validator.nominators >= 200:
            trust_score = 60
        elif validator.nominators < 50:
            trust_score = 30
            warnings.append(f"⚠️ Low nominator count: {validator.nominators}")
        
        # Calculate weighted final score
        score = (
            apr_score * 0.35 +
            stability_score * 0.20 +
            take_score * 0.15 +
            growth_score * 0.15 +
            trust_score * 0.15
        )
        
        # Determine signal
        if score >= 75:
            signal = StakeSignal.STRONG_STAKE
        elif score >= 60:
            signal = StakeSignal.STAKE
        elif score >= 40:
            signal = StakeSignal.HOLD
        elif score >= 25:
            signal = StakeSignal.REDUCE
        else:
            signal = StakeSignal.AVOID
        
        # Add rank-based considerations
        if validator.rank <= 5:
            bullish.append(f"Top {validator.rank} validator by stake")
        elif validator.rank <= 20:
            bullish.append(f"Top 20 validator (rank #{validator.rank})")
        
        # Dominance warning
        if validator.dominance > 0.1:  # More than 10% dominance
            warnings.append(f"⚠️ High stake concentration: {validator.dominance*100:.1f}% of network")
        
        return score, signal, bullish, bearish, warnings
    
    def analyze_validators(self, validators: List[ValidatorData]) -> List[StakeRecommendation]:
        """
        Analyze all validators and generate stake recommendations
        """
        recommendations = []
        
        for validator in validators:
            try:
                score, signal, bullish, bearish, warnings = self.calculate_stake_score(validator)
                
                rec = StakeRecommendation(
                    validator_hotkey=validator.hotkey,
                    validator_name=validator.name,
                    validator_rank=validator.rank,
                    signal=signal,
                    score=round(score, 2),
                    apr=validator.apr,
                    apr_7_day_avg=validator.apr_7_day_average,
                    apr_30_day_avg=validator.apr_30_day_average,
                    take_rate=validator.take,
                    nominator_return_per_k=validator.nominator_return_per_k,
                    stake_24h_change=validator.stake_24h_change,
                    nominators_24h_change=validator.nominators_24h_change,
                    stake_concentration=validator.dominance,
                    nominator_count=validator.nominators,
                    bullish_factors=bullish,
                    bearish_factors=bearish,
                    warnings=warnings,
                )
                recommendations.append(rec)
                
            except Exception as e:
                logger.error(f"Error analyzing validator {validator.hotkey[:10]}...: {e}")
        
        # Sort by score (highest first)
        recommendations.sort(key=lambda x: x.score, reverse=True)
        
        return recommendations
    
    # ==================== Investment Scores ====================
    
    def calculate_investment_score(
        self, 
        subnet: SubnetData, 
        pool: SubnetPoolData
    ) -> Tuple[float, InvestmentSignal, Dict[str, float], List[str], List[str], List[str]]:
        """
        Calculate investment score for a subnet token
        
        Returns: (score, signal, component_scores, bullish_factors, bearish_factors, warnings)
        """
        bullish = []
        bearish = []
        warnings = []
        
        # Skip root subnet (netuid 0)
        if subnet.netuid == 0:
            return 50, InvestmentSignal.NEUTRAL, {}, [], [], ["Root subnet - not investable"]
        
        # 1. Momentum Score (25% weight) - Price changes
        momentum_score = 50
        
        if pool.price_change_1_day is not None:
            change_1d = pool.price_change_1_day * 100 if abs(pool.price_change_1_day) < 10 else pool.price_change_1_day
            if change_1d > 10:
                momentum_score += 30
                bullish.append(f"Strong 24h gain: +{change_1d:.1f}%")
            elif change_1d > 3:
                momentum_score += 15
                bullish.append(f"Positive 24h: +{change_1d:.1f}%")
            elif change_1d < -10:
                momentum_score -= 30
                bearish.append(f"Sharp 24h decline: {change_1d:.1f}%")
            elif change_1d < -3:
                momentum_score -= 15
                bearish.append(f"Negative 24h: {change_1d:.1f}%")
        
        if pool.price_change_1_week is not None:
            change_7d = pool.price_change_1_week * 100 if abs(pool.price_change_1_week) < 10 else pool.price_change_1_week
            if change_7d > 20:
                momentum_score += 20
                bullish.append(f"Strong 7d gain: +{change_7d:.1f}%")
            elif change_7d < -20:
                momentum_score -= 20
                bearish.append(f"Sharp 7d decline: {change_7d:.1f}%")
        
        momentum_score = max(0, min(100, momentum_score))
        
        # 2. Flow Score (20% weight) - Net TAO flow indicates interest
        flow_score = 50
        
        # Convert from raw to TAO (assuming 9 decimal places)
        net_flow_7d = subnet.net_flow_7_days / TAO_DECIMALS if subnet.net_flow_7_days != 0 else 0
        
        if net_flow_7d > 1000:  # More than 1000 TAO inflow
            flow_score = 90
            bullish.append(f"Strong TAO inflow: +{net_flow_7d:,.0f} TAO (7d)")
        elif net_flow_7d > 100:
            flow_score = 70
            bullish.append(f"Positive TAO flow: +{net_flow_7d:,.0f} TAO (7d)")
        elif net_flow_7d < -1000:
            flow_score = 20
            bearish.append(f"Heavy TAO outflow: {net_flow_7d:,.0f} TAO (7d)")
        elif net_flow_7d < -100:
            flow_score = 35
            bearish.append(f"Negative TAO flow: {net_flow_7d:,.0f} TAO (7d)")
        
        # 3. Emission Score (20% weight) - Higher emissions = more rewards
        emission_score = 50
        
        if subnet.emission > 0:
            emission_normalized = subnet.emission / TAO_DECIMALS
            
            # Top emitting subnets get highest scores
            if emission_normalized > 20:  # High emission
                emission_score = 90
                bullish.append(f"High emission rate: {emission_normalized:.2f}")
            elif emission_normalized > 10:
                emission_score = 75
                bullish.append(f"Good emission rate: {emission_normalized:.2f}")
            elif emission_normalized > 5:
                emission_score = 60
            elif emission_normalized < 1:
                emission_score = 30
                bearish.append("Low emission rate")
        
        # 4. Liquidity Score (15% weight) - Higher liquidity = easier to trade
        liquidity_score = 50
        
        liquidity_tao = pool.liquidity / TAO_DECIMALS if pool.liquidity > 0 else 0
        
        if liquidity_tao > 100000:  # 100K+ TAO liquidity
            liquidity_score = 100
            bullish.append(f"Excellent liquidity: {liquidity_tao:,.0f} TAO")
        elif liquidity_tao > 50000:
            liquidity_score = 80
            bullish.append(f"Good liquidity: {liquidity_tao:,.0f} TAO")
        elif liquidity_tao > 10000:
            liquidity_score = 60
        elif liquidity_tao < 1000:
            liquidity_score = 20
            warnings.append("⚠️ Low liquidity - may experience slippage")
        
        # 5. Sentiment Score (10% weight) - Fear & Greed index
        sentiment_score = 50
        
        if pool.fear_and_greed_index is not None:
            fng = pool.fear_and_greed_index
            if fng >= 70:  # Greed
                sentiment_score = 40  # Contrarian - might be overheated
                warnings.append(f"⚠️ High greed ({fng:.0f}) - potential overbought")
            elif fng >= 55:
                sentiment_score = 70
                bullish.append(f"Positive sentiment ({pool.fear_and_greed_sentiment})")
            elif fng <= 30:  # Fear
                sentiment_score = 70  # Contrarian - potential opportunity
                bullish.append(f"Fear sentiment ({fng:.0f}) - potential opportunity")
            elif fng <= 45:
                sentiment_score = 40
        
        # 6. Network Health Score (10% weight) - Active validators/miners
        health_score = 50
        
        total_active = subnet.active_validators + subnet.active_miners
        if total_active >= 100:
            health_score = 100
            bullish.append(f"Very active network: {total_active} participants")
        elif total_active >= 50:
            health_score = 80
            bullish.append(f"Active network: {total_active} participants")
        elif total_active >= 20:
            health_score = 60
        elif total_active < 5:
            health_score = 20
            warnings.append(f"⚠️ Low network activity: only {total_active} participants")
        
        # Calculate weighted final score
        overall_score = (
            momentum_score * 0.25 +
            flow_score * 0.20 +
            emission_score * 0.20 +
            liquidity_score * 0.15 +
            sentiment_score * 0.10 +
            health_score * 0.10
        )
        
        # Determine signal
        if overall_score >= 75:
            signal = InvestmentSignal.STRONG_BUY
        elif overall_score >= 60:
            signal = InvestmentSignal.BUY
        elif overall_score >= 40:
            signal = InvestmentSignal.NEUTRAL
        elif overall_score >= 25:
            signal = InvestmentSignal.SELL
        else:
            signal = InvestmentSignal.STRONG_SELL
        
        component_scores = {
            'momentum': momentum_score,
            'flow': flow_score,
            'emission': emission_score,
            'liquidity': liquidity_score,
            'sentiment': sentiment_score,
            'network_health': health_score,
        }
        
        return overall_score, signal, component_scores, bullish, bearish, warnings
    
    def analyze_subnets(
        self, 
        subnets: List[SubnetData], 
        pools: List[SubnetPoolData]
    ) -> List[SubnetInvestmentScore]:
        """
        Analyze all subnets and generate investment scores
        """
        # Create lookup for pools by netuid
        pool_lookup = {p.netuid: p for p in pools}
        
        scores = []
        
        for subnet in subnets:
            try:
                # Get corresponding pool data
                pool = pool_lookup.get(subnet.netuid)
                if not pool:
                    continue
                
                # Skip root subnet
                if subnet.netuid == 0:
                    continue
                
                overall_score, signal, components, bullish, bearish, warnings = \
                    self.calculate_investment_score(subnet, pool)
                
                investment_score = SubnetInvestmentScore(
                    netuid=subnet.netuid,
                    name=pool.name or subnet.name,
                    symbol=pool.symbol,
                    signal=signal,
                    overall_score=round(overall_score, 2),
                    momentum_score=round(components.get('momentum', 50), 2),
                    flow_score=round(components.get('flow', 50), 2),
                    emission_score=round(components.get('emission', 50), 2),
                    liquidity_score=round(components.get('liquidity', 50), 2),
                    sentiment_score=round(components.get('sentiment', 50), 2),
                    network_health_score=round(components.get('network_health', 50), 2),
                    market_cap=pool.market_cap / TAO_DECIMALS,
                    price=pool.price,
                    price_change_24h=pool.price_change_1_day,
                    price_change_7d=pool.price_change_1_week,
                    volume_24h=pool.tao_volume_24h / TAO_DECIMALS if pool.tao_volume_24h else 0,
                    emission=subnet.emission / TAO_DECIMALS if subnet.emission else 0,
                    net_flow_7d=subnet.net_flow_7_days / TAO_DECIMALS if subnet.net_flow_7_days else 0,
                    fear_and_greed_index=pool.fear_and_greed_index,
                    fear_and_greed_sentiment=pool.fear_and_greed_sentiment,
                    active_validators=subnet.active_validators,
                    active_miners=subnet.active_miners,
                    bullish_factors=bullish,
                    bearish_factors=bearish,
                    warnings=warnings,
                )
                scores.append(investment_score)
                
            except Exception as e:
                logger.error(f"Error analyzing subnet {subnet.netuid}: {e}")
        
        # Sort by score (highest first)
        scores.sort(key=lambda x: x.overall_score, reverse=True)
        
        return scores
    
    # ==================== Market Summary ====================
    
    def generate_subnet_summary(
        self,
        subnets: List[SubnetData],
        pools: List[SubnetPoolData],
        investment_scores: List[SubnetInvestmentScore]
    ) -> TAOMarketSummary:
        """
        Generate subnet-focused market summary
        """
        # Calculate totals
        total_market_cap = sum(p.market_cap for p in pools) / TAO_DECIMALS
        total_liquidity = sum(p.liquidity for p in pools) / TAO_DECIMALS
        
        # Top subnets by emission
        sorted_by_emission = sorted(subnets, key=lambda x: x.emission, reverse=True)
        top_emission = [
            {
                'netuid': s.netuid,
                'name': s.name,
                'emission': s.emission / TAO_DECIMALS
            }
            for s in sorted_by_emission[:5]
        ]
        
        # Top subnets by market cap
        sorted_by_mcap = sorted(pools, key=lambda x: x.market_cap, reverse=True)
        top_mcap = [
            {
                'netuid': p.netuid,
                'name': p.name,
                'symbol': p.symbol,
                'market_cap': p.market_cap / TAO_DECIMALS
            }
            for p in sorted_by_mcap[:5] if p.netuid != 0
        ]
        
        # Top subnets by flow
        sorted_by_flow = sorted(subnets, key=lambda x: x.net_flow_7_days, reverse=True)
        top_flow = [
            {
                'netuid': s.netuid,
                'name': s.name,
                'net_flow_7d': s.net_flow_7_days / TAO_DECIMALS
            }
            for s in sorted_by_flow[:5]
        ]
        
        # Calculate sentiment stats
        fng_values = [p.fear_and_greed_index for p in pools if p.fear_and_greed_index is not None]
        avg_fng = sum(fng_values) / len(fng_values) if fng_values else None
        
        # Count bullish/bearish/neutral subnets
        bullish = sum(1 for s in investment_scores if s.signal in [InvestmentSignal.STRONG_BUY, InvestmentSignal.BUY])
        bearish = sum(1 for s in investment_scores if s.signal in [InvestmentSignal.STRONG_SELL, InvestmentSignal.SELL])
        neutral = sum(1 for s in investment_scores if s.signal == InvestmentSignal.NEUTRAL)
        
        return TAOMarketSummary(
            total_subnets=len(subnets),
            total_validators=0,
            total_market_cap=total_market_cap,
            total_liquidity=total_liquidity,
            top_subnets_by_emission=top_emission,
            top_subnets_by_market_cap=top_mcap,
            top_subnets_by_flow=top_flow,
            best_stake_recommendations=[],
            best_investment_scores=investment_scores[:5],
            average_fear_greed=avg_fng,
            bullish_subnets=bullish,
            bearish_subnets=bearish,
            neutral_subnets=neutral,
        )


# Singleton instance
_analyzer: Optional[TaoAnalyzer] = None


def get_tao_analyzer() -> TaoAnalyzer:
    """Get or create the TAO analyzer instance"""
    global _analyzer
    if _analyzer is None:
        _analyzer = TaoAnalyzer()
    return _analyzer
