import sys; sys.path.insert(0, r"C:\Projects\Transformers\tools")
import db; db.init_db()

# Known WFC Siege Micromaster names (two-packs)
MICROMASTERS = {
    # Autobot patrols
    "Stakeout", "Small Foot",           # Rescue Patrol
    "Fixit", "Hubs",                    # Hot Rod Patrol
    "Roadhandler", "Swindler",          # Race Car Patrol
    "Flak", "Sidetrack",               # Battle Patrol
    "Mudslinger", "Highjump", "Tote", "Powertrain",  # Off Road Patrol
    "Whisper", "Stormcloud", "Rainmaker", "Visper",  # Air Strike Patrol
    "Direct Hit", "Power Run",
    # Decepticon patrols
    "Bombshock", "Growl",
    "Caliburst", "Lancequick",
    "Red Heat", "Stakeout",
    "Detour", "Blackjack",
    "Beastbox", "Ratbat",
    "Cannon", "Hammerhead",
    "Rung",                            # sometimes grouped
    "Wild Ride", "Mudflap",            # Road Assault Combiner
    "Rocketboy", "Scrounge",
    "Zetar", "Autobot Pinpointer",
    "Full-Barrel", "Overflow",
    "Topshot", "Flak",
}

all_figs = db.list_figures()
wfc = [f for f in all_figs if f["line"] and "wfc" in f["line"].lower()]

# Identify likely micromasters
micros = [f for f in wfc if f["name"] in MICROMASTERS]
others = [f for f in wfc if f["name"] not in MICROMASTERS]

print(f"WFC figures total: {len(wfc)}")
print(f"  Recognized Micromasters: {len(micros)}")
print(f"  Others (Deluxe/Voyager/etc): {len(others)}")

print("\nAll WFC figures (check for Micromasters):")
for f in sorted(wfc, key=lambda x: x["name"]):
    tag = " << MICROMASTER?" if f["name"] in MICROMASTERS else ""
    print(f"  {f['name']}{tag}")
