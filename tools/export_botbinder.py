"""
Export to Bot Binder's CSV import format.

REAL Bot Binder catalog format (learned from user's manual entries):
  Character Name, Line, Subline, Size Class, Era/Universe, Faction,
  Condition, Paid Price, Current Value

Example rows the user added manually:
  Soundwave, Studio Series, 86 Movie, Leader, Sunbow Cartoon,
    Decepticon, Opened Complete, , 85
  Wheeljack, Studio Series, Mainline, Deluxe, Bumblebee (2018),
    Autobot, Opened Complete, , 30

Key vocab corrections from prior attempt:
- G1 era is "Sunbow Cartoon", not "G1 toon"
- SS86 = Line "Studio Series" + Subline "86 Movie"
- SS Bumblebee Movie = Line "Studio Series" + Subline "Mainline"
- Faction is required per row

Usage:
  python tools/export_botbinder.py --status owned       (default)
  python tools/export_botbinder.py --status want
  python tools/export_botbinder.py --status preordered,ordered
"""
import csv
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import db

# ── Internal line code -> (Bot Binder Line, Subline) ─────────────────────
LINE_MAP = {
    # Studio Series family
    "SS":                   ("Studio Series",     "Mainline"),
    "SS86":                 ("Studio Series",     "86 Movie"),
    "SS86 Buzzworthy":      ("Studio Series",     "86 Movie"),
    "SS86 repaint":         ("Studio Series",     "86 Movie"),
    "SS86 Repaint":         ("Studio Series",     "86 Movie"),
    "SS86 Reissue":         ("Studio Series",     "86 Movie"),
    "SS Bumblebee Movie":   ("Studio Series",     "Mainline"),
    "Studio Bumblebee":     ("Studio Series",     "Mainline"),
    "Core Bumblebee":       ("Studio Series",     "Mainline"),
    "Core Bumblebee Movie": ("Studio Series",     "Mainline"),
    "Gamerverse":           ("Studio Series",     "Gamer Edition"),

    # War for Cybertron Trilogy
    "WFC":                  ("Generations",       "War for Cybertron"),
    "WFC: Siege":           ("Generations",       "WFC: Siege"),
    "WFC Siege":            ("Generations",       "WFC: Siege"),
    "WFC: Earthrise":       ("Generations",       "WFC: Earthrise"),
    "WFC Earthrise":        ("Generations",       "WFC: Earthrise"),
    "WFC: Kingdom":         ("Generations",       "WFC: Kingdom"),
    "WFC Kingdom":          ("Generations",       "WFC: Kingdom"),
    "Kingdom":              ("Generations",       "WFC: Kingdom"),

    # Modern Generations sublines (now specific, not rolled-up)
    "AotP":                 ("Generations",       "Age of the Primes"),
    "Legacy":               ("Generations",       "Legacy"),
    "PotPrimes":            ("Generations",       "Power of the Primes"),
    "PotP":                 ("Generations",       "Power of the Primes"),
    "Power of the Primes":  ("Generations",       "Power of the Primes"),
    "Titans Return":        ("Generations",       "Titans Return"),
    "Combiner Wars":        ("Generations",       "Combiner Wars"),
    "Thrilling 30":         ("Generations",       "Thrilling 30"),
    "Generations":          ("Generations",       "Generations"),
    "Wreck N Rule":         ("Generations",       "Wreckers"),
    "Core":                 ("Generations",       "Core Class"),
    "Devastation":          ("Generations",       "Devastation"),
    "SDCC version":         ("Generations",       "SDCC Exclusive"),

    # Reissue
    "Retro Headmasters":    ("Generations",       "Retro Headmasters"),
    "Retro Toy Version":    ("Vintage G1",        "Walmart Retro"),

    # Crossovers
    "Crossover":            ("Collaborative",     "Crossover"),
    "Hotwheels":            ("Collaborative",     "Hot Wheels"),

    # Other continuities
    "Cyberverse":           ("Cyberverse",        "Mainline"),
    "Beast Hunters":        ("Prime",             "Beast Hunters"),
    "RiD":                  ("Robots in Disguise","Mainline"),
    "Transformers One":     ("Transformers One",  "Mainline"),

    # Placeholders
    "Wait":                 ("",                  ""),
    "KO":                   ("",                  ""),
    "G1 KO":                ("",                  ""),
}

