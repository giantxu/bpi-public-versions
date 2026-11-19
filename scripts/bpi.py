#!/usr/bin/env python3
"""BPI / Public version toolkit - one CLI for the whole workflow.

Run from the matter folder (the one holding bpi_config.json):

  python bpi.py init                     create bpi_config.json + _work/ skeleton
  python bpi.py doctor                   check Python packages, OCR backend, LibreOffice
  python bpi.py survey                   inventory: units, files, pages, scans vs text, problems
  python bpi.py ocr [KEY ...]            OCR all scanned pages (cached)
  python bpi.py parties [KEY ...]        list company-like names found by OCR (to build supplier terms)
  python bpi.py propose KEY|all          automatic bracket proposals -> _work/auto/
  python bpi.py sheets KEY [FILE ...]    review contact sheets -> _work/sheets/KEY/sheet_###.png
  python bpi.py lines KEY FILE PAGE [Y0 Y1]   OCR/text lines with boxes (for precise span edits)
  python bpi.py build KEY|all            write BPI + Public PDFs
  python bpi.py qa KEY|all               re-OCR Public PDFs and look for leaked bracketed content
  python bpi.py log [KEY ...]            BCI log spreadsheet (one row per bracket)
  python bpi.py status                   which units are proposed / reviewed / built / stale

KEY = unit key shown by `survey` (normally the numeric prefix of a sub-folder, e.g. 205).
"""
import os, sys, json, re, shutil, hashlib
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import cfg as C

COLORS = {"term": (0.9, 0, 0), "bank": (0, 0, 0.9), "contact": (0, 0.55, 0.9), "person": (0.6, 0, 0.6),
          "pay": (0.9, 0.5, 0), "ld": (0.9, 0.5, 0), "amount": (0, 0.6, 0), "table": (0, 0.6, 0),
          "seal-red": (1, 0, 0.5), "seal-blue?": (0.3, 0.3, 1), "hand?": (1, 0.6, 0), "sigfield": (0.5, 0.3, 0),
          "manual": (0, 0, 0)}
NOSNAP = ("Signature", "Seal", "Supplier logo", "Initials", "Names")


# =========================================================================== helpers
def native_lines(page):
    W_, H_ = page.rect.width, page.rect.height
    out = []
    for b in page.get_text("dict")["blocks"]:
        for l in b.get("lines", []):
            t = "".join(s["text"] for s in l["spans"])
            if not t.strip():
                continue
            x0, y0, x1, y1 = l["bbox"]
            out.append({"t": t, "x": x0 / W_, "y": y0 / H_, "w": (x1 - x0) / W_, "h": (y1 - y0) / H_})
    return out


def page_lines(cfg, folder, f, mode, i, page):
    if mode == "text":
        return native_lines(page)
    j = cfg.work / "ocr" / C.safe(folder) / f / f"p{i + 1:03d}.json"
    return json.loads(j.read_text(encoding="utf-8")) if j.exists() else []


_LINES = {}


def lines_cached(cfg, folder, f, spec, pg):
    from compat import fitz
    k = (folder, f, pg)
    if k not in _LINES:
        page = fitz.open(spec["src"])[pg - 1]
        if page.rotation:
            page.remove_rotation()
        _LINES[k] = page_lines(cfg, folder, f, spec["mode"], pg - 1, page)
    return _LINES[k]


def keys_arg(cfg, args):
    if not args or args == ["all"]:
        return [k for k, _ in cfg.units()]
    return args


def auto_path(cfg, folder, f):
    return cfg.work / "auto" / C.safe(folder) / f"{f}.json"


# =========================================================================== init / doctor / survey
def cmd_init(_):
    p = Path.cwd() / "bpi_config.json"
    if p.exists():
        print("bpi_config.json already exists"); return
    cfgd = {k: v for k, v in C.DEFAULTS.items()}
    p.write_text(json.dumps(cfgd, ensure_ascii=False, indent=2), encoding="utf-8")
    w = Path.cwd() / cfgd["work_dir"]
    (w / "review").mkdir(parents=True, exist_ok=True)
    if not (w / "terms.json").exists():
        (w / "terms.json").write_text(json.dumps({"*": []}, indent=1), encoding="utf-8")
    print("created", p, "- edit source_dir, out_* folders, headers and own_company_regex")


