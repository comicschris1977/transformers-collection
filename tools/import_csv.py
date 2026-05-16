"""
Import collection_raw.csv (exported from Google Sheet) into collection.db.
Run once after fetch_sheet.py.
"""

import csv
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import db

CSV_PATH = Path(__file__).parent.parent / "collection_raw.csv"

STATUS_MAP = {
    "yes": "owned",
    "want": "want",
    "pordered": "preordered",
    "ordered": "ordered",
}


def s(val):
    """Return stripped string or empty string for None."""
    return (val or "").strip()


def parse_row(row):
    own_raw = s(row.get("OWN"))
    status = STATUS_MAP.get(own_raw.lower(), "want")

    name = s(row.get("NAME"))
    if not name:
        return None

    line = s(row.get("LINE")) or None

    rank_raw = s(row.get("RANK"))
    try:
        rank = int(rank_raw) if rank_raw else None
    except ValueError:
        rank = None

    notes_raw = s(row.get("Notes/Ordered from")) or None

    # If the figure is preordered/ordered, treat Notes/Ordered from as retailer.
    # Keep as notes otherwise.
    retailer = None
    notes = notes_raw
    if status in ("preordered", "ordered") and notes_raw:
        retailer = notes_raw
        notes = None

    combiner = s(row.get("Combiner/SET")) or None
    is_wrecker = s(row.get("Wrecker?")).upper() == "Y"

    return dict(
        name=name,
        line=line,
        status=status,
        rank=rank,
        retailer=retailer,
        notes=notes,
        combiner=combiner,
        is_wrecker=is_wrecker,
    )


def main():
    if not CSV_PATH.exists():
        print(f"ERROR: {CSV_PATH} not found. Run fetch_sheet.py first.")
        sys.exit(1)

    db.init_db()

    imported = skipped = errors = 0
    with open(CSV_PATH, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for i, row in enumerate(reader, start=2):
            try:
                parsed = parse_row(row)
                if parsed is None:
                    skipped += 1
                    continue
                db.add_figure(**parsed)
                imported += 1
            except Exception as e:
                print(f"  Row {i} error: {e} — {dict(row)}")
                errors += 1

    print(f"\nImport complete: {imported} imported, {skipped} skipped, {errors} errors.")
    print(f"Database: {db.DB_PATH}")


if __name__ == "__main__":
    main()