# ── Internal line code -> Era/Universe ───────────────────────────────────
ERA_MAP = {
    # SS86 era is the Sunbow cartoon (original 1984-87 animation)
    "SS86":                 "Sunbow Cartoon",
    "SS86 Buzzworthy":      "Sunbow Cartoon",
    "SS86 repaint":         "Sunbow Cartoon",
    "SS86 Repaint":         "Sunbow Cartoon",
    "SS86 Reissue":         "Sunbow Cartoon",

    # BB Movie line is the 2018 film
    "SS":                   "Sunbow Cartoon",       # default SS = G1
    "SS Bumblebee Movie":   "Bumblebee (2018)",
    "Studio Bumblebee":     "Bumblebee (2018)",
    "Core Bumblebee":       "Bumblebee (2018)",
    "Core Bumblebee Movie": "Bumblebee (2018)",
    "Gamerverse":           "War for Cybertron (game)",

    # WFC trilogy (Netflix series continuity)
    "WFC":                  "War for Cybertron Trilogy",
    "WFC: Siege":           "War for Cybertron Trilogy",
    "WFC Siege":            "War for Cybertron Trilogy",
    "WFC: Earthrise":       "War for Cybertron Trilogy",
    "WFC Earthrise":        "War for Cybertron Trilogy",
    "WFC: Kingdom":         "War for Cybertron Trilogy",
    "WFC Kingdom":          "War for Cybertron Trilogy",
    "Kingdom":              "War for Cybertron Trilogy",

    # Modern Generations sublines are G1-styled
    "AotP":                 "Sunbow Cartoon",
    "Legacy":               "Sunbow Cartoon",
    "PotPrimes":            "Sunbow Cartoon",
    "PotP":                 "Sunbow Cartoon",
    "Power of the Primes":  "Sunbow Cartoon",
    "Titans Return":        "Sunbow Cartoon",
    "Combiner Wars":        "Sunbow Cartoon",
    "Thrilling 30":         "Sunbow Cartoon",
    "Generations":          "Sunbow Cartoon",
    "Wreck N Rule":         "Sunbow Cartoon",
    "Core":                 "Sunbow Cartoon",
    "Devastation":          "Sunbow Cartoon",
    "SDCC version":         "Sunbow Cartoon",
    "Retro Headmasters":    "Sunbow Cartoon",
    "Retro Toy Version":    "Sunbow Cartoon",

    # Other continuities
    "Cyberverse":           "Cyberverse (2018)",
    "Beast Hunters":        "Prime (2010)",
    "RiD":                  "Robots in Disguise (2015)",
    "Transformers One":     "Transformers One (2024)",

    "Crossover":            "Crossover",
    "Hotwheels":            "Hot Wheels",

    # Placeholders
    "Wait":                 "Sunbow Cartoon",
    "KO":                   "Sunbow Cartoon",
    "G1 KO":                "Sunbow Cartoon",
}

# Per-character era overrides (mainly for crossovers)
ERA_OVERRIDES = {
    "agent knight":  "G.I. Joe",
    "ectotron":      "Ghostbusters",
    "mandalorian":   "Star Wars",
    "bone shaker":   "Hot Wheels",
    "gigawatt":      "Back to the Future",
}

