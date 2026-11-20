#!/usr/bin/env python3
"""BPI / Public version toolkit - one CLI for the whole workflow.

Run from the matter folder (the one holding bpi_config.json):

  python bpi.py next                     what to do next in this matter (use it whenever unsure)
  python bpi.py init | doctor | survey   create config / check the setup / inventory of the exhibits
  python bpi.py ocr [KEY ...]            OCR all scanned pages (cached)
  python bpi.py parties [KEY ...]        company-like names found in the text (to write supplier terms)
  python bpi.py terms-check [KEY ...]    company names no supplier term matches yet; terms that match nothing
  python bpi.py propose KEY|all          automatic bracket proposals -> _work/auto/
  python bpi.py sheets KEY [FILE ...]    review contact sheets -> _work/sheets/KEY/sheet_###.png
  python bpi.py page KEY FILE PAGE [public] [X0 Y0 X1 Y1]   one page, large, with a labelled grid and box ids
  python bpi.py lines KEY FILE PAGE [Y0 Y1]   numbered text lines with boxes (anchors for edits)
  python bpi.py boxes KEY FILE [PAGE]    final brackets with ids and the text each one covers
  python bpi.py check KEY|all            apply the edit file without building; list every problem
  python bpi.py build KEY [FILE ...]|all write BPI + Public PDFs
  python bpi.py audit KEY|all            text-based self-check: cut text, uncovered sensitive content,
                                         inconsistent numbers / clauses, over-bracketing
  python bpi.py qa KEY|all               re-OCR the Public PDFs and look for leaked bracketed content
  python bpi.py ack KEY ID [ID ...] -m "reason"    acknowledge a verified non-leak (audit / qa finding)
  python bpi.py acks [KEY ...]           list acknowledged findings (goes into the report)
  python bpi.py pubsheets KEY|all        4 Public pages per image -> _work/pub/KEY/ (visual leak review)
  python bpi.py viewed KEY N             attest that all N Public sheet images were looked at
  python bpi.py gate KEY|all             PASS / FAIL - a unit is finished only when its gate passes
  python bpi.py samples-ok "user said .."  record the user's approval of the samples (unlocks volume work)
  python bpi.py log KEY|all              BCI log spreadsheet (one row per bracket)
  python bpi.py status                   overview of all units

KEY = unit key shown by `survey` / `status` (normally the numeric prefix of a sub-folder, e.g. 205).
Commands that write never default to "all": name the unit(s). Environment variable BPI_UNITS=205,206
restricts a process to those units (use it for parallel reviewers).
"""
import os, sys, json, re, shutil, hashlib, time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import cfg as C
import edits as E
from edits import final_spec, lines_cached, page_lines, native_lines, auto_path, box_ids  # noqa: F401 (used by helpers / old scripts)

COLORS = {"term": (0.9, 0, 0), "bank": (0, 0, 0.9), "contact": (0, 0.55, 0.9), "person": (0.6, 0, 0.6),
          "pay": (0.9, 0.5, 0), "ld": (0.9, 0.5, 0), "amount": (0, 0.6, 0), "table": (0, 0.6, 0),
          "seal-red": (1, 0, 0.5), "seal-blue?": (0.3, 0.3, 1), "seal-sup": (1, 0, 0.5), "seal-edge?": (1, 0, 0.5),
          "seal-own?": (0.55, 0.55, 0.55),
          "amtwords": (0, 0.6, 0), "invno": (0.9, 0, 0), "remark": (0.9, 0, 0), "hand?": (1, 0.6, 0), "sigfield": (0.5, 0.3, 0),
          "manual": (0, 0, 0)}
WRITE_CMDS = ("propose", "build", "pubsheets", "qa", "sheets", "audit")


