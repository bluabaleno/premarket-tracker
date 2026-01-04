"""
Leaderboard Data

Load project leaderboard/tracking data from CSV.
"""

import csv
from pathlib import Path
from typing import Dict, Any
from ..config import Config
from ..utils.logging import get_logger

logger = get_logger(__name__)


class LeaderboardStore:
    """Manages leaderboard CSV data"""

    def __init__(self, path: Path = None):
        self.path = path or Config.LEADERBOARD_CSV

    def load(self) -> Dict[str, Dict[str, Any]]:
        """
        Load leaderboard data from CSV.

        Returns:
            Dictionary mapping project_name_lower -> project_info
        """
        if not self.path.exists():
            logger.warning("Leaderboard CSV not found")
            return {}

        try:
            leaderboard = {}
            with open(self.path, "r", encoding="utf-8") as f:
                reader = csv.DictReader(f)
                for row in reader:
                    project = row.get("Project", "").strip()
                    if not project:
                        continue

                    leaderboard[project.lower()] = {
                        "name": project,
                        "sector": row.get("Sector", ""),
                        "source": row.get("Source", ""),  # Cookie, Yaps, etc.
                        "market_status": row.get("Market Status", ""),
                        "polymarket_link": row.get("Polymarket Link", ""),
                        "leaderboard_link": row.get("Leaderboard Link", ""),
                        "priority_note": row.get("Priority Note", ""),
                        "in_touch": row.get("In Touch with Team? ", ""),
                    }

            logger.info(f"Loaded {len(leaderboard)} projects from leaderboard CSV")
            return leaderboard

        except Exception as e:
            logger.error(f"Failed to load leaderboard CSV: {e}")
            return {}

    def get_project(self, name: str) -> Dict[str, Any]:
        """
        Get info for a specific project.

        Args:
            name: Project name (case-insensitive)

        Returns:
            Project info dictionary or empty dict
        """
        data = self.load()
        return data.get(name.lower(), {})

    def list_projects(self) -> list:
        """List all project names"""
        data = self.load()
        return [v["name"] for v in data.values()]


# Convenience function for backwards compatibility
def load_leaderboard_data() -> Dict[str, Dict[str, Any]]:
    """Load leaderboard data (backwards compatible)"""
    store = LeaderboardStore()
    return store.load()
