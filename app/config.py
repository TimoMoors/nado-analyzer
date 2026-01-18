"""
Configuration management for Nado Trading Setup Analyzer
"""
from pydantic_settings import BaseSettings
from functools import lru_cache


class Settings(BaseSettings):
    """Application settings loaded from environment variables"""
    
    # Nado API Configuration (Ink Mainnet)
    # Docs: https://docs.nado.xyz/developer-resources/api/endpoints
    nado_gateway_url: str = "https://gateway.prod.nado.xyz"
    nado_archive_url: str = "https://archive.prod.nado.xyz"
    
    # Data refresh interval in seconds
    data_refresh_interval: int = 60
    
    # Database
    database_url: str = "sqlite+aiosqlite:///./nado_data.db"
    
    # Server
    host: str = "0.0.0.0"
    port: int = 8000
    debug: bool = True
    
    # Trading Setup Thresholds
    rsi_oversold: float = 30.0
    rsi_overbought: float = 70.0
    funding_rate_high: float = 0.01  # 1%
    funding_rate_low: float = -0.01  # -1%
    min_volume_24h: float = 100000.0  # $100k
    max_spread_percent: float = 0.5  # 0.5%
    
    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"


@lru_cache()
def get_settings() -> Settings:
    """Get cached settings instance"""
    return Settings()