# =========================================================================== helpers
def targets(cfg, args, cmd, need=True):
    """command arguments -> [(key, folder, only-files or None)]. `all` = every unit; an argument that is
    not a unit key is a file name restricting the unit named before it."""
    units = cfg.units()
    known = {k for k, _ in units} | {d for _, d in units}
    if not args:
        if need:
            raise SystemExit(f"{cmd}: name the unit key(s), or say 'all' explicitly - e.g.  bpi.py {cmd} {units[0][0] if units else 'KEY'}\n"
                             f"units: {', '.join(k for k, _ in units)}")
        args = ["all"]
    res = []
    for a in args:
        if a == "all":
            res += [[k, d, None] for k, d in units if cfg.may_write(k) or cmd not in WRITE_CMDS]
        elif a in known:
            k, d = cfg.unit(a)
            if cmd in WRITE_CMDS and not cfg.may_write(k):
                raise SystemExit(f"{cmd}: unit {k} is outside BPI_UNITS={os.environ.get('BPI_UNITS')} for this process - work only on your own units")
            res.append([k, d, None])
        elif res:
            res[-1][2] = (res[-1][2] or set()) | {a}
        else:
            raise SystemExit(f"{cmd}: {a!r} is not a unit key. units: {', '.join(k for k, _ in units)}")
    for k, d, only in res:
        if only:
            names = {f for f, *_ in C.files(cfg, d)}
            bad = only - names
            if bad:
                raise SystemExit(f"{cmd}: no such file in unit {k}: {', '.join(sorted(bad))}\nfiles: {', '.join(sorted(names))}")
    return [tuple(x) for x in res]


def _find_file(cfg, folder, f):
    for name, path, mode, out in C.files(cfg, folder):
        if name == f or out == f:
            return name, path, mode, out
    raise SystemExit(f"file not found in unit: {f}\nfiles: " + ", ".join(n for n, *_ in C.files(cfg, folder)))


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
def seal_kind(b, lines, terms, col, own_seal, own_col=""):
    """Seal colour says nothing about who owns a seal. A seal is proposed as a supplier seal when its text
    matches a supplier term (seal-sup), or when it is a fragment cut by the page edge in a colour that is
    not the submitter's own, i.e. a cross-page seal (seal-edge?)."""
    ins = [d for d in lines if b[0] <= d["x"] + d["w"] / 2 <= b[2] and b[1] <= d["y"] + d["h"] / 2 <= b[3]]
    txt = " ".join(d["t"] for d in ins)
    if txt and own_seal.search(txt):
        return None
    if txt and any(re.search(p, txt) for p, _ in terms):
        return "seal-sup"
    edge_col = "blue" if own_col == "red" else "red"
    if col == edge_col and (b[0] < 0.015 or b[2] > 0.985) and (b[2] - b[0]) < 0.12 and (b[3] - b[1]) > 0.04:
        return "seal-edge?"
    return None


def cmd_propose(args):
    from compat import fitz
    import propose as P
    import seals
    cfg = C.Cfg()
    P.set_own(C.clean_rx(cfg["own_company_regex"]), C.clean_rx(cfg["own_code_regex"]))
    own_seal = C.rx_join(cfg["own_seal_text_regex"], cfg["own_company_regex"])
    own_col = (cfg["own_seal_color"] or "").lower()
    for key, folder, only in targets(cfg, args, "propose"):
        terms = cfg.terms(key)
        for f, path, mode, out in C.files(cfg, folder):
            if only and f not in only:
                continue
            doc = fitz.open(path)
            spec = {"mode": mode, "src": str(path), "out": out, "pages": {}}
            for i, page in enumerate(doc):
                if page.rotation:
                    page.remove_rotation()
                lines = page_lines(cfg, folder, f, mode, i, page)
                props = P.propose(lines, terms, mode)
                if mode == "scan":
                    def seal(b, col, base):
                        r = [round(v, 4) for v in b[:4]]
                        own = col == own_col and not (r[3] < 0.17 or r[2] - r[0] > 0.55) \
                            and seal_kind(b, lines, terms, col, own_seal, own_col) != "seal-sup"
                        props.append({"r": r, "label": "Seal", "rot": 0, "src": "seal-own?" if own else base})
                    for b in seals.color_boxes(page, "red"):
                        seal(b, "red", "seal-red")
                    tb = [[d["x"], d["y"], d["x"] + d["w"], d["y"] + d["h"]] for d in lines]
                    for b in seals.handwriting_boxes(page, tb):
                        props.append({"r": [round(v, 4) for v in b], "label": "Signature", "rot": 0, "src": "hand?"})
                    for b in seals.color_boxes(page, "blue"):
                        seal(b, "blue", "seal-blue?")
                    for col in ("blue", "red"):
                        for b in seals.color_boxes(page, col):
                            k = seal_kind(b, lines, terms, col, own_seal, own_col)
                            if k:
                                props.append({"r": [round(v, 4) for v in b[:4]], "label": "Supplier seal", "rot": 0, "src": k})
                spec["pages"][str(i + 1)] = props
            ap = auto_path(cfg, folder, f)
            ap.parent.mkdir(parents=True, exist_ok=True)
            ap.write_text(json.dumps(spec, ensure_ascii=False), encoding="utf-8")
            n = sum(len(v) for v in spec["pages"].values())
            print(f"{key:8s} {f[:60]:60s} {mode:5s} pages={len(doc):4d} proposals={n}")