def cmd_doctor(_):
    ok = True
    for mod, pipname in (("fitz", "pymupdf"), ("numpy", "numpy"), ("openpyxl", "openpyxl"), ("PIL", "pillow")):
        try:
            __import__(mod); print(f"[ok] {pipname}")
        except ImportError:
            ok = False; print(f"[missing] pip install {pipname}")
    try:
        cfg = C.Cfg()
        import ocr
        print("[ok] OCR backend:", ocr.pick_backend(cfg))
        print("[ok] LibreOffice:" if C.soffice_path(cfg) else "[info] LibreOffice not found (needed only for .docx; "
              "alternative: MS Word + pip install docx2pdf)", C.soffice_path(cfg) or "")
        print("[ok] source folder:" if cfg.src.exists() else "[missing] source folder:", cfg.src)
    except SystemExit as e:
        ok = False; print("[problem]", e)
    print("ready" if ok else "fix the items above")


def cmd_survey(_):
    from compat import fitz
    cfg = C.Cfg()
    tot_pages = scanned = 0
    hashes = {}
    problems = []
    print(f"{'key':10s} {'files':>5s} {'pages':>6s}  folder")
    for key, folder in cfg.units():
        d = cfg.unit_dir(folder)
        n_files = n_pages = 0
        for p in sorted(d.iterdir()):
            if not p.is_file() or p.name.startswith((".", "~$")):
                continue
            h = hashlib.md5(p.read_bytes()).hexdigest()
            hashes.setdefault(h, []).append(f"{folder}/{p.name}")
            low = p.name.lower()
            if low.endswith(".pdf"):
                if not C.is_pdf(p):
                    head = p.read_bytes()[:300].decode("utf-8", "ignore").lower()
                    problems.append(f"NOT A PDF (looks like {'HTML/web page' if '<html' in head or 'doctype' in head else 'other'}): {folder}/{p.name}")
                    continue
                doc = fitz.open(p); n_files += 1; n_pages += len(doc)
                if C.file_mode(p) == "scan":
                    scanned += 1
            elif low.endswith((".docx", ".doc")):
                n_files += 1; n_pages += 0
            else:
                problems.append(f"other file type (not processed): {folder}/{p.name}")
            stem = re.sub(r"(?i)[-_ ]*(appendix)?[-_ ]*EN$", "", p.stem)
            if re.search(r"(?i)EN$", p.stem) and not any(q.stem == stem for q in d.iterdir() if q != p and not re.search(r"(?i)EN$", q.stem)):
                problems.append(f"translation without an obviously matching original: {folder}/{p.name}")
        tot_pages += n_pages
        print(f"{key:10s} {n_files:5d} {n_pages:6d}  {folder}")
    for h, ps in hashes.items():
        if len(ps) > 1:
            problems.append("IDENTICAL FILES: " + " = ".join(ps))
    print(f"\nPDF pages: {tot_pages}   scanned PDFs: {scanned}")
    print("\nProblems to raise with the user:" if problems else "\nNo problems found.")
    for p in problems:
        print("  -", p)


def cmd_ocr(args):
    import ocr
    cfg = C.Cfg()
    ocr.ocr_all(cfg, args or None)


def cmd_parties(args):
    """company-like strings per unit, de-duplicated, to help write supplier terms."""
    cfg = C.Cfg()
    pat = re.compile(r"(?i)公司|co\.?,?\s*ltd|sdn\.?\s*bhd|corp|limited|inc\b|gmbh|集团|研究院|设计院|llc|s\.a\.|pte")
    for key, folder in cfg.units():
        if args and key not in args:
            continue
        seen, out = set(), []
        for j in sorted((cfg.work / "ocr" / C.safe(folder)).glob("*/p*.json")):
            for d in json.loads(j.read_text(encoding="utf-8")):
                t = d["t"].strip()
                if pat.search(t) and len(t) < 80 and not cfg.own_re.search(t):
                    k = re.sub(r"[^A-Za-z一-鿿]", "", t).lower()[:10]
                    if k and k not in seen:
                        seen.add(k); out.append(t)
        for f, path, mode, _ in C.files(cfg, folder):
            if mode == "text":
                from compat import fitz
                for page in fitz.open(path):
                    for d in native_lines(page):
                        t = d["t"].strip()
                        if pat.search(t) and len(t) < 80 and not cfg.own_re.search(t):
                            k = re.sub(r"[^A-Za-z一-鿿]", "", t).lower()[:10]
                            if k and k not in seen:
                                seen.add(k); out.append(t)
        print(f"== {key}: " + " | ".join(out[:30]))


