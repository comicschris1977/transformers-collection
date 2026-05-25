# Site brand assets

Drop the three logo files into this folder with these exact filenames:

| Filename | Used for | Notes |
|---|---|---|
| `transformers_logo.png` | Wordmark in the header (replaces the styled "TRANSFORMERS" text) | PNG with transparent background. Wide aspect ratio (e.g. 600×120). Should look good on dark background. |
| `autobot_symbol.png` | Top-left of the header (replaces the SVG faux-Autobot symbol) | Square PNG with transparent background (e.g. 256×256). The red Autobot insignia. |
| `wreckers_logo.png` | Faction badge on cards tagged as a Wrecker (replaces the "WRECKER" text chip) | Small horizontal logo. Should be legible at ~80px wide. Transparent background preferred. |

**SVG works too** — if you have vectors, save them as `transformers_logo.svg`,
`autobot_symbol.svg`, `wreckers_logo.svg` and I'll prefer those (cleaner at
any zoom level). The build script auto-picks SVG over PNG when both exist.

Once dropped here, tell me and I'll wire them into the site.
