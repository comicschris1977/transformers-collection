"""
Generate the static collection website into site/.
Run this after fetch_images.py to include toy photos.
"""

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import db

SITE_DIR = Path(__file__).parent.parent / "docs"

STATUS_LABEL = {
    "owned": "Owned",
    "want": "Wishlist",
    "preordered": "Pre-ordered",
    "ordered": "Ordered",
}

STATUS_COLOR = {
    "owned": "#2ecc71",
    "want": "#3498db",
    "preordered": "#e67e22",
    "ordered": "#9b59b6",
}

PLACEHOLDER = "https://tfwiki.net/mediawiki/images2/thumb/8/8e/TFwiki_logo.png/200px-TFwiki_logo.png"


def build():
    db.init_db()
    figures = db.list_figures()
    stats = db.stats()

    SITE_DIR.mkdir(exist_ok=True)

    # Write JSON data file for JS to consume
    data = []
    for f in figures:
        data.append({
            "id": f["id"],
            "name": f["name"],
            "line": f["line"] or "",
            "status": f["status"],
            "rank": f["rank"],
            "retailer": f["retailer"] or "",
            "notes": f["notes"] or "",
            "combiner": f["combiner"] or "",
            "is_wrecker": f["is_wrecker"],
            "image_url": f["image_url"] or PLACEHOLDER,
        })

    with open(SITE_DIR / "data.json", "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False)

    status_color_js = json.dumps(STATUS_COLOR)
    status_label_js = json.dumps(STATUS_LABEL)
    today = __import__('datetime').date.today()

    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>Transformers Collection</title>
  <style>
    * {{ box-sizing: border-box; margin: 0; padding: 0; }}
    body {{
      font-family: 'Segoe UI', sans-serif;
      background: #0d0d0d;
      color: #eee;
      min-height: 100vh;
    }}
    header {{
      background: linear-gradient(135deg, #1a1a2e 0%, #16213e 50%, #0f3460 100%);
      padding: 24px 32px;
      border-bottom: 2px solid #e94560;
    }}
    header h1 {{
      font-size: 2rem;
      color: #e94560;
      letter-spacing: 2px;
      text-transform: uppercase;
    }}
    header p {{ color: #aaa; margin-top: 4px; font-size: 0.9rem; }}

    .stats {{
      display: flex;
      gap: 16px;
      padding: 20px 32px;
      background: #111;
      flex-wrap: wrap;
      border-bottom: 1px solid #222;
    }}
    .stat-card {{
      background: #1a1a1a;
      border-radius: 8px;
      padding: 12px 20px;
      text-align: center;
      min-width: 100px;
      border: 1px solid #2a2a2a;
    }}
    .stat-card .number {{ font-size: 1.8rem; font-weight: bold; color: #e94560; }}
    .stat-card .label {{ font-size: 0.75rem; color: #888; text-transform: uppercase; letter-spacing: 1px; margin-top: 2px; }}

    .controls {{
      padding: 20px 32px;
      display: flex;
      gap: 12px;
      flex-wrap: wrap;
      align-items: center;
      background: #111;
      border-bottom: 1px solid #222;
    }}
    #search {{
      padding: 10px 16px;
      border-radius: 6px;
      border: 1px solid #333;
      background: #1a1a1a;
      color: #eee;
      font-size: 1rem;
      width: 280px;
      outline: none;
    }}
    #search:focus {{ border-color: #e94560; }}
    .filter-btn {{
      padding: 8px 16px;
      border-radius: 6px;
      border: 1px solid #333;
      background: #1a1a1a;
      color: #aaa;
      cursor: pointer;
      font-size: 0.85rem;
      transition: all 0.2s;
    }}
    .filter-btn:hover {{ border-color: #e94560; color: #eee; }}
    .filter-btn.active {{ background: #e94560; border-color: #e94560; color: #fff; }}
    #result-count {{ color: #666; font-size: 0.85rem; margin-left: auto; }}

    .grid {{
      display: grid;
      grid-template-columns: repeat(auto-fill, minmax(220px, 1fr));
      gap: 16px;
      padding: 24px 32px;
    }}
    .card {{
      background: #1a1a1a;
      border-radius: 10px;
      overflow: hidden;
      border: 1px solid #2a2a2a;
      transition: transform 0.2s, border-color 0.2s;
      cursor: default;
    }}
    .card:hover {{ transform: translateY(-4px); border-color: #e94560; }}
    .card-img {{
      width: 100%;
      height: 200px;
      object-fit: contain;
      background: #111;
      padding: 8px;
    }}
    .card-body {{ padding: 12px; }}
    .card-name {{
      font-size: 1rem;
      font-weight: bold;
      color: #fff;
      margin-bottom: 4px;
      white-space: nowrap;
      overflow: hidden;
      text-overflow: ellipsis;
    }}
    .card-line {{ font-size: 0.8rem; color: #888; margin-bottom: 8px; }}
    .badges {{ display: flex; gap: 6px; flex-wrap: wrap; margin-bottom: 8px; }}
    .badge {{
      font-size: 0.7rem;
      padding: 2px 8px;
      border-radius: 20px;
      font-weight: 600;
      text-transform: uppercase;
      letter-spacing: 0.5px;
    }}
    .badge-status {{ color: #fff; }}
    .badge-wrecker {{ background: #2c3e50; color: #e74c3c; border: 1px solid #e74c3c; }}
    .badge-combiner {{ background: #2c3e50; color: #f39c12; border: 1px solid #f39c12; }}
    .card-rank {{ font-size: 0.85rem; color: #aaa; }}
    .card-rank span {{ color: #e94560; font-weight: bold; }}
    .card-retailer {{ font-size: 0.75rem; color: #666; margin-top: 4px; }}
    .card-notes {{ font-size: 0.75rem; color: #555; margin-top: 4px; font-style: italic; }}
    .no-results {{ text-align: center; color: #555; padding: 80px 32px; font-size: 1.1rem; }}
  </style>
</head>
<body>

<header>
  <h1>&#9889; Transformers Collection</h1>
  <p>Updated {today}</p>
</header>

<div class="stats">
  <div class="stat-card"><div class="number">{stats['total']}</div><div class="label">Total</div></div>
  <div class="stat-card"><div class="number">{stats['owned']}</div><div class="label">Owned</div></div>
  <div class="stat-card"><div class="number">{stats['want']}</div><div class="label">Wishlist</div></div>
  <div class="stat-card"><div class="number">{stats['preordered']}</div><div class="label">Pre-ordered</div></div>
  <div class="stat-card"><div class="number">{stats['ordered']}</div><div class="label">Ordered</div></div>
  <div class="stat-card"><div class="number">{stats['wreckers']}</div><div class="label">Wreckers</div></div>
  <div class="stat-card"><div class="number">{stats['avg_rank']}</div><div class="label">Avg Rank</div></div>
</div>

<div class="controls">
  <input type="text" id="search" placeholder="&#128269; Search name, line, combiner..." oninput="render()">
  <button class="filter-btn active" onclick="setFilter('all', this)">All</button>
  <button class="filter-btn" onclick="setFilter('owned', this)">Owned</button>
  <button class="filter-btn" onclick="setFilter('want', this)">Wishlist</button>
  <button class="filter-btn" onclick="setFilter('preordered', this)">Pre-ordered</button>
  <button class="filter-btn" onclick="setFilter('ordered', this)">Ordered</button>
  <button class="filter-btn" onclick="setFilter('wrecker', this)">Wreckers</button>
  <span id="result-count"></span>
</div>

<div class="grid" id="grid"></div>
<div class="no-results" id="no-results" style="display:none">No figures match your search.</div>

<script>
const STATUS_COLOR = {status_color_js};
const STATUS_LABEL = {status_label_js};
let allFigures = [];
let activeFilter = 'all';

async function init() {{
  const res = await fetch('data.json');
  allFigures = await res.json();
  render();
}}

function setFilter(f, btn) {{
  activeFilter = f;
  document.querySelectorAll('.filter-btn').forEach(b => b.classList.remove('active'));
  btn.classList.add('active');
  render();
}}

function render() {{
  const q = document.getElementById('search').value.toLowerCase().trim();
  let figs = allFigures;

  if (activeFilter === 'wrecker') {{
    figs = figs.filter(f => f.is_wrecker);
  }} else if (activeFilter !== 'all') {{
    figs = figs.filter(f => f.status === activeFilter);
  }}

  if (q) {{
    figs = figs.filter(f =>
      f.name.toLowerCase().includes(q) ||
      f.line.toLowerCase().includes(q) ||
      f.combiner.toLowerCase().includes(q) ||
      f.notes.toLowerCase().includes(q) ||
      f.retailer.toLowerCase().includes(q)
    );
  }}

  const grid = document.getElementById('grid');
  const noResults = document.getElementById('no-results');
  document.getElementById('result-count').textContent = `${{figs.length}} figure${{figs.length !== 1 ? 's' : ''}}`;

  if (figs.length === 0) {{
    grid.innerHTML = '';
    noResults.style.display = '';
    return;
  }}
  noResults.style.display = 'none';

  grid.innerHTML = figs.map(f => {{
    const color = STATUS_COLOR[f.status] || '#888';
    const label = STATUS_LABEL[f.status] || f.status;
    const rank = f.rank != null ? `<div class="card-rank">Rank: <span>${{f.rank}}/10</span></div>` : '';
    const wrecker = f.is_wrecker ? `<span class="badge badge-wrecker">Wrecker</span>` : '';
    const combiner = f.combiner ? `<span class="badge badge-combiner">${{f.combiner}}</span>` : '';
    const retailer = f.retailer ? `<div class="card-retailer">&#128722; ${{f.retailer}}</div>` : '';
    const notes = f.notes ? `<div class="card-notes">${{f.notes}}</div>` : '';
    const wikiUrl = `https://tfwiki.net/wiki/${{encodeURIComponent(f.name.replace(/ /g, '_'))}}`;

    return `
      <div class="card">
        <a href="${{wikiUrl}}" target="_blank" rel="noopener">
          <img class="card-img" src="${{f.image_url}}" alt="${{f.name}}"
               onerror="this.src='https://via.placeholder.com/220x200/111/444?text=No+Image'">
        </a>
        <div class="card-body">
          <div class="card-name" title="${{f.name}}">${{f.name}}</div>
          <div class="card-line">${{f.line || '—'}}</div>
          <div class="badges">
            <span class="badge badge-status" style="background:${{color}}">${{label}}</span>
            ${{wrecker}}${{combiner}}
          </div>
          ${{rank}}${{retailer}}${{notes}}
        </div>
      </div>`;
  }}).join('');
}}

init();
</script>
</body>
</html>"""

    with open(SITE_DIR / "index.html", "w", encoding="utf-8") as f:
        f.write(html)

    print(f"Site built: {SITE_DIR / 'index.html'}")
    print(f"  {len(figures)} figures, {len([f for f in figures if f['image_url'] and f['image_url'] != PLACEHOLDER])} with custom images")


if __name__ == "__main__":
    build()
