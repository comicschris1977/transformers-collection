"""
Sync the local DB with the Google Sheet.

Steps:
  1. Pull fresh CSV from Google Sheets (reuses fetch_sheet logic)
  2. Diff sheet rows against existing DB rows (matched by name+line, case-insensitive)
  3. INSERT new figures
  4. UPDATE figures where any tracked field changed
  5. Report (do NOT auto-delete) figures present in DB but missing from sheet
  6. Fetch images for any newly added figures
  7. Rebuild the static site

Run:
  python tools/sync_sheet.py            -- normal sync
  python tools/sync_sheet.py --dry-run  -- show diffs but make no changes
  python tools/sync_sheet.py --no-images -- skip image fetch step
"""

import csv
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(Path(__file__).parent))

import db
import fetch_sheet
import import_csv as imp
import fetch_images
import build_site

CSV_PATH = ROOT / "collection_raw.csv"

# Fields we sync from the sheet → DB. image_url is intentionally excluded.
SYNC_FIELDS = ("name", "line", "status", "rank", "retailer", "notes", "combiner", "is_wrecker")


def norm_key(name: str, line) -> tuple:
    """Stable matching key for sheet-row ↔ db-row pairing."""
    return ((name or "").strip().lower(), ((line or "") or "").strip().lower())


def normalize_for_compare(value):
    """Treat None and empty string as equal; lowercase nothing here (we want
    real changes like capitalisation fixes to flow through)."""
    if value is None:
        return ""
    if isinstance(value, bool):
        return bool(value)
    return value


def diff_fields(sheet_row: dict, db_row: dict) -> dict:
    """Return {field: new_value} for every tracked field that differs."""
    changes = {}
    for field in SYNC_FIELDS:
        new = normalize_for_compare(sheet_row.get(field))
        old = normalize_for_compare(db_row.get(field))
        if new != old:
            changes[field] = sheet_row.get(field)
    return changes