def cmd_terms_check(args):
    """(1) company-like names that no supplier term matches and that are not the submitter's own;
       (2) terms that match nothing in the unit (usually the OCR spells the name differently)."""
    from compat import fitz
    import checks as K
    cfg = C.Cfg()
    grand = 0
    allhits = {}
    for key, folder, _ in targets(cfg, args, "terms-check", need=False):
        terms = [(re.compile(p), p, l) for p, l in cfg.terms(key)]
        hits = {p: 0 for _, p, _ in terms}
        miss = {}
        for f, path, mode, out in C.files(cfg, folder):
            doc = fitz.open(path)
            for i in range(len(doc)):
                page = doc[i]
                for d in page_lines(cfg, folder, f, mode, i, page):
                    t = d["t"].strip()
                    for rx, p, _ in terms:
                        if rx.search(t):
                            hits[p] += 1
                    if K.COMPANY.search(t) and len(t) < 90 and not cfg.own_re.search(t) and not any(rx.search(t) for rx, _, _ in terms):
                        k = re.sub(r"[^A-Za-z\u4e00-\u9fff]", "", t).lower()[:14]
                        e = miss.setdefault(k, [t, 0, f, i + 1]); e[1] += 1
        for p, n in hits.items():
            allhits[p] = allhits.get(p, 0) + n
        grand += len(miss)
        print(f"== {key}: {len(miss)} company-like name(s) not matched by any term")
        for t, n, f, pg in sorted(miss.values(), key=lambda e: -e[1])[:60]:
            print(f"   {n:4d}x  {t[:70]}    (e.g. {f} p{pg})")
    dead = [p for p, n in allhits.items() if n == 0]
    if dead and not args:
        print(f"{len(dead)} term(s) match nothing in any unit (the OCR probably spells the name differently - rewrite them):")
        for p in dead:
            print("   ", p[:100])
    print(f"TOTAL unmatched names: {grand}. Add a tolerant regex for every counterparty (anchor on a short distinctive\n"
          f"fragment of the name, e.g. 'NORTHSTAR' rather than the full 'QINGDAO NORTHSTAR HEAVY INDUSTRY CO., LTD', because OCR misreads letters);\n"
          f"names that really are public (authorities, standards bodies) may stay unmatched.")


# =========================================================================== sheets / page / lines / boxes
def _draw_boxes(fitz, tp, spec, pg, scale=1.0):
    Wd, Ht = tp.rect.width, tp.rect.height
    fs = 8 * Wd / 595 * scale
    for p in spec["pages"].get(str(pg), []):
        r = fitz.Rect(p["r"][0] * Wd, p["r"][1] * Ht, p["r"][2] * Wd, p["r"][3] * Ht)
        c = COLORS.get(p["src"], (0, 0, 0))
        tp.draw_rect(r, color=c, width=1.2 * Wd / 595)
        tp.insert_text((r.x0, max(fs, r.y0 - 1)), box_ids(p)[:16], fontsize=fs, color=c, fontname="hebo")
    for p in spec.get("cands", {}).get(str(pg), []):
        r = fitz.Rect(p["r"][0] * Wd, p["r"][1] * Ht, p["r"][2] * Wd, p["r"][3] * Ht)
        tp.draw_rect(r, color=COLORS["seal-own?"], width=0.8 * Wd / 595, dashes="[3 3] 0")
        tp.insert_text((r.x0, max(fs, r.y0 - 1)), p["id"] + "?", fontsize=fs, color=COLORS["seal-own?"], fontname="hebo")


