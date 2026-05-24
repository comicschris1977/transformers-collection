"""
Fetch toy-specific product images from TFWiki.

Strategy (tried in order):
  1. {Name}/toys  — works for minor characters (Alpha Trion, etc.)
  2. {Name}_(G1)/toys — works for most G1-continuity characters
  3. File namespace search — fallback for characters whose /toys page is missing/outdated

Run:
  python fetch_images.py            -- fill figures missing a local image
  python fetch_images.py --all      -- re-fetch everything
  python fetch_images.py --missing  -- only figures with no image_url at all
"""

import json
import re
import sys
import time
import urllib.parse
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import db

IMAGES_DIR = Path(__file__).parent.parent / "docs" / "images"
API = "https://tfwiki.net/api.php"
DELAY = 0.8

HEADERS = {
    "User-Agent": "TransformersCollectionBot/1.0 (personal site, not commercial)",
    "Accept": "application/json",
}

# --------------------------------------------------------------------------
# Map our line codes to ordered lists of TFWiki section names to search for
# --------------------------------------------------------------------------
LINE_SECTIONS: dict = {
    "SS86":              ["Studio Series 86", "Studio Series"],
    "SS":                ["Studio Series"],
    "WFC":               ["War for Cybertron"],   # matches Siege/Earthrise/Kingdom too
    "AotP":              ["Age of the Primes"],
    "Legacy":            ["Legacy", "Legacy Evolution", "Generations Legacy"],
    "PotPrimes":         ["Power of the Primes"],
    "PotP":              ["Power of the Primes"],
    "Titans Return":     ["Titans Return"],
    "Combiner Wars":     ["Combiner Wars"],
    "Thrilling 30":      ["Thrilling 30", "Generations"],
    "Wreck N Rule":      ["Wreckers", "Wreck N Rule"],
    "Core":              ["Core", "Core Class"],
    "Retro Headmasters": ["Retro", "Headmasters"],
    "Retro Toy Version": ["Retro"],
    "Crossover":         ["Crossovers", "Crossover"],
    "Cyberverse":        ["Cyberverse"],
    "Beast Hunters":     ["Beast Hunters"],
    "Devastation":       ["Devastation"],
    "Studio Bumblebee":  ["Studio Series Bumblebee", "Studio Series"],
    "SS86 Buzzworthy":   ["Studio Series 86 Buzzworthy", "Studio Series 86", "Studio Series"],
    "SS86 repaint":      ["Studio Series 86", "Studio Series"],
    "SS86 Reissue":      ["Studio Series 86", "Studio Series"],
}

# Line code -> expanded name used in file searches
LINE_EXPANDED: dict = {
    "SS86":          "Studio Series 86",
    "SS":            "Studio Series",
    "WFC":           "War for Cybertron",
    "AotP":          "Age of the Primes",
    "Legacy":        "Legacy",
    "PotPrimes":     "Power of the Primes",
    "PotP":          "Power of the Primes",
    "Titans Return": "Titans Return",
    "Combiner Wars": "Combiner Wars",
    "Thrilling 30":  "Thrilling 30",
}

# Words in filenames that indicate non-toy-photo images
SKIP_KEYWORDS = [
    "icon", "logo", "banner", "nav", "flag", "symbol",
    "placeholder", "noimage", "stub", "coming_soon", "cartoon",
    "packaging", "box", "art", "concept", "early", "stock",
]


def clean_name(name: str) -> str:
    return re.sub(r"\s*\*.*", "", name).strip()


def api_call(params: dict) -> dict:
    url = API + "?" + urllib.parse.urlencode({**params, "format": "json"})
    req = urllib.request.Request(url, headers=HEADERS)
    with urllib.request.urlopen(req, timeout=20) as r:
        return json.loads(r.read())


# --------------------------------------------------------------------------
# Section-based approach
# --------------------------------------------------------------------------

def get_sections(page_title: str) -> list:
    try:
        d = api_call({"action": "parse", "page": page_title, "prop": "sections"})
        if "error" in d:
            return []
        return [(s["index"], s["line"]) for s in d.get("parse", {}).get("sections", [])]
    except Exception:
        return []


def get_section_wikitext(page_title: str, section_idx: str) -> str:
    try:
        d = api_call({
            "action": "parse",
            "page": page_title,
            "prop": "wikitext",
            "section": section_idx,
        })
        return d.get("parse", {}).get("wikitext", {}).get("*", "")
    except Exception:
        return ""


def extract_files(wikitext: str) -> list:
    return re.findall(
        r"\[\[(?:File|Image):([^\|\]]+\.(?:jpg|jpeg|png))",
        wikitext,
        re.IGNORECASE,
    )


def find_section(sections: list, line: str):
    candidates = LINE_SECTIONS.get(line or "", [line or ""])
    for target in candidates:
        target_lower = target.lower()
        for idx, title in sections:
            title_lower = re.sub(r"<[^>]+>", "", title).lower()  # strip HTML tags
            if target_lower in title_lower or title_lower in target_lower:
                return idx
    return None


def get_image_url(filename: str):
    try:
        d = api_call({
            "action": "query",
            "titles": "File:" + filename,
            "prop": "imageinfo",
            "iiprop": "url",
        })
        pages = d.get("query", {}).get("pages", {})
        for page in pages.values():
            info = page.get("imageinfo", [])
            if info:
                return info[0].get("url")
    except Exception:
        pass
    return None


