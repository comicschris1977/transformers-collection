"""
CLI for managing the Transformers collection. Outputs JSON.

Usage:
  collection.py list [--status owned|want|preordered|ordered] [--line LINE]
                     [--combiner COMBINER] [--wrecker] [--min-rank N] [--max-rank N]
  collection.py search QUERY
  collection.py show ID
  collection.py add --name NAME [--line LINE] [--status STATUS] [--rank N]
                    [--retailer RETAILER] [--notes NOTES] [--combiner COMBINER]
                    [--wrecker]
  collection.py edit ID [--name NAME] [--line LINE] [--status STATUS] [--rank N]
                        [--retailer RETAILER] [--notes NOTES] [--combiner COMBINER]
                        [--wrecker true|false]
  collection.py delete ID
  collection.py stats
"""

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import db


def out(data):
    print(json.dumps(data, indent=2, ensure_ascii=False))


def cmd_list(args):
    wrecker = None
    if args.wrecker:
        wrecker = True
    rows = db.list_figures(
        status=args.status,
        line=args.line,
        combiner=args.combiner,
        wrecker=wrecker,
        min_rank=args.min_rank,
        max_rank=args.max_rank,
    )
    out({"count": len(rows), "figures": rows})


def cmd_search(args):
    rows = db.search_figures(args.query)
    out({"count": len(rows), "figures": rows})


def cmd_show(args):
    fig = db.get_figure(args.id)
    if not fig:
        out({"error": f"No figure with id {args.id}"})
        sys.exit(1)
    out(fig)


def cmd_add(args):
    is_wrecker = args.wrecker or False
    fid = db.add_figure(
        name=args.name,
        line=args.line,
        status=args.status or "want",
        rank=args.rank,
        retailer=args.retailer,
        notes=args.notes,
        combiner=args.combiner,
        is_wrecker=is_wrecker,
    )
    out({"added": fid, "figure": db.get_figure(fid)})


def cmd_edit(args):
    kwargs = {}
    if args.name:
        kwargs["name"] = args.name
    if args.line:
        kwargs["line"] = args.line
    if args.status:
        kwargs["status"] = args.status
    if args.rank is not None:
        kwargs["rank"] = args.rank
    if args.retailer:
        kwargs["retailer"] = args.retailer
    if args.notes:
        kwargs["notes"] = args.notes
    if args.combiner:
        kwargs["combiner"] = args.combiner
    if args.wrecker is not None:
        kwargs["is_wrecker"] = args.wrecker.lower() in ("true", "1", "yes")

    ok = db.edit_figure(args.id, **kwargs)
    if not ok:
        out({"error": f"No figure with id {args.id}"})
        sys.exit(1)
    out({"updated": args.id, "figure": db.get_figure(args.id)})


def cmd_delete(args):
    ok = db.delete_figure(args.id)
    if not ok:
        out({"error": f"No figure with id {args.id}"})
        sys.exit(1)
    out({"deleted": args.id})


def cmd_stats(args):
    out(db.stats())


def main():
    db.init_db()

    p = argparse.ArgumentParser()
    sub = p.add_subparsers(dest="cmd")

    # list
    pl = sub.add_parser("list")
    pl.add_argument("--status")
    pl.add_argument("--line")
    pl.add_argument("--combiner")
    pl.add_argument("--wrecker", action="store_true")
    pl.add_argument("--min-rank", type=int, dest="min_rank")
    pl.add_argument("--max-rank", type=int, dest="max_rank")

    # search
    ps = sub.add_parser("search")
    ps.add_argument("query")

    # show
    psh = sub.add_parser("show")
    psh.add_argument("id", type=int)

    # add
    pa = sub.add_parser("add")
    pa.add_argument("--name", required=True)
    pa.add_argument("--line")
    pa.add_argument("--status")
    pa.add_argument("--rank", type=int)
    pa.add_argument("--retailer")
    pa.add_argument("--notes")
    pa.add_argument("--combiner")
    pa.add_argument("--wrecker", action="store_true")

    # edit
    pe = sub.add_parser("edit")
    pe.add_argument("id", type=int)
    pe.add_argument("--name")
    pe.add_argument("--line")
    pe.add_argument("--status")
    pe.add_argument("--rank", type=int)
    pe.add_argument("--retailer")
    pe.add_argument("--notes")
    pe.add_argument("--combiner")
    pe.add_argument("--wrecker")

    # delete
    pd = sub.add_parser("delete")
    pd.add_argument("id", type=int)

    # stats
    sub.add_parser("stats")

    args = p.parse_args()
    dispatch = {
        "list": cmd_list,
        "search": cmd_search,
        "show": cmd_show,
        "add": cmd_add,
        "edit": cmd_edit,
        "delete": cmd_delete,
        "stats": cmd_stats,
    }
    if args.cmd not in dispatch:
        p.print_help()
        sys.exit(1)
    dispatch[args.cmd](args)


if __name__ == "__main__":
    main()
