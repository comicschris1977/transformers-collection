"""Fix the 4 not-found Wait figures and Starscream's wrong image."""
import sys, urllib.parse, urllib.request, json, time, sqlite3
sys.path.insert(0, r"C:\Projects\Transformers\tools")
import db, fetch_images as fi

db.init_db()

API = "https://tfwiki.net/api.php"
def api(p):
    url = API + "?" + urllib.parse.urlencode({**p, "format": "json"})
    req = urllib.request.Request(url, headers={"User-Agent": "TransformersCollectionBot/1.0"})
    with urllib.request.urlopen(req, timeout=20) as r:
        return json.loads(r.read())

SKIP = [
    "symbol","logo","icon","banner","flag","nav","placeholder","stub",
    "noimage","insignia","badge","featured","vanguard","con-g2","allspark",
    "all_spark","primus","matrix","ozsa","timeline","soundwave","megatron",
]

def best_jpg(imgs, char_hint=""):
    hint = char_hint.lower().replace(" ", "")
    # First pass: prefer filenames containing the character name
    for img in imgs:
        n = img.lower()
        if any(kw in n for kw in SKIP): continue
        if hint and hint[:5] in n.replace("-","").replace("_",""):
            url = fi.get_image_url(img)
            if url: return url, img
    # Second pass: any clean jpg
    for img in imgs:
        n = img.lower()
        if any(kw in n for kw in SKIP): continue
        if n.endswith((".jpg", ".jpeg")):
            url = fi.get_image_url(img)
            if url: return url, img
    # Third pass: include PNG
    for img in imgs:
        n = img.lower()
        if any(kw in n for kw in SKIP): continue
        url = fi.get_image_url(img)
        if url: return url, img
    return None, None

def fetch_and_save(fig_id, page, char_hint=""):
    d = api({"action": "parse", "page": page, "prop": "images"})
    if "error" in d:
        return False, "page not found"
    imgs = d.get("parse", {}).get("images", [])
    url, fname = best_jpg(imgs, char_hint)
    time.sleep(0.3)
    if not url:
        return False, "no usable image"
    dest = fi.IMAGES_DIR / f"{fig_id}.jpg"
    if fi.download(url, dest):
        db.set_image_url(fig_id, f"images/{fig_id}.jpg")
        return True, fname
    return False, f"download failed ({fname})"

fixes = [
    # (fig_id, name, page_to_try)
    (621, "Rodimus Prime", "Rodimus_Prime"),
    (669, "Six Shot",      "Sixshot_(G1)"),
    (672, "Slug",          "Slug_(G1)"),
    (563, "Lightspeed",    "Lightspeed_(G1)"),
    (666, "Starscream",    "Starscream_(G1)"),   # fix wrong image
]

# Get fig IDs from DB by name for the wait figures
all_figs = {f["name"]: f["id"] for f in db.list_figures()}

for fid, name, page in fixes:
    # Resolve ID from DB if possible
    actual_id = all_figs.get(name, fid)
    print(f"{name} (id {actual_id}) -> {page} ... ", end="", flush=True)
    ok, msg = fetch_and_save(actual_id, page, char_hint=name)
    print("OK —", msg if ok else f"FAIL: {msg}")
    time.sleep(0.8)
