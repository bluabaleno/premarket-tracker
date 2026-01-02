"""
Polymarket Daily Price Tracker
Tracks market odds over time and shows daily changes
Now supports fetching directly from API (no more manual CSV scraping!)
"""

import csv
import json
import os
import requests
from datetime import datetime
from urllib.parse import urlparse
# Try to import CLOB client (optional - for live order book prices)
try:
    from py_clob_client.client import ClobClient
    clob = ClobClient("https://clob.polymarket.com")
    CLOB_AVAILABLE = True
except ImportError:
    clob = None
    CLOB_AVAILABLE = False
    print("⚠️  py_clob_client not installed - using Gamma API prices only")

# Config
DATA_DIR = "/Users/jacques.whales/PredictionMarkets/Polymarket/data"
CSV_PATH = "/Users/jacques.whales/PredictionMarkets/Polymarket/polymarketPreMarkets121925.csv"
GAMMA_API = "https://gamma-api.polymarket.com"
USE_API = True  # Set to True to fetch from API instead of CSV

def ensure_data_dir():
    """Create data directory if it doesn't exist"""
    os.makedirs(DATA_DIR, exist_ok=True)

def get_snapshot_path(date_str=None):
    """Get path for daily snapshot file"""
    if date_str is None:
        date_str = datetime.now().strftime("%Y-%m-%d")
    return os.path.join(DATA_DIR, f"snapshot_{date_str}.json")

def extract_event_slug(url):
    """Extract event slug from Polymarket URL"""
    parsed = urlparse(url)
    parts = parsed.path.split("/")
    if "event" in parts:
        idx = parts.index("event")
        if idx + 1 < len(parts):
            return parts[idx + 1]
    return None

def get_event_from_gamma(event_slug):
    """Fetch event data from Gamma API"""
    url = f"https://gamma-api.polymarket.com/events?slug={event_slug}"
    try:
        resp = requests.get(url, timeout=10)
        resp.raise_for_status()
        data = resp.json()
        return data[0] if data else None
    except Exception as e:
        print(f"Error fetching {event_slug}: {e}")
        return None

def get_live_price(token_id):
    """Get live price from CLOB API"""
    if not CLOB_AVAILABLE:
        return None
    try:
        mid = clob.get_midpoint(token_id)
        return float(mid.get('mid', 0)) if mid else None
    except:
        return None

def fetch_all_markets(csv_path):
    """Fetch all markets from CSV and get current prices"""
    markets_data = {}
    
    with open(csv_path, 'r') as f:
        reader = csv.DictReader(f)
        seen_slugs = set()
        
        for row in reader:
            event_url = row.get("h-fit href", "")
            if not event_url or not event_url.startswith("http"):
                continue
            
            slug = extract_event_slug(event_url)
            if not slug or slug in seen_slugs:
                continue
            seen_slugs.add(slug)
            
            event = get_event_from_gamma(slug)
            if not event:
                continue
            
            event_data = {
                "title": event.get("title"),
                "volume": float(event.get("volume") or 0),
                "liquidity": float(event.get("liquidity") or 0),
                "markets": {}
            }
            
            for market in event.get("markets", []):
                outcomes = json.loads(market.get("outcomes", "[]"))
                outcome_prices = json.loads(market.get("outcomePrices", "[]"))
                clob_token_ids = json.loads(market.get("clobTokenIds", "[]"))
                
                market_slug = market.get("slug")
                yes_price = float(outcome_prices[0]) if outcome_prices else 0
                
                # Try to get live CLOB price
                if clob_token_ids:
                    live_price = get_live_price(clob_token_ids[0])
                    if live_price is not None:
                        yes_price = live_price
                
                event_data["markets"][market_slug] = {
                    "question": market.get("question"),
                    "yes_price": yes_price,
                    "volume": float(market.get("volume") or 0),
                    "closed": market.get("closed", False)
                }
            
            markets_data[slug] = event_data
    
    return markets_data

