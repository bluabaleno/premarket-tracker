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
from src.polymarket.data import SnapshotStore, PortfolioStore, LeaderboardStore, LaunchedProjectStore, KaitoStore, CookieStore, WallchainStore
from src.polymarket.data.launch_detector import update_launched_projects
from src.polymarket.analysis import compare_snapshots, calculate_portfolio_pnl
from src.polymarket.utils import setup_logging, extract_project_name

from src.polymarket.ui import generate_html_dashboard


def build_fdv_history(data_dir: Path, days: int = 14) -> dict:
    """
    Build FDV price history from historical snapshots (Polymarket + Limitless).

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

    def process_market(project, question, yes_price, volume, date):
        """Helper to process a single FDV market"""
        # Match both ">$2B" and "above $2B" patterns
        match = re.search(r'(?:>|above)\s*\$?(\d+\.?\d*)([BMK]?)', question, re.IGNORECASE)
        if not match:
            return

        val = float(match[1])
        suffix = (match[2] or '').upper()
        if suffix == 'B': val *= 1e9
        elif suffix == 'M': val *= 1e6

        label = f">${match[1]}{suffix}"

        if project not in fdv_data:
            fdv_data[project] = {'thresholds': {}}

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
            'price': yes_price
        })
        th['volume'] = max(th['volume'], volume)

    for snap_file in snapshots:
        date = snap_file.replace('snapshot_', '').replace('.json', '')
        try:
            with open(data_dir / snap_file) as f:
                data = json.load(f)
        except:
            continue

        # Process Polymarket FDV markets
        for slug, event in data.get('markets', {}).items():
            slug_lower = slug.lower()
            is_fdv_event = (
                'fdv' in slug_lower or
                'market-cap' in slug_lower or
                'valuation' in slug_lower
            )
            if not is_fdv_event:
                continue

            title = event.get('title', '')
            project = title.split(' FDV')[0].split(' market cap')[0].strip() if title else 'Unknown'

            for m_slug, m in event.get('markets', {}).items():
                process_market(
                    project,
                    m.get('question', ''),
                    m.get('yes_price', 0),
                    m.get('volume', 0),
                    date
                )

        # Process Limitless FDV markets
        for proj_name, proj in data.get('limitless', {}).get('projects', {}).items():
            for m in proj.get('markets', []):
                title = m.get('title', '').lower()
                if 'fdv' not in title and 'market cap' not in title:
                    continue

                process_market(
                    proj_name,
                    m.get('title', ''),
                    m.get('yes_price', 0),
                    m.get('volume', 0),
                    date
                )

    # Convert thresholds dict to sorted list
    result = {}
    for project, pdata in fdv_data.items():
        thresholds = list(pdata['thresholds'].values())
        thresholds.sort(key=lambda x: x['value'])
        if thresholds:
            result[project] = {'thresholds': thresholds}

    return result


def build_incentive_data(data_dir: Path, days: int = 30) -> dict:
    """
    Build per-project volume momentum and market metadata from historical
    Limitless snapshots. Used by the Incentive Allocation dashboard tab.

    Returns dict with 'markets' (per-project scoring data) and 'grant_config'.
    """
    import json
    from src.polymarket.config import Config

    snapshots = sorted([
        f for f in os.listdir(data_dir)
        if f.startswith('snapshot_') and f.endswith('.json')
    ])[-days:]

    # Phase 1: Build per-project volume history from Limitless data in snapshots
    project_histories = {}  # {name: [{date, volume, depth, market_count}, ...]}
    latest_markets = {}     # {name: [market, ...]} from most recent snapshot

    for snap_file in snapshots:
        date = snap_file.replace('snapshot_', '').replace('.json', '')
        try:
            with open(data_dir / snap_file) as f:
                data = json.load(f)
        except Exception:
            continue

        lim_projects = data.get('limitless', {}).get('projects', {})
        for proj_name, proj_data in lim_projects.items():
            markets = proj_data.get('markets', [])
            total_vol = proj_data.get('totalVolume', sum(m.get('volume', 0) for m in markets))
            total_depth = sum(m.get('liquidity', {}).get('depth', 0) for m in markets)

            if proj_name not in project_histories:
                project_histories[proj_name] = []

            project_histories[proj_name].append({
                'date': date,
                'volume': total_vol,
                'depth': total_depth,
                'market_count': len(markets),
            })

            latest_markets[proj_name] = markets

    # Phase 2: Compute momentum and TGE proximity per project
    result_markets = {}
    tge_pattern = re.compile(
        r'launch.*?(?:by\s+)?'
        r'(January|February|March|April|May|June|July|August|'
        r'September|October|November|December)\s+(\d{1,2})(?:,?\s*(\d{4}))?',
        re.IGNORECASE
    )
    month_map = {
        'january': 1, 'february': 2, 'march': 3, 'april': 4,
        'may': 5, 'june': 6, 'july': 7, 'august': 8,
        'september': 9, 'october': 10, 'november': 11, 'december': 12
    }
    today = datetime.now()

    for proj_name, history in project_histories.items():
        history.sort(key=lambda x: x['date'])

        # Volume history for sparkline
        volume_history = [{'date': h['date'], 'volume': h['volume']} for h in history]

        # Daily deltas (volume is cumulative, so delta = diff between snapshots)
        daily_deltas = []
        for i in range(1, len(history)):
            delta = history[i]['volume'] - history[i - 1]['volume']
            daily_deltas.append({'date': history[i]['date'], 'delta': max(0, delta)})

        # Momentum: compare avg daily vol last 3d vs 4-7d ago
        recent = [d['delta'] for d in daily_deltas[-3:]] if len(daily_deltas) >= 3 else [d['delta'] for d in daily_deltas]
        older = [d['delta'] for d in daily_deltas[-7:-3]] if len(daily_deltas) >= 7 else []

        avg_recent = sum(recent) / len(recent) if recent else 0
        avg_older = sum(older) / len(older) if older else 0
        avg_daily_7d = sum(d['delta'] for d in daily_deltas[-7:]) / min(7, len(daily_deltas)) if daily_deltas else 0

        if avg_older > 0:
            momentum_7d = (avg_recent - avg_older) / avg_older
        else:
            momentum_7d = 1.0 if avg_recent > 0 else 0.0

        # TGE proximity: parse launch dates from market titles
        earliest_tge = None
        earliest_tge_prob = None
        has_launch_markets = False
        markets_data = latest_markets.get(proj_name, [])

        individual = []
        for m in markets_data:
            title = m.get('title', '')
            mtype = 'fdv' if ('fdv' in title.lower() or 'market cap' in title.lower()) else 'launch'
            if 'launch' in title.lower() and 'after launch' not in title.lower():
                has_launch_markets = True
                match = tge_pattern.search(title)
                if match:
                    month_name = match.group(1).lower()
                    day = int(match.group(2))
                    year = int(match.group(3)) if match.group(3) else today.year
                    try:
                        tge_date = datetime(year, month_map[month_name], day)
                        if earliest_tge is None or tge_date < earliest_tge:
                            earliest_tge = tge_date
                            earliest_tge_prob = m.get('yes_price', 0)
                    except ValueError:
                        pass

            individual.append({
                'title': re.sub(r'[^\x00-\x7F]+', '', title).strip(),
                'slug': m.get('slug', ''),
                'volume': m.get('volume', 0),
                'yes_price': m.get('yes_price', 0),
                'liquidity_depth': m.get('liquidity', {}).get('depth', 0),
                'type': mtype,
            })

        latest = history[-1] if history else {}
        tge_days = (earliest_tge - today).days if earliest_tge else None

        result_markets[proj_name] = {
            'name': proj_name,
            'total_volume': latest.get('volume', 0),
            'market_count': latest.get('market_count', 0),
            'total_liquidity_depth': latest.get('depth', 0),
            'volume_history': volume_history,
            'daily_volume': daily_deltas,
            'momentum_7d': round(momentum_7d, 4),
            'avg_daily_volume_7d': round(avg_daily_7d, 2),
            'earliest_tge_date': earliest_tge.strftime('%Y-%m-%d') if earliest_tge else None,
            'tge_days_remaining': tge_days,
            'tge_probability': earliest_tge_prob,
            'has_launch_markets': has_launch_markets,
            'individual_markets': individual,
        }

    return {
        'markets': result_markets,
        'snapshot_dates': [f.replace('snapshot_', '').replace('.json', '') for f in snapshots],
        'grant_config': Config.GRANT_MILESTONES,
    }


def build_grant_tracking_data(data_dir: Path, grant_start_date: str) -> dict:
    """
    Compute cumulative grant progress metrics from Limitless snapshots since
    the grant start date. Creates/updates grant_tracking.json for baseline.
    """
    import json
    from src.polymarket.config import Config

    tracking_path = Config.GRANT_TRACKING_PATH
    today = datetime.now()
    start = datetime.strptime(grant_start_date, '%Y-%m-%d')
    days_elapsed = (today - start).days

    # Load or create tracking state
    if tracking_path.exists():
        with open(tracking_path) as f:
            tracking = json.load(f)
    else:
        tracking = {
            'grant_start_date': grant_start_date,
            'baseline_volume': None,
            'competitions': [],
        }

    # Load all snapshots
    snapshots = sorted([
        f for f in os.listdir(data_dir)
        if f.startswith('snapshot_') and f.endswith('.json')
    ])

    # Compute per-snapshot Limitless totals
    volume_per_snapshot = []
    for snap_file in snapshots:
        date = snap_file.replace('snapshot_', '').replace('.json', '')
        try:
            with open(data_dir / snap_file) as f:
                data = json.load(f)
        except Exception:
            continue

        lim = data.get('limitless', {}).get('projects', {})
        total_vol = sum(p.get('totalVolume', 0) for p in lim.values())
        total_depth = sum(
            sum(m.get('liquidity', {}).get('depth', 0) for m in p.get('markets', []))
            for p in lim.values()
        )
        market_count = len(lim)

        volume_per_snapshot.append({
            'date': date,
            'total_volume': round(total_vol, 2),
            'total_depth': round(total_depth, 2),
            'market_count': market_count,
        })

    # Set baseline from grant start date snapshot (or nearest before)
    if tracking['baseline_volume'] is None:
        for vs in volume_per_snapshot:
            if vs['date'] <= grant_start_date:
                tracking['baseline_volume'] = vs['total_volume']
        if tracking['baseline_volume'] is None and volume_per_snapshot:
            tracking['baseline_volume'] = volume_per_snapshot[0]['total_volume']
        # Save baseline
        with open(tracking_path, 'w') as f:
            json.dump(tracking, f, indent=2)

    baseline = tracking.get('baseline_volume', 0) or 0
    latest = volume_per_snapshot[-1] if volume_per_snapshot else {}
    cumulative_volume = (latest.get('total_volume', 0) - baseline) if latest else 0
    cumulative_volume = max(0, cumulative_volume)

    # Daily progress since grant start
    daily_progress = []
    for vs in volume_per_snapshot:
        if vs['date'] >= grant_start_date:
            daily_progress.append({
                'date': vs['date'],
                'cumulative_volume': round(max(0, vs['total_volume'] - baseline), 2),
                'oi': vs['total_depth'],
                'market_count': vs['market_count'],
            })

    return {
        'grant_start_date': grant_start_date,
        'days_elapsed': days_elapsed,
        'milestone_config': Config.GRANT_MILESTONES,
        'cumulative_volume': round(cumulative_volume, 2),
        'current_oi': latest.get('total_depth', 0),
        'market_count': latest.get('market_count', 0),
        'baseline_volume': baseline,
        'daily_progress': daily_progress,
        'volume_per_snapshot': volume_per_snapshot,
        'competitions': tracking.get('competitions', []),
    }


def build_yesterday_timeline(data_dir: Path) -> dict:
    """
    Get yesterday's timeline milestone data to compare with today's.
    Returns dict: {"ProjectName": [{"date": "2026-01-31", "prob": 0.45}, ...]}
    """
    import json
    
    snapshots = sorted([
        f for f in os.listdir(data_dir) 
        if f.startswith('snapshot_') and f.endswith('.json')
    ])
    
    # Get the second most recent snapshot (yesterday)
    if len(snapshots) < 2:
        return {}
    
    yesterday_file = snapshots[-2]
    
    try:
        with open(data_dir / yesterday_file) as f:
            data = json.load(f)
    except:
        return {}
    
    # Extract timeline milestones (same logic as dashboard buildTimelineData)
    timeline = {}
    date_pattern = re.compile(r'(?:by\s+)?(\d{4}[-/]\d{1,2}[-/]\d{1,2}|Jan(?:uary)?|Feb(?:ruary)?|Mar(?:ch)?|Apr(?:il)?|May|Jun(?:e)?|Jul(?:y)?|Aug(?:ust)?|Sep(?:tember)?|Oct(?:ober)?|Nov(?:ember)?|Dec(?:ember)?)\s*\d{0,2},?\s*\d{0,4}', re.IGNORECASE)
    
    for slug, event in data.get('markets', {}).items():
        slug_lower = slug.lower()
        # Skip FDV events
        if 'fdv' in slug_lower or 'market-cap' in slug_lower or 'valuation' in slug_lower:
            continue
        
        title = event.get('title', '')
        # Match "will X launch by" pattern
        if 'launch' not in title.lower():
            continue
            
        # Extract project name
        project = title.split(' launch')[0].split(' to launch')[0].split('Will ')[-1].strip()
        if not project or len(project) < 2:
            continue
        
        for m_slug, m in event.get('markets', {}).items():
            q = m.get('question', '')
            # Try to extract date
            match = date_pattern.search(q)
            if not match:
                continue
            
            date_str = match.group(0)
            # Simple date normalization - just store for comparison
            price = m.get('yes_price', 0)
            
            if project not in timeline:
                timeline[project] = []
            
            timeline[project].append({
                'question': q,
                'prob': price
            })
    
    return timeline

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

    # Detect and add newly launched projects (auto-detection from resolved markets)
    new_launches = update_launched_projects(current_markets, limitless_data)
    if new_launches > 0:
        print(f"🚀 Auto-detected {new_launches} new project launch(es)!")

    # Load launched projects and fetch post-TGE market volumes
    launched_store = LaunchedProjectStore()
    post_tge_volumes = launched_store.fetch_and_record_post_tge_volume(today)
    if post_tge_volumes:
        print(f"💰 Fetched post-TGE volume for {len(post_tge_volumes)} project(s)")
    launched_projects = launched_store.list_projects()
    print(f"🎯 Loaded {len(launched_projects)} launched projects")

    # Load Kaito Yaps data
    kaito_data = KaitoStore().load()
    print(f"📊 Loaded Kaito data: {len(kaito_data.get('pre_tge', []))} pre-TGE, {len(kaito_data.get('post_tge', []))} post-TGE")

    # Load Cookie campaign data
    cookie_data = CookieStore().load()
    print(f"🍪 Loaded Cookie data: {len(cookie_data.get('active_campaigns', []))} active campaigns")

    # Load Wallchain campaign data
    wallchain_data = WallchainStore().load()
    print(f"🔗 Loaded Wallchain data: {len(wallchain_data.get('active_campaigns', []))} active campaigns")

    # Build FDV history from snapshots
    fdv_history = build_fdv_history(Config.DATA_DIR, days=14)
    print(f"📈 Loaded FDV history for {len(fdv_history)} projects")

    # Build incentive allocation data from Limitless historical snapshots
    incentive_data = build_incentive_data(Config.DATA_DIR, days=30)
    print(f"💎 Built incentive data for {len(incentive_data.get('markets', {}))} Limitless projects")

    # Build grant tracking data
    grant_tracking_data = build_grant_tracking_data(Config.DATA_DIR, Config.GRANT_START_DATE)
    print(f"📊 Grant tracking: Day {grant_tracking_data.get('days_elapsed', 0)}, cumulative vol: ${grant_tracking_data.get('cumulative_volume', 0):,.0f}")

    # Generate HTML dashboard(s)
    if prev_snapshot:
        # Extract previous Limitless data from snapshot (if available)
        prev_limitless = prev_snapshot.get("limitless")

        # Determine which dashboards to generate
        generate_internal = not args.public  # Generate internal unless --public only
        generate_public = args.public or args.both

        if generate_internal:
            # Public dashboard (default) - Daily Changes + Timeline only
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
                wallchain_data,
                public_mode=True,
                prev_limitless_data=prev_limitless,
                fdv_history=fdv_history,
                incentive_data=incentive_data,
                grant_tracking_data=grant_tracking_data
            )

            # Internal dashboard - all tabs including Launched, Portfolio, etc.
            internal_output = os.path.join(os.path.dirname(Config.DASHBOARD_OUTPUT), "internal_dashboard.html")
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
                wallchain_data,
                public_mode=False,
                output_path=internal_output,
                prev_limitless_data=prev_limitless,
                fdv_history=fdv_history,
                incentive_data=incentive_data,
                grant_tracking_data=grant_tracking_data
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
                wallchain_data,
                public_mode=True,
                output_path=public_output,
                prev_limitless_data=prev_limitless,
                fdv_history=fdv_history,
                incentive_data=incentive_data,
                grant_tracking_data=grant_tracking_data
            )

    # Check for new post-TGE markets on Limitless
    if limitless_data and limitless_data.get("projects"):
        new_markets = launched_store.check_all_for_new_markets(limitless_data)
        if new_markets:
            print(f"\n{'='*60}")
            print("🔍 NEW POST-TGE MARKETS DISCOVERED")
            print(f"{'='*60}")
            for project_id, markets in new_markets.items():
                project = launched_store.get_project(project_id)
                ticker = project.get("ticker", "???") if project else "???"
                print(f"\n${ticker} ({project_id}) - {len(markets)} new market(s):")
                for m in markets:
                    price_str = f"{m['yes_price']*100:.1f}%" if m.get('yes_price') else "N/A"
                    vol_str = f"${m['volume']:,.0f}" if m.get('volume') else "$0"
                    print(f"   • {m['title']}")
                    print(f"     slug: {m['slug']}")
                    print(f"     price: {price_str} | vol: {vol_str}")
            print(f"\n💡 To add: python -m src.polymarket.data.launched add <project_id> <slug>")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Polymarket Daily Price Tracker")
    parser.add_argument("--public", action="store_true", help="Generate public dashboard only (Daily Changes + Timeline)")
    parser.add_argument("--both", action="store_true", help="Generate both internal and public dashboards")
    args = parser.parse_args()

    main(args)
