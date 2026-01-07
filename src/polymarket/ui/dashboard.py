"""
Dashboard HTML Generator

Generates the interactive HTML dashboard with all tabs.
"""

import json
import os
import re
from datetime import datetime
from ..config import Config


def generate_html_dashboard(current_markets, prev_snapshot, prev_date, limitless_data=None, leaderboard_data=None, portfolio_data=None, launched_projects=None, kaito_data=None, cookie_data=None):
    """Generate an HTML dashboard with data embedded, grouped by PROJECT"""
    
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
        .event-card.priority-project {{
            border: 2px solid var(--red);
            box-shadow: 0 0 10px rgba(239, 68, 68, 0.3);
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
            <button class="tab-btn" onclick="switchTab('launched')">🎯 Launched</button>
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

        <!-- Tab 6: Launched Projects -->
        <div id="tab-launched" class="tab-content">
            <div style="text-align:center;margin-bottom:1.5rem;">
                <p style="color:var(--text-secondary);font-size:0.95rem;">
                    Track post-TGE market performance for launched projects
                </p>
            </div>
            <div id="launched-view" style="background:var(--bg-card);border-radius:12px;padding:20px;"></div>
        </div>
    </div>

    <script>
        const projectsData = {json.dumps(projects_data)};
        const limitlessData = {json.dumps(limitless_data.get('projects', {}) if limitless_data else {})};
        const limitlessError = {json.dumps(limitless_data.get('error') if limitless_data else None)};
        const leaderboardData = {json.dumps(leaderboard_data if leaderboard_data else {})};
        const portfolioData = {json.dumps(portfolio_data if portfolio_data else [])};
        const launchedProjectsData = {json.dumps(launched_projects if launched_projects else [])};
        const kaitoData = {json.dumps(kaito_data if kaito_data else {"pre_tge": [], "post_tge": []})};
        const cookieData = {json.dumps(cookie_data if cookie_data else {"slugs": [], "active_campaigns": []})};
        let showClosed = false;
        let gapRendered = false;
        let arbRendered = false;
        let portfolioRendered = false;
        let launchedRendered = false;

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
            if (tab === 'launched' && !launchedRendered) {{
                renderLaunchedProjects();
                launchedRendered = true;
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
            
            // Helper to get leaderboard info
            function getLeaderboard(projName) {{
                const key = projName.toLowerCase();
                return leaderboardData[key] || null;
            }}

            // Sort projects: leaderboard projects first, then by earliest 50% threshold
            const sorted = projects.sort((a,b) => {{
                const aLb = getLeaderboard(a);
                const bLb = getLeaderboard(b);

                // Leaderboard projects come first
                if (aLb && !bLb) return -1;
                if (!aLb && bLb) return 1;

                // Then sort by earliest 50% date
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

                // Kaito status lookup
                const projLower = proj.toLowerCase().replace(/[^a-z0-9]/g, '');
                const kaitoPreTge = kaitoData.pre_tge || [];
                const kaitoPostTge = kaitoData.post_tge || [];
                const isKaitoPreTge = kaitoPreTge.some(k => k.toLowerCase().replace(/[^a-z0-9]/g, '') === projLower);
                const isKaitoPostTge = kaitoPostTge.some(k => k.toLowerCase().replace(/[^a-z0-9]/g, '') === projLower);
                
                // Cookie status lookup
                const cookieSlugs = cookieData.slugs || [];
                const hasCookieCampaign = cookieSlugs.some(s => s.replace(/-/g, '') === projLower);

                // Calculate gradient based on Kaito status
                const lastProb = milestones[milestones.length-1].prob;
                const alpha = 0.15 + lastProb * 0.8;
                const barColor = isKaitoPreTge ? '16,185,129' : hasCookieCampaign ? '245,158,11' : lb ? '139,92,246' : '99,102,241';

                // Build badges
                let badges = '';
                if (isKaitoPreTge) {{
                    badges += '<span style="background:#10b981;color:white;padding:1px 4px;border-radius:3px;font-size:0.55rem;margin-left:4px;font-weight:600;">K</span>';
                }} else if (isKaitoPostTge) {{
                    badges += '<span style="background:#6b7280;color:white;padding:1px 4px;border-radius:3px;font-size:0.55rem;margin-left:4px;font-weight:600;">K</span>';
                }}
                if (hasCookieCampaign) {{
                    badges += '<span style="background:#f59e0b;color:white;padding:1px 4px;border-radius:3px;font-size:0.55rem;margin-left:2px;font-weight:600;">C</span>';
                }}

                html += `<div style="display:flex;align-items:center;height:28px;margin-bottom:4px;">`;
                html += `<div style="width:160px;padding-right:10px;text-align:right;font-size:0.8rem;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;display:flex;align-items:center;justify-content:flex-end;">${{proj}}${{badges}}</div>`;
                html += `<div style="flex:1;position:relative;height:100%;">`;
                html += `<div style="position:absolute;left:${{leftPct}}%;width:${{widthPct}}%;height:20px;top:4px;background:rgba(${{barColor}},${{alpha.toFixed(2)}});border-radius:4px;"></div>`;
                
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
                        polyPrice: m.newPrice,
                        yesTokenId: m.yesTokenId,
                        noTokenId: m.noTokenId
                    }}))
                );

                const matchedMarkets = [];
                const unmatchedMarkets = [];

                polyMarkets.forEach(pm => {{
                    if (limitlessProject && limitlessProject.data.markets) {{
                        const match = findMarketMatch(pm.question, limitlessProject.data.markets);
                        if (match) {{
                            const spread = (pm.polyPrice - match.yes_price) * 100;
                            const liq = match.liquidity || {{}};
                            const depth = liq.depth || 0;
                            matchedMarkets.push({{
                                question: pm.question,
                                polyPrice: pm.polyPrice,
                                limPrice: match.yes_price,
                                spread: spread,
                                absSpread: Math.abs(spread),
                                polyYesTokenId: pm.yesTokenId,
                                polyNoTokenId: pm.noTokenId,
                                limSlug: match.slug,
                                liquidity: {{
                                    type: liq.type || 'amm',
                                    depth: depth,
                                    bids: liq.bids || [],
                                    asks: liq.asks || [],
                                    isLow: depth < 500
                                }}
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

                projects.push({{
                    name: polyProject.name,
                    hasLimitless: !!limitlessProject,
                    matchedMarkets,
                    unmatchedMarkets,
                    maxSpread,
                    kaitoStatus,
                    hasCookieCampaign,
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
                // Check if has any leaderboard (Kaito pre-tge, Cookie, or CSV)
                const aHasLB = !!a.leaderboard || a.kaitoStatus === 'pre-tge' || a.hasCookieCampaign;
                const bHasLB = !!b.leaderboard || b.kaitoStatus === 'pre-tge' || b.hasCookieCampaign;
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
            const matchedProjects = projects.filter(p => p.matchedMarkets.length > 0).length;
            const priorityProjects = projects.filter(p => p.leaderboard && !p.hasLimitless);
            const leaderboardMissing = priorityProjects.length;
            const kaitoPreTgeMissing = projects.filter(p => p.kaitoStatus === 'pre-tge' && !p.hasLimitless).length;
            const kaitoPreTgeCount = projects.filter(p => p.kaitoStatus === 'pre-tge').length;

            let html = `
                <div style="display:flex;flex-wrap:wrap;gap:0.75rem;margin-bottom:1rem;">
                    <button class="tab-btn active" id="gap-filter-all" onclick="filterGap('all')" style="padding:0.5rem 1rem;font-size:0.8rem;">
                        All Projects
                    </button>
                    <button class="tab-btn" id="gap-filter-kaito-pretge" onclick="filterGap('kaito-pretge')" style="padding:0.5rem 1rem;font-size:0.8rem;background:#10b981;border-color:#10b981;color:white;">
                        🟢 Kaito Pre-TGE (${{kaitoPreTgeMissing}} gaps)
                    </button>
                    <button class="tab-btn" id="gap-filter-priority" onclick="filterGap('priority')" style="padding:0.5rem 1rem;font-size:0.8rem;background:var(--red);border-color:var(--red);color:white;">
                        🚨 Priority (${{leaderboardMissing}})
                    </button>
                    <button class="tab-btn" id="gap-filter-missing" onclick="filterGap('missing')" style="padding:0.5rem 1rem;font-size:0.8rem;">
                        Not on Limitless
                    </button>
                    <button class="tab-btn" id="gap-filter-leaderboard" onclick="filterGap('leaderboard')" style="padding:0.5rem 1rem;font-size:0.8rem;">
                        Has Leaderboard
                    </button>
                </div>
                <div style="display:flex;justify-content:space-between;margin-bottom:1.5rem;padding:0.5rem 1rem;background:var(--bg-secondary);border-radius:8px;flex-wrap:wrap;gap:0.5rem;">
                    <span style="color:#10b981;font-size:0.9rem;">
                        🟢 <strong>${{kaitoPreTgeMissing}}</strong> Kaito Pre-TGE projects need Limitless markets
                    </span>
                    <span style="color:var(--red);font-size:0.9rem;">
                        🚨 <strong>${{leaderboardMissing}}</strong> leaderboard projects missing
                    </span>
                    <span style="color:var(--green);font-size:0.9rem;">
                        ✅ <strong>${{totalMatched}}</strong> markets matched
                    </span>
                </div>
            `;

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
                
                // Only show lbBadge if it's not already covered by Kaito or Cookie badges
                const lbSource = lb ? lb.source : '';
                const showLbBadge = lb && !lbSource.includes('Yaps') && !lbSource.includes('Cookie');
                const lbBadge = showLbBadge ? `<a href="${{lb.link}}" target="_blank" style="text-decoration:none;margin-left:0.5rem;"><span style="background:#8b5cf6;color:white;padding:0.15rem 0.4rem;border-radius:4px;font-size:0.65rem;font-weight:600;">${{lb.source}}</span></a>` : '';
                
                const isHighPriority = isKaitoPreTge && !project.hasLimitless;

                html += `
                    <div class="event-card gap-project${{isCollapsed ? ' collapsed' : ''}}${{isHighPriority ? ' priority-project' : ''}}" id="gap-${{projectId}}" data-has-leaderboard="${{lb ? 'true' : 'false'}}" data-on-limitless="${{project.hasLimitless ? 'true' : 'false'}}" data-priority="${{isPriority ? 'true' : 'false'}}" data-kaito="${{project.kaitoStatus}}" data-cookie="${{project.hasCookieCampaign ? 'true' : 'false'}}">
                        <div class="event-header" onclick="toggleGapProject('${{projectId}}')">
                            <div style="display:flex;align-items:center;flex-wrap:wrap;">
                                <span class="toggle-icon">▼</span>
                                <span class="event-title" style="cursor:pointer;">${{project.name}}</span>
                                ${{kaitoBadge}}
                                ${{cookieBadge}}
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
                                    <th style="text-align:right;width:90px;">Liq (Lim)</th>
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

                        html += `
                            <tr style="cursor:pointer;" onclick="toggleDepthChart('${{rowId}}')"
                                data-poly-token="${{m.polyYesTokenId || ''}}"
                                data-lim-slug="${{m.limSlug || ''}}"
                                data-lim-bids='${{JSON.stringify(liq.bids || [])}}'
                                data-lim-asks='${{JSON.stringify(liq.asks || [])}}'
                                data-lim-type="${{liq.type || 'amm'}}">
                                <td class="market-question">${{m.question}}</td>
                                <td style="text-align:right;font-weight:500;">${{(m.polyPrice * 100).toFixed(1)}}%</td>
                                <td style="text-align:right;font-weight:500;">${{(m.limPrice * 100).toFixed(1)}}%</td>
                                <td style="text-align:right;color:${{spreadColor}};font-weight:500;">${{spreadSign}}${{m.spread.toFixed(1)}}pp</td>
                                <td style="text-align:right;color:${{liqColor}};font-size:0.85rem;">
                                    ${{depthStr}}${{liqWarning}}
                                    <span style="font-size:0.7rem;color:var(--text-secondary);margin-left:2px;">(${{liqType}})</span>
                                </td>
                            </tr>
                            <tr id="${{rowId}}" style="display:none;background:var(--bg-secondary);">
                                <td colspan="5" style="padding:1rem;">
                                    <div id="${{rowId}}-chart" style="min-height:200px;display:flex;align-items:center;justify-content:center;">
                                        <span style="color:var(--text-secondary);">Loading depth chart...</span>
                                    </div>
                                </td>
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

        function drawDepthChart(container, polyData, limData, limType) {{
            // Colors
            const polyColor = '#6366f1';  // Indigo for Polymarket
            const limColor = '#a855f7';   // Purple for Limitless

            // Normalize orderbook data
            const polyBids = (polyData?.bids || []).map(b => ({{ price: parseFloat(b.price), size: parseFloat(b.size) }}));
            const polyAsks = (polyData?.asks || []).map(a => ({{ price: parseFloat(a.price), size: parseFloat(a.size) }}));
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
            let bids = Object.values(bidLevels).sort((a, b) => b.price - a.price);
            let asks = Object.values(askLevels).sort((a, b) => a.price - b.price).reverse();

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
                            <input type="checkbox" checked onchange="toggleOBPlatform('${{obId}}', 'poly', this.checked)" style="accent-color:${{polyColor}};">
                            <span style="color:${{polyColor}};">■ Polymarket</span>
                        </label>
                        <label style="display:flex;align-items:center;gap:4px;cursor:pointer;">
                            <input type="checkbox" checked onchange="toggleOBPlatform('${{obId}}', 'lim', this.checked)" style="accent-color:${{limColor}};">
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
                            <div class="${{obId}}-poly" style="position:absolute;left:0;top:0;height:100%;width:${{polyWidth}}%;background:${{polyColor}};opacity:0.6;transition:opacity 0.15s;"></div>
                            <div class="${{obId}}-lim" style="position:absolute;left:0;top:0;height:100%;width:${{limWidth}}%;background:${{limColor}};opacity:0.6;transition:opacity 0.15s;"></div>
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
                            <div class="${{obId}}-poly" style="position:absolute;left:0;top:0;height:100%;width:${{polyWidth}}%;background:${{polyColor}};opacity:0.6;transition:opacity 0.15s;"></div>
                            <div class="${{obId}}-lim" style="position:absolute;left:0;top:0;height:100%;width:${{limWidth}}%;background:${{limColor}};opacity:0.6;transition:opacity 0.15s;"></div>
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

            // Recalculate cumulative totals based on what's visible
            const state = obVisibility[obId];

            // Update ask cumulative totals (accumulate from best ask near spread to worst at top)
            const askRows = Array.from(document.querySelectorAll(`.${{obId}}-ask`));
            let askRunning = 0;
            // Process from last (best ask) to first (worst ask)
            for (let i = askRows.length - 1; i >= 0; i--) {{
                const row = askRows[i];
                const polyVal = parseFloat(row.dataset.poly) || 0;
                const limVal = parseFloat(row.dataset.lim) || 0;
                let levelTotal = 0;
                if (state.poly) levelTotal += polyVal;
                if (state.lim) levelTotal += limVal;
                askRunning += levelTotal;
                const totalSpan = row.querySelector(`.${{obId}}-total`);
                if (totalSpan) totalSpan.textContent = '$' + askRunning.toFixed(0);
            }}

            // Update bid cumulative totals (accumulate from best bid near spread to worst at bottom)
            const bidRows = Array.from(document.querySelectorAll(`.${{obId}}-bid`));
            let bidRunning = 0;
            // Process from first (best bid) to last (worst bid)
            for (let i = 0; i < bidRows.length; i++) {{
                const row = bidRows[i];
                const polyVal = parseFloat(row.dataset.poly) || 0;
                const limVal = parseFloat(row.dataset.lim) || 0;
                let levelTotal = 0;
                if (state.poly) levelTotal += polyVal;
                if (state.lim) levelTotal += limVal;
                bidRunning += levelTotal;
                const totalSpan = row.querySelector(`.${{obId}}-total`);
                if (totalSpan) totalSpan.textContent = '$' + bidRunning.toFixed(0);
            }}
        }}

        async function toggleDepthChart(rowId) {{
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
            chartContainer.innerHTML = '<span style="color:var(--text-secondary);">Fetching Polymarket orderbook...</span>';

            const polyData = await fetchPolyOrderbook(polyTokenId);
            const limData = {{ bids: limBids, asks: limAsks }};

            drawDepthChart(chartContainer, polyData, limData, limType);
        }}

        function filterGap(filter) {{
            // Update button states
            document.querySelectorAll('#gap-analysis .tab-btn').forEach(btn => {{
                btn.classList.remove('active');
                if (btn.id !== 'gap-filter-priority') {{
                    btn.style.background = '';
                    btn.style.borderColor = '';
                    btn.style.color = '';
                }}
            }});
            document.getElementById('gap-filter-' + filter).classList.add('active');

            // Show/hide projects based on filter
            document.querySelectorAll('.gap-project').forEach(card => {{
                const hasLB = card.dataset.hasLeaderboard === 'true';
                const onLim = card.dataset.onLimitless === 'true';
                const isPriority = card.dataset.priority === 'true';

                let show = false;
                switch(filter) {{
                    case 'all':
                        show = true;
                        break;
                    case 'kaito-pretge':
                        show = card.dataset.kaito === 'pre-tge' && !onLim;
                        break;
                    case 'priority':
                        show = isPriority;
                        break;
                    case 'missing':
                        show = !onLim;
                        break;
                    case 'leaderboard':
                        show = hasLB;
                        break;
                }}

                card.style.display = show ? '' : 'none';
            }});
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
                                <div style="display:grid;grid-template-columns:repeat(3, 1fr);gap:0.5rem;">
                                    <div style="background:var(--bg-secondary);padding:0.75rem;border-radius:8px;text-align:center;">
                                        <div style="font-size:1.1rem;font-weight:600;">${{formatVolume(project.pre_tge_volume)}}</div>
                                        <div style="font-size:0.65rem;color:var(--text-secondary);">Pre-TGE</div>
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
    </script>
</body>
</html>'''
    
    output_path = Config.DASHBOARD_OUTPUT
    with open(output_path, 'w') as f:
        f.write(html)

    print(f"📊 Dashboard saved to {output_path}")
    return output_path
