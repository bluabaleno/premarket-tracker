"""
Analyze Limitless market liquidity - identify thin orderbooks

Shows markets with high volume-to-depth ratio (demand exceeds liquidity)
"""

from src.polymarket.api import LimitlessClient

def analyze_liquidity():
    print("📡 Fetching Limitless markets...")
    client = LimitlessClient()
    data = client.fetch_markets()

    if data.get("error"):
        print(f"Error: {data['error']}")
        return

    markets = []

    for project_name, project in data["projects"].items():
        for market in project.get("markets", []):
            liq = market.get("liquidity", {})
            depth = liq.get("depth", 0)
            volume = market.get("volume", 0)
            trade_type = liq.get("type", "amm")

            # Calculate volume/depth ratio (higher = thinner relative to demand)
            if depth > 0:
                ratio = volume / depth
            else:
                ratio = float('inf') if volume > 0 else 0

            # Get bid-ask spread for CLOB markets
            bids = liq.get("bids", [])
            asks = liq.get("asks", [])
            spread = None
            if bids and asks:
                best_bid = max(b["price"] for b in bids) if bids else 0
                best_ask = min(a["price"] for a in asks) if asks else 1
                if best_bid > 0 and best_ask < 1:
                    spread = (best_ask - best_bid) * 100  # in percentage points

            markets.append({
                "project": project_name,
                "title": market.get("title", ""),
                "slug": market.get("slug", ""),
                "volume": volume,
                "depth": depth,
                "ratio": ratio,
                "type": trade_type,
                "spread": spread,
                "yes_price": market.get("yes_price", 0),
            })

    # Filter to markets with some volume (ignore dead markets)
    active_markets = [m for m in markets if m["volume"] > 100]

    # Sort by volume/depth ratio (highest first = thinnest)
    active_markets.sort(key=lambda x: x["ratio"], reverse=True)

    print(f"\n{'='*100}")
    print("🔍 THINNEST LIMITLESS MARKETS (by Volume/Depth Ratio)")
    print(f"{'='*100}")
    print(f"Higher ratio = more volume relative to available liquidity = needs deeper books\n")

    print(f"{'Project':<20} {'Market':<35} {'Volume':>10} {'Depth':>10} {'Ratio':>8} {'Type':<5} {'Spread':>8}")
    print("-" * 100)

    for m in active_markets[:30]:
        vol_str = f"${m['volume']:,.0f}"
        depth_str = f"${m['depth']:,.0f}" if m['depth'] > 0 else "$0"
        ratio_str = f"{m['ratio']:.1f}x" if m['ratio'] != float('inf') else "∞"
        spread_str = f"{m['spread']:.1f}pp" if m['spread'] is not None else "-"

        # Truncate strings
        project = m['project'][:19]
        title = m['title'][:34]

        print(f"{project:<20} {title:<35} {vol_str:>10} {depth_str:>10} {ratio_str:>8} {m['type']:<5} {spread_str:>8}")

    # Summary stats
    print(f"\n{'='*100}")
    print("📊 SUMMARY")
    print(f"{'='*100}")

    clob_markets = [m for m in active_markets if m["type"] == "clob"]
    amm_markets = [m for m in active_markets if m["type"] == "amm"]

    print(f"Total active markets (>$100 vol): {len(active_markets)}")
    print(f"  CLOB markets: {len(clob_markets)}")
    print(f"  AMM markets: {len(amm_markets)}")

    # Markets with very high ratios (need liquidity most)
    critical = [m for m in active_markets if m["ratio"] > 10]
    print(f"\n⚠️  Critical (ratio > 10x): {len(critical)} markets")

    # Markets with wide spreads
    wide_spread = [m for m in clob_markets if m["spread"] and m["spread"] > 5]
    print(f"⚠️  Wide spread (>5pp): {len(wide_spread)} CLOB markets")

    # Low depth markets
    low_depth = [m for m in active_markets if m["depth"] < 500 and m["volume"] > 500]
    print(f"⚠️  Low depth (<$500) with volume: {len(low_depth)} markets")

    print("\n" + "="*100)
    print("🎯 TOP PRIORITY FOR LIQUIDITY (high volume, low depth, CLOB)")
    print("="*100 + "\n")

    # Priority: CLOB markets with high volume and low depth
    priority = [m for m in clob_markets if m["volume"] > 1000 and m["depth"] < 2000]
    priority.sort(key=lambda x: x["ratio"], reverse=True)

    if priority:
        print(f"{'Project':<20} {'Market':<35} {'Volume':>10} {'Depth':>10} {'Spread':>8}")
        print("-" * 85)
        for m in priority[:15]:
            vol_str = f"${m['volume']:,.0f}"
            depth_str = f"${m['depth']:,.0f}"
            spread_str = f"{m['spread']:.1f}pp" if m['spread'] is not None else "-"
            print(f"{m['project'][:19]:<20} {m['title'][:34]:<35} {vol_str:>10} {depth_str:>10} {spread_str:>8}")
    else:
        print("No CLOB markets matching priority criteria found.")


if __name__ == "__main__":
    analyze_liquidity()
