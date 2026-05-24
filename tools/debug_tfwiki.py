"""
Debug TFWiki MediaWiki API to find toy-specific pages and images.
Tests various page title patterns to find the right one.
"""
import urllib.request, urllib.parse, json, re, time

PYTHON = "C:\\Users\\CJ\\AppData\\Local\\Programs\\Python\\Python312\\python.exe"
API = "https://tfwiki.net/api.php"

def api(params):
    url = API + "?" + urllib.parse.urlencode({**params, "format": "json"})
    req = urllib.request.Request(url, headers={"User-Agent": "TransformersCollectionBot/1.0"})
    with urllib.request.urlopen(req, timeout=15) as r:
        return json.loads(r.read())

def search(query, limit=5):
    """Full-text search on TFWiki."""
    d = api({"action": "query", "list": "search", "srsearch": query, "srlimit": limit, "srnamespace": 0})
    return [h["title"] for h in d.get("query", {}).get("search", [])]

def page_images(title):
    """Get all images on a page."""
    d = api({"action": "query", "titles": title, "prop": "images", "imlimit": 20})
    pages = d.get("query", {}).get("pages", {})
    for page in pages.values():
        return [img["title"] for img in page.get("images", [])]
    return []

def image_url(img_title):
    """Get the direct URL for an image title."""
    d = api({"action": "query", "titles": img_title, "prop": "imageinfo", "iiprop": "url"})
    pages = d.get("query", {}).get("pages", {})
    for page in pages.values():
        info = page.get("imageinfo", [])
        if info:
            return info[0].get("url")
    return None

def best_toy_image(images):
    """Score images and return the best toy photo candidate."""
    scored = []
    for img in images:
        name = img.lower()
        # Skip icons, logos, nav elements
        if any(x in name for x in ["icon", "logo", "nav", "banner", "flag", "symbol", "body", "head"]):
            continue
        score = 0
        if any(x in name for x in ["toy", "figure", "robot", "alt", "vehicle", "box", "package"]):
            score += 3
        if any(ext in name for ext in [".jpg", ".jpeg", ".png"]):
            score += 1
        scored.append((score, img))
    scored.sort(reverse=True)
    return [img for _, img in scored] if scored else []

# ── Test cases ────────────────────────────────────────────────────────────────
tests = [
    ("Optimus Prime", "SS86",    "Studio Series 86"),
    ("Grimlock",      "SS86",    "Studio Series 86"),
    ("Soundwave",     "SS86",    "Studio Series 86"),
    ("Bumblebee",     "WFC",     "War for Cybertron"),
    ("Cyclonus",      "SS86",    "Studio Series 86"),
    ("Arcee",         "WFC",     "War for Cybertron"),
]

for name, line, line_full in tests:
    print(f"\n{'='*60}")
    print(f"{name} ({line} / {line_full})")

    # Try various search queries
    queries = [
        f"{name} {line_full} toy",
        f"{name} {line_full}",
        f"{name} {line}",
        f"{name} toy",
    ]

    all_results = []
    for q in queries[:2]:
        results = search(q)
        print(f"  Search '{q}': {results[:3]}")
        all_results.extend(results)
        time.sleep(0.3)

    # Try the most relevant result
    if all_results:
        page = all_results[0]
        imgs = page_images(page)
        print(f"  Page '{page}' has {len(imgs)} images")
        candidates = best_toy_image(imgs)
        print(f"  Top candidates: {candidates[:3]}")
        if candidates:
            url = image_url(candidates[0])
            print(f"  Best image URL: {url}")

    time.sleep(0.5)
