# bpi_config.json

Created by `bpi.py init` in the matter folder. Paths are relative to that folder.

```json
{
  "source_dir": "Exhibit 12 purchase records",
  "work_dir": "_work",
  "out_bpi": "Exhibit 12 - BPI Version",
  "out_public": "Exhibit 12 - Public Version",
  "header_left": "EAPA Case No. 0000  |  Exhibit 12",
  "bpi_header": "BUSINESS CONFIDENTIAL  -  Bracketed Information Is Business Confidential",
  "public_header": "PUBLIC VERSION  -  Business Confidential Information Deleted",
  "own_company_regex": "(?i)example\\s*steel|示例钢铁|123456-X|industrial\\s*park\\s*road|09-?123\\s*4567",
  "own_code_regex": "EXS|EXSB|CT\\d+\\w*",
  "own_seal_text_regex": "CONTRACT|123456",
  "own_seal_color": "blue",
  "dpi": 200,
  "jpeg_quality": 82,
  "ocr_backend": "auto",
  "ocr_dpi": 150,
  "soffice": ""
}
```

- `source_dir` – the exhibit folder; each sub-folder is a *unit* (key = its numeric prefix, e.g. `205` for `205.Rolling Mill Project`), files lying
  directly in it form unit `_root`. Output folders mirror the sub-folders and file names.
- Header texts use the PDF base-14 fonts: **Latin characters only** (English headers are what US agencies expect).
  Labels inside brackets are English for the same reason.
- `own_company_regex` – submitter's own names (all languages, common OCR misreads), address fragments, phone, own
  account numbers. Lines matching it are not treated as supplier contact lines; the submitter's bank *name* stays
  public while its account number is still bracketed.
- `own_code_regex` – segments of the submitter's own document codes (its company prefix, its contract-number
  pattern). In invoice numbers any other alphabetic segment of 3+ letters is treated as a counterparty code and the
  whole number is bracketed (`invno`).
- `own_seal_text_regex` – words readable on the submitter's own seal (registration number, "CONTRACT", …); a seal
  whose OCR text matches it is never proposed as a supplier seal.
- `dpi` / `jpeg_quality` – resolution and quality of re-rasterised Public pages (200 / 82 ≈ 0.25 MB per A4 page).
  Lower them (150 / 70) if the filing portal limits file size.
- `ocr_backend` – `auto` picks macOS Vision on a Mac, else RapidOCR, else Tesseract. `ocr_dpi` 150 is a good balance.
- `soffice` – path to LibreOffice if not on PATH (Windows default locations are searched automatically).

Work folder layout: `ocr/` OCR cache · `auto/` proposals · `review/KEY.json` edits · `terms.json`, `terms_KEY.json`
supplier regexes · `sheets/KEY/` contact sheets · `docxpdf/` converted Word files · `rules.md` agreed rules.