def load_sheet_rows() -> list:
    """Read collection_raw.csv and parse into figure dicts (skipping blanks)."""
    rows = []
    with open(CSV_PATH, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for csv_row in reader:
            parsed = imp.parse_row(csv_row)
            if parsed is None:
                continue
            rows.append(parsed)
    return rows


def fetch_fresh_csv():
    """Pull latest sheet via OAuth and save to collection_raw.csv."""
    print("Authenticating with Google Sheets...")
    creds = fetch_sheet.get_credentials()
    print("Fetching sheet data...")
    rows = fetch_sheet.fetch_sheet(creds)
    if not rows:
        print("ERROR: No rows returned from sheet.")
        sys.exit(1)
    fetch_sheet.save_csv(rows)


def main():
    dry_run    = "--dry-run"   in sys.argv
    no_images  = "--no-images" in sys.argv

    db.init_db()

    # 1. Pull the latest sheet
    fetch_fresh_csv()

    # 2. Load sheet + DB into matching dicts
    sheet_rows = load_sheet_rows()
    db_rows    = db.list_figures()

    sheet_by_key = {}
    sheet_dupes  = []
    for r in sheet_rows:
        key = norm_key(r["name"], r["line"])
        if key in sheet_by_key:
            sheet_dupes.append(r)
        else:
            sheet_by_key[key] = r

    db_by_key = {norm_key(r["name"], r["line"]): r for r in db_rows}

    # 3. Classify — first pass: exact (name, line) match
    new_rows     = []
    changed_rows = []  # (db_row, sheet_row, changes_dict)
    unchanged    = 0
    missing_from_sheet = []

    for key, sheet_row in sheet_by_key.items():
        db_row = db_by_key.get(key)
        if db_row is None:
            new_rows.append(sheet_row)
            continue
        changes = diff_fields(sheet_row, db_row)
        if changes:
            changed_rows.append((db_row, sheet_row, changes))
        else:
            unchanged += 1

    for key, db_row in db_by_key.items():
        if key not in sheet_by_key:
            missing_from_sheet.append(db_row)

    # 3b. Rename detection — name-only match between "new" sheet rows and
    # "missing" DB rows. Only treat as rename when the name is unique on
    # both sides (avoid clobbering duplicates like the user's two Bumblebees).
    def _name_lower(s):
        return (s or "").strip().lower()

    new_by_name     = {}
    missing_by_name = {}
    for r in new_rows:
        new_by_name.setdefault(_name_lower(r["name"]), []).append(r)
    for r in missing_from_sheet:
        missing_by_name.setdefault(_name_lower(r["name"]), []).append(r)

    renamed_rows = []  # (db_row, sheet_row, changes_dict)
    for name_lc, sheet_candidates in list(new_by_name.items()):
        db_candidates = missing_by_name.get(name_lc, [])
        if len(sheet_candidates) == 1 and len(db_candidates) == 1:
            sheet_row = sheet_candidates[0]
            db_row    = db_candidates[0]
            changes   = diff_fields(sheet_row, db_row)
            renamed_rows.append((db_row, sheet_row, changes))
            new_rows.remove(sheet_row)
            missing_from_sheet.remove(db_row)

    # 4. Report
    print("\n" + "=" * 60)
    print("SYNC REPORT")
    print("=" * 60)
    print(f"Sheet rows:      {len(sheet_rows)}")
    print(f"DB rows:         {len(db_rows)}")
    print(f"Unchanged:       {unchanged}")
    print(f"New (to add):    {len(new_rows)}")
    print(f"Changed:         {len(changed_rows)}")
    print(f"Renamed (line):  {len(renamed_rows)}")
    print(f"In DB, not sheet: {len(missing_from_sheet)}")
    if sheet_dupes:
        print(f"Duplicate sheet keys (skipped after first): {len(sheet_dupes)}")
    print()

    if new_rows:
        print("--- NEW FIGURES ---")
        for r in new_rows:
            print(f"  + {r['name']} [{r['line'] or '?'}]  status={r['status']}  rank={r['rank']}")
        print()

    if renamed_rows:
        print("--- RENAMED (line change, keeps image) ---")
        for db_row, _sheet_row, changes in renamed_rows:
            label = f"{db_row['name']} (id {db_row['id']})"
            print(f"  ~ {label}")
            for field, new_val in changes.items():
                old_val = db_row.get(field)
                print(f"      {field}: {old_val!r} -> {new_val!r}")
        print()

    if changed_rows:
        print("--- CHANGED FIGURES ---")
        for db_row, _sheet_row, changes in changed_rows:
            label = f"{db_row['name']} [{db_row['line'] or '?'}] (id {db_row['id']})"
            print(f"  ~ {label}")
            for field, new_val in changes.items():
                old_val = db_row.get(field)
                print(f"      {field}: {old_val!r} -> {new_val!r}")
        print()

    if missing_from_sheet:
        print("--- IN DB BUT NOT IN SHEET (not auto-deleted) ---")
        for db_row in missing_from_sheet:
            print(f"  ? {db_row['name']} [{db_row['line'] or '?'}] (id {db_row['id']})")
        print()

    if dry_run:
        print("Dry run — no changes applied.")
        return

    if not new_rows and not changed_rows and not renamed_rows:
        print("Nothing to sync.")
        return

    # 5. Apply changes
    print("Applying changes...")
    new_ids = []
    for r in new_rows:
        new_id = db.add_figure(
            name=r["name"], line=r["line"], status=r["status"], rank=r["rank"],
            retailer=r["retailer"], notes=r["notes"], combiner=r["combiner"],
            is_wrecker=r["is_wrecker"],
        )
        new_ids.append((new_id, r["name"], r["line"]))

    def _apply(db_row, changes):
        clears  = [f for f, v in changes.items() if v is None]
        setters = {f: v for f, v in changes.items() if v is not None}
        db.edit_figure(db_row["id"], clear_fields=clears or None, **setters)

    for db_row, _sheet_row, changes in changed_rows:
        _apply(db_row, changes)
    for db_row, _sheet_row, changes in renamed_rows:
        _apply(db_row, changes)

    print(f"  Added {len(new_ids)}, updated {len(changed_rows)}, renamed {len(renamed_rows)}.")

    # 6. Fetch images for new figures
    if new_ids and not no_images:
        print(f"\nFetching images for {len(new_ids)} new figure(s)...")
        fetch_images.IMAGES_DIR.mkdir(parents=True, exist_ok=True)
        for fid, name, line in new_ids:
            print(f"  [{name}] ", end="", flush=True)
            try:
                rel = fetch_images.fetch_figure(fid, name, line)
                if rel:
                    db.set_image_url(fid, rel)
                    print("OK")
                else:
                    print("not found")
            except Exception as e:
                print(f"ERROR: {e}")

    # 7. Rebuild site
    print("\nRebuilding site...")
    build_site.build()

    # 8. Quick TFWiki link audit for any newly-added characters. Use
    #    audit_links's helpers directly so we only check the new names
    #    (full audit is `$PYTHON tools/audit_links.py`).
    if new_ids:
        print("\nChecking TFWiki links for new figures...")
        import audit_links
        any_dead = False
        for fid, name, _line in new_ids:
            url = __import__("tfwiki_links").tfwiki_url(name)
            status = audit_links._head(url)
            if status != 200:
                any_dead = True
                print(f"  DEAD ({status})  {name}  ->  {url}")
                suggestion = audit_links._suggest_override(name)
                if suggestion:
                    print(f"            add to tfwiki_links.py:  '{name}': '{suggestion}',")
        if not any_dead:
            print("  all new characters resolve cleanly.")

    print("\nDone. Review changes, then commit & push when ready.")


if __name__ == "__main__":
    main()
