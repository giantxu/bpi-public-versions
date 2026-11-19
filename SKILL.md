---
name: bpi-public-versions
description: Prepare bracketed BPI / business-confidential versions and redacted Public versions of exhibit documents (scanned contracts, invoices, purchase orders, price lists, Word translations) for US trade proceedings - CBP EAPA requests for information (19 C.F.R. 165.4), Commerce/ITC antidumping and countervailing questionnaires, APO filings. Use this skill whenever the user wants to "make BPI and Public versions", bracket business confidential information, prepare a public version of an exhibit or attachment, redact supplier names / prices / bank accounts in a submission, or mentions BPI, BCI, BPI版, Public版, 公开版, 保密版, 括号, 打括号, 涂白 or 公开版本 for a set of PDFs - even if they only say "do the exhibits like last time".
---

# BPI / Public versions of exhibit documents

You turn a folder of exhibit documents into two parallel sets:

- **BPI version** – the original, untouched, with red single brackets `[ ]` drawn around every item claimed as
  business confidential, and a "BUSINESS CONFIDENTIAL" header on every page.
- **Public version** – the same pages with everything inside the brackets permanently removed, black brackets left
  in place with a short summary label inside ("Supplier name and address", "Quantities, unit prices and amounts"),
  and a "PUBLIC VERSION" header on every page.

The hard part is not the drawing – `scripts/bpi.py` does that – it is deciding, page by page, exactly what is
confidential, consistently across hundreds of scanned pages in two languages, and proving nothing leaked.
The workflow below scales to thousands of pages across dozens of folders. Follow its order: agreeing the rules and
showing samples before the full run is what keeps rework small.

## 0. Tools

All commands run from the **matter folder** (the folder that will hold `bpi_config.json`):

```
python <skill>/scripts/bpi.py <command> ...
```

(`python3` on macOS/Linux, `python` or `py` on Windows.) Commands: `init doctor survey ocr parties propose sheets
lines build qa log status` – run `bpi.py` without arguments for help. Dependencies and Windows notes:
`references/setup.md`. Config keys: `references/config.md`.

## 1. Understand the governing requirements

Read the user's instruction document (RFI, questionnaire, APO instructions) completely. Requirement documents often
contain **scanned example pages** (e.g. CBP RFI Appendix II "Public Version Examples") – render those pages to images
and look at them; text extraction returns garbage for them, and they show the expected look (what was bracketed,
how the summary labels read, where "PUBLIC VERSION" sits). Summarise for the user: bracket style (single vs double
brackets), what must always be bracketed (account numbers, tax IDs, personal identifiers), what can never be
bracketed, labelling and certification requirements. `references/requirements.md` has the CBP EAPA essentials.

## 2. Survey the exhibits

`bpi.py init` (then edit `bpi_config.json`: source folder, output folders, header text, and `own_company_regex` – the
submitting company's own names/address/phone, which must stay public), `bpi.py doctor`, then `bpi.py survey`.
Also look at a few pages of each document type yourself. Report to the user, besides counts:
- files that are not what their name says (e.g. a "translation .pdf" that is actually a saved web page / chat log –
  it must not be submitted);
- byte-identical duplicates (within or across folders), translations without originals, partial documents;
- who the counterparties are (suppliers, contractors, forwarders, consultants) – `bpi.py parties` after OCR.

## 3. Agree the bracketing rules with the user before doing volume work

Propose the default rule set in `references/bracketing-rules.md` and ask the user to decide the open points listed
there (supplier identity, quantities, invoice numbers containing supplier abbreviations, whole clause vs numbers only,
output format for Word files, the company's own staff names...). Write the agreed rules into
`_work/rules.md` in the matter folder – every later step and every reviewer works from that file.

## 4. Samples first

Pick ~5 files that cover the variety (single-page scanned invoice, long bilingual contract with rotated price
tables, price appendix, Word translation, born-digital PDF). Run the full pipeline on them (steps 5–7) into a
samples folder and let the user review the BPI and Public PDFs. Adjust rules, then go to volume.

## 5. Volume pipeline (per unit = per sub-folder)

```
bpi.py ocr                     # once, all scanned pages (cached in _work/ocr)
bpi.py parties                 # -> write supplier regexes into _work/terms.json (see below)
bpi.py propose all             # automatic proposals -> _work/auto
bpi.py sheets KEY              # contact sheets -> _work/sheets/KEY/sheet_###.png (+ index.txt)
# look at EVERY sheet, write _work/review/KEY.json, re-run sheets until right
bpi.py build KEY
bpi.py qa KEY                  # leak check - must end with 0 issues or every hit explained
bpi.py log                     # BCI log spreadsheet
```

**Supplier terms** (`_work/terms.json`, `{"*": [[regex, label], ...], "KEY": [...]}`, or `_work/terms_KEY.json`):
OCR garbles names (similar-looking characters swapped, "Engincering" for "Engineering"), so write tolerant regexes, include abbreviations used in invoice
numbers, addresses, post codes, phone numbers and the company's English and Chinese names. Labels starting with
"Supplier name" make short name/address lines bracket from after their "卖方：" style label to the end of line.

**Review is the real work.** The automatic proposals catch names, amounts, bank lines, price columns, seals and
handwriting candidates, but they miss and over-catch. Look at every page; the edit format, the colour legend, the
most common corrections and how to place precise boxes are in `references/review-guide.md` – read it before the
first review. Prefer text-anchored `span` edits (exact) over eyeballed rectangles; use `bpi.py lines` to get anchors.

**Large jobs:** split units across parallel reviewers (one review file per unit, nobody edits `scripts/`, the
shared terms file or another unit's file). Give each the brief in `references/reviewer-brief.md` plus the path to
`_work/rules.md`. When they report back, check their QA, read their judgement calls, harmonise inconsistencies
between reviewers (the same clause type must get the same treatment everywhere), rebuild what you change, and run
`bpi.py status` to catch units whose review was edited after their last build.

## 6. Quality gates before saying "done"

- `bpi.py qa all` re-OCRs every Public page. Fix real leaks; for each remaining hit verify it on the rendered page and
  explain it (typical false positives: a bracketed price "240.00" equals a public postcode "24000"; a public title's
  digits contain a bracketed number; a generic equipment name matches a supplier regex).
- `bpi.py status` – nothing stale, page counts equal (qa checks), every file built.
- Look at a random sample of Public pages from every reviewer.
- Note file sizes – portals often cap uploads; offer to lower `dpi`/`jpeg_quality` or split.

## 7. Report to the user

Deliver: the two output folders, `BCI Log.xlsx` (one row per bracket with category and basis – the backbone of the
required "explanation of why each bracketed item is confidential"), and a short report: QA result with every
remaining hit explained, the judgement calls that need the user's confirmation, duplicates / misfiled / skipped files,
large files. Keep the report in the user's language.

## Why the Public version is built this way

Scanned pages are re-rasterised and the pixels inside brackets painted white, then saved as a new image-only page –
nothing hidden survives (no text layer, no original image underneath). Born-digital PDFs and converted Word files get
true redaction (text and image pixels under the box removed) so they stay searchable. Metadata is cleared.
Overlapping boxes are merged and the label is composed from what was merged ("Supplier name, bank account / tax ID,
seal and signature"), so the public reader still understands what was removed – the summarisation requirement.