def cmd_sheets(args):
    from compat import fitz
    cfg = C.Cfg()
    (key, folder, only), = targets(cfg, args[:1], "sheets")
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
            tmp = fitz.open()
            tp = tmp.new_page(width=page.rect.width, height=page.rect.height)
            tp.show_pdf_page(tp.rect, doc, i)
            Wd, Ht = tp.rect.width, tp.rect.height
            _draw_boxes(fitz, tp, spec, i + 1)
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
    print("sheets in", od, len(index), "(index.txt lists which file/page is in each tile; box labels are ids for del / relabel / keep)")


def cmd_page(args):
    """one page, large, with a labelled coordinate grid (every 0.05, labels every 0.1) and box ids.
    page KEY FILE PAGE            source page with the current brackets
    page KEY FILE PAGE public     the built Public page (to check a doubtful spot)
    ... X0 Y0 X1 Y1               zoom into that region (page fractions)"""
    from compat import fitz
    cfg = C.Cfg()
    if len(args) < 3:
        raise SystemExit("usage: bpi.py page KEY FILE PAGE [public] [X0 Y0 X1 Y1]")
    key, folder = cfg.unit(args[0])
    f, path, mode, out = _find_file(cfg, folder, args[1])
    pg = int(args[2])
    rest = args[3:]
    public = bool(rest) and rest[0] == "public"
    zoom = [float(v) for v in rest[1 if public else 0:][:4]]
    src = cfg.out_dir(cfg.out_pub, folder) / out if public else path
    if not Path(src).exists():
        raise SystemExit(f"{src} does not exist - build first")
    doc = fitz.open(src)
    if not 1 <= pg <= len(doc):
        raise SystemExit(f"{f} has {len(doc)} pages")
    page = doc[pg - 1]
    if page.rotation:
        page.remove_rotation()
    tmp = fitz.open(); tp = tmp.new_page(width=page.rect.width, height=page.rect.height)
    tp.show_pdf_page(tp.rect, doc, pg - 1)
    Wd, Ht = tp.rect.width, tp.rect.height
    x0, y0, x1, y1 = zoom if len(zoom) == 4 else (0, 0, 1, 1)
    zf = 1 / max(x1 - x0, y1 - y0)
    if not public:
        _draw_boxes(fitz, tp, final_spec(cfg, key, folder, f, quiet=True), pg, scale=max(0.5, 1 / zf))
    step = 0.05 if zf < 2.5 else 0.01
    fs = 6.5 * Wd / 595 / zf
    k = 0
    while k * step <= 1.0001:
        v = k * step
        major = abs(v * 10 - round(v * 10)) < 1e-6 if step == 0.05 else abs(v * 20 - round(v * 20)) < 1e-6
        col = (0, 0.55, 0.75)
        tp.draw_line((Wd * v, 0), (Wd * v, Ht), color=col, width=(0.5 if major else 0.2) / zf, stroke_opacity=0.55 if major else 0.3)
        tp.draw_line((0, Ht * v), (Wd, Ht * v), color=col, width=(0.5 if major else 0.2) / zf, stroke_opacity=0.55 if major else 0.3)
        if major:
            lab = f"{v:.2f}".rstrip("0").rstrip(".") if step == 0.05 else f"{v:.2f}"
            for yy in (y0, y1):
                tp.insert_text((Wd * v + 1 / zf, Ht * yy + (fs if yy == y0 else -1 / zf)), lab, fontsize=fs, color=(0, 0.35, 0.6), fontname="hebo")
            for xx in (x0, x1):
                tp.insert_text((Wd * xx + (1 / zf if xx == x0 else -fs * 2.4), Ht * v - 1 / zf), lab, fontsize=fs, color=(0, 0.35, 0.6), fontname="hebo")
        k += 1
    clip = fitz.Rect(x0 * Wd, y0 * Ht, x1 * Wd, y1 * Ht)
    sc = min(1150 / clip.width, 1500 / clip.height)
    od = cfg.work / "page" / key
    od.mkdir(parents=True, exist_ok=True)
    name = re.sub(r"[^\w.-]+", "_", Path(out).stem) + f"_p{pg:03d}" + ("_public" if public else "") + ("_zoom" if len(zoom) == 4 else "") + ".png"
    tp.get_pixmap(matrix=fitz.Matrix(sc, sc), clip=clip).save(str(od / name))
    print(od / name)
    print("grid labels are page fractions: x grows to the right, y grows downwards; a box is [x0, y0, x1, y1]")


