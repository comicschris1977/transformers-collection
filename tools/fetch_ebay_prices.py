"""
Fetch eBay 90-day average sold price for each (non-placeholder) figure.

eBay deprecated their public Finding API for sold listings in 2023, so we
scrape eBay's sold-listings search page. Notes for 2026 markup:
  - eBay blocks direct requests with 403 unless we hit the homepage first
    to collect anti-bot cookies (jar pre-warm). We use http.cookiejar for that.
  - The new price element is <span class="...s-card__price">$X.XX</span>
    (the older "s-item__price" class is gone).
We parse those, trim outliers, store the result in the DB.

Usage:
  $PYTHON tools/fetch_ebay_prices.py             -- refresh ALL non-placeholder figures
  $PYTHON tools/fetch_ebay_prices.py NAME LINE   -- probe one (no DB write)
  $PYTHON tools/fetch_ebay_prices.py --stale 14  -- only refresh figures whose
                                                   ebay_updated_at is >14 days old
                                                   (or never set)
  $PYTHON tools/fetch_ebay_prices.py --limit 20  -- cap how many to fetch this run

Skips:
  - Lines starting with 'wait' or 'ko' (no real product to price)
  - Figures whose name starts with '*' (note-only entries)

Pacing: 1.5s sleep between requests. ~240 figures = ~6 minutes for a full pass.
"""
import datetime as dt
import http.cookiejar
import json
import random
import re
import statistics
import sys
import time
import urllib.parse
import urllib.request
import urllib.error
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import db

# ── line code -> eBay search-friendly expansion ────────────────────────────
LINE_TO_QUERY = {
    "SS":                   "Studio Series",
    "SS86":                 "Studio Series 86",
    "SS86 Buzzworthy":      "Studio Series 86 Buzzworthy",
    "SS86 repaint":         "Studio Series 86",
    "SS86 Repaint":         "Studio Series 86",
    "SS86 Reissue":         "Studio Series 86",
    "SS Bumblebee Movie":   "Studio Series Bumblebee Movie",
    "Studio Bumblebee":     "Studio Series Bumblebee Movie",
    "Core Bumblebee":       "Studio Series Bumblebee Core",
    "Core Bumblebee Movie": "Studio Series Bumblebee Core",
    "WFC":                  "War for Cybertron",
    "WFC: Siege":           "War for Cybertron Siege",
    "WFC Siege":            "War for Cybertron Siege",
    "WFC: Earthrise":       "War for Cybertron Earthrise",
    "WFC Earthrise":        "War for Cybertron Earthrise",
    "WFC: Kingdom":         "War for Cybertron Kingdom",
    "WFC Kingdom":          "War for Cybertron Kingdom",
    "Kingdom":              "War for Cybertron Kingdom",
    "AotP":                 "Age of the Primes",
    "Legacy":               "Legacy",
    "PotPrimes":            "Power of the Primes",
    "PotP":                 "Power of the Primes",
    "Power of the Primes":  "Power of the Primes",
    "Titans Return":        "Titans Return",
    "Combiner Wars":        "Combiner Wars",
    "Thrilling 30":         "Generations",
    "Generations":          "Generations",
    "Wreck N Rule":         "Wreckers",
    "Core":                 "Core Class",
    "Retro Headmasters":    "Retro Headmasters",
    "Retro Toy Version":    "Vintage G1",
    "Crossover":            "Crossovers",
    "Hotwheels":            "Hot Wheels",
    "Cyberverse":           "Cyberverse",
    "Beast Hunters":        "Prime Beast Hunters",
    "Devastation":          "Devastation",
    "Transformers One":     "Transformers One",
    "RiD":                  "Robots in Disguise",
    "SDCC version":         "SDCC",
}

BASE_URL = "https://www.ebay.com/sch/i.html"
HEADERS = {
    "User-Agent": ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                   "AppleWebKit/537.36 (KHTML, like Gecko) "
                   "Chrome/124.0.0.0 Safari/537.36"),
    "Accept": ("text/html,application/xhtml+xml,application/xml;q=0.9,"
               "image/avif,image/webp,image/apng,*/*;q=0.8"),
    "Accept-Language": "en-US,en;q=0.9",
    "Accept-Encoding": "identity",   # don't ask for gzip — keeps parsing simple
    "Cache-Control": "no-cache",
    "Pragma": "no-cache",
    "Sec-Ch-Ua": '"Chromium";v="124", "Google Chrome";v="124", "Not-A.Brand";v="99"',
    "Sec-Ch-Ua-Mobile": "?0",
    "Sec-Ch-Ua-Platform": '"Windows"',
    "Sec-Fetch-Dest": "document",
    "Sec-Fetch-Mode": "navigate",
    "Sec-Fetch-Site": "none",
    "Sec-Fetch-User": "?1",
    "Upgrade-Insecure-Requests": "1",
    "Referer": "https://www.ebay.com/",
}

