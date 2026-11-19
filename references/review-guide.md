# Review guide – reading contact sheets and writing edits

## Contact sheets

`bpi.py sheets KEY` writes `_work/sheets/KEY/sheet_###.png`: 6 page tiles per sheet (3 columns × 2 rows, each tile
fitted into 512×724 px) and `index.txt` saying which file/page each tile is. Cyan tick marks every 0.1 of page
width/height. Coordinates in edits are **normalised to the page** (0–1, origin top-left), so estimate them from the
ticks – then let `snap`/`span` make them exact.

Box colours (proposal `src`):
red `term` supplier term · blue `bank` · light blue `contact` · purple `person` · orange `pay`/`ld` clause ·
green `amount`/`table` · pink `seal-red` · violet `seal-blue?` · yellow-orange `hand?` handwriting candidate ·
brown `sigfield` signature field · black `manual` (your additions).

## Edit file `_work/review/KEY.json`

```json
{
  "commercial invoice-2.pdf": {
    "1": {"delat": [[0.50, 0.455]],
          "add": [{"r": [0.76, 0.705, 0.90, 0.775], "label": "Signature"}]}
  },
  "purchase contract-1.pdf": {
    "*":  {"delsrc": ["seal-blue?"]},
    "9":  {"add": [{"span": {"from": "^4\\.2\\.1", "to": "Seller by T/T", "x0": 0.5, "x1": 1},
                    "label": "Payment terms (percentages, amounts and timing)"}]},
    "30": {"delsrc": ["sigfield", "hand?"], "relabel": [[0.37, 0.5, "Signature"]]}
  }
}
```

Ops (per page; `"*"` = every page of the file, combined with page-specific ops):
- `delsrc: [src,...]` delete all proposals of those kinds on the page.
- `delat: [[x,y],...]` delete the smallest box containing the point.
- `relabel: [[x,y,label]]`, `grow: [[x,y,x0,y0,x1,y1]]` modify the box at the point.
- `clear: true` drop all proposals on the page.
- `add: [{r: [x0,y0,x1,y1] | span: {from,to,x0,x1,y0,y1,pad}, label, rot, snap}]`
  - `span` = union of text lines from the first line matching regex `from` to the first later line matching `to`,
    restricted to lines whose centre lies in the x/y window (use x0/x1 for one column of a bilingual two-column page).
    Exact; preferred for clauses. Get anchors with `bpi.py lines KEY "file.pdf" PAGE [y0 y1]`.
  - `r` boxes snap to the text lines whose centres fall inside (except labels Signature, Seal, Supplier logo,
    Initials, Names, Handwritten…, or `"snap": false`) – so a rough box around a paragraph becomes tight.
  - `rot: 90` for content printed sideways (landscape tables on portrait pages): brackets go top/bottom and the
    label is rotated.
`WARN … miss` lines from `sheets`/`build` mean a point edit hit nothing – fix it (proposals change when you re-run
`propose`).

After edits, boxes that overlap substantially are merged and their labels composed; boxes inside a bigger box are
dropped.

## What to look for on every page

1. **Missing**: supplier names in running text, letterhead addresses without a "Tel/Address" keyword, logos,
   amounts written in words, payment clauses (bracket whole clause, both languages), price columns on pages that
   continue a table without its header, signatures (handwriting detection misses faint ones), page initials at the
   bottom corners, seals of Malaysian/foreign subsidiaries that are blue, names in approval screenshots.
2. **False**: `hand?` boxes on two-column text, drawings, punch holes, scan edges; `seal-red` on red translation
   overlays; `seal-blue?` on the submitter's own cross-page seal; `sigfield` boxes over empty signature fields;
   `person` boxes on "(Signature and stamp)" captions; `amount` on capacities ("30万吨", "2.7 Million tons").
3. **Partial**: a box covering "Example Environmental Engineering" but not "Co., Ltd."; an address
   box starting after "No. 33,"; a clause box ending one line early. Partial = leak.
4. **Label quality**: the public label must say what was removed. Merge related items into one block with a
   composed label rather than a dozen tiny boxes.

## Reading QA hits

`qa` re-OCRs the Public PDF at a different resolution, so it often reads correctly a name the cached OCR misread
(cached: one wrong character in the company name, QA: the correct name). A "supplier term visible" hit therefore usually means the supplier regex is
too strict for the misreading in the cache: widen the regex in the terms file (character classes for the
characters that get confused, or anchor on a distinctive fragment of the name), re-run `propose`, `build`, `qa`.
Regexes and span anchors are tied to the OCR backend that produced the cache; when a matter moves between machines
with different backends, keep the `_work/ocr` cache with it instead of re-running OCR.

## Efficient patterns

- Write review files with a small generator script when a long contract repeats the same edit (initials on every
  page, cross-page seal fragments): `"*"` handles "every page"; a script handles "pages 4–21".
- For a contract and its page-identical translation, write edits once and copy them to the translation, then review
  the translation pages that differ.
- Re-run `sheets` only for the files you changed: `bpi.py sheets KEY "file.pdf"`.
- Keep helper scripts outside the skill folder (e.g. in the matter's `_work/`), never edit `scripts/` during a job.
