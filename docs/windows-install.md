# Windows installation guide

For Windows 10 / 11. Install once; each new matter then only needs its own configuration file.
中文版：[windows-install.zh.md](windows-install.zh.md)

## 1. What you need

| Software | Purpose | Required? |
|---|---|---|
| Python 3.9 or later | Runs the scripts | Yes |
| Python packages (PyMuPDF, numpy, openpyxl, Pillow, RapidOCR) | PDF reading/writing, image processing, Excel output, Chinese/English OCR | Yes |
| LibreOffice (free) | Converts Word translations (.docx) to PDF | Only if there are Word files; an installed Microsoft Word can be used instead |
| An AI assistant that supports `SKILL.md` skills | Follows the skill workflow, reviews pages and runs the scripts | To use the skill; the scripts also run standalone from a terminal |

## 2. Installation steps

### Step 1 – Install Python

1. Go to <https://www.python.org/downloads/windows/> and download the latest Python 3 (64-bit) installer.
2. Run the installer. On the first screen, tick **Add python.exe to PATH**, then click **Install Now**.
3. Press the Windows key, type `cmd` to open Command Prompt, and run:

   ```
   python --version
   ```

   If you see "is not recognized as an internal or external command", run the installer again, choose **Modify**
   and tick *Add Python to environment variables* – or use the `py` command instead of `python`.

### Step 2 – Install the Python packages

```
python -m pip install --upgrade pip
python -m pip install pymupdf numpy openpyxl pillow rapidocr_onnxruntime
```

`rapidocr_onnxruntime` is the OCR engine; its Chinese and English recognition models are bundled, nothing else to
download.

### Step 3 – Install LibreOffice (for Word files)

1. Download the Windows 64-bit version from <https://www.libreoffice.org/download/download/> and install it with the
   default options (default path `C:\Program Files\LibreOffice`); the scripts find it automatically.
2. Alternatively, if Microsoft Word is installed, run `python -m pip install docx2pdf` instead.
3. Skip this step if the exhibits contain no Word files.

### Step 4 – Install the skill

1. Download this repository (**Code → Download ZIP** on GitHub and unzip, or `git clone`). Make sure the folder is
   named `bpi-public-versions` and directly contains `SKILL.md`, `scripts\` and `references\`.
2. Copy the whole folder into the skills directory of your AI assistant (see its documentation for the location),
   or import it through the assistant's settings.
3. Restart the assistant so it loads the skill.

### Step 5 – Check the setup

Open the matter folder (e.g. `D:\Matters\Case A`) in File Explorer, type `cmd` in the address bar and press Enter,
then run (replace `<skills dir>` with the actual path):

```
python "<skills dir>\bpi-public-versions\scripts\bpi.py" init
python "<skills dir>\bpi-public-versions\scripts\bpi.py" doctor
```

`init` creates `bpi_config.json` in the matter folder; `doctor` lists each component as `[ok]` or missing.
`OCR backend: rapidocr` and `ready` mean the installation is complete.

## 3. Using it on a new matter

1. Put the exhibits in a sub-folder of the matter folder, one sub-folder per project (e.g. `205.Rolling Mill Project`).
2. Open `bpi_config.json` in Notepad and fill in:
   - `source_dir` – name of the exhibit folder;
   - `out_bpi` / `out_public` – names of the output folders;
   - `header_left` – left page header, e.g. `EAPA Case No. xxxx | Exhibit xx` (Latin characters only);
   - `own_company_regex` – the submitting company's own names (all languages), address, phone, separated by `|`
     (this information stays public).
3. Tell the assistant: "Use the bpi-public-versions skill to prepare BPI and Public versions of the exhibits in
   `D:\Matters\Case A`", and provide the requirements document (e.g. the RFI).
4. The assistant then works through: read the requirements → survey the exhibits and report problem files → agree
   the bracketing rules with you → samples for your review → full run → leak check → deliver the BPI and Public
   folders and `BCI Log.xlsx`.

## 4. Troubleshooting

- **Garbled Chinese in the console** – run `chcp 65001` first, or add the environment variable `PYTHONUTF8=1`.
- **"pip is not recognized"** – always use `python -m pip …`; if that fails, `py -m pip …`.
- **OCR speed** – RapidOCR takes about 1–3 seconds per page on a typical laptop; 3,000 pages take a few hours.
  Results are cached in `_work\ocr`, so OCR runs only once per matter.
- **Don't re-run OCR on another computer mid-matter** – different machines / OCR engines misread different
  characters, so review edits already written may no longer match. To move a matter, copy the whole matter folder
  including `_work`.
- **Blocked by antivirus** – if the first run is blocked, add Python and the matter folder to the trusted list.
- **Files too large** – if the filing portal limits file size, set `dpi` to 150 and `jpeg_quality` to 70 in
  `bpi_config.json` and rebuild.
- **Path too long errors** – keep the matter folder on a short path (e.g. `D:\Matters\`) or enable long-path
  support in Windows.