# Tunables
PACING_SECONDS    = 3.0   # base sleep between requests
PACING_JITTER     = 1.5   # ±jitter so requests don't look mechanical
REWARM_EVERY      = 15    # re-fetch homepage every N requests (resets cookies)
MIN_PRICE         = 5.0   # sanity floor (no $0.99 dust)
MAX_PRICE         = 600.0 # sanity ceiling (no MISB grails skewing avg)
MIN_SAMPLES       = 2     # need this many hits to report an average
TRIM_PCT          = 0.10  # trim top/bottom 10% before averaging
RETRY_ON_EMPTY    = True  # if first attempt returns no data, re-warm + try once more


def _clean_name(name: str) -> str:
    """Strip '*<continuity>' notes from user-entered names."""
    return re.sub(r"\s*\*.*$", "", name).strip()


def is_placeholder(line) -> bool:
    if not line: return False
    return line.lower().startswith(("wait", "ko", "g1 ko"))


def build_query(name: str, line: str) -> str:
    """Construct an eBay search query string for (name, line)."""
    clean = _clean_name(name)
    line_q = LINE_TO_QUERY.get(line, line) if line else ""
    if line_q:
        return f"Transformers {line_q} {clean}"
    return f"Transformers {clean}"


_opener = None
def _build_opener():
    """Fresh session — new cookie jar, new homepage prime."""
    jar = http.cookiejar.CookieJar()
    op = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(jar))
    op.addheaders = list(HEADERS.items())
    try:
        op.open("https://www.ebay.com/", timeout=20).read()
    except Exception:
        pass
    return op

def _get_opener():
    """Build & warm up an eBay-friendly URL opener (cookies, homepage prime)."""
    global _opener
    if _opener is None:
        _opener = _build_opener()
    return _opener

def _rewarm():
    """Force a fresh session (called periodically to dodge rate-limit holdoff)."""
    global _opener
    _opener = _build_opener()


def fetch_sold_html(query: str) -> str:
    """Fetch eBay sold-listings page HTML for the query."""
    params = {
        "_nkw": query,
        "LH_Sold": "1",          # sold filter
        "LH_Complete": "1",      # completed (closes the deal)
        "_sop": "13",            # sort: ended recently
        "_ipg": "60",            # 60 results per page (enough sample)
    }
    url = BASE_URL + "?" + urllib.parse.urlencode(params)
    op = _get_opener()
    with op.open(url, timeout=30) as r:
        return r.read().decode("utf-8", errors="ignore")


# Match a single dollar price like "$24.99". Range listings ("$10.00 to $30.00")
# get split; we take the midpoint.
PRICE_RE = re.compile(r"\$([\d,]+(?:\.\d{2})?)")
# 2026 eBay price element. Class list looks like:
#   <span class="su-styled-text primary bold large-1 s-card__price">$24.99</span>
PRICE_SPAN_RE = re.compile(
    r'<span class="[^"]*\bs-card__price\b[^"]*"[^>]*>([^<]+)</span>',
    re.IGNORECASE,
)


def parse_prices(html: str) -> list[float]:
    """Extract prices from sold-listings page. Filter outliers."""
    out = []
    for block in PRICE_SPAN_RE.findall(html):
        nums = PRICE_RE.findall(block)
        if not nums:
            continue
        try:
            vals = [float(n.replace(",", "")) for n in nums]
            price = sum(vals) / len(vals)  # midpoint if range
        except ValueError:
            continue
        if MIN_PRICE <= price <= MAX_PRICE:
            out.append(price)
    return out


