"""
Centralized configuration for Polymarket Tracker

All paths, URLs, and constants in one place.
Supports environment variables via .env file.
"""

import os
from pathlib import Path

# Try to load .env file if python-dotenv is available
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass  # dotenv not installed, use defaults


class Config:
    """Application configuration"""

    # Base paths
    BASE_DIR = Path(__file__).parent.parent.parent  # Project root
    DATA_DIR = BASE_DIR / "data"

    # API endpoints
    GAMMA_API = os.getenv("GAMMA_API", "https://gamma-api.polymarket.com")
    CLOB_API = os.getenv("CLOB_API", "https://clob.polymarket.com")
    LIMITLESS_API = os.getenv("LIMITLESS_API", "https://api.limitless.exchange")

    # Limitless config
    LIMITLESS_CATEGORY_ID = int(os.getenv("LIMITLESS_CATEGORY_ID", "43"))

    # Feature flags
    USE_API = os.getenv("USE_API", "true").lower() == "true"

    # File paths
    PORTFOLIO_PATH = BASE_DIR / "portfolio.json"
    LEADERBOARD_CSV = BASE_DIR / "Pre-TGE markets - Pre-TGE marketsFULL.csv"
    PROJECT_MAPPINGS = BASE_DIR / "project_mappings.json"
    DASHBOARD_OUTPUT = BASE_DIR / "dashboard.html"

    # API settings
    API_TIMEOUT = int(os.getenv("API_TIMEOUT", "30"))
    PRE_MARKET_TAG = "pre-market"
    PRE_MARKET_LIMIT = 200

    @classmethod
    def ensure_dirs(cls):
        """Create necessary directories if they don't exist"""
        cls.DATA_DIR.mkdir(parents=True, exist_ok=True)

    @classmethod
    def get_snapshot_path(cls, date_str: str) -> Path:
        """Get path for a daily snapshot file"""
        return cls.DATA_DIR / f"snapshot_{date_str}.json"

    @classmethod
    def as_dict(cls) -> dict:
        """Export config as dictionary (useful for debugging)"""
        return {
            "BASE_DIR": str(cls.BASE_DIR),
            "DATA_DIR": str(cls.DATA_DIR),
            "GAMMA_API": cls.GAMMA_API,
            "CLOB_API": cls.CLOB_API,
            "LIMITLESS_API": cls.LIMITLESS_API,
            "LIMITLESS_CATEGORY_ID": cls.LIMITLESS_CATEGORY_ID,
            "USE_API": cls.USE_API,
            "API_TIMEOUT": cls.API_TIMEOUT,
        }


# For backwards compatibility - can import these directly
GAMMA_API = Config.GAMMA_API
CLOB_API = Config.CLOB_API
LIMITLESS_API = Config.LIMITLESS_API
DATA_DIR = Config.DATA_DIR
