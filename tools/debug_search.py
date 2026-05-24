import re, gzip, urllib.parse, urllib.request, http.cookiejar, json, time

# Use a proper cookie jar + opener to simulate a real browser session
cj = http.cookiejar.CookieJar()
opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(cj))

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
    "Accept-Language": "en-US,en;q=0.9",
    "Accept-Encoding": "gzip, deflate, br",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
    "Sec-Fetch-Dest": "document",
    "Sec-Fetch-Mode": "navigate",
    "Sec-Fetch-Site": "none",
}

def fetch(url, referer=None):
    h = {**HEADERS}
    if referer:
        h["Referer"] = referer
    req = urllib.request.Request(url, headers=h)
    with opener.open(req, timeout=15) as r:
        data = r.read()
        enc = r.info().get("Content-Encoding", "")
        if "gzip" in enc:
            import gzip as gz
            data = gz.decompress(data)
        return data.decode("utf-8", errors="ignore")

# ── 1. Google Images ──────────────────────────────────────────────────────────
print("=== Google Images ===")
# First: seed cookies by visiting google.com
fetch("https://www.google.com/")
time.sleep(0.5)

# Now do image search
q = "transformers Optimus Prime Studio Series 86 toy official"
url = "https://www.google.com/search?" + urllib.parse.urlencode({
    "q": q, "tbm": "isch", "ijn": "0", "safe": "off"
})
html = fetch(url, referer="https://www.google.com/")
print(f"HTML length: {len(html)}")

# Google embeds image data in a JSON block
data_matches = re.findall(r'"(https://[^"]+\.(?:jpg|jpeg|png)(?:\?[^"]*)?)"', html)
google_imgs = [u for u in data_matches if "gstatic" not in u and "google" not in u.lower()]
print(f"External image URLs: {len(google_imgs)}")
for u in google_imgs[:8]:
    print(f"  {u[:110]}")

time.sleep(1)

# ── 2. Walmart ────────────────────────────────────────────────────────────────
print("\n=== Walmart ===")
url2 = "https://www.walmart.com/search?" + urllib.parse.urlencode({"q": "transformers optimus prime studio series 86"})
try:
    html2 = fetch(url2)
    print(f"HTML length: {len(html2)}")
    # Walmart embeds product data as JSON
    imgs = re.findall(r'"imageUrl"\s*:\s*"(https://i5\.walmartimages\.com/[^"]+)"', html2)
    imgs += re.findall(r'(https://i5\.walmartimages\.com/[^"\']+\.(?:jpg|png))', html2)
    unique = list(dict.fromkeys(imgs))
    print(f"Walmart images: {len(unique)}")
    for img in unique[:5]:
        print(f"  {img[:100]}")
except Exception as e:
    print(f"Error: {e}")