def average_trimmed(prices: list[float]) -> float | None:
    """Trim top/bottom TRIM_PCT, return mean. None if not enough samples."""
    if len(prices) < MIN_SAMPLES:
        return None
    prices = sorted(prices)
    n = len(prices)
    k = int(n * TRIM_PCT)
    trimmed = prices[k : n - k] if (n - 2 * k) >= MIN_SAMPLES else prices
    return statistics.mean(trimmed)


def fetch_one(name: str, line: str) -> tuple[float | None, int, str]:
    """Returns (avg_price, sold_count, query_used). None price if no usable data."""
    query = build_query(name, line)
    try:
        html = fetch_sold_html(query)
    except urllib.error.HTTPError as e:
        print(f"  HTTP {e.code} for query '{query}'")
        return None, 0, query
    except Exception as e:
        print(f"  ERR: {e}")
        return None, 0, query
    prices = parse_prices(html)
    avg = average_trimmed(prices)
    return avg, len(prices), query


def _set_price(fid: int, avg, count: int):
    """Write price data to the DB."""
    with db._conn() as con:
        con.execute(
            "UPDATE figures SET ebay_avg_price = ?, ebay_sold_count = ?, "
            "ebay_updated_at = date('now') WHERE id = ?",
            (avg, count, fid),
        )


def main():
    args = sys.argv[1:]
    stale_days = None
    limit = None
    only_missing = False
    positional = []
    i = 0
    while i < len(args):
        a = args[i]
        if a == "--stale":
            stale_days = int(args[i + 1]); i += 2
        elif a == "--limit":
            limit = int(args[i + 1]); i += 2
        elif a == "--only-missing":
            only_missing = True; i += 1
        else:
            positional.append(a); i += 1

    db.init_db()

    # Single-pair probe: NAME LINE
    if len(positional) == 2:
        name, line = positional
        avg, count, q = fetch_one(name, line)
        print(f"Query: {q}")
        print(f"Sold listings parsed: {count}")
        if avg is not None:
            print(f"Trimmed average: ${avg:.2f}")
        else:
            print("Not enough data.")
        return

    figs = db.list_figures()
    # Skip placeholder lines and note-only entries
    targets = [f for f in figs if not is_placeholder(f["line"])
               and not f["name"].startswith("*")]

    if only_missing:
        # Only figures with no price OR ebay_sold_count == 0
        targets = [f for f in targets
                   if not f.get("ebay_avg_price") or not f.get("ebay_sold_count")]

    if stale_days is not None:
        cutoff = dt.date.today() - dt.timedelta(days=stale_days)
        def _is_stale(f):
            ts = f.get("ebay_updated_at")
            if not ts: return True
            try:
                return dt.date.fromisoformat(ts) < cutoff
            except Exception:
                return True
        targets = [f for f in targets if _is_stale(f)]

    if limit:
        targets = targets[:limit]

    print(f"Refreshing eBay prices for {len(targets)} figure(s)...")
    print(f"Pacing: {PACING_SECONDS}s ±{PACING_JITTER}s, re-warm every {REWARM_EVERY}\n")
    ok = empty = err = 0
    for i, f in enumerate(targets, 1):
        name, line, fid = f["name"], f["line"] or "", f["id"]
        print(f"  [{i}/{len(targets)}] {name} [{line}] ... ", end="", flush=True)
        # Re-warm periodically to dodge eBay's rate-limit holdoff
        if i > 1 and (i - 1) % REWARM_EVERY == 0:
            print("(re-warming session) ", end="", flush=True)
            _rewarm()
            time.sleep(2.0)

        try:
            avg, count, _q = fetch_one(name, line)
            # Retry once on empty if RETRY_ON_EMPTY (might be transient block)
            if avg is None and count == 0 and RETRY_ON_EMPTY:
                _rewarm()
                time.sleep(2.5)
                avg, count, _q = fetch_one(name, line)

            if avg is not None:
                _set_price(fid, round(avg, 2), count)
                print(f"${avg:.2f} (n={count})")
                ok += 1
            else:
                _set_price(fid, None, count)
                print(f"no data (n={count})")
                empty += 1
        except Exception as e:
            print(f"ERR: {e}")
            err += 1

        # Jittered pacing
        sleep_for = PACING_SECONDS + random.uniform(-PACING_JITTER, PACING_JITTER)
        time.sleep(max(1.0, sleep_for))

    print(f"\nDone: {ok} priced, {empty} no-data, {err} errors")


if __name__ == "__main__":
    main()
