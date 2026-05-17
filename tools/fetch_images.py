"""
Fetch toy images from TFWiki and save them locally to docs/images/<id>.jpg.
Downloads files locally to avoid hotlinking blocks.

Search strategy (in order):
  1. TFWiki search for "<name> toy <line>" — targets toy-specific pages
  2. TFWiki search for "<name> <line>"
  3. TFWiki search for "<name>"
  4. Skips the figure if nothing found

Stores the local relative path in image_url column.
"""

import sys
import time
import re
import urllib.parse
import urllib.request
import json
import shutil
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import db

TFWIKI = "https://tfwiki.net"
API = f"{TFWIKI}/api.php"
DELAY = 0.6
IMAGES_DIR = Path(__file__).parent.parent / "docs" / "images"

# TFWiki infobox image patterns to skip (faction logos, symbols, etc.)
SKIP_PATTERNS = [
    "symbol", "logo", "icon", "badge", "emblem", "autobot", "decepticon",
    "maximal", "predacon", "cobra", "nerv", "ghostbuster", "upbtn",
]

LINE_ALIASES = {
    "SS86": "Studio Series 86",
    "SS": "Studio Series",
    "WFC": "War for Cybertron",
    "AotP": "Age of the Primes",
    "Legacy": "Legacy Evolution",
    "PotPrimes": "Power of the Primes",
    "PotP": "Power of the Primes",
    "Titans Return": "Titans Return",
    "Combiner Wars": "Combiner Wars",
    "Thrilling 30": "Thrilling 30",
    "Wreck N Rule": "Wreckers",
    "Core": "Core class",
    "KO": "",
}


def api_get(params: dict) -> dict:
    params["format"] = "json"
    url = API + "?" + urllib.parse.urlencode(params)
    req = urllib.request.Request(url, headers={"User-Agent": "TransformersCollectionBot/1.0"})
    with urllib.request.urlopen(req, timeout=10) as r:
        return json.loads(r.read())


def opensearch(query: str, limit: int = 5) -> list[str]:
    data = api_get({"action": "opensearch", "search": query, "limit": limit})
    return data[1] if len(data) > 1 else []


def scrape_best_image(page_title: str) -> str | None:
    """
    Scrape TFWiki page and return the URL of the best toy image.
    Prefers larger images, skips faction symbols and logos.
    """
    slug = page_title.replace(" ", "_")
    url = f"{TFWIKI}/wiki/{urllib.parse.quote(slug)}"
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    try:
        with urllib.request.urlopen(req, timeout=12) as r:
            html = r.read().decode("utf-8", errors="ignore")
    except Exception:
        return None

    srcs = re.findall(r'src="(/mediawiki/images2/thumb/[^"]+?)"', html)
    candidates = []
    for src in srcs:
        lower = src.lower()
        if any(skip in lower for skip in SKIP_PATTERNS):
            continue
        m = re.search(r"/(\d+)px-", src)
        if m:
            size = int(m.group(1))
            if size >= 100:
                upsized = re.sub(r"/\d+px-", "/400px-", src)
                candidates.append((size, TFWIKI + upsized))

    if not candidates:
        return None
    # Return the URL of the largest image found
    candidates.sort(key=lambda x: x[0], reverse=True)
    return candidates[0][1]


def download_image(url: str, dest: Path) -> bool:
    """Download image URL to dest file. Returns True on success."""
    req = urllib.request.Request(url, headers={
        "User-Agent": "Mozilla/5.0",
        "Referer": TFWIKI,
    })
    try:
        with urllib.request.urlopen(req, timeout=15) as r:
            with open(dest, "wb") as f:
                shutil.copyfileobj(r, f)
        return dest.stat().st_size > 1000  # sanity check
    except Exception:
        if dest.exists():
            dest.unlink()
        return False


def find_and_download(figure_id: int, name: str, line: str | None) -> str | None:
    """
    Find the best TFWiki image for a figure and download it locally.
    Returns the relative web path (images/<id>.jpg) or None.
    """
    line_expanded = LINE_ALIASES.get(line, line) if line else ""

    queries = []
    if line_expanded:
        queries.append(f"{name} toy {line_expanded}")
        queries.append(f"{name} {line_expanded}")
    queries.append(f"{name} toy")
    queries.append(name)

    dest = IMAGES_DIR / f"{figure_id}.jpg"

    for q in queries:
        titles = opensearch(q, limit=5)
        time.sleep(DELAY)

        # Prefer titles that contain the character name (avoid totally wrong matches)
        name_lower = name.lower().split()[0]  # first word of name
        ranked = sorted(titles, key=lambda t: (name_lower not in t.lower(), t))

        for title in ranked:
            img_url = scrape_best_image(title)
            time.sleep(DELAY)
            if not img_url:
                continue
            if download_image(img_url, dest):
                return f"images/{figure_id}.jpg"
        break  # only try first query batch if we got results

    return None


def main():
    db.init_db()
    IMAGES_DIR.mkdir(parents=True, exist_ok=True)

    figures = db.list_figures()
    # Re-fetch all (clear old remote URLs), or just missing ones
    import sys
    refetch_all = "--all" in sys.argv
    if refetch_all:
        targets = figures
        print(f"Re-fetching ALL {len(targets)} figures...\n")
    else:
        targets = [f for f in figures if not f["image_url"] or f["image_url"].startswith("http")]
        print(f"{len(targets)} figures need local images (out of {len(figures)} total)\n")

    for i, fig in enumerate(targets, 1):
        name = fig["name"]
        line = fig["line"]
        print(f"[{i}/{len(targets)}] {name} ({line}) ... ", end="", flush=True)
        try:
            rel_path = find_and_download(fig["id"], name, line)
            if rel_path:
                db.set_image_url(fig["id"], rel_path)
                print(f"OK")
            else:
                db.set_image_url(fig["id"], None)
                print("not found")
        except Exception as e:
            print(f"ERROR: {e}")
        time.sleep(DELAY)

    local = len([f for f in db.list_figures() if f["image_url"] and not f["image_url"].startswith("http")])
    print(f"\nDone. {local}/{len(figures)} figures have local images.")


if __name__ == "__main__":
    main()