def fetch_markets_from_api():
    """Fetch all pre-market events directly from Gamma API (no CSV needed!)"""
    markets_data = {}
    
    url = f"{GAMMA_API}/events"
    params = {
        "tag_slug": "pre-market",
        "limit": 200,
        "order": "volume",
        "ascending": "false"
    }
    
    try:
        resp = requests.get(url, params=params, timeout=30)
        resp.raise_for_status()
        events = resp.json()
    except Exception as e:
        print(f"Error fetching from Gamma API: {e}")
        return markets_data
    
    for event in events:
        event_slug = event.get("slug")
        event_data = {
            "title": event.get("title"),
            "volume": float(event.get("volume") or 0),
            "liquidity": float(event.get("liquidity") or 0),
            "closed": event.get("closed", False),
            "markets": {}
        }
        
        for market in event.get("markets", []):
            outcomes = json.loads(market.get("outcomes", "[]"))
            outcome_prices = json.loads(market.get("outcomePrices", "[]"))
            clob_token_ids = json.loads(market.get("clobTokenIds", "[]"))
            
            market_slug = market.get("slug")
            yes_price = float(outcome_prices[0]) if outcome_prices else 0
            
            # Get live CLOB price for active markets
            if clob_token_ids and not market.get("closed"):
                live_price = get_live_price(clob_token_ids[0])
                if live_price is not None:
                    yes_price = live_price
            
            event_data["markets"][market_slug] = {
                "question": market.get("question"),
                "yes_price": yes_price,
                "volume": float(market.get("volume") or 0),
                "closed": market.get("closed", False)
            }
        
        markets_data[event_slug] = event_data
    
    return markets_data

def save_snapshot(markets_data, date_str=None):
    """Save daily snapshot"""
    ensure_data_dir()
    snapshot = {
        "timestamp": datetime.now().isoformat(),
        "date": date_str or datetime.now().strftime("%Y-%m-%d"),
        "markets": markets_data
    }
    
    path = get_snapshot_path(date_str)
    with open(path, 'w') as f:
        json.dump(snapshot, f, indent=2)
    
    print(f"✅ Saved snapshot to {path}")
    return path

def load_snapshot(date_str):
    """Load a snapshot by date"""
    path = get_snapshot_path(date_str)
    if os.path.exists(path):
        with open(path, 'r') as f:
            return json.load(f)
    return None

def get_previous_snapshot():
    """Find the most recent previous snapshot"""
    ensure_data_dir()
    today = datetime.now().strftime("%Y-%m-%d")
    
    files = sorted([f for f in os.listdir(DATA_DIR) if f.startswith("snapshot_") and f.endswith(".json")])
    
    for f in reversed(files):
        date = f.replace("snapshot_", "").replace(".json", "")
        if date != today:
            return load_snapshot(date), date
    
    return None, None

def compare_snapshots(current, previous):
    """Compare two snapshots and return changes"""
    changes = []
    
    for event_slug, event_data in current.get("markets", {}).items():
        prev_event = previous.get("markets", {}).get(event_slug, {})
        
        for market_slug, market_data in event_data.get("markets", {}).items():
            if market_data.get("closed"):
                continue
                
            prev_market = prev_event.get("markets", {}).get(market_slug, {})
            current_price = market_data.get("yes_price", 0)
            prev_price = prev_market.get("yes_price")
            
            if prev_price is not None and prev_price != current_price:
                change = current_price - prev_price
                change_pct = (change / prev_price * 100) if prev_price > 0 else 0
                
                changes.append({
                    "event": event_data.get("title"),
                    "market": market_data.get("question"),
                    "prev_price": prev_price,
                    "current_price": current_price,
                    "change": change,
                    "change_pct": change_pct
                })
    
    return sorted(changes, key=lambda x: abs(x["change_pct"]), reverse=True)

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

