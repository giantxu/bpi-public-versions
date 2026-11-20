"""Review edits -> final bracket list.

final_spec() = automatic proposals (_work/auto) + the reviewer's edit file (_work/review/<KEY>.json).
The edit-file format is documented in references/review-guide.md. Everything that goes wrong while
applying edits is collected in PROBLEMS instead of aborting, so one bad anchor never hides the rest.
"""
import json, re, fnmatch

import cfg as C

NOSNAP = ("Signature", "Seal", "Supplier logo", "Initials", "Names")
CANDIDATE = ("seal-own?",)          # shown on review sheets, bracketed only when the reviewer keeps them
OPS = ("clear", "delsrc", "delat", "del", "keep", "relabel", "grow", "add")
ADD_KINDS = ("r", "span", "text", "after", "lines", "table")

PROBLEMS = []                        # (level, file, page, message) - level is "ERROR" or "WARN"
_LINES = {}


def problem(level, f, pg, msg, quiet=False):
    PROBLEMS.append((level, f, str(pg), msg))
    if not quiet:
        print(f"{level} {f} p{pg}: {msg}")


# --------------------------------------------------------------------------- text lines
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


def lines_cached(cfg, folder, f, spec, pg):
    from compat import fitz
    k = (folder, f, pg)
    if k not in _LINES:
        page = fitz.open(spec["src"])[pg - 1]
        if page.rotation:
            page.remove_rotation()
        _LINES[k] = page_lines(cfg, folder, f, spec["mode"], pg - 1, page)
    return _LINES[k]


def sorted_lines(lines):
    """reading order used for line numbers (L0, L1, ...) in `bpi.py lines` and in "lines" edits"""
    return sorted(lines, key=lambda l: (l["y"], l["x"]))


def auto_path(cfg, folder, f):
    return cfg.work / "auto" / C.safe(folder) / f"{f}.json"


# --------------------------------------------------------------------------- page / file keys
def parse_pages(key, n):
    """"*", "7", "3-17", "2,4,9-last", "odd", "even", "3-27:odd" -> set of page numbers"""
    key = key.strip()
    flt = None
    if ":" in key:
        key, flt = (x.strip() for x in key.split(":", 1))
    if key in ("odd", "even"):
        key, flt = "*", key
    if flt not in (None, "odd", "even"):
        raise ValueError(key)
    pages = set()
    if key == "*":
        pages = set(range(1, n + 1))
    else:
        for part in key.split(","):
            part = part.strip()
            m = re.fullmatch(r"(\d+)\s*-\s*(\d+|last)", part)
            if part == "last":
                pages.add(n)
            elif re.fullmatch(r"\d+", part):
                pages.add(int(part))
            elif m:
                pages |= set(range(int(m.group(1)), (n if m.group(2) == "last" else int(m.group(2))) + 1))
            else:
                raise ValueError(key)
    if flt:
        pages = {p for p in pages if p % 2 == (1 if flt == "odd" else 0)}
    return {p for p in pages if 1 <= p <= n}


def collect_edits(review, f, n, quiet=False):
    """merge all blocks of the review file that apply to file f: "*" (every file), glob keys
    ("commercial invoice-*.pdf"), then the exact file name; inside a block "*" first, then page ranges,
    then single pages. Lists are concatenated, flags overridden. -> {page: edits}"""
    per = {p: {} for p in range(1, n + 1)}
    blocks = []
    for fk, body in review.items():
        if fk.startswith("_") or not isinstance(body, dict):
            continue
        if fk == "*":
            blocks.append((0, body))
        elif fk == f:
            blocks.append((2, body))
        elif any(c in fk for c in "*?[") and fnmatch.fnmatchcase(f, fk):
            blocks.append((1, body))
    blocks.sort(key=lambda b: b[0])
    for rank, body in blocks:
        entries = []
        for pk, e in body.items():
            if pk.startswith("_"):
                continue
            try:
                pages = parse_pages(pk, n)
            except ValueError:
                problem("ERROR", f, pk, f"page key {pk!r} not understood (use 7, 3-17, 2,4,9-last, odd, even, 3-27:odd, *)", quiet)
                continue
            single = rank == 2 and re.fullmatch(r"\d+", pk.strip()) is not None
            if single and not pages:
                problem("ERROR", f, pk, f"page {pk} does not exist (file has {n} pages)", quiet)
            if not isinstance(e, dict):
                problem("ERROR", f, pk, "page entry must be an object of edit operations", quiet); continue
            for op in e:
                if op not in OPS and not op.startswith("_"):
                    problem("ERROR", f, pk, f"unknown operation {op!r} (known: {', '.join(OPS)})", quiet)
            entries.append((0 if pk.strip() == "*" else 2 if single else 1, pages, e, single, pk))
        entries.sort(key=lambda x: x[0])
        for _, pages, e, single, pk in entries:
            origin = {}
            for p in sorted(pages):
                tgt = per[p]
                for op, v in e.items():
                    if op == "add":
                        for n_, a in enumerate(v):
                            a = dict(a)
                            # an add under a multi-page key need not match on every page; _origin lets
                            # final_spec report adds that matched nowhere / missed pages
                            a["_opt"] = bool(a.get("optional", not single))
                            a["_origin"] = origin.setdefault(n_, {"key": pk, "multi": not single, "hit": [], "miss": [],
                                                                  "explicit": "optional" in a})
                            tgt.setdefault("add", []).append(a)
                    elif isinstance(v, list):
                        tgt.setdefault(op, []).extend(v)
                    else:
                        tgt[op] = v
    return per


