"""
Snapshot Comparator

Compare market snapshots to detect price changes.
"""

from typing import Dict, List, Any
from ..utils.logging import get_logger

logger = get_logger(__name__)


def compare_snapshots(
    current: Dict[str, Any],
    previous: Dict[str, Any]
) -> List[Dict[str, Any]]:
    """
    Compare two snapshots and return price changes.

    Args:
        current: Current market data (either snapshot dict or markets dict)
        previous: Previous snapshot dict

    Returns:
        List of change dictionaries, sorted by absolute change
    """
    if not previous:
        return []

    changes = []

    # Handle both raw markets dict and full snapshot format
    current_markets = current.get("markets", current)
    previous_markets = previous.get("markets", {})

    for event_slug, event_data in current_markets.items():
        prev_event = previous_markets.get(event_slug, {})

        for market_slug, market_data in event_data.get("markets", {}).items():
            # Skip closed markets
            if market_data.get("closed"):
                continue

            prev_market = prev_event.get("markets", {}).get(market_slug, {})
            current_price = market_data.get("yes_price", 0)
            prev_price = prev_market.get("yes_price")

            if prev_price is not None and prev_price != current_price:
                change = current_price - prev_price
                change_pct = (change / prev_price * 100) if prev_price > 0 else 0

                changes.append({
                    "event": event_data.get("title"),
                    "event_slug": event_slug,
                    "market": market_data.get("question"),
                    "market_slug": market_slug,
                    "prev_price": prev_price,
                    "current_price": current_price,
                    "change": change,
                    "change_pct": change_pct,
                })

    # Sort by absolute percentage change
    changes.sort(key=lambda x: abs(x["change_pct"]), reverse=True)

    logger.info(f"Found {len(changes)} price changes")
    return changes


def get_top_movers(
    changes: List[Dict[str, Any]],
    limit: int = 20,
    direction: str = None
) -> List[Dict[str, Any]]:
    """
    Get top movers from changes list.

    Args:
        changes: List of change dictionaries
        limit: Max results
        direction: "up", "down", or None for both

    Returns:
        Filtered and limited changes list
    """
    if direction == "up":
        filtered = [c for c in changes if c["change"] > 0]
    elif direction == "down":
        filtered = [c for c in changes if c["change"] < 0]
    else:
        filtered = changes

    return filtered[:limit]


def summarize_changes(changes: List[Dict[str, Any]]) -> Dict[str, Any]:
    """
    Get summary statistics for changes.

    Args:
        changes: List of change dictionaries

    Returns:
        Summary with counts and averages
    """
    if not changes:
        return {
            "total": 0,
            "up": 0,
            "down": 0,
            "avg_change": 0,
            "max_up": None,
            "max_down": None,
        }

    up = [c for c in changes if c["change"] > 0]
    down = [c for c in changes if c["change"] < 0]

    return {
        "total": len(changes),
        "up": len(up),
        "down": len(down),
        "avg_change": sum(c["change"] for c in changes) / len(changes),
        "max_up": max(up, key=lambda x: x["change"]) if up else None,
        "max_down": min(down, key=lambda x: x["change"]) if down else None,
    }
