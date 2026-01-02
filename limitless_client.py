"""
Limitless Exchange API Client
Fetches Pre-TGE market data with graceful failure handling
"""

import requests

LIMITLESS_API = "https://api.limitless.exchange"
PRE_TGE_CATEGORY_ID = 43


def fetch_limitless_markets():
    """
    Fetch Pre-TGE markets from Limitless Exchange.
    Returns normalized data structure or empty dict on failure.
    """
    try:
        url = f"{LIMITLESS_API}/markets/active/{PRE_TGE_CATEGORY_ID}"
        response = requests.get(url, timeout=10)
        response.raise_for_status()
        data = response.json()
        
        markets = data.get('data', [])
        
        # Normalize to match Polymarket structure
        result = {
            "source": "limitless",
            "timestamp": None,
            "projects": {}
        }
        
        for market in markets:
            title = market.get('title', 'Unknown')
            market_id = market.get('id')
            prices = market.get('prices', [])
            volume_raw = market.get('volume', '0')
            slug = market.get('slug', '')
            
            # Get token decimals (default to 6 for USDC)
            decimals = market.get('collateralToken', {}).get('decimals', 6)
            volume = float(volume_raw) / (10 ** decimals) if volume_raw else 0
            
            # Extract project name from title
            project_name = extract_project_name(title)
            
            if project_name not in result["projects"]:
                result["projects"][project_name] = {
                    "name": project_name,
                    "markets": [],
                    "totalVolume": 0
                }
            
            # Normalize price to 0-1 scale (API returns mixed: some 0-100, some 0-1)
            raw_yes = prices[0] if prices else 0
            yes_price = raw_yes / 100 if raw_yes > 1 else raw_yes
            
            result["projects"][project_name]["markets"].append({
                "id": market_id,
                "title": title,
                "slug": slug,
                "yes_price": yes_price,
                "volume": volume
            })
            result["projects"][project_name]["totalVolume"] += volume
        
        print(f"✅ Limitless: Fetched {len(markets)} markets, {len(result['projects'])} projects")
        return result
        
    except requests.exceptions.RequestException as e:
        print(f"⚠️  Limitless API error (non-fatal): {e}")
        return {"source": "limitless", "projects": {}, "error": str(e)}
    except Exception as e:
        print(f"⚠️  Limitless parsing error (non-fatal): {e}")
        return {"source": "limitless", "projects": {}, "error": str(e)}


def extract_project_name(title):
    """Extract project name from market title"""
    import re
    
    # Remove emoji prefixes (💎, 🚀, etc.)
    title = re.sub(r'^[\U0001F300-\U0001F9FF\s]+', '', title).strip()
    
    # Common patterns
    patterns = [
        r'^Will\s+(.+?)\s+(?:launch|token|TGE|have)',
        r'^(.+?)\s+(?:token|TGE|launch|FDV|market|above|below)',
        r'^(.+?)\s+(?:trading|airdrop)',
    ]
    
    for pattern in patterns:
        match = re.search(pattern, title, re.IGNORECASE)
        if match:
            name = match.group(1).strip()
            # Remove trailing "Protocol", "Network", etc.
            name = re.sub(r'\s+(Protocol|Network|Labs|Finance)$', '', name, flags=re.IGNORECASE)
            return name
    
    # Fallback: first 2 words
    words = title.split()[:2]
    return ' '.join(words)


if __name__ == "__main__":
    # Test the client
    data = fetch_limitless_markets()
    print(f"\nProjects found: {list(data.get('projects', {}).keys())}")