def unknown_file_keys(review, names):
    """review entries that match no file of the unit (usually a typo: such edits are never applied)"""
    bad = []
    for fk, body in review.items():
        if fk.startswith("_") or fk == "*" or not isinstance(body, dict):
            continue
        if fk in names or (any(c in fk for c in "*?[") and any(fnmatch.fnmatchcase(n, fk) for n in names)):
            continue
        bad.append(fk)
    return bad


# --------------------------------------------------------------------------- add -> boxes
def span_box(lines, sp):
    x0, x1 = sp.get("x0", 0), sp.get("x1", 1); y0, y1 = sp.get("y0", 0), sp.get("y1", 1)
    ls = [d for d in lines if x0 <= d["x"] + d["w"] / 2 <= x1 and y0 <= d["y"] + d["h"] / 2 <= y1]
    ls.sort(key=lambda d: (round(d["y"], 3), d["x"]))
    start = next((k for k, d in enumerate(ls) if re.search(sp["from"], d["t"])), None)
    if start is None:
        raise LookupError(f"span: no line matches from={sp['from']!r}")
    to = sp.get("to", sp["from"])
    end = next((k for k in range(start, len(ls)) if re.search(to, ls[k]["t"])), None)
    if end is None:
        raise LookupError(f"span: no line at or after the start matches to={to!r}")
    return _union_lines(ls[start:end + 1], sp.get("pad", 0.005))


def _union_lines(sel, pad=0.005):
    return [round(min(d["x"] for d in sel) - pad, 4), round(min(d["y"] for d in sel) - pad, 4),
            round(max(d["x"] + d["w"] for d in sel) + pad, 4), round(max(d["y"] + d["h"] for d in sel) + pad, 4)]


def snap_box(lines, r, pad=0.005):
    ls = [d for d in lines if r[0] <= d["x"] + d["w"] / 2 <= r[2] and r[1] <= d["y"] + d["h"] / 2 <= r[3]]
    return _union_lines(ls, pad) if ls else r


_NUM = re.compile(r"[\s¥￥$+\-]*\d[\d\s,，.．:]*\s*(?:%|％|元|万元)?")


def _numeric(d):
    return bool(_NUM.fullmatch(d["t"].strip())) and len(d["t"].strip()) <= 18


