"""
TAO Signal History Tracker

Records investment signals and tracks their outcomes over time.
This creates transparency and trust by showing historical accuracy.
"""
import json
import logging
from datetime import datetime, timedelta
from typing import List, Optional, Dict, Any
from sqlalchemy import desc
from sqlalchemy.orm import Session

from app.database import TaoSignalHistory, get_session
from app.tao_models import SubnetInvestmentScore, InvestmentSignal

logger = logging.getLogger(__name__)

# Only record signals that change or every N hours for same signal
SIGNAL_RECORDING_INTERVAL_HOURS = 6


class TaoSignalTracker:
    """Tracks and records TAO subnet investment signals"""
    
    def record_signals(self, investment_scores: List[SubnetInvestmentScore]) -> int:
        """
        Record current investment signals to database
        
        Only records if:
        - Signal has changed from last recorded signal
        - Or enough time has passed since last recording
        
        Returns number of signals recorded.
        """
        if not investment_scores:
            return 0
        
        session = get_session()
        recorded_count = 0
        
        try:
            for score in investment_scores:
                # Skip subnets without price data
                if score.price is None or score.price == 0:
                    continue
                
                # Check last recorded signal for this subnet
                last_signal = session.query(TaoSignalHistory).filter(
                    TaoSignalHistory.netuid == score.netuid
                ).order_by(desc(TaoSignalHistory.timestamp)).first()
                
                should_record = False
                
                if last_signal is None:
                    # First time seeing this subnet
                    should_record = True
                elif last_signal.signal != score.signal.value:
                    # Signal changed
                    should_record = True
                elif datetime.utcnow() - last_signal.timestamp > timedelta(hours=SIGNAL_RECORDING_INTERVAL_HOURS):
                    # Enough time passed, record again
                    should_record = True
                
                if should_record:
                    # Create factors JSON
                    factors = {
                        'bullish': score.bullish_factors[:5] if score.bullish_factors else [],
                        'bearish': score.bearish_factors[:5] if score.bearish_factors else [],
                        'warnings': score.warnings[:3] if score.warnings else []
                    }
                    
                    signal_record = TaoSignalHistory(
                        netuid=score.netuid,
                        name=score.name,
                        symbol=score.symbol,
                        signal=score.signal.value,
                        score=score.overall_score,
                        momentum_score=score.momentum_score,
                        flow_score=score.flow_score,
                        emission_score=score.emission_score,
                        liquidity_score=score.liquidity_score,
                        price_at_signal=score.price,
                        market_cap_at_signal=score.market_cap,
                        factors=json.dumps(factors),
                        timestamp=datetime.utcnow()
                    )
                    
                    session.add(signal_record)
                    recorded_count += 1
            
            session.commit()
            
            if recorded_count > 0:
                logger.info(f"Recorded {recorded_count} TAO signals")
            
        except Exception as e:
            session.rollback()
            logger.error(f"Error recording signals: {e}")
        finally:
            session.close()
        
        return recorded_count
    
    def update_outcomes(self, current_prices: Dict[int, float]) -> int:
        """
        Update outcome prices for signals that need it
        
        - Updates 24h outcome for signals ~24h old
        - Updates 7d outcome for signals ~7d old
        
        Returns number of outcomes updated.
        """
        session = get_session()
        updated_count = 0
        
        try:
            now = datetime.utcnow()
            
            # Find signals needing 24h update (22-26 hours old, not yet updated)
            signals_24h = session.query(TaoSignalHistory).filter(
                TaoSignalHistory.timestamp <= now - timedelta(hours=22),
                TaoSignalHistory.timestamp >= now - timedelta(hours=26),
                TaoSignalHistory.price_after_24h.is_(None)
            ).all()
            
            for signal in signals_24h:
                if signal.netuid in current_prices and signal.price_at_signal:
                    current_price = current_prices[signal.netuid]
                    signal.price_after_24h = current_price
                    signal.return_24h = ((current_price - signal.price_at_signal) / signal.price_at_signal) * 100
                    signal.outcome_updated_at = now
                    updated_count += 1
            
            # Find signals needing 7d update (6.5-7.5 days old, not yet updated)
            signals_7d = session.query(TaoSignalHistory).filter(
                TaoSignalHistory.timestamp <= now - timedelta(days=6, hours=12),
                TaoSignalHistory.timestamp >= now - timedelta(days=7, hours=12),
                TaoSignalHistory.price_after_7d.is_(None)
            ).all()
            
            for signal in signals_7d:
                if signal.netuid in current_prices and signal.price_at_signal:
                    current_price = current_prices[signal.netuid]
                    signal.price_after_7d = current_price
                    signal.return_7d = ((current_price - signal.price_at_signal) / signal.price_at_signal) * 100
                    signal.outcome_updated_at = now
                    updated_count += 1
            
            session.commit()
            
            if updated_count > 0:
                logger.info(f"Updated {updated_count} signal outcomes")
            
        except Exception as e:
            session.rollback()
            logger.error(f"Error updating outcomes: {e}")
        finally:
            session.close()
        
        return updated_count
    
    def get_signal_history(
        self,
        netuid: Optional[int] = None,
        signal_filter: Optional[str] = None,
        limit: int = 100
    ) -> List[Dict[str, Any]]:
        """
        Get historical signals with outcomes
        
        Args:
            netuid: Filter by specific subnet
            signal_filter: Filter by signal type (e.g., "strong_buy")
            limit: Maximum records to return
        
        Returns list of signal records with outcomes.
        """
        session = get_session()
        
        try:
            query = session.query(TaoSignalHistory).order_by(desc(TaoSignalHistory.timestamp))
            
            if netuid is not None:
                query = query.filter(TaoSignalHistory.netuid == netuid)
            
            if signal_filter:
                query = query.filter(TaoSignalHistory.signal == signal_filter)
            
            signals = query.limit(limit).all()
            
            results = []
            for s in signals:
                factors = json.loads(s.factors) if s.factors else {}
                
                results.append({
                    'id': s.id,
                    'netuid': s.netuid,
                    'name': s.name,
                    'symbol': s.symbol,
                    'signal': s.signal,
                    'score': s.score,
                    'momentum_score': s.momentum_score,
                    'flow_score': s.flow_score,
                    'emission_score': s.emission_score,
                    'liquidity_score': s.liquidity_score,
                    'price_at_signal': s.price_at_signal,
                    'market_cap_at_signal': s.market_cap_at_signal,
                    'bullish_factors': factors.get('bullish', []),
                    'bearish_factors': factors.get('bearish', []),
                    'warnings': factors.get('warnings', []),
                    'timestamp': s.timestamp.isoformat(),
                    'price_after_24h': s.price_after_24h,
                    'price_after_7d': s.price_after_7d,
                    'return_24h': s.return_24h,
                    'return_7d': s.return_7d,
                    'outcome_status': self._get_outcome_status(s)
                })
            
            return results
            
        finally:
            session.close()
    
    def _get_outcome_status(self, signal: TaoSignalHistory) -> str:
        """Determine the outcome status of a signal"""
        now = datetime.utcnow()
        age = now - signal.timestamp
        
        if signal.return_7d is not None:
            return 'complete'
        elif signal.return_24h is not None:
            return 'partial'  # Has 24h, waiting for 7d
        elif age < timedelta(hours=24):
            return 'pending'  # Too new
        else:
            return 'awaiting_update'  # Needs outcome update
    
    def get_performance_stats(self, days: int = 30) -> Dict[str, Any]:
        """
        Calculate signal performance statistics
        
        Returns accuracy metrics for buy/sell signals.
        """
        session = get_session()
        
        try:
            cutoff = datetime.utcnow() - timedelta(days=days)
            
            # Get signals with 24h outcomes
            signals = session.query(TaoSignalHistory).filter(
                TaoSignalHistory.timestamp >= cutoff,
                TaoSignalHistory.return_24h.isnot(None)
            ).all()
            
            if not signals:
                return {
                    'period_days': days,
                    'total_signals': 0,
                    'message': 'No signals with outcomes yet'
                }
            
            # Categorize by signal type
            stats = {
                'strong_buy': {'count': 0, 'wins_24h': 0, 'wins_7d': 0, 'total_return_24h': 0, 'total_return_7d': 0},
                'buy': {'count': 0, 'wins_24h': 0, 'wins_7d': 0, 'total_return_24h': 0, 'total_return_7d': 0},
                'neutral': {'count': 0, 'wins_24h': 0, 'wins_7d': 0, 'total_return_24h': 0, 'total_return_7d': 0},
                'sell': {'count': 0, 'wins_24h': 0, 'wins_7d': 0, 'total_return_24h': 0, 'total_return_7d': 0},
                'strong_sell': {'count': 0, 'wins_24h': 0, 'wins_7d': 0, 'total_return_24h': 0, 'total_return_7d': 0},
            }
            
            for s in signals:
                if s.signal not in stats:
                    continue
                
                stats[s.signal]['count'] += 1
                
                # For buy signals, positive return is a win
                # For sell signals, negative return is a win (correctly predicted decline)
                is_buy_signal = s.signal in ['strong_buy', 'buy']
                
                if s.return_24h is not None:
                    stats[s.signal]['total_return_24h'] += s.return_24h
                    if is_buy_signal and s.return_24h > 0:
                        stats[s.signal]['wins_24h'] += 1
                    elif not is_buy_signal and s.return_24h < 0:
                        stats[s.signal]['wins_24h'] += 1
                
                if s.return_7d is not None:
                    stats[s.signal]['total_return_7d'] += s.return_7d
                    if is_buy_signal and s.return_7d > 0:
                        stats[s.signal]['wins_7d'] += 1
                    elif not is_buy_signal and s.return_7d < 0:
                        stats[s.signal]['wins_7d'] += 1
            
            # Calculate percentages
            result = {
                'period_days': days,
                'total_signals': len(signals),
                'by_signal': {}
            }
            
            for signal_type, data in stats.items():
                if data['count'] > 0:
                    result['by_signal'][signal_type] = {
                        'count': data['count'],
                        'accuracy_24h': round((data['wins_24h'] / data['count']) * 100, 1) if data['count'] > 0 else 0,
                        'accuracy_7d': round((data['wins_7d'] / data['count']) * 100, 1) if data['count'] > 0 else 0,
                        'avg_return_24h': round(data['total_return_24h'] / data['count'], 2) if data['count'] > 0 else 0,
                        'avg_return_7d': round(data['total_return_7d'] / data['count'], 2) if data['count'] > 0 else 0,
                    }
            
            # Overall buy signal performance
            buy_signals = [s for s in signals if s.signal in ['strong_buy', 'buy']]
            if buy_signals:
                buy_wins = sum(1 for s in buy_signals if s.return_24h and s.return_24h > 0)
                result['buy_accuracy_24h'] = round((buy_wins / len(buy_signals)) * 100, 1)
                result['buy_avg_return_24h'] = round(sum(s.return_24h or 0 for s in buy_signals) / len(buy_signals), 2)
            
            return result
            
        finally:
            session.close()


# Singleton instance
_tracker: Optional[TaoSignalTracker] = None


def get_signal_tracker() -> TaoSignalTracker:
    """Get the signal tracker singleton"""
    global _tracker
    if _tracker is None:
        _tracker = TaoSignalTracker()
    return _tracker
