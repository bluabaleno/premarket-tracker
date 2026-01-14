"""Kaito Yaps data loading"""

import json
import os
from ..config import Config


class KaitoStore:
    """Load Kaito Yaps project status data"""

    def __init__(self, filepath: str = None):
        self.filepath = filepath or os.path.join(
            Config.DATA_DIR, "kaito_yaps_projects.json"
        )

    def load(self) -> dict:
        """
        Load Kaito data from JSON file.

        Returns dict with keys: pre_tge, post_tge, summary
        """
        try:
            with open(self.filepath, "r") as f:
                return json.load(f)
        except FileNotFoundError:
            return {"pre_tge": [], "post_tge": [], "summary": {}}
        except json.JSONDecodeError:
            return {"pre_tge": [], "post_tge": [], "summary": {}}

    def get_status(self, project_name: str) -> str:
        """
        Get TGE status for a project.

        Args:
            project_name: Project slug (lowercase)

        Returns:
            'pre-tge', 'post-tge', or 'none'
        """
        data = self.load()
        name_lower = project_name.lower().replace(" ", "").replace("-", "")

        # Check pre-TGE
        for p in data.get("pre_tge", []):
            if p.lower().replace("-", "") == name_lower:
                return "pre-tge"

        # Check post-TGE
        for p in data.get("post_tge", []):
            if p.lower().replace("-", "") == name_lower:
                return "post-tge"

        return "none"


def load_kaito_data() -> dict:
    """Load Kaito Yaps data (convenience function)"""
    return KaitoStore().load()


class CookieStore:
    """Load Cookie.fun active campaign data"""

    def __init__(self, filepath: str = None):
        self.filepath = filepath or os.path.join(
            Config.DATA_DIR, "cookie_campaigns.json"
        )

    def load(self) -> dict:
        """
        Load Cookie campaign data from JSON file.

        Returns dict with keys: active_campaigns, slugs, count
        """
        try:
            with open(self.filepath, "r") as f:
                return json.load(f)
        except FileNotFoundError:
            return {"active_campaigns": [], "slugs": [], "count": 0}
        except json.JSONDecodeError:
            return {"active_campaigns": [], "slugs": [], "count": 0}

    def has_campaign(self, project_name: str) -> bool:
        """Check if a project has an active Cookie campaign."""
        data = self.load()
        name_lower = project_name.lower().replace(" ", "").replace("-", "")
        
        for slug in data.get("slugs", []):
            if slug.replace("-", "") == name_lower:
                return True
        return False


def load_cookie_data() -> dict:
    """Load Cookie campaign data (convenience function)"""
    return CookieStore().load()


class WallchainStore:
    """Load Wallchain InfoFi campaign data"""

    def __init__(self, filepath: str = None):
        self.filepath = filepath or os.path.join(
            Config.DATA_DIR, "wallchain_campaigns.json"
        )

    def load(self) -> dict:
        """
        Load Wallchain campaign data from JSON file.

        Returns dict with keys: active_campaigns, slugs, count
        """
        try:
            with open(self.filepath, "r") as f:
                return json.load(f)
        except FileNotFoundError:
            return {"active_campaigns": [], "slugs": [], "count": 0}
        except json.JSONDecodeError:
            return {"active_campaigns": [], "slugs": [], "count": 0}

    def has_campaign(self, project_name: str) -> bool:
        """Check if a project has an active Wallchain campaign."""
        data = self.load()
        name_lower = project_name.lower().replace(" ", "").replace("-", "")

        for slug in data.get("slugs", []):
            if slug.replace("-", "") == name_lower:
                return True
        return False


def load_wallchain_data() -> dict:
    """Load Wallchain campaign data (convenience function)"""
    return WallchainStore().load()