def cmd_lines(args):
    """numbered text lines of a page:  L<n>  x0 y0 x1 y1  text
    Use the numbers in edits ({"lines": "12-18"}) or the text in {"text": "regex"} / {"after": "regex"} / span edits."""
    from compat import fitz
    cfg = C.Cfg()
    if len(args) < 3:
        raise SystemExit("usage: bpi.py lines KEY FILE PAGE [Y0 Y1]")
    key, folder = cfg.unit(args[0])
    f, path, mode, out = _find_file(cfg, folder, args[1])
    pg = int(args[2])
    y0, y1 = (float(args[3]), float(args[4])) if len(args) > 4 else (0, 1)
    page = fitz.open(path)[pg - 1]
    if page.rotation:
        page.remove_rotation()
    for n, l in enumerate(E.sorted_lines(page_lines(cfg, folder, f, mode, pg - 1, page))):
        if y0 <= l["y"] <= y1:
            print(f'L{n:<3d} {l["x"]:.3f} {l["y"]:.3f} {l["x"] + l["w"]:.3f} {l["y"] + l["h"]:.3f}  {l["t"][:80]}')


def cmd_boxes(args):
    """final brackets of a file (or one page) with the text each one covers - check here that a bracket
    covers what you meant and nothing else, without having to look at a picture."""
    cfg = C.Cfg()
    if len(args) < 2:
        raise SystemExit("usage: bpi.py boxes KEY FILE [PAGE]")
    key, folder = cfg.unit(args[0])
    f, path, mode, out = _find_file(cfg, folder, args[1])
    spec = final_spec(cfg, key, folder, f)
    for pg in sorted(spec["pages"], key=int):
        if len(args) > 2 and pg != args[2]:
            continue
        regs = spec["pages"][pg]
        if not regs and not spec["cands"].get(pg):
            continue
        print(f"-- p{pg}")
        lines = lines_cached(cfg, folder, f, spec, int(pg))
        for q in sorted(regs, key=lambda q: (q["r"][1], q["r"][0])):
            r = q["r"]
            full, part = [], []
            for d in lines:
                ix = min(d["x"] + d["w"], r[2]) - max(d["x"], r[0]); iy = min(d["y"] + d["h"], r[3]) - max(d["y"], r[1])
                if ix <= 0 or iy <= 0:
                    continue
                t = d["t"].strip()
                fr = ix * iy / max(1e-9, d["w"] * d["h"])
                if fr >= 0.85:
                    full.append(t[:60])
                elif fr >= 0.08:
                    import propose as P
                    a, b = P.char_span(dict(d, t=t), r)
                    part.append(f"{t[:a][-25:]}⟦{t[a:b][:60]}⟧{t[b:][:25]}" + ("" if iy / d["h"] > 0.6 else "   (only part of the line HEIGHT)"))
            txt = " | ".join(full)[:150]
            if not full and not part:
                txt = "(no text: seal / signature / image / empty)"
            print(f"   {box_ids(q):10s} {str(r):34s} [{q['label']}]" + (f"  covers: {txt}" if txt else ""))
            for t in part[:6]:
                print(f"   {'':10s} covers part of a line (inside ⟦ ⟧): {t}")
        for q in spec["cands"].get(pg, []):
            print(f"   {q['id'] + '?':10s} {str(q['r']):34s} own-colour seal candidate - NOT bracketed (\"keep\": [\"{q['id']}\"] to bracket it)")