def table_box(lines, t, mem):
    """block of a price table between two column headers.
    {"from": "数量|Qty", "to": "合价|Amount|Total", "until": "合计|TOTAL"(optional), "inherit": true}
    Works for upright tables (columns side by side) and for tables printed sideways (numbers run up the
    page). On continuation pages without a header row the column band of the previous page is reused."""
    frm, to = re.compile(t["from"]), re.compile(t.get("to", t["from"]))
    until = re.compile(t["until"]) if t.get("until") else None
    cells = [d for d in lines if _numeric(d)]
    big = [c for c in cells if len(c["t"].strip()) >= 3]
    vert = sum(c["h"] * 1.414 > c["w"] for c in big) > len(big) / 2 if big else False
    h1s = sorted((d for d in lines if frm.search(d["t"]) and len(d["t"]) <= 40), key=lambda d: (d["y"], d["x"]))
    key = (t["from"], t.get("to"))
    if h1s:
        h1 = h1s[0]
        hs = [h1] + [d for d in lines if to.search(d["t"]) and len(d["t"]) <= 40 and
                     (abs(d["x"] - h1["x"]) < 0.06 if vert else abs(d["y"] - h1["y"]) < 0.04)]
        if not vert:
            b0, b1 = min(h["x"] for h in hs) - 0.008, max(h["x"] + h["w"] for h in hs) + 0.008
            edge = max(h["y"] + h["h"] for h in hs)
        else:
            b0, b1 = min(h["y"] for h in hs) - 0.006, max(h["y"] + h["h"] for h in hs) + 0.006
            hx0, hx1 = min(h["x"] for h in hs), max(h["x"] + h["w"] for h in hs)
            strip = [d for d in lines if not _numeric(d) and b0 <= d["y"] + d["h"] / 2 <= b1
                     and d["x"] < hx1 + 0.03 and d["x"] + d["w"] > hx0 - 0.03]     # other words of the header cells
            hx0, hx1 = min([hx0] + [d["x"] for d in strip]), max([hx1] + [d["x"] + d["w"] for d in strip])
            band = [c for c in cells if b0 - 0.01 <= c["y"] + c["h"] / 2 <= b1 + 0.01]
            right = sum(c["x"] > hx1 for c in band) >= sum(c["x"] + c["w"] < hx0 for c in band)
            edge = (hx1, True) if right else (hx0, False)
        mem[key] = (vert, b0, b1, edge)
    elif t.get("inherit", True) and key in mem and mem[key][0] == vert:
        _, b0, b1, edge = mem[key]
        edge = None
    else:
        raise LookupError(f"table: no header line matches from={t['from']!r} (and no earlier page of this file to inherit the columns from)")
    if not vert:
        col = [c for c in cells if b0 - 0.015 <= c["x"] + c["w"] / 2 <= b1 + 0.015 and (edge is None or c["y"] > edge - 0.004)]
        if not col:
            raise LookupError("table: no numeric cells found under the header columns")
        x0, x1 = min(b0, min(c["x"] for c in col) - 0.006), max(b1, max(c["x"] + c["w"] for c in col) + 0.006)
        y0, y1 = min(c["y"] for c in col) - 0.005, max(c["y"] + c["h"] for c in col) + 0.006
        if until:
            stop = [d["y"] for d in lines if until.search(d["t"]) and d["y"] > y0]
            if stop:
                y1 = min(y1, min(stop) - 0.003)
    else:
        col = [c for c in cells if b0 - 0.012 <= c["y"] + c["h"] / 2 <= b1 + 0.012]
        if edge is not None:
            col = [c for c in col if (c["x"] > edge[0] - 0.004 if edge[1] else c["x"] + c["w"] < edge[0] + 0.004)]
        if not col:
            raise LookupError("table: no numeric cells found in the header band")
        y0, y1 = min(b0, min(c["y"] for c in col) - 0.005), max(b1, max(c["y"] + c["h"] for c in col) + 0.005)
        x0, x1 = min(c["x"] for c in col) - 0.006, max(c["x"] + c["w"] for c in col) + 0.006
        # rows whose numbers the OCR missed: extend along the rows to the other text of the table body
        body = [d for d in lines if d["t"].strip() and d["y"] > y1 - 0.01]
        grown = True
        while grown:                                   # only text contiguous with the block (not a far-away page number)
            grown = False
            for d in body:
                if d["x"] < x0 - 0.004 and d["x"] + d["w"] > x0 - 0.12 and (edge is None or not edge[1]):
                    x0 = max(0.015, d["x"] - 0.004); grown = True
                if d["x"] + d["w"] > x1 + 0.004 and d["x"] < x1 + 0.12 and (edge is None or edge[1]):
                    x1 = min(0.985, d["x"] + d["w"] + 0.004); grown = True
        if edge is not None:
            x0, x1 = (max(x0, edge[0] + 0.002), x1) if edge[1] else (x0, min(x1, edge[0] - 0.002))
    return [round(max(0, x0), 4), round(max(0, y0), 4), round(min(1, x1), 4), round(min(1, y1), 4)], (90 if vert else 0)


