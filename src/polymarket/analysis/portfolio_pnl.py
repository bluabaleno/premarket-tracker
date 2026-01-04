"""
Portfolio P&L Calculator

Calculate profit/loss for portfolio positions.
"""

from typing import Dict, List, Any, Optional
from ..utils.logging import get_logger

logger = get_logger(__name__)


def calculate_portfolio_pnl(
    portfolio: Dict[str, Any],
    current_markets: Dict[str, Any],
    limitless_data: Dict[str, Any] = None
) -> List[Dict[str, Any]]:
    """
    Calculate P&L for portfolio positions based on current prices.

    Args:
        portfolio: Portfolio dict with 'positions' key
        current_markets: Current Polymarket data
        limitless_data: Current Limitless data (optional)

    Returns:
        List of position results with P&L calculations
    """
    results = []

    for position in portfolio.get("positions", []):
        position_result = {
            "id": position.get("id"),
            "name": position.get("name"),
            "opened_at": position.get("opened_at"),
            "legs": [],
            "total_cost": 0,
            "total_value": 0,
            "total_pnl": 0,
        }

        for leg in position.get("legs", []):
            leg_result = _calculate_leg_pnl(
                leg, current_markets, limitless_data
            )
            position_result["legs"].append(leg_result)
            position_result["total_cost"] += leg_result["cost"]
            position_result["total_value"] += leg_result["value"]
            position_result["total_pnl"] += leg_result["pnl"]

        # Calculate P&L percentage
        if position_result["total_cost"] > 0:
            position_result["pnl_pct"] = (
                position_result["total_pnl"] / position_result["total_cost"]
            ) * 100
        else:
            position_result["pnl_pct"] = 0

        results.append(position_result)

    logger.info(f"Calculated P&L for {len(results)} positions")
    return results


def _calculate_leg_pnl(
    leg: Dict[str, Any],
    current_markets: Dict[str, Any],
    limitless_data: Dict[str, Any] = None
) -> Dict[str, Any]:
    """
    Calculate P&L for a single leg.

    Args:
        leg: Leg dictionary with platform, market, direction, shares, entry_price
        current_markets: Current Polymarket data
        limitless_data: Current Limitless data

    Returns:
        Leg result with current price and P&L
    """
    platform = leg.get("platform")
    market_slug = leg.get("market")
    direction = leg.get("direction")
    shares = leg.get("shares", 0)
    entry_price = leg.get("entry_price", 0)
    cost = leg.get("cost", shares * entry_price)

    # Find current price
    current_price = _find_current_price(
        platform, market_slug, direction,
        current_markets, limitless_data
    )

    # Calculate value and P&L
    if current_price is not None:
        current_value = shares * current_price
        pnl = current_value - cost
    else:
        # Assume no change if we can't find price
        current_value = cost
        pnl = 0
        current_price = entry_price

    return {
        "platform": platform,
        "market": market_slug,
        "direction": direction,
        "shares": shares,
        "entry_price": entry_price,
        "current_price": current_price,
        "cost": cost,
        "value": current_value,
        "pnl": pnl,
    }


def _find_current_price(
    platform: str,
    market_slug: str,
    direction: str,
    current_markets: Dict[str, Any],
    limitless_data: Dict[str, Any] = None
) -> Optional[float]:
    """
    Find current price for a market.

    Args:
        platform: "polymarket" or "limitless"
        market_slug: Market identifier
        direction: "yes" or "no"
        current_markets: Polymarket data
        limitless_data: Limitless data

    Returns:
        Current price (adjusted for direction) or None
    """
    current_price = None

    if platform == "polymarket":
        # Search through Polymarket data
        for event_slug, event_data in current_markets.items():
            for mkt_slug, mkt_data in event_data.get("markets", {}).items():
                if market_slug in mkt_slug or mkt_slug in market_slug:
                    current_price = mkt_data.get("yes_price", 0)
                    break
            if current_price is not None:
                break

    elif platform == "limitless" and limitless_data:
        # Search through Limitless data
        for proj_name, proj_data in limitless_data.get("projects", {}).items():
            for mkt in proj_data.get("markets", []):
                mkt_slug = mkt.get("slug", "")
                if market_slug in mkt_slug or mkt_slug in market_slug:
                    current_price = mkt.get("yes_price", 0)
                    break
            if current_price is not None:
                break

    # Adjust for direction (NO price = 1 - YES price)
    if current_price is not None and direction == "no":
        current_price = 1 - current_price

    return current_price


def calculate_total_pnl(positions: List[Dict[str, Any]]) -> Dict[str, float]:
    """
    Calculate total P&L across all positions.

    Args:
        positions: List of position results from calculate_portfolio_pnl

    Returns:
        Dictionary with total_cost, total_value, total_pnl, total_pnl_pct
    """
    total_cost = sum(p["total_cost"] for p in positions)
    total_value = sum(p["total_value"] for p in positions)
    total_pnl = sum(p["total_pnl"] for p in positions)

    return {
        "total_cost": total_cost,
        "total_value": total_value,
        "total_pnl": total_pnl,
        "total_pnl_pct": (total_pnl / total_cost * 100) if total_cost > 0 else 0,
    }
