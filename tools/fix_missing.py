import urllib.request, sys, sqlite3
sys.path.insert(0, r"C:\Projects\Transformers\tools")
import db; db.init_db()

# 1. Download Wheeljack Origins image directly from TFWiki
url = "https://tfwiki.net/mediawiki/images2/thumb/6/68/TF-Legacy-United-Origins-Wheeljack.jpg/300px-TF-Legacy-United-Origins-Wheeljack.jpg"
dest = r"C:\Projects\Transformers\docs\images\728.jpg"
req = urllib.request.Request(url, headers={
    "User-Agent": "TransformersCollectionBot/1.0",
    "Referer": "https://tfwiki.net/",
})
with urllib.request.urlopen(req, timeout=15) as r:
    data = r.read()
with open(dest, "wb") as f:
    f.write(data)
print(f"Downloaded Wheeljack Origins: {len(data)//1024}KB")
db.set_image_url(728, "images/728.jpg")
print("Set image_url for Wheeljack Origins (id 728)")

# 2. Fix Weirdwolf spelling in DB
conn = sqlite3.connect(r"C:\Projects\Transformers\collection.db")
conn.execute("UPDATE figures SET name='Weirdwolf' WHERE name='Wierdwolf'")
conn.commit()
conn.close()
print("Fixed Weirdwolf spelling in DB")