def resolve_add(lines, a, mem):
    """one add entry -> list of (rect, rot). Raises LookupError when a text anchor is not found."""
    import propose as P
    if "span" in a:
        return [(span_box(lines, a["span"]), a.get("rot", 0))]
    if "text" in a:
        rx, g, out = re.compile(a["text"]), a.get("group", 0), []
        for d in lines:
            for m in rx.finditer(d["t"]):
                if m.end(g) <= m.start(g):
                    continue
                out.append(P.line_box(d) if a.get("whole_line") else P.sub_box(d, m.start(g), m.end(g), pad=0.004))
        if not out:
            raise LookupError(f"text: nothing matches {a['text']!r}")
        return [([round(v, 4) for v in b], rot) for b, rot in out]
    if "after" in a:
        rx, out = re.compile(a["after"]), []
        for d in lines:
            m = rx.search(d["t"])
            if not m:
                continue
            rest = d["t"][m.end():]
            lead = len(rest) - len(rest.lstrip(" :：\t"))
            if len(rest.strip(" :：._-—()（）/")) >= 1:
                out.append(P.sub_box(d, m.end() + lead, len(d["t"]), pad=0.004))
                continue
            cy = d["y"] + d["h"] / 2                       # label alone: take the value cell to its right
            nb = [o for o in lines if o is not d and o["y"] <= cy <= o["y"] + o["h"] and o["x"] >= d["x"] + d["w"] * 0.8]
            if nb:
                out.append(P.line_box(min(nb, key=lambda o: o["x"])))
        if not out:
            raise LookupError(f"after: no line matches {a['after']!r} with a value behind it")
        return [([round(v, 4) for v in b], rot) for b, rot in out]
    if "lines" in a:
        ls, v = sorted_lines(lines), a["lines"]
        if isinstance(v, int):
            i0 = i1 = v
        elif isinstance(v, str):
            m = re.fullmatch(r"L?(\d+)\s*(?:-\s*L?(\d+))?", v.strip())
            if not m:
                raise LookupError(f"lines: {v!r} not understood (use 12, \"12-18\" or [12, 18])")
            i0, i1 = int(m.group(1)), int(m.group(2) or m.group(1))
        else:
            i0, i1 = int(v[0]), int(v[-1])
        if not (0 <= i0 <= i1 < len(ls)):
            raise LookupError(f"lines: {v!r} out of range (page has lines L0-L{len(ls) - 1})")
        sel = ls[i0:i1 + 1]
        return [(_union_lines(sel, a.get("pad", 0.005)), 90 if all(P.is_vertical(d) for d in sel) else a.get("rot", 0))]
    if "table" in a:
        r, rot = table_box(lines, a["table"], mem)
        return [(r, rot)]
    if "r" in a:
        r = a["r"]
        if a.get("snap", True) and a["label"] not in NOSNAP and not a["label"].startswith("Handwritten"):
            r = snap_box(lines, r)
        return [(r, a.get("rot", 0))]
    raise LookupError(f"add entry needs one of: {', '.join(ADD_KINDS)}")


# --------------------------------------------------------------------------- labels / merging
def _auto_labels(props):
    for q in props:
        r = q["r"]
        if q["src"] in ("hand?", "seal-blue?") and r[3] < 0.17:
            q["label"] = "Supplier logo"
        elif q["src"] == "seal-blue?" and r[2] - r[0] > 0.55:
            q["label"] = "Supplier letterhead"
    return props


def _target(props, ref):
    """a box by id ("a3") or by a point [x, y] inside it (smallest box containing the point)"""
    if isinstance(ref, str):
        return next((q for q in props if q.get("id") == ref), None)
    hits = [q for q in props if q["r"][0] <= ref[0] <= q["r"][2] and q["r"][1] <= ref[1] <= q["r"][3]]
    return min(hits, key=lambda q: (q["r"][2] - q["r"][0]) * (q["r"][3] - q["r"][1])) if hits else None


