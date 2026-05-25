"""
Smart image re-fetcher — applies everything we've learned this session.

Strategy per figure:
  1. KO / Wait-for*  -> character art (TFWiki infobox)
  2. TFWiki line-section match on character page (combined /toys +
     /Generations toys + continuity-aware variants)
  3. af411 line-aware lookup (filter to the figure's actual line guide)
  4. af411 generic fuzzy (last resort)

Image picking from a section:
  - Prefer files whose name contains the line token (e.g. "Legacy",
    "AOTP", "Studio-Series-86") OR start with the line-specific prefix
  - Avoid card art, box art, render previews, concept art
  - Prefer JPG over PNG (TFWiki uses PNG mostly for icons/symbols)

Usage:
  python tools/smart_fetch.py             -- DRY RUN (show diffs only)
  python tools/smart_fetch.py --apply     -- replace images, update DB
  python tools/smart_fetch.py --apply ID1 ID2 ...  -- only these IDs
  python tools/smart_fetch.py NAME LINE   -- probe one (dry run)

Backups: --apply copies the current image to docs/images/.backup/<id>.jpg
before overwriting, so anything we get wrong can be restored with
`python tools/smart_fetch.py --restore ID`.
"""
import hashlib
import json
import re
import shutil
import sys
import time
import urllib.parse
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import db
import fetch_images as fi
import fetch_af411 as af411
import verify

IMAGES_DIR  = fi.IMAGES_DIR
BACKUP_DIR  = IMAGES_DIR / ".backup"
API         = "https://tfwiki.net/api.php"
TF_HDR      = {"User-Agent": "TransformersCollectionBot/1.0"}
DL_HDR      = {**TF_HDR, "Accept": "image/jpeg,image/*", "Referer": "https://tfwiki.net/"}
AF_HDR      = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)",
               "Accept": "image/jpeg,image/*",
               "Referer": "https://www.actionfigure411.com/"}

# Filename tokens that strongly identify the toy line in a file's name.
# Used to pick the best image when a section has multiple files.
LINE_FILE_TOKENS = {
    "AotP":                 ["AOTP-toy", "AOTP "],
    "SS86":                 ["Studio-Series-86", "SS-86", "Studio Series 86"],
    "SS":                   ["Studio-Series", "Studio Series"],
    "SS86 Buzzworthy":      ["Studio-Series-86", "Buzzworthy"],
    "SS86 repaint":         ["Studio-Series-86"],
    "SS86 Repaint":         ["Studio-Series-86"],
    "SS86 Reissue":         ["Studio-Series-86"],
    "SS Bumbleebee Movie":  ["Studio-Series-BB", "Studio Series BB"],
    "Studio Bumblebee":     ["Studio-Series-BB"],
    "Core Bumblebee":       ["Studio-Series", "Core"],
    "WFC":                  ["WFC", "War-for-Cybertron", "TF-Generations-WFC"],
    "WFC: Siege":           ["WFC-S", "Siege"],
    "WFC: Earthrise":       ["WFC-E", "Earthrise"],
    "WFC: Kingdom":         ["WFC-K", "Kingdom"],
    "Kingdom":              ["WFC-K", "Kingdom"],
    "Legacy":               ["TF-Legacy", "Legacy"],
    "PotP":                 ["TF-POTP", "POTP"],
    "PotPrimes":            ["TF-POTP", "POTP"],
    "Power of the Primes":  ["TF-POTP", "POTP"],
    "Titans Return":        ["Titans-Return", "TF-Generations-Titans"],
    "Combiner Wars":        ["Combiner-Wars", "TF-Generations-Combiner"],
    "Wreck N Rule":         ["Wreckers", "Wreck"],
    "Core":                 ["Core-Class", "Core "],
    "Cyberverse":           ["Cyberverse"],
    "Beast Hunters":        ["Beast-Hunters", "BH"],
    "Crossover":            ["Collaborative", "Crossover"],
    "Hotwheels":            ["Hot-Wheels", "HotWheels"],
    "Devastation":          ["Devastation"],
    "Transformers One":     ["Transformers-One", "TFOne"],
    "Retro Headmasters":    ["Retro-Headmasters", "Vintage-G1-Headmaster"],
    "Retro Toy Version":    ["Retro", "Vintage-G1"],
    "SDCC version":         ["SDCC"],
    "Thrilling 30":         ["Thrilling-30"],
    "Generations":          ["TF-Generations"],
    "RiD":                  ["RID", "Robots-in-Disguise"],
}

