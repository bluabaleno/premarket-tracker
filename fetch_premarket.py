"""
Polymarket Pre-Market Fetcher
Fetches crypto pre-market events directly from Gamma API
No more manual scraping needed!
"""

import json
import requests
from datetime import datetime
from py_clob_client.client import ClobClient

# Config
GAMMA_API = "https://gamma-api.polymarket.com"
OUTPUT_DIR = "/Users/jacques.whales/PredictionMarkets/Polymarket"

# Initialize CLOB client for live prices
clob = ClobClient("https://clob.polymarket.com")

def fetch_premarket_events(limit=200, active_only=True):
    """
    Fetch all pre-market crypto events from Gamma API
    Uses tag_slug=pre-market to filter for pre-market category
    """
    url = f"{GAMMA_API}/events"
    params = {
        "tag_slug": "pre-market",
        "limit": limit,
        "order": "volume",
        "ascending": "false"
    }
    
    if active_only:
        params["closed"] = "false"
    
    try:
        resp = requests.get(url, params=params, timeout=30)
        resp.raise_for_status()
        return resp.json()
    except Exception as e:
        print(f"Error fetching from Gamma API: {e}")
        return []

def get_live_price(token_id):
    """Get live midpoint price from CLOB"""
    try:
        mid = clob.get_midpoint(token_id)
        return float(mid.get('mid', 0)) if mid else None
    except:
        return None

def process_events(events):
    """Process events and extract market data with live prices"""
    processed = []
    
    for event in events:
        event_data = {
            "slug": event.get("slug"),
            "title": event.get("title"),
            "volume": float(event.get("volume") or 0),
            "liquidity": float(event.get("liquidity") or 0),
            "closed": event.get("closed", False),
            "end_date": event.get("endDate"),
            "markets": []
        }
        
        for market in event.get("markets", []):
            outcomes = json.loads(market.get("outcomes", "[]"))
            outcome_prices = json.loads(market.get("outcomePrices", "[]"))
            clob_token_ids = json.loads(market.get("clobTokenIds", "[]"))
            
            yes_price = float(outcome_prices[0]) if outcome_prices else 0
            
            # Get live CLOB price if available
            if clob_token_ids and not market.get("closed"):
                live_price = get_live_price(clob_token_ids[0])
                if live_price is not None:
                    yes_price = live_price
            
            market_data = {
                "slug": market.get("slug"),
                "question": market.get("question"),
                "yes_price": yes_price,
                "yes_pct": round(yes_price * 100, 1),
                "volume": float(market.get("volume") or 0),
                "closed": market.get("closed", False),
                "clob_token_id": clob_token_ids[0] if clob_token_ids else None
            }
            event_data["markets"].append(market_data)
        
        processed.append(event_data)
    
    return processed

def save_markets_json(markets, filename="premarket_data.json"):
    """Save markets to JSON file"""
    output = {
        "fetched_at": datetime.now().isoformat(),
        "total_events": len(markets),
        "total_markets": sum(len(e["markets"]) for e in markets),
        "events": markets
    }
    
    path = f"{OUTPUT_DIR}/{filename}"
    with open(path, 'w') as f:
        json.dump(output, f, indent=2)
    
    print(f"✅ Saved to {path}")
    return path

def save_markets_csv(markets, filename="premarket_data.csv"):
    """Save flattened market data to CSV"""
    import csv
    
    path = f"{OUTPUT_DIR}/{filename}"
    
    rows = []
    for event in markets:
        for market in event["markets"]:
            rows.append({
                "event_title": event["title"],
                "event_volume": event["volume"],
                "market_question": market["question"],
                "yes_pct": market["yes_pct"],
                "market_volume": market["volume"],
                "closed": market["closed"],
                "clob_token_id": market["clob_token_id"]
            })
    
    with open(path, 'w', newline='') as f:
        if rows:
            writer = csv.DictWriter(f, fieldnames=rows[0].keys())
            writer.writeheader()
            writer.writerows(rows)
    
    print(f"✅ Saved CSV to {path}")
    return path

def display_summary(markets):
    """Display a summary of fetched markets"""
    active_events = [e for e in markets if not e["closed"]]
    total_volume = sum(e["volume"] for e in markets)
    active_volume = sum(e["volume"] for e in active_events)
    
    print(f"\n{'='*70}")
    print(f"📊 POLYMARKET PRE-MARKET SUMMARY")
    print(f"{'='*70}")
    print(f"Total Events: {len(markets)}")
    print(f"Active Events: {len(active_events)}")
    print(f"Total Volume: ${total_volume:,.0f}")
    print(f"Active Volume: ${active_volume:,.0f}")
    
    print(f"\n🔥 TOP 10 ACTIVE BY VOLUME:")
    print("-" * 70)
    
    for event in sorted(active_events, key=lambda x: x["volume"], reverse=True)[:10]:
        print(f"\n  📈 {event['title']}")
        print(f"     Volume: ${event['volume']:,.0f}")
        
        # Show top 3 markets
        active_mkts = [m for m in event["markets"] if not m["closed"]][:3]
        for m in active_mkts:
            print(f"       • {m['question'][:50]}... → {m['yes_pct']}%")

def run():
    """Main function to fetch and save pre-market data"""
    print(f"🚀 Fetching Polymarket Pre-Market Data - {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    print("-" * 60)
    
    # Fetch from API
    print("\n📡 Calling Gamma API (tag_slug=pre-market)...")
    events = fetch_premarket_events(limit=200, active_only=False)
    print(f"   Fetched {len(events)} events")
    
    # Process and get live prices
    print("\n💰 Getting live prices from CLOB...")
    markets = process_events(events)
    
    # Save outputs
    print("\n💾 Saving data...")
    save_markets_json(markets)
    save_markets_csv(markets)
    
    # Display summary
    display_summary(markets)
    
    return markets


if __name__ == "__main__":
    import sys
    
    if len(sys.argv) > 1 and sys.argv[1] == "json":
        # Quick JSON dump only
        events = fetch_premarket_events(active_only=True)
        print(json.dumps(events, indent=2))
    else:
        run()
