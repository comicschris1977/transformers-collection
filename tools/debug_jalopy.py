import urllib.request, urllib.parse, json, sys
sys.path.insert(0, r"C:\Projects\Transformers\tools")
import fetch_images as fi

API = "https://tfwiki.net/api.php"

def api(params):
    url = API + "?" + urllib.parse.urlencode({**params, "format": "json"})
    req = urllib.request.Request(url, headers={"User-Agent": "TransformersCollectionBot/1.0"})
    with urllib.request.urlopen(req, timeout=20) as r:
        return json.loads(r.read())

# Get all images on the Jalopy main page
d = api({"action": "parse", "page": "Jalopy", "prop": "images"})
imgs = d.get("parse", {}).get("images", [])
print("Images on Jalopy page:")
for img in imgs:
    print(" ", img)

# Also get the wikitext to find the toy image
print()
d2 = api({"action": "parse", "page": "Jalopy", "prop": "wikitext"})
wt = d2.get("parse", {}).get("wikitext", {}).get("*", "")
files = fi.extract_files(wt)
print("File refs in wikitext:")
for f in files:
    print(" ", f)
    url = fi.get_image_url(f)
    if url:
        print("   ->", url)
