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

# Config - use paths relative to script location
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(SCRIPT_DIR, "data")
CSV_PATH = os.path.join(SCRIPT_DIR, "polymarketPreMarkets121925.csv")
GAMMA_API = "https://gamma-api.polymarket.com"
USE_API = True  # Set to True to fetch from API instead of CSV

# Try to import Limitless client (optional - for gap analysis)
try:
    from limitless_client import fetch_limitless_markets
    LIMITLESS_AVAILABLE = True
except ImportError:
    LIMITLESS_AVAILABLE = False
    print("⚠️  limitless_client not found - gap analysis disabled")

# Leaderboard tracking CSV
LEADERBOARD_CSV_PATH = os.path.join(SCRIPT_DIR, "Pre-TGE markets - Pre-TGE marketsFULL.csv")

# Portfolio tracking
PORTFOLIO_PATH = os.path.join(SCRIPT_DIR, "portfolio.json")

def load_leaderboard_data():
    """Load project leaderboard tracking data from CSV"""
    if not os.path.exists(LEADERBOARD_CSV_PATH):
        print("⚠️  Leaderboard CSV not found")
        return {}
    
    try:
        leaderboard = {}
        with open(LEADERBOARD_CSV_PATH, 'r', encoding='utf-8') as f:
            reader = csv.DictReader(f)
            for row in reader:
                project = row.get('Project', '').strip()
                if not project:
                    continue
                leaderboard[project.lower()] = {
                    'name': project,
                    'sector': row.get('Sector', ''),
                    'source': row.get('Source', ''),  # Cookie, Yaps, etc.
                    'market_status': row.get('Market Status', ''),
                    'polymarket_link': row.get('Polymarket Link', ''),
                    'leaderboard_link': row.get('Leaderboard Link', ''),
                    'priority_note': row.get('Priority Note', ''),
                    'in_touch': row.get('In Touch with Team? ', '')
                }
        print(f"📋 Loaded {len(leaderboard)} projects from leaderboard CSV")
        return leaderboard
    except Exception as e:
        print(f"⚠️  Error loading leaderboard CSV: {e}")
        return {}

def load_portfolio():
    """Load portfolio positions from JSON file"""
    if not os.path.exists(PORTFOLIO_PATH):
        return {"positions": []}

    try:
        with open(PORTFOLIO_PATH, 'r') as f:
            return json.load(f)
    except Exception as e:
        print(f"⚠️  Error loading portfolio: {e}")
        return {"positions": []}

def calculate_portfolio_pnl(portfolio, current_markets, limitless_data):
    """Calculate P&L for portfolio positions based on current prices"""
    results = []

    for position in portfolio.get("positions", []):
        position_result = {
            "id": position.get("id"),
            "name": position.get("name"),
            "opened_at": position.get("opened_at"),
            "legs": [],
            "total_cost": 0,
            "total_value": 0,
            "total_pnl": 0
        }

        for leg in position.get("legs", []):
            platform = leg.get("platform")
            market_slug = leg.get("market")
            direction = leg.get("direction")
            shares = leg.get("shares", 0)
            entry_price = leg.get("entry_price", 0)
            cost = leg.get("cost", shares * entry_price)

            # Find current price
            current_price = None
            if platform == "polymarket":
                # Search through current_markets for this market
                for event_slug, event_data in current_markets.items():
                    for mkt_slug, mkt_data in event_data.get("markets", {}).items():
                        if market_slug in mkt_slug or mkt_slug in market_slug:
                            current_price = mkt_data.get("yes_price", 0)
                            if direction == "no":
                                current_price = 1 - current_price
                            break
                    if current_price is not None:
                        break
            elif platform == "limitless" and limitless_data:
                # Search through limitless_data
                for proj_name, proj_data in limitless_data.get("projects", {}).items():
                    for mkt in proj_data.get("markets", []):
                        mkt_slug = mkt.get("slug", "")
                        if market_slug in mkt_slug or mkt_slug in market_slug:
                            current_price = mkt.get("yes_price", 0)
                            if direction == "no":
                                current_price = 1 - current_price
                            break
                    if current_price is not None:
                        break

            # Calculate value and P&L
            if current_price is not None:
                current_value = shares * current_price
                pnl = current_value - cost
            else:
                current_value = cost  # Assume no change if we can't find price
                pnl = 0
                current_price = entry_price

            leg_result = {
                "platform": platform,
                "market": market_slug,
                "direction": direction,
                "shares": shares,
                "entry_price": entry_price,
                "current_price": current_price,
                "cost": cost,
                "value": current_value,
                "pnl": pnl
            }

            position_result["legs"].append(leg_result)
            position_result["total_cost"] += cost
            position_result["total_value"] += current_value
            position_result["total_pnl"] += pnl

        # Calculate P&L percentage
        if position_result["total_cost"] > 0:
            position_result["pnl_pct"] = (position_result["total_pnl"] / position_result["total_cost"]) * 100
        else:
            position_result["pnl_pct"] = 0

        results.append(position_result)

    return results

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

