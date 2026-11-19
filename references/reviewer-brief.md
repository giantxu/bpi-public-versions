# Brief template for parallel reviewers

Fill in the <> parts and send one brief per group of units (balance groups by page count; ~300–550 pages each).

---
You are reviewing exhibit documents to produce BPI (bracketed) and Public (redacted) versions for a <proceeding>
submission. Matter folder: `<matter folder>` – run every command from there.
Tool: `python <skill>/scripts/bpi.py` (commands: sheets, lines, propose, build, qa).
Read first: `<skill>/references/review-guide.md` (edit format, sheet reading) and `<matter>/_work/rules.md`
(the agreed bracketing rules – follow them exactly). Reference units already finished: <keys> – their
`_work/review/<KEY>.json` files show the expected style.

The submitting company is <own company> (its own name/address/seal stay public; its account numbers are bracketed).
Counterparties in your units: <list from `bpi.py parties`>.

Your units: <keys with one line of description each, e.g. "205 – 550 pp incl. a 210-page contract and its English version">.

For each unit:
1. `bpi.py sheets KEY` and look at EVERY sheet (index.txt says which page is where).
2. Write `_work/review/KEY.json` (only your units). If a supplier name/abbreviation/address keeps being missed,
   add regexes to `_work/terms_KEY.json` and re-run `bpi.py propose KEY`, then re-check point edits.
3. Re-run sheets until correct; no WARN lines.
4. `bpi.py build KEY`, then `bpi.py qa KEY` until 0 issues or every remaining hit is verified as a false positive
   on the rendered page. Long builds: use a long timeout or run in background.
5. `bpi.py pubsheets KEY` and look at EVERY Public page (not a sample) – stamps, seal fragments at the page
   edges, remarks columns, wrapped amounts in words and overlay totals are what OCR-based QA misses.

Do not edit `<skill>/scripts`, `_work/terms.json`, `_work/rules.md`, other units' files or the source folder; do not
delete anything. Put helper scripts in your own sub-folder of `_work/reviewers/<your name>/`.

Report back briefly: per unit files/pages, QA result (explain any remaining hits), judgement calls the user should
confirm (anything not covered by rules.md), oddities (misfiled documents, duplicates, unreadable pages).
---
