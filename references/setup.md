# Setup (macOS and Windows)

Python 3.9+ and these packages:

```
pip install pymupdf numpy openpyxl pillow
```

OCR (one of):
- **macOS** – nothing extra if Xcode Command Line Tools are installed (`xcode-select --install`): the macOS Vision
  helper `scripts/ocr_vision.swift` is compiled automatically on first use. Best quality for mixed Chinese/English.
- **Windows / Linux / macOS** – `pip install rapidocr_onnxruntime` (PaddleOCR models, good Chinese + English, no
  separate program needed). This is the default on Windows.
- Fallback – Tesseract with Chinese data (`chi_sim`) + `pip install pytesseract`. Weaker on scans.

Word files (.docx translations) are converted to PDF with **LibreOffice** (`soffice`), or with Microsoft Word via
`pip install docx2pdf` if LibreOffice is absent.

Check everything with `python <skill>/scripts/bpi.py doctor`.

## Windows notes

Step-by-step guide: `docs/windows-install.md` in the repository (Chinese: `docs/windows-install.zh.md`).


- Use `python` (or `py`) instead of `python3`. Paths with spaces or Chinese characters are fine – quote them.
- Copy the skill folder `bpi-public-versions` into the skills folder of the assistant you use (or import the packaged
  `.skill` file through its settings).
- If the console shows garbled Chinese, run `chcp 65001` or set the environment variable `PYTHONUTF8=1`.
- RapidOCR runs on the CPU; OCR of ~3,000 pages takes a few hours on a laptop (macOS Vision: ~15 minutes).
  OCR is cached, so it runs once per matter.
- LibreOffice cannot run two conversions at the same time with the same profile – convert Word files once
  (`bpi.py propose all` does it) before starting parallel reviewers.

QR codes / barcodes (optional, used by `bpi.py audit`): detected with the macOS Vision framework when `swiftc` is
available, otherwise with OpenCV if installed (`pip install opencv-python-headless`); without either, check codes by
eye on the Public sheets.