# Substrings that disqualify a file as the main toy photo
EXCLUDE_KEYWORDS = [
    "cardart", "card-art", "card_art", "boxart", "box-art", "box_art",
    "concept", "render", "promo", "prototype", "logo", "symbol", "icon",
    "banner", "instructions", "package", "packaging", "marketing",
    "tech-spec", "tech_spec", "techspec", "early", "stock", "stub",
    "before-and-after", "comic", "cartoon-still", "screencap",
    # Cartoon-screencap descriptive patterns
    "snipes", "learns", "noms", "smallbot", "stuck", "loses",
    "fights", "saves", "talks", "shoots", "rescues", "battles",
    "explains", "salutes", "warns", "attacks", "defeats",
    " art.", "-art.",
]

# Strong "this is a toy photo" prefixes. Files starting with one of these are
# almost always cleanly-shot product photography.
TOY_PREFIXES = [
    "tf-legacy", "tf-studio-series", "tf-potp", "tf-aotp", "tf-ss-",
    "tf-generations", "tf-titans-return", "tf-combiner-wars",
    "tf-wfc", "tf-cyberverse", "tf-beast-hunters",
    "tf-retro", "tf-vintage-g1", "tf-rid", "tf-prime", "tf-age",
    "tf-collaborative", "tf-bot-shots", "tf-classics",
    "aotp-", "aotp ", "potp-", "ss-toy", "ss-deluxe", "ss-voyager",
    "ss-leader", "ss-commander", "ss86-", "legacy-",
    "studio-series-", "studio series", "war-for-cybertron-",
    "transformers-collaborative-", "collaborative-",
    "wfc-", "wfcs-", "wfc-s-", "wfc-e-", "wfc-k-",
    "powerofthe-primes-", "g2-universe-", "vg1-toy",
    "titanstoy", "earthrise-toy", "siege-toy", "kingdom-toy",
    "retrog1", "machinima-potp",
    "legacyevolutiontoy", "legacyunitedtoy",
]
# Threshold a file must meet to be picked. Stops us grabbing random
# cartoon stills as "toy photos".
MIN_TOY_SCORE = 20


def _api(params):
    url = API + "?" + urllib.parse.urlencode({**params, "format": "json"})
    req = urllib.request.Request(url, headers=TF_HDR)
    with urllib.request.urlopen(req, timeout=20) as r:
        return json.loads(r.read())


def _tf_file_url(filename):
    d = _api({"action": "query", "titles": "File:" + filename,
              "prop": "imageinfo", "iiprop": "url"})
    for p in d.get("query", {}).get("pages", {}).values():
        info = p.get("imageinfo", [])
        if info:
            return info[0].get("url")
    return None


def _download(url, dest, headers):
    req = urllib.request.Request(url, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=20) as r:
            data = r.read()
        if len(data) < 5000:
            return False, len(data)
        dest.write_bytes(data)
        return True, len(data)
    except Exception as e:
        return False, str(e)


def _hash(path):
    if not path.exists():
        return None
    return hashlib.md5(path.read_bytes()).hexdigest()


# --- TFWiki section-based fetch -------------------------------------------

def _matching_sections(data, line):
    """Return [(idx, title)] of TFWiki sections that match the line."""
    hints = verify.LINE_HINTS.get(line, [line])
    matches = []
    for i, title in enumerate(data["sections"], start=1):
        tl = title.lower()
        for hint in hints:
            if hint.lower() in tl:
                # index in API is 1-based but we just need the title for now
                matches.append((str(i), title))
                break
    return matches


def _score_file(filename, line):
    """Higher = better. Negative = exclude."""
    name = filename.lower()
    if any(kw in name for kw in EXCLUDE_KEYWORDS):
        return -1
    score = 0
    if name.endswith((".jpg", ".jpeg")):
        score += 5
    # Big boost for files that start with a known toy-photo prefix
    if any(name.startswith(p) for p in TOY_PREFIXES):
        score += 25
    # Boost for line-specific tokens anywhere in the filename
    tokens = LINE_FILE_TOKENS.get(line, [])
    for t in tokens:
        if t.lower() in name:
            score += 20
            break
    # Toy-ish words
    if "-toy" in name or "toy-" in name or "_toy" in name or "toy.jpg" in name:
        score += 3
    # Penalty for descriptive multi-word filenames (likely cartoon stills)
    space_count = name.count(" ")
    if space_count > 2:
        score -= 12
    return score


