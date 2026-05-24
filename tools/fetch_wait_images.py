"""
For 'Wait for...' figures, fetch the main TFWiki character page image
(the infobox/top image) rather than a specific toy version.
Also updates fetch_images.py behaviour so future unknowns use the same fallback.
"""
import sys, time, urllib.parse, urllib.request, json, re
sys.path.insert(0, r"C:\Projects\Transformers\tools")
import db, fetch_images as fi

db.init_db()
fi.IMAGES_DIR.mkdir(parents=True, exist_ok=True)

API = "https://tfwiki.net/api.php"

def api(params):
    url = API + "?" + urllib.parse.urlencode({**params, "format": "json"})
    req = urllib.request.Request(url, headers={"User-Agent": "TransformersCollectionBot/1.0"})
    with urllib.request.urlopen(req, timeout=20) as r:
        return json.loads(r.read())

# Infobox image skip list — things that are NOT the character art
SKIP = [
    "symbol", "logo", "icon", "banner", "flag", "nav",
    "placeholder", "stub", "noimage", "insignia", "badge",
    "featured", "vanguard", "con-g2", "allspark", "all_spark",
    "primus", "matrix", "energon", "ozsa", "timeline",
]

def score_image(filename):
    """Score a TFWiki image filename — higher = more likely to be character art."""
    name = filename.lower()
    score = 0
    # Strongly prefer JPG (PNG files are usually icons/symbols on TFWiki)
    if name.endswith(".jpg") or name.endswith(".jpeg"):
        score += 10
    # Skip obvious non-art
    if any(kw in name for kw in SKIP):
        return -999
    # Boost names that look like character art
    if any(kw in name for kw in ["art", "cartoon", "animation", "g1", "tf"]):
        score += 3
    # Penalise very short names (usually icons)
    if len(filename) < 10:
        score -= 5
    return score

def get_infobox_image(char_name):
    """
    Get the best character art image from a TFWiki character main page.
    Tries {Name} first, then {Name}_(G1).
    """
    clean = fi.clean_name(char_name).replace(" ", "_")
    for page in [clean, clean + "_(G1)"]:
        try:
            d = api({"action": "parse", "page": page, "prop": "images"})
            if "error" in d:
                continue
            imgs = d.get("parse", {}).get("images", [])
            scored = sorted(
                [(score_image(img), img) for img in imgs
                 if img.lower().endswith((".jpg", ".jpeg", ".png"))],
                reverse=True,
            )
            candidates = [img for sc, img in scored if sc > 0]
            for candidate in candidates[:5]:
                url = fi.get_image_url(candidate)
                time.sleep(0.3)
                if url:
                    return url, candidate, page
        except Exception as e:
            print(f"    API error for {page}: {e}")
        time.sleep(0.5)
    return None, None, None

# Get all Wait-for figures (re-fetch all so bad images get replaced)
figures = db.list_figures()
waits = [f for f in figures if f["line"] and "wait" in f["line"].lower()]
print(f"Processing {len(waits)} Wait-for figures...\n")

ok = skip = fail = 0
for fig in waits:
    fid, name, line = fig["id"], fig["name"], fig["line"]
    print(f"  {name} ({line})", end=" ... ", flush=True)

    url, fname, page = get_infobox_image(name)
    time.sleep(0.5)

    if url:
        dest = fi.IMAGES_DIR / f"{fid}.jpg"
        if fi.download(url, dest):
            db.set_image_url(fid, f"images/{fid}.jpg")
            print(f"OK — {fname}")
            ok += 1
        else:
            print(f"download failed ({fname})")
            fail += 1
    else:
        print("not found on TFWiki")
        fail += 1

print(f"\nDone: {ok} updated, {fail} failed, {skip} skipped.")
