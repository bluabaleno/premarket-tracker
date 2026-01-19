"""
Launch Detection Module

Automatically detects when projects have launched (TGE) by monitoring
resolved "FDV one day after launch" markets via fresh API calls.
"""

import json
import re
import requests
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, List, Optional, Tuple
from ..utils.logging import get_logger
from ..config import Config

logger = get_logger(__name__)

LAUNCHED_PROJECTS_PATH = Path(__file__).parent.parent.parent.parent / "data" / "launched_projects.json"
GAMMA_API = "https://gamma-api.polymarket.com"


def load_launched_projects() -> Dict:
    """Load the launched projects JSON file."""
    if LAUNCHED_PROJECTS_PATH.exists():
        with open(LAUNCHED_PROJECTS_PATH) as f:
            return json.load(f)
    return {"projects": [], "_template": {}}


def save_launched_projects(data: Dict) -> None:
    """Save the launched projects JSON file."""
    with open(LAUNCHED_PROJECTS_PATH, "w") as f:
        json.dump(data, f, indent=2)
    logger.info(f"Saved {len(data.get('projects', []))} launched projects")


def extract_project_name(title: str) -> Optional[str]:
    """
    Extract project name from market title.

    Examples:
        "Fogo FDV above $300M one day after launch?" -> "Fogo"
        "Will Monad launch a token by December 31?" -> "Monad"
    """
    # FDV pattern: "ProjectName FDV above..."
    fdv_match = re.match(r'^([A-Za-z0-9\.\-]+)\s+FDV\s+above', title, re.IGNORECASE)
    if fdv_match:
        return fdv_match.group(1)

    # Launch pattern: "Will ProjectName launch..."
    launch_match = re.match(r'^Will\s+([A-Za-z0-9\.\-]+)\s+launch', title, re.IGNORECASE)
    if launch_match:
        return launch_match.group(1)

    return None


def fetch_event_details(slug: str) -> Optional[Dict]:
    """Fetch full event details from Gamma API including closedTime."""
    try:
        resp = requests.get(
            f"{GAMMA_API}/events",
            params={"slug": slug},
            timeout=10
        )
        resp.raise_for_status()
        data = resp.json()
        return data[0] if data else None
    except Exception as e:
        logger.warning(f"Failed to fetch event {slug}: {e}")
        return None