# ── Size Class lookup (Deluxe default; overrides for specific (name, line)) ──
SIZE_OVERRIDES = {
    # SS86 Commander
    ("optimus prime", "ss86"):       "Commander",
    # SS86 Leader
    ("astrotrain", "ss86"):          "Leader",
    ("galvatron", "ss86"):           "Leader",
    ("grimlock", "ss86"):            "Leader",
    ("megatron", "ss86"):            "Leader",
    ("snarl", "ss86"):               "Leader",
    ("sludge", "ss86"):              "Leader",
    ("swoop", "ss86"):               "Leader",
    ("starscream", "ss86"):          "Leader",
    # SS86 Voyager
    ("blaster", "ss86"):             "Voyager",
    ("blurr", "ss86"):               "Voyager",
    ("hot rod", "ss86"):             "Voyager",
    ("ironhide", "ss86"):            "Voyager",
    ("ironhide bd", "ss86"):         "Voyager",
    ("perceptor", "ss86"):           "Legends, Deluxe",  # 3-pack: Perceptor (Deluxe) + Ratbat/Ramhorn (Legends)
    ("perceptor", "ss86 repaint"):   "Legends, Deluxe",
    ("ratchet", "ss86"):             "Voyager",
    ("scourge", "ss86"):             "Voyager",
    ("soundwave", "ss86"):           "Leader",  # per user's manual entry
    ("sweeps", "ss86"):              "Voyager",
    ("wreck gar", "ss86"):           "Voyager",
    ("hook", "ss86"):                "Voyager",
    ("long haul", "ss86"):           "Voyager",
    ("hound", "ss86"):               "Voyager",
    ("quintesson", "ss86"):          "Voyager",
    ("shockwave", "ss86"):           "Voyager",
    # Other SS
    ("shockwave", "core bumblebee movie"): "Voyager",
    ("optimus prime", "gamerverse"): "Voyager",
    # AotP Commander
    ("onslaught", "aotp"):           "Commander",
    ("silverbolt", "aotp"):          "Commander",
    # AotP Voyager (Primes)
    ("alchemist prime", "aotp"):     "Voyager",
    ("amalgamous prime", "aotp"):    "Voyager",
    ("liege maximo", "aotp"):        "Voyager",
    ("megatronus prime", "aotp"):    "Voyager",
    ("micronus prime", "aotp"):      "Voyager",
    ("nexus prime", "aotp"):         "Voyager",
    ("onyx prime", "aotp"):          "Voyager",
    ("prima prime", "aotp"):         "Voyager",
    ("quintus prime", "aotp"):       "Voyager",
    ("sentinel prime", "aotp"):      "Voyager",
    ("solus prime", "aotp"):         "Voyager",
    ("herald of unicron", "aotp"):   "Voyager",
    ("star optimus", "aotp"):        "Titan",
    # WFC big-class
    ("optimus prime", "wfc"):        "Voyager",
    ("megatron", "wfc"):             "Voyager",
    ("ultra magnus", "wfc"):         "Commander",
    # Legacy big-class
    ("bulkhead", "legacy"):          "Voyager",
    ("jhiaxus", "legacy"):           "Voyager",
    ("tarn", "legacy"):              "Voyager",
    ("motormaster", "legacy"):       "Commander",
    ("optimus prime", "legacy"):     "Voyager",
    ("wheeljack origins", "legacy"): "Voyager",
    # PotP
    ("hun-grrr", "power of the primes"): "Voyager",
    # TR
    ("octane", "titans return"):     "Voyager",
    # Cassettes (Legends class — small)
    ("buzzsaw", "ss86"):             "Legends",
    ("frenzy", "ss86"):              "Legends",
    ("laserbeak", "wfc"):            "Legends",
    ("laserbeak", "wfc: siege"):     "Legends",
    ("ravage", "core"):              "Legends",  # Core Cassette
    ("ratbat", "ss86"):              "Legends",
    ("ramhorn", "ss86"):             "Legends",
    ("steeljaw", "ss86"):            "Legends",
    ("rumble", "legacy"):            "Legends",
    ("eject", "wait"):               "Legends",
    ("rewind", "wait"):              "Legends",
    ("slugfest", "wait"):            "Legends",
    ("overkill", "wait"):            "Legends",
    # Non-figure
    ("matrix of leadership", "ss86"): "N/A",
}

