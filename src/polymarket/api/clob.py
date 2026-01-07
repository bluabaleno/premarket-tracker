"""
Polymarket CLOB (Central Limit Order Book) Client

Gets live prices from Polymarket's order book.
"""

import requests
from typing import Optional, Dict, Any, List
from ..config import Config
from ..utils.logging import get_logger

logger = get_logger(__name__)

# Try to import the CLOB client
try:
    from py_clob_client.client import ClobClient
    CLOB_AVAILABLE = True
except ImportError:
    CLOB_AVAILABLE = False
    logger.debug("py_clob_client not installed - CLOB features disabled")


class CLOBClient:
    """Client for Polymarket CLOB API"""

    def __init__(self, base_url: str = None):
        self.base_url = base_url or Config.CLOB_API
        self._client = None

        if CLOB_AVAILABLE:
            try:
                self._client = ClobClient(self.base_url)
            except Exception as e:
                logger.warning(f"Failed to initialize CLOB client: {e}")

    @property
    def available(self) -> bool:
        """Check if CLOB client is available"""
        return self._client is not None

    def get_midpoint(self, token_id: str) -> Optional[float]:
        """
        Get midpoint price for a token.

        Args:
            token_id: The CLOB token ID

        Returns:
            Midpoint price (0-1 scale) or None
        """
        if not self._client:
            return None

        try:
            mid = self._client.get_midpoint(token_id)
            return float(mid.get("mid", 0)) if mid else None
        except Exception as e:
            logger.debug(f"Failed to get midpoint for {token_id}: {e}")
            return None

    def get_price(self, token_id: str, side: str = "BUY") -> Optional[float]:
        """
        Get best price for a side.

        Args:
            token_id: The CLOB token ID
            side: "BUY" or "SELL"

        Returns:
            Best price or None
        """
        if not self._client:
            return None

        try:
            price = self._client.get_price(token_id, side=side)
            return float(price) if price else None
        except Exception as e:
            logger.debug(f"Failed to get {side} price for {token_id}: {e}")
            return None

    def get_live_prices(self, token_id: str) -> Optional[Dict[str, Any]]:
        """
        Get both midpoint and buy price.

        Args:
            token_id: The CLOB token ID

        Returns:
            Dictionary with midpoint and buy_price, or None
        """
        if not self._client:
            return None

        try:
            mid = self._client.get_midpoint(token_id)
            price = self._client.get_price(token_id, side="BUY")
            return {"midpoint": mid, "buy_price": price}
        except Exception as e:
            logger.debug(f"Failed to get prices for {token_id}: {e}")
            return None


# Module-level instance for convenience
_default_client: Optional[CLOBClient] = None


def get_clob_client() -> CLOBClient:
    """Get or create the default CLOB client"""
    global _default_client
    if _default_client is None:
        _default_client = CLOBClient()
    return _default_client


def get_live_price(token_id: str) -> Optional[float]:
    """
    Convenience function to get live midpoint price.

    Backwards compatible with old get_live_price() function.
    """
    client = get_clob_client()
    return client.get_midpoint(token_id)


def fetch_orderbook(token_id: str) -> Optional[Dict[str, Any]]:
    """
    Fetch full orderbook for a token using direct HTTP request.

    Args:
        token_id: The CLOB token ID (YES or NO token)

    Returns:
        Dictionary with 'bids' and 'asks' lists, each containing
        {'price': float, 'size': float} dicts, or None on error.
    """
    try:
        url = f"{Config.CLOB_API}/book"
        resp = requests.get(url, params={"token_id": token_id}, timeout=10)
        resp.raise_for_status()
        data = resp.json()

        # Normalize the response to our standard format
        # Size in orderbook is contracts, convert to USD: price × contracts
        bids = []
        asks = []

        for bid in data.get("bids", []):
            price = float(bid.get("price", 0))
            contracts = float(bid.get("size", 0))
            bids.append({
                "price": price,
                "size": price * contracts  # USD value
            })

        for ask in data.get("asks", []):
            price = float(ask.get("price", 0))
            contracts = float(ask.get("size", 0))
            asks.append({
                "price": price,
                "size": price * contracts  # USD value
            })

        return {"bids": bids, "asks": asks}
    except requests.RequestException as e:
        logger.debug(f"Failed to fetch orderbook for {token_id}: {e}")
        return None
