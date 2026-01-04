"""
Snapshot Storage

Load and save daily market snapshots.
"""

import json
import os
from datetime import datetime
from pathlib import Path
from typing import Dict, Optional, Tuple, Any
from ..config import Config
from ..utils.logging import get_logger

logger = get_logger(__name__)


class SnapshotStore:
    """Manages daily market snapshots"""

    def __init__(self, data_dir: Path = None):
        self.data_dir = data_dir or Config.DATA_DIR
        self.data_dir.mkdir(parents=True, exist_ok=True)

    def _get_path(self, date_str: str) -> Path:
        """Get path for a snapshot file"""
        return self.data_dir / f"snapshot_{date_str}.json"

    def save(self, markets_data: Dict, date_str: str = None) -> Path:
        """
        Save a market snapshot.

        Args:
            markets_data: Dictionary of market data
            date_str: Date string (YYYY-MM-DD), defaults to today

        Returns:
            Path to saved file
        """
        if date_str is None:
            date_str = datetime.now().strftime("%Y-%m-%d")

        snapshot = {
            "timestamp": datetime.now().isoformat(),
            "date": date_str,
            "markets": markets_data,
        }

        path = self._get_path(date_str)
        with open(path, "w") as f:
            json.dump(snapshot, f, indent=2)

        logger.info(f"Saved snapshot to {path}")
        return path

    def load(self, date_str: str) -> Optional[Dict[str, Any]]:
        """
        Load a snapshot by date.

        Args:
            date_str: Date string (YYYY-MM-DD)

        Returns:
            Snapshot dictionary or None if not found
        """
        path = self._get_path(date_str)
        if not path.exists():
            return None

        try:
            with open(path, "r") as f:
                return json.load(f)
        except Exception as e:
            logger.error(f"Failed to load snapshot {date_str}: {e}")
            return None

    def get_previous(self, exclude_date: str = None) -> Tuple[Optional[Dict], Optional[str]]:
        """
        Get the most recent previous snapshot.

        Args:
            exclude_date: Date to exclude (defaults to today)

        Returns:
            Tuple of (snapshot_data, date_str) or (None, None)
        """
        if exclude_date is None:
            exclude_date = datetime.now().strftime("%Y-%m-%d")

        # List all snapshot files
        files = sorted([
            f for f in os.listdir(self.data_dir)
            if f.startswith("snapshot_") and f.endswith(".json")
        ])

        # Find most recent that isn't today
        for f in reversed(files):
            date = f.replace("snapshot_", "").replace(".json", "")
            if date != exclude_date:
                snapshot = self.load(date)
                if snapshot:
                    return snapshot, date

        return None, None

    def list_dates(self) -> list:
        """List all available snapshot dates"""
        files = [
            f.replace("snapshot_", "").replace(".json", "")
            for f in os.listdir(self.data_dir)
            if f.startswith("snapshot_") and f.endswith(".json")
        ]
        return sorted(files)


# Convenience functions for backwards compatibility
def save_snapshot(markets_data: Dict, date_str: str = None) -> Path:
    """Save a snapshot (backwards compatible)"""
    store = SnapshotStore()
    return store.save(markets_data, date_str)


def load_snapshot(date_str: str) -> Optional[Dict]:
    """Load a snapshot (backwards compatible)"""
    store = SnapshotStore()
    return store.load(date_str)


def get_previous_snapshot() -> Tuple[Optional[Dict], Optional[str]]:
    """Get previous snapshot (backwards compatible)"""
    store = SnapshotStore()
    return store.get_previous()
