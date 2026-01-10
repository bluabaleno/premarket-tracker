"""
Polymarket Daily Price Tracker (Refactored)

Clean orchestrator that uses modular components.

Usage:
    python daily_tracker.py              # Generate internal dashboard (all tabs)
    python daily_tracker.py --public     # Generate public dashboard only
    python daily_tracker.py --both       # Generate both dashboards
"""

import argparse
import os
import re
from datetime import datetime
from pathlib import Path
from src.polymarket.config import Config
from src.polymarket.api import GammaClient, LimitlessClient
from src.polymarket.data import SnapshotStore, PortfolioStore, LeaderboardStore, LaunchedProjectStore, KaitoStore, CookieStore
from src.polymarket.analysis import compare_snapshots, calculate_portfolio_pnl
from src.polymarket.utils import setup_logging, extract_project_name

from src.polymarket.ui import generate_html_dashboard


def build_fdv_history(data_dir: Path, days: int = 14) -> dict:
    """
    Build FDV price history from historical snapshots.
    
    Returns dict: {
        "ProjectName": {
            "thresholds": [
                {
                    "label": ">$2B",
                    "value": 2000000000,
                    "volume": 25000000,
                    "history": [{"date": "2026-01-05", "price": 0.85}, ...]
                }
            ]
        }
    }
    """
    import json
    
    snapshots = sorted([
        f for f in os.listdir(data_dir) 
        if f.startswith('snapshot_') and f.endswith('.json')
    ])[-days:]
    
    # Build per-project, per-threshold history
    fdv_data = {}
    
    for snap_file in snapshots:
        date = snap_file.replace('snapshot_', '').replace('.json', '')
        try:
            with open(data_dir / snap_file) as f:
                data = json.load(f)
        except:
            continue
        
        for slug, event in data.get('markets', {}).items():
            slug_lower = slug.lower()
            # Match FDV events by slug pattern
            is_fdv_event = (
                'fdv' in slug_lower or
                'market-cap' in slug_lower or
                'valuation' in slug_lower
            )
            if not is_fdv_event:
                continue
                
            title = event.get('title', '')
            # Extract project name more reliably
            project = title.split(' FDV')[0].split(' market cap')[0].strip() if title else 'Unknown'
            
            if project not in fdv_data:
                fdv_data[project] = {'thresholds': {}}
            
            for m_slug, m in event.get('markets', {}).items():
                q = m.get('question', '')
                # Match both ">$2B" and "above $2B" patterns
                match = re.search(r'(?:>|above)\s*\$?(\d+\.?\d*)([BMK]?)', q, re.IGNORECASE)
                if not match:
                    continue
                    
                val = float(match[1])
                suffix = (match[2] or '').upper()
                if suffix == 'B': val *= 1e9
                elif suffix == 'M': val *= 1e6
                
                label = f">${match[1]}{suffix}"
                
                if label not in fdv_data[project]['thresholds']:
                    fdv_data[project]['thresholds'][label] = {
                        'label': label,
                        'value': val,
                        'volume': 0,
                        'history': []
                    }
                
                th = fdv_data[project]['thresholds'][label]
                th['history'].append({
                    'date': date,
                    'price': m.get('yes_price', 0)
                })
                th['volume'] = max(th['volume'], m.get('volume', 0))
    
    # Convert thresholds dict to sorted list
    result = {}
    for project, data in fdv_data.items():
        thresholds = list(data['thresholds'].values())
        thresholds.sort(key=lambda x: x['value'])
        if thresholds:
            result[project] = {'thresholds': thresholds}
    
    return result


def display_changes(changes, limit=20):
    """Display price changes nicely"""
    if not changes:
        print("\n📊 No price changes detected (or no previous data)")
        return

    print(f"\n{'='*80}")
    print(f"📊 TOP {min(limit, len(changes))} PRICE CHANGES")
    print(f"{'='*80}\n")

    for c in changes[:limit]:
        arrow = "🔺" if c["change"] > 0 else "🔻"
        color_sign = "+" if c["change"] > 0 else ""

        print(f"{arrow} {c['market'][:60]}")
        print(f"   {c['prev_price']*100:.1f}% → {c['current_price']*100:.1f}% ({color_sign}{c['change']*100:.1f}pp / {color_sign}{c['change_pct']:.1f}%)")
        print()


