"""
Single source of truth for character-name -> TFWiki page name.

Used by:
  - build_site.py   (injects TFWIKI_OVERRIDES into the site's JavaScript)
  - audit_links.py  (HEAD-checks every figure's resolved URL)

When a new character ends up with a dead link, add an entry here pointing to
the correct TFWiki article. Then re-run audit_links.py to confirm.
"""
import re
import urllib.parse

# Default rule:
#   1. Strip "*<continuity>" suffix from the user's free-text name
#   2. Title-case each word AND each hyphen-separated segment
#   3. Replace spaces with underscores
#   4. Append "_(G1)"
#
# That works for ~90% of G1 characters. The rest go in OVERRIDES below.
TFWIKI_OVERRIDES = {
    # ── The Thirteen Primes — no _(G1) page; bare name ──
    "Liege Maximo":         "Liege_Maximo",
    "Quintus Prime":        "Quintus_Prime",
    "Solus Prime":          "Solus_Prime",
    "Onyx Prime":           "Onyx_Prime",
    "Micronus Prime":       "Micronus_Prime",
    "Prima Prime":          "Prima",
    "Alchemist Prime":      "Maccadam",
    "Megatronus Prime":     "Megatronus_Prime",

    # ── User-collection variants of well-known characters ──
    "Star Optimus":         "Optimus_Prime_(G1)",
    "Vector Prime":         "Vector_Prime_(Cybertron)",
    "Ironhide BD":          "Ironhide_(G1)",       # Battle Damage deco
    "Wheeljack Origins":    "Wheeljack_(G1)",      # Origins deco
    "Wild Ride":            "Wildrider_(G1)",      # Hasbro renamed Wildrider
    "Wreck Gar":            "Wreck-Gar_(G1)",      # canonical hyphen
    "Leadfoot G2":          "Leadfoot_(G2)",

    # ── Crossovers / Collaboratives (bare-name pages) ──
    "Mandalorian":          "The_Mandalorian",
    "Ectotron":             "Ectotron",
    "Agent Knight":         "Agent_Knight",
    "Bone Shaker":          "Bone_Shaker",

    # ── Disambiguators that the default _(G1) wouldn't catch ──
    "Quintesson":           "Quintesson_Judge_(G1)",
    "Hun-Grrr":             "Hun-Gurrr_(G1)",      # TFWiki spelling: double-r
    "Minerva":              "Minerva_(G1_robot)",  # unusual disambig
    "Strongarm":            "Strongarm_(RID)",     # 2015 RID character
    "Jhiaxus":              "Jhiaxus_(G2)",        # G2 origin
    "Road Rocket":          "Road_Rocket_(G2)",    # G2 origin

    # ── Bare-name characters (TFWiki article has no continuity suffix) ──
    "Amalgamous Prime":     "Amalgamous_Prime",
    "Battleslash":          "Battleslash",
    "Dracodon":             "Dracodon",
    "Gigawatt":             "Gigawatt",
    "Jalopy":               "Jalopy",
    "Matrix of Leadership": "Matrix_of_Leadership",
    "Nexus Prime":          "Nexus_Prime",
    "Pointblank":           "Pointblank",
    "Rattrap":              "Rattrap",
    "Red Heat":             "Red_Heat",
    "Roadtrap":             "Roadtrap",
    "Six Shot":             "Six_Shot",
    "Skullgrin":            "Skullgrin",
    "Spike":                "Spike",
    "Sweeps":               "Sweeps",
    "Trip-Up":              "Trip-Up",
    "Horri-Bull":           "Horri-Bull",

    # ── 2-pack partners documented on the partner's page ──
    "Daddy-O":              "Trip-Up",
}


def _strip_continuity(name: str) -> str:
    """Remove '*<continuity>' suffix (e.g. 'Nemesis Prime *Animated')."""
    return re.sub(r"\s*\*.*$", "", name).strip()


def _title_case(name: str) -> str:
    """Title-case each word AND each hyphen-segment.

    'daddy-o' -> 'Daddy-O', 'BumbleBee' -> 'Bumblebee', 'first aid' -> 'First Aid'.
    """
    def tc(w: str) -> str:
        return "-".join(p[:1].upper() + p[1:].lower() for p in w.split("-"))
    return " ".join(tc(w) for w in name.split())


def tfwiki_path(name: str) -> str:
    """Return the URL-safe path portion of the TFWiki link (no domain)."""
    clean = _strip_continuity(name)
    if clean in TFWIKI_OVERRIDES:
        return TFWIKI_OVERRIDES[clean]
    titled = _title_case(clean)
    return urllib.parse.quote(titled.replace(" ", "_")) + "_(G1)"


def tfwiki_url(name: str) -> str:
    """Return the full TFWiki article URL for a character name."""
    return "https://tfwiki.net/wiki/" + tfwiki_path(name)
