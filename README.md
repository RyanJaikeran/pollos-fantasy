# PollosBowl Gazette

A one-page site of stats and roasts for the PollosBowl fantasy league, built from a Sleeper export.

The site lives in `docs/index.html` and is served by GitHub Pages.

## Updating after a new week

1. Export the league from Sleeper and drop the `sleeper_league_<id>.json` file into this folder. It's git-ignored, so it never gets pushed.
2. Run `python3 build.py`. That rebuilds `docs/index.html` (and `index.html`, the claude.ai version).
3. Commit and push. Pages redeploys within a minute or two.

## Files

- `template.html`: layout, charts and all the jokes. Some joke copy quotes week 1–3 numbers directly, so refresh it as the season goes on.
- `build.py`: crunches the Sleeper export and fills in the template.
- `picks.json`: the power rankings shown on the Predictions page (roster IDs in ranked order).
