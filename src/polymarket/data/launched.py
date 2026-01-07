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

        history = project.get("volume_history", [])
        if history:
            # Sum all daily volumes for cumulative total
            post_tge_total = sum(h.get("total_volume", 0) for h in history)

            # Calculate trend (compare cumulative at day N vs day N-7)
            if len(history) >= 7:
                recent_week = sum(h.get("total_volume", 0) for h in history[-7:])
                prior_total = post_tge_total - recent_week
                trend = ((recent_week / prior_total) * 100 - 100) if prior_total > 0 else 0
            else:
                trend = 0
        else:
            post_tge_total = 0
            trend = 0

        return {
            "project_id": project_id,
            "name": project.get("name"),
            "ticker": project.get("ticker"),
            "tge_date": project.get("tge_date"),
            "pre_tge_volume": pre_tge_total,
            "post_tge_volume": post_tge_total,
            "volume_ratio": (post_tge_total / pre_tge_total) if pre_tge_total > 0 else 0,
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


# Convenience function
def load_launched_projects() -> Dict[str, Any]:
    """Load launched projects data"""
    store = LaunchedProjectStore()
    return store.load()
