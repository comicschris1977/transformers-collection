import sys; sys.path.insert(0, r"C:\Projects\Transformers\tools")
import db; db.init_db()

kos = [f for f in db.list_figures() if f["line"] and f["line"].strip().upper() == "KO"]
print(f"KO figures: {len(kos)}\n")
for f in sorted(kos, key=lambda x: x["name"]):
    img = f["image_url"] or "none"
    print(f"  {f['id']:>4}  {f['name']:<30} | img: {img}")
