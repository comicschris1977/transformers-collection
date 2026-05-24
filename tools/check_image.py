import sys, struct
sys.path.insert(0, r"C:\Projects\Transformers\tools")
import fetch_images as fi

# Check what Amazon actually returned for these IDs
import re, gzip, urllib.request

def first_amazon_urls(query, n=3):
    url = "https://www.amazon.com/s?" + __import__("urllib.parse", fromlist=["urlencode"]).urlencode({"k": query})
    req = urllib.request.Request(url, headers=fi.HEADERS)
    with urllib.request.urlopen(req, timeout=20) as r:
        data = r.read()
        if r.info().get("Content-Encoding") == "gzip":
            data = gzip.decompress(data)
        html = data.decode("utf-8", errors="ignore")
    raw = re.findall(r"https://m\.media-amazon\.com/images/I/([A-Za-z0-9%+_-]+)\._[^\"']+\.(?:jpg|png)", html)
    seen, out = set(), []
    for img_id in raw:
        if img_id not in seen:
            seen.add(img_id)
            out.append(f"https://m.media-amazon.com/images/I/{img_id}._AC_SL800_.jpg")
        if len(out) >= n:
            break
    return out

for name, line in [("Optimus Prime", "SS86"), ("Grimlock", "SS86"), ("Cyclonus", "SS86")]:
    q = fi.build_queries(name, line)[0]
    urls = first_amazon_urls(q)
    print(f"\n{name} ({line}) query: {q}")
    for u in urls:
        print(f"  {u}")
