# bpi-public-versions

**English** | [中文](#中文说明)

An agent skill (`SKILL.md` format) plus a small Python toolkit for preparing **bracketed BPI / business-confidential
versions** and **redacted Public versions** of exhibit documents for US trade proceedings – CBP EAPA requests for
information (19 C.F.R. § 165.4), Commerce / ITC antidumping and countervailing duty questionnaires, APO filings.

It handles real-world exhibit sets: scanned bilingual (Chinese/English) contracts with rotated price tables, invoices
with seals and signatures, purchase orders, overlay translations and Word translations – thousands of pages across
dozens of folders.

## What you get

For every source file, two PDFs with identical page counts and folder structure:

| Version | Content |
|---|---|
| **BPI** | Original pages untouched, red single brackets `[ ]` around every confidential item, "BUSINESS CONFIDENTIAL" header on every page |
| **Public** | Bracketed content permanently removed (scans re-rasterised and painted out; born-digital PDFs truly redacted), black brackets with a summary label ("Supplier name and address", "Quantities, unit prices and amounts"), "PUBLIC VERSION" header on every page, metadata cleared |

Plus `BCI Log.xlsx` – one row per bracket with category and basis, the working base for the required explanation of
why each item is confidential.

## How it works

1. **Read the requirements** (including scanned example pages) and summarise the bracketing conventions.
2. **Survey** the exhibits – counts, scans vs text, disguised non-PDF files, duplicates, translations without originals.
3. **Agree the rules** with the user (supplier identity, quantities, document numbers, whole clauses vs figures …).
4. **Samples first** – a handful of representative files for user review.
5. **Volume pipeline** – OCR → automatic proposals (supplier terms, amounts, bank lines, price columns, payment and
   penalty clauses, seals, handwriting) → page-by-page human-style review on contact sheets with precise text-anchored
   edits → build.
6. **Leak check** – every Public page is OCR'd again and searched for supplier names and bracketed numbers.
7. **Report** – outputs, BCI log, remaining QA hits explained, judgement calls for confirmation.

The skill's instructions are in [`SKILL.md`](SKILL.md); details in [`references/`](references/).

## Installation

1. Python 3.9+ and packages:
   ```
   pip install pymupdf numpy openpyxl pillow rapidocr_onnxruntime
   ```
   On macOS the built-in Vision OCR is used automatically when Xcode Command Line Tools are installed
   (`rapidocr_onnxruntime` is then optional). For Word files install LibreOffice (or MS Word + `pip install docx2pdf`).
2. Copy (or `git clone`) this repository as a folder named `bpi-public-versions` into the skills directory of an
   assistant that supports `SKILL.md` skills. The scripts also work standalone from any terminal.
3. Check the setup from a matter folder:
   ```
   python <skill>/scripts/bpi.py init      # creates bpi_config.json
   python <skill>/scripts/bpi.py doctor
   ```

Windows step-by-step guide: [`docs/windows-install.md`](docs/windows-install.md) (中文版: [`docs/windows-install.zh.md`](docs/windows-install.zh.md)).

## Command reference

```
python scripts/bpi.py init | doctor | survey | ocr | parties
python scripts/bpi.py propose KEY|all     # automatic bracket proposals
python scripts/bpi.py sheets KEY          # review contact sheets
python scripts/bpi.py lines KEY FILE PAGE # text lines with boxes, for precise edits
python scripts/bpi.py build KEY|all       # BPI + Public PDFs
python scripts/bpi.py qa KEY|all          # leak check
python scripts/bpi.py log                 # BCI log spreadsheet
python scripts/bpi.py status
```

Configuration: [`references/config.md`](references/config.md).

## Disclaimer

This toolkit assists with document preparation; it is not legal advice. Bracketing decisions and the final
submission remain the responsibility of the filer and counsel. Always review the outputs before filing.

## License

[MIT](LICENSE)

---

## 中文说明

一个通用技能（`SKILL.md` 格式）及配套 Python 工具，用于为美国贸易调查（CBP EAPA 信息请求、商务部 / ITC 反倾销反补贴问卷、APO 提交等）批量制作附件的 **BPI 版（保密版，原件加括号）** 和 **Public 版（公开版，删除括号内信息并写入概括说明）**。

适用于真实的附件材料：中英双语扫描合同（含横排价格表）、带印章和签字的发票、采购订单、红字叠加译文、Word 译文等，可处理几十个文件夹、数千页。

**输出**
- BPI 版：原件不动，所有保密信息加红色单括号，每页加 “BUSINESS CONFIDENTIAL” 页眉。
- Public 版：括号内内容彻底删除（扫描页重新栅格化后涂白，电子版 PDF 真正删除文字），保留黑色括号并写入英文概括说明，每页加 “PUBLIC VERSION” 页眉，清除元数据。
- `BCI Log.xlsx`：每个括号一行，含类别和保密理由，可作为括号说明的底稿。

**流程**：理解要求文件 → 摸底附件 → 与用户确认括号口径 → 先做样例 → 批量制作（OCR、自动标注、逐页复核、生成）→ 防泄露复查 → 交付报告。

**安装**：见上文 Installation；Windows 详细中文步骤见 [`docs/windows-install.zh.md`](docs/windows-install.zh.md)。

**声明**：本工具仅辅助文件制作，不构成法律意见；括号认定和最终提交由提交方及其律师负责，提交前请务必复核。

许可证：[MIT](LICENSE)
