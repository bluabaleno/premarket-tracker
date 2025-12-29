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
from py_clob_client.client import ClobClient

# Config
DATA_DIR = "/Users/jacques.whales/PredictionMarkets/Polymarket/data"
CSV_PATH = "/Users/jacques.whales/PredictionMarkets/Polymarket/polymarketPreMarkets121925.csv"
GAMMA_API = "https://gamma-api.polymarket.com"
USE_API = True  # Set to True to fetch from API instead of CSV

# Initialize read-only CLOB client
clob = ClobClient("https://clob.polymarket.com")

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


if __name__ == "__main__":
    import sys
    
    if len(sys.argv) > 1 and sys.argv[1] == "report":
        generate_report()
    else:
        run_daily_update()