def _section_files(page, section_idx_or_title):
    """Fetch wikitext for a section, return file refs."""
    # We don't store section indexes in cache; re-fetch using title match
    try:
        d = _api({"action": "parse", "page": page,
                  "prop": "sections"})
        sections = d.get("parse", {}).get("sections", [])
        target_idx = None
        for s in sections:
            t = re.sub(r"<[^>]+>", "", s["line"])
            if t == section_idx_or_title or s["index"] == section_idx_or_title:
                target_idx = s["index"]
                break
        if not target_idx:
            return []
        d2 = _api({"action": "parse", "page": page,
                   "prop": "wikitext", "section": target_idx})
        wt = d2.get("parse", {}).get("wikitext", {}).get("*", "")
        return re.findall(
            r"\[\[(?:File|Image):([^\|\]]+\.(?:jpg|jpeg|png))",
            wt, re.IGNORECASE,
        )
    except Exception:
        return []


def fetch_tfwiki(name, line):
    """
    Get the best toy image from TFWiki for (name, line).
    Returns (url, filename, source_page) or (None, None, None).
    """
    data, primary = verify.find_page(name, line)
    if not data:
        return None, None, None

    # The verify cache merges multiple pages — we need to know which page
    # holds each section so we can fetch its wikitext. Re-walk the candidate
    # pages individually.
    clean_name, continuity = verify._parse_continuity(name)
    clean = re.sub(r"\s*\*.*", "", clean_name).strip().replace(" ", "_")
    candidates = [
        clean + "_(G1)/Generations toys",
        clean + "_(G1)/toys",
        clean + "/toys",
        clean + "_(G1)",
        clean,
    ]
    if continuity:
        cs = continuity.replace(" ", "_")
        candidates = [clean + "_(" + cs + ")/toys", clean + "_(" + cs + ")"] + candidates

    line_lc = (line or "").lower()
    if "transformers one" in line_lc:
        candidates = [clean + "_(Transformers_One)/toys", clean + "_(Transformers_One)"] + candidates
    if "cyberverse" in line_lc:
        candidates = [clean + "_(Cyberverse)/toys", clean + "_(Cyberverse)"] + candidates

    key_any = (clean_name.lower(), "*")
    if key_any in verify.PAGE_OVERRIDES:
        candidates = list(verify.PAGE_OVERRIDES[key_any]) + candidates

    hints = verify.LINE_HINTS.get(line, [line])

    for page in candidates:
        page_data = verify._fetch_page(page)
        if not page_data:
            continue
        # Find section in this page (word-boundary match so "Core" doesn't
        # match "Encore" and "Selects" doesn't match "Selectsmark" etc.)
        matching_titles = []
        for title in page_data["sections"]:
            tl = title.lower()
            for h in hints:
                pattern = r"\b" + re.escape(h.lower()) + r"\b"
                if re.search(pattern, tl):
                    matching_titles.append(title)
                    break
        for title in matching_titles:
            # Skip cartoon/comic sections — they list screencaps, not toys
            tl = title.lower()
            if any(bad in tl for bad in ("cartoon", "comic", "marketing material",
                                          "fiction", "manga", "continuity")):
                continue
            files = _section_files(page, title)
            time.sleep(0.3)
            if not files:
                continue
            scored = [(_score_file(f, line), f) for f in files]
            scored = [(s, f) for s, f in scored if s >= MIN_TOY_SCORE]
            scored.sort(key=lambda x: -x[0])
            for _, filename in scored[:5]:
                url = _tf_file_url(filename)
                time.sleep(0.2)
                if url:
                    return url, filename, f"{page}#{title}"
    return None, None, None


# --- af411 line-aware fallback --------------------------------------------

_af411_index = None
def _af_index():
    global _af411_index
    if _af411_index is None:
        figs = db.list_figures()
        lines = list(set(f["line"] or "" for f in figs))
        _af411_index = af411.load_or_build_index(lines)
        _af411_index.update(af411.MANUAL_PAIRS)
    return _af411_index


def fetch_af411_for_line(name, line):
    """af411 lookup — uses existing index."""
    idx = _af_index()
    result = af411.lookup(name, idx)
    if not result:
        return None, None, None
    slug, pid = result
    url = f"{af411.BASE}/images/{slug}-{pid}.jpg"
    return url, f"{slug}-{pid}.jpg", "af411"


# --- Top-level fetcher -----------------------------------------------------

def smart_fetch(name, line):
    """Returns dict: {url, filename, source} or None."""
    line_str = (line or "").strip()

    # Placeholder lines -> character art ONLY (do not fall through to toy search)
    if line_str.lower().startswith(("wait", "ko", "g1 ko")):
        url, fname, page = fi.get_infobox_image(name)
        if url:
            return {"url": url, "filename": fname, "source": f"infobox:{page}",
                    "headers": DL_HDR}
        return None  # placeholder line: don't try to find a "toy"

    # TFWiki section-based
    url, fname, src = fetch_tfwiki(name, line_str)
    if url:
        return {"url": url, "filename": fname, "source": f"tfwiki:{src}",
                "headers": DL_HDR}

    # af411 fallback
    url, fname, src = fetch_af411_for_line(name, line_str)
    if url:
        return {"url": url, "filename": fname, "source": "af411",
                "headers": AF_HDR}

    return None


