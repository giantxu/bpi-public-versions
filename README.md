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
5. **Unit by unit** – OCR → automatic proposals (supplier terms, amounts, bank lines, price columns, payment and
   penalty clauses, seals, handwriting) → page-by-page review on contact sheets with text-anchored edits → build.
6. **Three checks** – a text audit (text cut by a bracket edge, sensitive text outside every bracket, a number or
   clause bracketed in one place and visible in another, quantity columns left out, over-bracketing of the
   submitter's own details, of whole tables or of whole pages), a re-OCR of every Public page and of the text at
   every bracket edge (a bracket that starts one character late), and a visual check of every Public page plus
   enlarged cut-outs of seals, signatures and other non-text ink. A unit is finished only when
   `bpi.py gate` prints PASS; findings are fixed or acknowledged with a written reason.
7. **Report** – outputs, BCI log, gate results, acknowledged findings, judgement calls for confirmation.

A Public version can also be made from a BPI file someone else has bracketed: see
[`references/from-bpi.md`](references/from-bpi.md) for the bracket forms to look for (annotations of any type,
typed brackets, marks baked into scanned pages) and the checks that catch the ones a detector misses.

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
python scripts/bpi.py next                      # what to do next in this matter
python scripts/bpi.py init | doctor | survey | ocr | parties | terms-check
python scripts/bpi.py propose KEY|all           # automatic bracket proposals
python scripts/bpi.py sheets KEY                # review contact sheets with box ids
python scripts/bpi.py page KEY FILE PAGE        # one page, large, labelled grid (add "public" / a zoom window)
python scripts/bpi.py lines | boxes KEY FILE [PAGE]   # numbered text lines / what each bracket covers
python scripts/bpi.py check KEY                 # does the edit file apply cleanly?
python scripts/bpi.py build KEY [FILE ...]      # BPI + Public PDFs
python scripts/bpi.py audit KEY                 # leaks, inconsistencies and over-bracketing found in the text
python scripts/bpi.py qa KEY                    # re-OCR leak check of the Public PDFs
python scripts/bpi.py ack KEY ID ... -m "why"   # acknowledge a verified non-leak ; acks = list them
python scripts/bpi.py pubsheets KEY ; viewed KEY CODE ...   # visual check: pages and seal / signature cut-outs
python scripts/bpi.py gate KEY|all              # PASS / FAIL - a unit is finished when its gate passes
python scripts/bpi.py samples-ok "…" | log | status
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

已有他人括好的 BPI 文件、只需制作 Public 版时，见 [`references/from-bpi.md`](references/from-bpi.md)：括号可能是各种批注（包括图章）、打出来的方括号（含特殊编码字体、跨行）、或拍进扫描图片里的拐角标记，需先全文清点括号形式，并逐页查看未改动的页面。

**流程**：理解要求文件 → 摸底附件 → 与用户确认括号口径 → 先做样例 → 逐单元制作（OCR、自动标注、逐页复核、生成）→ 三重防泄露检查（文字自检 `audit`、公开版重新 OCR `qa`、逐页目视）→ `gate` 验收通过 → 交付报告。不确定下一步时运行 `bpi.py next`。

**安装**：见上文 Installation；Windows 详细中文步骤见 [`docs/windows-install.zh.md`](docs/windows-install.zh.md)。

**声明**：本工具仅辅助文件制作，不构成法律意见；括号认定和最终提交由提交方及其律师负责，提交前请务必复核。

许可证：[MIT](LICENSE)
