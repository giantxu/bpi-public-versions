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

The drawing is done by `scripts/bpi.py`. Your work is deciding, page by page, exactly what is confidential,
consistently across hundreds of pages in two languages – and proving that nothing leaked. A Public version with
one visible supplier name or account number is a failed job, however many pages are right.

## Working rules (they matter more than speed)

1. **Done means `bpi.py gate KEY` prints PASS.** Not "the files were generated", not "qa shows 0". Never report a
   unit as finished without pasting its gate output. If you cannot get a unit through the gate, say so and say why.
2. **When unsure what to do next, run `bpi.py next`.** It names the next step and the command.
3. **Small batches, finished one at a time.** Take the smallest unit, bring it to gate PASS, then the next. Do not
   start volume work, and do not hand units to parallel helpers, before one unit has passed the gate and the user
   has approved samples.
4. **Place brackets by text, not by eye, wherever there is text** (`text`, `after`, `span`, `lines`, `table` edits).
   Coordinates read off a picture are easily one line or a few characters off, and a bracket that is off leaks.
   Use rectangles only for what has no text (signatures, seals, logos) and read them off `bpi.py page` (zoomed).
5. **Check what you wrote before you build:** `bpi.py check KEY`, then `bpi.py boxes KEY FILE PAGE` shows the text
   each bracket really covers.
6. **Bracket only what is confidential.** Over-bracketing is a defect just like a leak: the submitter's own name,
   address, logo and seal, headings, item names and specifications, dates and document numbers stay visible. A
   price table gets a bracket over its quantity / price / amount columns, not over the whole table; a clause gets
   a bracket over that clause, not over the page.
7. **Three checks, all required, none replaces another:** `audit` (text cut by a bracket edge, sensitive text
   outside every bracket, a number or clause bracketed in one place and visible in another, over-bracketing),
   `qa` (re-OCR of the Public files and of the text at every bracket edge), and looking at every Public page
   yourself – seals and signatures can only be judged by eye, and a seal belongs to whoever is named on it, so
   read it before you label it. If you cannot view images, say so; do not record a check you did not make.
8. **Never silence a finding.** Fix the cause, or `ack` it with the true reason why the item is public. Never make
   a finding disappear by drawing a bigger bracket over text that is not confidential – the audit reports that
   too. Acknowledged items go into your report.
9. **The same thing gets the same treatment everywhere:** a total bracketed on the item list is bracketed on the
   cover page; a clause bracketed in the original is bracketed in its translation.
10. Commands that write need an explicit unit key (`build 205`, not `build`). Work only on the units you were given.

## 0. Tools

All commands run from the **matter folder** (the folder that holds `bpi_config.json`):

```
python <skill>/scripts/bpi.py <command> ...        (python3 on macOS/Linux, python or py on Windows)
```

Run `bpi.py` without arguments for the command list. Dependencies and Windows notes: `references/setup.md`.
Config keys: `references/config.md`.

## 1. Understand the governing requirements

Read the user's instruction document (RFI, questionnaire, APO instructions) completely. Requirement documents often
contain **scanned example pages** (e.g. CBP RFI Appendix II "Public Version Examples") – render those pages to images
and look at them; text extraction returns garbage for them, and they show the expected look. Summarise for the
user: bracket style (single vs double brackets), what must always be bracketed (account numbers, tax IDs, personal
identifiers), what can never be bracketed, labelling and certification requirements.
`references/requirements.md` has the CBP EAPA essentials.

## 2. Set up and survey

`bpi.py init`, then edit `bpi_config.json`: source folder, output folders, header text and the four `own_*` keys
(the submitting company's own names / address / phone, its document-code prefixes, the words on its seal, its seal
colour – all of that stays public). Then `bpi.py doctor`, `bpi.py survey`, `bpi.py ocr`.
Look at a few pages of each document type yourself. Report to the user, besides counts:
- files that are not what their name says (a "translation .pdf" that is a saved web page – must not be submitted);
- byte-identical duplicates, translations without originals, partial documents;
- who the counterparties are (suppliers, contractors, forwarders, consultants).