def cmd_check(args):
    """apply the edit file(s) without building; every problem is listed. Exit code 1 when there are problems."""
    cfg = C.Cfg()
    bad = 0
    for key, folder, only in targets(cfg, args, "check"):
        n0 = len(E.PROBLEMS)
        fl = C.files(cfg, folder)
        unknown = E.unknown_file_keys(E.load_review(cfg, key), [f for f, *_ in fl])
        for u in unknown:
            print(f"ERROR {key}: review entry {u!r} matches no file of the unit - its edits are never applied (typo?)")
        for f, *_ in fl:
            if only and f not in only:
                continue
            if not auto_path(cfg, folder, f).exists():
                print(f"ERROR {key}: {f} has no proposals - run propose"); bad += 1; continue
            final_spec(cfg, key, folder, f)
        n = len(E.PROBLEMS) - n0 + len(unknown)
        bad += n
        print(f"== check {key}: {'clean' if not n else str(n) + ' problem(s)'}")
    if bad:
        print("Fix the edit file: an ERROR means a bracket is missing; a WARN means an edit did nothing.")
    raise SystemExit(1 if bad else 0)


# =========================================================================== build / qa / log
def cmd_build(args):
    import engine as Eng
    cfg = C.Cfg()
    Eng.configure(cfg)
    st = cfg.state()
    lim = int(cfg["sample_units_limit"] or 0)
    failed = []
    for key, folder, only in targets(cfg, args, "build"):
        built = set(st.get("built_units", []))
        if lim and key not in built and len(built) >= lim and not st.get("samples_ok"):
            raise SystemExit(
                f"build {key}: SAMPLES FIRST. {len(built)} unit(s) are already built ({', '.join(sorted(built))}).\n"
                f"Before more units are produced, the user must review sample BPI / Public files and confirm the rules.\n"
                f"Finish those units (bpi.py gate KEY), show the files to the user, then record the approval:\n"
                f"    bpi.py samples-ok \"<what the user said>\"")
        ob, op = cfg.out_dir(cfg.out_bpi, folder), cfg.out_dir(cfg.out_pub, folder)
        ob.mkdir(parents=True, exist_ok=True); op.mkdir(parents=True, exist_ok=True)
        unknown = E.unknown_file_keys(E.load_review(cfg, key), [f for f, *_ in C.files(cfg, folder)])
        for u in unknown:
            print(f"ERROR {key}: review entry {u!r} matches no file of the unit - its edits are never applied (typo?)")
        for f, path, mode, out in C.files(cfg, folder):
            if only and f not in only:
                continue
            if not auto_path(cfg, folder, f).exists():
                failed.append(f"{key}/{f}: no proposals (run propose)"); continue
            spec = final_spec(cfg, key, folder, f)
            if spec["errors"]:
                for p in (ob / out, op / out):
                    if p.exists():
                        p.unlink()
                failed.append(f"{key}/{f}: {spec['errors']} edit error(s) - NOT BUILT (a bracket would be missing)")
                continue
            regs = {int(k): v for k, v in spec["pages"].items()}
            Eng.make_bpi(str(path), str(ob / out), regs)
            Eng.make_public(str(path), str(op / out), regs, mode=mode)
            print("built", key, out, sum(len(v) for v in regs.values()), "brackets")
        st = cfg.state()
        st["built_units"] = sorted(set(st.get("built_units", [])) | {key})
        cfg.save_state(st)
    if failed:
        print("\nNOT BUILT:")
        for x in failed:
            print("   ", x)
        print("Fix the edit file (bpi.py check KEY shows every problem) and build again.")
        raise SystemExit(1)
    print("next: bpi.py audit KEY ; bpi.py qa KEY ; bpi.py pubsheets KEY ; bpi.py gate KEY")


