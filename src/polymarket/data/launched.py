"""
Launched Projects Tracker

Track projects that have TGE'd and their post-launch market performance.
"""

import json
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Any, Optional
from ..config import Config
from ..utils.logging import get_logger

logger = get_logger(__name__)

# Path for launched projects data
LAUNCHED_PROJECTS_PATH = Config.DATA_DIR / "launched_projects.json"


class LaunchedProjectStore:
    """Manages launched project tracking data"""

    def __init__(self, path: Path = None):
        self.path = path or LAUNCHED_PROJECTS_PATH

    def load(self) -> Dict[str, Any]:
        """Load launched projects data"""
        if not self.path.exists():
            return {"projects": []}

        try:
            with open(self.path, "r") as f:
                data = json.load(f)
                # Filter out template
                data["projects"] = [
                    p for p in data.get("projects", [])
                    if not p.get("id", "").startswith("_")
                ]
                return data
        except Exception as e:
            logger.error(f"Failed to load launched projects: {e}")
            return {"projects": []}

    def save(self, data: Dict[str, Any]) -> bool:
        """Save launched projects data"""
        try:
            with open(self.path, "w") as f:
                json.dump(data, f, indent=2)
            return True
        except Exception as e:
            logger.error(f"Failed to save launched projects: {e}")
            return False

    def get_project(self, project_id: str) -> Optional[Dict[str, Any]]:
        """Get a specific project by ID"""
        data = self.load()
        for project in data["projects"]:
            if project.get("id") == project_id:
                return project
        return None

    def add_project(
        self,
        name: str,
        ticker: str,
        tge_date: str,
        pre_tge_poly_volume: float = 0,
        pre_tge_lim_volume: float = 0,
        final_odds: Dict = None,
        notes: str = ""
    ) -> Dict[str, Any]:
        """
        Add a newly launched project.

        Args:
            name: Project name (e.g., "Zama")
            ticker: Token ticker (e.g., "ZAMA")
            tge_date: TGE date (YYYY-MM-DD)
            pre_tge_poly_volume: Final Polymarket pre-TGE volume
            pre_tge_lim_volume: Final Limitless pre-TGE volume
            final_odds: Final odds at resolution
            notes: Any notes

        Returns:
            The created project dict
        """
        data = self.load()

        project_id = name.lower().replace(" ", "-")

        # Check if already exists
        for p in data["projects"]:
            if p.get("id") == project_id:
                logger.warning(f"Project {name} already exists")
                return p

        project = {
            "id": project_id,
            "name": name,
            "ticker": ticker,
            "tge_date": tge_date,
            "pre_tge": {
                "polymarket_volume": pre_tge_poly_volume,
                "limitless_volume": pre_tge_lim_volume,
                "final_odds": final_odds or {},
                "captured_at": datetime.now().strftime("%Y-%m-%d")
            },
            "post_tge_markets": {
                "limitless": [],
                "polymarket": []
            },
            "volume_history": [],
            "notes": notes
        }

        data["projects"].append(project)
        self.save(data)

        logger.info(f"Added launched project: {name} ({ticker})")
        return project

    def add_post_tge_market(
        self,
        project_id: str,
        platform: str,
        market_slug: str
    ) -> bool:
        """
        Link a post-TGE market to a launched project.

        Args:
            project_id: Project ID
            platform: "limitless" or "polymarket"
            market_slug: Market slug/identifier

        Returns:
            True if successful
        """
        data = self.load()

        for project in data["projects"]:
            if project.get("id") == project_id:
                if platform not in project["post_tge_markets"]:
                    project["post_tge_markets"][platform] = []

                if market_slug not in project["post_tge_markets"][platform]:
                    project["post_tge_markets"][platform].append(market_slug)
                    self.save(data)
                    logger.info(f"Added {platform} market {market_slug} to {project_id}")
                    return True
                return True  # Already exists

        logger.warning(f"Project {project_id} not found")
        return False

    def record_volume(
        self,
        project_id: str,
        date: str,
        limitless_volume: float = 0,
        polymarket_volume: float = 0
    ) -> bool:
        """
        Record daily volume snapshot for a project.

        Args:
            project_id: Project ID
            date: Date (YYYY-MM-DD)
            limitless_volume: Total Limitless volume for post-TGE markets
            polymarket_volume: Total Polymarket volume for post-TGE markets

        Returns:
            True if successful
        """
        data = self.load()

        for project in data["projects"]:
            if project.get("id") == project_id:
                # Check if we already have an entry for this date
                for entry in project["volume_history"]:
                    if entry.get("date") == date:
                        # Update existing entry
                        entry["limitless_volume"] = limitless_volume
                        entry["polymarket_volume"] = polymarket_volume
                        entry["total_volume"] = limitless_volume + polymarket_volume
                        self.save(data)
                        return True

                # Add new entry
                project["volume_history"].append({
                    "date": date,
                    "limitless_volume": limitless_volume,
                    "polymarket_volume": polymarket_volume,
                    "total_volume": limitless_volume + polymarket_volume
                })

                # Keep sorted by date
                project["volume_history"].sort(key=lambda x: x["date"])

                self.save(data)
                logger.info(f"Recorded volume for {project_id}: ${limitless_volume + polymarket_volume:,.0f}")
                return True

        logger.warning(f"Project {project_id} not found")
        return False

    def get_volume_summary(self, project_id: str) -> Dict[str, Any]:
        """
        Get volume summary for a project.

        Returns:
            Dict with pre_tge_total, post_tge_total, volume_trend, etc.
        """
        project = self.get_project(project_id)
        if not project:
            return {}

        pre_tge = project.get("pre_tge", {})
        pre_tge_total = (
            pre_tge.get("polymarket_volume", 0) +
            pre_tge.get("limitless_volume", 0)
        )
        # Limitless-only pre-TGE volume
        pre_tge_limitless = pre_tge.get("limitless_volume", 0)

        # Get breakdown by market type
        fdv_market_volume = pre_tge.get("fdv_market_volume", 0)
        launch_market_volume = pre_tge.get("launch_market_volume", 0)
        fdv_result = pre_tge.get("fdv_result")  # e.g., "$500M"

        history = project.get("volume_history", [])
        if history:
            # Sum all daily volumes for cumulative total
            post_tge_total = sum(h.get("total_volume", 0) for h in history)
            # Limitless-only post-TGE volume
            post_tge_limitless = sum(h.get("limitless_volume", 0) for h in history)

            # Calculate trend (compare cumulative at day N vs day N-7)
            if len(history) >= 7:
                recent_week = sum(h.get("total_volume", 0) for h in history[-7:])
                prior_total = post_tge_total - recent_week
                trend = ((recent_week / prior_total) * 100 - 100) if prior_total > 0 else 0
            else:
                trend = 0
        else:
            post_tge_total = 0
            post_tge_limitless = 0
            trend = 0

        return {
            "project_id": project_id,
            "name": project.get("name"),
            "ticker": project.get("ticker"),
            "tge_date": project.get("tge_date"),
            "pre_tge_volume": pre_tge_total,
            "pre_tge_limitless": pre_tge_limitless,
            "fdv_market_volume": fdv_market_volume,
            "launch_market_volume": launch_market_volume,
            "fdv_result": fdv_result,  # e.g., "$500M" - highest FDV threshold resolved YES
            "post_tge_volume": post_tge_total,
            "post_tge_limitless": post_tge_limitless,
            "volume_ratio": (post_tge_total / pre_tge_total) if pre_tge_total > 0 else 0,
            "limitless_volume_ratio": (post_tge_limitless / pre_tge_limitless) if pre_tge_limitless > 0 else 0,
            "trend_7d": trend,
            "days_since_tge": len(history)
        }

    def list_projects(self, include_history: bool = True) -> List[Dict[str, Any]]:
        """List all launched projects with summaries and optional volume history"""
        data = self.load()
        results = []
        for p in data["projects"]:
            summary = self.get_volume_summary(p["id"])
            if include_history:
                summary["volume_history"] = p.get("volume_history", [])
            results.append(summary)
        return results

    def discover_post_tge_markets(
        self,
        project_id: str,
        limitless_data: Dict[str, Any]
    ) -> List[Dict[str, Any]]:
        """
        Discover potential post-TGE markets for a project based on ticker pattern.

        Looks for markets matching patterns like:
        - Slug: sent-above-dollar0X-on-date (ticker-above-dollar...)
        - Title: $SENT above $X.XX on [date]

        Args:
            project_id: Project ID to search for
            limitless_data: Limitless market data from snapshot

        Returns:
            List of market dicts that match but aren't yet tracked
        """
        project = self.get_project(project_id)
        if not project:
            logger.warning(f"Project {project_id} not found")
            return []

        ticker = project.get("ticker", "").lower()
        if not ticker:
            logger.warning(f"Project {project_id} has no ticker")
            return []

        # Get already tracked markets
        tracked = set(project.get("post_tge_markets", {}).get("limitless", []))

        # Patterns to match post-TGE price markets
        # Slug pattern: {ticker}-above-dollar (e.g., sent-above-dollar002698)
        # Title pattern: ${TICKER} above $
        slug_pattern = f"{ticker}-above-dollar"
        title_pattern_upper = f"${ticker.upper()} above"
        title_pattern_lower = f"${ticker.lower()} above"

        discovered = []

        for proj_name, proj_data in limitless_data.get("projects", {}).items():
            for market in proj_data.get("markets", []):
                slug = market.get("slug", "").lower()
                title = market.get("title", "")

                # Skip if already tracked
                if slug in tracked or market.get("slug") in tracked:
                    continue

                # Skip FDV and launch date markets (pre-TGE)
                title_lower = title.lower()
                if "fdv" in title_lower or "launch" in title_lower:
                    continue

                # Check if matches our patterns
                is_match = (
                    slug_pattern in slug or
                    title_pattern_upper in title or
                    title_pattern_lower in title
                )

                if is_match:
                    discovered.append({
                        "slug": market.get("slug"),
                        "title": title,
                        "yes_price": market.get("yes_price", 0),
                        "volume": market.get("volume", 0),
                        "project_name": proj_name
                    })

        return discovered

    def check_all_for_new_markets(
        self,
        limitless_data: Dict[str, Any]
    ) -> Dict[str, List[Dict[str, Any]]]:
        """
        Check all launched projects (past TGE) for new post-TGE markets.

        Returns:
            Dict mapping project_id to list of discovered markets
        """
        today = datetime.now().strftime("%Y-%m-%d")
        data = self.load()
        results = {}

        for project in data["projects"]:
            tge_date = project.get("tge_date", "")
            project_id = project.get("id")

            # Skip if TGE hasn't happened yet
            if not tge_date or tge_date > today:
                continue

            # Discover new markets
            discovered = self.discover_post_tge_markets(project_id, limitless_data)

            if discovered:
                results[project_id] = discovered

        return results

    def fetch_and_record_post_tge_volume(self, date: str = None) -> Dict[str, float]:
        """
        Fetch current volume for all tracked post-TGE markets and record it.

        Args:
            date: Date to record (YYYY-MM-DD), defaults to today

        Returns:
            Dict mapping project_id to total volume fetched
        """
        import requests
        from ..config import Config

        if date is None:
            date = datetime.now().strftime("%Y-%m-%d")

        data = self.load()
        results = {}

        for project in data["projects"]:
            project_id = project.get("id")
            tge_date = project.get("tge_date", "")

            # Skip if TGE hasn't happened yet
            if not tge_date or tge_date > date:
                continue

            limitless_slugs = project.get("post_tge_markets", {}).get("limitless", [])
            if not limitless_slugs:
                continue

            total_volume = 0
            for slug in limitless_slugs:
                try:
                    url = f"{Config.LIMITLESS_API}/markets/{slug}"
                    resp = requests.get(url, timeout=10)
                    if resp.status_code == 200:
                        market = resp.json()
                        # Volume is in raw units, convert using decimals
                        decimals = market.get("collateralToken", {}).get("decimals", 6)
                        vol_raw = market.get("volume", "0")
                        volume = float(vol_raw) / (10 ** decimals) if vol_raw else 0
                        total_volume += volume
                        logger.debug(f"Fetched {slug}: ${volume:,.0f}")
                except Exception as e:
                    logger.warning(f"Failed to fetch {slug}: {e}")

            if total_volume > 0:
                self.record_volume(project_id, date, limitless_volume=total_volume)
                results[project_id] = total_volume
                logger.info(f"Recorded ${total_volume:,.0f} for {project_id}")

        return results