CAT = [("Invoice No.", "invoice number (contains supplier abbreviation)"), ("logo", "supplier logo"),
       ("letterhead", "supplier letterhead"), ("Supplier name and address", "supplier name and address"),
       ("Supplier name", "supplier name"), ("contact", "supplier contact information"),
       ("Manufacturer", "manufacturer names"), ("Amount in words", "amounts"), ("QR", "QR code"),
       ("Bank", "bank account / tax ID"), ("Seal", "seal"), ("Signature", "signature"), ("Initials", "initials"),
       ("Name", "personal name"),
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
                    big["ids"] = big.get("ids", [big.get("id", "?")]) + small.get("ids", [small.get("id", "?")])
                    if small.get("rot") and not big.get("rot"):
                        big["rot"] = small["rot"]
                    cur.remove(small); changed = True
                    break
            if changed:
                break
    return cur


# --------------------------------------------------------------------------- final spec
def load_review(cfg, key):
    rv = cfg.work / "review" / f"{key}.json"
    if not rv.exists():
        return {}
    try:
        return json.loads(rv.read_text(encoding="utf-8"))
    except json.JSONDecodeError as e:
        raise SystemExit(f"{rv}: not valid JSON ({e}). Fix the file; nothing was built.")


def final_spec(cfg, key, folder, f, quiet=False):
    """-> spec with spec["pages"][page] = final brackets (each with id / ids, r, label, src, rot),
    spec["cands"][page] = candidates that are shown on sheets but not bracketed,
    spec["errors"] = number of ERROR problems for this file (a file with errors must not be built)."""
    spec = json.loads(auto_path(cfg, folder, f).read_text(encoding="utf-8"))
    n = len(spec["pages"])
    n0 = len(PROBLEMS)
    edits = collect_edits(load_review(cfg, key), f, n, quiet)
    spec["cands"] = {}
    mem = {}
    origins = []
    for pg in sorted(spec["pages"], key=int):
        props = _auto_labels(spec["pages"][pg])
        for i, q in enumerate(props):
            q["id"] = f"a{i}"
        e = edits.get(int(pg), {})
        cur = [] if e.get("clear") else [dict(q) for q in props]
        drop = set(e.get("delsrc", []))
        cur = [q for q in cur if q["src"] not in drop]
        for it in e.get("relabel", []):
            ref, lab = (it[0], it[1]) if len(it) == 2 else (it[:2], it[2])
            q = _target(cur, ref)
            if q: q["label"] = lab; q["_kept"] = True
            else: problem("WARN", f, pg, f"relabel {ref}: no box there", quiet)
        for g in e.get("grow", []):
            ref, box = (g[0], g[1:5]) if isinstance(g[0], str) else (g[:2], g[2:6])
            q = _target(cur, ref)
            if q:
                q["r"] = [min(q["r"][0], box[0]), min(q["r"][1], box[1]), max(q["r"][2], box[2]), max(q["r"][3], box[3])]
                q["_kept"] = True
            else: problem("WARN", f, pg, f"grow {ref}: no box there", quiet)
        for ref in e.get("keep", []):
            q = _target(cur, ref)
            if q: q["_kept"] = True
            else: problem("WARN", f, pg, f"keep {ref}: no box there", quiet)
        for ref in list(e.get("delat", [])) + list(e.get("del", [])):
            q = _target(cur, ref)
            if q: cur.remove(q)
            else: problem("WARN", f, pg, f"delete {ref}: no box there (already gone, or wrong id / point)", quiet)
        spec["cands"][pg] = [q for q in cur if q["src"] in CANDIDATE and not q.get("_kept")]
        cur = [q for q in cur if not (q["src"] in CANDIDATE and not q.get("_kept"))]
        adds = e.get("add", [])
        if adds:
            lines = lines_cached(cfg, folder, f, spec, int(pg))
        for k, a in enumerate(adds):
            if "label" not in a:
                problem("ERROR", f, pg, f"add #{k + 1} has no label", quiet); continue
            org = a.get("_origin")
            try:
                boxes = resolve_add(lines, a, mem)
                if org and org not in origins:
                    origins.append(org)
                if org:
                    org["hit"].append(int(pg)); org["label"] = a["label"]
            except LookupError as ex:
                if org and org not in origins:
                    origins.append(org)
                if org:
                    org["miss"].append(int(pg)); org["label"] = a["label"]; org["why"] = str(ex)
                    org["kind"] = next((kd for kd in ADD_KINDS if kd in a), "?")
                if not a.get("_opt"):
                    problem("ERROR", f, pg, f"add #{k + 1} ({a['label']}): {ex}", quiet)
                continue
            except (re.error, KeyError, TypeError, ValueError, IndexError) as ex:
                problem("ERROR", f, pg, f"add #{k + 1} ({a.get('label')}): malformed entry ({ex.__class__.__name__}: {ex})", quiet)
                continue
            for j, (r, rot) in enumerate(boxes):
                cur.append({"r": [round(max(0, r[0]), 4), round(max(0, r[1]), 4), round(min(1, r[2]), 4), round(min(1, r[3]), 4)],
                            "label": a["label"], "rot": rot, "src": a.get("src", "manual"),
                            "id": f"m{k}" + (f".{j}" if len(boxes) > 1 else "")})
        for q in cur:
            q.pop("_kept", None)
        spec["pages"][pg] = cur
    for org in origins:               # adds written for several pages at once
        if not org["multi"] or not org["miss"]:
            continue
        if not org["hit"]:
            problem("ERROR", f, org["key"], f"add ({org['label']}) for pages {org['key']!r} matched on no page: {org['why']}", quiet)
        elif org.get("kind") in ("table", "span", "lines") and not org["explicit"]:
            problem("WARN", f, org["key"], f"add ({org['label']}, {org['kind']}) for pages {org['key']!r} did not apply on page(s) "
                    f"{', '.join(map(str, org['miss']))}: {org['why']} - handle those pages separately, or mark the add \"optional\": true", quiet)
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
    spec["errors"] = sum(1 for lv, ff, *_ in PROBLEMS[n0:] if lv == "ERROR" and ff == f)
    return spec


def box_ids(q):
    return "+".join(q.get("ids", [q.get("id", "?")]))
