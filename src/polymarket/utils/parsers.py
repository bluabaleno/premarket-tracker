"""
Parsing utilities for Polymarket Tracker

Consolidated functions for extracting project names, event slugs,
and thresholds from market titles and URLs.
"""

import re
from typing import Optional
from urllib.parse import urlparse


# Patterns for extracting project names from titles
PROJECT_NAME_PATTERNS = [
    r'^Will\s+(.+?)\s+launch',
    r'^Will\s+(.+?)\s+perform',
    r'^Will\s+(.+?)\s+IPO',
    r'^Will\s+(.+?)\s+(?:token|TGE|have)',
    r'^(.+?)\s+market cap',
    r'^(.+?)\s+FDV\s+above',
    r'^(.+?)\s+airdrop',
    r'^(.+?)\s+IPO\s+closing',
    r'^(.+?)\s+public\s+sale',
    r'^(.+?)\s+(?:token|TGE|launch|FDV|market|above|below)',
    r'^(.+?)\s+(?:trading|airdrop)',
    r'^Over\s+\$\d+[MK]?\s+committed\s+to\s+the\s+(.+?)\s+public',
    r'^What\s+day\s+will\s+the\s+(.+?)\s+airdrop',
]

# Suffixes to remove from project names
SUFFIX_CLEANUP_PATTERN = r'\s+(Protocol|Network|Labs|Finance)$'

# Emoji pattern (for Limitless titles that have emoji prefixes)
EMOJI_PATTERN = r'^[\U0001F300-\U0001F9FF\s]+'


def extract_project_name(title: str, remove_emoji: bool = False) -> str:
    """
    Extract project name from market/event title.

    Args:
        title: The market or event title
        remove_emoji: If True, strip emoji prefixes (useful for Limitless)

    Returns:
        Extracted project name

    Examples:
        >>> extract_project_name("Will Zama launch a token in 2025?")
        'Zama'
        >>> extract_project_name("Infinex FDV above $3B one day after launch?")
        'Infinex'
    """
    if not title:
        return "Unknown"

    # Remove emoji prefix if requested
    if remove_emoji:
        title = re.sub(EMOJI_PATTERN, '', title).strip()

    # Try each pattern
    for pattern in PROJECT_NAME_PATTERNS:
        match = re.search(pattern, title, re.IGNORECASE)
        if match:
            name = match.group(1).strip()
            # Clean up common suffixes
            name = re.sub(SUFFIX_CLEANUP_PATTERN, '', name, flags=re.IGNORECASE)
            return name

    # Fallback: split on common keywords and take first part
    fallback = re.split(
        r'\s+(market|FDV|launch|airdrop|IPO|token|above)',
        title,
        flags=re.IGNORECASE
    )
    if fallback and fallback[0].strip():
        return fallback[0].strip()

    # Last resort: truncate title
    return title[:30]


def extract_event_slug(url: str) -> Optional[str]:
    """
    Extract event slug from Polymarket URL.

    Args:
        url: Full Polymarket URL

    Returns:
        Event slug or None if not found

    Examples:
        >>> extract_event_slug("https://polymarket.com/event/zama-fdv-above")
        'zama-fdv-above'
    """
    if not url:
        return None

    try:
        parsed = urlparse(url)
        parts = parsed.path.split("/")

        if "event" in parts:
            idx = parts.index("event")
            if idx + 1 < len(parts):
                return parts[idx + 1]
    except (ValueError, IndexError):
        pass

    return None


def extract_threshold(question: str) -> Optional[str]:
    """
    Extract FDV/value threshold from market question.

    Args:
        question: Market question text

    Returns:
        Normalized threshold string (e.g., "800m", "2b") or None

    Examples:
        >>> extract_threshold("Zama FDV above $800M one day after launch?")
        '800m'
        >>> extract_threshold("Infinex FDV above $2B one day after launch?")
        '2b'
    """
    if not question:
        return None

    match = re.search(r'\$?([\d.]+)\s*(b|m|k)', question, re.IGNORECASE)
    if match:
        return (match.group(1) + match.group(2)).lower()

    return None


def normalize_project_name(name: str) -> str:
    """
    Normalize project name for matching across platforms.

    Args:
        name: Project name

    Returns:
        Lowercase alphanumeric version for comparison

    Examples:
        >>> normalize_project_name("Zama Protocol")
        'zamaprotocol'
        >>> normalize_project_name("USD.AI")
        'usdai'
    """
    return re.sub(r'[^a-z0-9]', '', name.lower())


def format_volume(volume: float) -> str:
    """
    Format volume as human-readable string.

    Args:
        volume: Volume in dollars

    Returns:
        Formatted string like "$1.2M" or "$500K"
    """
    if volume >= 1_000_000:
        return f"${volume / 1_000_000:.1f}M"
    elif volume >= 1_000:
        return f"${volume / 1_000:.0f}K"
    else:
        return f"${volume:.0f}"