def run_daily_update():
    """Main function to run daily update"""
    print(f"🚀 Running Polymarket Price Tracker - {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    print("-" * 60)
    
    # Fetch current data (from API or CSV)
    if USE_API:
        print("\n📡 Fetching from Gamma API (tag_slug=pre-market)...")
        current_markets = fetch_markets_from_api()
    else:
        print("\n📡 Fetching from CSV + Gamma API...")
        current_markets = fetch_all_markets(CSV_PATH)
    print(f"   Found {len(current_markets)} events")
    
    # Save today's snapshot
    today = datetime.now().strftime("%Y-%m-%d")
    save_snapshot(current_markets, today)
    
    # Load previous snapshot and compare
    prev_snapshot, prev_date = get_previous_snapshot()
    
    if prev_snapshot:
        print(f"\n📅 Comparing with previous snapshot from {prev_date}")
        current_snapshot = {"markets": current_markets}
        changes = compare_snapshots(current_snapshot, prev_snapshot)
        display_changes(changes)
    else:
        print("\n📝 First run - no previous data to compare")
        print("   Run again tomorrow to see changes!")
    
    # Summary
    print(f"\n{'='*80}")
    print("📈 MARKET SUMMARY")
    print(f"{'='*80}")
    
    total_volume = sum(e.get("volume", 0) for e in current_markets.values())
    active_markets = sum(
        1 for e in current_markets.values() 
        for m in e.get("markets", {}).values() 
        if not m.get("closed")
    )
    
    print(f"Total Volume: ${total_volume:,.0f}")
    print(f"Active Markets: {active_markets}")
    print(f"Events Tracked: {len(current_markets)}")

def generate_report(output_format="csv"):
    """Generate a report of current prices with changes"""
    current_markets = fetch_all_markets(CSV_PATH)
    prev_snapshot, prev_date = get_previous_snapshot()
    
    rows = []
    for event_slug, event_data in current_markets.items():
        prev_event = prev_snapshot.get("markets", {}).get(event_slug, {}) if prev_snapshot else {}
        
        for market_slug, market_data in event_data.get("markets", {}).items():
            prev_market = prev_event.get("markets", {}).get(market_slug, {})
            current_price = market_data.get("yes_price", 0)
            prev_price = prev_market.get("yes_price")
            
            change = (current_price - prev_price) if prev_price is not None else None
            
            rows.append({
                "event": event_data.get("title"),
                "market": market_data.get("question"),
                "yes_pct": round(current_price * 100, 1),
                "prev_pct": round(prev_price * 100, 1) if prev_price else None,
                "change_pp": round(change * 100, 1) if change else None,
                "volume": market_data.get("volume"),
                "closed": market_data.get("closed")
            })
    
    if output_format == "csv":
        output_path = os.path.join(DATA_DIR, f"report_{datetime.now().strftime('%Y-%m-%d')}.csv")
        with open(output_path, 'w', newline='') as f:
            writer = csv.DictWriter(f, fieldnames=rows[0].keys())
            writer.writeheader()
            writer.writerows(rows)
        print(f"📊 Report saved to {output_path}")
        return output_path
    
    return rows

def generate_html_dashboard(current_markets, prev_snapshot, prev_date):
    """Generate an HTML dashboard with data embedded, grouped by PROJECT"""
    import re
    
    def extract_project_name(title):
        """Extract project name from event title"""
        # Common patterns to extract project names
        patterns = [
            r'^Will\s+(.+?)\s+launch',
            r'^Will\s+(.+?)\s+perform',
            r'^Will\s+(.+?)\s+IPO',
            r'^(.+?)\s+market cap',
            r'^(.+?)\s+FDV\s+above',
            r'^(.+?)\s+airdrop',
            r'^(.+?)\s+IPO\s+closing',
            r'^(.+?)\s+public\s+sale',
            r'^Over\s+\$\d+[MK]?\s+committed\s+to\s+the\s+(.+?)\s+public',
            r'^What\s+day\s+will\s+the\s+(.+?)\s+airdrop',
        ]
        
        for pattern in patterns:
            match = re.search(pattern, title, re.IGNORECASE)
            if match:
                name = match.group(1).strip()
                # Clean up common suffixes
                name = re.sub(r'\s+(Protocol|Network|Labs|Finance)$', '', name, flags=re.IGNORECASE)
                return name
        
        # Fallback: use first word(s) before common keywords
        fallback = re.split(r'\s+(market|FDV|launch|airdrop|IPO|token|above)', title, flags=re.IGNORECASE)
        if fallback:
            return fallback[0].strip()
        
        return title[:30]  # Last resort: truncate title
    
    # First pass: collect all markets with their project associations
    projects_dict = {}
    
    for event_slug, event_data in current_markets.items():
        prev_event = prev_snapshot.get("markets", {}).get(event_slug, {}) if prev_snapshot else {}
        
        title = event_data.get("title", "")
        project_name = extract_project_name(title)
        
        if project_name not in projects_dict:
            projects_dict[project_name] = {
                "name": project_name,
                "events": [],
                "totalChange": 0,
                "totalVolume": 0,
                "hasOpenMarkets": False
            }
        
        event_info = {
            "slug": event_slug,
            "title": title,
            "volume": event_data.get("volume", 0),
            "markets": [],
            "totalChange": 0,
            "allClosed": True  # Assume closed until we find an open market
        }
        
        for market_slug, market_data in event_data.get("markets", {}).items():
            is_closed = market_data.get("closed", False)
            
            prev_market = prev_event.get("markets", {}).get(market_slug, {})
            current_price = market_data.get("yes_price", 0)
            prev_price = prev_market.get("yes_price")
            
            change = (current_price - prev_price) if prev_price is not None else 0
            
            market_info = {
                "question": market_data.get("question", ""),
                "oldPrice": prev_price,
                "newPrice": current_price,
                "change": change,
                "direction": "up" if change > 0 else ("down" if change < 0 else "none"),
                "closed": is_closed
            }
            
            event_info["markets"].append(market_info)
            if not is_closed:
                event_info["allClosed"] = False
                event_info["totalChange"] += abs(change)
        
        # Sort markets within event by absolute change
        event_info["markets"].sort(key=lambda x: abs(x["change"]), reverse=True)
        
        if event_info["markets"]:
            projects_dict[project_name]["events"].append(event_info)
            projects_dict[project_name]["totalVolume"] += event_info["volume"]
            if not event_info["allClosed"]:
                projects_dict[project_name]["hasOpenMarkets"] = True
                projects_dict[project_name]["totalChange"] += event_info["totalChange"]
    
    # Convert to list and sort by total change (open projects first, then by change)
    projects_data = list(projects_dict.values())
    # Filter out projects with no events at all
    projects_data = [p for p in projects_data if p["events"]]
    # Sort: open projects first by change, then closed projects
    projects_data.sort(key=lambda x: (not x["hasOpenMarkets"], -x["totalChange"]))
    
    # Sort events within each project by change
    for project in projects_data:
        project["events"].sort(key=lambda x: x["totalChange"], reverse=True)
    
    # Calculate stats
    total_changes = sum(1 for p in projects_data for e in p["events"] for m in e["markets"] if m["change"] != 0)
    up_count = sum(1 for p in projects_data for e in p["events"] for m in e["markets"] if m["change"] > 0)
    down_count = sum(1 for p in projects_data for e in p["events"] for m in e["markets"] if m["change"] < 0)
    
    today = datetime.now().strftime("%Y-%m-%d")
    
    html = f'''<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Polymarket Daily Changes - {today}</title>
    <style>
        :root {{
            --bg-primary: #0a0a0f;
            --bg-secondary: #12121a;
            --bg-card: #1a1a25;
            --text-primary: #ffffff;
            --text-secondary: #8b8b9e;
            --accent: #6366f1;
            --green: #22c55e;
            --green-light: rgba(34, 197, 94, 0.15);
            --red: #ef4444;
            --red-light: rgba(239, 68, 68, 0.15);
            --border: rgba(255, 255, 255, 0.08);
        }}
        * {{ margin: 0; padding: 0; box-sizing: border-box; }}
        body {{
            font-family: 'Inter', -apple-system, BlinkMacSystemFont, sans-serif;
            background: var(--bg-primary);
            color: var(--text-primary);
            min-height: 100vh;
            line-height: 1.5;
        }}
        .container {{ max-width: 1200px; margin: 0 auto; padding: 2rem; }}
        header {{ text-align: center; margin-bottom: 2rem; }}
        h1 {{
            font-size: 2rem;
            font-weight: 700;
            background: linear-gradient(135deg, #fff, #6366f1);
            -webkit-background-clip: text;
            background-clip: text;
            -webkit-text-fill-color: transparent;
            margin-bottom: 0.5rem;
        }}
        .subtitle {{ color: var(--text-secondary); }}
        .date-range {{
            display: inline-block;
            background: var(--bg-card);
            padding: 0.5rem 1rem;
            border-radius: 8px;
            margin-top: 1rem;
            font-size: 0.875rem;
        }}
        .stats-row {{
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(140px, 1fr));
            gap: 1rem;
            margin-bottom: 2rem;
        }}
        .stat-card {{
            background: var(--bg-card);
            border-radius: 12px;
            padding: 1.25rem;
            text-align: center;
        }}
        .stat-value {{ font-size: 1.75rem; font-weight: 700; }}
        .stat-value.green {{ color: var(--green); }}
        .stat-value.red {{ color: var(--red); }}
        .stat-label {{ color: var(--text-secondary); font-size: 0.75rem; margin-top: 0.25rem; }}
        
        .search-box {{
            margin-bottom: 1.5rem;
        }}
        .search-box input {{
            width: 100%;
            padding: 0.75rem 1rem;
            background: var(--bg-card);
            border: 1px solid var(--border);
            border-radius: 8px;
            color: var(--text-primary);
            font-size: 0.875rem;
        }}
        .search-box input:focus {{
            outline: none;
            border-color: var(--accent);
        }}
        
        .events-list {{ display: flex; flex-direction: column; gap: 1rem; }}
        
        .event-card {{
            background: var(--bg-card);
            border-radius: 12px;
            overflow: hidden;
        }}
        .event-header {{
            padding: 1rem 1.25rem;
            display: flex;
            justify-content: space-between;
            align-items: center;
            border-bottom: 1px solid var(--border);
            cursor: pointer;
        }}
        .event-header:hover {{ background: var(--bg-secondary); }}
        .event-title {{ font-weight: 600; font-size: 1rem; color: var(--text-primary); text-decoration: none; }}
        .event-title:hover {{ color: var(--accent); }}
        .event-meta {{
            display: flex;
            gap: 1rem;
            align-items: center;
        }}
        .event-volume {{
            font-size: 0.75rem;
            color: var(--text-secondary);
            background: var(--bg-secondary);
            padding: 0.25rem 0.5rem;
            border-radius: 4px;
        }}
        .event-change {{
            font-size: 0.875rem;
            font-weight: 600;
        }}
        .event-change.up {{ color: var(--green); }}
        .event-change.down {{ color: var(--red); }}
        
        .toggle-icon {{
            font-size: 0.8rem;
            transition: transform 0.2s;
            margin-right: 0.5rem;
        }}
        .event-card.collapsed .toggle-icon {{
            transform: rotate(-90deg);
        }}
        .event-card.collapsed .markets-container {{
            display: none;
        }}
        .total-change {{
            font-size: 0.75rem;
            padding: 0.25rem 0.5rem;
            border-radius: 4px;
            font-weight: 600;
        }}
        .total-change.positive {{
            background: var(--green-light);
            color: var(--green);
        }}
        .total-change.negative {{
            background: var(--red-light);
            color: var(--red);
        }}
        .total-change.neutral {{
            background: var(--bg-secondary);
            color: var(--text-secondary);
        }}
        
        .markets-table {{
            width: 100%;
            border-collapse: collapse;
        }}
        .markets-table th {{
            padding: 0.5rem 1rem;
            text-align: left;
            font-size: 0.7rem;
            color: var(--text-secondary);
            text-transform: uppercase;
            background: var(--bg-secondary);
        }}
        .markets-table td {{
            padding: 0.75rem 1rem;
            border-top: 1px solid var(--border);
            font-size: 0.875rem;
        }}
        .market-question {{
            max-width: 400px;
            overflow: hidden;
            text-overflow: ellipsis;
            white-space: nowrap;
        }}
        .price-cell {{ text-align: right; font-weight: 500; min-width: 60px; }}
        .change-cell {{ text-align: right; min-width: 80px; font-weight: 600; }}
        .change-cell.up {{ color: var(--green); }}
        .change-cell.down {{ color: var(--red); }}
        .change-cell.none {{ color: var(--text-secondary); }}
        
        .price-bar-bg {{
            width: 100px;
            height: 8px;
            background: var(--bg-primary);
            border-radius: 4px;
            overflow: hidden;
        }}
        .price-bar {{
            height: 100%;
            border-radius: 4px;
            transition: width 0.3s;
        }}
        .price-bar.high {{ background: var(--green); }}
        .price-bar.mid {{ background: #f59e0b; }}
        .price-bar.low {{ background: var(--red); }}
        
        .no-changes {{ color: var(--text-secondary); padding: 0.75rem 1rem; font-size: 0.875rem; }}
        
        .closed-badge {{
            font-size: 0.65rem;
            padding: 0.15rem 0.4rem;
            border-radius: 4px;
            background: rgba(239, 68, 68, 0.2);
            color: var(--red);
            margin-left: 0.5rem;
            font-weight: 600;
        }}
        
        .toggle-container {{
            display: flex;
            align-items: center;
            gap: 0.5rem;
            margin-bottom: 1rem;
        }}
        .toggle-switch {{
            position: relative;
            width: 44px;
            height: 24px;
            background: var(--bg-card);
            border-radius: 12px;
            cursor: pointer;
            border: 1px solid var(--border);
            transition: background 0.2s;
        }}
        .toggle-switch.active {{
            background: var(--accent);
            border-color: var(--accent);
        }}
        .toggle-switch::after {{
            content: '';
            position: absolute;
            top: 2px;
            left: 2px;
            width: 18px;
            height: 18px;
            background: white;
            border-radius: 50%;
            transition: transform 0.2s;
        }}
        .toggle-switch.active::after {{
            transform: translateX(20px);
        }}
        .toggle-label {{
            font-size: 0.85rem;
            color: var(--text-secondary);
        }}
        
        .event-card.closed-project {{
            opacity: 0.6;
        }}
        .event-card.closed-project .event-header {{
            background: var(--bg-secondary);
        }}
        
        @media (max-width: 768px) {{
            .container {{ padding: 1rem; }}
            .markets-table {{ font-size: 0.75rem; }}
            .price-bar-bg {{ display: none; }}
        }}
    </style>
</head>
<body>
    <div class="container">
        <header>
            <h1>📈 Daily Price Changes</h1>
            <p class="subtitle">Polymarket pre-market odds by project</p>
            <div class="date-range">📅 {prev_date or 'N/A'} → {today}</div>
        </header>

        <div class="stats-row">
            <div class="stat-card">
                <div class="stat-value">{len(projects_data)}</div>
                <div class="stat-label">Projects</div>
            </div>
            <div class="stat-card">
                <div class="stat-value">{total_changes}</div>
                <div class="stat-label">Price Changes</div>
            </div>
            <div class="stat-card">
                <div class="stat-value green">{up_count}</div>
                <div class="stat-label">Prices Up</div>
            </div>
            <div class="stat-card">
                <div class="stat-value red">{down_count}</div>
                <div class="stat-label">Prices Down</div>
            </div>
        </div>

        <div style="display:flex;gap:1rem;align-items:center;flex-wrap:wrap;margin-bottom:1.5rem;">
            <div class="search-box" style="flex:1;min-width:200px;margin-bottom:0;">
                <input type="text" id="searchInput" placeholder="🔍 Search projects...">
            </div>
            <div class="toggle-container">
                <div class="toggle-switch" id="showClosedToggle" onclick="toggleShowClosed()"></div>
                <span class="toggle-label">Show closed markets</span>
            </div>
        </div>

        <div class="events-list" id="eventsList"></div>
    </div>

    <script>
        const projectsData = {json.dumps(projects_data)};
        let showClosed = false;

        function formatVolume(vol) {{
            if (vol >= 1000000) return '$' + (vol / 1000000).toFixed(1) + 'M';
            if (vol >= 1000) return '$' + (vol / 1000).toFixed(0) + 'K';
            return '$' + vol.toFixed(0);
        }}

        function getPriceBarClass(price) {{
            if (price >= 0.5) return 'high';
            if (price >= 0.2) return 'mid';
            return 'low';
        }}
        
        function toggleShowClosed() {{
            showClosed = !showClosed;
            document.getElementById('showClosedToggle').classList.toggle('active', showClosed);
            applyFilters();
        }}

        function applyFilters() {{
            const search = document.getElementById('searchInput').value.toLowerCase();
            let filtered = projectsData.filter(p => p.name.toLowerCase().includes(search));
            if (!showClosed) {{
                filtered = filtered.filter(p => p.hasOpenMarkets);
            }}
            renderProjects(filtered);
        }}

        function toggleProject(name) {{
            const card = document.getElementById('project-' + name.replace(/[^a-zA-Z0-9]/g, '_'));
            card.classList.toggle('collapsed');
        }}

        function renderProjects(projects) {{
            const list = document.getElementById('eventsList');
            
            list.innerHTML = projects.map((project, idx) => {{
                const allMarkets = project.events.flatMap(e => e.markets);
                const openMarkets = allMarkets.filter(m => !m.closed);
                const upCount = openMarkets.filter(m => m.change > 0).length;
                const downCount = openMarkets.filter(m => m.change < 0).length;
                const netChange = openMarkets.reduce((sum, m) => sum + m.change, 0);
                const totalAbsChange = (project.totalChange * 100).toFixed(1);
                const changeClass = netChange > 0 ? 'positive' : (netChange < 0 ? 'negative' : 'neutral');
                const projectId = project.name.replace(/[^a-zA-Z0-9]/g, '_');
                const isClosed = !project.hasOpenMarkets;
                
                return `
                    <div class="event-card${{idx >= 5 ? ' collapsed' : ''}}${{isClosed ? ' closed-project' : ''}}" id="project-${{projectId}}">
                        <div class="event-header" onclick="toggleProject('${{project.name}}')">
                            <div style="display:flex;align-items:center;">
                                <span class="toggle-icon">▼</span>
                                <span class="event-title" style="cursor:pointer">${{project.name}}</span>
                                ${{isClosed ? '<span class="closed-badge">CLOSED</span>' : ''}}
                                <span style="margin-left:0.5rem;font-size:0.75rem;color:var(--text-secondary);">(${{project.events.length}} events)</span>
                            </div>
                            <div class="event-meta">
                                ${{!isClosed ? `<span class="total-change ${{changeClass}}">${{totalAbsChange}}pp</span>` : ''}}
                                <span class="event-volume">${{formatVolume(project.totalVolume)}}</span>
                                ${{upCount > 0 || downCount > 0 ? `<span class="event-change">
                                    ${{upCount > 0 ? '🔺' + upCount : ''}} ${{downCount > 0 ? '🔻' + downCount : ''}}
                                </span>` : ''}}
                            </div>
                        </div>
                        <div class="markets-container">
                            ${{project.events.map(event => `
                                <div style="border-top:1px solid var(--border);padding:0.5rem 1rem 0;">
                                    <div style="display:flex;align-items:center;margin-bottom:0.5rem;">
                                        <a href="https://polymarket.com/event/${{event.slug}}" target="_blank" 
                                           style="font-size:0.85rem;color:var(--accent);text-decoration:none;">
                                            ${{event.title}} →
                                        </a>
                                        ${{event.allClosed ? '<span class="closed-badge" style="margin-left:0.5rem;">CLOSED</span>' : ''}}
                                    </div>
                                    <table class="markets-table">
                                        <thead>
                                            <tr>
                                                <th>Market</th>
                                                <th style="text-align:right">Price</th>
                                                <th style="width:100px"></th>
                                                <th style="text-align:right">Change</th>
                                            </tr>
                                        </thead>
                                        <tbody>
                                            ${{event.markets.filter(m => showClosed || !m.closed).map(m => `
                                                <tr style="${{m.closed ? 'opacity:0.5;' : ''}}">
                                                    <td class="market-question">
                                                        ${{m.question}}
                                                        ${{m.closed ? '<span class="closed-badge" style="margin-left:0.25rem;">CLOSED</span>' : ''}}
                                                    </td>
                                                    <td class="price-cell">${{(m.newPrice * 100).toFixed(1)}}%</td>
                                                    <td>
                                                        <div class="price-bar-bg">
                                                            <div class="price-bar ${{getPriceBarClass(m.newPrice)}}" style="width: ${{m.newPrice * 100}}%"></div>
                                                        </div>
                                                    </td>
                                                    <td class="change-cell ${{m.direction}}">
                                                        ${{m.change !== 0 ? (m.change > 0 ? '+' : '') + (m.change * 100).toFixed(1) + 'pp' : '-'}}
                                                    </td>
                                                </tr>
                                            `).join('')}}
                                        </tbody>
                                    </table>
                                </div>
                            `).join('')}}
                        </div>
                    </div>
                `;
            }}).join('');
        }}

        // Setup event handlers
        document.getElementById('searchInput').oninput = applyFilters;
        
        // Initial render (hide closed by default)
        applyFilters();
    </script>
</body>
</html>'''
    
    output_path = "/Users/jacques.whales/PredictionMarkets/Polymarket/dashboard.html"
    with open(output_path, 'w') as f:
        f.write(html)
    
    print(f"📊 Dashboard saved to {output_path}")
    return output_path


if __name__ == "__main__":
    import sys
    
    if len(sys.argv) > 1 and sys.argv[1] == "report":
        generate_report()
    else:
        run_daily_update()
        
        # Auto-generate HTML dashboard
        today = datetime.now().strftime("%Y-%m-%d")
        current_path = get_snapshot_path(today)
        if os.path.exists(current_path):
            with open(current_path, 'r') as f:
                current_data = json.load(f)
            prev_snapshot, prev_date = get_previous_snapshot()
            if prev_snapshot:
                generate_html_dashboard(current_data.get("markets", {}), prev_snapshot, prev_date)