# --- Main runner ----------------------------------------------------------

def run(apply=False, only_ids=None):
    db.init_db()
    figures = db.list_figures()
    if only_ids:
        figures = [f for f in figures if f["id"] in only_ids]

    if apply:
        BACKUP_DIR.mkdir(exist_ok=True, parents=True)

    changes = []  # (figure, new_filename, new_source, new_size)
    skipped = same = err = 0

    for i, f in enumerate(figures, 1):
        if i % 10 == 0:
            print(f"  ...{i}/{len(figures)}")
        fid, name, line = f["id"], f["name"], f["line"] or ""

        # Placeholder lines (Wait for*, KO) were hand-curated upstream; smart
        # fetch's character-art search isn't reliable enough to safely replace
        # them. Skip entirely if an image already exists.
        current_path = IMAGES_DIR / f"{fid}.jpg"
        if (line.lower().startswith(("wait", "ko", "g1 ko"))
                and current_path.exists()
                and current_path.stat().st_size > 5000):
            skipped += 1
            continue

        try:
            picked = smart_fetch(name, line)
        except Exception as e:
            err += 1
            print(f"  [{fid}] {name} [{line}] ERR: {e}")
            continue
        if not picked:
            skipped += 1
            continue

        # Compare with current image
        current_path = IMAGES_DIR / f"{fid}.jpg"
        current_hash = _hash(current_path)

        # Download to a temp path
        tmp = IMAGES_DIR / f"_tmp_{fid}.jpg"
        ok, info = _download(picked["url"], tmp, picked["headers"])
        if not ok:
            err += 1
            if tmp.exists():
                tmp.unlink()
            continue

        new_hash = _hash(tmp)
        if new_hash == current_hash:
            same += 1
            tmp.unlink()
            continue

        # Different — log it
        changes.append({
            "id": fid, "name": name, "line": line,
            "filename": picked["filename"],
            "source": picked["source"],
            "size_kb": tmp.stat().st_size // 1024,
        })

        if apply:
            # Back up current, replace
            if current_path.exists():
                shutil.copy2(current_path, BACKUP_DIR / f"{fid}.jpg")
            shutil.move(str(tmp), str(current_path))
            db.set_image_url(fid, f"images/{fid}.jpg")
        else:
            tmp.unlink()

    print(f"\n{'=' * 60}")
    print(f"Total: {len(figures)}, same: {same}, would change: {len(changes)}, "
          f"skipped: {skipped}, errors: {err}")
    print("=" * 60)
    if changes:
        print(f"\nDiff ({'APPLIED' if apply else 'DRY RUN'}):\n")
        for c in changes:
            print(f"  [{c['id']:>4}] {c['name']:<28} [{c['line']:<18}]  "
                  f"-> {c['filename']} ({c['size_kb']}KB, via {c['source']})")
    if apply:
        print(f"\nBackups saved to {BACKUP_DIR}")
    return changes


def restore(ids):
    """Restore backed-up images for given IDs."""
    db.init_db()
    for fid in ids:
        bak = BACKUP_DIR / f"{fid}.jpg"
        dest = IMAGES_DIR / f"{fid}.jpg"
        if not bak.exists():
            print(f"  [{fid}] no backup found")
            continue
        shutil.copy2(bak, dest)
        db.set_image_url(fid, f"images/{fid}.jpg")
        print(f"  [{fid}] restored from backup")


def main():
    apply   = "--apply"   in sys.argv
    restore_mode = "--restore" in sys.argv

    positional = [a for a in sys.argv[1:] if not a.startswith("--")]
    # Numeric IDs only
    id_args = [int(a) for a in positional if a.isdigit()]

    if restore_mode:
        if not id_args:
            print("Usage: --restore ID [ID ...]")
            return
        restore(id_args)
        return

    # Single-pair probe: smart_fetch.py NAME LINE
    if len(positional) == 2 and not positional[0].isdigit():
        name, line = positional
        r = smart_fetch(name, line)
        print(f"\n{name} [{line}]")
        if r:
            print(f"  -> {r['filename']}\n     from {r['source']}\n     URL: {r['url']}")
        else:
            print("  -> nothing found")
        return

    run(apply=apply, only_ids=id_args or None)


if __name__ == "__main__":
    main()