def cmd_pubsheets(args):
    """4 built Public pages per image at readable size, for the visual leak review -> work/pub/KEY/"""
    from compat import fitz
    cfg = C.Cfg()
    for key, folder, only in targets(cfg, args, "pubsheets"):
        od = cfg.work / "pub" / key
        shutil.rmtree(od, ignore_errors=True); od.mkdir(parents=True, exist_ok=True)
        pages = []
        for f, path, mode, out in C.files(cfg, folder):
            p = cfg.out_dir(cfg.out_pub, folder) / out
            if not p.exists():
                print(f"WARN {out}: not built"); continue
            for i, pg in enumerate(fitz.open(str(p))):
                pages.append((f"{out} p{i + 1}", pg.get_pixmap(dpi=72)))
        idx = []
        for s in range(0, len(pages), 4):
            sd = fitz.open(); sp = sd.new_page(width=1200, height=1720)
            for k, (lab, pm) in enumerate(pages[s:s + 4]):
                x = (k % 2) * 600; y = (k // 2) * 860
                sp.insert_image(fitz.Rect(x, y + 14, x + 600, y + 860), pixmap=pm, keep_proportion=True)
                sp.insert_text((x + 4, y + 11), lab.encode("ascii", "replace").decode(), fontsize=11, color=(1, 0, 0), fontname="hebo")
                sp.draw_rect(fitz.Rect(x, y, x + 600, y + 860), color=(0.5, 0.5, 0.5))
            fn = od / f"pub_{s // 4 + 1:03d}.png"
            sp.get_pixmap(dpi=72).save(str(fn))
            idx.append(f"{fn.name}  " + " | ".join(l for l, _ in pages[s:s + 4]))
        (od / "index.txt").write_text("\n".join(idx), encoding="utf-8")
        print(f"pub sheets {od}: {len(idx)} images. Look at EVERY one, zoom doubtful spots with "
              f"`bpi.py page {key} FILE PAGE public X0 Y0 X1 Y1`, then: bpi.py viewed {key} {len(idx)}")


def cmd_qa(args):
    """Leak check: OCR every Public page and search for (a) supplier terms, (b) 5+ digit numbers that were
    inside a bracket on the same page of the source and (c) numbers bracketed anywhere else in the unit
    (a total bracketed on the item list but visible on the cover page). Also checks page counts and
    headers. Hits need judgement (a bracketed '240.00' equals a public postcode '24000'): fix real leaks,
    acknowledge verified false positives with `ack`. qa cannot see names, signatures, seals or short
    numbers - audit and the visual check of the Public sheets cover those."""
    import ocr
    import checks as K
    from compat import fitz
    cfg = C.Cfg()
    backend = ocr.pick_backend(cfg)
    total = 0
    for key, folder, only in targets(cfg, args, "qa"):
        terms = [re.compile(p) for p, l in cfg.terms(key) if l.lower().startswith(("supplier", "third", "manufacturer"))]
        own_code = C.rx_join(cfg["own_code_regex"])
        items = []

        def hit(kind, out, pg, text):
            items.append({"id": K.fid(kind, out, pg, text), "kind": kind, "file": out, "page": pg, "text": text})
        unit_secrets = K.unit_secrets(K.unit_pages_spec(cfg, key, folder)[0], own_code)
        for f, path, mode, out in C.files(cfg, folder):
            if not auto_path(cfg, folder, f).exists():
                hit("qa-build", out, 0, "no proposals - run propose and build"); continue
            spec = final_spec(cfg, key, folder, f, quiet=True)
            pubp, bpip = cfg.out_dir(cfg.out_pub, folder) / out, cfg.out_dir(cfg.out_bpi, folder) / out
            if spec["errors"] or not pubp.exists() or not bpip.exists():
                hit("qa-build", out, 0, "output missing or edit errors - run check and build"); continue
            pub, src = fitz.open(pubp), fitz.open(path)
            if len(pub) != len(src) or len(fitz.open(bpip)) != len(src):
                hit("qa-build", out, 0, "page count differs from source")
            for i, page in enumerate(pub):
                if cfg["public_header"].split()[0] not in page.get_text():
                    hit("qa-build", out, i + 1, "public header missing")
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
                found = set()
                for s in sorted(secrets):
                    if s in digits:
                        hit("qa-num", out, i + 1, f"number {s} still visible"); found.add(s)
                for t in got:
                    for c, a, b in K.num_tokens(t, own_code):
                        s = c if (c in unit_secrets and len(c) >= 6) else None
                        if s and not any(s in x or x in s for x in found):
                            sf, sp = unit_secrets[s]
                            if (sf, int(sp)) != (out, i + 1):
                                hit("qa-num", out, i + 1, f"number {t[a:b]} is visible here but bracketed in {sf} p{sp}"); found.add(s)
                    if not cfg.own_re.search(t) and any(rx.search(t) for rx in terms):
                        hit("qa-term", out, i + 1, f"supplier term visible: {t[:60]}")
        (cfg.work / "qa").mkdir(exist_ok=True)
        (cfg.work / "qa" / f"{key}.json").write_text(json.dumps({"time": time.time(), "items": items}, ensure_ascii=False, indent=0), encoding="utf-8")
        acks = K.load_acks(cfg, key)
        opened = [x for x in items if x["id"] not in acks]
        total += len(opened)
        print(f"== qa {key} ({folder}): {len(opened)} open, {len(items) - len(opened)} acknowledged")
        for x in opened:
            print(f"   [{x['id']}] {x['file']} p{x['page']}: {x['text']}")
    print("TOTAL open qa hits:", total, "  (verify each on the Public page: bpi.py page KEY FILE PAGE public ; "
          "real leak -> fix + rebuild ; false positive -> bpi.py ack KEY ID -m \"reason\")")


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
    if "manufacturer" in l or "qr code" in l: return "supplier"
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
    for key, folder, _ in targets(cfg, args, "log", need=False):
        for f, path, mode, out in C.files(cfg, folder):
            if not auto_path(cfg, folder, f).exists():
                continue
            spec = final_spec(cfg, key, folder, f, quiet=True)
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
    import checks as K
    cfg = C.Cfg()
    st = cfg.state()
    print(f"{'key':10s} {'files':>5s} {'auto':>5s} {'review':>6s} {'built':>5s} {'gate':>5s}  first open item")
    npass = 0
    for key, folder in cfg.units():
        fl = C.files(cfg, folder)
        auto = sum(auto_path(cfg, folder, f).exists() for f, *_ in fl)
        rv = cfg.work / "review" / f"{key}.json"
        nb = sum((cfg.out_dir(cfg.out_pub, folder) / o).exists() for *_, o in fl)
        res = K.gate_unit(cfg, key, folder, codes="cached") if auto else [(False, "proposals", "")]
        ok = all(r[0] for r in res)
        npass += ok
        note = "" if ok else next(r[1] for r in res if not r[0])
        print(f"{key:10s} {len(fl):5d} {auto:5d} {'yes' if rv.exists() else '-':>6s} {nb:5d} {'PASS' if ok else 'FAIL':>5s}  {note}")
    print(f"{npass} of {len(cfg.units())} units pass the gate. samples approved: {'yes' if st.get('samples_ok') else 'no'}")


def _lazy(name):
    def run(args):
        import checks as K
        return getattr(K, name)(args)
    return run


CMDS = {"init": cmd_init, "doctor": cmd_doctor, "survey": cmd_survey, "ocr": cmd_ocr, "parties": cmd_parties,
        "terms-check": cmd_terms_check, "propose": cmd_propose, "sheets": cmd_sheets, "page": cmd_page, "lines": cmd_lines,
        "boxes": cmd_boxes, "check": cmd_check, "build": cmd_build, "pubsheets": cmd_pubsheets, "qa": cmd_qa,
        "audit": _lazy("cmd_audit"), "ack": _lazy("cmd_ack"), "acks": _lazy("cmd_acks"), "gate": _lazy("cmd_gate"),
        "viewed": _lazy("cmd_viewed"), "samples-ok": _lazy("cmd_samples_ok"), "next": _lazy("cmd_next"),
        "log": cmd_log, "status": cmd_status}

if __name__ == "__main__":
    if len(sys.argv) < 2 or sys.argv[1] not in CMDS:
        print(__doc__); sys.exit(1)
    r = CMDS[sys.argv[1]](sys.argv[2:])
    if sys.argv[1] == "audit":
        sys.exit(1 if r else 0)
