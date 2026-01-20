"""
Dashboard HTML Generator

Generates the interactive HTML dashboard with all tabs.
"""

import json
import os
import re
from datetime import datetime
from ..config import Config


def generate_html_dashboard(current_markets, prev_snapshot, prev_date, limitless_data=None, leaderboard_data=None, portfolio_data=None, launched_projects=None, kaito_data=None, cookie_data=None, wallchain_data=None, public_mode=False, output_path=None, prev_limitless_data=None, fdv_history=None):
    """Generate an HTML dashboard with data embedded, grouped by PROJECT

    Args:
        public_mode: If True, only show public tabs (Daily Changes, Timeline)
                    and hide internal analysis tabs (Gap Analysis, Arb, Portfolio, Launched)
        output_path: Custom output path for the dashboard file
        prev_limitless_data: Previous Limitless data for calculating price changes
        fdv_history: Historical FDV price data for time series charts
    """
    
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
                "closed": is_closed,
                "yesTokenId": market_data.get("yes_token_id"),
                "noTokenId": market_data.get("no_token_id"),
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
        project["source"] = "polymarket"

    # Add Limitless-only projects (not on Polymarket)
    if limitless_data and limitless_data.get("projects"):
        # Normalize names for matching
        def normalize(s):
            return s.lower().replace(" ", "").replace("-", "").replace("_", "")

        poly_names = {normalize(p["name"]) for p in projects_data}

        # Build lookup for previous Limitless prices
        prev_lim_prices = {}
        if prev_limitless_data and prev_limitless_data.get("projects"):
            for pname, pproj in prev_limitless_data["projects"].items():
                for pm in pproj.get("markets", []):
                    slug = pm.get("slug")
                    if slug:
                        prev_lim_prices[slug] = pm.get("yes_price", 0)

        for lim_name, lim_project in limitless_data["projects"].items():
            if normalize(lim_name) not in poly_names:
                # This is a Limitless-only project
                markets_list = lim_project.get("markets", [])
                if not markets_list:
                    continue

                # Build event structure similar to Polymarket
                event_info = {
                    "slug": f"limitless-{normalize(lim_name)}",
                    "title": lim_name,
                    "volume": lim_project.get("totalVolume", 0),
                    "markets": [],
                    "totalChange": 0,
                    "allClosed": False
                }

                event_total_change = 0
                for market in markets_list:
                    slug = market.get("slug")
                    new_price = market.get("yes_price", 0)
                    old_price = prev_lim_prices.get(slug)

                    # Calculate change if we have previous data
                    if old_price is not None:
                        change = new_price - old_price
                        direction = "up" if change > 0 else ("down" if change < 0 else "none")
                    else:
                        change = 0
                        direction = "none"

                    event_total_change += abs(change)

                    market_info = {
                        "question": market.get("title", ""),
                        "oldPrice": old_price,
                        "newPrice": new_price,
                        "change": change,
                        "direction": direction,
                        "closed": False,
                        "limSlug": slug,
                        "volume": market.get("volume", 0),
                        "liquidity": market.get("liquidity", {}),
                    }
                    event_info["markets"].append(market_info)

                event_info["totalChange"] = event_total_change

                projects_data.append({
                    "name": lim_name,
                    "events": [event_info],
                    "totalChange": event_total_change,
                    "totalVolume": lim_project.get("totalVolume", 0),
                    "hasOpenMarkets": True,
                    "source": "limitless"
                })

        # Re-sort after adding Limitless projects
        projects_data.sort(key=lambda x: (not x["hasOpenMarkets"], -x["totalChange"]))

    # Calculate stats
    total_changes = sum(1 for p in projects_data for e in p["events"] for m in e["markets"] if m["change"] != 0)
    up_count = sum(1 for p in projects_data for e in p["events"] for m in e["markets"] if m["change"] > 0)
    down_count = sum(1 for p in projects_data for e in p["events"] for m in e["markets"] if m["change"] < 0)

    today = datetime.now().strftime("%Y-%m-%d")

    # Define which tabs to show based on public_mode
    # Public: Daily Changes, Timeline (with Kaito/Cookie badges)
    # Internal: + Gap Analysis, Arb Calculator, Portfolio, Launched
    internal_tabs_html = "" if public_mode else '''
            <button class="tab-btn" onclick="switchTab('gap')">🔍 Gap Analysis</button>
            <button class="tab-btn" onclick="switchTab('arb')">💰 Arb Calculator</button>
            <button class="tab-btn" onclick="switchTab('portfolio')">📁 Portfolio</button>
            <button class="tab-btn" onclick="switchTab('launched')">🎯 Launched</button>
            <button class="tab-btn" onclick="switchTab('fdv')">📈 FDV Predictions</button>'''

    internal_tab_content_html = "<!-- Internal tabs hidden in public mode -->" if public_mode else '''<!-- Tab 3: Gap Analysis -->
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

        <!-- Tab 6: Launched Projects -->
        <div id="tab-launched" class="tab-content">
            <div style="text-align:center;margin-bottom:1.5rem;">
                <p style="color:var(--text-secondary);font-size:0.95rem;">
                    Track post-TGE market performance for launched projects
                </p>
            </div>
            <div id="launched-view" style="background:var(--bg-card);border-radius:12px;padding:20px;"></div>
        </div>

        <!-- Tab 7: FDV Predictions -->
        <div id="tab-fdv" class="tab-content">
            <div style="text-align:center;margin-bottom:1.5rem;">
                <p style="color:var(--text-secondary);font-size:0.95rem;">
                    Market-implied FDV predictions. Curves show probability of exceeding each valuation threshold.
                </p>
            </div>
            <div id="fdv-view" style="background:var(--bg-card);border-radius:12px;padding:20px;"></div>
        </div>'''
    
    # Redirect logic for GitHub Pages
    redirect_target = 'public_dashboard.html' if public_mode else 'dashboard.html'

    html = f'''<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <style>html{{visibility:hidden;opacity:0;}}</style>
    <script>
        if (window.location.hostname.includes('github.io')) {{
            window.location.replace(window.location.href.replace('{redirect_target}', 'auth_dashboard.html'));
        }} else {{
            document.documentElement.style.visibility = 'visible';
            document.documentElement.style.opacity = '1';
        }}
    </script>
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
        .event-card.priority-project {{
            border: 2px solid var(--red);
            box-shadow: 0 0 10px rgba(239, 68, 68, 0.3);
        }}
        
        @media (max-width: 768px) {{
            .container {{ padding: 1rem; }}
            .markets-table {{ font-size: 0.75rem; }}
            .price-bar-bg {{ display: none; }}
        }}

        /* Timeline Styles */
        .timeline-container {{
            background: var(--bg-card);
            border-radius: 16px;
            padding: 24px;
            border: 1px solid var(--border);
        }}
        .timeline-month-axis {{
            display: flex;
            padding-left: 175px;
            margin-bottom: 16px;
            border-bottom: 1px solid var(--border);
            padding-bottom: 12px;
        }}
        .timeline-month {{
            flex: 1;
            text-align: center;
            font-size: 0.7rem;
            font-weight: 500;
            color: var(--text-secondary);
            letter-spacing: 0.02em;
        }}
        .timeline-month.current {{
            color: #22c55e;
            font-weight: 600;
        }}
        .timeline-row {{
            margin-bottom: 1px;
        }}
        .timeline-row-inner {{
            display: flex;
            align-items: center;
            height: 32px;
            padding: 2px 8px;
            cursor: pointer;
            border-radius: 6px;
            transition: all 0.15s ease;
            border: 1px solid transparent;
        }}
        .timeline-row-inner:hover {{
            background: rgba(255,255,255,0.04);
            border-color: rgba(255,255,255,0.08);
        }}
        .timeline-change {{
            width: 55px;
            text-align: right;
            padding-right: 8px;
            font-size: 0.7rem;
            font-weight: 600;
        }}
        .timeline-project-name {{
            width: 120px;
            padding-right: 10px;
            text-align: right;
            font-size: 0.8rem;
            font-weight: 500;
            white-space: nowrap;
            overflow: hidden;
            text-overflow: ellipsis;
            display: flex;
            align-items: center;
            justify-content: flex-end;
            gap: 4px;
            color: var(--text);
        }}
        .timeline-bar-container {{
            flex: 1;
            position: relative;
            height: 100%;
        }}
        .timeline-bar {{
            position: absolute;
            height: 20px;
            top: 6px;
            border-radius: 5px;
            transition: all 0.25s ease;
            box-shadow: 0 1px 4px rgba(0,0,0,0.2);
        }}
        .timeline-bar::after {{
            content: '';
            position: absolute;
            top: 0;
            left: 0;
            right: 0;
            height: 40%;
            background: linear-gradient(to bottom, rgba(255,255,255,0.12), transparent);
            border-radius: 5px 5px 0 0;
            pointer-events: none;
        }}
        .timeline-marker {{
            position: absolute;
            width: 3px;
            height: 24px;
            top: 4px;
            border-radius: 2px;
            transition: all 0.2s ease;
        }}
        .timeline-marker.current {{
            background: white;
            box-shadow: 0 0 6px rgba(255,255,255,0.5);
        }}
        .timeline-marker.ghost {{
            opacity: 0.5;
        }}
        .timeline-marker.ghost.earlier {{
            background: rgba(34,197,94,0.6);
        }}
        .timeline-marker.ghost.later {{
            background: rgba(239,68,68,0.6);
        }}
        .timeline-badge {{
            padding: 1px 4px;
            border-radius: 3px;
            font-size: 0.55rem;
            font-weight: 600;
            letter-spacing: 0.01em;
            margin-left: 2px;
        }}
        .timeline-badge.kaito {{
            background: rgba(16,185,129,0.2);
            color: #10b981;
        }}
        .timeline-badge.kaito-post {{
            background: rgba(16,185,129,0.1);
            color: rgba(16,185,129,0.6);
        }}
        .timeline-badge.cookie {{
            background: rgba(245,158,11,0.2);
            color: #f59e0b;
        }}
        .timeline-badge.wallchain {{
            background: rgba(253,200,48,0.2);
            color: #fdc830;
        }}
        .timeline-section-header {{
            padding: 8px 12px;
            margin-bottom: 8px;
            font-size: 0.75rem;
            font-weight: 600;
            color: var(--text-secondary);
            text-transform: uppercase;
            letter-spacing: 0.05em;
            border-bottom: 1px solid var(--border);
            display: flex;
            align-items: center;
            justify-content: space-between;
        }}
        .timeline-section-header.launched {{
            color: #22c55e;
            border-color: rgba(34,197,94,0.3);
            cursor: pointer;
        }}
        .timeline-section-header.launched:hover {{
            background: rgba(34,197,94,0.05);
        }}
        .timeline-collapse-btn {{
            background: none;
            border: none;
            color: #22c55e;
            font-size: 0.7rem;
            cursor: pointer;
            padding: 2px 8px;
            border-radius: 4px;
            transition: all 0.15s ease;
        }}
        .timeline-collapse-btn:hover {{
            background: rgba(34,197,94,0.15);
        }}
        .timeline-launched-content {{
            overflow: hidden;
            max-height: 2000px;
            transition: max-height 0.3s ease;
        }}
        .timeline-launched-content.collapsed {{
            max-height: 0 !important;
        }}
        .timeline-resolved-row {{
            opacity: 0.7;
        }}
        .timeline-resolved-row .timeline-row-inner {{
            background: rgba(34,197,94,0.05);
        }}
        .timeline-resolved-row .timeline-row-inner:hover {{
            background: rgba(34,197,94,0.1);
            opacity: 1;
        }}
        .timeline-resolved-badge {{
            background: #22c55e;
            color: white;
            padding: 2px 6px;
            border-radius: 4px;
            font-size: 0.6rem;
            font-weight: 600;
            margin-left: auto;
            white-space: nowrap;
        }}
        .timeline-tge-date {{
            color: #22c55e;
            font-size: 0.7rem;
            font-weight: 500;
        }}
        .timeline-fdv-panel {{
            margin-left: 175px;
            margin-bottom: 8px;
            margin-top: 0;
            padding: 20px 24px;
            background: linear-gradient(135deg, rgba(30,30,35,0.95) 0%, rgba(25,25,30,0.98) 100%);
            border-radius: 12px;
            border: 1px solid rgba(255,255,255,0.08);
            box-shadow: 0 4px 20px rgba(0,0,0,0.3), inset 0 1px 0 rgba(255,255,255,0.05);
            animation: slideDown 0.2s ease-out;
        }}
        @keyframes slideDown {{
            from {{ opacity: 0; transform: translateY(-8px); }}
            to {{ opacity: 1; transform: translateY(0); }}
        }}
        .fdv-section {{
            margin-bottom: 20px;
            padding-bottom: 16px;
            border-bottom: 1px solid rgba(255,255,255,0.06);
        }}
        .fdv-section:last-child {{
            margin-bottom: 0;
            padding-bottom: 0;
            border-bottom: none;
        }}
        .fdv-section-header {{
            display: flex;
            justify-content: space-between;
            align-items: center;
            margin-bottom: 14px;
        }}
        .fdv-section-title {{
            font-size: 0.85rem;
            font-weight: 600;
            color: var(--text-primary);
            display: flex;
            align-items: center;
            gap: 8px;
            letter-spacing: 0.01em;
        }}
        .fdv-volume-badge {{
            background: linear-gradient(135deg, rgba(99,102,241,0.15) 0%, rgba(99,102,241,0.08) 100%);
            padding: 6px 12px;
            border-radius: 8px;
            border: 1px solid rgba(99,102,241,0.25);
        }}
        .fdv-volume-badge .label {{
            font-size: 0.6rem;
            color: var(--text-secondary);
            margin-right: 6px;
            text-transform: uppercase;
            letter-spacing: 0.03em;
        }}
        .fdv-volume-badge .value {{
            font-size: 0.8rem;
            font-weight: 700;
            color: #a5b4fc;
        }}
        .fdv-cards-row {{
            display: flex;
            flex-wrap: wrap;
            gap: 10px;
        }}
        .fdv-card {{
            flex: 0 0 auto;
            width: 90px;
            background: linear-gradient(145deg, rgba(45,45,55,0.8) 0%, rgba(35,35,45,0.9) 100%);
            border-radius: 10px;
            padding: 12px;
            border: 1px solid rgba(255,255,255,0.06);
            transition: all 0.2s ease;
            position: relative;
            overflow: hidden;
        }}
        .fdv-card::before {{
            content: '';
            position: absolute;
            top: 0;
            left: 0;
            right: 0;
            height: 1px;
            background: linear-gradient(90deg, transparent, rgba(255,255,255,0.1), transparent);
        }}
        .fdv-card:hover {{
            border-color: rgba(255,255,255,0.12);
            transform: translateY(-2px);
            box-shadow: 0 6px 20px rgba(0,0,0,0.25);
        }}
        .fdv-card-header {{
            display: flex;
            align-items: center;
            gap: 6px;
            margin-bottom: 6px;
        }}
        .fdv-card-dot {{
            width: 8px;
            height: 8px;
            border-radius: 50%;
            box-shadow: 0 0 6px currentColor;
        }}
        .fdv-card-label {{
            font-size: 0.8rem;
            font-weight: 600;
            color: var(--text-primary);
        }}
        .fdv-card-volume {{
            font-size: 0.6rem;
            color: var(--text-secondary);
            margin-bottom: 8px;
        }}
        .fdv-yes-no {{
            display: flex;
            gap: 4px;
            border-radius: 6px;
            overflow: hidden;
        }}
        .fdv-yes-no .yes {{
            flex: 1;
            background: linear-gradient(180deg, #22c55e 0%, #16a34a 100%);
            color: white;
            padding: 5px 4px;
            text-align: center;
            font-weight: 700;
            font-size: 0.65rem;
            text-shadow: 0 1px 2px rgba(0,0,0,0.2);
        }}
        .fdv-yes-no .no {{
            flex: 1;
            background: linear-gradient(180deg, #ef4444 0%, #dc2626 100%);
            color: white;
            padding: 5px 4px;
            text-align: center;
            font-weight: 700;
            font-size: 0.65rem;
            text-shadow: 0 1px 2px rgba(0,0,0,0.2);
        }}
        .fdv-chart-container {{
            background: rgba(0,0,0,0.2);
            border-radius: 10px;
            padding: 12px;
            border: 1px solid rgba(255,255,255,0.04);
        }}
        .fdv-chart-row {{
            display: flex;
            gap: 20px;
            align-items: flex-start;
            margin-bottom: 14px;
        }}
        .fdv-chart-legend {{
            flex: 1;
            padding: 8px 12px;
            background: rgba(255,255,255,0.02);
            border-radius: 8px;
            border: 1px solid rgba(255,255,255,0.04);
        }}
        .fdv-chart-legend-title {{
            font-size: 0.6rem;
            color: var(--text-secondary);
            margin-bottom: 8px;
            text-transform: uppercase;
            letter-spacing: 0.05em;
            font-weight: 500;
        }}
        .fdv-chart-legend-item {{
            font-size: 0.7rem;
            color: var(--text-primary);
            margin-bottom: 4px;
            display: flex;
            align-items: center;
            gap: 6px;
        }}
        .fdv-chart-legend-item:last-child {{
            margin-bottom: 0;
        }}

        /* FDV Table Styles */
        .fdv-table {{
            width: 100%;
            border-collapse: collapse;
        }}
        .fdv-table-header {{
            display: grid;
            grid-template-columns: 2fr 1.5fr 1fr 1fr 50px;
            padding: 12px 16px;
            background: rgba(255,255,255,0.03);
            border-radius: 8px 8px 0 0;
            border-bottom: 1px solid rgba(255,255,255,0.08);
            font-size: 0.75rem;
            color: var(--text-secondary);
            text-transform: uppercase;
            letter-spacing: 0.05em;
            font-weight: 500;
        }}
        .fdv-table-row {{
            border-bottom: 1px solid rgba(255,255,255,0.04);
        }}
        .fdv-table-row:last-child {{
            border-bottom: none;
        }}
        .fdv-row-main {{
            display: grid;
            grid-template-columns: 2fr 1.5fr 1fr 1fr 50px;
            padding: 14px 16px;
            align-items: center;
            cursor: pointer;
            transition: background 0.15s ease;
        }}
        .fdv-row-main:hover {{
            background: rgba(255,255,255,0.03);
        }}
        .fdv-project-name {{
            font-weight: 600;
            color: var(--text-primary);
            font-size: 0.95rem;
        }}
        .fdv-predicted-range {{
            font-weight: 600;
            color: var(--accent);
            font-size: 0.9rem;
        }}
        .fdv-change {{
            font-weight: 600;
            font-size: 0.85rem;
        }}
        .fdv-change.positive {{
            color: #22c55e;
        }}
        .fdv-change.negative {{
            color: #ef4444;
        }}
        .fdv-change.neutral {{
            color: var(--text-secondary);
        }}
        .fdv-volume {{
            color: var(--text-secondary);
            font-size: 0.85rem;
        }}
        .fdv-expand-btn {{
            display: flex;
            align-items: center;
            justify-content: center;
            width: 28px;
            height: 28px;
            border-radius: 6px;
            background: rgba(255,255,255,0.05);
            border: 1px solid rgba(255,255,255,0.08);
            color: var(--text-secondary);
            font-size: 0.8rem;
            transition: all 0.15s ease;
        }}
        .fdv-expand-btn.expanded {{
            background: var(--accent);
            color: white;
            border-color: var(--accent);
        }}
        .fdv-row-expanded {{
            display: none;
            padding: 16px;
            background: rgba(0,0,0,0.2);
            border-top: 1px solid rgba(255,255,255,0.04);
            animation: slideDown 0.2s ease-out;
        }}
        .fdv-row-expanded.show {{
            display: block;
        }}
        .fdv-threshold-pills {{
            display: flex;
            flex-wrap: wrap;
            gap: 8px;
            margin-top: 16px;
        }}
        .fdv-threshold-pill {{
            display: flex;
            align-items: center;
            gap: 8px;
            padding: 8px 12px;
            background: rgba(255,255,255,0.04);
            border-radius: 8px;
            border: 1px solid rgba(255,255,255,0.06);
        }}
        .fdv-pill-dot {{
            width: 8px;
            height: 8px;
            border-radius: 50%;
        }}
        .fdv-pill-label {{
            font-weight: 600;
            font-size: 0.8rem;
            color: var(--text-primary);
        }}
        .fdv-pill-prob {{
            font-size: 0.75rem;
            font-weight: 600;
        }}
        @keyframes fadeIn {{
            from {{ opacity: 0; transform: translateY(-4px); }}
            to {{ opacity: 1; transform: translateY(0); }}
        }}
    </style>
</head>
<body>
    <div class="container">
        <header>
            <h1>🚀 Pre-TGE Tracker</h1>
            <p class="subtitle">Polymarket & Limitless prediction markets</p>
            <div class="date-range">📅 {today}</div>
        </header>

        <div class="tab-nav">
            <button class="tab-btn" onclick="switchTab('changes')">📊 Daily Changes</button>
            <button class="tab-btn active" onclick="switchTab('timeline')">🚀 Launch Timeline</button>{internal_tabs_html}
        </div>

        <!-- Tab 1: Daily Changes -->
        <div id="tab-changes" class="tab-content">
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
        <div id="tab-timeline" class="tab-content active">
            <div style="text-align:center;margin-bottom:1.5rem;">
                <p style="color:var(--text-secondary);font-size:0.95rem;">
                    Token launch predictions from Polymarket & Limitless. Bar color intensity = probability.
                </p>
            </div>
            <div class="legend" style="display:flex;justify-content:center;gap:20px;margin-bottom:1.5rem;flex-wrap:wrap;padding:12px 20px;background:var(--bg-secondary);border-radius:10px;border:1px solid var(--border);">
                <div style="display:flex;align-items:center;gap:6px;">
                    <div style="width:20px;height:10px;background:rgba(99,102,241,0.5);border-radius:4px;box-shadow:0 1px 3px rgba(0,0,0,0.2);"></div>
                    <span style="font-size:0.75rem;color:var(--text-secondary);">Default</span>
                </div>
                <div style="display:flex;align-items:center;gap:6px;">
                    <div style="width:20px;height:10px;background:rgba(16,185,129,0.5);border-radius:4px;box-shadow:0 1px 3px rgba(0,0,0,0.2);"></div>
                    <span style="font-size:0.75rem;color:var(--text-secondary);">Kaito</span>
                </div>
                <div style="display:flex;align-items:center;gap:6px;">
                    <div style="width:20px;height:10px;background:rgba(245,158,11,0.5);border-radius:4px;box-shadow:0 1px 3px rgba(0,0,0,0.2);"></div>
                    <span style="font-size:0.75rem;color:var(--text-secondary);">Cookie</span>
                </div>
                <div style="display:flex;align-items:center;gap:6px;">
                    <div style="width:20px;height:10px;background:rgba(253,200,48,0.5);border-radius:4px;box-shadow:0 1px 3px rgba(0,0,0,0.2);"></div>
                    <span style="font-size:0.75rem;color:var(--text-secondary);">Wallchain</span>
                </div>
                <div style="display:flex;align-items:center;gap:6px;">
                    <div style="width:3px;height:12px;background:white;border-radius:2px;box-shadow:0 0 4px rgba(255,255,255,0.5);"></div>
                    <span style="font-size:0.75rem;color:var(--text-secondary);">50% mark</span>
                </div>
                <div style="display:flex;align-items:center;gap:6px;">
                    <div style="width:3px;height:12px;background:rgba(34,197,94,0.5);border-radius:2px;"></div>
                    <span style="font-size:0.75rem;color:var(--text-secondary);">Earlier vs yesterday</span>
                </div>
                <div style="display:flex;align-items:center;gap:6px;">
                    <div style="width:3px;height:12px;background:rgba(239,68,68,0.5);border-radius:2px;"></div>
                    <span style="font-size:0.75rem;color:var(--text-secondary);">Later vs yesterday</span>
                </div>
            </div>
            <div id="timeline-viz" style="background:var(--bg-card);border-radius:12px;padding:20px;overflow-x:auto;"></div>
        </div>

        {internal_tab_content_html}
    </div>

    <script>
        const projectsData = {json.dumps(projects_data)};
        const limitlessData = {json.dumps(limitless_data.get('projects', {}) if limitless_data else {})};
        const limitlessError = {json.dumps(limitless_data.get('error') if limitless_data else None)};
        const leaderboardData = {json.dumps(leaderboard_data if leaderboard_data else {})};
        const portfolioData = {json.dumps([] if public_mode else (portfolio_data if portfolio_data else []))};
        const launchedProjectsData = {json.dumps(launched_projects if launched_projects else [])};
        const kaitoData = {json.dumps(kaito_data if kaito_data else {"pre_tge": [], "post_tge": []})};
        const cookieData = {json.dumps(cookie_data if cookie_data else {"slugs": [], "active_campaigns": []})};
        const wallchainData = {json.dumps(wallchain_data if wallchain_data else {"slugs": [], "active_campaigns": []})};
        const fdvHistoryData = {json.dumps(fdv_history if fdv_history else {})};
        const publicMode = {'true' if public_mode else 'false'};
        let showClosed = false;
        let gapRendered = false;
        let arbRendered = false;
        let portfolioRendered = false;
        let launchedRendered = false;
        let fdvRendered = false;
        let fdvFilterProject = null;  // Filter FDV to show only this project
        let expandedTimelineProject = null;  // Currently expanded project on timeline
        let launchedSectionCollapsed = false;

        function toggleLaunchedSection() {{
            const content = document.getElementById('launched-content');
            const btn = document.getElementById('launched-toggle-btn');
            if (!content || !btn) return;

            launchedSectionCollapsed = !launchedSectionCollapsed;
            if (launchedSectionCollapsed) {{
                content.classList.add('collapsed');
                btn.textContent = 'Show ▼';
            }} else {{
                content.classList.remove('collapsed');
                btn.textContent = 'Hide ▲';
            }}
        }}

        function toggleTimelineFdv(projectName) {{
            const cleanName = projectName.replace(/[^a-zA-Z0-9]/g, '');
            const container = document.getElementById('fdv-inline-' + cleanName);
            const icon = document.getElementById('fdv-icon-' + cleanName);
            
            if (!container) return;
            
            // If already expanded, collapse it
            if (expandedTimelineProject === projectName) {{
                container.style.display = 'none';
                if (icon) icon.style.transform = 'rotate(0deg)';
                expandedTimelineProject = null;
                return;
            }}
            
            // Collapse any previously expanded
            if (expandedTimelineProject) {{
                const prevClean = expandedTimelineProject.replace(/[^a-zA-Z0-9]/g, '');
                const prevContainer = document.getElementById('fdv-inline-' + prevClean);
                const prevIcon = document.getElementById('fdv-icon-' + prevClean);
                if (prevContainer) prevContainer.style.display = 'none';
                if (prevIcon) prevIcon.style.transform = 'rotate(0deg)';
            }}
            
            // Expand this project
            expandedTimelineProject = projectName;
            if (icon) icon.style.transform = 'rotate(180deg)';
            container.style.display = 'block';
            
            // Render mini FDV chart for this project
            renderInlineFdv(projectName, container);
        }}
        
        function renderInlineFdv(projectName, container) {{
            let html = '';
            
            // ===== TIMELINE MARKETS SECTION =====
            const timelineData = buildTimelineData();
            const milestones = timelineData[projectName];

            if (milestones && milestones.length > 0) {{
                html += `<div class="fdv-section">`;
                html += `<div class="fdv-section-header"><div class="fdv-section-title">📅 Launch Timeline</div></div>`;
                html += `<div class="fdv-cards-row">`;

                milestones.slice(0, 6).forEach(m => {{
                    const prob = (m.prob * 100).toFixed(0);
                    const noProb = (100 - m.prob * 100).toFixed(0);
                    // Format as "Jan 31" style
                    const months = ['Jan','Feb','Mar','Apr','May','Jun','Jul','Aug','Sep','Oct','Nov','Dec'];
                    const month = months[parseInt(m.date.slice(5, 7)) - 1];
                    const day = parseInt(m.date.slice(8, 10));
                    const dateLabel = month + ' ' + day;

                    // Color based on probability
                    const probVal = parseFloat(prob);
                    const dateColor = probVal >= 70 ? '#22c55e' : probVal >= 40 ? '#f59e0b' : '#6b7280';

                    html += `
                        <div class="fdv-card">
                            <div style="font-size:0.7rem;color:var(--text-secondary);margin-bottom:2px;">by</div>
                            <div class="fdv-card-label" style="margin-bottom:8px;color:${{dateColor}};">${{dateLabel}}</div>
                            <div class="fdv-yes-no">
                                <div class="yes">${{prob}}%</div>
                                <div class="no">${{noProb}}%</div>
                            </div>
                        </div>
                    `;
                }});

                html += '</div></div>';
            }}
            
            // ===== FDV SECTION =====
            const data = fdvHistoryData[projectName];
            if (!data || !data.thresholds || data.thresholds.length === 0) {{
                if (html === '') {{
                    container.innerHTML = '<p style="color:var(--text-secondary);font-size:0.75rem;margin:0;text-align:center;padding:8px 0;">No market data available for this project.</p>';
                    return;
                }}
                container.innerHTML = html;
                return;
            }}

            const colors = ['#22c55e', '#f59e0b', '#8b5cf6', '#06b6d4', '#ef4444', '#ec4899'];
            const thresholds = data.thresholds;
            const allDates = [...new Set(thresholds.flatMap(t => t.history.map(h => h.date)))].sort();

            if (allDates.length < 2) {{
                container.innerHTML = html + '<p style="color:var(--text-secondary);font-size:0.75rem;margin:0;padding-top:8px;">Not enough FDV historical data yet.</p>';
                return;
            }}
            
            // Build mini chart
            const width = 500;
            const height = 120;
            const padding = {{ left: 35, right: 90, top: 15, bottom: 25 }};
            const chartW = width - padding.left - padding.right;
            const chartH = height - padding.top - padding.bottom;
            
            let pathsSvg = '';
            let legendHtml = '';
            
            thresholds.slice(0, 5).forEach((th, idx) => {{
                const color = colors[idx % colors.length];
                const history = th.history.sort((a,b) => a.date.localeCompare(b.date));
                if (history.length < 2) return;
                
                const points = history.map(h => {{
                    const dateIdx = allDates.indexOf(h.date);
                    const x = padding.left + (chartW * dateIdx / (allDates.length - 1));
                    const y = padding.top + chartH * (1 - h.price);
                    return {{ x, y }};
                }});
                
                let pathD = `M ${{points[0].x.toFixed(1)}} ${{points[0].y.toFixed(1)}}`;
                for (let i = 1; i < points.length; i++) {{
                    pathD += ` L ${{points[i].x.toFixed(1)}} ${{points[i].y.toFixed(1)}}`;
                }}
                
                const currentPct = (history[history.length - 1].price * 100).toFixed(0);
                const lastPt = points[points.length - 1];
                
                // Glow effect + main line
                pathsSvg += `<path d="${{pathD}}" fill="none" stroke="${{color}}" stroke-width="4" stroke-opacity="0.2" stroke-linecap="round"/>`;
                pathsSvg += `<path d="${{pathD}}" fill="none" stroke="${{color}}" stroke-width="2" stroke-linecap="round"/>`;
                // Endpoint with glow
                pathsSvg += `<circle cx="${{lastPt.x}}" cy="${{lastPt.y}}" r="5" fill="${{color}}" fill-opacity="0.3"/>`;
                pathsSvg += `<circle cx="${{lastPt.x}}" cy="${{lastPt.y}}" r="3" fill="${{color}}"/>`;
                
                legendHtml += `<div class="fdv-chart-legend-item"><span style="width:8px;height:8px;border-radius:50%;background:${{color}};display:inline-block;box-shadow:0 0 4px ${{color}};"></span> ${{th.label.replace('>', '')}} <span style="color:${{color}};font-weight:600;">(${{currentPct}}%)</span></div>`;
            }});
            
            // Build threshold cards
            let cardsHtml = '';
            thresholds.slice(0, 6).forEach((th, idx) => {{
                const color = colors[idx % colors.length];
                const currentPrice = th.history.length > 0 ? th.history[th.history.length - 1].price : 0;
                const yesPercentage = (currentPrice * 100).toFixed(0);
                const noPercentage = (100 - currentPrice * 100).toFixed(0);

                cardsHtml += `
                    <div class="fdv-card">
                        <div class="fdv-card-header">
                            <div class="fdv-card-dot" style="background:${{color}};"></div>
                            <span class="fdv-card-label">${{th.label.replace('>', '')}}</span>
                        </div>
                        <div class="fdv-card-volume">${{formatVolume(th.volume)}} Vol</div>
                        <div class="fdv-yes-no">
                            <div class="yes">${{yesPercentage}}%</div>
                            <div class="no">${{noPercentage}}%</div>
                        </div>
                    </div>
                `;
            }});
            
            // Calculate total volume
            const totalVolume = thresholds.reduce((sum, t) => sum + (t.volume || 0), 0);
            
            const fdvHtml = `
                <div class="fdv-section">
                    <div class="fdv-section-header">
                        <div class="fdv-section-title">📈 FDV Predictions</div>
                        <div class="fdv-volume-badge">
                            <span class="label">Total Vol</span>
                            <span class="value">${{formatVolume(totalVolume)}}</span>
                        </div>
                    </div>
                    <div class="fdv-chart-row">
                        <div class="fdv-chart-container">
                            <svg width="${{width}}" height="${{height}}" style="display:block;">
                                <defs>
                                    <linearGradient id="gridGrad" x1="0%" y1="0%" x2="0%" y2="100%">
                                        <stop offset="0%" style="stop-color:rgba(255,255,255,0.06)"/>
                                        <stop offset="100%" style="stop-color:rgba(255,255,255,0.02)"/>
                                    </linearGradient>
                                </defs>
                                <line x1="${{padding.left}}" y1="${{padding.top}}" x2="${{width - padding.right}}" y2="${{padding.top}}" stroke="rgba(255,255,255,0.05)" stroke-dasharray="2,4"/>
                                <line x1="${{padding.left}}" y1="${{padding.top + chartH/2}}" x2="${{width - padding.right}}" y2="${{padding.top + chartH/2}}" stroke="rgba(255,255,255,0.05)" stroke-dasharray="2,4"/>
                                <line x1="${{padding.left}}" y1="${{padding.top + chartH}}" x2="${{width - padding.right}}" y2="${{padding.top + chartH}}" stroke="rgba(255,255,255,0.05)" stroke-dasharray="2,4"/>
                                <text x="${{padding.left - 6}}" y="${{padding.top + 3}}" text-anchor="end" fill="rgba(255,255,255,0.4)" font-size="9" font-weight="500">100%</text>
                                <text x="${{padding.left - 6}}" y="${{padding.top + chartH/2 + 3}}" text-anchor="end" fill="rgba(255,255,255,0.4)" font-size="9" font-weight="500">50%</text>
                                <text x="${{padding.left - 6}}" y="${{padding.top + chartH + 3}}" text-anchor="end" fill="rgba(255,255,255,0.4)" font-size="9" font-weight="500">0%</text>
                                ${{pathsSvg}}
                            </svg>
                        </div>
                        <div class="fdv-chart-legend">
                            <div class="fdv-chart-legend-title">Thresholds</div>
                            ${{legendHtml}}
                        </div>
                    </div>
                    <div class="fdv-cards-row">
                        ${{cardsHtml}}
                    </div>
                </div>
            `;
            
            container.innerHTML = html + fdvHtml;
        }}
        
        function showProjectFdv(projectName) {{
            fdvFilterProject = projectName;
            fdvRendered = false;
            switchTab('fdv');
        }}
        
        function clearFdvFilter() {{
            fdvFilterProject = null;
            fdvRendered = false;
            renderFdvPredictions();
        }}

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
                const isLimitless = project.source === 'limitless';

                return `
                    <div class="event-card${{idx >= 5 ? ' collapsed' : ''}}${{isClosed ? ' closed-project' : ''}}" id="project-${{projectId}}">
                        <div class="event-header" onclick="toggleProject('${{project.name}}')">
                            <div style="display:flex;align-items:center;">
                                <span class="toggle-icon">▼</span>
                                <span class="event-title" style="cursor:pointer">${{project.name}}</span>
                                ${{isLimitless ? '<span class="closed-badge" style="background:#DCF58C;color:#1a1a1a;margin-left:0.5rem;">LIMITLESS</span>' : ''}}
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
                            ${{project.events.map(event => {{
                                const isLimEvent = event.slug.startsWith('limitless-');
                                const eventUrl = isLimEvent
                                    ? 'https://limitless.exchange/pro?category=43'
                                    : 'https://polymarket.com/event/' + event.slug;
                                const linkColor = isLimEvent ? '#DCF58C' : 'var(--accent)';
                                return `
                                <div style="border-top:1px solid var(--border);padding:0.5rem 1rem 0;">
                                    <div style="display:flex;align-items:center;margin-bottom:0.5rem;">
                                        <a href="${{eventUrl}}" target="_blank"
                                           style="font-size:0.85rem;color:${{linkColor}};text-decoration:none;">
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
                                            ${{event.markets.filter(m => showClosed || !m.closed).map(m => {{
                                                const marketUrl = m.limSlug
                                                    ? 'https://limitless.exchange/pro/markets/' + m.limSlug
                                                    : (m.yesTokenId ? 'https://polymarket.com/event/' + event.slug : null);
                                                return `
                                                <tr style="${{m.closed ? 'opacity:0.5;' : ''}}">
                                                    <td class="market-question">
                                                        ${{marketUrl
                                                            ? `<a href="${{marketUrl}}" target="_blank" style="color:inherit;text-decoration:none;border-bottom:1px dotted var(--text-secondary);">${{m.question}}</a>`
                                                            : m.question}}
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
                                            `}}).join('')}}
                                        </tbody>
                                    </table>
                                </div>
                            `}}).join('')}}
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
            if (tab === 'launched' && !launchedRendered) {{
                renderLaunchedProjects();
                launchedRendered = true;
            }}
            if (tab === 'fdv' && !fdvRendered) {{
                renderFdvPredictions();
                fdvRendered = true;
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
                const source = project.source || 'polymarket';
                project.events.forEach(event => {{
                    event.markets.forEach(market => {{
                        if (market.closed) return;
                        const q = market.question.toLowerCase();
                        if (q.includes('launch') && q.includes('by')) {{
                            const dateMatch = q.match(/by\\s+(\\w+)\\s+(\\d+),?\\s*(\\d*)/i);
                            if (dateMatch) {{
                                const monthStr = dateMatch[1];
                                const day = dateMatch[2];
                                const year = dateMatch[3] || new Date().getFullYear().toString();
                                const months = {{'jan':0,'january':0,'feb':1,'february':1,'mar':2,'march':2,'apr':3,'april':3,'may':4,'jun':5,'june':5,'jul':6,'july':6,'aug':7,'august':7,'sep':8,'september':8,'oct':9,'october':9,'nov':10,'november':10,'dec':11,'december':11}};
                                const monthNum = months[monthStr.toLowerCase()];
                                if (monthNum !== undefined) {{
                                    const dateKey = `${{year}}-${{String(monthNum+1).padStart(2,'0')}}-${{String(day).padStart(2,'0')}}`;
                                    if (!timeline[project.name]) timeline[project.name] = [];
                                    timeline[project.name].push({{
                                        date: dateKey,
                                        prob: market.newPrice,
                                        change: market.change || 0,
                                        source: source
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
        
        // Helper to get FDV-based daily change for a project
        function getProjectFdvChange(projName) {{
            const data = fdvHistoryData[projName];
            if (!data || !data.thresholds || data.thresholds.length === 0) return 0;
            
            // Calculate max change across thresholds using recent history
            let maxChange = 0;
            for (const th of data.thresholds) {{
                if (th.history && th.history.length >= 2) {{
                    const sorted = [...th.history].sort((a, b) => a.date.localeCompare(b.date));
                    const latest = sorted[sorted.length - 1].price;
                    const previous = sorted[sorted.length - 2].price;
                    const change = latest - previous;
                    if (Math.abs(change) > Math.abs(maxChange)) {{
                        maxChange = change;
                    }}
                }}
            }}
            return maxChange;
        }}
        
        function renderTimeline() {{
            const container = document.getElementById('timeline-viz');
            const timelineData = buildTimelineData();
            const projects = Object.keys(timelineData).filter(p => timelineData[p].length > 0);

            // Get launched projects and filter out ones that are in timeline data
            const launchedNames = (launchedProjectsData || []).map(p => p.name.toLowerCase());
            const pendingProjects = projects.filter(p => !launchedNames.includes(p.toLowerCase()));

            if (projects.length === 0 && (!launchedProjectsData || launchedProjectsData.length === 0)) {{
                container.innerHTML = '<p style="text-align:center;color:var(--text-secondary);padding:2rem;">No launch date markets found in current data.</p>';
                return;
            }}
            
            // Define months dynamically starting from current month
            const now = new Date();
            const startYear = now.getFullYear();
            const startMonth = now.getMonth() + 1; // 1-indexed
            const months = [];
            const monthLabels = ['Jan','Feb','Mar','Apr','May','Jun','Jul','Aug','Sep','Oct','Nov','Dec'];

            // Generate 12 months from current month
            for (let i = 0; i < 12; i++) {{
                const m = ((startMonth - 1 + i) % 12) + 1;
                const year = startYear + Math.floor((startMonth - 1 + i) / 12);
                const lastDay = new Date(year, m, 0).getDate();
                months.push({{
                    label: monthLabels[m-1],
                    key: `${{year}}-${{String(m).padStart(2,'0')}}-${{lastDay}}`,
                    year, month: m
                }});
            }}

            const currentMonth = 0; // Current month is always first
            
            // Helper to get leaderboard info
            function getLeaderboard(projName) {{
                const key = projName.toLowerCase();
                return leaderboardData[key] || null;
            }}

            // Sort pending projects: leaderboard projects first, then by earliest 50% threshold
            const sorted = pendingProjects.sort((a,b) => {{
                const aLb = getLeaderboard(a);
                const bLb = getLeaderboard(b);

                // Leaderboard projects come first
                if (aLb && !bLb) return -1;
                if (!aLb && bLb) return 1;

                // Sort by earliest 50% date, or fall back to first milestone date
                const aFirst50 = timelineData[a].find(m => m.prob >= 0.5);
                const bFirst50 = timelineData[b].find(m => m.prob >= 0.5);
                const aDate = aFirst50 ? aFirst50.date : timelineData[a][0].date;
                const bDate = bFirst50 ? bFirst50.date : timelineData[b][0].date;
                return aDate.localeCompare(bDate);
            }});

            // Sort launched projects by TGE date (most recent first), filter to 2026 only
            const currentYear = new Date().getFullYear();
            const sortedLaunched = (launchedProjectsData || [])
                .filter(p => p.tge_date && p.tge_date.startsWith(String(currentYear)))
                .sort((a, b) => b.tge_date.localeCompare(a.tge_date));

            let html = '<div class="timeline-container" style="min-width:800px;">';

            // Month axis
            html += '<div class="timeline-month-axis">';
            months.forEach((m, i) => {{
                const isCurrent = i === currentMonth;
                html += `<div class="timeline-month${{isCurrent ? ' current' : ''}}">${{m.label}}</div>`;
            }});
            html += '</div>';

            // LAUNCHED SECTION - Show resolved projects at top (collapsible)
            if (sortedLaunched.length > 0) {{
                html += `<div class="timeline-section-header launched" onclick="toggleLaunchedSection()">
                    <span>✓ Launched in ${{currentYear}} (${{sortedLaunched.length}})</span>
                    <span class="timeline-collapse-btn" id="launched-toggle-btn">Hide ▲</span>
                </div>`;
                html += '<div class="timeline-launched-content" id="launched-content">';

                // Column headers
                html += `<div class="timeline-row" style="opacity:0.6;margin-bottom:4px;">`;
                html += `<div class="timeline-row-inner" style="cursor:default;">`;
                html += `<div class="timeline-change"></div>`;
                html += `<div class="timeline-project-name" style="font-size:0.6rem;font-weight:400;">Project</div>`;
                html += `<div class="timeline-bar-container"></div>`;
                html += `<div style="display:grid;grid-template-columns:100px 90px 80px 90px 100px;align-items:center;gap:8px;padding-left:12px;font-size:0.55rem;color:var(--text-secondary);width:500px;flex-shrink:0;">`;
                html += `<span>TGE Date</span>`;
                html += `<span>Launch Mkt</span>`;
                html += `<span>FDV Result</span>`;
                html += `<span>FDV Vol</span>`;
                html += `<span></span>`;
                html += `</div>`;
                html += `</div></div>`;

                sortedLaunched.forEach(proj => {{
                    const projName = proj.name;
                    const tgeDate = new Date(proj.tge_date);
                    const formattedDate = tgeDate.toLocaleDateString('en-US', {{ month: 'short', day: 'numeric', year: 'numeric' }});

                    // Get volume breakdown and FDV result (from list_projects summary)
                    const fdvVol = proj.fdv_market_volume || 0;
                    const launchVol = proj.launch_market_volume || 0;
                    const fdvResult = proj.fdv_result;  // e.g., "$500M"

                    // Format volumes
                    const fmtVol = (v) => v >= 1000000 ? '$' + (v/1000000).toFixed(1) + 'M' : v >= 1000 ? '$' + (v/1000).toFixed(0) + 'K' : '$' + v.toFixed(0);

                    // Calculate position on timeline for TGE date marker
                    let tgeIdx = -1;
                    const tgeDateStr = proj.tge_date;
                    for (let i = 0; i < months.length; i++) {{
                        if (months[i].key >= tgeDateStr) {{
                            tgeIdx = i;
                            break;
                        }}
                    }}

                    html += `<div class="timeline-row timeline-resolved-row">`;
                    html += `<div class="timeline-row-inner">`;
                    html += `<div class="timeline-change"></div>`;
                    html += `<div class="timeline-project-name">${{projName}}</div>`;
                    html += `<div class="timeline-bar-container">`;

                    // Show a green marker at the TGE date position
                    if (tgeIdx >= 0 && tgeIdx < months.length) {{
                        const markerPct = ((tgeIdx + 0.5) / months.length) * 100;
                        html += `<div class="timeline-marker" style="left:${{markerPct}}%;background:#22c55e;box-shadow:0 0 6px rgba(34,197,94,0.5);"></div>`;
                    }}

                    html += `</div>`;
                    // Aligned columns: Date | Launch Vol | FDV Result | FDV Vol | Badge
                    html += `<div style="display:grid;grid-template-columns:100px 90px 80px 90px 100px;align-items:center;gap:8px;padding-left:12px;font-size:0.65rem;width:500px;flex-shrink:0;">`;
                    // TGE Date
                    html += `<span class="timeline-tge-date">${{formattedDate}}</span>`;
                    // Launch Vol
                    html += `<span style="color:var(--text-secondary);">${{launchVol > 0 ? 'Launch: ' + fmtVol(launchVol) : '-'}}</span>`;
                    // FDV Result
                    html += `<span style="color:#22c55e;">${{fdvResult ? '>' + fdvResult : '-'}}</span>`;
                    // FDV Vol
                    html += `<span style="color:var(--text-secondary);">${{fdvVol > 0 ? fmtVol(fdvVol) : '-'}}</span>`;
                    // Badge
                    html += `<span class="timeline-resolved-badge">✓ LAUNCHED</span>`;
                    html += `</div>`;
                    html += `</div></div>`;
                }});

                html += '</div>'; // Close launched-content

                // Add pending section header if there are pending projects
                if (sorted.length > 0) {{
                    html += '<div class="timeline-section-header" style="margin-top:16px;">📅 Upcoming</div>';
                }}
            }}

            // PENDING PROJECTS - existing timeline rows
            sorted.forEach(proj => {{
                const milestones = timelineData[proj];
                const first = milestones[0];
                const last = milestones[milestones.length - 1];
                const lb = getLeaderboard(proj);

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

                // Find 50% threshold position (today)
                let p50Idx = -1;
                for (let i = 0; i < months.length; i++) {{
                    const monthKey = months[i].key;
                    const relevant = milestones.filter(m => m.date <= monthKey);
                    if (relevant.length > 0 && relevant[relevant.length-1].prob >= 0.5) {{
                        p50Idx = i;
                        break;
                    }}
                }}
                
                // Find yesterday's 50% position (use prob - change for each milestone)
                let p50IdxYesterday = -1;
                for (let i = 0; i < months.length; i++) {{
                    const monthKey = months[i].key;
                    const relevant = milestones.filter(m => m.date <= monthKey);
                    if (relevant.length > 0) {{
                        const m = relevant[relevant.length-1];
                        const yesterdayProb = (m.prob || 0) - (m.change || 0);
                        if (yesterdayProb >= 0.5) {{
                            p50IdxYesterday = i;
                            break;
                        }}
                    }}
                }}

                // Kaito status lookup
                const projLower = proj.toLowerCase().replace(/[^a-z0-9]/g, '');
                const kaitoPreTge = kaitoData.pre_tge || [];
                const kaitoPostTge = kaitoData.post_tge || [];
                const isKaitoPreTge = kaitoPreTge.some(k => k.toLowerCase().replace(/[^a-z0-9]/g, '') === projLower);
                const isKaitoPostTge = kaitoPostTge.some(k => k.toLowerCase().replace(/[^a-z0-9]/g, '') === projLower);
                
                // Cookie status lookup
                const cookieSlugs = cookieData.slugs || [];
                const hasCookieCampaign = cookieSlugs.some(s => s.replace(/-/g, '') === projLower);

                // Wallchain status lookup
                const wallchainSlugs = wallchainData.slugs || [];
                const hasWallchainCampaign = wallchainSlugs.some(s => s.replace(/-/g, '') === projLower);

                // Limitless-only check (if first milestone is from limitless)
                const isLimitlessOnly = milestones[0].source === 'limitless';

                // Get FDV-based change for this project
                const dailyChange = getProjectFdvChange(proj);
                const changePct = (dailyChange * 100).toFixed(1);
                const hasSignificantChange = Math.abs(dailyChange) >= 0.01; // 1pp or more
                
                // Calculate bar color based on infofi platform status
                const lastProb = milestones[milestones.length-1].prob;
                const alpha = 0.15 + lastProb * 0.8;
                const barColor = isKaitoPreTge ? '16,185,129' : hasCookieCampaign ? '245,158,11' : hasWallchainCampaign ? '253,200,48' : lb ? '139,92,246' : '99,102,241';

                // Build badges using CSS classes
                let badges = '';
                if (isKaitoPreTge) {{
                    badges += '<span class="timeline-badge kaito">K</span>';
                }} else if (isKaitoPostTge) {{
                    badges += '<span class="timeline-badge kaito-post">K</span>';
                }}
                if (hasCookieCampaign) {{
                    badges += '<span class="timeline-badge cookie">C</span>';
                }}
                if (hasWallchainCampaign) {{
                    badges += '<span class="timeline-badge wallchain">W</span>';
                }}
                
                // Build change indicator (fixed width, left-aligned column)
                let changeIndicator = '';
                if (hasSignificantChange) {{
                    const changeColor = dailyChange > 0 ? '#22c55e' : '#ef4444';
                    const changeSign = dailyChange > 0 ? '▲' : '▼';
                    changeIndicator = `<span style="color:${{changeColor}};font-weight:600;font-size:0.7rem;">${{changeSign}}${{Math.abs(changePct)}}%</span>`;
                }}

                html += `<div class="timeline-row" id="timeline-row-${{proj.replace(/[^a-zA-Z0-9]/g, '')}}">`;
                html += `<div class="timeline-row-inner" onclick="toggleTimelineFdv('${{proj}}')">`;
                // Fixed-width change column (left)
                html += `<div class="timeline-change">${{changeIndicator}}</div>`;
                // Project name + badges
                html += `<div class="timeline-project-name">${{proj}}${{badges}}</div>`;
                html += `<div class="timeline-bar-container">`;
                html += `<div class="timeline-bar" style="left:${{leftPct}}%;width:${{widthPct}}%;background:rgba(${{barColor}},${{alpha.toFixed(2)}});"></div>`;

                // Ghost marker for yesterday's 50% position (if different from today)
                // Green = launch moved earlier (good), Red = launch slipped later
                if (p50IdxYesterday !== -1 && p50IdxYesterday !== p50Idx) {{
                    const ghostMarkerPct = ((p50IdxYesterday + 0.5) / months.length) * 100;
                    const shiftedEarlier = p50Idx < p50IdxYesterday;
                    const ghostClass = shiftedEarlier ? 'earlier' : 'later';
                    html += `<div class="timeline-marker ghost ${{ghostClass}}" style="left:${{ghostMarkerPct}}%;"></div>`;
                }}

                // Today's 50% marker (solid white)
                if (p50Idx !== -1) {{
                    const markerPct = ((p50Idx + 0.5) / months.length) * 100;
                    html += `<div class="timeline-marker current" style="left:${{markerPct}}%;"></div>`;
                }}

                html += '</div></div>';

                // Expandable FDV section (hidden by default)
                html += `<div id="fdv-inline-${{proj.replace(/[^a-zA-Z0-9]/g, '')}}" class="timeline-fdv-panel" style="display:none;"></div>`;
                
                html += '</div>';
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

            // Extract date from market question (e.g., "by February 28", "by Q1 2026")
            function extractDate(q) {{
                // Match patterns like "by February 28", "by March 31, 2026", "by Q1 2026", "by December 31"
                const datePatterns = [
                    /by\\s+(january|february|march|april|may|june|july|august|september|october|november|december)\\s+(\\d{{1,2}})(?:,?\\s*(\\d{{4}}))?/i,
                    /by\\s+(q[1-4])\\s*(\\d{{4}})?/i,
                    /by\\s+(end of\\s+)?(january|february|march|april|may|june|july|august|september|october|november|december)(?:\\s+(\\d{{4}}))?/i
                ];
                for (const pattern of datePatterns) {{
                    const match = q.match(pattern);
                    if (match) return match[0].toLowerCase().replace(/\\s+/g, ' ');
                }}
                return null;
            }}

            // Normalize question for comparison
            function normalizeQuestion(q) {{
                return q.toLowerCase()
                    .replace(/[^a-z0-9\\s]/g, '')
                    .replace(/\\s+/g, ' ')
                    .trim();
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

            // Find matching Limitless market by threshold, date, or question similarity
            function findMarketMatch(polyQuestion, limitlessMarkets, alreadyMatched = new Set()) {{
                // limitlessMarkets is an array of market objects
                // Filter out already matched markets
                const markets = (limitlessMarkets || []).filter(m => !alreadyMatched.has(m.slug));

                // Try threshold matching first (for FDV markets)
                const polyThreshold = extractThreshold(polyQuestion);
                if (polyThreshold) {{
                    for (const lm of markets) {{
                        const limThreshold = extractThreshold(lm.title || lm.question || '');
                        if (limThreshold && polyThreshold === limThreshold) {{
                            return lm;
                        }}
                    }}
                }}

                // Try date matching (for launch date markets)
                const polyDate = extractDate(polyQuestion);
                if (polyDate) {{
                    for (const lm of markets) {{
                        const limDate = extractDate(lm.title || lm.question || '');
                        if (limDate && polyDate === limDate) {{
                            return lm;
                        }}
                    }}
                }}

                // No fallback similarity matching - only exact threshold/date matches
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
                        polyPrice: m.newPrice,
                        yesTokenId: m.yesTokenId,
                        noTokenId: m.noTokenId
                    }}))
                );

                const matchedMarkets = [];
                const unmatchedMarkets = []; // Polymarket-only
                const limOnlyMarkets = []; // Limitless-only
                const matchedLimSlugs = new Set(); // Track which Limitless markets were matched

                polyMarkets.forEach(pm => {{
                    if (limitlessProject && limitlessProject.data.markets) {{
                        const match = findMarketMatch(pm.question, limitlessProject.data.markets, matchedLimSlugs);
                        if (match) {{
                            const spread = (pm.polyPrice - match.yes_price) * 100;
                            const liq = match.liquidity || {{}};
                            const depth = liq.depth || 0;
                            const volume = match.volume || 0;
                            const ratio = depth > 0 ? volume / depth : (volume > 0 ? Infinity : 0);
                            matchedMarkets.push({{
                                question: pm.question,
                                polyPrice: pm.polyPrice,
                                limPrice: match.yes_price,
                                spread: spread,
                                absSpread: Math.abs(spread),
                                polyYesTokenId: pm.yesTokenId,
                                polyNoTokenId: pm.noTokenId,
                                limSlug: match.slug,
                                volume: volume,
                                ratio: ratio,
                                liquidity: {{
                                    type: liq.type || 'amm',
                                    depth: depth,
                                    bids: liq.bids || [],
                                    asks: liq.asks || [],
                                    isLow: depth < 500,
                                    isThin: ratio > 10
                                }}
                            }});
                            matchedLimSlugs.add(match.slug);
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

                // Find Limitless-only markets (not matched to any Polymarket market)
                if (limitlessProject && limitlessProject.data.markets) {{
                    // markets is an array, not an object
                    limitlessProject.data.markets.forEach(market => {{
                        const slug = market.slug || '';
                        if (!matchedLimSlugs.has(slug) && !market.closed) {{
                            const liq = market.liquidity || {{}};
                            limOnlyMarkets.push({{
                                question: market.title || market.question || 'Unknown',
                                limPrice: market.yes_price,
                                limSlug: slug,
                                volume: market.volume || 0,
                                liquidity: {{
                                    type: liq.type || 'amm',
                                    depth: liq.depth || 0,
                                    bids: liq.bids || [],
                                    asks: liq.asks || []
                                }}
                            }});
                        }}
                    }});
                }}

                // Sort matched markets by absolute spread (biggest first)
                matchedMarkets.sort((a, b) => b.absSpread - a.absSpread);

                const maxSpread = matchedMarkets.length > 0 ? Math.max(...matchedMarkets.map(m => m.absSpread)) : 0;
                
                // Look up leaderboard info
                const projectLower = polyProject.name.toLowerCase();
                const lbInfo = leaderboardData[projectLower] || null;

                // Look up Kaito status
                const kaitoPreTge = kaitoData.pre_tge || [];
                const kaitoPostTge = kaitoData.post_tge || [];
                const normalizedName = projectLower.replace(/[^a-z0-9]/g, '');
                const kaitoStatus = kaitoPreTge.some(k => k.toLowerCase().replace(/[^a-z0-9]/g, '') === normalizedName) 
                    ? 'pre-tge' 
                    : kaitoPostTge.some(k => k.toLowerCase().replace(/[^a-z0-9]/g, '') === normalizedName) 
                        ? 'post-tge' 
                        : 'none';

                // Look up Cookie campaign status
                const cookieSlugs = cookieData.slugs || [];
                const hasCookieCampaign = cookieSlugs.some(s => s.replace(/-/g, '') === normalizedName);

                // Look up Wallchain campaign status
                const wallchainSlugs = wallchainData.slugs || [];
                const hasWallchainCampaign = wallchainSlugs.some(s => s.replace(/-/g, '') === normalizedName);

                // Calculate total volumes
                const polyVolume = polyProject.events.reduce((sum, e) => sum + (e.volume || 0), 0);
                const limVolume = limitlessProject ? (limitlessProject.data.totalVolume || 0) : 0;

                projects.push({{
                    name: polyProject.name,
                    hasLimitless: !!limitlessProject,
                    matchedMarkets,
                    unmatchedMarkets,
                    limOnlyMarkets,
                    maxSpread,
                    polyVolume,
                    limVolume,
                    kaitoStatus,
                    hasCookieCampaign,
                    hasWallchainCampaign,
                    leaderboard: lbInfo ? {{
                        source: lbInfo.source,
                        sector: lbInfo.sector,
                        link: lbInfo.leaderboard_link,
                        priority: lbInfo.priority_note
                    }} : null
                }});
            }});
            
            // Sort: priority for gap closure
            // 1. Unmatched (NOT on Limitless) + has leaderboard (Kaito/Cookie) - PRIORITY
            // 2. Matched projects (on both platforms) - monitor spreads
            // 3. Everything else
            projects.sort((a, b) => {{
                // Check if has any leaderboard (Kaito pre-tge, Cookie, Wallchain, or CSV)
                const aHasLB = !!a.leaderboard || a.kaitoStatus === 'pre-tge' || a.hasCookieCampaign || a.hasWallchainCampaign;
                const bHasLB = !!b.leaderboard || b.kaitoStatus === 'pre-tge' || b.hasCookieCampaign || b.hasWallchainCampaign;
                const aOnLim = a.hasLimitless;
                const bOnLim = b.hasLimitless;
                const aMatched = a.matchedMarkets.length > 0;
                const bMatched = b.matchedMarkets.length > 0;

                // Priority 1: Unmatched + has leaderboard (need to create markets!)
                const aPriority1 = !aOnLim && aHasLB;
                const bPriority1 = !bOnLim && bHasLB;
                if (aPriority1 && !bPriority1) return -1;
                if (bPriority1 && !aPriority1) return 1;
                if (aPriority1 && bPriority1) return b.maxSpread - a.maxSpread;

                // Priority 2: Matched projects (on both platforms)
                if (aMatched && !bMatched) return -1;
                if (bMatched && !aMatched) return 1;
                if (aMatched && bMatched) return b.maxSpread - a.maxSpread;

                // Priority 3: Everything else - by spread
                return b.maxSpread - a.maxSpread;
            }});

            // Render
            let html = ``;

            projects.forEach((project, idx) => {{
                const projectId = project.name.replace(/[^a-zA-Z0-9]/g, '_');
                const hasMatches = project.matchedMarkets.length > 0;
                const isCollapsed = idx >= 3;
                const lb = project.leaderboard;
                const isPriority = lb && !project.hasLimitless;
                const isKaitoPreTge = project.kaitoStatus === 'pre-tge';
                
                // Kaito badge (with link if available from leaderboard)
                const kaitoLink = lb && lb.source.includes('Yaps') ? lb.link : `https://yaps.kaito.ai/${{project.name.toLowerCase().replace(/[^a-z0-9]/g, '')}}`;
                const kaitoBadge = project.kaitoStatus === 'pre-tge' 
                    ? `<a href="${{kaitoLink}}" target="_blank" style="text-decoration:none;margin-left:0.5rem;"><span style="background:#10b981;color:white;padding:0.15rem 0.4rem;border-radius:4px;font-size:0.65rem;font-weight:600;">🟢 Kaito Pre-TGE</span></a>`
                    : project.kaitoStatus === 'post-tge'
                        ? `<a href="${{kaitoLink}}" target="_blank" style="text-decoration:none;margin-left:0.5rem;"><span style="background:#6b7280;color:white;padding:0.15rem 0.4rem;border-radius:4px;font-size:0.65rem;font-weight:600;">Kaito Post-TGE</span></a>`
                        : '';
                
                // Cookie badge (with link)
                const cookieLink = lb && lb.source.includes('Cookie') ? lb.link : `https://www.cookie.fun/campaigns/${{project.name.toLowerCase().replace(/[^a-z0-9]/g, '-')}}`;
                const cookieBadge = project.hasCookieCampaign
                    ? `<a href="${{cookieLink}}" target="_blank" style="text-decoration:none;margin-left:0.5rem;"><span style="background:#f59e0b;color:white;padding:0.15rem 0.4rem;border-radius:4px;font-size:0.65rem;font-weight:600;">🍪 Cookie</span></a>`
                    : '';

                // Wallchain badge (with link)
                const wallchainBadge = project.hasWallchainCampaign
                    ? `<a href="https://wallchain.xyz" target="_blank" style="text-decoration:none;margin-left:0.5rem;"><span style="background:#FDC830;color:#1a1a1a;padding:0.15rem 0.4rem;border-radius:4px;font-size:0.65rem;font-weight:600;">🔗 Wallchain</span></a>`
                    : '';

                // Only show lbBadge if it's not already covered by Kaito or Cookie badges
                const lbSource = lb ? lb.source : '';
                const showLbBadge = lb && !lbSource.includes('Yaps') && !lbSource.includes('Cookie');
                const lbBadge = showLbBadge ? `<a href="${{lb.link}}" target="_blank" style="text-decoration:none;margin-left:0.5rem;"><span style="background:#8b5cf6;color:white;padding:0.15rem 0.4rem;border-radius:4px;font-size:0.65rem;font-weight:600;">${{lb.source}}</span></a>` : '';
                
                const isHighPriority = isKaitoPreTge && !project.hasLimitless;

                // Format volume helper
                const fmtVol = (v) => {{
                    if (v >= 1000000) return '$' + (v / 1000000).toFixed(1) + 'M';
                    if (v >= 1000) return '$' + (v / 1000).toFixed(0) + 'K';
                    return '$' + Math.round(v);
                }};

                html += `
                    <div class="event-card gap-project${{isCollapsed ? ' collapsed' : ''}}" id="gap-${{projectId}}">
                        <div class="event-header" onclick="toggleGapProject('${{projectId}}')">
                            <div style="display:flex;align-items:center;flex-wrap:wrap;">
                                <span class="toggle-icon">▼</span>
                                <span class="event-title" style="cursor:pointer;">${{project.name}}</span>
                                <span style="margin-left:0.5rem;font-size:0.75rem;">
                                    ${{project.matchedMarkets.length > 0 ? `<span style="color:var(--green);">${{project.matchedMarkets.length}} matched</span>` : ''}}
                                    ${{project.unmatchedMarkets.length > 0 ? `<span style="color:var(--text-secondary);margin-left:0.3rem;">· ${{project.unmatchedMarkets.length}} Poly-only</span>` : ''}}
                                    ${{project.limOnlyMarkets && project.limOnlyMarkets.length > 0 ? `<span style="color:#10b981;margin-left:0.3rem;">· ${{project.limOnlyMarkets.length}} Lim-only</span>` : ''}}
                                </span>
                            </div>
                            <div class="event-meta" style="display:flex;gap:1rem;align-items:center;">
                                <span style="font-size:0.7rem;color:var(--text-secondary);">
                                    <span style="color:#6366f1;">P: ${{fmtVol(project.polyVolume)}}</span>
                                    ${{project.limVolume > 0 ? `<span style="color:#10b981;margin-left:0.5rem;">L: ${{fmtVol(project.limVolume)}}</span>` : ''}}
                                </span>
                                ${{hasMatches ? `<span style="color:${{project.maxSpread > 5 ? 'var(--yellow)' : 'var(--text-secondary)'}};">
                                    Spread: ${{project.maxSpread.toFixed(1)}}pp
                                </span>` : ''}}
                            </div>
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
                                    <th style="text-align:right;width:90px;">Depth</th>
                                    <th style="text-align:right;width:70px;" title="Volume / Depth ratio - higher = thinner book">Vol/Dep</th>
                                </tr>
                            </thead>
                            <tbody>
                    `;

                    project.matchedMarkets.forEach((m, mIdx) => {{
                        const spreadColor = m.absSpread > 10 ? 'var(--red)' : (m.absSpread > 5 ? 'var(--yellow)' : 'var(--text-secondary)');
                        const spreadSign = m.spread > 0 ? '+' : '';
                        const liq = m.liquidity || {{}};
                        const depthStr = liq.depth >= 1000 ? '$' + (liq.depth / 1000).toFixed(1) + 'K' : '$' + Math.round(liq.depth);
                        const liqWarning = liq.isLow ? '<span title="Low liquidity" style="color:var(--red);margin-left:4px;">⚠️</span>' : '';
                        const liqColor = liq.isLow ? 'var(--red)' : 'var(--text-secondary)';
                        const liqType = liq.type === 'clob' ? 'CLOB' : 'AMM';
                        const rowId = `liq-row-${{project.name.replace(/[^a-zA-Z0-9]/g, '_')}}-${{mIdx}}`;

                        // Volume/Depth ratio coloring: red >10x, yellow >5x, green <2x
                        const ratio = m.ratio || 0;
                        const ratioStr = ratio === Infinity ? '∞' : ratio >= 100 ? Math.round(ratio) + 'x' : ratio.toFixed(1) + 'x';
                        const ratioColor = ratio > 10 ? 'var(--red)' : (ratio > 5 ? 'var(--yellow)' : (ratio < 2 ? 'var(--green)' : 'var(--text-secondary)'));

                        html += `
                            <tr style="cursor:pointer;" onclick="toggleDepthChart('${{rowId}}')"
                                data-poly-token="${{m.polyYesTokenId || ''}}"
                                data-lim-slug="${{m.limSlug || ''}}"
                                data-lim-bids='${{JSON.stringify(liq.bids || [])}}'
                                data-lim-asks='${{JSON.stringify(liq.asks || [])}}'
                                data-lim-type="${{liq.type || 'amm'}}"
                                data-ratio="${{ratio}}">
                                <td class="market-question">${{m.question}}</td>
                                <td style="text-align:right;font-weight:500;">${{(m.polyPrice * 100).toFixed(1)}}%</td>
                                <td style="text-align:right;font-weight:500;">${{(m.limPrice * 100).toFixed(1)}}%</td>
                                <td style="text-align:right;color:${{spreadColor}};font-weight:500;">${{spreadSign}}${{m.spread.toFixed(1)}}pp</td>
                                <td style="text-align:right;color:${{liqColor}};font-size:0.85rem;">
                                    ${{depthStr}}${{liqWarning}}
                                    <span style="font-size:0.7rem;color:var(--text-secondary);margin-left:2px;">(${{liqType}})</span>
                                </td>
                                <td style="text-align:right;color:${{ratioColor}};font-weight:600;font-size:0.85rem;">
                                    ${{ratioStr}}
                                </td>
                            </tr>
                            <tr id="${{rowId}}" style="display:none;background:var(--bg-secondary);">
                                <td colspan="6" style="padding:1rem;">
                                    <div id="${{rowId}}-chart" style="min-height:200px;display:flex;align-items:center;justify-content:center;">
                                        <span style="color:var(--text-secondary);">Loading depth chart...</span>
                                    </div>
                                </td>
                            </tr>
                        `;
                    }});

                    html += '</tbody></table>';
                }}

                // Polymarket-only markets
                if (project.unmatchedMarkets.length > 0) {{
                    html += `
                        <div style="padding:0.5rem 1rem;color:var(--text-secondary);font-size:0.8rem;border-top:1px solid var(--border);background:rgba(99,102,241,0.1);">
                            <strong>Polymarket Only</strong> (${{project.unmatchedMarkets.length}})
                        </div>
                        <table class="markets-table" style="margin:0 1rem 0.5rem;">
                            <tbody>
                    `;
                    project.unmatchedMarkets.forEach((m, mIdx) => {{
                        const rowId = `poly-only-${{project.name.replace(/[^a-zA-Z0-9]/g, '_')}}-${{mIdx}}`;
                        html += `
                            <tr style="cursor:pointer;" onclick="toggleDepthChart('${{rowId}}', 'poly-only')"
                                data-poly-token="${{m.yesTokenId || ''}}">
                                <td class="market-question" style="color:var(--text-secondary);">${{m.question}}</td>
                                <td style="text-align:right;font-weight:500;width:80px;">${{(m.polyPrice * 100).toFixed(1)}}%</td>
                                <td style="text-align:right;width:80px;color:var(--text-secondary);">—</td>
                            </tr>
                            <tr id="${{rowId}}" style="display:none;background:var(--bg-secondary);">
                                <td colspan="3" style="padding:1rem;">
                                    <div id="${{rowId}}-chart" style="min-height:200px;display:flex;align-items:center;justify-content:center;">
                                        <span style="color:var(--text-secondary);">Loading depth chart...</span>
                                    </div>
                                </td>
                            </tr>
                        `;
                    }});
                    html += '</tbody></table>';
                }}

                // Limitless-only markets
                if (project.limOnlyMarkets && project.limOnlyMarkets.length > 0) {{
                    html += `
                        <div style="padding:0.5rem 1rem;color:var(--text-secondary);font-size:0.8rem;border-top:1px solid var(--border);background:rgba(16,185,129,0.1);">
                            <strong>Limitless Only</strong> (${{project.limOnlyMarkets.length}})
                        </div>
                        <table class="markets-table" style="margin:0 1rem 0.5rem;">
                            <tbody>
                    `;
                    project.limOnlyMarkets.forEach((m, mIdx) => {{
                        const liq = m.liquidity || {{}};
                        const depth = liq.depth || 0;
                        const depthStr = depth >= 1000 ? '$' + (depth / 1000).toFixed(1) + 'K' : '$' + Math.round(depth);
                        const rowId = `lim-only-${{project.name.replace(/[^a-zA-Z0-9]/g, '_')}}-${{mIdx}}`;
                        html += `
                            <tr style="cursor:pointer;" onclick="toggleDepthChart('${{rowId}}', 'lim-only')"
                                data-lim-slug="${{m.limSlug || ''}}"
                                data-lim-bids='${{JSON.stringify(liq.bids || [])}}'
                                data-lim-asks='${{JSON.stringify(liq.asks || [])}}'
                                data-lim-type="${{liq.type || 'amm'}}">
                                <td class="market-question" style="color:var(--text-secondary);">${{m.question}}</td>
                                <td style="text-align:right;width:80px;color:var(--text-secondary);">—</td>
                                <td style="text-align:right;font-weight:500;width:80px;">${{(m.limPrice * 100).toFixed(1)}}%</td>
                                <td style="text-align:right;width:70px;font-size:0.85rem;">${{depthStr}}</td>
                            </tr>
                            <tr id="${{rowId}}" style="display:none;background:var(--bg-secondary);">
                                <td colspan="4" style="padding:1rem;">
                                    <div id="${{rowId}}-chart" style="min-height:200px;display:flex;align-items:center;justify-content:center;">
                                        <span style="color:var(--text-secondary);">Loading depth chart...</span>
                                    </div>
                                </td>
                            </tr>
                        `;
                    }});
                    html += '</tbody></table>';
                }}

                html += '</div></div>';
            }});

            container.innerHTML = html;
        }}

        function toggleGapProject(projectId) {{
            const card = document.getElementById('gap-' + projectId);
            if (card) card.classList.toggle('collapsed');
        }}

        // Cache for fetched Polymarket orderbooks
        const polyOrderbookCache = {{}};

        async function fetchPolyOrderbook(tokenId) {{
            if (!tokenId) return null;
            if (polyOrderbookCache[tokenId]) return polyOrderbookCache[tokenId];

            try {{
                const resp = await fetch(`https://clob.polymarket.com/book?token_id=${{tokenId}}`);
                if (!resp.ok) return null;
                const data = await resp.json();
                polyOrderbookCache[tokenId] = data;
                return data;
            }} catch (e) {{
                console.error('Failed to fetch Poly orderbook:', e);
                return null;
            }}
        }}

        function drawDepthChart(container, polyData, limData, limType, defaultChecked = {{ poly: true, lim: true }}) {{
            // Colors
            const polyColor = '#6366f1';  // Indigo for Polymarket
            const limColor = '#DCF58C';   // Lime for Limitless

            // Normalize orderbook data
            // Polymarket API returns size in contracts - convert to USD: price × contracts
            const polyBids = (polyData?.bids || []).map(b => {{
                const price = parseFloat(b.price);
                const contracts = parseFloat(b.size);
                return {{ price, size: price * contracts }};
            }});
            const polyAsks = (polyData?.asks || []).map(a => {{
                const price = parseFloat(a.price);
                const contracts = parseFloat(a.size);
                return {{ price, size: price * contracts }};
            }});
            const limBids = (limData?.bids || []).map(b => ({{ price: parseFloat(b.price), size: parseFloat(b.size) }}));
            const limAsks = (limData?.asks || []).map(a => ({{ price: parseFloat(a.price), size: parseFloat(a.size) }}));

            // Group by price level (round to 0.1% for grouping)
            function groupByPrice(orders) {{
                const grouped = {{}};
                orders.forEach(o => {{
                    const key = (Math.round(o.price * 1000) / 1000).toFixed(3);
                    if (!grouped[key]) grouped[key] = 0;
                    grouped[key] += o.size;
                }});
                return Object.entries(grouped).map(([price, size]) => ({{ price: parseFloat(price), size }}));
            }}

            const polyBidsGrouped = groupByPrice(polyBids);
            const polyAsksGrouped = groupByPrice(polyAsks);
            const limBidsGrouped = groupByPrice(limBids);
            const limAsksGrouped = groupByPrice(limAsks);

            // Create price level map with both platforms
            const bidLevels = {{}};
            const askLevels = {{}};

            polyBidsGrouped.forEach(b => {{
                const key = b.price.toFixed(3);
                if (!bidLevels[key]) bidLevels[key] = {{ price: b.price, poly: 0, lim: 0 }};
                bidLevels[key].poly += b.size;
            }});
            limBidsGrouped.forEach(b => {{
                const key = b.price.toFixed(3);
                if (!bidLevels[key]) bidLevels[key] = {{ price: b.price, poly: 0, lim: 0 }};
                bidLevels[key].lim += b.size;
            }});

            polyAsksGrouped.forEach(a => {{
                const key = a.price.toFixed(3);
                if (!askLevels[key]) askLevels[key] = {{ price: a.price, poly: 0, lim: 0 }};
                askLevels[key].poly += a.size;
            }});
            limAsksGrouped.forEach(a => {{
                const key = a.price.toFixed(3);
                if (!askLevels[key]) askLevels[key] = {{ price: a.price, poly: 0, lim: 0 }};
                askLevels[key].lim += a.size;
            }});

            // Convert to sorted arrays - show full orderbook
            // Bids: sort descending (highest first)
            // Asks: sort ascending (lowest first), then reverse for display (highest ask on top)
            // Filter out empty levels (no liquidity from either platform)
            let bids = Object.values(bidLevels)
                .filter(l => l.poly > 0 || l.lim > 0)
                .sort((a, b) => b.price - a.price);
            let asks = Object.values(askLevels)
                .filter(l => l.poly > 0 || l.lim > 0)
                .sort((a, b) => a.price - b.price).reverse();

            if (bids.length === 0 && asks.length === 0) {{
                container.innerHTML = '<span style="color:var(--text-secondary);">No orderbook data available</span>';
                return;
            }}

            // Find max size for bar scaling (use max of individual platform, not combined)
            const allSizes = [
                ...bids.map(b => b.poly), ...bids.map(b => b.lim),
                ...asks.map(a => a.poly), ...asks.map(a => a.lim)
            ];
            const maxSize = Math.max(...allSizes) * 1.1 || 1000;

            // Calculate spread - best bid is first in bids, best ask is last in asks (after reverse)
            const bestBid = bids.length > 0 ? bids[0].price : 0;
            const bestAsk = asks.length > 0 ? asks[asks.length - 1].price : 1;
            const spread = ((bestAsk - bestBid) * 100).toFixed(1);
            const midpoint = ((bestBid + bestAsk) / 2 * 100).toFixed(1);

            // Generate unique ID for this orderbook instance
            const obId = 'ob-' + Math.random().toString(36).substr(2, 9);

            // Build single-column orderbook
            let html = `
                <div style="max-width:400px;margin:0 auto;">
                    <div style="display:flex;gap:1rem;font-size:0.75rem;margin-bottom:0.5rem;justify-content:center;align-items:center;">
                        <label style="display:flex;align-items:center;gap:4px;cursor:pointer;">
                            <input type="checkbox" ${{defaultChecked.poly ? 'checked' : ''}} onchange="toggleOBPlatform('${{obId}}', 'poly', this.checked)" style="accent-color:${{polyColor}};">
                            <span style="color:${{polyColor}};">■ Polymarket</span>
                        </label>
                        <label style="display:flex;align-items:center;gap:4px;cursor:pointer;">
                            <input type="checkbox" ${{defaultChecked.lim ? 'checked' : ''}} onchange="toggleOBPlatform('${{obId}}', 'lim', this.checked)" style="accent-color:${{limColor}};">
                            <span style="color:${{limColor}};">■ Limitless</span>
                        </label>
                    </div>
                    <div id="${{obId}}" style="display:grid;grid-template-columns:55px 1fr 60px;gap:4px;font-size:0.65rem;color:var(--text-secondary);padding:4px 8px;border-bottom:1px solid var(--border);">
                        <span>Price</span><span style="text-align:center;">Depth</span><span style="text-align:right;">Total</span>
                    </div>
            `;

            // Calculate cumulative totals for asks (from best ask near spread to worst at top)
            // asks array is reversed: index 0 = highest price (worst), last index = lowest price (best, near spread)
            let askCumulative = [];
            let askRunning = 0;
            for (let i = asks.length - 1; i >= 0; i--) {{
                askRunning += asks[i].poly + asks[i].lim;
                askCumulative[i] = askRunning;
            }}

            // Render asks (highest price at top, lowest at bottom near spread)
            asks.forEach((level, idx) => {{
                const cumTotal = askCumulative[idx] || 0;
                const polyWidth = (level.poly / maxSize) * 100;
                const limWidth = (level.lim / maxSize) * 100;
                html += `
                    <div class="${{obId}}-row ${{obId}}-ask" data-poly="${{level.poly}}" data-lim="${{level.lim}}" data-idx="${{idx}}" style="display:grid;grid-template-columns:55px 1fr 60px;gap:4px;align-items:center;padding:2px 8px;">
                        <span style="color:var(--red);font-weight:500;font-size:0.8rem;">${{(level.price * 100).toFixed(1)}}¢</span>
                        <div style="position:relative;height:16px;background:var(--bg-primary);border-radius:2px;overflow:hidden;">
                            <div class="${{obId}}-poly" style="position:absolute;left:0;top:0;height:100%;width:${{polyWidth}}%;background:${{polyColor}};opacity:${{defaultChecked.poly ? '0.6' : '0'}};transition:opacity 0.15s;"></div>
                            <div class="${{obId}}-lim" style="position:absolute;left:0;top:0;height:100%;width:${{limWidth}}%;background:${{limColor}};opacity:${{defaultChecked.lim ? '0.6' : '0'}};transition:opacity 0.15s;"></div>
                        </div>
                        <span class="${{obId}}-total" style="text-align:right;color:var(--text-secondary);font-size:0.75rem;">$${{cumTotal.toFixed(0)}}</span>
                    </div>
                `;
            }});

            // Spread divider
            html += `
                <div style="display:grid;grid-template-columns:55px 1fr 60px;gap:4px;padding:6px 8px;background:var(--bg-primary);margin:4px 0;border-radius:4px;">
                    <span></span>
                    <span style="text-align:center;font-size:0.75rem;color:var(--text-primary);">
                        Spread: <strong>${{spread}}¢</strong>
                    </span>
                    <span></span>
                </div>
            `;

            // Calculate cumulative totals for bids (from best bid near spread to worst at bottom)
            // bids array: index 0 = highest price (best, near spread), last index = lowest price (worst)
            let bidCumulative = [];
            let bidRunning = 0;
            for (let i = 0; i < bids.length; i++) {{
                bidRunning += bids[i].poly + bids[i].lim;
                bidCumulative[i] = bidRunning;
            }}

            // Render bids (highest price at top near spread, lowest at bottom)
            bids.forEach((level, idx) => {{
                const cumTotal = bidCumulative[idx] || 0;
                const polyWidth = (level.poly / maxSize) * 100;
                const limWidth = (level.lim / maxSize) * 100;
                html += `
                    <div class="${{obId}}-row ${{obId}}-bid" data-poly="${{level.poly}}" data-lim="${{level.lim}}" data-idx="${{idx}}" style="display:grid;grid-template-columns:55px 1fr 60px;gap:4px;align-items:center;padding:2px 8px;">
                        <span style="color:var(--green);font-weight:500;font-size:0.8rem;">${{(level.price * 100).toFixed(1)}}¢</span>
                        <div style="position:relative;height:16px;background:var(--bg-primary);border-radius:2px;overflow:hidden;">
                            <div class="${{obId}}-poly" style="position:absolute;left:0;top:0;height:100%;width:${{polyWidth}}%;background:${{polyColor}};opacity:${{defaultChecked.poly ? '0.6' : '0'}};transition:opacity 0.15s;"></div>
                            <div class="${{obId}}-lim" style="position:absolute;left:0;top:0;height:100%;width:${{limWidth}}%;background:${{limColor}};opacity:${{defaultChecked.lim ? '0.6' : '0'}};transition:opacity 0.15s;"></div>
                        </div>
                        <span class="${{obId}}-total" style="text-align:right;color:var(--text-secondary);font-size:0.75rem;">$${{cumTotal.toFixed(0)}}</span>
                    </div>
                `;
            }});

            html += `</div>`;

            container.innerHTML = html;
        }}

        // Track visibility state per orderbook
        const obVisibility = {{}};

        function toggleOBPlatform(obId, platform, visible) {{
            // Initialize state if needed
            if (!obVisibility[obId]) obVisibility[obId] = {{ poly: true, lim: true }};
            obVisibility[obId][platform] = visible;

            // Toggle bar visibility
            const bars = document.querySelectorAll(`.${{obId}}-${{platform}}`);
            bars.forEach(bar => {{
                bar.style.opacity = visible ? '0.6' : '0';
            }});

            const state = obVisibility[obId];

            // Helper to get visible total for a row
            const getVisibleTotal = (row) => {{
                const polyVal = parseFloat(row.dataset.poly) || 0;
                const limVal = parseFloat(row.dataset.lim) || 0;
                let total = 0;
                if (state.poly) total += polyVal;
                if (state.lim) total += limVal;
                return total;
            }};

            // Update asks: hide empty rows, recalculate cumulative for visible rows
            const askRows = Array.from(document.querySelectorAll(`.${{obId}}-ask`));
            let askRunning = 0;
            // Process from last (best ask) to first (worst ask)
            for (let i = askRows.length - 1; i >= 0; i--) {{
                const row = askRows[i];
                const levelTotal = getVisibleTotal(row);
                // Hide row if no visible liquidity
                row.style.display = levelTotal > 0 ? 'grid' : 'none';
                if (levelTotal > 0) {{
                    askRunning += levelTotal;
                    const totalSpan = row.querySelector(`.${{obId}}-total`);
                    if (totalSpan) totalSpan.textContent = '$' + askRunning.toFixed(0);
                }}
            }}

            // Update bids: hide empty rows, recalculate cumulative for visible rows
            const bidRows = Array.from(document.querySelectorAll(`.${{obId}}-bid`));
            let bidRunning = 0;
            // Process from first (best bid) to last (worst bid)
            for (let i = 0; i < bidRows.length; i++) {{
                const row = bidRows[i];
                const levelTotal = getVisibleTotal(row);
                // Hide row if no visible liquidity
                row.style.display = levelTotal > 0 ? 'grid' : 'none';
                if (levelTotal > 0) {{
                    bidRunning += levelTotal;
                    const totalSpan = row.querySelector(`.${{obId}}-total`);
                    if (totalSpan) totalSpan.textContent = '$' + bidRunning.toFixed(0);
                }}
            }}
        }}

        async function toggleDepthChart(rowId, marketType = 'matched') {{
            const row = document.getElementById(rowId);
            if (!row) return;

            const isHidden = row.style.display === 'none';
            row.style.display = isHidden ? 'table-row' : 'none';

            if (!isHidden) return; // Just hiding, no need to fetch

            const chartContainer = document.getElementById(rowId + '-chart');
            if (!chartContainer) return;

            // Get data from the clickable row (previous sibling)
            const clickRow = row.previousElementSibling;
            if (!clickRow) return;

            const polyTokenId = clickRow.dataset.polyToken;
            const limSlug = clickRow.dataset.limSlug;
            const limType = clickRow.dataset.limType;

            // Parse embedded Limitless data
            let limBids = [], limAsks = [];
            try {{
                limBids = JSON.parse(clickRow.dataset.limBids || '[]');
                limAsks = JSON.parse(clickRow.dataset.limAsks || '[]');
            }} catch (e) {{}}

            // Fetch Polymarket orderbook
            chartContainer.innerHTML = '<span style="color:var(--text-secondary);">Fetching orderbook...</span>';

            const polyData = await fetchPolyOrderbook(polyTokenId);
            const limData = {{ bids: limBids, asks: limAsks }};

            // Determine default checked state based on market type
            const defaultChecked = {{
                poly: marketType !== 'lim-only',  // unchecked for Limitless-only
                lim: marketType !== 'poly-only'   // unchecked for Polymarket-only
            }};

            drawDepthChart(chartContainer, polyData, limData, limType, defaultChecked);
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

        // ===== LAUNCHED PROJECTS =====

        // Generate SVG cumulative volume chart
        function renderVolumeChart(history, preTgeVolume, chartId) {{
            if (!history || history.length === 0) {{
                return `<div style="text-align:center;color:var(--text-secondary);padding:1rem;font-size:0.8rem;">No volume history yet</div>`;
            }}

            const width = 400;
            const height = 120;
            const padding = {{ top: 20, right: 50, bottom: 25, left: 10 }};
            const chartWidth = width - padding.left - padding.right;
            const chartHeight = height - padding.top - padding.bottom;

            // Calculate cumulative volumes
            let cumulative = 0;
            const points = history.map((h, i) => {{
                cumulative += h.total_volume;
                return {{ day: i + 1, volume: cumulative, date: h.date }};
            }});

            // Add day 0 with 0 volume
            points.unshift({{ day: 0, volume: 0, date: 'TGE' }});

            const maxVolume = Math.max(cumulative, preTgeVolume);
            const maxDay = points.length - 1;

            // Scale functions
            const xScale = (day) => padding.left + (day / Math.max(maxDay, 1)) * chartWidth;
            const yScale = (vol) => padding.top + chartHeight - (vol / maxVolume) * chartHeight;

            // Build path
            const pathPoints = points.map(p => `${{xScale(p.day).toFixed(1)}},${{yScale(p.volume).toFixed(1)}}`);
            const linePath = 'M ' + pathPoints.join(' L ');

            // Area path (for fill)
            const areaPath = linePath + ` L ${{xScale(maxDay).toFixed(1)}},${{yScale(0).toFixed(1)}} L ${{xScale(0).toFixed(1)}},${{yScale(0).toFixed(1)}} Z`;

            // Pre-TGE reference line
            const preTgeY = yScale(preTgeVolume);

            return `
                <svg width="100%" viewBox="0 0 ${{width}} ${{height}}" style="max-width:${{width}}px;">
                    <!-- Grid lines -->
                    <line x1="${{padding.left}}" y1="${{preTgeY}}" x2="${{width - padding.right}}" y2="${{preTgeY}}"
                          stroke="var(--accent)" stroke-width="1" stroke-dasharray="4,4" opacity="0.5"/>

                    <!-- Pre-TGE label -->
                    <text x="${{width - padding.right + 5}}" y="${{preTgeY + 4}}"
                          fill="var(--accent)" font-size="10">Pre-TGE</text>

                    <!-- Area fill -->
                    <path d="${{areaPath}}" fill="url(#gradient-${{chartId}})" opacity="0.3"/>

                    <!-- Line -->
                    <path d="${{linePath}}" fill="none" stroke="var(--green)" stroke-width="2"/>

                    <!-- Points -->
                    ${{points.map(p => `
                        <circle cx="${{xScale(p.day)}}" cy="${{yScale(p.volume)}}" r="3" fill="var(--green)"/>
                    `).join('')}}

                    <!-- X-axis labels -->
                    <text x="${{padding.left}}" y="${{height - 5}}" fill="var(--text-secondary)" font-size="9">Day 0</text>
                    <text x="${{width - padding.right}}" y="${{height - 5}}" fill="var(--text-secondary)" font-size="9" text-anchor="end">Day ${{maxDay}}</text>

                    <!-- Current value label -->
                    <text x="${{xScale(maxDay)}}" y="${{yScale(cumulative) - 8}}"
                          fill="var(--green)" font-size="10" text-anchor="middle" font-weight="600">
                        ${{formatVolume(cumulative)}}
                    </text>

                    <!-- Gradient definition -->
                    <defs>
                        <linearGradient id="gradient-${{chartId}}" x1="0%" y1="0%" x2="0%" y2="100%">
                            <stop offset="0%" stop-color="var(--green)" stop-opacity="0.4"/>
                            <stop offset="100%" stop-color="var(--green)" stop-opacity="0"/>
                        </linearGradient>
                    </defs>
                </svg>
            `;
        }}

        function renderLaunchedProjects() {{
            const container = document.getElementById('launched-view');

            if (!launchedProjectsData || launchedProjectsData.length === 0) {{
                container.innerHTML = `
                    <div style="text-align:center;padding:2rem;">
                        <p style="color:var(--text-secondary);margin-bottom:1rem;">No launched projects tracked yet</p>
                        <p style="font-size:0.85rem;color:var(--text-secondary);">
                            Use <code style="background:var(--bg-primary);padding:0.2rem 0.4rem;border-radius:4px;">LaunchedProjectStore</code> to add projects after TGE
                        </p>
                        <div style="margin-top:1.5rem;padding:1rem;background:var(--bg-secondary);border-radius:8px;text-align:left;font-size:0.8rem;">
                            <p style="color:var(--accent);margin-bottom:0.5rem;font-weight:600;">Quick Start:</p>
                            <code style="color:var(--text-secondary);white-space:pre-wrap;">from src.polymarket.data import LaunchedProjectStore

store = LaunchedProjectStore()
store.add_project(
    name="Zama",
    ticker="ZAMA",
    tge_date="2026-01-15",
    pre_tge_poly_volume=500000,
    pre_tge_lim_volume=50000
)</code>
                        </div>
                    </div>
                `;
                return;
            }}

            // Calculate totals
            const totalPreTGE = launchedProjectsData.reduce((sum, p) => sum + p.pre_tge_volume, 0);
            const totalPostTGE = launchedProjectsData.reduce((sum, p) => sum + p.post_tge_volume, 0);

            // Filter projects with volume history for the chart section
            const projectsWithHistory = launchedProjectsData.filter(p => p.volume_history && p.volume_history.length > 0);

            let html = `
                <div style="display:grid;grid-template-columns:repeat(4, 1fr);gap:1rem;margin-bottom:1.5rem;">
                    <div style="background:var(--bg-secondary);padding:1rem;border-radius:8px;text-align:center;">
                        <div style="font-size:1.5rem;font-weight:700;">${{launchedProjectsData.length}}</div>
                        <div style="font-size:0.75rem;color:var(--text-secondary);">Projects Launched</div>
                    </div>
                    <div style="background:var(--bg-secondary);padding:1rem;border-radius:8px;text-align:center;">
                        <div style="font-size:1.5rem;font-weight:700;">${{formatVolume(totalPreTGE)}}</div>
                        <div style="font-size:0.75rem;color:var(--text-secondary);">Pre-TGE Volume</div>
                    </div>
                    <div style="background:var(--bg-secondary);padding:1rem;border-radius:8px;text-align:center;">
                        <div style="font-size:1.5rem;font-weight:700;">${{formatVolume(totalPostTGE)}}</div>
                        <div style="font-size:0.75rem;color:var(--text-secondary);">Post-TGE Volume</div>
                    </div>
                    <div style="background:var(--bg-secondary);padding:1rem;border-radius:8px;text-align:center;">
                        <div style="font-size:1.5rem;font-weight:700;color:${{totalPostTGE >= totalPreTGE ? 'var(--green)' : 'var(--red)'}};">
                            ${{totalPreTGE > 0 ? (totalPostTGE / totalPreTGE * 100).toFixed(0) : 0}}%
                        </div>
                        <div style="font-size:0.75rem;color:var(--text-secondary);">Volume Ratio</div>
                    </div>
                </div>
            `;

            // Render each launched project
            launchedProjectsData.forEach((project, idx) => {{
                const volumeRatio = project.volume_ratio * 100;
                const ratioColor = volumeRatio >= 100 ? 'var(--green)' : (volumeRatio >= 50 ? 'var(--yellow)' : 'var(--red)');
                const trendColor = project.trend_7d >= 0 ? 'var(--green)' : 'var(--red)';
                const hasHistory = project.volume_history && project.volume_history.length > 0;
                const chartId = 'chart-' + idx;

                html += `
                    <div class="event-card" style="margin-bottom:1rem;">
                        <div class="event-header">
                            <div style="display:flex;align-items:center;gap:0.75rem;">
                                <span class="event-title">${{project.name}}</span>
                                <span style="background:var(--accent);color:white;padding:0.15rem 0.5rem;border-radius:4px;font-size:0.7rem;font-weight:600;">
                                    $` + project.ticker + `
                                </span>
                                <span style="font-size:0.75rem;color:var(--text-secondary);">
                                    TGE: ${{project.tge_date}}
                                </span>
                            </div>
                            <div class="event-meta">
                                <span style="color:${{ratioColor}};font-weight:600;">
                                    ${{volumeRatio.toFixed(0)}}% of pre-TGE
                                </span>
                                ${{project.trend_7d !== 0 ? `
                                    <span style="color:${{trendColor}};font-size:0.85rem;">
                                        ${{project.trend_7d >= 0 ? '↑' : '↓'}} ${{Math.abs(project.trend_7d).toFixed(1)}}% 7d
                                    </span>
                                ` : ''}}
                            </div>
                        </div>
                        <div class="markets-container" style="padding:1rem;">
                            <div style="display:grid;grid-template-columns:${{hasHistory ? '1fr 1fr' : '1fr'}};gap:1rem;">
                                <div style="display:grid;grid-template-columns:repeat(4, 1fr);gap:0.5rem;">
                                    <div style="background:var(--bg-secondary);padding:0.75rem;border-radius:8px;text-align:center;">
                                        <div style="font-size:1.1rem;font-weight:600;">${{formatVolume(project.fdv_market_volume || 0)}}</div>
                                        <div style="font-size:0.65rem;color:var(--text-secondary);">FDV Market</div>
                                    </div>
                                    <div style="background:var(--bg-secondary);padding:0.75rem;border-radius:8px;text-align:center;">
                                        <div style="font-size:1.1rem;font-weight:600;">${{formatVolume(project.launch_market_volume || 0)}}</div>
                                        <div style="font-size:0.65rem;color:var(--text-secondary);">Launch Date</div>
                                    </div>
                                    <div style="background:var(--bg-secondary);padding:0.75rem;border-radius:8px;text-align:center;">
                                        <div style="font-size:1.1rem;font-weight:600;">${{formatVolume(project.post_tge_volume)}}</div>
                                        <div style="font-size:0.65rem;color:var(--text-secondary);">Post-TGE</div>
                                    </div>
                                    <div style="background:var(--bg-secondary);padding:0.75rem;border-radius:8px;text-align:center;">
                                        <div style="font-size:1.1rem;font-weight:600;">${{project.days_since_tge}}</div>
                                        <div style="font-size:0.65rem;color:var(--text-secondary);">Days</div>
                                    </div>
                                </div>
                                ${{hasHistory ? `
                                    <div style="background:var(--bg-secondary);padding:0.5rem;border-radius:8px;">
                                        <div style="font-size:0.7rem;color:var(--text-secondary);margin-bottom:0.25rem;text-align:center;">Cumulative Post-TGE Volume</div>
                                        ${{renderVolumeChart(project.volume_history, project.pre_tge_volume, chartId)}}
                                    </div>
                                ` : `
                                    <div style="display:none;"></div>
                                `}}
                            </div>
                        </div>
                    </div>
                `;
            }});

            container.innerHTML = html;
        }}

        // ===== FDV PREDICTIONS (Table UI) =====
        let fdvExpandedRows = {{}};

        function toggleFdvRow(projectId) {{
            fdvExpandedRows[projectId] = !fdvExpandedRows[projectId];
            const expandedDiv = document.getElementById('fdv-expanded-' + projectId);
            const btn = document.getElementById('fdv-btn-' + projectId);
            if (fdvExpandedRows[projectId]) {{
                expandedDiv.classList.add('show');
                btn.classList.add('expanded');
                btn.textContent = '−';
            }} else {{
                expandedDiv.classList.remove('show');
                btn.classList.remove('expanded');
                btn.textContent = '+';
            }}
        }}

        function calculatePredictedFdv(thresholds) {{
            // Sort thresholds by value (ascending)
            const sorted = [...thresholds].sort((a, b) => {{
                const valA = parseThresholdValue(a.label);
                const valB = parseThresholdValue(b.label);
                return valA - valB;
            }});

            // Get current prices for each threshold
            const withPrices = sorted.map(t => {{
                const currentPrice = t.history && t.history.length > 0
                    ? t.history[t.history.length - 1].price
                    : 0;
                return {{ ...t, currentPrice, value: parseThresholdValue(t.label) }};
            }});

            // Find lower bound: highest threshold with >50% probability
            // Find upper bound: lowest threshold with <50% probability
            let lowerBound = null;
            let upperBound = null;

            for (const t of withPrices) {{
                if (t.currentPrice >= 0.5) {{
                    lowerBound = t;
                }} else if (t.currentPrice < 0.5 && upperBound === null) {{
                    upperBound = t;
                }}
            }}

            // Format the range
            if (lowerBound && upperBound) {{
                return `${{lowerBound.label.replace('>', '')}} - ${{upperBound.label.replace('>', '')}}`;
            }} else if (lowerBound) {{
                return `>${{lowerBound.label.replace('>', '')}}`;
            }} else if (upperBound) {{
                return `<${{upperBound.label.replace('>', '')}}`;
            }}
            return 'Unknown';
        }}

        function parseThresholdValue(label) {{
            // Parse "$500M" or "$1B" into numeric value
            const match = label.match(/\\$?([\\d.]+)\\s*(M|B|K)?/i);
            if (!match) return 0;
            let value = parseFloat(match[1]);
            const unit = (match[2] || '').toUpperCase();
            if (unit === 'B') value *= 1000;
            else if (unit === 'K') value /= 1000;
            return value; // Return in millions
        }}

        function renderFdvPredictions() {{
            const container = document.getElementById('fdv-view');

            // Color palette for chart lines
            const colors = ['#22c55e', '#f59e0b', '#8b5cf6', '#06b6d4', '#ef4444', '#ec4899', '#14b8a6', '#f97316'];

            // Process project data
            const projects = Object.entries(fdvHistoryData)
                .filter(([_, data]) => data.thresholds && data.thresholds.length > 0)
                .map(([name, data]) => {{
                    const totalVolume = data.thresholds.reduce((sum, t) => sum + (t.volume || 0), 0);

                    // Calculate 24h change (max change across thresholds)
                    let maxChange = 0;
                    let resolvedCount = 0;
                    data.thresholds.forEach(t => {{
                        if (t.history && t.history.length >= 2) {{
                            const sorted = [...t.history].sort((a, b) => a.date.localeCompare(b.date));
                            const latest = sorted[sorted.length - 1].price;
                            const previous = sorted[sorted.length - 2].price;
                            const change = latest - previous;
                            if (Math.abs(change) > Math.abs(maxChange)) maxChange = change;

                            if (latest >= 0.99 || latest <= 0.01) resolvedCount++;
                        }}
                    }});

                    const isResolved = resolvedCount >= data.thresholds.length * 0.8;
                    const predictedFdv = calculatePredictedFdv(data.thresholds);

                    return [name, {{ ...data, totalVolume, maxChange, isResolved, predictedFdv }}];
                }})
                .filter(([_, data]) => !data.isResolved)
                .filter(([name, _]) => !fdvFilterProject || name.toLowerCase().includes(fdvFilterProject.toLowerCase()))
                .sort((a, b) => b[1].totalVolume - a[1].totalVolume);

            if (projects.length === 0) {{
                const noMatchMsg = fdvFilterProject
                    ? `<p style="text-align:center;color:var(--text-secondary);padding:2rem;">No FDV data found for "${{fdvFilterProject}}". <a href="#" onclick="clearFdvFilter();return false;" style="color:var(--accent);">Show all projects</a></p>`
                    : '<p style="text-align:center;color:var(--text-secondary);padding:2rem;">No FDV prediction markets found.</p>';
                container.innerHTML = noMatchMsg;
                return;
            }}

            let html = '';

            // Filter header if filtering
            if (fdvFilterProject) {{
                html += `
                    <div style="background:var(--accent);color:white;padding:0.75rem 1rem;border-radius:8px;margin-bottom:1rem;display:flex;align-items:center;justify-content:space-between;">
                        <span>📈 Showing FDV predictions for <strong>${{fdvFilterProject}}</strong></span>
                        <button onclick="clearFdvFilter()" style="background:rgba(255,255,255,0.2);border:none;color:white;padding:0.35rem 0.75rem;border-radius:6px;cursor:pointer;font-size:0.8rem;">← Show all projects</button>
                    </div>
                `;
            }}

            // Table header
            html += `
                <div class="fdv-table-header">
                    <div>Project</div>
                    <div>Predicted FDV</div>
                    <div>24h</div>
                    <div>Volume</div>
                    <div></div>
                </div>
            `;

            // Table rows
            projects.forEach(([name, data], rowIdx) => {{
                const thresholds = data.thresholds;
                const projectId = name.replace(/[^a-zA-Z0-9]/g, '');
                const isExpanded = fdvExpandedRows[projectId] || false;

                // 24h change display
                const changeVal = data.maxChange * 100;
                const changeClass = changeVal > 0.5 ? 'positive' : changeVal < -0.5 ? 'negative' : 'neutral';
                const changeStr = changeVal > 0 ? `+${{changeVal.toFixed(1)}}%` : changeVal < 0 ? `${{changeVal.toFixed(1)}}%` : '0%';

                // Build expanded content (chart)
                let chartHtml = '';
                const allDates = [...new Set(thresholds.flatMap(t => t.history.map(h => h.date)))].sort();
                const numDates = allDates.length;

                if (numDates >= 2) {{
                    const width = 600;
                    const height = 180;
                    const padding = {{ left: 45, right: 20, top: 20, bottom: 30 }};
                    const chartW = width - padding.left - padding.right;
                    const chartH = height - padding.top - padding.bottom;

                    let pathsSvg = '';

                    thresholds.forEach((th, idx) => {{
                        const color = colors[idx % colors.length];
                        const history = [...th.history].sort((a, b) => a.date.localeCompare(b.date));
                        if (history.length < 2) return;

                        const points = history.map(h => {{
                            const dateIdx = allDates.indexOf(h.date);
                            const x = padding.left + (chartW * dateIdx / (numDates - 1));
                            const y = padding.top + chartH * (1 - h.price);
                            return {{ x, y }};
                        }});

                        let pathD = `M ${{points[0].x.toFixed(1)}} ${{points[0].y.toFixed(1)}}`;
                        for (let i = 1; i < points.length; i++) {{
                            const prev = points[i - 1];
                            const curr = points[i];
                            const tension = 0.3;
                            const dx = (curr.x - prev.x) * tension;
                            pathD += ` C ${{(prev.x + dx).toFixed(1)}} ${{prev.y.toFixed(1)}}, ${{(curr.x - dx).toFixed(1)}} ${{curr.y.toFixed(1)}}, ${{curr.x.toFixed(1)}} ${{curr.y.toFixed(1)}}`;
                        }}

                        const lastPoint = points[points.length - 1];
                        const fillPath = pathD + ` L ${{lastPoint.x}} ${{padding.top + chartH}} L ${{points[0].x}} ${{padding.top + chartH}} Z`;

                        pathsSvg += `
                            <defs>
                                <linearGradient id="fdvgrad${{rowIdx}}_${{idx}}" x1="0%" y1="0%" x2="0%" y2="100%">
                                    <stop offset="0%" style="stop-color:${{color}};stop-opacity:0.15"/>
                                    <stop offset="100%" style="stop-color:${{color}};stop-opacity:0"/>
                                </linearGradient>
                            </defs>
                            <path d="${{fillPath}}" fill="url(#fdvgrad${{rowIdx}}_${{idx}})"/>
                            <path d="${{pathD}}" fill="none" stroke="${{color}}" stroke-width="2" stroke-linecap="round"/>
                            <circle cx="${{lastPoint.x}}" cy="${{lastPoint.y}}" r="3" fill="${{color}}"/>
                        `;
                    }});

                    const dateLabels = [0, Math.floor(numDates / 2), numDates - 1]
                        .map(i => {{
                            const date = allDates[i];
                            const x = padding.left + (chartW * i / (numDates - 1));
                            const label = date.slice(5);
                            return `<text x="${{x}}" y="${{height - 8}}" text-anchor="middle" fill="var(--text-secondary)" font-size="10">${{label}}</text>`;
                        }}).join('');

                    chartHtml = `
                        <svg width="${{width}}" height="${{height}}" style="display:block;max-width:100%;">
                            <line x1="${{padding.left}}" y1="${{padding.top}}" x2="${{width - padding.right}}" y2="${{padding.top}}" stroke="rgba(255,255,255,0.06)"/>
                            <line x1="${{padding.left}}" y1="${{padding.top + chartH * 0.5}}" x2="${{width - padding.right}}" y2="${{padding.top + chartH * 0.5}}" stroke="rgba(255,255,255,0.08)" stroke-dasharray="4"/>
                            <line x1="${{padding.left}}" y1="${{padding.top + chartH}}" x2="${{width - padding.right}}" y2="${{padding.top + chartH}}" stroke="rgba(255,255,255,0.06)"/>
                            <text x="${{padding.left - 8}}" y="${{padding.top + 4}}" text-anchor="end" fill="var(--text-secondary)" font-size="9">100%</text>
                            <text x="${{padding.left - 8}}" y="${{padding.top + chartH * 0.5 + 4}}" text-anchor="end" fill="var(--text-secondary)" font-size="9">50%</text>
                            <text x="${{padding.left - 8}}" y="${{padding.top + chartH + 4}}" text-anchor="end" fill="var(--text-secondary)" font-size="9">0</text>
                            ${{pathsSvg}}
                            ${{dateLabels}}
                        </svg>
                    `;
                }}

                // Threshold pills
                const pillsHtml = thresholds.map((th, idx) => {{
                    const color = colors[idx % colors.length];
                    const currentPrice = th.history && th.history.length > 0 ? th.history[th.history.length - 1].price : 0;
                    const pct = (currentPrice * 100).toFixed(0);
                    return `
                        <div class="fdv-threshold-pill">
                            <div class="fdv-pill-dot" style="background:${{color}};"></div>
                            <span class="fdv-pill-label">${{th.label.replace('>', '')}}</span>
                            <span class="fdv-pill-prob" style="color:${{color}};">${{pct}}%</span>
                        </div>
                    `;
                }}).join('');

                html += `
                    <div class="fdv-table-row">
                        <div class="fdv-row-main" onclick="toggleFdvRow('${{projectId}}')">
                            <div class="fdv-project-name">${{name}}</div>
                            <div class="fdv-predicted-range">${{data.predictedFdv}}</div>
                            <div class="fdv-change ${{changeClass}}">${{changeStr}}</div>
                            <div class="fdv-volume">${{formatVolume(data.totalVolume)}}</div>
                            <div id="fdv-btn-${{projectId}}" class="fdv-expand-btn ${{isExpanded ? 'expanded' : ''}}">${{isExpanded ? '−' : '+'}}</div>
                        </div>
                        <div id="fdv-expanded-${{projectId}}" class="fdv-row-expanded ${{isExpanded ? 'show' : ''}}">
                            ${{chartHtml}}
                            <div class="fdv-threshold-pills">
                                ${{pillsHtml}}
                            </div>
                        </div>
                    </div>
                `;
            }});

            container.innerHTML = html || '<p style="text-align:center;color:var(--text-secondary);padding:2rem;">No FDV data with sufficient history.</p>';
        }}

        // Initial render - Timeline is default tab
        renderTimeline();
        timelineRendered = true;
    </script>
</body>
</html>'''
    
    final_output_path = output_path or Config.DASHBOARD_OUTPUT
    with open(final_output_path, 'w') as f:
        f.write(html)

    mode_str = " (public)" if public_mode else ""
    print(f"📊 Dashboard{mode_str} saved to {final_output_path}")
    return final_output_path
