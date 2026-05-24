"""
Fetch toy images from actionfigure411.com.

Image URL pattern: https://www.actionfigure411.com/transformers/images/{slug}-{id}.jpg
Visual guide URL:  https://www.actionfigure411.com/transformers/{line-slug}-visual-guide.php

Usage:
  python fetch_af411.py               # fill figures missing images
  python fetch_af411.py --build-index # rebuild the slug index from visual guides
"""

import json, re, sys, time, urllib.parse, urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import db

IMAGES_DIR = Path(__file__).parent.parent / "docs" / "images"
INDEX_FILE = Path(__file__).parent / "af411_index.json"
BASE = "https://www.actionfigure411.com/transformers"

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
    "Accept": "text/html,*/*",
}

# Map our line codes to actionfigure411 visual guide slugs (can be multiple)
LINE_GUIDES = {
    "WFC":           ["war-for-cybertron-siege-series", "war-for-cybertron-earthrise", "war-for-cybertron-kingdom"],
    "SS86":          ["studio-series"],
    "SS":            ["studio-series"],
    "Legacy":        ["legacy-evolution", "legacy-united", "legacy-series"],
    "AotP":          ["age-of-the-primes"],
    "PotPrimes":     ["power-of-the-primes"],
    "PotP":          ["power-of-the-primes"],
    "Titans Return": ["titans-return"],
    "Combiner Wars": ["combiner-wars"],
    "Thrilling 30":  ["generations"],
    "Cyberverse":    ["cyberverse"],
    "Core":          ["legacy-evolution", "legacy-series"],
}


def fetch_html(url: str) -> str:
    req = urllib.request.Request(url, headers=HEADERS)
    try:
        with urllib.request.urlopen(req, timeout=15) as r:
            return r.read().decode("utf-8", errors="ignore")
    except Exception:
        return ""


def build_index_from_guide(guide_slug: str) -> dict:
    """Fetch a visual guide page and extract {name_lower: (slug, id)} entries."""
    url = f"{BASE}/{guide_slug}-visual-guide.php"
    html = fetch_html(url)
    if not html:
        return {}

    # Extract all product links: /transformers/.../slug-ID.php
    entries = {}
    for m in re.finditer(r'href="(/transformers/[^"]+/([^/"]+)-(\d+)\.php)"', html):
        full_slug = m.group(2)   # e.g. "trip-up-daddy-o"
        pid       = m.group(3)   # e.g. "4401"
        # Convert slug to searchable name (both individual names in a two-pack)
        parts = full_slug.replace("-", " ")
        entries[parts] = (full_slug, pid)
        # Also index individual parts split on " & " or " and "
        for sep in [" & ", " and "]:
            if sep in parts:
                for p in parts.split(sep):
                    entries[p.strip()] = (full_slug, pid)
    return entries


def load_or_build_index(lines: list) -> dict:
    """Load cached index or build it from the visual guides."""
    if INDEX_FILE.exists():
        return json.loads(INDEX_FILE.read_text())

    print("Building actionfigure411 index...")
    index = {}
    seen_guides = set()
    for line in lines:
        for guide in LINE_GUIDES.get(line, []):
            if guide in seen_guides:
                continue
            seen_guides.add(guide)
            print(f"  Fetching {guide}...", end=" ", flush=True)
            entries = build_index_from_guide(guide)
            print(f"{len(entries)} entries")
            index.update(entries)
            time.sleep(1)

    INDEX_FILE.write_text(json.dumps(index, indent=2))
    print(f"Index saved: {len(index)} total entries\n")
    return index


def name_variants(name: str) -> list:
    """Generate search-friendly variants of a figure name."""
    clean = re.sub(r"\s*\*.*", "", name).strip().lower()
    variants = [clean]
    # Strip common suffixes
    for suffix in [" bd", " *origins", " origins", " repaint", " reissue"]:
        if clean.endswith(suffix):
            variants.append(clean[:-len(suffix)].strip())
    return variants


def lookup(name: str, index: dict):
    """Find the best matching (slug, id) for a figure name."""
    for variant in name_variants(name):
        if variant in index:
            return index[variant]
        # Partial match — name is contained in an index key (two-pack)
        for key, val in index.items():
            if variant in key:
                return val
    return None


def download_af411(slug: str, pid: str, dest: Path) -> bool:
    url = f"{BASE}/images/{slug}-{pid}.jpg"
    req = urllib.request.Request(url, headers={**HEADERS, "Referer": BASE + "/"})
    try:
        with urllib.request.urlopen(req, timeout=15) as r:
            data = r.read()
        if len(data) < 5_000:
            return False
        dest.write_bytes(data)
        return True
    except Exception:
        return False


def fetch_figure_af411(figure_id: int, name: str, line: str, index: dict):
    result = lookup(name, index)
    if not result:
        return None
    slug, pid = result
    dest = IMAGES_DIR / f"{figure_id}.jpg"
    if download_af411(slug, pid, dest):
        return f"images/{figure_id}.jpg"
    return None


# ── Manual two-pack mappings (Micromasters) ───────────────────────────────────
# Both figures in a pair share the same product image
MANUAL_PAIRS = {
    # name_lower: (slug, id)
    "trip-up":     ("trip-up-daddy-o", "4401"),
    "daddy-o":     ("trip-up-daddy-o", "4401"),
    "bombshock":   ("bombshock-growl",  "4402"),
    "growl":       ("bombshock-growl",  "4402"),
    "red heat":    ("red-heat-stakeout", "5360"),
    "stakeout":    ("red-heat-stakeout", "5360"),
    "wild ride":   ("wild-ride-mudflap", "4686"),   # Legacy if it exists
}


def main():
    db.init_db()
    IMAGES_DIR.mkdir(parents=True, exist_ok=True)

    figures  = db.list_figures()
    rebuild  = "--build-index" in sys.argv
    if rebuild and INDEX_FILE.exists():
        INDEX_FILE.unlink()

    all_lines = list(set(f["line"] or "" for f in figures))
    index = load_or_build_index(all_lines)
    # Merge manual pairs
    index.update(MANUAL_PAIRS)

    targets = [f for f in figures if not f["image_url"] or f["image_url"].startswith("http")]
    print(f"{len(targets)} figures need images\n")

    ok = fail = 0
    for fig in targets:
        name, line, fid = fig["name"], fig["line"] or "", fig["id"]
        print(f"  {name} ({line}) ... ", end="", flush=True)
        rel = fetch_figure_af411(fid, name, line, index)
        if rel:
            db.set_image_url(fid, rel)
            print("OK")
            ok += 1
        else:
            print("not found")
            fail += 1
        time.sleep(0.5)

    print(f"\nDone: {ok} fetched, {fail} not found.")


if __name__ == "__main__":
    main()
