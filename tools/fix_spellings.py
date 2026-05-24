import sqlite3, sys
sys.path.insert(0, r"C:\Projects\Transformers\tools")
import db; db.init_db()

fixes = [
    ("Beachcomer",   "Beachcomber"),
    ("Blugeon",      "Bludgeon"),
    ("Bubblebee",    "Bumblebee"),   # covers both SS86 and Devastation entries
    ("Rachet",       "Ratchet"),
    ("Ratrap",       "Rattrap"),
    ("Rukus",        "Ruckus"),
    ("Leige Maximo", "Liege Maximo"),
]

conn = sqlite3.connect(r"C:\Projects\Transformers\collection.db")
for wrong, right in fixes:
    cur = conn.execute("UPDATE figures SET name=? WHERE name=?", (right, wrong))
    if cur.rowcount:
        print(f"  {wrong} -> {right} ({cur.rowcount} row{'s' if cur.rowcount>1 else ''})")
    else:
        print(f"  {wrong}: not found (already fixed?)")
conn.commit()
conn.close()
print("Done.")