# =========================================================================== propose
def cmd_propose(args):
    from compat import fitz
    import propose as P
    import seals
    cfg = C.Cfg()
    P.set_own(cfg["own_company_regex"])
    for key in keys_arg(cfg, args):
        key, folder = cfg.unit(key)
        terms = cfg.terms(key)
        for f, path, mode, out in C.files(cfg, folder):
            doc = fitz.open(path)
            spec = {"mode": mode, "src": str(path), "out": out, "pages": {}}
            for i, page in enumerate(doc):
                if page.rotation:
                    page.remove_rotation()
                lines = page_lines(cfg, folder, f, mode, i, page)
                props = P.propose(lines, terms, mode)
                if mode == "scan":
                    for b in seals.color_boxes(page, "red"):
                        props.append({"r": [round(v, 4) for v in b[:4]], "label": "Seal", "rot": 0, "src": "seal-red"})
                    tb = [[d["x"], d["y"], d["x"] + d["w"], d["y"] + d["h"]] for d in lines]
                    for b in seals.handwriting_boxes(page, tb):
                        props.append({"r": [round(v, 4) for v in b], "label": "Signature", "rot": 0, "src": "hand?"})
                    for b in seals.color_boxes(page, "blue"):
                        props.append({"r": [round(v, 4) for v in b[:4]], "label": "Seal", "rot": 0, "src": "seal-blue?"})
                spec["pages"][str(i + 1)] = props
            ap = auto_path(cfg, folder, f)
            ap.parent.mkdir(parents=True, exist_ok=True)
            ap.write_text(json.dumps(spec, ensure_ascii=False), encoding="utf-8")
            n = sum(len(v) for v in spec["pages"].values())
            print(f"{key:8s} {f[:60]:60s} {mode:5s} pages={len(doc):4d} proposals={n}")


# =========================================================================== edits -> final spec
def span_box(cfg, folder, f, spec, pg, sp):
    ls = lines_cached(cfg, folder, f, spec, pg)
    x0, x1 = sp.get("x0", 0), sp.get("x1", 1); y0, y1 = sp.get("y0", 0), sp.get("y1", 1)
    ls = [d for d in ls if x0 <= d["x"] + d["w"] / 2 <= x1 and y0 <= d["y"] + d["h"] / 2 <= y1]
    ls.sort(key=lambda d: (round(d["y"], 3), d["x"]))
    start = next((k for k, d in enumerate(ls) if re.search(sp["from"], d["t"])), None)
    if start is None:
        raise SystemExit(f"span from {sp['from']!r} not found: {f} p{pg}")
    to = sp.get("to", sp["from"])
    end = next((k for k in range(start, len(ls)) if re.search(to, ls[k]["t"])), None)
    if end is None:
        raise SystemExit(f"span to {to!r} not found: {f} p{pg}")
    sel = ls[start:end + 1]
    pad = sp.get("pad", 0.005)
    return [round(min(d["x"] for d in sel) - pad, 4), round(min(d["y"] for d in sel) - pad, 4),
            round(max(d["x"] + d["w"] for d in sel) + pad, 4), round(max(d["y"] + d["h"] for d in sel) + pad, 4)]


def snap_box(cfg, folder, f, spec, pg, r, pad=0.005):
    ls = [d for d in lines_cached(cfg, folder, f, spec, pg)
          if r[0] <= d["x"] + d["w"] / 2 <= r[2] and r[1] <= d["y"] + d["h"] / 2 <= r[3]]
    if not ls:
        return r
    return [round(min(d["x"] for d in ls) - pad, 4), round(min(d["y"] for d in ls) - pad, 4),
            round(max(d["x"] + d["w"] for d in ls) + pad, 4), round(max(d["y"] + d["h"] for d in ls) + pad, 4)]


def _auto_labels(props):
    for q in props:
        r = q["r"]
        if q["src"] in ("hand?", "seal-blue?") and r[3] < 0.17:
            q["label"] = "Supplier logo"
        elif q["src"] == "seal-blue?" and r[2] - r[0] > 0.55:
            q["label"] = "Supplier letterhead"
    return props


