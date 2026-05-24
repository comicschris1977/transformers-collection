import sys; sys.path.insert(0, r"C:\Projects\Transformers\tools")
import db; db.init_db()

waits = [f for f in db.list_figures() if f["line"] and "wait" in f["line"].lower()]
no_img = [f for f in waits if not f["image_url"] or f["image_url"].startswith("http")]
has_img = [f for f in waits if f["image_url"] and not f["image_url"].startswith("http")]

print(f"Wait figures: {len(waits)} total, {len(no_img)} missing image, {len(has_img)} already have one\n")

print("Missing images:")
for f in no_img:
    print(f"  {f['id']:>4}  {f['name']:<30} | {f['line']}")

print("\nLine values used:")
for l in sorted(set(f["line"] for f in waits)):
    print(f"  {l}")