def generate_html_dashboard(current_markets, prev_snapshot, prev_date, limitless_data=None, leaderboard_data=None, portfolio_data=None):
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
        
        /* Tab Navigation */
        .tab-nav {{
            display: flex;
            gap: 0.5rem;
            margin-bottom: 1.5rem;
            justify-content: center;
        }}
        .tab-btn {{
            padding: 0.75rem 1.5rem;
            background: var(--bg-card);
            border: 1px solid var(--border);
            border-radius: 10px;
            color: var(--text-secondary);
            font-size: 0.9rem;
            font-weight: 500;
            cursor: pointer;
            transition: all 0.2s;
        }}
        .tab-btn:hover {{
            background: var(--bg-secondary);
            color: var(--text-primary);
        }}
        .tab-btn.active {{
            background: var(--accent);
            border-color: var(--accent);
            color: white;
        }}
        .tab-content {{
            display: none;
        }}
        .tab-content.active {{
            display: block;
        }}
        
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

        <div class="tab-nav">
            <button class="tab-btn active" onclick="switchTab('changes')">📊 Daily Changes</button>
            <button class="tab-btn" onclick="switchTab('timeline')">🚀 Launch Timeline</button>
            <button class="tab-btn" onclick="switchTab('gap')">🔍 Gap Analysis</button>
            <button class="tab-btn" onclick="switchTab('arb')">💰 Arb Calculator</button>
            <button class="tab-btn" onclick="switchTab('portfolio')">📁 Portfolio</button>
        </div>

        <!-- Tab 1: Daily Changes -->
        <div id="tab-changes" class="tab-content active">
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

        <!-- Tab 2: Launch Timeline -->
        <div id="tab-timeline" class="tab-content">
            <div style="text-align:center;margin-bottom:1.5rem;">
                <p style="color:var(--text-secondary);font-size:0.95rem;">
                    Token launch predictions based on Polymarket odds. Bars show launch window, color intensity = probability.
                </p>
            </div>
            <div class="legend" style="display:flex;justify-content:center;gap:20px;margin-bottom:1.5rem;flex-wrap:wrap;">
                <div style="display:flex;align-items:center;gap:6px;">
                    <div style="width:18px;height:12px;background:rgba(99,102,241,0.2);border-radius:3px;"></div>
                    <span style="font-size:0.8rem;color:var(--text-secondary);">&lt;20%</span>
                </div>
                <div style="display:flex;align-items:center;gap:6px;">
                    <div style="width:18px;height:12px;background:rgba(99,102,241,0.5);border-radius:3px;"></div>
                    <span style="font-size:0.8rem;color:var(--text-secondary);">40-60%</span>
                </div>
                <div style="display:flex;align-items:center;gap:6px;">
                    <div style="width:18px;height:12px;background:rgba(99,102,241,0.85);border-radius:3px;"></div>
                    <span style="font-size:0.8rem;color:var(--text-secondary);">80%+</span>
                </div>
                <div style="display:flex;align-items:center;gap:6px;">
                    <div style="width:4px;height:14px;background:white;border-radius:2px;"></div>
                    <span style="font-size:0.8rem;color:var(--text-secondary);">50% threshold</span>
                </div>
            </div>
            <div id="timeline-viz" style="background:var(--bg-card);border-radius:12px;padding:20px;overflow-x:auto;"></div>
        </div>

        <!-- Tab 3: Gap Analysis -->
        <div id="tab-gap" class="tab-content">
            <div style="text-align:center;margin-bottom:1.5rem;">
                <p style="color:var(--text-secondary);font-size:0.95rem;">
                    Comparing Polymarket pre-TGE projects with Limitless coverage
                </p>
            </div>
            <div id="gap-analysis" style="background:var(--bg-card);border-radius:12px;padding:20px;"></div>
        </div>

        <!-- Tab 4: Arb Calculator -->
        <div id="tab-arb" class="tab-content">
            <div style="text-align:center;margin-bottom:1.5rem;">
                <p style="color:var(--text-secondary);font-size:0.95rem;">
                    Calculate optimal split for cross-platform arbitrage
                </p>
            </div>
            <div id="arb-calculator" style="background:var(--bg-card);border-radius:12px;padding:20px;"></div>
        </div>

        <!-- Tab 5: Portfolio -->
        <div id="tab-portfolio" class="tab-content">
            <div style="text-align:center;margin-bottom:1.5rem;">
                <p style="color:var(--text-secondary);font-size:0.95rem;">
                    Track your positions across Polymarket and Limitless
                </p>
            </div>
            <div id="portfolio-view" style="background:var(--bg-card);border-radius:12px;padding:20px;"></div>
        </div>
    </div>

    <script>
        const projectsData = {json.dumps(projects_data)};
        const limitlessData = {json.dumps(limitless_data.get('projects', {}) if limitless_data else {})};
        const limitlessError = {json.dumps(limitless_data.get('error') if limitless_data else None)};
        const leaderboardData = {json.dumps(leaderboard_data if leaderboard_data else {})};
        const portfolioData = {json.dumps(portfolio_data if portfolio_data else [])};
        let showClosed = false;
        let gapRendered = false;
        let arbRendered = false;
        let portfolioRendered = false;

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
        
        // ===== TAB SWITCHING =====
        function switchTab(tab) {{
            document.querySelectorAll('.tab-btn').forEach(btn => btn.classList.remove('active'));
            document.querySelectorAll('.tab-content').forEach(content => content.classList.remove('active'));

            document.querySelector(`.tab-btn[onclick*="${{tab}}"]`).classList.add('active');
            document.getElementById('tab-' + tab).classList.add('active');

            if (tab === 'timeline' && !timelineRendered) {{
                renderTimeline();
                timelineRendered = true;
            }}
            if (tab === 'gap' && !gapRendered) {{
                renderGapAnalysis();
                gapRendered = true;
            }}
            if (tab === 'arb' && !arbRendered) {{
                renderArbCalculator();
                arbRendered = true;
            }}
            if (tab === 'portfolio' && !portfolioRendered) {{
                renderPortfolio();
                portfolioRendered = true;
            }}
        }}
        
        // ===== TIMELINE VISUALIZATION =====
        let timelineRendered = false;
        
        // Extract timeline data from projects (launch date markets)
        function buildTimelineData() {{
            const timeline = {{}};
            const launchPatterns = [
                /Will\\s+(.+?)\\s+launch\\s+.*by\\s+(\\w+\\s+\\d+,?\\s*\\d*)/i,
                /Will\\s+(.+?)\\s+launch\\s+.*by\\s+(\\w+\\s+\\d+)/i
            ];
            
            projectsData.forEach(project => {{
                project.events.forEach(event => {{
                    event.markets.forEach(market => {{
                        if (market.closed) return;
                        const q = market.question.toLowerCase();
                        if (q.includes('launch') && q.includes('by')) {{
                            const dateMatch = q.match(/by\\s+(\\w+)\\s+(\\d+),?\\s*(\\d*)/i);
                            if (dateMatch) {{
                                const monthStr = dateMatch[1];
                                const day = dateMatch[2];
                                const year = dateMatch[3] || '2026';
                                const months = {{'jan':0,'january':0,'feb':1,'february':1,'mar':2,'march':2,'apr':3,'april':3,'may':4,'jun':5,'june':5,'jul':6,'july':6,'aug':7,'august':7,'sep':8,'september':8,'oct':9,'october':9,'nov':10,'november':10,'dec':11,'december':11}};
                                const monthNum = months[monthStr.toLowerCase()];
                                if (monthNum !== undefined) {{
                                    const dateKey = `${{year}}-${{String(monthNum+1).padStart(2,'0')}}-${{String(day).padStart(2,'0')}}`;
                                    if (!timeline[project.name]) timeline[project.name] = [];
                                    timeline[project.name].push({{
                                        date: dateKey,
                                        prob: market.newPrice
                                    }});
                                }}
                            }}
                        }}
                    }});
                }});
            }});
            
            // Sort milestones by date
            Object.keys(timeline).forEach(proj => {{
                timeline[proj].sort((a,b) => a.date.localeCompare(b.date));
            }});
            
            return timeline;
        }}
        
        function renderTimeline() {{
            const container = document.getElementById('timeline-viz');
            const timelineData = buildTimelineData();
            const projects = Object.keys(timelineData).filter(p => timelineData[p].length > 0);
            
            if (projects.length === 0) {{
                container.innerHTML = '<p style="text-align:center;color:var(--text-secondary);padding:2rem;">No launch date markets found in current data.</p>';
                return;
            }}
            
            // Define months (Jan 2025 - Dec 2026)
            const months = [];
            for (let year = 2025; year <= 2026; year++) {{
                for (let m = 1; m <= 12; m++) {{
                    const lastDay = new Date(year, m, 0).getDate();
                    months.push({{
                        label: ['Jan','Feb','Mar','Apr','May','Jun','Jul','Aug','Sep','Oct','Nov','Dec'][m-1],
                        key: `${{year}}-${{String(m).padStart(2,'0')}}-${{lastDay}}`,
                        year, month: m
                    }});
                }}
            }}
            
            const currentMonth = 12; // Jan 2026 = index 12
            
            // Sort projects by earliest 50% threshold
            const sorted = projects.sort((a,b) => {{
                const aFirst = timelineData[a].find(m => m.prob >= 0.5);
                const bFirst = timelineData[b].find(m => m.prob >= 0.5);
                if (!aFirst && !bFirst) return 0;
                if (!aFirst) return 1;
                if (!bFirst) return -1;
                return aFirst.date.localeCompare(bFirst.date);
            }});
            
            let html = '<div style="min-width:800px;">';
            
            // Month axis
            html += '<div style="display:flex;padding-left:140px;margin-bottom:10px;">';
            months.forEach((m, i) => {{
                const isCurrent = i === currentMonth;
                html += `<div style="flex:1;text-align:center;font-size:0.65rem;color:${{isCurrent ? '#22c55e' : 'var(--text-secondary)'}};">${{m.label}}</div>`;
            }});
            html += '</div>';
            
            // Project rows
            sorted.forEach(proj => {{
                const milestones = timelineData[proj];
                const first = milestones[0];
                const last = milestones[milestones.length - 1];
                
                // Find start/end month indices
                let startIdx = 0, endIdx = months.length - 1;
                for (let i = 0; i < months.length; i++) {{
                    if (months[i].key >= first.date) {{ startIdx = Math.max(0, i-1); break; }}
                }}
                for (let i = months.length - 1; i >= 0; i--) {{
                    if (months[i].key <= last.date) {{ endIdx = i; break; }}
                }}
                
                const leftPct = (startIdx / months.length) * 100;
                const widthPct = ((endIdx - startIdx + 1) / months.length) * 100;
                
                // Find 50% threshold position
                let p50Idx = -1;
                for (let i = 0; i < months.length; i++) {{
                    const monthKey = months[i].key;
                    const relevant = milestones.filter(m => m.date <= monthKey);
                    if (relevant.length > 0 && relevant[relevant.length-1].prob >= 0.5) {{
                        p50Idx = i;
                        break;
                    }}
                }}
                
                // Calculate gradient
                const lastProb = milestones[milestones.length-1].prob;
                const alpha = 0.15 + lastProb * 0.8;
                
                html += `<div style="display:flex;align-items:center;height:28px;margin-bottom:4px;">`;
                html += `<div style="width:140px;padding-right:10px;text-align:right;font-size:0.8rem;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;">${{proj}}</div>`;
                html += `<div style="flex:1;position:relative;height:100%;">`;
                html += `<div style="position:absolute;left:${{leftPct}}%;width:${{widthPct}}%;height:20px;top:4px;background:rgba(99,102,241,${{alpha.toFixed(2)}});border-radius:4px;"></div>`;
                
                if (p50Idx !== -1) {{
                    const markerPct = ((p50Idx + 0.5) / months.length) * 100;
                    html += `<div style="position:absolute;left:${{markerPct}}%;width:3px;height:24px;top:2px;background:white;border-radius:2px;box-shadow:0 0 6px rgba(255,255,255,0.5);"></div>`;
                }}
                
                html += '</div></div>';
            }});
            
            html += '</div>';
            container.innerHTML = html;
        }}
        
        // ===== GAP ANALYSIS =====
        function renderGapAnalysis() {{
            const container = document.getElementById('gap-analysis');
            
            if (limitlessError) {{
                container.innerHTML = `<p style="text-align:center;color:var(--text-secondary);padding:2rem;">
                    ⚠️ Could not fetch Limitless data: ${{limitlessError}}<br>
                    <small>Polymarket data is still available above.</small>
                </p>`;
                return;
            }}
            
            if (Object.keys(limitlessData).length === 0) {{
                container.innerHTML = '<p style="text-align:center;color:var(--text-secondary);padding:2rem;">No Limitless data available.</p>';
                return;
            }}
            
            // Normalize project names for matching
            function normalizeProject(s) {{ return s.toLowerCase().replace(/[^a-z0-9]/g, ''); }}

            // Extract threshold from market (e.g., "$2B", "$800M", "100M")
            function extractThreshold(q) {{
                const match = q.match(/\\$?([\\d.]+)\\s*(b|m|k)/i);
                if (match) return (match[1] + match[2]).toLowerCase();
                return null;
            }}

            // Find matching Limitless project for a Polymarket project
            function findLimitlessProject(polyName) {{
                const pNorm = normalizeProject(polyName);
                for (const [lName, lData] of Object.entries(limitlessData)) {{
                    const lNorm = normalizeProject(lName);
                    if (lNorm === pNorm || lNorm.includes(pNorm) || pNorm.includes(lNorm)) {{
                        return {{ name: lName, data: lData }};
                    }}
                }}
                return null;
            }}

            // Find matching Limitless market by threshold
            function findMarketMatch(polyQuestion, limitlessMarkets) {{
                const polyThreshold = extractThreshold(polyQuestion);
                if (!polyThreshold) return null;

                for (const lm of limitlessMarkets) {{
                    const limThreshold = extractThreshold(lm.title || '');
                    if (limThreshold && polyThreshold === limThreshold) {{
                        return lm;
                    }}
                }}
                return null;
            }}

            // Build comparison data
            const projects = [];
            let totalMatched = 0;
            let totalUnmatched = 0;

            projectsData.filter(p => p.hasOpenMarkets).forEach(polyProject => {{
                const limitlessProject = findLimitlessProject(polyProject.name);
                const polyMarkets = polyProject.events.flatMap(e =>
                    e.markets.filter(m => !m.closed).map(m => ({{
                        question: m.question,
                        polyPrice: m.newPrice
                    }}))
                );

                const matchedMarkets = [];
                const unmatchedMarkets = [];

                polyMarkets.forEach(pm => {{
                    if (limitlessProject && limitlessProject.data.markets) {{
                        const match = findMarketMatch(pm.question, limitlessProject.data.markets);
                        if (match) {{
                            const spread = (pm.polyPrice - match.yes_price) * 100;
                            matchedMarkets.push({{
                                question: pm.question,
                                polyPrice: pm.polyPrice,
                                limPrice: match.yes_price,
                                spread: spread,
                                absSpread: Math.abs(spread)
                            }});
                            totalMatched++;
                        }} else {{
                            unmatchedMarkets.push(pm);
                            totalUnmatched++;
                        }}
                    }} else {{
                        unmatchedMarkets.push(pm);
                        totalUnmatched++;
                    }}
                }});

                // Sort matched markets by absolute spread (biggest first)
                matchedMarkets.sort((a, b) => b.absSpread - a.absSpread);

                const maxSpread = matchedMarkets.length > 0 ? Math.max(...matchedMarkets.map(m => m.absSpread)) : 0;
                
                // Look up leaderboard info
                const projectLower = polyProject.name.toLowerCase();
                const lbInfo = leaderboardData[projectLower] || null;

                projects.push({{
                    name: polyProject.name,
                    hasLimitless: !!limitlessProject,
                    matchedMarkets,
                    unmatchedMarkets,
                    maxSpread,
                    leaderboard: lbInfo ? {{
                        source: lbInfo.source,
                        sector: lbInfo.sector,
                        link: lbInfo.leaderboard_link,
                        priority: lbInfo.priority_note
                    }} : null
                }});
            }});
            
            // Sort: projects with matches first, then by max spread
            projects.sort((a, b) => {{
                if (a.matchedMarkets.length > 0 && b.matchedMarkets.length === 0) return -1;
                if (b.matchedMarkets.length > 0 && a.matchedMarkets.length === 0) return 1;
                return b.maxSpread - a.maxSpread;
            }});

            // Render
            const matchedProjects = projects.filter(p => p.matchedMarkets.length > 0).length;
            let html = `
                <div style="display:flex;justify-content:space-between;margin-bottom:1.5rem;padding:0.5rem 1rem;background:var(--bg-secondary);border-radius:8px;">
                    <span style="color:var(--green);font-size:0.9rem;">
                        ✅ <strong>${{totalMatched}}</strong> markets matched across <strong>${{matchedProjects}}</strong> projects
                    </span>
                    <span style="color:var(--text-secondary);font-size:0.9rem;">
                        📊 <strong>${{totalUnmatched}}</strong> Polymarket-only
                    </span>
                </div>
            `;

            projects.forEach((project, idx) => {{
                const projectId = project.name.replace(/[^a-zA-Z0-9]/g, '_');
                const hasMatches = project.matchedMarkets.length > 0;
                const isCollapsed = idx >= 3;
                const lb = project.leaderboard;
                const lbBadge = lb ? `<a href="${{lb.link}}" target="_blank" style="text-decoration:none;margin-left:0.5rem;"><span style="background:${{lb.source.includes('Cookie') ? '#f59e0b' : '#8b5cf6'}};color:white;padding:0.15rem 0.4rem;border-radius:4px;font-size:0.65rem;font-weight:600;">${{lb.source}}</span></a>` : '';

                html += `
                    <div class="event-card${{isCollapsed ? ' collapsed' : ''}}" id="gap-${{projectId}}">
                        <div class="event-header" onclick="toggleGapProject('${{projectId}}')">
                            <div style="display:flex;align-items:center;flex-wrap:wrap;">
                                <span class="toggle-icon">▼</span>
                                <span class="event-title" style="cursor:pointer;">${{project.name}}</span>
                                ${{lbBadge}}
                                ${{!project.hasLimitless ? '<span class="closed-badge" style="background:var(--red);margin-left:0.5rem;">NOT ON LIMITLESS</span>' : ''}}
                                <span style="margin-left:0.5rem;font-size:0.75rem;color:var(--text-secondary);">
                                    (${{project.matchedMarkets.length}} matched${{project.unmatchedMarkets.length > 0 ? ', ' + project.unmatchedMarkets.length + ' unmatched' : ''}})
                                </span>
                            </div>
                            ${{hasMatches ? `<div class="event-meta">
                                <span style="color:${{project.maxSpread > 5 ? 'var(--yellow)' : 'var(--text-secondary)'}};">
                                    Max spread: ${{project.maxSpread.toFixed(1)}}pp
                                </span>
                            </div>` : ''}}
                        </div>
                        <div class="markets-container">
                `;

                if (hasMatches) {{
                    html += `
                        <table class="markets-table" style="margin:0.5rem 1rem;">
                            <thead>
                                <tr>
                                    <th style="text-align:left;">Market</th>
                                    <th style="text-align:right;width:80px;">Polymarket</th>
                                    <th style="text-align:right;width:80px;">Limitless</th>
                                    <th style="text-align:right;width:70px;">Spread</th>
                                </tr>
                            </thead>
                            <tbody>
                    `;

                    project.matchedMarkets.forEach(m => {{
                        const spreadColor = m.absSpread > 10 ? 'var(--red)' : (m.absSpread > 5 ? 'var(--yellow)' : 'var(--text-secondary)');
                        const spreadSign = m.spread > 0 ? '+' : '';
                        html += `
                            <tr>
                                <td class="market-question">${{m.question}}</td>
                                <td style="text-align:right;font-weight:500;">${{(m.polyPrice * 100).toFixed(1)}}%</td>
                                <td style="text-align:right;font-weight:500;">${{(m.limPrice * 100).toFixed(1)}}%</td>
                                <td style="text-align:right;color:${{spreadColor}};font-weight:500;">${{spreadSign}}${{m.spread.toFixed(1)}}pp</td>
                            </tr>
                        `;
                    }});

                    html += '</tbody></table>';
                }}

                if (project.unmatchedMarkets.length > 0 && hasMatches) {{
                    html += `<div style="padding:0.5rem 1rem;color:var(--text-secondary);font-size:0.8rem;border-top:1px solid var(--border);">
                        ${{project.unmatchedMarkets.length}} additional Polymarket-only market(s)
                    </div>`;
                }} else if (!hasMatches) {{
                    html += `<div style="padding:1rem;color:var(--text-secondary);text-align:center;">
                        No matching markets found on Limitless
                    </div>`;
                }}

                html += '</div></div>';
            }});

            container.innerHTML = html;
        }}

        function toggleGapProject(projectId) {{
            const card = document.getElementById('gap-' + projectId);
            if (card) card.classList.toggle('collapsed');
        }}

        // ===== ARB CALCULATOR =====
        function calculateSplit(budget, limYesPrice, polyNoPrice) {{
            // To lock in arb: buy equal shares on both sides
            // Limitless YES price + Polymarket NO price = combined cost per share
            const combinedCost = limYesPrice + polyNoPrice;
            const shares = budget / combinedCost;
            const limAmount = shares * limYesPrice;
            const polyAmount = shares * polyNoPrice;
            const payout = shares; // Each share pays $1 if it wins
            const profit = payout - budget;
            const profitPct = (profit / budget) * 100;

            return {{
                shares: shares,
                limAmount: limAmount,
                polyAmount: polyAmount,
                payout: payout,
                profit: profit,
                profitPct: profitPct,
                combinedCost: combinedCost
            }};
        }}

        function updateArbCalc(rowId) {{
            const budgetInput = document.getElementById('budget-' + rowId);
            const resultDiv = document.getElementById('result-' + rowId);
            const budget = parseFloat(budgetInput.value) || 0;

            if (budget <= 0) {{
                resultDiv.innerHTML = '<span style="color:var(--text-secondary);">Enter budget</span>';
                return;
            }}

            const limPrice = parseFloat(budgetInput.dataset.limprice);
            const polyPrice = parseFloat(budgetInput.dataset.polyprice);
            const result = calculateSplit(budget, limPrice, polyPrice);

            if (result.profit > 0) {{
                resultDiv.innerHTML = `
                    <span style="color:var(--green);">Lim: $` + result.limAmount.toFixed(2) + ` | Poly: $` + result.polyAmount.toFixed(2) + ` → +$` + result.profit.toFixed(2) + ` (` + result.profitPct.toFixed(1) + `%)</span>
                `;
            }} else {{
                resultDiv.innerHTML = `<span style="color:var(--red);">No arb (cost > $1)</span>`;
            }}
        }}

        function renderArbCalculator() {{
            const container = document.getElementById('arb-calculator');

            // Build list of all matched markets with spreads (reuse gap analysis logic)
            const opportunities = [];

            function normalizeProject(s) {{ return s.toLowerCase().replace(/[^a-z0-9]/g, ''); }}
            function extractThreshold(q) {{
                const match = q.match(/\\$?([\\d.]+)\\s*(b|m|k)/i);
                if (match) return (match[1] + match[2]).toLowerCase();
                return null;
            }}

            projectsData.filter(p => p.hasOpenMarkets).forEach(polyProject => {{
                const pNorm = normalizeProject(polyProject.name);
                let limitlessProject = null;

                for (const [lName, lData] of Object.entries(limitlessData)) {{
                    const lNorm = normalizeProject(lName);
                    if (lNorm === pNorm || lNorm.includes(pNorm) || pNorm.includes(lNorm)) {{
                        limitlessProject = lData;
                        break;
                    }}
                }}

                if (!limitlessProject) return;

                const polyMarkets = polyProject.events.flatMap(e =>
                    e.markets.filter(m => !m.closed).map(m => ({{ question: m.question, polyPrice: m.newPrice }}))
                );

                polyMarkets.forEach(pm => {{
                    const polyThreshold = extractThreshold(pm.question);
                    if (!polyThreshold) return;

                    for (const lm of (limitlessProject.markets || [])) {{
                        const limThreshold = extractThreshold(lm.title || '');
                        if (limThreshold && polyThreshold === limThreshold) {{
                            const limYesPrice = lm.yes_price;
                            const polyNoPrice = 1 - pm.polyPrice;
                            const combinedCost = limYesPrice + polyNoPrice;
                            const spread = (1 - combinedCost) * 100; // Profit as percentage

                            if (combinedCost < 1) {{ // Only show if there's an arb
                                opportunities.push({{
                                    project: polyProject.name,
                                    question: pm.question,
                                    limYes: limYesPrice,
                                    polyNo: polyNoPrice,
                                    polyYes: pm.polyPrice,
                                    spread: spread,
                                    combinedCost: combinedCost
                                }});
                            }}
                            break;
                        }}
                    }}
                }});
            }});

            // Sort by spread (best arbs first)
            opportunities.sort((a, b) => b.spread - a.spread);

            if (opportunities.length === 0) {{
                container.innerHTML = `<p style="text-align:center;color:var(--text-secondary);padding:2rem;">
                    No arbitrage opportunities found (all combined costs >= $1.00)
                </p>`;
                return;
            }}

            let html = `
                <div style="margin-bottom:1rem;padding:0.75rem;background:var(--bg-secondary);border-radius:8px;">
                    <strong style="color:var(--green);">${{opportunities.length}}</strong> potential arb opportunities found
                    <span style="color:var(--text-secondary);margin-left:1rem;font-size:0.85rem;">
                        Buy Limitless YES + Polymarket NO for guaranteed payout
                    </span>
                </div>
                <table class="markets-table">
                    <thead>
                        <tr>
                            <th>Market</th>
                            <th style="text-align:right;">Lim YES</th>
                            <th style="text-align:right;">Poly NO</th>
                            <th style="text-align:right;">Cost</th>
                            <th style="text-align:right;">Edge</th>
                            <th style="width:100px;">Budget</th>
                            <th style="min-width:200px;">Split</th>
                        </tr>
                    </thead>
                    <tbody>
            `;

            opportunities.forEach((opp, idx) => {{
                const rowId = 'arb-' + idx;
                const edgeColor = opp.spread > 5 ? 'var(--green)' : (opp.spread > 2 ? 'var(--yellow)' : 'var(--text-secondary)');
                html += `
                    <tr>
                        <td>
                            <div style="font-weight:500;">${{opp.project}}</div>
                            <div style="font-size:0.75rem;color:var(--text-secondary);max-width:250px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap;">${{opp.question}}</div>
                        </td>
                        <td style="text-align:right;color:var(--accent);">${{(opp.limYes * 100).toFixed(1)}}%</td>
                        <td style="text-align:right;color:var(--accent);">${{(opp.polyNo * 100).toFixed(1)}}%</td>
                        <td style="text-align:right;">${{opp.combinedCost.toFixed(3)}}</td>
                        <td style="text-align:right;color:${{edgeColor}};font-weight:600;">+${{opp.spread.toFixed(1)}}%</td>
                        <td>
                            <input type="number" id="budget-${{rowId}}" placeholder="$"
                                style="width:80px;padding:0.25rem 0.5rem;background:var(--bg-primary);border:1px solid var(--border);border-radius:4px;color:white;font-size:0.85rem;"
                                data-limprice="${{opp.limYes}}" data-polyprice="${{opp.polyNo}}"
                                oninput="updateArbCalc('${{rowId}}')">
                        </td>
                        <td id="result-${{rowId}}" style="font-size:0.85rem;">
                            <span style="color:var(--text-secondary);">Enter budget</span>
                        </td>
                    </tr>
                `;
            }});

            html += '</tbody></table>';
            container.innerHTML = html;
        }}

        // ===== PORTFOLIO =====
        function renderPortfolio() {{
            const container = document.getElementById('portfolio-view');

            if (!portfolioData || portfolioData.length === 0) {{
                container.innerHTML = `
                    <div style="text-align:center;padding:2rem;">
                        <p style="color:var(--text-secondary);margin-bottom:1rem;">No positions in portfolio</p>
                        <p style="font-size:0.85rem;color:var(--text-secondary);">
                            Edit <code style="background:var(--bg-primary);padding:0.2rem 0.4rem;border-radius:4px;">portfolio.json</code> to add positions
                        </p>
                    </div>
                `;
                return;
            }}

            // Calculate totals
            const totalCost = portfolioData.reduce((sum, p) => sum + p.total_cost, 0);
            const totalValue = portfolioData.reduce((sum, p) => sum + p.total_value, 0);
            const totalPnL = portfolioData.reduce((sum, p) => sum + p.total_pnl, 0);
            const totalPnLPct = totalCost > 0 ? (totalPnL / totalCost) * 100 : 0;

            let html = `
                <div style="display:grid;grid-template-columns:repeat(4, 1fr);gap:1rem;margin-bottom:1.5rem;">
                    <div style="background:var(--bg-secondary);padding:1rem;border-radius:8px;text-align:center;">
                        <div style="font-size:1.5rem;font-weight:700;">${{totalCost.toFixed(2)}}</div>
                        <div style="font-size:0.75rem;color:var(--text-secondary);">Total Invested</div>
                    </div>
                    <div style="background:var(--bg-secondary);padding:1rem;border-radius:8px;text-align:center;">
                        <div style="font-size:1.5rem;font-weight:700;">${{totalValue.toFixed(2)}}</div>
                        <div style="font-size:0.75rem;color:var(--text-secondary);">Current Value</div>
                    </div>
                    <div style="background:var(--bg-secondary);padding:1rem;border-radius:8px;text-align:center;">
                        <div style="font-size:1.5rem;font-weight:700;color:${{totalPnL >= 0 ? 'var(--green)' : 'var(--red)'}};">
                            ${{totalPnL >= 0 ? '+' : ''}}${{totalPnL.toFixed(2)}}
                        </div>
                        <div style="font-size:0.75rem;color:var(--text-secondary);">P&L</div>
                    </div>
                    <div style="background:var(--bg-secondary);padding:1rem;border-radius:8px;text-align:center;">
                        <div style="font-size:1.5rem;font-weight:700;color:${{totalPnLPct >= 0 ? 'var(--green)' : 'var(--red)'}};">
                            ${{totalPnLPct >= 0 ? '+' : ''}}${{totalPnLPct.toFixed(1)}}%
                        </div>
                        <div style="font-size:0.75rem;color:var(--text-secondary);">Return</div>
                    </div>
                </div>
            `;

            // Render each position
            portfolioData.forEach(position => {{
                const pnlColor = position.total_pnl >= 0 ? 'var(--green)' : 'var(--red)';
                html += `
                    <div class="event-card" style="margin-bottom:1rem;">
                        <div class="event-header">
                            <div>
                                <span class="event-title">${{position.name}}</span>
                                <span style="margin-left:0.5rem;font-size:0.75rem;color:var(--text-secondary);">
                                    Opened: ${{position.opened_at}}
                                </span>
                            </div>
                            <div class="event-meta">
                                <span style="color:${{pnlColor}};font-weight:600;">
                                    ${{position.total_pnl >= 0 ? '+' : ''}}$${{position.total_pnl.toFixed(2)}}
                                    (${{position.pnl_pct >= 0 ? '+' : ''}}${{position.pnl_pct.toFixed(1)}}%)
                                </span>
                            </div>
                        </div>
                        <div class="markets-container">
                            <table class="markets-table">
                                <thead>
                                    <tr>
                                        <th>Platform</th>
                                        <th>Direction</th>
                                        <th style="text-align:right;">Shares</th>
                                        <th style="text-align:right;">Entry</th>
                                        <th style="text-align:right;">Current</th>
                                        <th style="text-align:right;">Cost</th>
                                        <th style="text-align:right;">Value</th>
                                        <th style="text-align:right;">P&L</th>
                                    </tr>
                                </thead>
                                <tbody>
                                    ${{position.legs.map(leg => `
                                        <tr>
                                            <td>
                                                <span style="background:${{leg.platform === 'limitless' ? '#8b5cf6' : '#6366f1'}};color:white;padding:0.15rem 0.4rem;border-radius:4px;font-size:0.7rem;font-weight:600;text-transform:uppercase;">
                                                    ${{leg.platform}}
                                                </span>
                                            </td>
                                            <td>
                                                <span style="color:${{leg.direction === 'yes' ? 'var(--green)' : 'var(--red)'}};font-weight:500;text-transform:uppercase;">
                                                    ${{leg.direction}}
                                                </span>
                                            </td>
                                            <td style="text-align:right;">${{leg.shares.toFixed(2)}}</td>
                                            <td style="text-align:right;">${{(leg.entry_price * 100).toFixed(1)}}%</td>
                                            <td style="text-align:right;">${{(leg.current_price * 100).toFixed(1)}}%</td>
                                            <td style="text-align:right;">$${{leg.cost.toFixed(2)}}</td>
                                            <td style="text-align:right;">$${{leg.value.toFixed(2)}}</td>
                                            <td style="text-align:right;color:${{leg.pnl >= 0 ? 'var(--green)' : 'var(--red)'}};font-weight:500;">
                                                ${{leg.pnl >= 0 ? '+' : ''}}$${{leg.pnl.toFixed(2)}}
                                            </td>
                                        </tr>
                                    `).join('')}}
                                </tbody>
                            </table>
                        </div>
                    </div>
                `;
            }});

            container.innerHTML = html;
        }}
    </script>
</body>
</html>'''
    
    output_path = os.path.join(SCRIPT_DIR, "dashboard.html")
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
            
            # Fetch Limitless data (optional, graceful failure)
            limitless_data = None
            if LIMITLESS_AVAILABLE:
                try:
                    limitless_data = fetch_limitless_markets()
                except Exception as e:
                    print(f"⚠️  Limitless fetch failed: {e}")
                    limitless_data = {"error": str(e), "projects": {}}
            
            # Load leaderboard data (optional)
            leaderboard_data = load_leaderboard_data()

            # Load portfolio and calculate P&L
            portfolio = load_portfolio()
            portfolio_pnl = calculate_portfolio_pnl(portfolio, current_data.get("markets", {}), limitless_data)
            print(f"📁 Loaded {len(portfolio_pnl)} portfolio positions")

            if prev_snapshot:
                generate_html_dashboard(current_data.get("markets", {}), prev_snapshot, prev_date, limitless_data, leaderboard_data, portfolio_pnl)
