# Public version from a finished BPI file

Sometimes the user hands over a BPI file that someone else has already bracketed – often one large compiled PDF
with hundreds of exhibits – and asks only for the Public version. The work is then not deciding what is
confidential but **finding every bracket the preparer drew, in whatever form, and erasing exactly what lies
between them**. Every bracket form you fail to recognise becomes a page copied into the Public version unchanged.

The lessons below come from a 1,500-page file in which the brackets had been drawn in more than ten different
ways. Most of the misses were found only by looking at pages, not by any text check.

## 1. Survey the bracket forms before writing any code

Do this on the whole file, not on the first pages:

- **Annotations:** list every annotation type with its count and pages (`PolyLine`, `Ink`, `Line`, `Polygon`,
  `Square`, `Stamp`, `FreeText`, `Highlight` …). Look at each type you do not handle. Brackets drawn as **Stamp**
  annotations (custom "[" and "]" stamps) were missed because only line-type annotations were read.
- **Vector strokes in the page content:** brackets drawn before the file was flattened become plain paths.
  Count strokes by width and shape; do not take thin table rules for brackets.
- **Brackets baked into page images:** a BPI that was printed and scanned, or flattened, carries its marks inside
  the image, with an OCR text layer on top. No annotation or path exists. In the case above about a third of the
  file (≈460 pages) was like this, marked with **corner marks** – "┌" at the top-left and "┘" at the
  bottom-right of each area – sometimes full "[ ]", sometimes thinner marks.
  Find them by keeping only thick strokes (erosion), then looking for two arms of about the mark's arm length that
  meet within a few pixels (the two arms of a scanned corner rarely meet in one pixel).
- **Typed brackets:** "[" and "]" characters in the text, usually in separator-page titles and headings
  ("Exhibit … – [Coal] Documents"). Also:
  - fonts with a custom encoding that **show** "[" and "]" but store other codes ('<' '>', '>' '@', characters in
    the Greek block …). Compare the OCR of the rendered heading with the extracted text to spot them;
  - a bracket that runs over **several lines** of a heading;
  - **large** typed brackets (twice the text size or more) around a whole table;
  - small typed brackets at both ends of **every table row**, i.e. whole rows bracketed;
  - ERP print-outs that use "【…】" as ordinary formatting, and translator notes such as "[Logo]",
    "[Company seal: …]", "[Handwritten signature]" – these are not brackets (but check notes for names).
- **Shapes** that a strict "[ ]" test misses: one arm only, a hook or wobble at an arm end, a slanted spine on a
  skewed scan, arms longer than the spine on short brackets, a bracket built from separate line segments,
  corner pairs (┌ + ┘ or ┐ + └), one "]" closing two "[" drawn one above the other (stepped left edge), and a
  "[" on one line closed by a "]" on the **next** line further left (the area is the rest of line 1 plus the start
  of line 2, not the box between the two marks).

## 2. Pairing

- "[" with "]": the nearest "]" to the right **at the same height**; weigh vertical misalignment heavily, or a tall
  "[" pairs with a small "]" inside the area and the real "]" is left over.
- Corner marks: pair a "┌" with a "┘" so that the rectangle between them contains **no other corner** (the areas
  of one page do not overlap). Plain nearest-distance pairing fails on dense forms.
- A balanced count of left and right marks is not proof: both corners of one area can be missed together.
- Dense forms (customs declarations, inbound sheets) have touching and crossing marks; the detector will be wrong
  on many of them. Where a field is clearly marked but the pairing cannot be settled, erase the **whole field or
  band** – over-erasing a public label is a cosmetic defect, under-erasing is a leak.

## 3. Review before building

- Render every page that has image marks with the found areas (numbered), the unpaired corners (circled) and a
  coordinate grid in PDF points, plus a zoom helper. Reviewers – parallel helpers are fine, one batch of about 60
  pages each – return per page `ok` / `fix` (drop area ids, add corner points) / `unsure`. Settle every `unsure`
  page yourself.
- Thin or very narrow areas are almost always a wrong pairing (a "┌" joined to the "┘" of another area).
- A lone mark at the very corner of many pages, thinner than the real marks and without a partner, can be a
  scanning or flattening artefact; note it, do not invent an area for it.

## 4. Erasing

- Text layer: remove the words whose centre lies between the brackets, word by word (a neighbour that only
  touches the edge stays whole); pixel-redact images in the area; then render and check that no ink is left –
  if outlined text or vector drawings remain, flatten that page to an image.
- **Scanned pages: never move an erase edge inward.** Snapping an edge to the nearest blank row once moved the top
  edge below the first enclosed line (another bracket's arm sat directly above it), and that whole line – a
  bracketed quantity – stayed visible. Let edges grow outward by a few points at most, never shrink.
- Multi-line typed brackets: erase each line's characters separately; the bounding box of the whole bracket also
  covers the heading text before the "[" on the first line.
- Keep the preparer's brackets (or redraw them, corner marks as corner marks) and write a summary label inside.
  Areas too small for any label: count them and tell the user.

## 5. Public-version housekeeping

- Replace the file's own confidentiality marks: "BUSINESS CONFIDENTIAL …", "CONTAINS BUSINESS PROPRIETARY
  INFORMATION", "BCI" on the cover. They occur as page text, as FreeText annotations, and as outlined paths that
  text search cannot find (look at the top margin of pages that have no text mark).
- Bookmarks: remove "BCI"/"BPI" tags, and remove names and terms that are bracketed in the pages (customer names,
  raw-material names in titles). Drop bookmarks with broken targets.
- Flatten annotations into the page before erasing, then clear metadata and XMP.
- Labels: take the text inside each area (OCR when the text layer is garbled), the document type from the
  separator-page title before it (compiled files often have bookmarks pointing at wrong pages), leave the
  submitter's own name and address out of the classification, and read a number glued to its unit
  ("12,345.0000MT") as a quantity, not a reference number.

## 6. Names left outside the brackets

Search the whole file for counterparty names that lie outside every area. Most hits turn out to be covered by a
bracket form you had not recognised yet (in the case above 2 of 11 candidates were real omissions). For the real
ones ask the user; if they are to be bracketed, bracket them in the Public version **and** in a copy of the BPI
file (same bracket style, original left untouched) so that the two versions match.

## 7. Checks before delivery

1. Text layer: no word whose centre lies inside an area survives (words cut by an edge are acceptable).
2. Re-OCR every page that became an image and look for numbers that were inside an area of the same page.
   Dates written with separators produce false hits ("01/02/2025" against an invoice number ending "022025").
3. **Look at every page the build left completely unchanged.** This is where unrecognised bracket forms hide; the
   stamp brackets and several heading brackets in the case above were found this way, not by any check.
4. Every typed bracket pair in the file is either erased or explained.
5. When rebuilding, compare the new file with the delivered one page by page and say which pages changed.

If the user needs the file before all checks are done, deliver it, say plainly which checks are still open, and
patch fixed pages into the delivered file (keeping its bookmarks) as they come.