def detect_launched_projects(markets_data: Dict) -> List[Dict]:
    """
    Detect projects that have launched based on resolved FDV markets.

    Only detects launches when we can confirm:
    1. An "FDV above X one day after launch" market is closed
    2. We can fetch the actual closedTime from the API
    3. The TGE date is in 2026

    Args:
        markets_data: Dictionary of market data from Gamma API

    Returns:
        List of newly detected launched projects
    """
    # Load existing launched projects
    launched_data = load_launched_projects()
    existing_names = {p["name"].lower() for p in launched_data.get("projects", [])}

    # Track detected launches by project name
    detected: Dict[str, Dict] = {}

    for event_slug, event in markets_data.items():
        title = event.get("title", "")
        project_name = extract_project_name(title)

        if not project_name:
            continue

        # Skip if already in launched projects
        if project_name.lower() in existing_names:
            continue

        # Only look for FDV "one day after launch" markets (most reliable indicator)
        if "fdv above" not in title.lower() or "one day after launch" not in title.lower():
            continue

        # Check if any market in this event is closed
        has_closed_market = any(m.get("closed") for m in event.get("markets", {}).values())
        if not has_closed_market:
            continue

        # Fetch fresh data from API to get closedTime
        logger.info(f"Checking resolved FDV markets for {project_name}...")
        event_details = fetch_event_details(event_slug)
        if not event_details:
            continue

        # Find the earliest closedTime and FDV results from resolved markets
        earliest_closed = None
        fdv_results = []  # List of (threshold_value, threshold_label, resolved_yes)

        for market in event_details.get("markets", []):
            if not market.get("closed"):
                continue

            closed_time_str = market.get("closedTime")
            if not closed_time_str:
                continue

            try:
                # Parse closedTime (format: "2026-01-16 23:51:26+00")
                closed_time = datetime.strptime(
                    closed_time_str.replace("+00", "").strip(),
                    "%Y-%m-%d %H:%M:%S"
                )
                if earliest_closed is None or closed_time < earliest_closed:
                    earliest_closed = closed_time
            except ValueError as e:
                logger.warning(f"Could not parse closedTime '{closed_time_str}': {e}")
                continue

            # Extract FDV threshold and resolution
            question = market.get("question", "")
            outcome_prices = market.get("outcomePrices", "[]")
            if isinstance(outcome_prices, str):
                outcome_prices = json.loads(outcome_prices)

            # Check if resolved YES (price = 1)
            resolved_yes = len(outcome_prices) > 0 and float(outcome_prices[0]) >= 0.99

            # Parse FDV threshold from question like "Fogo FDV above $500M one day after launch?"
            fdv_match = re.search(r'\$(\d+(?:\.\d+)?)\s*(M|B|K)?', question, re.IGNORECASE)
            if fdv_match:
                value = float(fdv_match.group(1))
                unit = (fdv_match.group(2) or '').upper()
                if unit == 'B':
                    value *= 1_000_000_000
                elif unit == 'M':
                    value *= 1_000_000
                elif unit == 'K':
                    value *= 1_000

                label = f"${fdv_match.group(1)}{fdv_match.group(2) or ''}"
                fdv_results.append((value, label, resolved_yes))

        if earliest_closed is None:
            continue

        # Find the highest FDV threshold that resolved YES
        fdv_results.sort(key=lambda x: x[0], reverse=True)
        highest_fdv_yes = None
        for value, label, resolved_yes in fdv_results:
            if resolved_yes:
                highest_fdv_yes = label
                break

        # Calculate TGE date (FDV markets resolve "one day after launch")
        tge_date = (earliest_closed - timedelta(days=1)).strftime("%Y-%m-%d")

        # Only count 2026 launches
        if not tge_date.startswith("2026"):
            logger.debug(f"Skipping {project_name} - TGE date {tge_date} not in 2026")
            continue

        # Calculate volumes by market type
        fdv_volume = event.get("volume", 0)
        launch_volume = 0
        other_volume = 0

        # Find related markets (launch date markets, etc.)
        for other_slug, other_event in markets_data.items():
            if other_slug == event_slug:
                continue
            other_title = other_event.get("title", "")
            other_name = extract_project_name(other_title)
            if other_name and other_name.lower() == project_name.lower():
                vol = other_event.get("volume", 0)
                if "launch" in other_title.lower() and "by" in other_title.lower():
                    launch_volume += vol
                else:
                    other_volume += vol

        total_volume = fdv_volume + launch_volume + other_volume

        detected[project_name] = {
            "name": project_name,
            "tge_date": tge_date,
            "polymarket_volume": total_volume,
            "fdv_market_volume": fdv_volume,
            "launch_market_volume": launch_volume,
            "fdv_result": highest_fdv_yes,  # e.g., "$500M" or None
            "other_volume": other_volume,
            "limitless_volume": 0,
            "closed_time": earliest_closed.isoformat()
        }

        fdv_str = f", FDV Result: >{highest_fdv_yes}" if highest_fdv_yes else ""
        logger.info(f"Detected launch: {project_name} (TGE: {tge_date}, FDV Vol: ${fdv_volume:,.0f}, Launch Vol: ${launch_volume:,.0f}{fdv_str})")

    return list(detected.values())


def update_launched_projects(markets_data: Dict, limitless_data: Dict = None) -> int:
    """
    Detect and add newly launched projects to launched_projects.json.

    Args:
        markets_data: Polymarket data from Gamma API
        limitless_data: Optional Limitless market data

    Returns:
        Number of new projects added
    """
    new_launches = detect_launched_projects(markets_data)

    if not new_launches:
        logger.info("No new launches detected")
        return 0

    # Load and update
    launched_data = load_launched_projects()

    for launch in new_launches:
        fdv_result = launch.get("fdv_result")
        project_entry = {
            "id": launch["name"].lower().replace(" ", "-").replace(".", ""),
            "name": launch["name"],
            "ticker": launch["name"].upper().replace(".", "")[:6],
            "tge_date": launch["tge_date"],
            "pre_tge": {
                "polymarket_volume": launch["polymarket_volume"],
                "limitless_volume": launch.get("limitless_volume", 0),
                "fdv_market_volume": launch.get("fdv_market_volume", 0),
                "launch_market_volume": launch.get("launch_market_volume", 0),
                "fdv_result": fdv_result,  # e.g., "$500M" - highest threshold resolved YES
                "final_odds": {},
                "captured_at": datetime.now().strftime("%Y-%m-%d")
            },
            "post_tge_markets": {
                "limitless": [],
                "polymarket": []
            },
            "volume_history": [],
            "notes": f"Auto-detected TGE on {launch['tge_date']}" + (f", FDV >{fdv_result}" if fdv_result else "")
        }

        launched_data["projects"].append(project_entry)
        fdv_vol = launch.get('fdv_market_volume', 0)
        launch_vol = launch.get('launch_market_volume', 0)
        fdv_str = f", FDV >{fdv_result}" if fdv_result else ""
        print(f"   ✓ {launch['name']} - TGE: {launch['tge_date']}, FDV Vol: ${fdv_vol:,.0f}, Launch Vol: ${launch_vol:,.0f}{fdv_str}")

    save_launched_projects(launched_data)
    return len(new_launches)