def _pick(props, pt):
    hits = [q for q in props if q["r"][0] <= pt[0] <= q["r"][2] and q["r"][1] <= pt[1] <= q["r"][3]]
    return min(hits, key=lambda q: (q["r"][2] - q["r"][0]) * (q["r"][3] - q["r"][1])) if hits else None


CAT = [("Invoice No.", "invoice number (contains supplier abbreviation)"), ("logo", "supplier logo"),
       ("letterhead", "supplier letterhead"), ("Supplier name and address", "supplier name and address"),
       ("Supplier name", "supplier name"), ("contact", "supplier contact information"),
       ("Bank", "bank account / tax ID"), ("Seal", "seal"), ("Signature", "signature"), ("Name", "personal name"),
       ("Payment", "payment terms"), ("Liquidated", "liquidated damages terms"), ("Quantities", "quantities and prices"),
       ("price", "price"), ("Amount", "amounts"), ("ratio", "payment ratio")]


def compose(labels):
    uniq = []
    for l in labels:
        if l not in uniq:
            uniq.append(l)
    if len(uniq) == 1:
        return uniq[0]
    cats = []
    for l in uniq:
        c = next((v for k, v in CAT if k.lower() in l.lower()), l.lower())
        if c not in cats and not any(c in x for x in cats):
            cats = [x for x in cats if x not in c] + [c]
    if len(cats) == 1:
        return uniq[0] if len(uniq[0]) > len(cats[0]) else cats[0][0].upper() + cats[0][1:]
    txt = ", ".join(cats[:-1]) + " and " + cats[-1]
    return txt[0].upper() + txt[1:]


def _merge_overlaps(cur):
    changed = True
    while changed:
        changed = False
        for i in range(len(cur)):
            for j in range(i + 1, len(cur)):
                a, b = cur[i]["r"], cur[j]["r"]
                ix = min(a[2], b[2]) - max(a[0], b[0]); iy = min(a[3], b[3]) - max(a[1], b[1])
                small_area = min((a[2] - a[0]) * (a[3] - a[1]), (b[2] - b[0]) * (b[3] - b[1]))
                same = cur[i].get("src") == cur[j].get("src")
                if ix > 0.002 and iy > 0.002 and (same or ix * iy > 0.25 * small_area):
                    big, small = (cur[i], cur[j]) if (a[2] - a[0]) * (a[3] - a[1]) >= (b[2] - b[0]) * (b[3] - b[1]) else (cur[j], cur[i])
                    big["r"] = [min(a[0], b[0]), min(a[1], b[1]), max(a[2], b[2]), max(a[3], b[3])]
                    big["labels"] = big.get("labels", [big["label"]]) + small.get("labels", [small["label"]])
                    big["label"] = compose(big["labels"])
                    if small.get("rot") and not big.get("rot"):
                        big["rot"] = small["rot"]
                    cur.remove(small); changed = True
                    break
            if changed:
                break
    return cur


def final_spec(cfg, key, folder, f):
    """auto proposals + review edits (_work/review/<KEY>.json). Edit ops per page (or "*" = every page):
       clear | delsrc | delat | relabel | grow | add  (see references/review-guide.md)"""
    spec = json.loads(auto_path(cfg, folder, f).read_text(encoding="utf-8"))
    for pg in spec["pages"]:
        spec["pages"][pg] = _auto_labels(spec["pages"][pg])
    rv = cfg.work / "review" / f"{key}.json"
    edits = json.loads(rv.read_text(encoding="utf-8")).get(f, {}) if rv.exists() else {}
    allp = edits.get("*", {})
    for pg in list(spec["pages"]):
        e = dict(allp)
        for k, v in edits.get(pg, {}).items():
            e[k] = (e.get(k, []) + v) if isinstance(v, list) else v
        if not e:
            continue
        cur = [] if e.get("clear") else [dict(q) for q in spec["pages"][pg]]
        cur = [q for q in cur if q["src"] not in set(e.get("delsrc", []))]
        for x, y, lab in e.get("relabel", []):
            q = _pick(cur, (x, y))
            if q: q["label"] = lab
            else: print(f"WARN relabel miss {f} p{pg} {x},{y}")
        for g in e.get("grow", []):
            q = _pick(cur, g[:2])
            if q: q["r"] = [min(q["r"][0], g[2]), min(q["r"][1], g[3]), max(q["r"][2], g[4]), max(q["r"][3], g[5])]
            else: print(f"WARN grow miss {f} p{pg}")
        for pt in e.get("delat", []):
            q = _pick(cur, pt)
            if q: cur.remove(q)
            else: print(f"WARN delat miss {f} p{pg} {pt}")
        for a in e.get("add", []):
            a = dict(a); a.setdefault("rot", 0); a.setdefault("src", "manual")
            if "span" in a:
                a["r"] = span_box(cfg, folder, f, spec, int(pg), a.pop("span"))
            elif a.get("snap", True) and a["label"] not in NOSNAP and not a["label"].startswith("Handwritten"):
                a["r"] = snap_box(cfg, folder, f, spec, int(pg), a["r"])
            a.pop("snap", None)
            cur.append(a)
        spec["pages"][pg] = cur
    for pg in list(spec["pages"]):
        spec["pages"][pg] = _merge_overlaps(spec["pages"][pg])
    for pg, cur in spec["pages"].items():  # drop boxes lying inside a bigger box
        keep = []
        for q in cur:
            r = q["r"]
            inside = any(o is not q and o["r"][0] - .004 <= r[0] and o["r"][1] - .004 <= r[1] and r[2] <= o["r"][2] + .004
                         and r[3] <= o["r"][3] + .004 and (o["r"][2] - o["r"][0]) * (o["r"][3] - o["r"][1]) > (r[2] - r[0]) * (r[3] - r[1])
                         for o in cur)
            if not inside:
                keep.append(q)
        spec["pages"][pg] = keep
    return spec