# ── Faction lookup ───────────────────────────────────────────────────────
# G1 character allegiance. Most well-known. Default fallback = "Autobot"
# (more Autobots than Decepticons in user's collection roughly).
FACTION = {
    # ── AUTOBOTS ──
    # 1984 Cars
    "optimus prime": "Autobot", "bumblebee": "Autobot", "cliffjumper": "Autobot",
    "ironhide": "Autobot", "ironhide bd": "Autobot", "jazz": "Autobot",
    "ratchet": "Autobot", "wheeljack": "Autobot", "wheeljack origins": "Autobot",
    "sideswipe": "Autobot", "sunstreaker": "Autobot", "mirage": "Autobot",
    "hound": "Autobot", "trailbreaker": "Autobot", "prowl": "Autobot",
    "bluestreak": "Autobot",
    # 1984 Minicars
    "gears": "Autobot", "brawn": "Autobot", "huffer": "Autobot",
    "windcharger": "Autobot", "beachcomber": "Autobot", "cosmos": "Autobot",
    "powerglide": "Autobot", "seaspray": "Autobot", "warpath": "Autobot",
    "outback": "Autobot", "pipes": "Autobot", "tailgate": "Autobot",
    "wheelie": "Autobot", "hubcap": "Autobot", "bumper": "Autobot",
    # 1985 Autobots
    "jetfire": "Autobot", "tracks": "Autobot", "smokescreen": "Autobot",
    "skids": "Autobot", "grapple": "Autobot", "inferno": "Autobot",
    "hoist": "Autobot", "red alert": "Autobot", "perceptor": "Autobot",
    "blaster": "Autobot", "omega supreme": "Autobot",
    # Dinobots
    "grimlock": "Autobot", "slug": "Autobot", "sludge": "Autobot",
    "snarl": "Autobot", "swoop": "Autobot",
    # 1986 movie / post-movie
    "hot rod": "Autobot", "rodimus prime": "Autobot", "kup": "Autobot",
    "blurr": "Autobot", "springer": "Autobot", "arcee": "Autobot",
    "ultra magnus": "Autobot", "sky lynx": "Autobot", "wreck gar": "Autobot",
    "metroplex": "Autobot",
    # Aerialbots
    "silverbolt": "Autobot", "air raid": "Autobot", "skydive": "Autobot",
    "slingshot": "Autobot", "fireflight": "Autobot",
    # Protectobots
    "hot spot": "Autobot", "streetwise": "Autobot", "blades": "Autobot",
    "groove": "Autobot", "first aid": "Autobot",
    # Technobots
    "scattershot": "Autobot", "lightspeed": "Autobot", "strafe": "Autobot",
    "afterburner": "Autobot", "nosecone": "Autobot",
    # Headmasters (Autobot)
    "hardhead": "Autobot", "highbrow": "Autobot", "brainstorm": "Autobot",
    "chromedome": "Autobot", "fortress maximus": "Autobot",
    # Targetmasters (Autobot)
    "pointblank": "Autobot", "sureshot": "Autobot", "crosshairs": "Autobot",
    # Powermasters (Autobot)
    "joyride": "Autobot",
    # Throttlebots
    "goldbug": "Autobot", "chase": "Autobot", "freeway": "Autobot",
    "searchlight": "Autobot", "wideload": "Autobot", "rollbar": "Autobot",
    # Wreckers
    "sandstorm": "Autobot", "broadside": "Autobot", "topspin": "Autobot",
    "twin twist": "Autobot", "whirl": "Autobot", "roadbuster": "Autobot",
    "rotorstorm": "Autobot",
    # Pretenders (Autobot)
    "cloudburst": "Autobot", "splashdown": "Autobot", "waverider": "Autobot",
    "sky high": "Autobot", "chainclaw": "Autobot", "catilla": "Autobot",
    "carnivac": "Autobot",  # Autobot Pretender Beast
    "ironfist": "Autobot",
    # Blaster's cassettes
    "eject": "Autobot", "rewind": "Autobot", "steeljaw": "Autobot",
    "ramhorn": "Autobot",
    # Female Autobots / Fembots
    "elita one": "Autobot", "chromia": "Autobot", "minerva": "Autobot",
    "windblade": "Autobot", "road rage": "Autobot", "strongarm": "Autobot",
    # Sub-misc
    "alpha trion": "Autobot", "spike": "Autobot",
    "matrix of leadership": "N/A",  # not a character
    "punch": "Autobot", "counterpunch": "Autobot",
    "doublecross": "Autobot",  # Monsterbot
    "repugnus": "Autobot",  # Monsterbot (despite the name)
    "scoop": "Autobot",
    "nightbeat": "Autobot",  # Autobot Headmaster
    "quake": "Autobot",  # Action Master Autobot
    "knock out": "Autobot",  # actually Decepticon in Prime — but Legacy figure
    "thunderclash": "Autobot",
    "apelinq": "Autobot",  # Maximal
    "circuit": "Autobot", "guzzle": "Autobot",  # Action Masters
    "hot shot": "Autobot",  # mostly Autobot historically
    "ricochet": "Autobot",  # Stepper
    "rack 'n ruin": "Autobot",
    "tap-out": "Autobot",
    "pyro": "Autobot",
    "manta ray": "Autobot",  # G2 Cyberjet (Autobot in toy bio)
    "rattrap": "Autobot",  # Maximal in BW; was Autobot-aligned
    "devcon": "Autobot",  # bounty hunter, Autobot-aligned
    "powermaster optimus prime": "Autobot",
    "star optimus": "Autobot",
    "greenlight": "Autobot",
    "stakeout": "Autobot",  # Autobot Rescue Patrol micro
    "trip-up": "Autobot",   # Autobot Race Car Patrol
    "daddy-o": "Autobot",   # Autobot Race Car Patrol
    "battleslash": "Autobot",  # PotP Autobot Mini-Con
    "agent knight": "Autobot",  # GI Joe x TF collab Autobot
    "ectotron": "Autobot",      # Ghostbusters collab Autobot
    "mandalorian": "Autobot",   # SW collab Autobot
    "bone shaker": "Autobot",   # HW collab Autobot
    "gigawatt": "Autobot",      # BTTF collab Autobot
    "ectotron": "Autobot",
    "medix": "Autobot",         # Rescue Bot Autobot

    # ── DECEPTICONS ──
    # Big bads
    "megatron": "Decepticon", "galvatron": "Decepticon", "shockwave": "Decepticon",
    "starscream": "Decepticon", "skywarp": "Decepticon",
    "thundercracker": "Decepticon", "soundwave": "Decepticon",
    "reflector": "Decepticon", "ramjet": "Decepticon",
    "dirge": "Decepticon", "thrust": "Decepticon",
    # Triple Changers
    "astrotrain": "Decepticon", "blitzwing": "Decepticon", "octane": "Decepticon",
    "sixshot": "Decepticon", "six shot": "Decepticon",
    # Insecticons
    "bombshell": "Decepticon", "kickback": "Decepticon", "shrapnel": "Decepticon",
    "barrage": "Decepticon", "venom": "Decepticon", "chop shop": "Decepticon",
    "ransack": "Decepticon",
    # Constructicons
    "bonecrusher": "Decepticon", "hook": "Decepticon", "long haul": "Decepticon",
    "mixmaster": "Decepticon", "scavenger": "Decepticon", "scrapper": "Decepticon",
    # Combaticons
    "onslaught": "Decepticon", "blast off": "Decepticon", "brawl": "Decepticon",
    "swindle": "Decepticon", "vortex": "Decepticon",
    # Stunticons
    "motormaster": "Decepticon", "dead end": "Decepticon",
    "drag strip": "Decepticon", "breakdown": "Decepticon",
    "wild ride": "Decepticon",  # Wildrider
    # Predacons
    "razorclaw": "Decepticon", "divebomb": "Decepticon", "rampage": "Decepticon",
    "headstrong": "Decepticon", "tantrum": "Decepticon",
    # Terrorcons
    "hun-grrr": "Decepticon", "cutthroat": "Decepticon",
    "rippersnapper": "Decepticon", "sinnertwin": "Decepticon", "blot": "Decepticon",
    # Decepticon Headmasters
    "skullcruncher": "Decepticon", "weirdwolf": "Decepticon",
    "mindwipe": "Decepticon", "apeface": "Decepticon", "snapdragon": "Decepticon",
    "scorponok": "Decepticon", "squeezeplay": "Decepticon",
    "fangry": "Decepticon",
    # Decepticon Targetmasters
    "slugslinger": "Decepticon", "triggerhappy": "Decepticon",
    "misfire": "Decepticon", "spinister": "Decepticon",
    "cyclonus": "Decepticon", "scourge": "Decepticon", "sweeps": "Decepticon",
    # Decepticon Pretenders
    "bomb-burst": "Decepticon", "iguanus": "Decepticon",
    "skullgrin": "Decepticon", "bludgeon": "Decepticon",
    "octopunch": "Decepticon", "snarler": "Decepticon",
    "horri-bull": "Decepticon",
    # Powermasters (Decepticon)
    "doubledealer": "Decepticon",
    # Soundwave's cassettes
    "buzzsaw": "Decepticon", "rumble": "Decepticon", "frenzy": "Decepticon",
    "ravage": "Decepticon", "laserbeak": "Decepticon", "ratbat": "Decepticon",
    "slugfest": "Decepticon", "overkill": "Decepticon",
    # Battlechargers (1986)
    "runamuck": "Decepticon", "runabout": "Decepticon",
    # Micromasters (Decepticon Patrols)
    "bombshock": "Decepticon", "growl": "Decepticon",
    "red heat": "Decepticon", "jalopy": "Decepticon", "roadtrap": "Decepticon",
    # Quintesson — antagonist faction
    "quintesson": "Decepticon",  # treat as villain
    # Other Decepticons
    "nemesis prime": "Decepticon",  # evil OP clone
    "ruckus": "Decepticon",  # G1 Action Master (Decepticon)
    "leadfoot g2": "Decepticon",  # G2 Decepticon Predator (Generations Selects)
    "dracodon": "Decepticon",  # Beast Wars Mutant — Decepticon-aligned in modern toys
    "jhiaxus": "Decepticon",  # G2 Decepticon leader
    "tarn": "Decepticon",  # DJD leader
    # The Thirteen Primes (Autobot ancestors — call them Autobot in faction)
    "prima prime": "Autobot", "nexus prime": "Autobot",
    "alchemist prime": "Autobot", "amalgamous prime": "Autobot",
    "micronus prime": "Autobot", "onyx prime": "Autobot",
    "quintus prime": "Autobot", "solus prime": "Autobot",
    "vector prime": "Autobot", "sentinel prime": "Autobot",
    # Special: Liege Maximo was traitor; Megatronus = The Fallen (became Decepticon)
    "liege maximo": "Decepticon",
    "megatronus prime": "Decepticon",
    "herald of unicron": "Decepticon",  # Unicron-aligned

    # 2024+ Movies
    # Transformers One: characters who became Autobots/Decepticons later
    # We just default by character below

    # Special / Beast Wars / Other
    "road rocket": "Autobot",  # G2 mostly Autobot
    "wheeljack": "Autobot",
    # Cyberverse, RID, Prime — character-specific
    "repugnus": "Autobot",  # Cyberverse Autobot
}


