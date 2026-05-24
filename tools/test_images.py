import sys, time
sys.path.insert(0, r"C:\Projects\Transformers\tools")
import fetch_images as fi
from pathlib import Path

fi.IMAGES_DIR.mkdir(parents=True, exist_ok=True)

tests = [
    (9001, "Alpha Trion",  "AotP"),
    (9002, "Optimus Prime","SS86"),
    (9003, "Grimlock",     "SS86"),
    (9004, "Bumblebee",    "WFC"),
    (9005, "Cyclonus",     "SS86"),
    (9006, "Soundwave",    "Legacy"),
    (9007, "Hot Rod",      "SS86"),
]

for fid, name, line in tests:
    result = fi.fetch_figure(fid, name, line)
    dest = fi.IMAGES_DIR / f"{fid}.jpg"
    size = dest.stat().st_size // 1024 if result and dest.exists() else 0
    status = f"OK {size}KB" if result else "not found"
    print(f"{name} ({line}): {status}")
    if result:
        dest.unlink()   # clean up test files