# =========================================================================== sheets / lines
def cmd_sheets(args):
    from compat import fitz
    cfg = C.Cfg()
    key, folder = cfg.unit(args[0])
    only = set(args[1:]) or None
    od = cfg.work / "sheets" / key
    shutil.rmtree(od, ignore_errors=True)
    od.mkdir(parents=True, exist_ok=True)
    tiles = []
    for f, path, mode, out in C.files(cfg, folder):
        if only and f not in only:
            continue
        spec = final_spec(cfg, key, folder, f)
        doc = fitz.open(path)
        for i, page in enumerate(doc):
            if page.rotation:
                page.remove_rotation()
            props = spec["pages"].get(str(i + 1), [])
            tmp = fitz.open()
            tp = tmp.new_page(width=page.rect.width, height=page.rect.height)
            tp.show_pdf_page(tp.rect, doc, i)
            Wd, Ht = tp.rect.width, tp.rect.height
            for k, p in enumerate(props):
                r = fitz.Rect(p["r"][0] * Wd, p["r"][1] * Ht, p["r"][2] * Wd, p["r"][3] * Ht)
                c = COLORS.get(p["src"], (0, 0, 0))
                tp.draw_rect(r, color=c, width=1.2 * Wd / 595)
                tp.insert_text((r.x0, max(8, r.y0 - 1)), str(k), fontsize=8 * Wd / 595, color=c, fontname="hebo")
            for g in range(1, 10):  # tick marks every 0.1 of width / height
                tp.draw_line((Wd * g / 10, 0), (Wd * g / 10, 6), color=(0, 0.7, 0.7), width=1)
                tp.draw_line((Wd * g / 10, Ht - 6), (Wd * g / 10, Ht), color=(0, 0.7, 0.7), width=1)
                tp.draw_line((0, Ht * g / 10), (6, Ht * g / 10), color=(0, 0.7, 0.7), width=1)
                tp.draw_line((Wd - 6, Ht * g / 10), (Wd, Ht * g / 10), color=(0, 0.7, 0.7), width=1)
            label = f"{f} p{i + 1}".encode("ascii", "replace").decode()
            tp.insert_text((4, 10 * Wd / 595), label, fontsize=9 * Wd / 595, color=(1, 0, 0), fontname="hebo")
            sc = min(512 / Wd, 724 / Ht)
            tiles.append((f, i + 1, tp.get_pixmap(matrix=fitz.Matrix(sc, sc))))
    index = []
    per, cols = 6, 3
    for s in range(0, len(tiles), per):
        grp = tiles[s:s + per]
        w = max(t.width for _, _, t in grp); h = max(t.height for _, _, t in grp)
        rows = (len(grp) + cols - 1) // cols
        sd = fitz.open(); sp = sd.new_page(width=w * cols, height=h * rows)
        for k, (_, _, t) in enumerate(grp):
            x = (k % cols) * w; y = (k // cols) * h
            sp.insert_image(fitz.Rect(x, y, x + t.width, y + t.height), pixmap=t)
            sp.draw_rect(fitz.Rect(x, y, x + t.width, y + t.height), color=(0.5, 0.5, 0.5))
        name = f"sheet_{s // per + 1:03d}.png"
        sp.get_pixmap(dpi=72).save(str(od / name))
        index.append(name + ": " + ", ".join(f"{f} p{p}" for f, p, _ in grp))
    (od / "index.txt").write_text("\n".join(index), encoding="utf-8")
    print("sheets in", od, len(index), "(index.txt lists which file/page is in each tile)")


def cmd_lines(args):
    from compat import fitz
    cfg = C.Cfg()
    key, folder = cfg.unit(args[0])
    f, pg = args[1], int(args[2])
    y0, y1 = (float(args[3]), float(args[4])) if len(args) > 4 else (0, 1)
    for name, path, mode, out in C.files(cfg, folder):
        if name == f:
            page = fitz.open(path)[pg - 1]
            if page.rotation:
                page.remove_rotation()
            for l in sorted(page_lines(cfg, folder, f, mode, pg - 1, page), key=lambda l: (l["y"], l["x"])):
                if y0 <= l["y"] <= y1:
                    print(f'{l["x"]:.3f} {l["y"]:.3f} {l["x"] + l["w"]:.3f} {l["y"] + l["h"]:.3f}  {l["t"][:70]}')
            return
    raise SystemExit("file not found in unit: " + f)


# =========================================================================== build / qa / log
def cmd_build(args):
    import engine as E
    cfg = C.Cfg()
    E.configure(cfg)
    for key in keys_arg(cfg, args):
        key, folder = cfg.unit(key)
        ob, op = cfg.out_dir(cfg.out_bpi, folder), cfg.out_dir(cfg.out_pub, folder)
        ob.mkdir(parents=True, exist_ok=True); op.mkdir(parents=True, exist_ok=True)
        for f, path, mode, out in C.files(cfg, folder):
            spec = final_spec(cfg, key, folder, f)
            regs = {int(k): v for k, v in spec["pages"].items()}
            E.make_bpi(str(path), str(ob / out), regs)
            E.make_public(str(path), str(op / out), regs, mode=mode)
            print("built", key, out, sum(len(v) for v in regs.values()), "brackets")


def cmd_qa(args):
    """Leak check: OCR every Public page and search for (a) supplier terms and (b) 5+ digit numbers that
    were inside a bracket in the source. Also checks page counts and headers. Hits need human judgement:
    a bracketed '240.00' equals a public postcode '24000' etc."""
    import ocr
    from compat import fitz
    cfg = C.Cfg()
    backend = ocr.pick_backend(cfg)
    total = 0
    for key in keys_arg(cfg, args):
        key, folder = cfg.unit(key)
        terms = [re.compile(p) for p, l in cfg.terms(key) if l.lower().startswith(("supplier", "third"))]
        problems = []
        for f, path, mode, out in C.files(cfg, folder):
            spec = final_spec(cfg, key, folder, f)
            pubp, bpip = cfg.out_dir(cfg.out_pub, folder) / out, cfg.out_dir(cfg.out_bpi, folder) / out
            if not pubp.exists() or not bpip.exists():
                problems.append(f"{out}: output missing - run build"); continue
            pub, src = fitz.open(pubp), fitz.open(path)
            if len(pub) != len(src) or len(fitz.open(bpip)) != len(src):
                problems.append(f"{out}: page count differs from source")
            for i, page in enumerate(pub):
                if cfg["public_header"].split()[0] not in page.get_text():
                    problems.append(f"{out} p{i + 1}: public header missing")
                regs = spec["pages"].get(str(i + 1), [])
                secrets = set()
                for d in lines_cached(cfg, folder, f, spec, i + 1):
                    cx, cy = d["x"] + d["w"] / 2, d["y"] + d["h"] / 2
                    if any(r["r"][0] <= cx <= r["r"][2] and r["r"][1] <= cy <= r["r"][3] for r in regs):
                        for tok in re.findall(r"\d[\d,，.]{4,}\d", d["t"]):
                            if len(re.sub(r"\D", "", tok)) >= 5:
                                secrets.add(re.sub(r"\D", "", tok))
                got = [d["t"] for d in ocr.ocr_page(cfg, page, dpi=150, backend=backend)]
                digits = " ".join(re.sub(r"\D", "", t) for t in got)
                for s in secrets:
                    if s in digits:
                        problems.append(f"{out} p{i + 1}: number {s} still visible")
                for t in got:
                    if not cfg.own_re.search(t) and any(rx.search(t) for rx in terms):
                        problems.append(f"{out} p{i + 1}: supplier term visible: {t[:60]}")
        total += len(problems)
        print(f"== {key} ({folder}): {len(problems)} issue(s)")
        for p in problems:
            print("   ", p)
    print("TOTAL issues:", total)


REASON = {
    "supplier": "Identity and contact details of a third party (supplier/contractor) in the submitter's business records; "
                "commercially sensitive, not publicly available.",
    "bank": "Financial account / tax identification numbers (privacy-protected; must be bracketed).",
    "price": "Negotiated prices, quantities and amounts - confidential commercial and financial information "
             "(5 U.S.C. § 552(b)(4)).",
    "terms": "Negotiated payment / penalty terms - confidential commercial information whose disclosure would cause "
             "competitive harm.",
    "person": "Names, signatures and identifiers of private individuals.",
}


def _cat(label):
    l = label.lower()
    if "bank" in l or "tax id" in l: return "bank"
    if any(k in l for k in ("payment", "liquidated", "terms", "ratio", "penalt", "schedule")): return "terms"
    if any(k in l for k in ("quantit", "amount", "price", "rate")): return "price"
    if any(k in l for k in ("signature", "initials", "names")) or l.strip() == "name": return "person"
    return "supplier"


def cmd_log(args):
    from openpyxl import Workbook
    from openpyxl.styles import Font, Alignment, PatternFill
    cfg = C.Cfg()
    wb = Workbook(); ws = wb.active; ws.title = "BCI log"
    ws.append(["Folder", "File (BPI/Public)", "Pages", "Page", "Bracketed item (public summary)", "Category", "Basis for BCI treatment"])
    for c in ws[1]:
        c.font = Font(bold=True, color="FFFFFF"); c.fill = PatternFill("solid", fgColor="1F4E78")
    for key in keys_arg(cfg, args):
        key, folder = cfg.unit(key)
        for f, path, mode, out in C.files(cfg, folder):
            spec = final_spec(cfg, key, folder, f)
            n = len(spec["pages"])
            for pg in sorted(spec["pages"], key=int):
                for r in spec["pages"][pg]:
                    c = _cat(r["label"])
                    ws.append([folder, out, n, int(pg), r["label"], c, REASON[c]])
    for col, w in zip("ABCDEFG", (40, 34, 7, 6, 60, 10, 90)):
        ws.column_dimensions[col].width = w
    for row in ws.iter_rows(min_row=2):
        for c in row:
            c.alignment = Alignment(wrap_text=True, vertical="top")
    ws.freeze_panes = "A2"
    out = cfg.root / "BCI Log.xlsx"
    wb.save(out); print("saved", out, ws.max_row - 1, "rows")


def cmd_status(_):
    cfg = C.Cfg()
    print(f"{'key':10s} {'files':>5s} {'auto':>5s} {'review':>6s} {'built':>5s}  note")
    for key, folder in cfg.units():
        fl = C.files(cfg, folder)
        auto = sum(auto_path(cfg, folder, f).exists() for f, *_ in fl)
        rv = cfg.work / "review" / f"{key}.json"
        built = [cfg.out_dir(cfg.out_pub, folder) / o for *_, o in fl]
        nb = sum(p.exists() for p in built)
        note = ""
        if nb and rv.exists() and min((p.stat().st_mtime for p in built if p.exists()), default=0) < rv.stat().st_mtime:
            note = "STALE: review edited after build"
        print(f"{key:10s} {len(fl):5d} {auto:5d} {'yes' if rv.exists() else '-':>6s} {nb:5d}  {note}")


CMDS = {"init": cmd_init, "doctor": cmd_doctor, "survey": cmd_survey, "ocr": cmd_ocr, "parties": cmd_parties,
        "propose": cmd_propose, "sheets": cmd_sheets, "lines": cmd_lines, "build": cmd_build, "qa": cmd_qa,
        "log": cmd_log, "status": cmd_status}

if __name__ == "__main__":
    if len(sys.argv) < 2 or sys.argv[1] not in CMDS:
        print(__doc__); sys.exit(1)
    CMDS[sys.argv[1]](sys.argv[2:])
