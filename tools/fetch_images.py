"""
Fetch toy image URLs from TFWiki for each figure in the collection.
Uses TFWiki opensearch to find the best page, then scrapes the first
large content image from that page.

Stores the URL in the image_url column of the database.
"""

import sys
import time
import re
import urllib.parse
import urllib.request
import json
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import db

TFWIKI = "https://tfwiki.net"
API = f"{TFWIKI}/api.php"
DELAY = 0.75  # seconds between requests

LINE_ALIASES = {
    "SS86": "Studio Series 86",
    "SS": "Studio Series",
    "WFC": "War for Cybertron",
    "AotP": "Age of the Primes",
    "Legacy": "Legacy",
    "PotPrimes": "Power of the Primes",
    "PotP": "Power of the Primes",
    "Titans Return": "Titans Return",
    "Combiner Wars": "Combiner Wars",
    "Thrilling 30": "Thrilling 30",
    "Wreck N Rule": "Wreckers",
    "Core": "",
    "KO": "",
}


def api_get(params: dict) -> dict:
    params["format"] = "json"
    url = API + "?" + urllib.parse.urlencode(params)
    req = urllib.request.Request(url, headers={"User-Agent": "TransformersCollectionBot/1.0"})
    with urllib.request.urlopen(req, timeout=10) as r:
        return json.loads(r.read())


def opensearch(query: str) -> list[str]:
    """Return list of matching page titles."""
    data = api_get({"action": "opensearch", "search": query, "limit": 3})
    return data[1] if len(data) > 1 else []


def scrape_first_image(page_title: str) -> str | None:
    """Scrape TFWiki page HTML and return URL of the first large content image."""
    slug = page_title.replace(" ", "_")
    url = f"{TFWIKI}/wiki/{urllib.parse.quote(slug)}"
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    try:
        with urllib.request.urlopen(req, timeout=12) as r:
            html = r.read().decode("utf-8", errors="ignore")
    except Exception:
        return None

    # Find images from TFWiki's content image path, sized ≥120px
    srcs = re.findall(r'src="(/mediawiki/images2/thumb/[^"]+?)"', html)
    for src in srcs:
        m = re.search(r"/(\d+)px-", src)
        if m and int(m.group(1)) >= 120:
            # Upsize thumbnail to 400px
            upsized = re.sub(r"/\d+px-", "/400px-", src)
            return TFWIKI + upsized
    return None


def find_image(name: str, line: str | None) -> tuple[str | None, str]:
    """Return (image_url, page_title_used) or (None, '')."""
    line_expanded = LINE_ALIASES.get(line, line) if line else ""

    # Try increasingly broad searches
    queries = []
    if line_expanded:
        queries.append(f"{name} {line_expanded}")
    queries.append(name)

    for q in queries:
        titles = opensearch(q)
        time.sleep(DELAY)
        for title in titles:
            img = scrape_first_image(title)
            time.sleep(DELAY)
            if img:
                return img, title
    return None, ""


def main():
    db.init_db()
    figures = db.list_figures()
    missing = [f for f in figures if not f["image_url"]]
    print(f"{len(missing)} figures need images (out of {len(figures)} total)\n")

    found_count = 0
    for i, fig in enumerate(missing, 1):
        name = fig["name"]
        line = fig["line"]
        print(f"[{i}/{len(missing)}] {name} ({line}) ... ", end="", flush=True)
        try:
            url, page = find_image(name, line)
            if url:
                db.set_image_url(fig["id"], url)
                print(f"OK ({page})")
                found_count += 1
            else:
                print("not found")
        except Exception as e:
            print(f"ERROR: {e}")
        time.sleep(DELAY)

    total_with_img = len([f for f in db.list_figures() if f["image_url"]])
    print(f"\nDone. {total_with_img}/{len(figures)} figures have images.")


if __name__ == "__main__":
    main()
