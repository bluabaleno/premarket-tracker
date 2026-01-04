"""
Portfolio Storage

Load and save portfolio positions.
"""

import json
from pathlib import Path
from typing import Dict, List, Any, Optional
from ..config import Config
from ..utils.logging import get_logger

logger = get_logger(__name__)


class PortfolioStore:
    """Manages portfolio data"""

    def __init__(self, path: Path = None):
        self.path = path or Config.PORTFOLIO_PATH

    def load(self) -> Dict[str, Any]:
        """
        Load portfolio from JSON file.

        Returns:
            Portfolio dictionary with 'positions' key
        """
        if not self.path.exists():
            logger.debug("Portfolio file not found, returning empty")
            return {"positions": []}

        try:
            with open(self.path, "r") as f:
                data = json.load(f)
                logger.info(f"Loaded {len(data.get('positions', []))} portfolio positions")
                return data
        except Exception as e:
            logger.error(f"Failed to load portfolio: {e}")
            return {"positions": []}

    def save(self, portfolio: Dict[str, Any]) -> bool:
        """
        Save portfolio to JSON file.

        Args:
            portfolio: Portfolio dictionary

        Returns:
            True if successful
        """
        try:
            with open(self.path, "w") as f:
                json.dump(portfolio, f, indent=2)
            logger.info(f"Saved portfolio to {self.path}")
            return True
        except Exception as e:
            logger.error(f"Failed to save portfolio: {e}")
            return False

    def add_position(self, position: Dict[str, Any]) -> bool:
        """
        Add a new position to the portfolio.

        Args:
            position: Position dictionary with id, name, legs, opened_at

        Returns:
            True if successful
        """
        portfolio = self.load()
        portfolio["positions"].append(position)
        return self.save(portfolio)

    def remove_position(self, position_id: str) -> bool:
        """
        Remove a position by ID.

        Args:
            position_id: The position ID to remove

        Returns:
            True if found and removed
        """
        portfolio = self.load()
        original_len = len(portfolio["positions"])
        portfolio["positions"] = [
            p for p in portfolio["positions"]
            if p.get("id") != position_id
        ]

        if len(portfolio["positions"]) < original_len:
            return self.save(portfolio)
        return False

    def get_position(self, position_id: str) -> Optional[Dict[str, Any]]:
        """
        Get a position by ID.

        Args:
            position_id: The position ID

        Returns:
            Position dictionary or None
        """
        portfolio = self.load()
        for pos in portfolio["positions"]:
            if pos.get("id") == position_id:
                return pos
        return None


# Convenience function for backwards compatibility
def load_portfolio() -> Dict[str, Any]:
    """Load portfolio (backwards compatible)"""
    store = PortfolioStore()
    return store.load()
