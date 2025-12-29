"""
Polymarket Market Lookup Script
Looks up markets from CSV using Gamma API (events endpoint) + CLOB API for live prices
"""

import csv
import json
import requests
from urllib.parse import urlparse
from py_clob_client.client import ClobClient

# Initialize read-only CLOB client
clob = ClobClient("https://clob.polymarket.com")

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
    """Fetch event data (including markets) from Gamma API using event slug"""
    url = f"https://gamma-api.polymarket.com/events?slug={event_slug}"
    try:
        resp = requests.get(url, timeout=10)
        resp.raise_for_status()
        data = resp.json()
        return data[0] if data else None
    except Exception as e:
        print(f"Error fetching from Gamma API: {e}")
        return None

def get_live_price(token_id):
    """Get live price from CLOB API"""
    try:
        mid = clob.get_midpoint(token_id)
        price = clob.get_price(token_id, side="BUY")
        return {"midpoint": mid, "buy_price": price}
    except Exception as e:
        return None

def lookup_market(event_url):
    """Main lookup function - takes event URL, returns market data with live prices"""
    slug = extract_event_slug(event_url)
    if not slug:
        return {"error": "Could not extract slug from URL"}
    
    # Get event data from Gamma (includes markets)
    event = get_event_from_gamma(slug)
    if not event:
        return {"error": f"No event found for slug: {slug}"}
    
    results = {
        "event_title": event.get("title"),
        "event_slug": event.get("slug"),
        "volume": event.get("volume"),
        "liquidity": event.get("liquidity"),
        "markets": []
    }
    
    # Process each market in the event
    for market in event.get("markets", []):
        # Parse outcome prices (they come as JSON strings)
        outcomes = json.loads(market.get("outcomes", "[]"))
        outcome_prices = json.loads(market.get("outcomePrices", "[]"))
        clob_token_ids = json.loads(market.get("clobTokenIds", "[]"))
        
        market_data = {
            "question": market.get("question"),
            "slug": market.get("slug"),
            "outcomes": outcomes,
            "prices": dict(zip(outcomes, outcome_prices)) if outcomes else {},
            "volume": market.get("volume"),
            "liquidity": market.get("liquidity"),
        }
        
        # Get live prices from CLOB
        if clob_token_ids:
            market_data["clob_prices"] = {}
            for i, token_id in enumerate(clob_token_ids):
                outcome = outcomes[i] if i < len(outcomes) else f"Outcome {i}"
                price_data = get_live_price(token_id)
                if price_data:
                    market_data["clob_prices"][outcome] = price_data
        
        results["markets"].append(market_data)
    
    return results


def process_csv(csv_path, limit=5):
    """Process CSV and look up markets"""
    with open(csv_path, 'r') as f:
        reader = csv.DictReader(f)
        
        count = 0
        for row in reader:
            if count >= limit:
                break
            
            # Get the event URL (second column based on header)
            event_url = row.get("h-fit href", "")
            if not event_url or not event_url.startswith("http"):
                continue
            
            market_name = row.get("text-sm", "Unknown")
            print(f"\n{'='*70}")
            print(f"📊 {market_name}")
            print(f"🔗 {event_url}")
            
            result = lookup_market(event_url)
            
            if isinstance(result, dict) and "error" in result:
                print(f"❌ Error: {result['error']}")
            else:
                print(f"💰 Event Volume: ${float(result.get('volume') or 0):,.2f}")
                print(f"💧 Liquidity: ${float(result.get('liquidity') or 0):,.2f}")
                print(f"\n  Markets ({len(result['markets'])} total):")
                
                for market in result['markets'][:3]:  # Show first 3 markets
                    print(f"\n    ► {market['question']}")
                    if market.get('prices'):
                        for outcome, price in market['prices'].items():
                            pct = float(price) * 100
                            print(f"      {outcome}: {pct:.1f}%")
                    if market.get('clob_prices'):
                        print(f"      (CLOB live: {market['clob_prices']})")
                
                if len(result['markets']) > 3:
                    print(f"\n    ... and {len(result['markets']) - 3} more markets")
            
            count += 1


def lookup_single(event_url):
    """Look up a single market by URL"""
    result = lookup_market(event_url)
    print(json.dumps(result, indent=2))
    return result


if __name__ == "__main__":
    import sys
    
    csv_path = "/Users/jacques.whales/PredictionMarkets/Polymarket/polymarketPreMarkets121925.csv"
    
    if len(sys.argv) > 1:
        # If URL passed as argument, look up single market
        lookup_single(sys.argv[1])
    else:
        # Otherwise process CSV
        print("Looking up first 5 markets from CSV...\n")
        process_csv(csv_path, limit=5)
