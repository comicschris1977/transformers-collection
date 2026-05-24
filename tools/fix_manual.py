"""
Manual image fixes for figures with non-standard TFWiki page structures.
"""
import sys, sqlite3, urllib.parse, urllib.request, json, time
sys.path.insert(0, r"C:\Projects\Transformers\tools")
import db, fetch_images as fi

db.init_db()
fi.IMAGES_DIR.mkdir(parents=True, exist_ok=True)

def api(params):
    url = "https://tfwiki.net/api.php?" + urllib.parse.urlencode({**params, "format": "json"})
    req = urllib.request.Request(url, headers={"User-Agent": "TransformersCollectionBot/1.0"})
    with urllib.request.urlopen(req, timeout=20) as r:
        return json.loads(r.read())

def get_best_image_from_page(page_title):
    """Get wikitext images from a specific page title."""
    d = api({"action": "parse", "page": page_title, "prop": "wikitext"})
    if "error" in d:
        print(f"  Page not found: {page_title}")
        return None
    wt = d.get("parse", {}).get("wikitext", {}).get("*", "")
    files = fi.extract_files(wt)
    candidates = fi.rank_files(files) or files[:5]
    for filename in candidates[:5]:
        url = fi.get_image_url(filename)
        time.sleep(0.3)
        if url:
            return url, filename
    return None

def thumb_to_full(thumb_url):
    """Convert TFWiki thumbnail URL to full-size URL."""
    # https://tfwiki.net/mediawiki/images2/thumb/c/c1/File.jpg/300px-File.jpg
    # ->  https://tfwiki.net/mediawiki/images2/c/c1/File.jpg
    import re
    m = re.match(r"(https://tfwiki\.net/mediawiki/images2)/thumb/([a-f0-9]/[a-f0-9]{2})/(.+\.(?:jpg|png))/\d+px-.+", thumb_url)
    if m:
        return f"{m.group(1)}/{m.group(2)}/{m.group(3)}"
    return thumb_url

conn = sqlite3.connect(r"C:\Projects\Transformers\collection.db")

# ── 1. Ironhide BD (id 582) — direct URL provided ────────────────────────────
print("[1] Ironhide BD")
thumb = "https://tfwiki.net/mediawiki/images2/thumb/c/c1/TF-SS-TFTM-BB-Ironhide.jpg/300px-TF-SS-TFTM-BB-Ironhide.jpg"
full = thumb_to_full(thumb)
print(f"  Full URL: {full}")
dest = fi.IMAGES_DIR / "582.jpg"
if fi.download(full, dest):
    db.set_image_url(582, "images/582.jpg")
    print(f"  OK — {dest.stat().st_size // 1024}KB")
else:
    print("  Failed — trying thumb URL")
    if fi.download(thumb, dest):
        db.set_image_url(582, "images/582.jpg")
        print(f"  OK (thumb) — {dest.stat().st_size // 1024}KB")

# ── 2. Roadtrap (id 657) — page: Roadtrap_(POTP) ─────────────────────────────
print("[2] Roadtrap")
result = get_best_image_from_page("Roadtrap_(POTP)")
if result:
    url, fname = result
    dest = fi.IMAGES_DIR / "657.jpg"
    if fi.download(url, dest):
        db.set_image_url(657, "images/657.jpg")
        print(f"  OK — {fname} ({dest.stat().st_size // 1024}KB)")
    else:
        print(f"  Download failed for {fname}")
else:
    print("  No image found")
time.sleep(0.5)

# ── 3. Bone Shaker (id 519) — page: Bone_Shaker ──────────────────────────────
print("[3] Bone Shaker")
# Fix name in DB while we're at it
conn.execute("UPDATE figures SET name='Bone Shaker' WHERE id=519")
conn.commit()
print("  Name fixed: 'Bone Shaker Hot Wheels' -> 'Bone Shaker'")
result = get_best_image_from_page("Bone_Shaker")
if result:
    url, fname = result
    dest = fi.IMAGES_DIR / "519.jpg"
    if fi.download(url, dest):
        db.set_image_url(519, "images/519.jpg")
        print(f"  OK — {fname} ({dest.stat().st_size // 1024}KB)")
    else:
        print(f"  Download failed for {fname}")
else:
    print("  No image found")
time.sleep(0.5)

# ── 4. Ironfist / Fisitron (id 579) — page: Ironfist_(G1) ────────────────────
print("[4] Ironfist")
conn.execute("UPDATE figures SET name='Ironfist' WHERE id=579")
conn.commit()
print("  Name fixed: 'Ironfist / Fisitron' -> 'Ironfist'")
result = get_best_image_from_page("Ironfist_(G1)")
if result:
    url, fname = result
    dest = fi.IMAGES_DIR / "579.jpg"
    if fi.download(url, dest):
        db.set_image_url(579, "images/579.jpg")
        print(f"  OK — {fname} ({dest.stat().st_size // 1024}KB)")
    else:
        print(f"  Download failed for {fname}")
else:
    print("  No image found")

conn.close()
print("\nDone.")
