"""
Verify (character, line) pairs against TFWiki's actual toy releases.

Catches mislabels before they cause wrong images. Used by sync_sheet to
flag changed/new figures, and runnable standalone to scan the whole DB.

Usage:
  python tools/verify.py             -- show all mismatches in DB
  python tools/verify.py --quiet     -- one line per mismatch
  python tools/verify.py --rebuild   -- ignore cache, re-query TFWiki
  python tools/verify.py NAME LINE   -- check one specific pair

How it works:
  - Fetches the character's TFWiki page section titles (cached locally)
  - Matches the figure's `line` against expected keywords for that line
  - If no section matches, suggests what TFWiki *does* have for that
    character (so you can quickly see the right line value)
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

API        = "https://tfwiki.net/api.php"
HDR        = {"User-Agent": "TransformersCollectionBot/1.0"}
CACHE_FILE = Path(__file__).parent / "tfwiki_sections_cache.json"

# Keywords expected in TFWiki section titles for each line code.
# (Case-insensitive substring match against any section title.)
#
# TFWiki organises toy lists by parent line, not wave. So "SS86" maps to
# "Studio Series" (the parent), not "Studio Series 86". Specific waves are
# subsections inside that parent and aren't returned by prop=sections.
LINE_HINTS = {
    # Studio Series — any SS subline accepted (waves are not in top-level sections)
    "SS":                   ["Studio Series"],
    "SS86":                 ["Studio Series"],
    "SS86 Buzzworthy":      ["Studio Series", "Buzzworthy"],
    "SS86 repaint":         ["Studio Series"],
    "SS86 Repaint":         ["Studio Series"],
    "SS86 Reissue":         ["Studio Series"],
    "SS Bumbleebee Movie":  ["Studio Series"],
    "Studio Bumblebee":     ["Studio Series"],
    "Core Bumblebee":       ["Studio Series", "Core"],

    # War for Cybertron trilogy — all three sublines under "War for Cybertron Trilogy"
    "WFC":                  ["War for Cybertron"],
    "WFC: Siege":           ["War for Cybertron", "Siege"],
    "WFC: Earthrise":       ["War for Cybertron", "Earthrise"],
    "WFC: Kingdom":         ["War for Cybertron", "Kingdom"],
    "Kingdom":              ["War for Cybertron", "Kingdom"],

    # Modern Generations sublines
    "AotP":                 ["Age of the Primes"],
    "Legacy":               ["Legacy"],
    "PotPrimes":            ["Power of the Primes"],
    "PotP":                 ["Power of the Primes"],
    "Power of the Primes":  ["Power of the Primes"],
    "Titans Return":        ["Titans Return"],
    "Combiner Wars":        ["Combiner Wars"],
    "Thrilling 30":         ["Generations", "Thrilling 30"],
    "Generations":          ["Generations"],
    "Wreck N Rule":         ["Wreckers", "Selects"],
    # Core is a class (Core class), not a line — appears in many lines
    "Core":                 ["Core", "Studio Series", "Legacy", "Cyberverse"],

    # Retro / reissue / collab
    "Retro Headmasters":    ["Retro", "Headmasters", "Vintage G1"],
    "Retro Toy Version":    ["Retro", "Vintage G1"],
    "Crossover":            ["Crossover", "Collaborative", "Collab"],
    "Hotwheels":            ["Hot Wheels", "Collaborative", "Crossover"],

    # Other animated continuities
    "Cyberverse":           ["Cyberverse"],
    # Beast Hunters was a wave of Transformers Prime (2013)
    "Beast Hunters":        ["Prime", "Beast Hunters"],
    "RiD":                  ["Robots in Disguise"],
    # "Devastation" likely Combiner Wars Devastator OR Studio Series Devastation
    "Devastation":          ["Devastation", "Combiner Wars", "Studio Series"],
    "Transformers One":     ["Transformers One"],

    # Special exclusives — accept many lines since SDCC drops happen widely
    "SDCC version":         ["SDCC", "Exclusive", "Generations", "Studio Series"],
}

# Lines that intentionally have no specific toy (character art only)
PLACEHOLDER_PREFIXES = ("wait", "ko", "g1 ko")

# Section titles that look toy-related (used to filter suggestions)
TOY_KEYWORDS = [
    "Studio Series", "Generations", "Legacy", "Cyberverse",
    "Power of the Primes", "Titans Return", "Combiner Wars",
    "War for Cybertron", "Age of the Primes", "Retro", "Wreckers",
    "Buzzworthy", "Cybertron", "Thrilling 30", "Beast Hunters",
    "Crossover", "Collaborative", "Collab", "Hot Wheels", "SDCC",
    "Siege", "Earthrise", "Kingdom", "Selects", "Origins",
    "Headmasters", "Devastation", "Transformers One", "Robots in Disguise",
    "Core Class", "Voyager", "Leader", "Commander", "Deluxe",
]

# ──────────────────────────────────────────────────────────────────────────
# Cache
# ──────────────────────────────────────────────────────────────────────────

_cache = None
def _get_cache():
    global _cache
    if _cache is None:
        if CACHE_FILE.exists():
            try:
                _cache = json.loads(CACHE_FILE.read_text())
            except Exception:
                _cache = {}
        else:
            _cache = {}
    return _cache

def _save_cache():
    if _cache is not None:
        CACHE_FILE.write_text(json.dumps(_cache, indent=2))

# ──────────────────────────────────────────────────────────────────────────
# TFWiki
# ──────────────────────────────────────────────────────────────────────────

def _api(params):
    url = API + "?" + urllib.parse.urlencode({**params, "format": "json"})
    req = urllib.request.Request(url, headers=HDR)
    with urllib.request.urlopen(req, timeout=20) as r:
        return json.loads(r.read())

def _clean(name):
    return re.sub(r"\s*\*.*", "", name).strip()

def _parse_continuity(name):
    """Extract '*<continuity>' suffix from a name. Returns (clean_name, continuity|None)."""
    m = re.match(r"^(.+?)\s*\*\s*(.+)$", name)
    if m:
        return m.group(1).strip(), m.group(2).strip()
    return name.strip(), None

# Known character-name → preferred TFWiki page mappings (no auto-discovery needed)
PAGE_OVERRIDES = {
    # Transformers One (2024 movie) — characters use their pre-Optimus names
    ("optimus prime", "transformers one"): ["Orion_Pax", "Orion_Pax/toys", "Orion_Pax_(Transformers_One)"],
    ("megatron", "transformers one"):      ["D-16", "D-16/toys"],
    # Quintesson Judge — SS86 release of the Pit of Judgement Quintesson
    ("quintesson", "*"):                   ["Quintesson_Judge_(G1)/toys", "Quintesson_Judge_(G1)",
                                            "Quintesson_Judge"],
    # Vector Prime is a Cybertron-line character (no G1 page)
    ("vector prime", "*"):                 ["Vector_Prime_(Cybertron)/toys", "Vector_Prime_(Cybertron)"],
}

# Line abbreviation -> patterns to search in TFWiki File namespace for
# proof-of-existence. Used as a final fallback when section/wikitext matching
# both fail. Patterns are joined with character name during search.
FILE_LINE_TOKENS = {
    "AotP":                 ["AOTP", "Age of the Primes"],
    "SS86":                 ["Studio-Series-86", "Studio Series 86", "SS-86"],
    "SS":                   ["Studio-Series", "Studio Series"],
    "SS86 Buzzworthy":      ["Buzzworthy", "Studio-Series-86"],
    "SS86 repaint":         ["Studio-Series-86"],
    "SS86 Repaint":         ["Studio-Series-86"],
    "SS86 Reissue":         ["Studio-Series-86"],
    "SS Bumbleebee Movie":  ["Studio-Series", "Bumblebee-Movie"],
    "Studio Bumblebee":     ["Studio-Series", "Bumblebee-Movie"],
    "Core Bumblebee":       ["Core-Class", "Studio-Series"],
    "WFC":                  ["WFC", "War-for-Cybertron"],
    "WFC: Siege":           ["WFC-S", "Siege"],
    "WFC: Earthrise":       ["WFC-E", "Earthrise"],
    "WFC: Kingdom":         ["WFC-K", "Kingdom"],
    "Kingdom":              ["Kingdom"],
    "Legacy":               ["Legacy"],
    "PotP":                 ["POTP", "Power-of-the-Primes"],
    "PotPrimes":            ["POTP"],
    "Power of the Primes":  ["POTP"],
    "Titans Return":        ["Titans-Return", "TR"],
    "Combiner Wars":        ["Combiner-Wars", "CW"],
    "Wreck N Rule":         ["Wreckers", "Wreck"],
    "Core":                 ["Core-Class", "Core"],
    "Cyberverse":           ["Cyberverse"],
    "Beast Hunters":        ["Beast-Hunters", "Prime"],
    "Crossover":            ["Collaborative", "Crossover"],
    "Hotwheels":            ["Hot-Wheels", "HotWheels"],
    "Devastation":          ["Devastation", "Combiner-Wars"],
    "Transformers One":     ["Transformers-One", "TFOne"],
    "Retro Headmasters":    ["Retro", "Vintage-G1", "Headmaster"],
    "Retro Toy Version":    ["Retro", "Vintage-G1"],
    "SDCC version":         ["SDCC"],
    "Thrilling 30":         ["Thrilling-30", "Generations"],
    "Generations":          ["Generations"],
    "RiD":                  ["RID", "Robots-in-Disguise"],
}

def _fetch_page(page):
    """
    Return {"sections": [...], "wikitext_lc": "..."} for a page, or None if missing.
    Cached on disk so repeat runs are instant.
    """
    cache = _get_cache()
    if page in cache:
        v = cache[page]
        if v is None:
            return None
        if isinstance(v, dict):
            return v
        # Old format (just a list of sections) — fall through to re-fetch with wikitext
        del cache[page]
    try:
        d = _api({"action": "parse", "page": page, "prop": "sections|wikitext"})
        if "error" in d:
            cache[page] = None
        else:
            sections = [re.sub(r"<[^>]+>", "", s["line"])
                        for s in d.get("parse", {}).get("sections", [])]
            wt = d.get("parse", {}).get("wikitext", {}).get("*", "")
            cache[page] = {
                "sections": sections,
                "wikitext_lc": wt.lower(),  # store lowercase for fast matching
            }
        time.sleep(0.3)
        _save_cache()
        return cache[page]
    except Exception:
        return None

def find_page(name, line=""):
    """
    Try common TFWiki page name variants and combine sections+wikitext from
    every one that exists.

    TFWiki splits long character pages: e.g., G1 Optimus's modern Generations
    sublines (SS86, Legacy, WFC, etc.) live at `Optimus_Prime_(G1)/Generations toys`,
    not on the main /toys page. So we always merge.

    Some lines map to character variants on different continuities (e.g.,
    "Transformers One" -> `_(Transformers_One)`).

    Returns (combined_data, primary_page_used) or (None, None).
    """
    clean_name, continuity = _parse_continuity(name)
    clean = re.sub(r"\s*\*.*", "", clean_name).strip().replace(" ", "_")
    candidates = [
        clean + "/toys",
        clean + "_(G1)/toys",
        clean + "_(G1)/Generations toys",
        clean + "_(G1)",
        clean,
    ]

    # Star-suffix continuity: "Nemesis Prime *Animated" -> also try _(Animated)
    if continuity:
        cont_safe = continuity.replace(" ", "_")
        candidates.insert(0, clean + "_(" + cont_safe + ")")
        candidates.insert(0, clean + "_(" + cont_safe + ")/toys")

    # Line-specific continuity variants
    line_lc = (line or "").lower()
    if "transformers one" in line_lc or "tfone" in line_lc:
        candidates.insert(0, clean + "_(Transformers_One)")
        candidates.insert(0, clean + "_(Transformers_One)/toys")
    if "cyberverse" in line_lc:
        candidates.insert(0, clean + "_(Cyberverse)")
        candidates.insert(0, clean + "_(Cyberverse)/toys")
    if "beast hunters" in line_lc or line_lc == "rid":
        candidates.insert(0, clean + "_(Prime)")
        candidates.insert(0, clean + "_(Prime)/toys")
        candidates.insert(0, clean + "_(Robots_in_Disguise_2015)")

    # Explicit overrides for tricky character/line combos
    key_specific = (clean_name.lower(), (line or "").lower())
    key_any      = (clean_name.lower(), "*")
    for key in (key_specific, key_any):
        if key in PAGE_OVERRIDES:
            for p in reversed(PAGE_OVERRIDES[key]):
                candidates.insert(0, p)

    all_sections = []
    all_wikitext = []
    pages_used = []
    for page in candidates:
        data = _fetch_page(page)
        if data:
            all_sections.extend(data["sections"])
            all_wikitext.append(data["wikitext_lc"])
            pages_used.append(page)

    if not pages_used:
        return None, None

    return {
        "sections": all_sections,
        "wikitext_lc": "\n".join(all_wikitext),
    }, pages_used[0]

# ──────────────────────────────────────────────────────────────────────────
# Verification
# ──────────────────────────────────────────────────────────────────────────

def verify(name, line):
    """
    Check whether (name, line) makes sense per TFWiki.

    Returns dict:
      ok          : True if valid (or unverifiable), False if mismatch
      page        : TFWiki page used, or None
      suggestions : list of section titles TFWiki has for this character
      reason      : human-readable explanation
    """
    line_str = (line or "").strip()

    if line_str.lower().startswith(PLACEHOLDER_PREFIXES):
        return {"ok": True, "page": None, "suggestions": [], "reason": "placeholder line"}

    data, page = find_page(name, line_str)
    if data is None:
        return {"ok": True, "page": None, "suggestions": [],
                "reason": "no TFWiki page found — can't verify"}

    sections = data["sections"]
    wt_lc    = data["wikitext_lc"]

    hints = LINE_HINTS.get(line_str, [line_str])
    if not hints:
        return {"ok": True, "page": page, "suggestions": [], "reason": "no hints"}

    # Pass 1: section title match (cheap, strict)
    for hint in hints:
        hl = hint.lower()
        for sec in sections:
            if hl in sec.lower():
                return {"ok": True, "page": page, "suggestions": [], "reason": "section match"}

    # Pass 2: wikitext mention (handles subsections, prose mentions of the line)
    for hint in hints:
        if hint.lower() in wt_lc:
            return {"ok": True, "page": page, "suggestions": [],
                    "reason": "wikitext mention"}

    # Pass 3: File-namespace search.  If TFWiki has an image file whose name
    # contains a line token AND part of the character name, the figure is real.
    file_tokens = FILE_LINE_TOKENS.get(line_str, [])
    if file_tokens:
        clean_name = _clean(name)
        first_word = clean_name.split()[0] if clean_name else ""
        for token in file_tokens:
            if _file_exists_for(token, first_word):
                return {"ok": True, "page": page, "suggestions": [],
                        "reason": f"file proof: {token} + {first_word}"}

    # Still nothing — build suggestions from sections
    suggestions, seen = [], set()
    for s in sections:
        if s in seen:
            continue
        if any(kw.lower() in s.lower() for kw in TOY_KEYWORDS):
            suggestions.append(s)
            seen.add(s)

    if not suggestions:
        return {"ok": True, "page": page, "suggestions": [],
                "reason": "no toy sections on TFWiki page — can't verify"}

    return {"ok": False, "page": page, "suggestions": suggestions[:20],
            "reason": "no section or wikitext match"}


_file_search_cache = None
def _file_exists_for(line_token, char_word):
    """
    Returns True if TFWiki has any File: matching both the line token and the
    character name fragment. Cached.
    """
    global _file_search_cache
    if _file_search_cache is None:
        f = Path(__file__).parent / "tfwiki_filesearch_cache.json"
        if f.exists():
            try:
                _file_search_cache = json.loads(f.read_text())
            except Exception:
                _file_search_cache = {}
        else:
            _file_search_cache = {}

    key = f"{line_token}||{char_word}".lower()
    if key in _file_search_cache:
        return _file_search_cache[key]
    try:
        d = _api({"action": "query", "list": "search",
                  "srsearch": f'"{line_token}" {char_word}',
                  "srnamespace": 6, "srlimit": 3})
        hits = d.get("query", {}).get("search", [])
        result = bool(hits)
        time.sleep(0.3)
        _file_search_cache[key] = result
        (Path(__file__).parent / "tfwiki_filesearch_cache.json").write_text(
            json.dumps(_file_search_cache, indent=2)
        )
        return result
    except Exception:
        return False

# ──────────────────────────────────────────────────────────────────────────
# CLI
# ──────────────────────────────────────────────────────────────────────────

def main():
    quiet   = "--quiet"   in sys.argv
    rebuild = "--rebuild" in sys.argv

    # Single-pair check: python verify.py "Blot" "Combiner Wars"
    positional = [a for a in sys.argv[1:] if not a.startswith("--")]
    if len(positional) == 2:
        name, line = positional
        r = verify(name, line)
        flag = "OK" if r["ok"] else "MISMATCH"
        print(f"{flag}: {name} [{line}]  ({r['reason']})")
        if r["page"]:
            print(f"  TFWiki: {r['page']}")
        if r["suggestions"]:
            print(f"  TFWiki has these toy-related sections:")
            for s in r["suggestions"]:
                print(f"    - {s}")
        return

    if rebuild and CACHE_FILE.exists():
        CACHE_FILE.unlink()
        global _cache
        _cache = None

    db.init_db()
    figs = db.list_figures()
    print(f"Verifying {len(figs)} figures against TFWiki...\n")

    mismatches = []
    for i, f in enumerate(figs, 1):
        if i % 25 == 0:
            print(f"  ...{i}/{len(figs)}")
        r = verify(f["name"], f["line"])
        if not r["ok"]:
            mismatches.append((f, r))

    print(f"\n{'=' * 60}")
    print(f"Found {len(mismatches)} possible mislabels:")
    print("=" * 60)

    if not mismatches:
        print("All figures look consistent with TFWiki.")
        return

    for f, r in mismatches:
        if quiet:
            top = ", ".join(r["suggestions"][:3]) if r["suggestions"] else "(no toy sections)"
            print(f"  {f['name']} [{f['line']}]  -> {top}")
        else:
            print(f"\n  {f['name']} [{f['line']}]  (id {f['id']})")
            print(f"    TFWiki page: {r['page']}")
            if r['suggestions']:
                print(f"    TFWiki has these toy-related sections:")
                for s in r['suggestions']:
                    print(f"      - {s}")
            else:
                print(f"    TFWiki has no toy-related sections for this character")

if __name__ == "__main__":
    main()
