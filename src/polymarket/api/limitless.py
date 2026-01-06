"""
Limitless Exchange API Client

Fetches Pre-TGE market data from Limitless Exchange.
"""

import requests
from typing import Dict, List, Any, Optional
from ..config import Config
from ..utils.logging import get_logger
from ..utils.parsers import extract_project_name

logger = get_logger(__name__)


class LimitlessClient:
    """Client for Limitless Exchange API"""

    def __init__(self, base_url: str = None, timeout: int = None):
        self.base_url = base_url or Config.LIMITLESS_API
        self.timeout = timeout or Config.API_TIMEOUT
        self.category_id = Config.LIMITLESS_CATEGORY_ID

    def fetch_active_markets(self, category_id: int = None) -> List[Dict[str, Any]]:
        """
        Fetch active markets for a category (with pagination).

        Args:
            category_id: Category ID (default: Pre-TGE category)

        Returns:
            List of market dictionaries
        """
        cat_id = category_id or self.category_id
        all_markets = []
        page = 1
        limit = 24

        try:
            while True:
                url = f"{self.base_url}/markets/active/{cat_id}"
                params = {"page": page, "limit": limit, "sortBy": "trending"}
                resp = requests.get(url, params=params, timeout=self.timeout)
                resp.raise_for_status()
                data = resp.json()
                markets = data.get("data", [])

                if not markets:
                    break

                all_markets.extend(markets)
                page += 1

                if page > 20:  # Safety limit
                    break

            logger.info(f"Fetched {len(all_markets)} markets from Limitless ({page-1} pages)")
            return all_markets
        except requests.RequestException as e:
            logger.warning(f"Limitless API error: {e}")
            return all_markets  # Return what we got so far

    def fetch_markets(self) -> Dict[str, Any]:
        """
        Fetch Pre-TGE markets and normalize to our data structure.

        Returns:
            Dictionary with source, projects, and optional error
        """
        result = {
            "source": "limitless",
            "timestamp": None,
            "projects": {},
            "error": None,
        }

        try:
            markets = self.fetch_active_markets()

            for market in markets:
                title = market.get("title", "Unknown")
                market_id = market.get("id")
                prices = market.get("prices", [])
                volume_raw = market.get("volume", "0")
                slug = market.get("slug", "")

                # Get token decimals (default to 6 for USDC)
                decimals = market.get("collateralToken", {}).get("decimals", 6)
                volume = float(volume_raw) / (10 ** decimals) if volume_raw else 0

                # Extract project name from title
                project_name = extract_project_name(title, remove_emoji=True)

                if project_name not in result["projects"]:
                    result["projects"][project_name] = {
                        "name": project_name,
                        "markets": [],
                        "totalVolume": 0,
                    }

                # Normalize price to 0-1 scale
                raw_yes = prices[0] if prices else 0
                yes_price = raw_yes / 100 if raw_yes > 1 else raw_yes

                result["projects"][project_name]["markets"].append({
                    "id": market_id,
                    "title": title,
                    "slug": slug,
                    "yes_price": yes_price,
                    "volume": volume,
                })
                result["projects"][project_name]["totalVolume"] += volume

            logger.info(f"Processed {len(result['projects'])} Limitless projects")

        except Exception as e:
            logger.warning(f"Limitless parsing error: {e}")
            result["error"] = str(e)

        return result


# Backwards compatibility - function that matches old limitless_client.py
def fetch_limitless_markets() -> Dict[str, Any]:
    """
    Fetch Pre-TGE markets from Limitless Exchange.

    This function provides backwards compatibility with the old API.
    """
    client = LimitlessClient()
    return client.fetch_markets()