# Convenience function
def load_launched_projects() -> Dict[str, Any]:
    """Load launched projects data"""
    store = LaunchedProjectStore()
    return store.load()


if __name__ == "__main__":
    import sys

    def print_usage():
        print("Usage:")
        print("  python -m src.polymarket.data.launched add <project_id> <slug>")
        print("  python -m src.polymarket.data.launched discover <project_id>")
        print("  python -m src.polymarket.data.launched list")
        print()
        print("Examples:")
        print("  python -m src.polymarket.data.launched add sentient dollarsent-above-050-on-jan-24")
        print("  python -m src.polymarket.data.launched discover sentient")

    if len(sys.argv) < 2:
        print_usage()
        sys.exit(1)

    command = sys.argv[1]
    store = LaunchedProjectStore()

    if command == "add":
        if len(sys.argv) < 4:
            print("Error: add requires project_id and slug")
            print_usage()
            sys.exit(1)
        project_id = sys.argv[2]
        slug = sys.argv[3]
        if store.add_post_tge_market(project_id, "limitless", slug):
            print(f"✓ Added {slug} to {project_id}")
        else:
            print(f"✗ Failed to add market")

    elif command == "discover":
        if len(sys.argv) < 3:
            print("Error: discover requires project_id")
            print_usage()
            sys.exit(1)
        project_id = sys.argv[2]

        # Load latest snapshot for Limitless data
        import os
        from ..config import Config
        snapshots = sorted([
            f for f in os.listdir(Config.DATA_DIR)
            if f.startswith('snapshot_') and f.endswith('.json')
        ])
        if not snapshots:
            print("No snapshots found")
            sys.exit(1)

        latest = snapshots[-1]
        with open(Config.DATA_DIR / latest) as f:
            data = json.load(f)

        limitless_data = data.get("limitless", {})
        discovered = store.discover_post_tge_markets(project_id, limitless_data)

        if not discovered:
            print(f"No new markets found for {project_id}")
        else:
            project = store.get_project(project_id)
            ticker = project.get("ticker", "???") if project else "???"
            print(f"Found {len(discovered)} new ${ticker} market(s):\n")
            for i, m in enumerate(discovered, 1):
                price_str = f"{m['yes_price']*100:.1f}%" if m.get('yes_price') else "N/A"
                print(f"  {i}. {m['title']}")
                print(f"     slug: {m['slug']}")
                print(f"     price: {price_str}")
                print()

            # Prompt to add
            print("Add markets? Enter numbers separated by space (e.g., '1 2 3'), or 'all', or 'n':")
            choice = input("> ").strip().lower()

            if choice == 'n':
                print("Skipped")
            elif choice == 'all':
                for m in discovered:
                    store.add_post_tge_market(project_id, "limitless", m['slug'])
                print(f"✓ Added {len(discovered)} markets")
            else:
                try:
                    indices = [int(x) - 1 for x in choice.split()]
                    added = 0
                    for idx in indices:
                        if 0 <= idx < len(discovered):
                            store.add_post_tge_market(project_id, "limitless", discovered[idx]['slug'])
                            added += 1
                    print(f"✓ Added {added} market(s)")
                except ValueError:
                    print("Invalid input")

    elif command == "list":
        projects = store.list_projects(include_history=False)
        print(f"{'Project':<20} {'Ticker':<8} {'TGE Date':<12} {'Post-TGE Markets':<10}")
        print("-" * 55)
        for p in projects:
            project = store.get_project(p['project_id'])
            num_markets = len(project.get('post_tge_markets', {}).get('limitless', [])) if project else 0
            print(f"{p['name']:<20} {p['ticker']:<8} {p['tge_date']:<12} {num_markets}")

    else:
        print(f"Unknown command: {command}")
        print_usage()
        sys.exit(1)