**Supplier terms** (`_work/terms.json`: `{"*": [[regex, label], ...], "KEY": [...]}`, or `_work/terms_KEY.json`).
`bpi.py parties` lists company-like names. Write one tolerant regex per counterparty, **anchored on a short
distinctive fragment** of its name ("NORTHSTAR", not the full "QINGDAO NORTHSTAR HEAVY INDUSTRY CO., LTD" – OCR
misreads letters: "QINGDA0", "INDUSTKY"), plus its abbreviations, address fragments, post code, phone. Labels starting with
"Supplier name" bracket short name/address lines from after their "Seller:" style label to the end of the line.
Then run `bpi.py terms-check` and repeat until every counterparty in its list is matched: every name the terms
miss becomes manual work and leak risk on every page it appears on.

## 3. Agree the bracketing rules with the user before doing volume work

Propose the default rule set in `references/bracketing-rules.md` and ask the user to decide the open points listed
there. Write the agreed rules into `_work/rules.md` – every later step and every reviewer works from that file.

## 4. Samples first

Take up to three small units that cover the variety (scanned invoice, bilingual contract with price tables, Word
translation, born-digital PDF). Bring each through step 5 to gate PASS and give the user the BPI and Public files
to review. Adjust `_work/rules.md` to the feedback. Only then record the approval – `bpi.py samples-ok "<what the
user said>"` – which unlocks building further units. Do not run it on your own authority.

## 5. One unit, start to gate

```
bpi.py propose KEY                 # automatic proposals -> _work/auto
bpi.py sheets KEY                  # contact sheets with box ids -> _work/sheets/KEY/ (+ index.txt)
#   look at EVERY tile; page / lines to place things exactly; write _work/review/KEY.json
bpi.py check KEY                   # the edit file applies cleanly?  then: boxes KEY FILE PAGE
bpi.py build KEY                   # BPI + Public PDFs (build KEY "file.pdf" for one file)
bpi.py audit KEY                   # fix or acknowledge every finding; rebuild what you changed
bpi.py qa KEY                      # fix real leaks, acknowledge verified false positives
bpi.py pubsheets KEY               # look at EVERY image (pages + cut-outs of seals / signatures); each shows
                                   #   a code: bpi.py viewed KEY CODE CODE ...
bpi.py gate KEY                    # PASS = unit finished
```

The edit format, the box colours, what to look for on a page and how to read audit / qa findings are in
`references/review-guide.md` – read it before the first review. The automatic proposals catch names, amounts, bank
lines, clauses with percentages, seals and handwriting candidates, but they miss and over-catch: reviewing every
page is the real work. For long files work in page ranges (`"2-27": {...}`) and rebuild file by file.

**Large matters:** only after samples are approved, and only if helpers can each finish what they are given.
`references/reviewer-brief.md` says how to size assignments (one unit each, restricted with `BPI_UNITS`), what to
tell reviewers and how to check what comes back. Otherwise go unit by unit with `bpi.py next`.

## 6. Before saying "done"

- `bpi.py status` – every unit PASS. (`bpi.py gate all` for the details.)
- `bpi.py acks all` – read every acknowledgement once more; anything not clearly public is a leak.
- Consistency across units: the same clause type treated the same way everywhere (original and translation too).
- Note file sizes – portals often cap uploads; offer to lower `dpi` / `jpeg_quality` or to split.

## 7. Report to the user

Deliver the two output folders and `BCI Log.xlsx` (`bpi.py log all` – one row per bracket with category and basis,
the backbone of the required explanation of why each item is confidential), and a short report in the user's
language: gate result per unit; the acknowledged findings grouped by reason; judgement calls that need the user's
confirmation; duplicates / misfiled / skipped files; large files. State plainly anything that is not finished.

## Why the Public version is built this way

Scanned pages are re-rasterised and the pixels inside brackets painted white, then saved as a new image-only page –
nothing hidden survives (no text layer, no original image underneath). Born-digital PDFs and converted Word files get
true redaction (text and image pixels under the box removed) so they stay searchable. Metadata is cleared.
Overlapping boxes are merged and the label is composed from what was merged ("Supplier name, bank account / tax ID,
seal and signature"), so the public reader still understands what was removed – the summarisation requirement.
