"""
Audit every figure's TFWiki link.  Reports any 404s.

When the DB has new characters whose default URL doesn't resolve, you need to
add an override entry to tools/tfwiki_links.py and re-run.

For each dead link, this tool also probes TFWiki for likely alternatives and
suggests a one-line override snippet you can paste in.

Usage:
  $PYTHON tools/audit_links.py            # check everything
  $PYTHON tools/audit_links.py --quiet    # one-line per dead link
  $PYTHON tools/audit_links.py NAME       # check a single name

Exit code: 0 if all links resolve, 1 if any are dead (so sync_sheet can
chain it).
"""
import json
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import db
import tfwiki_links

API = "https://tfwiki.net/api.php"
HDR = {"User-Agent": "TransformersCollectionBot/1.0"}


def _head(url: str):
    """Return HTTP status code for a URL, following redirects."""
    try:
        req = urllib.request.Request(url, method="HEAD", headers=HDR)
        with urllib.request.urlopen(req, timeout=15) as r:
            return r.status
    except urllib.error.HTTPError as e:
        return e.code
    except Exception as e:
        return f"err:{type(e).__name__}"


def _api(params: dict) -> dict:
    url = API + "?" + urllib.parse.urlencode({**params, "format": "json"})
    req = urllib.request.Request(url, headers=HDR)
    with urllib.request.urlopen(req, timeout=20) as r:
        return json.loads(r.read())


def _page_exists(page: str) -> bool:
    try:
        d = _api({"action": "query", "titles": page})
        for p in d.get("query", {}).get("pages", {}).values():
            if "missing" not in p:
                return True
    except Exception:
        pass
    return False


def _suggest_override(name: str) -> str:
    """Probe TFWiki for plausible page names; return the first one that exists."""
    clean = tfwiki_links._strip_continuity(name)
    titled = tfwiki_links._title_case(clean)
    base = titled.replace(" ", "_")
    candidates = [
        base,                          # bare name
        base + "_(G1)",                # default
        base.replace("-", "_") + "_(G1)",
        base.replace(" ", "") + "_(G1)",
        base.split("_")[0] + "_(G1)",  # first word only (strip suffix)
        base + "_(G2)",
        base + "_(Animated)",
        base + "_(Cybertron)",
        base + "_(Prime)",
        base + "_(RID)",
        base + "_(Movie)",
    ]
    for c in candidates:
        time.sleep(0.2)
        if _page_exists(c):
            return c
    return ""


def _check_name(name: str, quiet: bool = False) -> bool:
    """Check one name. Return True if OK, False if dead."""
    url = tfwiki_links.tfwiki_url(name)
    status = _head(url)
    if status == 200:
        if not quiet:
            print(f"  OK    {name:<32}  {url}")
        return True
    print(f"  {status}  {name:<32}  {url}")
    if not quiet:
        suggestion = _suggest_override(name)
        if suggestion:
            print(f"        suggestion: '{name}': '{suggestion}',")
        else:
            print(f"        no obvious page found — search tfwiki.net manually")
    return False


def main():
    args = sys.argv[1:]
    quiet = "--quiet" in args
    positional = [a for a in args if not a.startswith("--")]

    if positional:
        ok = all(_check_name(name) for name in positional)
        sys.exit(0 if ok else 1)

    db.init_db()
    figs = db.list_figures()
    seen = set()
    deads = []
    for f in figs:
        name = f["name"]
        if name in seen:
            continue
        seen.add(name)
        url = tfwiki_links.tfwiki_url(name)
        status = _head(url)
        if status != 200:
            deads.append((name, f["line"], url, status))
            if quiet:
                print(f"  {status}  {name} [{f['line']}]  ->  {url}")

    if not deads:
        print(f"All {len(seen)} unique characters resolve (200 OK).")
        sys.exit(0)

    print(f"\n{len(deads)} dead link(s) out of {len(seen)} unique characters:\n")
    if not quiet:
        for name, line, url, status in deads:
            print(f"  {status}  {name} [{line}]")
            print(f"        {url}")
            suggestion = _suggest_override(name)
            if suggestion:
                print(f"        SUGGESTION: '{name}': '{suggestion}',")
            else:
                print(f"        (no obvious match — search tfwiki.net manually)")
            print()
    print(f"\nFix: add entries to TFWIKI_OVERRIDES in tools/tfwiki_links.py, then rerun.")
    sys.exit(1)


if __name__ == "__main__":
    main()
