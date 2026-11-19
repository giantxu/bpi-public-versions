"""OCR with line-level boxes, cross-platform.

Backends (config "ocr_backend", default auto):
  vision     macOS Vision framework (best Chinese/English quality on a Mac; compiled once with swiftc)
  rapidocr   RapidOCR / PaddleOCR models via onnxruntime - pip install rapidocr_onnxruntime (Windows/Linux/macOS)
  tesseract  Tesseract with chi_sim+eng - needs the tesseract program + pip install pytesseract
Every backend returns a list of {"t","x","y","w","h"} with coordinates normalised to the image (top-left origin).
"""
import json, os, platform, shutil, subprocess, sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
_engine = {}


def _vision_bin(work):
    exe = Path(work) / "bin" / "ocr_vision"
    if not exe.exists():
        if not shutil.which("swiftc"):
            return None
        exe.parent.mkdir(parents=True, exist_ok=True)
        r = subprocess.run(["swiftc", "-O", str(HERE / "ocr_vision.swift"), "-o", str(exe)], capture_output=True, text=True)
        if r.returncode != 0:
            return None
    return exe


def pick_backend(cfg):
    want = cfg["ocr_backend"]
    if want in ("vision", "auto") and platform.system() == "Darwin" and _vision_bin(cfg.work):
        return "vision"
    if want in ("rapidocr", "auto"):
        try:
            import rapidocr_onnxruntime  # noqa
            return "rapidocr"
        except ImportError:
            if want == "rapidocr":
                raise SystemExit("pip install rapidocr_onnxruntime")
    if want in ("tesseract", "auto"):
        try:
            import pytesseract  # noqa
            if shutil.which("tesseract") or os.path.exists(r"C:\Program Files\Tesseract-OCR\tesseract.exe"):
                return "tesseract"
        except ImportError:
            pass
    raise SystemExit("No OCR backend available. Windows/Linux: pip install rapidocr_onnxruntime ; "
                     "macOS: install Xcode command line tools (swiftc) or rapidocr_onnxruntime.")


def _poly_to_box(poly, W, H):
    xs = [p[0] for p in poly]; ys = [p[1] for p in poly]
    return {"x": min(xs) / W, "y": min(ys) / H, "w": (max(xs) - min(xs)) / W, "h": (max(ys) - min(ys)) / H}


def ocr_png(cfg, png, backend=None):
    backend = backend or pick_backend(cfg)
    if backend == "vision":
        r = subprocess.run([str(_vision_bin(cfg.work)), str(png)], capture_output=True, text=True)
        return json.loads(r.stdout or "[]")
    from PIL import Image
    W, H = Image.open(png).size
    if backend == "rapidocr":
        from rapidocr_onnxruntime import RapidOCR
        eng = _engine.setdefault("rapid", RapidOCR())
        result, _ = eng(str(png))
        out = []
        for poly, text, score in result or []:
            d = _poly_to_box(poly, W, H); d["t"] = text; out.append(d)
        return out
    if backend == "tesseract":
        import pytesseract
        if not shutil.which("tesseract") and os.path.exists(r"C:\Program Files\Tesseract-OCR\tesseract.exe"):
            pytesseract.pytesseract.tesseract_cmd = r"C:\Program Files\Tesseract-OCR\tesseract.exe"
        data = pytesseract.image_to_data(Image.open(png), lang="chi_sim+eng", output_type=pytesseract.Output.DICT)
        lines = {}
        for i, t in enumerate(data["text"]):
            if not t.strip():
                continue
            k = (data["block_num"][i], data["par_num"][i], data["line_num"][i])
            x, y, w, h = data["left"][i], data["top"][i], data["width"][i], data["height"][i]
            L = lines.setdefault(k, {"t": [], "x0": x, "y0": y, "x1": x + w, "y1": y + h})
            L["t"].append(t); L["x0"] = min(L["x0"], x); L["y0"] = min(L["y0"], y)
            L["x1"] = max(L["x1"], x + w); L["y1"] = max(L["y1"], y + h)
        return [{"t": " ".join(L["t"]), "x": L["x0"] / W, "y": L["y0"] / H,
                 "w": (L["x1"] - L["x0"]) / W, "h": (L["y1"] - L["y0"]) / H} for L in lines.values()]
    raise SystemExit("unknown OCR backend " + backend)


def ocr_page(cfg, page, dpi=None, backend=None):
    """OCR one fitz page (rotation removed by caller)."""
    import tempfile
    dpi = dpi or cfg["ocr_dpi"]
    fd, png = tempfile.mkstemp(suffix=".png"); os.close(fd)
    try:
        page.get_pixmap(dpi=dpi).save(png)
        return ocr_png(cfg, png, backend)
    finally:
        try:
            os.remove(png)
        except OSError:
            pass


def ocr_all(cfg, keys=None, workers=None):
    """OCR every page of every scanned PDF (cached in work/ocr/<folder>/<file>/pNNN.json)."""
    from compat import fitz
    from concurrent.futures import ThreadPoolExecutor
    import cfg as C
    backend = pick_backend(cfg)
    print("OCR backend:", backend, flush=True)
    jobs = []
    for key, folder in cfg.units():
        if keys and key not in keys:
            continue
        for f, path, mode, out in C.files(cfg, folder):
            if mode != "scan":
                continue
            n = len(fitz.open(path))
            for i in range(n):
                o = cfg.work / "ocr" / C.safe(folder) / f / f"p{i + 1:03d}.json"
                if not o.exists():
                    jobs.append((path, i, o))
    print("pages to OCR:", len(jobs), flush=True)

    def work(j):
        path, i, o = j
        o.parent.mkdir(parents=True, exist_ok=True)
        page = fitz.open(path)[i]
        if page.rotation:
            page.remove_rotation()
        try:
            res = ocr_page(cfg, page, backend=backend)
        except Exception as e:
            print("OCR failed", path, i + 1, e, flush=True); res = []
        o.write_text(json.dumps(res, ensure_ascii=False), encoding="utf-8")

    # vision runs as separate processes -> threads parallelise well; rapidocr/tesseract are CPU bound
    workers = workers or (6 if backend == "vision" else max(1, (os.cpu_count() or 2) // 2))
    done = 0
    with ThreadPoolExecutor(workers if backend != "rapidocr" else 1) as ex:
        for _ in ex.map(work, jobs):
            done += 1
            if done % 50 == 0:
                print(done, "/", len(jobs), flush=True)
    print("OCR finished", flush=True)
