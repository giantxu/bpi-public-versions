"""Shared configuration, paths and file discovery for the BPI / Public version toolkit.

The matter folder (where you run the commands) holds `bpi_config.json`. Every path in it is relative
to that folder. See references/config.md for all keys.
"""
import os, sys, json, re, subprocess, shutil
from pathlib import Path

# Windows consoles often default to a legacy code page; never crash on Chinese file names.
for _s in (sys.stdout, sys.stderr):
    try:
        _s.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

DEFAULTS = {
    "source_dir": "source",
    "work_dir": "_work",
    "out_bpi": "BPI Version",
    "out_public": "Public Version",
    "header_left": "Case No. ____  |  Exhibit ____",
    "bpi_header": "BUSINESS CONFIDENTIAL  -  Bracketed Information Is Business Confidential",
    "public_header": "PUBLIC VERSION  -  Business Confidential Information Deleted",
    # regex matching text that belongs to the submitting company itself (its name, address, phone,
    # own account numbers). Lines matching it are not treated as supplier contact info.
    "own_company_regex": "(?!x)x",
    "own_code_regex": "(?!x)x",
    "own_seal_text_regex": "(?!x)x",
    # colour of the submitting company's own seal ("blue" / "red" / ""). Seals of that colour are shown
    # as candidates on the review sheets but are NOT bracketed unless the reviewer keeps them.
    "own_seal_color": "",
    # the first N units may be built freely (samples); more only after `bpi.py samples-ok` (0 = no limit)
    "sample_units_limit": 3,
    "dpi": 200,
    "jpeg_quality": 82,
    "ocr_backend": "auto",          # auto | vision | rapidocr | tesseract
    "ocr_dpi": 150,
    "soffice": "",                   # path to LibreOffice soffice; empty = search PATH / default locations
}


def clean_rx(p):
    """drop a leading inline flag group such as (?i) so patterns can be combined safely"""
    return re.sub(r"^\s*\(\?[aiLmsux]+\)", "", p or "")


def rx_join(*pats):
    """one case-insensitive regex matching any of the given patterns"""
    return re.compile("|".join(f"(?:{clean_rx(p)})" for p in pats if p), re.I)


def find_config():
    env = os.environ.get("BPI_CONFIG")
    if env:
        return Path(env).resolve()
    p = Path.cwd().resolve()
    for d in [p, *p.parents]:
        if (d / "bpi_config.json").exists():
            return d / "bpi_config.json"
    raise SystemExit("bpi_config.json not found (run from the matter folder or set BPI_CONFIG). "
                     "Create one with:  python bpi.py init")


class Cfg:
    def __init__(self, path=None):
        self.path = Path(path) if path else find_config()
        self.root = self.path.parent
        data = dict(DEFAULTS)
        data.update(json.loads(self.path.read_text(encoding="utf-8")))
        self.data = data
        self.src = self.root / data["source_dir"]
        self.work = self.root / data["work_dir"]
        self.out_bpi = self.root / data["out_bpi"]
        self.out_pub = self.root / data["out_public"]
        try:
            self.own_re = rx_join(data["own_company_regex"])
            rx_join(data["own_code_regex"]); rx_join(data["own_seal_text_regex"])
        except re.error as e:
            raise SystemExit(f"bpi_config.json: invalid regular expression in an own_* key: {e}")
        self.work.mkdir(parents=True, exist_ok=True)

    def __getitem__(self, k):
        return self.data[k]

    # ------------------------------------------------------------------ units (sub-folders)
    def units(self):
        """list of (key, folder name). A unit is one sub-folder of source_dir; files lying directly in
        source_dir form the unit '_root'. key = leading token before the first '.' when it is unique
        (e.g. '205' for '205.Rolling Mill Project'), otherwise the whole folder name."""
        dirs = sorted(d.name for d in self.src.iterdir() if d.is_dir() and not d.name.startswith("."))
        prefixes = [d.split(".")[0] for d in dirs]
        res = []
        for d, p in zip(dirs, prefixes):
            res.append((p if prefixes.count(p) == 1 and p != d else d, d))
        if any(f.is_file() and not f.name.startswith(".") for f in self.src.iterdir()):
            res.append(("_root", "."))
        return res

    def unit(self, key):
        for k, d in self.units():
            if k == key or d == key:
                return k, d
        raise SystemExit(f"no unit {key!r}; known: {[k for k, _ in self.units()]}")

    def unit_dir(self, folder):
        return self.src if folder == "." else self.src / folder

    def out_dir(self, root, folder):
        return root if folder == "." else root / folder

    # ------------------------------------------------------------------ state / restrictions
    def state(self):
        p = self.work / "state.json"
        return json.loads(p.read_text(encoding="utf-8")) if p.exists() else {}

    def save_state(self, st):
        (self.work / "state.json").write_text(json.dumps(st, ensure_ascii=False, indent=1), encoding="utf-8")

    def may_write(self, key):
        """environment variable BPI_UNITS=205,206 restricts this process to those units (unset = all).
        Give each parallel reviewer its own BPI_UNITS so nobody can overwrite another reviewer's units.
        Use ";" as separator when a unit key itself contains a comma."""
        env = os.environ.get("BPI_UNITS", "").strip()
        if not env:
            return True
        parts = [k.strip() for k in (env.split(";") if ";" in env else env.split(","))]
        return key in parts or key == env or ("," in key and ";" not in env and all(x in parts for x in key.split(",")))

    # ------------------------------------------------------------------ terms
    def terms(self, key):
        res = []
        g = self.work / "terms.json"
        if g.exists():
            t = json.loads(g.read_text(encoding="utf-8"))
            res += t.get("*", []) + t.get(key, [])
        u = self.work / f"terms_{key}.json"
        if u.exists():
            res += json.loads(u.read_text(encoding="utf-8"))
        out = []
        for x in res:
            try:
                re.compile(x[0])
            except re.error as e:
                raise SystemExit(f"terms file: invalid regular expression {x[0]!r}: {e}")
            out.append(tuple(x))
        return out


