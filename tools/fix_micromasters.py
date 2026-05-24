"""Download the correct two-pack images for all Micromaster pairs."""
import sys, urllib.request
from pathlib import Path

sys.path.insert(0, r"C:\Projects\Transformers\tools")
import db; db.init_db()

IMAGES_DIR = Path(r"C:\Projects\Transformers\docs\images")
BASE = "https://www.actionfigure411.com/transformers/images"
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
    "Referer":    "https://www.actionfigure411.com/",
}

def download(url, dest):
    req = urllib.request.Request(url, headers=HEADERS)
    with urllib.request.urlopen(req, timeout=15) as r:
        data = r.read()
    if len(data) < 5000:
        return False
    dest.write_bytes(data)
    return True

# Two-pack slug → list of figure names in DB that share this image
PACKS = {
    "trip-up-daddy-o-4401":    ["Trip-Up", "Daddy-O"],
    "bombshock-growl-4402":    ["Bombshock", "Growl"],
    "red-heat-stakeout-5360":  ["Red Heat", "Stakeout"],
}

# Build name→id lookup from DB
name_to_id = {f["name"]: f["id"] for f in db.list_figures()}

for slug, names in PACKS.items():
    url = f"{BASE}/{slug}.jpg"
    print(f"\n{slug}")
    print(f"  URL: {url}")

    # Download image once
    tmp = IMAGES_DIR / "_tmp_micro.jpg"
    try:
        ok = download(url, tmp)
    except Exception as e:
        print(f"  ERROR: {e}")
        continue

    if not ok:
        print("  Download failed (too small)")
        continue

    size = tmp.stat().st_size // 1024
    print(f"  Downloaded: {size}KB")

    # Copy to each figure's image slot
    for name in names:
        fid = name_to_id.get(name)
        if not fid:
            print(f"  '{name}' not found in DB")
            continue
        dest = IMAGES_DIR / f"{fid}.jpg"
        dest.write_bytes(tmp.read_bytes())
        db.set_image_url(fid, f"images/{fid}.jpg")
        print(f"  Saved for {name} (id {fid})")

# Clean up tmp
tmp_path = IMAGES_DIR / "_tmp_micro.jpg"
if tmp_path.exists():
    tmp_path.unlink()

print("\nDone.")
