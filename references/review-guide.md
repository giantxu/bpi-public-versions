# Review guide – looking at pages, writing edits, proving nothing leaked

## 1. Looking

| Command | What you get |
|---|---|
| `bpi.py sheets KEY [FILE ...]` | `_work/sheets/KEY/sheet_###.png`: 6 page tiles per image with the current brackets; `index.txt` says which file/page each tile is. Every box carries its **id** (`a3` = automatic proposal, `m0` = your addition, `a3+m0` = merged). |
| `bpi.py page KEY FILE PAGE` | one page, large, with a **labelled grid** (page fractions) and box ids → `_work/page/KEY/`. Add `X0 Y0 X1 Y1` to zoom into a region; add `public` to see the built Public page instead. Use it whenever you need a coordinate or doubt what you see on a sheet. |
| `bpi.py lines KEY FILE PAGE` | the page's text lines, numbered `L0, L1, …`, with their boxes. Anchors for text-based edits. |
| `bpi.py boxes KEY FILE [PAGE]` | every final bracket with its id, rectangle, label and **the text it covers** (`⟦ ⟧` marks the covered part of a line). Check here that a bracket covers what you meant – no picture needed. |

Box colours on sheets (proposal `src`): red `term` supplier term, `invno` invoice number with a counterparty code,
`remark` purchase-order remark naming a manufacturer · blue `bank` · light blue `contact` · purple `person` ·
orange `pay` / `ld` clause · green `amount`, `amtwords`, `table` · pink `seal-red`, `seal-sup` (seal whose text
matches a supplier term), `seal-edge?` (cross-page seal fragment at the page edge) · violet `seal-blue?` ·
yellow-orange `hand?` handwriting candidate · brown `sigfield` · black `manual` · **grey dashed `seal-own?`** =
seal in the submitter's own colour: a candidate that is *not* bracketed unless you `keep` it.

## 2. Edit file `_work/review/KEY.json`

```json
{
  "*": { "*": {"delsrc": ["sigfield"]} },
  "commercial invoice-*.pdf": {
    "1": {"add": [{"after": "INVOICE\\s*N[O0o]\\.?\\s*[:：]", "label": "Invoice No. (contains supplier abbreviation)"}]}
  },
  "purchase contract-1.pdf": {
    "*":      {"delsrc": ["hand?"]},
    "1":      {"del": ["a14", "a15"]},
    "2-27":   {"add": [{"r": [0.96, 0.08, 1.0, 0.30], "label": "Supplier seal", "snap": false}]},
    "9":      {"add": [{"span": {"from": "^4\\.2\\.1", "to": "Seller by T/T"}, "label": "Payment terms (percentages, amounts and timing)"},
                       {"text": "RM\\s*[\\d,]+(?:\\.\\d+)?", "label": "Amount"},
                       {"lines": "31-34", "label": "Liquidated damages terms"}]},
    "18-28":  {"clear": true,
               "add": [{"table": {"from": "数量|Qty", "to": "合价|Total"}, "label": "Quantities, unit prices and amounts"}]},
    "30":     {"delsrc": ["hand?"], "relabel": [["a7", "Signature"]], "keep": ["a12"]}
  }
}
```

**File keys:** an exact file name, a glob (`commercial invoice-*.pdf`), or `"*"` = every file of the unit.
**Page keys:** `"7"`, `"3-17"`, `"2,4,9-last"`, `"odd"`, `"even"`, `"3-27:odd"`, `"*"`. All blocks that apply to a
page are combined (lists are concatenated). Keys starting with `_` are ignored (use `"_notes"` for remarks).

**Removing / changing proposals**
- `delsrc: ["hand?", "sigfield"]` – delete all proposals of those kinds.
- `del: ["a3", "a7"]` – delete by id. (`delat: [[x, y]]` deletes the smallest box containing a point.)
- `relabel: [["a3", "Signature"]]`, `grow: [["a3", x0, y0, x1, y1]]` – change the box with that id (the point
  forms `[x, y, label]` / `[x, y, x0, y0, x1, y1]` also work).