def is_pdf(p):
    with open(p, "rb") as f:
        return f.read(5) == b"%PDF-"


def soffice_path(cfg):
    if cfg["soffice"]:
        return cfg["soffice"]
    for name in ("soffice", "soffice.exe", "libreoffice"):
        p = shutil.which(name)
        if p:
            return p
    for p in (r"C:\Program Files\LibreOffice\program\soffice.exe",
              r"C:\Program Files (x86)\LibreOffice\program\soffice.exe",
              "/Applications/LibreOffice.app/Contents/MacOS/soffice"):
        if os.path.exists(p):
            return p
    return None


def docx_to_pdf(cfg, folder, name):
    """convert a .docx to PDF once (cached under work/docxpdf). LibreOffice first, then MS Word via docx2pdf."""
    out = cfg.work / "docxpdf" / folder
    out.mkdir(parents=True, exist_ok=True)
    pdf = out / (Path(name).stem + ".pdf")
    if pdf.exists():
        return pdf
    src = cfg.unit_dir(folder) / name
    so = soffice_path(cfg)
    if so:
        subprocess.run([so, "--headless", "--convert-to", "pdf", "--outdir", str(out), str(src)],
                       capture_output=True)
    if not pdf.exists():
        try:
            from docx2pdf import convert  # uses Microsoft Word (Windows / macOS)
            convert(str(src), str(pdf))
        except Exception as e:
            raise SystemExit(f"cannot convert {src} to PDF: install LibreOffice (or MS Word + pip install docx2pdf). {e}")
    return pdf


def file_mode(p):
    """'text' for born-digital PDFs (true redaction keeps them searchable), else 'scan' (re-rasterised)."""
    from compat import fitz
    doc = fitz.open(p)
    for pg in doc:
        area = pg.rect.width * pg.rect.height
        big = any(r.width * r.height > 0.3 * area for img in pg.get_images(full=True)
                  for r in pg.get_image_rects(img[0]))
        if big or len(pg.get_text().strip()) < 30:
            return "scan"
    return "text"


def files(cfg, folder):
    """list of (source name, pdf path, mode, output name). Word files are converted to PDF; a converted
    translation whose stem collides with a PDF gets '_EN' appended. Non-PDF files that merely carry a
    .pdf extension (e.g. saved web pages) are skipped - `survey` reports them."""
    res = []
    d = cfg.unit_dir(folder)
    names = sorted(n.name for n in d.iterdir() if n.is_file() and not n.name.startswith(("~$", ".")))
    stems = {Path(n).stem for n in names if n.lower().endswith(".pdf")}
    for f in names:
        p = d / f
        low = f.lower()
        if low.endswith((".docx", ".doc")):
            stem = Path(f).stem
            out = stem + ("_EN" if stem in stems and "EN" not in stem else "") + ".pdf"
            res.append((f, docx_to_pdf(cfg, folder, f), "text", out))
        elif low.endswith(".pdf") and is_pdf(p):
            res.append((f, p, file_mode(p), f))
    return res


def safe(folder):
    return "_root" if folder == "." else folder
