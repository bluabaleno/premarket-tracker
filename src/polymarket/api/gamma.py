"""
Polymarket Gamma API Client

Fetches market data from Polymarket's Gamma API.
"""

import json
import requests
from typing import Dict, List, Optional, Any
from ..config import Config
from ..utils.logging import get_logger

logger = get_logger(__name__)


class GammaClient:
    """Client for Polymarket Gamma API"""

    def __init__(self, base_url: str = None, timeout: int = None):
        self.base_url = base_url or Config.GAMMA_API
        self.timeout = timeout or Config.API_TIMEOUT

    def fetch_events(
        self,
        tag_slug: str = None,
        limit: int = None,
        order: str = "volume",
        ascending: bool = False,
    ) -> List[Dict[str, Any]]:
        """
        Fetch events from Gamma API.

        Args:
            tag_slug: Filter by tag (e.g., "pre-market")
            limit: Max number of events
            order: Sort field
            ascending: Sort direction

        Returns:
            List of event dictionaries
        """
        params = {
            "tag_slug": tag_slug or Config.PRE_MARKET_TAG,
            "limit": limit or Config.PRE_MARKET_LIMIT,
            "order": order,
            "ascending": str(ascending).lower(),
        }

        try:
            resp = requests.get(
                f"{self.base_url}/events",
                params=params,
                timeout=self.timeout,
            )
            resp.raise_for_status()
            events = resp.json()
            logger.info(f"Fetched {len(events)} events from Gamma API")
            return events
        except requests.Timeout:
            logger.error("Gamma API timeout")
            return []
        except requests.RequestException as e:
            logger.error(f"Gamma API error: {e}")
            return []

    def fetch_event_by_slug(self, slug: str) -> Optional[Dict[str, Any]]:
        """
        Fetch a single event by slug.

        Args:
            slug: Event slug

        Returns:
            Event dictionary or None
        """
        try:
            resp = requests.get(
                f"{self.base_url}/events",
                params={"slug": slug},
                timeout=self.timeout,
            )
            resp.raise_for_status()
            data = resp.json()
            return data[0] if data else None
        except requests.RequestException as e:
            logger.error(f"Failed to fetch event {slug}: {e}")
            return None

    def fetch_pre_markets(self) -> Dict[str, Dict]:
        """
        Fetch all pre-market events and normalize to our data structure.

        Returns:
            Dictionary mapping event_slug -> event_data
        """
        events = self.fetch_events(tag_slug="pre-market")
        markets_data = {}

        for event in events:
            event_slug = event.get("slug")
            event_data = {
                "title": event.get("title"),
                "volume": float(event.get("volume") or 0),
                "liquidity": float(event.get("liquidity") or 0),
                "closed": event.get("closed", False),
                "markets": {},
            }

            for market in event.get("markets", []):
                outcome_prices = json.loads(market.get("outcomePrices", "[]"))
                market_slug = market.get("slug")
                yes_price = float(outcome_prices[0]) if outcome_prices else 0

                # Extract CLOB token IDs for orderbook fetching (also JSON string like outcomePrices)
                clob_token_ids_raw = market.get("clobTokenIds", "[]")
                clob_token_ids = json.loads(clob_token_ids_raw) if isinstance(clob_token_ids_raw, str) else clob_token_ids_raw or []
                yes_token_id = clob_token_ids[0] if len(clob_token_ids) > 0 else None
                no_token_id = clob_token_ids[1] if len(clob_token_ids) > 1 else None

                event_data["markets"][market_slug] = {
                    "question": market.get("question"),
                    "yes_price": yes_price,
                    "volume": float(market.get("volume") or 0),
                    "closed": market.get("closed", False),
                    "closed_time": market.get("closedTime"),
                    "outcome_prices": outcome_prices,
                    "yes_token_id": yes_token_id,
                    "no_token_id": no_token_id,
                }

            markets_data[event_slug] = event_data

        logger.info(f"Processed {len(markets_data)} pre-market events")
        return markets_data