- `keep: ["a12"]` – bracket a grey `seal-own?` candidate after all (it is a supplier's seal).
- `clear: true` – drop every proposal on the page(s).
Ids are stable until `propose` is run again for the unit; after a re-run, check your `del` / `relabel` ids.

**Adding brackets – prefer text anchors over coordinates.** A coordinate estimated from a picture is easily off by
a line or a few characters, and a bracket that is off leaks. In order of preference:
1. `{"text": "regex"}` – bracket every match of the regex on the page (just the matched characters;
   `"whole_line": true` for the whole line, `"group": 1` for a capture group). Names, numbers, amounts.
2. `{"after": "regex"}` – bracket the value behind a label: from the end of the match to the end of the line
   (`"Engineer\\s*[:：]"`, `"Tel\\.?\\s*[:：]"`, `"账号\\s*[:：]"`).
3. `{"span": {"from": "regex", "to": "regex"}}` – all lines from the first line matching `from` to the first later
   line matching `to`; add `x0`/`x1` (page fractions) to stay inside one column of a two-column page. Whole clauses.
4. `{"lines": "31-34"}` – lines by their numbers from `bpi.py lines`.
5. `{"table": {"from": "数量|Qty", "to": "合价|Amount|Total", "until": "合计|TOTAL"}}` – the block of a price table
   from the column header matching `from` to the one matching `to` (upright tables and tables printed sideways);
   on continuation pages without a header row the columns of the previous page are reused. Keeps headers and item
   descriptions visible. Always check the result with `boxes` / `page`: a row whose numbers the OCR missed may
   need an `r` box.
6. `{"r": [x0, y0, x1, y1]}` – a rectangle in page fractions; needed for what has no text: signatures, initials,
   seals, logos, handwriting, columns the OCR could not read. Read the numbers off `bpi.py page … ` (zoom in),
   never off a small sheet tile, and add a margin. `r` boxes snap to the text lines inside them unless the label
   is Signature / Seal / Supplier logo / Initials / Names / Handwritten… or `"snap": false`.
`rot: 90` draws the brackets for content printed sideways.

An add under a single-page key must match, otherwise it is an ERROR and the file is not built. An add under a
multi-page key need only match somewhere (`"optional": true` / `false` overrides this).

**After every round of edits:** `bpi.py check KEY` (every problem at once: unknown file names, anchors that match
nothing, ids that no longer exist), then `bpi.py boxes KEY FILE PAGE` for the pages you touched. Overlapping boxes
are merged and their labels composed; boxes inside a bigger box are dropped.

## 3. What to look for on every page

1. **Missing**: supplier names in running text, letterhead addresses without a "Tel/Address" keyword, logos,
   amounts written in words, payment clauses (bracket the whole clause, both languages), price columns on pages
   that continue a table without its header, signatures (handwriting detection misses faint ones), page initials
   at the bottom corners, names in approval screenshots, and – the misses most often found later by the client:
   - amounts in words that wrap onto a second line ("SAY IN CHINA YUAN TEN MILLION" / "ONLY") – every line;
   - invoice / document numbers embedding the supplier's code ("ABC-XYZ-P-003", "XYZ2022-01") – whole number;
   - remarks / manufacturer / brand columns of purchase-order item lists naming makers or vendors (OCR often
     misses these columns – check them by eye on every item-list page);
   - supplier seals that are not red: **seal colour says nothing about the owner**. Identify every seal and every
     cross-page seal fragment at the page edge by its text, comparing a fragment with the complete seal elsewhere
     in the document; only the submitter's own seal stays public;
   - QR codes and barcodes whose content is not printed in clear on the page (an e-invoice QR linking to the
     full invoice) – bracket ("QR code (encodes e-invoice details)"); a code repeating a public number may stay;
   - totals in red overlay translations, supplier stamps with tax numbers at a page foot, and the first letters
     of a name left just outside a bracket ("Supplier: TA[").
2. **False**: `hand?` boxes on two-column text, drawings, punch holes, scan edges; `seal-red` on red translation
   overlays; `sigfield` boxes over empty signature fields; `person` boxes on "(Signature and stamp)" captions;
   `amount` on capacities ("30万吨", "2.7 Million tons").
3. **Partial**: a box covering "Example Environmental Engineering" but not "Co., Ltd."; an address box starting
   after "No. 33,"; a clause box ending one line early. Partial = leak.
4. **Label quality**: the public label must say what was removed. One block with a composed label is better than
   a dozen tiny boxes.

## 4. Proving nothing leaked – three checks, all required

**a. `bpi.py audit KEY`** (no OCR run, takes seconds; run it after every round of edits). It reads the source text
and your brackets and lists
- `cut` / `half` – a bracket edge cuts through text: `Contractor: N⟦ORTHSTAR … CO., LTD⟧` means the "N" is outside;
- `term`, `company`, `bank`, `contact`, `person`, `amount`, `amtwords`, `pay`, `ld`, `invno`, `remark`, `number` –
  sensitive-looking text that no bracket covers (also everything you removed with `delsrc` / `clear` and did not
  re-cover);
- `seal` – a seal proposal left unbracketed; `code` – an unbracketed QR code / barcode with its decoded content.
Each finding has an id. Either fix the edit file, or – when you have verified that the item is public (the
submitter's own data, a generic clause without negotiated figures, a tariff code, a header word) – acknowledge it
with the reason:
`bpi.py ack KEY 3fa2c1 9b0d77 -m "HS tariff codes on the customs form, public"` or, for a whole group,
`bpi.py ack KEY --kind pay --file "contract-2.pdf" --pages 52-116 -m "standard general conditions, no negotiated figures (rule 8)"`.
Never acknowledge to make a number go down: acknowledged items are listed for the user (`bpi.py acks KEY`).
The audit only sees text the OCR could read – it does not replace looking.

**b. `bpi.py qa KEY`** re-OCRs the built Public PDFs and searches for supplier terms and for 5+ digit numbers that
were inside brackets. Verify each hit on the page (`bpi.py page KEY FILE PAGE public`); typical false positives: a
bracketed price "240.00" equals a public postcode "24000"; a public contract number contains a bracketed number.
Fix real leaks, `ack` verified false positives. A "supplier term visible" hit often means the supplier regex is too
strict for a misreading in the OCR cache: anchor the regex on a short distinctive fragment of the name. qa cannot
see names of persons, signatures, seals or short numbers.

**c. Looking at the Public pages.** `bpi.py pubsheets KEY` → look at **every** image in `_work/pub/KEY/` (4 pages
each); zoom into doubtful spots with `bpi.py page KEY FILE PAGE public X0 Y0 X1 Y1`. Any visible supplier
identity, price, quantity, amount, account / tax number, personal name, signature, seal or payment / penalty term
is a leak: fix, rebuild that file, regenerate, look again. Then record it: `bpi.py viewed KEY N`.

`bpi.py gate KEY` checks all of this (clean edit file, fresh build, no open audit / qa findings, Public sheets
newer than the build and attested as viewed) and prints PASS or FAIL with the next command. **A unit is done when
its gate passes – not before.**

## 5. Efficient patterns

- Page ranges and globs replace generator scripts: initials on every page (`"2-last"`), cross-page seal strips on
  the right edge of odd pages (`"3-27:odd"`), the same letterhead box on every invoice (`"commercial invoice-*.pdf"`).
- For a contract and its page-identical translation, write the edits once under a glob that matches both
  (`"purchase contract-1*.pdf"`), then review the pages of the translation that differ.
- Rebuild only what changed: `bpi.py build KEY "file.pdf"`; regenerate sheets for it: `bpi.py sheets KEY "file.pdf"`.
- Regexes, line numbers and ids are tied to the OCR cache: when a matter moves to another machine, move the whole
  matter folder including `_work/`.
- Keep helper files in the matter's `_work/`; never edit the skill's `scripts/` during a job.
