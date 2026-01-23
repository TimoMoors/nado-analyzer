"""
TAO Stats API Client

Fetches data from taostats.io API for Bittensor ecosystem analysis.

API Documentation: https://docs.taostats.io/
"""
import httpx
import asyncio
from datetime import datetime, timedelta
from typing import Optional, List, Dict, Any
import logging

from app.config import get_settings
from app.tao_models import (
    SubnetData, SubnetPoolData, ValidatorData, MetagraphEntry
)

logger = logging.getLogger(__name__)

# Taostats API base URL
TAOSTATS_API_URL = "https://api.taostats.io"


class TaoStatsClient:
    """
    Client for interacting with Taostats API
    
    Endpoints used:
    - /api/subnet/latest/v1 - Subnet network metrics
    - /api/dtao/pool/latest/v1 - Subnet token market data
    - /api/validator/latest/v1 - Top validators
    - /api/metagraph/latest/v1 - Miners/validators per subnet
    - /api/subnet/history/v1 - Historical subnet data
    """
    
    def __init__(self, api_key: str):
        self.api_key = api_key
        self._client: Optional[httpx.AsyncClient] = None
        
        # Cache
        self._subnets_cache: Optional[List[SubnetData]] = None
        self._pools_cache: Optional[List[SubnetPoolData]] = None
        self._validators_cache: Optional[List[ValidatorData]] = None
        self._cache_time: Optional[datetime] = None
        self._cache_ttl = 60  # Cache for 60 seconds
    
    @property
    def headers(self) -> Dict[str, str]:
        return {
            'Authorization': self.api_key,
            'Accept': 'application/json',
            'Content-Type': 'application/json',
        }
    
    async def __aenter__(self):
        self._client = httpx.AsyncClient(timeout=60.0)
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        if self._client:
            await self._client.aclose()
    
    @property
    def client(self) -> httpx.AsyncClient:
        if self._client is None:
            self._client = httpx.AsyncClient(timeout=60.0)
        return self._client
    
    async def close(self):
        """Close the HTTP client"""
        if self._client:
            await self._client.aclose()
            self._client = None
    
    def _is_cache_valid(self) -> bool:
        """Check if cache is still valid"""
        if self._cache_time is None:
            return False
        return (datetime.utcnow() - self._cache_time).total_seconds() < self._cache_ttl
    
    # ==================== Subnet Data ====================
    
    async def get_subnets(self, use_cache: bool = True) -> List[SubnetData]:
        """
        Get all subnet data
        
        Endpoint: GET /api/subnet/latest/v1
        """
        if use_cache and self._is_cache_valid() and self._subnets_cache:
            return self._subnets_cache
        
        try:
            response = await self.client.get(
                f"{TAOSTATS_API_URL}/api/subnet/latest/v1",
                headers=self.headers
            )
            response.raise_for_status()
            data = response.json()
            
            subnets = []
            for item in data.get('data', []):
                try:
                    subnet = SubnetData(
                        netuid=item.get('netuid', 0),
                        name=item.get('name'),
                        emission=float(item.get('emission', 0) or 0),
                        projected_emission=float(item.get('projected_emission', 0) or 0),
                        validators=item.get('validators', 0) or 0,
                        active_validators=item.get('active_validators', 0) or 0,
                        active_miners=item.get('active_miners', 0) or 0,
                        max_neurons=item.get('max_neurons', 0) or 0,
                        active_keys=item.get('active_keys', 0) or 0,
                        registration_cost=float(item.get('registration_cost', 0) or 0),
                        neuron_registration_cost=float(item.get('neuron_registration_cost', 0) or 0),
                        registration_allowed=item.get('registration_allowed', True),
                        tao_flow=float(item.get('tao_flow', 0) or 0),
                        net_flow_1_day=float(item.get('net_flow_1_day', 0) or 0),
                        net_flow_7_days=float(item.get('net_flow_7_days', 0) or 0),
                        net_flow_30_days=float(item.get('net_flow_30_days', 0) or 0),
                        tempo=item.get('tempo', 0) or 0,
                        immunity_period=item.get('immunity_period', 0) or 0,
                        owner_address=item.get('owner', {}).get('ss58') if item.get('owner') else None,
                    )
                    subnets.append(subnet)
                except Exception as e:
                    logger.warning(f"Error parsing subnet {item.get('netuid')}: {e}")
            
            self._subnets_cache = subnets
            self._cache_time = datetime.utcnow()
            
            logger.info(f"Fetched {len(subnets)} subnets from Taostats API")
            return subnets
            
        except httpx.HTTPStatusError as e:
            if e.response.status_code == 429:
                logger.warning("Rate limited by Taostats API, using cache if available")
                if self._subnets_cache:
                    return self._subnets_cache
            logger.error(f"HTTP error fetching subnets: {e}")
            raise
        except Exception as e:
            logger.error(f"Error fetching subnets: {e}")
            raise
    
    # ==================== Pool/Market Data ====================
    
    async def get_subnet_pools(self, use_cache: bool = True) -> List[SubnetPoolData]:
        """
        Get subnet token pool/market data
        
        Endpoint: GET /api/dtao/pool/latest/v1
        """
        if use_cache and self._is_cache_valid() and self._pools_cache:
            return self._pools_cache
        
        try:
            response = await self.client.get(
                f"{TAOSTATS_API_URL}/api/dtao/pool/latest/v1",
                headers=self.headers
            )
            response.raise_for_status()
            data = response.json()
            
            pools = []
            for item in data.get('data', []):
                try:
                    pool = SubnetPoolData(
                        netuid=item.get('netuid', 0),
                        name=item.get('name'),
                        symbol=item.get('symbol'),
                        market_cap=float(item.get('market_cap', 0) or 0),
                        liquidity=float(item.get('liquidity', 0) or 0),
                        price=float(item.get('price', 0) or 0),
                        price_change_1_hour=_safe_float(item.get('price_change_1_hour')),
                        price_change_1_day=_safe_float(item.get('price_change_1_day')),
                        price_change_1_week=_safe_float(item.get('price_change_1_week')),
                        price_change_1_month=_safe_float(item.get('price_change_1_month')),
                        market_cap_change_1_day=_safe_float(item.get('market_cap_change_1_day')),
                        tao_volume_24h=float(item.get('tao_volume_24_hr', 0) or 0),
                        tao_buy_volume_24h=float(item.get('tao_buy_volume_24_hr', 0) or 0),
                        tao_sell_volume_24h=float(item.get('tao_sell_volume_24_hr', 0) or 0),
                        buys_24h=item.get('buys_24_hr', 0) or 0,
                        sells_24h=item.get('sells_24_hr', 0) or 0,
                        buyers_24h=item.get('buyers_24_hr', 0) or 0,
                        sellers_24h=item.get('sellers_24_hr', 0) or 0,
                        fear_and_greed_index=_safe_float(item.get('fear_and_greed_index')),
                        fear_and_greed_sentiment=item.get('fear_and_greed_sentiment'),
                        total_tao=float(item.get('total_tao', 0) or 0),
                        total_alpha=float(item.get('total_alpha', 0) or 0),
                        alpha_staked=float(item.get('alpha_staked', 0) or 0),
                        highest_price_24h=_safe_float(item.get('highest_price_24_hr')),
                        lowest_price_24h=_safe_float(item.get('lowest_price_24_hr')),
                    )
                    pools.append(pool)
                except Exception as e:
                    logger.warning(f"Error parsing pool {item.get('netuid')}: {e}")
            
            self._pools_cache = pools
            if not self._cache_time:
                self._cache_time = datetime.utcnow()
            
            logger.info(f"Fetched {len(pools)} subnet pools from Taostats API")
            return pools
            
        except httpx.HTTPStatusError as e:
            if e.response.status_code == 429:
                logger.warning("Rate limited, using cache if available")
                if self._pools_cache:
                    return self._pools_cache
            logger.error(f"HTTP error fetching pools: {e}")
            raise
        except Exception as e:
            logger.error(f"Error fetching pools: {e}")
            raise
    
    # ==================== Validator Data ====================
    
    async def get_validators(self, use_cache: bool = True) -> List[ValidatorData]:
        """
        Get top validator data
        
        Endpoint: GET /api/validator/latest/v1
        """
        if use_cache and self._is_cache_valid() and self._validators_cache:
            return self._validators_cache
        
        try:
            response = await self.client.get(
                f"{TAOSTATS_API_URL}/api/validator/latest/v1",
                headers=self.headers
            )
            response.raise_for_status()
            data = response.json()
            
            validators = []
            for item in data.get('data', []):
                try:
                    validator = ValidatorData(
                        hotkey=item.get('hotkey', {}).get('ss58', '') if isinstance(item.get('hotkey'), dict) else str(item.get('hotkey', '')),
                        coldkey=item.get('coldkey', {}).get('ss58') if isinstance(item.get('coldkey'), dict) else None,
                        name=item.get('name'),
                        rank=item.get('rank', 0) or 0,
                        stake=float(item.get('stake', 0) or 0),
                        stake_24h_change=float(item.get('stake_24_hr_change', 0) or 0),
                        system_stake=float(item.get('system_stake', 0) or 0),
                        validator_stake=float(item.get('validator_stake', 0) or 0),
                        dominance=float(item.get('dominance', 0) or 0),
                        nominators=item.get('nominators', 0) or 0,
                        nominators_24h_change=item.get('nominators_24_hr_change', 0) or 0,
                        apr=float(item.get('apr', 0) or 0),
                        apr_7_day_average=float(item.get('apr_7_day_average', 0) or 0),
                        apr_30_day_average=float(item.get('apr_30_day_average', 0) or 0),
                        total_daily_return=float(item.get('total_daily_return', 0) or 0),
                        validator_return=float(item.get('validator_return', 0) or 0),
                        nominator_return_per_k=float(item.get('nominator_return_per_k', 0) or 0),
                        nominator_return_per_k_7_day_avg=float(item.get('nominator_return_per_k_7_day_average', 0) or 0),
                        nominator_return_per_k_30_day_avg=float(item.get('nominator_return_per_k_30_day_average', 0) or 0),
                        take=float(item.get('take', 0) or 0),
                        pending_emission=float(item.get('pending_emission', 0) or 0),
                        registrations=item.get('registrations', []) or [],
                        permits=item.get('permits', []) or [],
                    )
                    validators.append(validator)
                except Exception as e:
                    logger.warning(f"Error parsing validator: {e}")
            
            self._validators_cache = validators
            if not self._cache_time:
                self._cache_time = datetime.utcnow()
            
            logger.info(f"Fetched {len(validators)} validators from Taostats API")
            return validators
            
        except httpx.HTTPStatusError as e:
            if e.response.status_code == 429:
                logger.warning("Rate limited, using cache if available")
                if self._validators_cache:
                    return self._validators_cache
            logger.error(f"HTTP error fetching validators: {e}")
            raise
        except Exception as e:
            logger.error(f"Error fetching validators: {e}")
            raise
    
    # ==================== Metagraph Data ====================
    
    async def get_metagraph(self, netuid: Optional[int] = None) -> List[MetagraphEntry]:
        """
        Get metagraph data (miners/validators per subnet)
        
        Endpoint: GET /api/metagraph/latest/v1
        
        Args:
            netuid: Optional - filter by specific subnet
        """
        try:
            params = {}
            if netuid is not None:
                params['netuid'] = netuid
            
            response = await self.client.get(
                f"{TAOSTATS_API_URL}/api/metagraph/latest/v1",
                headers=self.headers,
                params=params
            )
            response.raise_for_status()
            data = response.json()
            
            entries = []
            for item in data.get('data', []):
                try:
                    entry = MetagraphEntry(
                        netuid=item.get('netuid', 0),
                        uid=item.get('uid', 0),
                        hotkey=item.get('hotkey', {}).get('ss58', '') if isinstance(item.get('hotkey'), dict) else str(item.get('hotkey', '')),
                        coldkey=item.get('coldkey', {}).get('ss58') if isinstance(item.get('coldkey'), dict) else None,
                        stake=float(item.get('stake', 0) or 0),
                        trust=float(item.get('trust', 0) or 0),
                        validator_trust=float(item.get('validator_trust', 0) or 0),
                        consensus=float(item.get('consensus', 0) or 0),
                        incentive=float(item.get('incentive', 0) or 0),
                        dividends=float(item.get('dividends', 0) or 0),
                        emission=float(item.get('emission', 0) or 0),
                        daily_reward=float(item.get('daily_reward', 0) or 0),
                        daily_mining_tao=float(item.get('daily_mining_tao', 0) or 0),
                        daily_validating_tao=float(item.get('daily_validating_tao', 0) or 0),
                        daily_total_rewards_as_tao=float(item.get('daily_total_rewards_as_tao', 0) or 0),
                        active=item.get('active', True),
                        validator_permit=item.get('validator_permit', False),
                        is_immunity_period=item.get('is_immunity_period', False),
                        rank=item.get('rank', 0) or 0,
                    )
                    entries.append(entry)
                except Exception as e:
                    logger.warning(f"Error parsing metagraph entry: {e}")
            
            logger.info(f"Fetched {len(entries)} metagraph entries")
            return entries
            
        except httpx.HTTPStatusError as e:
            logger.error(f"HTTP error fetching metagraph: {e}")
            raise
        except Exception as e:
            logger.error(f"Error fetching metagraph: {e}")
            raise
    
    # ==================== Historical Data ====================
    
    async def get_subnet_history(self, netuid: int, limit: int = 50) -> List[Dict[str, Any]]:
        """
        Get historical data for a specific subnet
        
        Endpoint: GET /api/subnet/history/v1
        """
        try:
            response = await self.client.get(
                f"{TAOSTATS_API_URL}/api/subnet/history/v1",
                headers=self.headers,
                params={'netuid': netuid, 'limit': limit}
            )
            response.raise_for_status()
            data = response.json()
            
            return data.get('data', [])
            
        except Exception as e:
            logger.error(f"Error fetching subnet history for {netuid}: {e}")
            return []
    
    # ==================== Combined Data Fetch ====================
    
    async def get_all_data(self) -> Dict[str, Any]:
        """
        Fetch all data needed for analysis
        
        Returns dict with subnets, pools, and validators
        """
        try:
            # Fetch all data (with small delays to avoid rate limiting)
            subnets = await self.get_subnets()
            await asyncio.sleep(0.5)
            
            pools = await self.get_subnet_pools()
            await asyncio.sleep(0.5)
            
            validators = await self.get_validators()
            
            return {
                'subnets': subnets,
                'pools': pools,
                'validators': validators,
                'timestamp': datetime.utcnow()
            }
            
        except Exception as e:
            logger.error(f"Error fetching all data: {e}")
            raise


def _safe_float(value: Any) -> Optional[float]:
    """Safely convert value to float, return None if not possible"""
    if value is None:
        return None
    try:
        return float(value)
    except (ValueError, TypeError):
        return None


# Singleton instance
_client: Optional[TaoStatsClient] = None


async def get_tao_client() -> TaoStatsClient:
    """Get or create the TAO client instance"""
    global _client
    if _client is None:
        settings = get_settings()
        api_key = getattr(settings, 'taostats_api_key', None)
        if not api_key:
            raise ValueError("TAOSTATS_API_KEY not configured")
        _client = TaoStatsClient(api_key)
    return _client
