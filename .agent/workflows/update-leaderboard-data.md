---
description: Update Kaito Yaps and Cookie campaign leaderboard data
---

# Update Leaderboard Data

This workflow extracts project data from saved Kaito Yaps and Cookie.fun HTML pages, updates the JSON data files, and regenerates the dashboard with badges.

## Prerequisites

- Saved HTML files in the project root:
  - `Yapper Leaderboard - Pre-TGE.html` (from https://yaps.kaito.ai - filtered to Pre-TGE)
  - `Cookie.fun 1.0 (Alpha).html` (from https://cookie.fun/campaigns)

## Steps

### 1. Save Updated Webpages

1. Open https://yaps.kaito.ai in browser
2. Click "Pre-TGE" filter to show only pre-TGE projects
3. Save page as HTML: `Yapper Leaderboard - Pre-TGE.html`
4. Open https://cookie.fun/campaigns in browser
5. Save page as HTML: `Cookie.fun 1.0 (Alpha).html`

### 2. Extract Kaito Yaps Data

Run the extraction script to parse project names from the Kaito HTML:

```bash
// turbo
python3 << 'EOF'
import re
import json

with open('Yapper Leaderboard - Pre-TGE.html', 'r') as f:
    content = f.read()

# Extract project names from alt tags
pattern = r'alt="([A-Za-z0-9\s\.-]+)"'
matches = re.findall(pattern, content)

# Filter and clean
exclude = {'User', 'Avatar', 'Image', 'Logo', 'Icon', 'Coin', 'img'}
projects = sorted(set([
    m.strip() for m in matches 
    if m.strip() and len(m) > 2 and m not in exclude
    and not any(x in m.lower() for x in ['coin', 'icon', 'avatar'])
]))

data = {
    "pre_tge": projects,
    "post_tge": [],
    "summary": {"pre_tge_count": len(projects), "extracted_at": "$(date +%Y-%m-%d)"}
}

with open('data/kaito_yaps_projects.json', 'w') as f:
    json.dump(data, f, indent=2)

print(f"✅ Extracted {len(projects)} Kaito Pre-TGE projects")
EOF
```

### 3. Extract Cookie Campaign Data

Run the extraction script to parse campaigns from Cookie.fun HTML:

```bash
// turbo
python3 << 'EOF'
import re
import json

with open('Cookie.fun 1.0 (Alpha).html', 'r') as f:
    content = f.read()

# Extract project names from card icons
pattern = r'alt="([^"]+)"[^>]*width="40"'
matches = set(re.findall(pattern, content))

# Also get from alt tags with rounded-full class
alt_pattern = r'alt="([A-Za-z0-9 ]+)"[^>]*class="rounded-full'
alt_matches = set(re.findall(alt_pattern, content))

# Combine and filter
all_projects = matches | alt_matches
exclude = {'User', 'Avatar', 'Image', 'Logo', 'Icon'}
projects = sorted([p for p in all_projects if p not in exclude])

# Create normalized slugs
slugs = [p.lower().replace(' ', '-').replace('_', '-') for p in projects]
slugs = [re.sub(r'[^a-z0-9-]', '', s) for s in slugs]

data = {
    "source": "Cookie.fun Active Campaigns",
    "extracted_at": "$(date +%Y-%m-%d)",
    "active_campaigns": projects,
    "slugs": slugs,
    "count": len(projects)
}

with open('data/cookie_campaigns.json', 'w') as f:
    json.dump(data, f, indent=2)

print(f"✅ Extracted {len(projects)} Cookie campaigns")
EOF
```

### 4. Regenerate Dashboard

// turbo
```bash
python3 daily_tracker.py
```

This will:
- Load the updated Kaito and Cookie JSON files
- Display badges in Gap Analysis and Launch Timeline tabs
- Show 🟢 Kaito Pre-TGE (green) and 🍪 Cookie (orange) badges

### 5. Verify Changes

Open `dashboard.html` in browser and check:
- Gap Analysis tab: Kaito and Cookie badges on project cards
- Launch Timeline tab: K (green) and C (orange) badges next to project names
- Filter buttons work correctly

### 6. Commit Changes

```bash
git add data/kaito_yaps_projects.json data/cookie_campaigns.json
git commit -m "chore: update Kaito and Cookie leaderboard data"
```

## Data Files

| File | Description |
|------|-------------|
| `data/kaito_yaps_projects.json` | Pre-TGE and Post-TGE project lists from Kaito |
| `data/cookie_campaigns.json` | Active Cookie.fun campaign slugs |
| `data/launched_projects.json` | Launched projects with volume history |
| `src/polymarket/data/kaito.py` | KaitoStore and CookieStore classes |

## Troubleshooting

- **No projects extracted**: Check if HTML structure changed, may need to update regex patterns
- **Badges not showing**: Verify project name matching (uses normalized lowercase alphanumeric comparison)
- **Missing projects**: Some projects may have different names across platforms - check normalization logic