def clean_name(name: str) -> str:
    return re.sub(r"\s*\*.*$", "", name).strip()


def map_line_subline(line: str) -> tuple[str, str]:
    if not line: return ("", "")
    return LINE_MAP.get(line, (line, ""))


def map_era(name_clean: str, line: str) -> str:
    if name_clean.lower() in ERA_OVERRIDES:
        return ERA_OVERRIDES[name_clean.lower()]
    return ERA_MAP.get(line, "Sunbow Cartoon")


def map_size(name_clean: str, line: str) -> str:
    name_l = name_clean.lower()
    line_l = (line or "").lower()
    if (name_l, line_l) in SIZE_OVERRIDES:
        return SIZE_OVERRIDES[(name_l, line_l)]
    if "core" in line_l:
        return "Core"
    return "Deluxe"


def map_faction(name_clean: str) -> str:
    return FACTION.get(name_clean.lower(), "Autobot")  # default Autobot


STATUS_TO_CONDITION = {
    "owned":      "Opened Complete",
    "preordered": "",
    "ordered":    "",
    "want":       "",
}


def main():
    args = sys.argv[1:]
    statuses = ["owned"]
    out_path = None
    i = 0
    while i < len(args):
        a = args[i]
        if a == "--status":
            v = args[i + 1]
            statuses = [s.strip() for s in v.split(",")] if v != "all" else None
            i += 2
        elif a == "--out":
            out_path = Path(args[i + 1])
            i += 2
        else:
            i += 1

    db.init_db()
    figs = db.list_figures()
    if statuses is not None:
        figs = [f for f in figs if f["status"] in statuses]

    if out_path is None:
        tag = "all" if statuses is None else "+".join(statuses)
        out_path = Path(__file__).parent.parent / f"bot_binder_{tag}.csv"

    # CSV header — Bot Binder columns (lowercase_underscore convention from template)
    cols = ["character", "line", "subline", "size_class", "era",
            "faction", "condition", "paid_price", "current_value"]

    with open(out_path, "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=cols)
        w.writeheader()
        for f in figs:
            cn = clean_name(f["name"])
            ln = f["line"] or ""
            bb_line, bb_subline = map_line_subline(ln)
            w.writerow({
                "character":      cn,
                "line":           bb_line,
                "subline":        bb_subline,
                "size_class":     map_size(cn, ln),
                "era":            map_era(cn, ln),
                "faction":        map_faction(cn),
                "condition":      STATUS_TO_CONDITION.get(f["status"], ""),
                "paid_price":     "",
                "current_value":  "",
            })

    status_label = ", ".join(statuses) if statuses else "all"
    print(f"Wrote {len(figs)} rows ({status_label}) -> {out_path}")


if __name__ == "__main__":
    main()