def main(args=None):
    """Main orchestrator function"""
    # Default args if not provided
    if args is None:
        class DefaultArgs:
            public = False
            both = False
        args = DefaultArgs()

    logger = setup_logging()

    print(f"🚀 Running Polymarket Price Tracker - {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    print("-" * 60)

    # Ensure directories exist
    Config.ensure_dirs()

    # Initialize stores
    snapshot_store = SnapshotStore()

    # Fetch current market data from both platforms
    print("\n📡 Fetching from Gamma API (tag_slug=pre-market)...")
    gamma = GammaClient()
    current_markets = gamma.fetch_pre_markets()
    print(f"   Found {len(current_markets)} events")

    # Fetch Limitless data
    print("\n📡 Fetching from Limitless API...")
    limitless_data = None
    try:
        limitless = LimitlessClient()
        limitless_data = limitless.fetch_markets()
        print(f"   Found {len(limitless_data.get('projects', {}))} projects")
    except Exception as e:
        print(f"⚠️  Limitless fetch failed: {e}")
        limitless_data = {"error": str(e), "projects": {}}

    # Save today's snapshot (includes both Polymarket and Limitless)
    today = datetime.now().strftime("%Y-%m-%d")
    snapshot_store.save(current_markets, today, limitless_data=limitless_data)

    # Load previous snapshot and compare
    prev_snapshot, prev_date = snapshot_store.get_previous(exclude_date=today)

    if prev_snapshot:
        print(f"\n📅 Comparing with previous snapshot from {prev_date}")
        changes = compare_snapshots({"markets": current_markets}, prev_snapshot)
        display_changes(changes)
    else:
        print("\n📝 First run - no previous data to compare")
        print("   Run again tomorrow to see changes!")
        changes = []

    # Summary
    print(f"\n{'='*80}")
    print("📈 MARKET SUMMARY")
    print(f"{'='*80}")

    # Polymarket stats
    poly_volume = sum(e.get("volume", 0) for e in current_markets.values())
    poly_markets = sum(
        1 for e in current_markets.values()
        for m in e.get("markets", {}).values()
        if not m.get("closed")
    )

    # Limitless stats
    lim_projects = limitless_data.get("projects", {}) if limitless_data else {}
    lim_volume = sum(p.get("totalVolume", 0) for p in lim_projects.values())
    lim_markets = sum(len(p.get("markets", [])) for p in lim_projects.values())

    # Format volumes
    def fmt_vol(v):
        if v >= 1_000_000:
            return f"${v/1_000_000:.1f}M"
        elif v >= 1_000:
            return f"${v/1_000:.0f}K"
        return f"${v:.0f}"

    print(f"Total Volume: {fmt_vol(poly_volume)} (Polymarket) + {fmt_vol(lim_volume)} (Limitless)")
    print(f"Active Markets: {poly_markets} (Poly) + {lim_markets} (Lim)")
    print(f"Projects Tracked: {len(current_markets)} (Poly) + {len(lim_projects)} (Lim)")

    # Load supplementary data
    leaderboard_data = LeaderboardStore().load()

    # Load portfolio and calculate P&L
    portfolio = PortfolioStore().load()
    portfolio_pnl = calculate_portfolio_pnl(
        portfolio, current_markets, limitless_data
    )
    print(f"📁 Loaded {len(portfolio_pnl)} portfolio positions")

    # Load launched projects
    launched_store = LaunchedProjectStore()
    launched_projects = launched_store.list_projects()
    print(f"🎯 Loaded {len(launched_projects)} launched projects")

    # Load Kaito Yaps data
    kaito_data = KaitoStore().load()
    print(f"📊 Loaded Kaito data: {len(kaito_data.get('pre_tge', []))} pre-TGE, {len(kaito_data.get('post_tge', []))} post-TGE")

    # Load Cookie campaign data
    cookie_data = CookieStore().load()
    print(f"🍪 Loaded Cookie data: {len(cookie_data.get('active_campaigns', []))} active campaigns")

    # Build FDV history from snapshots
    fdv_history = build_fdv_history(Config.DATA_DIR, days=14)
    print(f"📈 Loaded FDV history for {len(fdv_history)} projects")

    # Generate HTML dashboard(s)
    if prev_snapshot:
        # Extract previous Limitless data from snapshot (if available)
        prev_limitless = prev_snapshot.get("limitless")

        # Determine which dashboards to generate
        generate_internal = not args.public  # Generate internal unless --public only
        generate_public = args.public or args.both

        if generate_internal:
            generate_html_dashboard(
                current_markets,
                prev_snapshot,
                prev_date,
                limitless_data,
                leaderboard_data,
                portfolio_pnl,
                launched_projects,
                kaito_data,
                cookie_data,
                public_mode=False,
                prev_limitless_data=prev_limitless,
                fdv_history=fdv_history
            )

        if generate_public:
            # Public dashboard goes to a separate file
            public_output = os.path.join(os.path.dirname(Config.DASHBOARD_OUTPUT), "public_dashboard.html")
            generate_html_dashboard(
                current_markets,
                prev_snapshot,
                prev_date,
                limitless_data,
                leaderboard_data,
                portfolio_pnl,
                launched_projects,
                kaito_data,
                cookie_data,
                public_mode=True,
                output_path=public_output,
                prev_limitless_data=prev_limitless
            )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Polymarket Daily Price Tracker")
    parser.add_argument("--public", action="store_true", help="Generate public dashboard only (Daily Changes + Timeline)")
    parser.add_argument("--both", action="store_true", help="Generate both internal and public dashboards")
    args = parser.parse_args()

    main(args)
