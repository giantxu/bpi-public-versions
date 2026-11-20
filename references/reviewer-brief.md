# Parallel reviewers – when to use them and what to tell them

## Before you split the work

- **Finish one small unit yourself first**, to gate PASS. It tells you how long a page takes and what the documents
  of this matter look like. Do not parallelise something you have not done once end to end.
- **Size each assignment to what one reviewer can finish in one go.** Take the pages-per-session you measured on
  that first unit, not a guess: for many assistants that is a few dozen pages, not hundreds. A reviewer that runs
  out of time or context hands back nothing. One unit per assignment; a unit larger than one assignment is given
  to one reviewer *file by file* (assignment 1: files a–f, assignment 2: files g–m …), never to two at once.
- Parallel reviewers must not share anything writable: one review file per unit, and each reviewer is started with
  the environment variable `BPI_UNITS=<its unit keys>` so the tool refuses to touch other units.
- If your environment cannot run reviewers reliably in parallel, work through the units one after another with
  `bpi.py next` – slower, but nothing is lost.

## Brief (fill in the <> parts)

---
You are reviewing exhibit documents to produce BPI (bracketed) and Public (redacted) versions for a <proceeding>
submission. Matter folder: `<matter folder>` – run every command from there, with `BPI_UNITS=<keys>` set.
Tool: `python <skill>/scripts/bpi.py` – run `bpi.py next` whenever you are unsure what to do.
Read first: `<skill>/references/review-guide.md` (how to look, the edit format, the three leak checks) and
`<matter>/_work/rules.md` (the agreed bracketing rules – follow them exactly). Finished reference unit: <key> –
its `_work/review/<key>.json` shows the expected style.

The submitting company is <own company> (its own name, address and seal stay public; its account numbers are
bracketed). Counterparties in your unit(s): <names>.

Your assignment: unit <key> (<n> pages)<, files: …>.

Work file by file:
1. `bpi.py sheets KEY "file"`; look at every tile; `bpi.py page` / `lines` for anything you need to place exactly.
2. Edit `_work/review/KEY.json`, preferring text-anchored adds (`text`, `after`, `span`, `lines`, `table`).
3. `bpi.py check KEY` until clean; `bpi.py boxes KEY "file" PAGE` for the pages you touched.
4. `bpi.py build KEY "file"`; `bpi.py audit KEY` – fix or acknowledge (with the real reason) every finding.
When all files are done: `bpi.py qa KEY`, `bpi.py pubsheets KEY`, look at EVERY Public sheet, `bpi.py viewed KEY N`,
then `bpi.py gate KEY`.

Report after EACH file in one line (file, pages, open audit findings) so that progress survives an interruption,
and at the end paste the complete output of `bpi.py gate KEY` and `bpi.py acks KEY`. A unit whose gate does not
print PASS is not finished – say so plainly instead of calling it done. Also list: judgement calls the user should
confirm (anything rules.md does not settle), and oddities (misfiled documents, duplicates, unreadable pages).

Do not edit `<skill>/scripts`, `_work/terms.json`, `_work/rules.md`, other units' files or the source folder; do not
delete anything. If a supplier name is not being caught, tell me the name – I maintain the terms.
---

## When reports come back

- Run `bpi.py gate KEY` yourself for every unit reported as finished – do not take the report's word for it.
- Read `bpi.py acks KEY`: acknowledgements that are not obviously right are leaks until proven otherwise.
- A passed gate proves that the process was followed, not that the pages are right: the checks read OCR text and
  cannot see a faint seal or a number the OCR missed, and they cannot tell whether a block is too large.
- Look at a sample of Public pages from every reviewer (`bpi.py page … public`).
- Harmonise: the same clause type must get the same treatment in every unit. When two reviewers decided
  differently, pick one rule, write it into `_work/rules.md`, fix the units, re-gate.