def rank_files(files: list) -> list:
    """Sort candidate files: toy photos first, skip obvious non-photos."""
    scored = []
    for f in files:
        name_lower = f.lower()
        if any(kw in name_lower for kw in SKIP_KEYWORDS):
            continue
        score = 0
        if any(x in name_lower for x in ["toy", "figure", "robot"]):
            score += 2
        scored.append((score, f))
    scored.sort(key=lambda x: -x[0])
    return [f for _, f in scored]


def try_toys_page(page_title: str, line: str, dest: Path):
    """Try to get image from a /toys page. Returns relative path or None."""
    sections = get_sections(page_title)
    time.sleep(DELAY)
    if not sections:
        return None

    idx = find_section(sections, line or "")
    if idx is None:
        return None

    wikitext = get_section_wikitext(page_title, idx)
    time.sleep(DELAY)

    files = extract_files(wikitext)
    if not files:
        return None

    candidates = rank_files(files) or files[:5]
    for filename in candidates[:5]:
        url = get_image_url(filename)
        time.sleep(0.3)
        if url and download(url, dest):
            return "images/" + dest.name

    return None


# --------------------------------------------------------------------------
# File-search fallback
# --------------------------------------------------------------------------

def file_search_fallback(name: str, line: str, dest: Path):
    """Search TFWiki File namespace for a matching toy image."""
    line_exp = LINE_EXPANDED.get(line or "", line or "")
    cn = clean_name(name)

    queries = []
    if line_exp:
        queries.append(f"{cn} {line_exp}")
    queries.append(cn)

    for q in queries:
        try:
            d = api_call({
                "action": "query",
                "list": "search",
                "srsearch": q,
                "srnamespace": 6,   # File namespace
                "srlimit": 10,
            })
        except Exception:
            continue
        time.sleep(DELAY)

        results = [h["title"].removeprefix("File:") for h in d.get("query", {}).get("search", [])]
        candidates = rank_files(results) or results[:5]

        for filename in candidates[:5]:
            url = get_image_url(filename)
            time.sleep(0.3)
            if url and download(url, dest):
                return "images/" + dest.name

    return None


# --------------------------------------------------------------------------
# Download helper
# --------------------------------------------------------------------------

def download(url: str, dest: Path) -> bool:
    req = urllib.request.Request(url, headers={
        **HEADERS,
        "Accept": "image/jpeg,image/png,image/*",
        "Referer": "https://tfwiki.net/",
    })
    try:
        with urllib.request.urlopen(req, timeout=20) as r:
            data = r.read()
        if len(data) < 5_000:
            return False
        dest.write_bytes(data)
        return True
    except Exception:
        if dest.exists():
            dest.unlink()
        return False


# --------------------------------------------------------------------------
# Main entry
# --------------------------------------------------------------------------

def try_main_page(page_title: str, dest: Path):
    """Try to get a toy image from the character's main page (for minor chars with no /toys subpage)."""
    try:
        d = api_call({"action": "parse", "page": page_title, "prop": "wikitext"})
        if "error" in d:
            return None
        wikitext = d.get("parse", {}).get("wikitext", {}).get("*", "")
    except Exception:
        return None

    files = extract_files(wikitext)
    if not files:
        return None

    candidates = rank_files(files) or files[:5]
    for filename in candidates[:5]:
        url = get_image_url(filename)
        time.sleep(0.3)
        if url and download(url, dest):
            return "images/" + dest.name
    return None


def fetch_figure(figure_id: int, name: str, line) -> str:
    cn = clean_name(name)
    wiki_name = cn.replace(" ", "_")
    dest = IMAGES_DIR / (str(figure_id) + ".jpg")

    # Strategy 1: {Name}/toys
    result = try_toys_page(wiki_name + "/toys", line, dest)
    if result:
        return result

    # Strategy 2: {Name}_(G1)/toys
    result = try_toys_page(wiki_name + "_(G1)/toys", line, dest)
    if result:
        return result

    # Strategy 3: Main character page (minor chars like Jalopy with no /toys subpage)
    result = try_main_page(wiki_name, dest)
    if result:
        return result

    # Strategy 4: File namespace search
    result = file_search_fallback(cn, line, dest)
    if result:
        return result

    return None


def main():
    db.init_db()
    IMAGES_DIR.mkdir(parents=True, exist_ok=True)

    figures = db.list_figures()
    refetch_all = "--all" in sys.argv
    missing_only = "--missing" in sys.argv

    if refetch_all:
        targets = figures
        print(f"Re-fetching ALL {len(targets)} figures...\n")
    elif missing_only:
        targets = [f for f in figures if not f["image_url"]]
        print(f"{len(targets)} figures have no image\n")
    else:
        targets = [
            f for f in figures
            if not f["image_url"] or f["image_url"].startswith("http")
        ]
        print(f"{len(targets)} figures need images\n")

    ok = fail = 0
    for i, fig in enumerate(targets, 1):
        name, line, fid = fig["name"], fig["line"], fig["id"]
        print(f"[{i}/{len(targets)}] {name} ({line}) ... ", end="", flush=True)
        try:
            rel = fetch_figure(fid, name, line)
            if rel:
                db.set_image_url(fid, rel)
                print("OK")
                ok += 1
            else:
                print("not found")
                fail += 1
        except Exception as e:
            print(f"ERROR: {e}")
            fail += 1

    local = sum(
        1 for f in db.list_figures()
        if f["image_url"] and not f["image_url"].startswith("http")
    )
    print(f"\nDone. {ok} fetched this run, {fail} failed.")
    print(f"Total local images: {local}/{len(figures)}")


if __name__ == "__main__":
    main()
