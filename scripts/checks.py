"""Machine checks that do not depend on anyone's eyes: audit, acknowledgements, gate, next step.

audit   reads the SOURCE text (OCR cache / text layer) and the final brackets and lists
        - text cut by a bracket edge (half a name or number left visible),
        - sensitive-looking content that no bracket covers (supplier terms, company names, amounts,
          bank / contact / ID numbers, names after "Legal representative:", payment percentages,
          invoice numbers with a counterparty code, remarks naming manufacturers, seals, QR codes).
        Every finding is either fixed in the review file or acknowledged with a written reason.
gate    PASS / FAIL per unit: clean edit file, fresh build, audit and qa with no open findings,
        Public sheets regenerated after the build and attested as viewed. "Done" means gate PASS.
"""
import hashlib, json, os, re, time
from pathlib import Path

import cfg as C
import edits as E

MUST = ("term", "company", "cut", "half", "bank", "contact", "person", "pay", "ld", "amount", "amtwords", "invno",
        "remark", "number", "seal", "code")
HINT = {
    "cut": "a bracket edge cuts this text - extend the bracket (text / lines / grow edit) so the whole item is inside",
    "half": "a bracket covers only the upper or lower half of this line - extend it",
    "term": "a supplier term is not inside any bracket",
    "company": "a company name that is not the submitter's is not inside any bracket",
    "number": "a long number (account, phone, ID ...) is not inside any bracket",
    "seal": "a seal / seal fragment is not inside any bracket - identify whose it is",
    "code": "a QR code / barcode is not bracketed - bracket it unless its content is printed in clear on the page",
}
COMPANY = re.compile(r"(?i)有限责任公司|有限公司|集团公司|股份公司|\bco\.?\s*,?\s*ltd\b\.?|sdn\.?\s*bhd\b\.?|\bgmbh\b|\bllc\b|\bpte\b\.?\s*ltd|"
                     r"(?-i:\b(?:Limited|LIMITED)\b(?!\s+to)|\b(?:Corp|CORP)\b\.?|\b(?:Corporation|CORPORATION)\b|\b(?:Inc|INC)\b\.?)")
LONGNUM = re.compile(r"\d[\d \-]{7,}\d")
DATE = re.compile(r"(?:19|20)\d{2}\s*[-./年]\s*\d{1,2}\s*[-./月]\s*\d{1,2}日?")
EMAIL = re.compile(r"[\w.+-]+@[\w-]+\.[\w.-]+|(?i:\bwww\.[\w-]+\.[\w./-]+|https?://[\w./?=&%-]+)")


def fid(kind, f, pg, text, r=None):
    t = re.sub(r"\s+", "", text)[:60]
    k = f"{kind}|{f}|{pg}|{t}|" + ("" if r is None else ",".join(f"{v:.2f}" for v in r))
    return hashlib.sha1(k.encode("utf-8")).hexdigest()[:6]


def cover(box, regs):
    """fraction of box area lying inside brackets"""
    a = max(1e-9, (box[2] - box[0]) * (box[3] - box[1]))
    s = 0.0
    for q in regs:
        r = q["r"]
        ix = min(r[2], box[2]) - max(r[0], box[0]); iy = min(r[3], box[3]) - max(r[1], box[1])
        if ix > 0 and iy > 0:
            s += ix * iy
    return min(1.0, s / a)


def _red_text(r, lines):
    """a red-ink cluster that is really printed / overlaid red text: flat and wide, or mostly filled by text lines"""
    w, h = r[2] - r[0], r[3] - r[1]
    if h < 0.05 and w > 3 * h * 0.7:          # flat strip (page is taller than wide: compare in page units)
        return True
    area, s = max(1e-9, w * h), 0.0
    for d in lines:
        ix = min(d["x"] + d["w"], r[2]) - max(d["x"], r[0]); iy = min(d["y"] + d["h"], r[3]) - max(d["y"], r[1])
        if ix > 0 and iy > 0 and len(d["t"].strip()) >= 4:
            s += ix * iy
    return s / area > 0.5


def _inside_text(lines, r):
    return " / ".join(d["t"].strip() for d in lines if r[0] <= d["x"] + d["w"] / 2 <= r[2] and r[1] <= d["y"] + d["h"] / 2 <= r[3])[:90]


# --------------------------------------------------------------------------- QR / barcodes (optional)
def _codes_bin(cfg):
    import platform, shutil, subprocess
    if platform.system() != "Darwin" or not shutil.which("swiftc"):
        return None
    exe = Path(cfg.work) / "bin" / "codes_vision"
    if not exe.exists():
        exe.parent.mkdir(parents=True, exist_ok=True)
        src = Path(__file__).resolve().parent / "codes_vision.swift"
        if subprocess.run(["swiftc", "-O", str(src), "-o", str(exe)], capture_output=True).returncode != 0:
            return None
    return exe


def page_codes(cfg, folder, f, path, npages, compute=True):
    """QR codes / barcodes per page (cached). -> {page: [{"r","t","s"}]} or None when no decoder exists."""
    import subprocess, tempfile
    cache = cfg.work / "codes" / C.safe(folder) / f"{f}.json"
    if cache.exists() and cache.stat().st_mtime >= Path(path).stat().st_mtime:
        return {int(k): v for k, v in json.loads(cache.read_text(encoding="utf-8")).items()}
    if not compute:
        return {}
    exe = _codes_bin(cfg)
    cv = None
    if not exe:
        try:
            import cv2, numpy  # noqa
            cv = cv2
        except ImportError:
            return None
    from compat import fitz
    doc = fitz.open(path)
    res = {}
    tmp = tempfile.mkdtemp()
    for i, page in enumerate(doc):
        if page.rotation:
            page.remove_rotation()
        png = os.path.join(tmp, f"{i}.png")
        page.get_pixmap(dpi=150).save(png)
        found = []
        if exe:
            out = subprocess.run([str(exe), png], capture_output=True, text=True).stdout
            for c in json.loads(out or "[]"):
                found.append({"r": [c["x"], c["y"], c["x"] + c["w"], c["y"] + c["h"]], "t": c.get("t", ""), "s": c.get("s", "")})
        else:
            img = cv.imread(png)
            ok, texts, pts, _ = cv.QRCodeDetector().detectAndDecodeMulti(img)
            if ok:
                H, W = img.shape[:2]
                for t, p in zip(texts, pts):
                    xs, ys = [q[0] for q in p], [q[1] for q in p]
                    found.append({"r": [min(xs) / W, min(ys) / H, max(xs) / W, max(ys) / H], "t": t, "s": "QR"})
        os.remove(png)
        if found:
            res[i + 1] = found
    cache.parent.mkdir(parents=True, exist_ok=True)
    cache.write_text(json.dumps(res, ensure_ascii=False), encoding="utf-8")
    return res


# --------------------------------------------------------------------------- audit
def audit_unit(cfg, key, folder, only=None, codes=True):
    """-> (items, notes). item = {id, kind, file, out, page, r, text, tier}"""
    import propose as P
    P.set_own(cfg["own_company_regex"], cfg["own_code_regex"])
    own, own_code = cfg.own_re, C.rx_join(cfg["own_code_regex"])
    terms = cfg.terms(key)
    items, notes, seen = [], [], set()
    nocodes = False

    def add(kind, f, out, pg, r, text, tier="must"):
        i = fid(kind, f, pg, text, r)
        if i in seen:
            return
        seen.add(i)
        items.append({"id": i, "kind": kind, "file": f, "out": out, "page": int(pg), "r": [round(v, 3) for v in r],
                      "text": text.strip()[:110], "tier": tier})

    for f, path, mode, out in C.files(cfg, folder):
        if only and f not in only:
            continue
        if not E.auto_path(cfg, folder, f).exists():
            notes.append(f"{f}: no proposals yet (run propose)"); continue
        spec = E.final_spec(cfg, key, folder, f, quiet=True)
        auto = json.loads(E.auto_path(cfg, folder, f).read_text(encoding="utf-8"))
        cds = page_codes(cfg, folder, f, path, len(spec["pages"]), compute=codes is True) if codes else {}
        if cds is None:
            nocodes, cds = True, {}
        for pg in sorted(spec["pages"], key=int):
            regs = spec["pages"][pg]
            lines = E.lines_cached(cfg, folder, f, spec, int(pg))
            # 1. text cut by a bracket edge
            for d in lines:
                t = d["t"]
                if len(t.strip()) < 3 or own.search(t):
                    continue                      # the submitter's own details may be visible
                x0, y0, x1, y1 = d["x"], d["y"], d["x"] + d["w"], d["y"] + d["h"]
                vert = P.is_vertical(d)
                for q in regs:
                    r = q["r"]
                    along = (min(y1, r[3]) - max(y0, r[1])) / max(1e-6, d["h"]) if vert else (min(x1, r[2]) - max(x0, r[0])) / max(1e-6, d["w"])
                    across = (min(x1, r[2]) - max(x0, r[0])) / max(1e-6, d["w"]) if vert else (min(y1, r[3]) - max(y0, r[1])) / max(1e-6, d["h"])
                    if along <= 0 or across <= 0:
                        continue
                    if across >= 0.6 and 0.06 < along < 0.94:
                        n = len(t)
                        a, b = P.char_span(d, r)
                        vis = t[:a] + t[b:]
                        if len(re.findall(r"[0-9A-Za-z\u4e00-\u9fff]", vis)) < 2 or not re.search(r"[0-9A-Za-z\u4e00-\u9fff]", t[a:b]):
                            continue
                        sep = r"[\s:：,，;；、。.()（）\[\]/|]"
                        cut_l = 0 < a < n and not re.match(sep, t[a - 1]) and not re.match(sep, t[a])
                        cut_r = 0 < b < n and not re.match(sep, t[b - 1]) and not re.match(sep, t[b])
                        if (cut_l or cut_r) and cover([x0, y0, x1, y1], [o for o in regs if o is not q]) < 0.3:
                            add("cut", f, out, pg, [x0, y0, x1, y1], f"{t[:a]}⟦{t[a:b]}⟧{t[b:]}   (⟦ ⟧ = inside '{q['label'][:28]}')")
                    elif along >= 0.5 and 0.25 < across < 0.6 and not vert and cover([x0, y0, x1, y1], regs) < 0.6 \
                            and len(re.findall(r"[0-9A-Za-z\u4e00-\u9fff]", t)) >= 6:
                        add("half", f, out, pg, [x0, y0, x1, y1], t)
            # 2. automatic text proposals that ended up outside every bracket
            for q in P.propose(lines, terms, mode):
                if q["src"] in ("term", "bank", "contact", "person", "pay", "ld", "amount", "amtwords", "invno", "remark") \
                        and cover(q["r"], regs) < 0.6:
                    add(q["src"], f, out, pg, q["r"], _inside_text(lines, q["r"]) or q["label"])
            # 3. company names, long numbers, e-mail / web addresses
            for d in lines:
                t = d["t"]
                if own.search(t):
                    continue
                m = COMPANY.search(t)
                if m and len(t) < 90:
                    b, _ = P.sub_box(d, max(0, m.start() - 6), m.end())
                    if cover(b, regs) < 0.6:
                        add("company", f, out, pg, b, t)
                for m in list(LONGNUM.finditer(t)) + list(EMAIL.finditer(t)):
                    tok = m.group(0)
                    plain = "@" not in tok and not re.search(r"[A-Za-z]", tok)
                    if plain and len(re.sub(r"\D", "", DATE.sub("", tok))) < 9:
                        continue                      # dates and short numbers are not account / phone / ID numbers
                    if plain and re.search(r"[A-Za-z][-–_/.]?$", t[:m.start()]):
                        continue                      # part of a document code (INV-2023-..., P2404...), not a number
                    s0 = t.rfind(" ", 0, m.start()) + 1
                    word = t[s0:m.end()]
                    if own_code.search(word) or own.search(word):
                        continue
                    b, _ = P.sub_box(d, m.start(), m.end())
                    if cover(b, regs) < 0.6:
                        add("number" if plain else "contact", f, out, pg, b, t)
            # 4. seals proposed automatically but not bracketed; handwriting candidates (information only)
            for q in auto["pages"].get(pg, []):
                r = q["r"]
                if q["src"] in ("seal-red", "seal-sup", "seal-edge?") and cover(r, regs) < 0.6:
                    if q["src"] == "seal-red" and _red_text(r, lines):
                        continue                      # red text (e.g. an overlay translation), not a seal
                    add("seal", f, out, pg, r, f"{q['src']} {_inside_text(lines, r)}")
                elif q["src"] == "hand?" and cover(r, regs) < 0.5:
                    add("hand", f, out, pg, r, "handwriting candidate not bracketed", tier="info")
            # 5. QR codes / barcodes
            for c in cds.get(int(pg), []):
                if cover(c["r"], regs) < 0.6:
                    add("code", f, out, pg, c["r"], f"{c['s']}: {c['t'][:70]}")
    if nocodes:
        notes.append("QR / barcode detection is not available on this machine (macOS with swiftc, or pip install "
                     "opencv-python-headless) - check codes by eye on the Public sheets")
    return items, notes


# --------------------------------------------------------------------------- acknowledgements
def ack_path(cfg, key):
    return cfg.work / "ack" / f"{key}.json"


def load_acks(cfg, key):
    p = ack_path(cfg, key)
    return json.loads(p.read_text(encoding="utf-8")) if p.exists() else {}


def load_qa(cfg, key):
    p = cfg.work / "qa" / f"{key}.json"
    return json.loads(p.read_text(encoding="utf-8")) if p.exists() else None


def cmd_audit(args):
    import bpi as B
    cfg = C.Cfg()
    show_acked = "--acked" in args
    args = [a for a in args if not a.startswith("--")]
    total_open = 0
    for key, folder, only in B.targets(cfg, args, "audit"):
        items, notes = audit_unit(cfg, key, folder, only)
        acks = load_acks(cfg, key)
        (cfg.work / "audit").mkdir(exist_ok=True)
        (cfg.work / "audit" / f"{key}.json").write_text(json.dumps(items, ensure_ascii=False, indent=0), encoding="utf-8")
        must = [x for x in items if x["tier"] == "must"]
        opened = [x for x in must if x["id"] not in acks]
        info = [x for x in items if x["tier"] != "must"]
        total_open += len(opened)
        print(f"== audit {key} ({folder}): {len(opened)} open, {len(must) - len(opened)} acknowledged, {len(info)} info")
        kinds = {}
        for x in opened:
            kinds[x["kind"]] = kinds.get(x["kind"], 0) + 1
        if kinds:
            print("   open by kind: " + ", ".join(f"{k} {v}" for k, v in sorted(kinds.items(), key=lambda kv: -kv[1])))
        for x in sorted(must if show_acked else opened, key=lambda x: (x["file"], x["page"], x["r"][1])):
            st = f"ACK({acks[x['id']]['reason']})" if x["id"] in acks else ""
            print(f"   [{x['id']}] {x['kind']:8s} {x['file']} p{x['page']} @{x['r']}  {x['text']}  {st}")
        if info and not show_acked:
            byf = {}
            for x in info:
                byf[(x["file"], x["page"])] = byf.get((x["file"], x["page"]), 0) + 1
            print(f"   info: {len(info)} handwriting candidates are not bracketed on {len(byf)} pages - make sure none is a signature / initials")
        for nt in notes:
            print("   note:", nt)
        used = {x["kind"] for x in opened}
        for k in sorted(used & set(HINT)):
            print(f"   {k}: {HINT[k]}")
    print(f"TOTAL open findings: {total_open}   (fix them in the review file, or acknowledge with a reason: "
          f"bpi.py ack KEY ID [ID ...] -m \"why this is not confidential / not a leak\")")
    return total_open


def cmd_ack(args):
    """ack KEY ID [ID ...] -m "reason"        acknowledge audit / qa findings by id
       ack KEY --kind pay [--file F] [--pages 52-116] -m "reason"   acknowledge all current open findings matching"""
    cfg = C.Cfg()
    if "-m" not in args or args.index("-m") + 1 >= len(args):
        raise SystemExit('ack needs a reason:  bpi.py ack KEY ID [ID ...] -m "why this is not a leak"')
    i = args.index("-m")
    reason = args[i + 1].strip()
    rest = args[:i] + args[i + 2:]
    if len(reason) < 12:
        raise SystemExit("the reason must say why the item is not confidential / not a leak (at least a short sentence)")
    key, folder = cfg.unit(rest[0])
    if not cfg.may_write(key):
        raise SystemExit(f"unit {key} is outside BPI_UNITS for this process")
    opts, ids, k = {}, [], 1
    while k < len(rest):
        if rest[k] in ("--kind", "--file", "--pages"):
            opts[rest[k][2:]] = rest[k + 1]; k += 2
        else:
            ids.append(rest[k].strip("[],")); k += 1
    ap = cfg.work / "audit" / f"{key}.json"
    known = {x["id"]: x for x in (json.loads(ap.read_text(encoding="utf-8")) if ap.exists() else [])}
    qa = load_qa(cfg, key)
    for x in (qa or {}).get("items", []):
        known[x["id"]] = x
    if opts:
        if "kind" not in opts:
            raise SystemExit("filter acknowledgement needs --kind (and usually --file / --pages)")
        for x in known.values():
            if x["kind"] != opts["kind"] or (opts.get("file") and x["file"] != opts["file"]):
                continue
            if opts.get("pages") and x["page"] not in E.parse_pages(opts["pages"], 10 ** 6):
                continue
            ids.append(x["id"])
    acks = load_acks(cfg, key)
    n = 0
    for i_ in ids:
        if i_ not in known:
            print(f"   unknown id {i_} (run audit / qa first; ids change when the text or box changes)"); continue
        x = known[i_]
        acks[i_] = {"reason": reason, "kind": x["kind"], "file": x["file"], "page": x["page"], "text": x["text"][:80],
                    "time": time.strftime("%Y-%m-%d %H:%M")}
        n += 1
    ack_path(cfg, key).parent.mkdir(exist_ok=True)
    ack_path(cfg, key).write_text(json.dumps(acks, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"acknowledged {n} finding(s) in unit {key}. They are listed in the final report (bpi.py acks {key}).")


def cmd_acks(args):
    cfg = C.Cfg()
    import bpi as B
    for key, folder, _ in B.targets(cfg, args, "acks", need=False):
        acks = load_acks(cfg, key)
        if not acks:
            continue
        print(f"== {key}: {len(acks)} acknowledged finding(s)")
        by = {}
        for i, a in acks.items():
            by.setdefault(a["reason"], []).append((i, a))
        for reason, lst in by.items():
            print(f"   reason: {reason}  ({len(lst)})")
            for i, a in lst[:12]:
                print(f"      [{i}] {a['kind']} {a['file']} p{a['page']}: {a['text'][:70]}")
            if len(lst) > 12:
                print(f"      ... and {len(lst) - 12} more")


# --------------------------------------------------------------------------- gate / next
def unit_pages(cfg, folder):
    from compat import fitz
    return sum(len(fitz.open(p)) for _, p, _, _ in C.files(cfg, folder))


def gate_unit(cfg, key, folder, codes=True):
    """-> list of (ok, item, what to do). codes="cached": do not start QR / barcode detection (overviews)."""
    from compat import fitz
    res = []
    fl = C.files(cfg, folder)
    missing = [f for f, *_ in fl if not E.auto_path(cfg, folder, f).exists()]
    res.append((not missing, "proposals", f"bpi.py propose {key}" if missing else ""))
    if missing:
        return res
    rv = cfg.work / "review" / f"{key}.json"
    res.append((rv.exists(), "review file", f"review the sheets (bpi.py sheets {key}) and write {rv.name}; an empty object {{}} "
                                           f"only if every proposal on every page is right"))
    n0 = len(E.PROBLEMS)
    review = E.load_review(cfg, key)
    bad = E.unknown_file_keys(review, [f for f, *_ in fl])
    for f, *_ in fl:
        E.final_spec(cfg, key, folder, f, quiet=True)
    probs = E.PROBLEMS[n0:]
    res.append((not probs and not bad, "edit file applies cleanly",
                f"bpi.py check {key}  ({len(probs)} problem(s){', unknown file names: ' + ', '.join(bad) if bad else ''})"))
    outs = [(cfg.out_dir(cfg.out_pub, folder) / o, cfg.out_dir(cfg.out_bpi, folder) / o, p) for _, p, _, o in fl]
    built = all(a.exists() and b.exists() for a, b, _ in outs)
    newest_in = max([rv.stat().st_mtime if rv.exists() else 0] + [E.auto_path(cfg, folder, f).stat().st_mtime for f, *_ in fl])
    fresh = built and min(a.stat().st_mtime for a, _, _ in outs) >= newest_in
    res.append((built and fresh, "build is complete and newer than the edits", f"bpi.py build {key}"))
    if built:
        bad_n = [a.name for a, b, p in outs if not (len(fitz.open(a)) == len(fitz.open(b)) == len(fitz.open(p)))]
        res.append((not bad_n, "page counts match the source", "rebuild: " + ", ".join(bad_n)))
    items, _ = audit_unit(cfg, key, folder, codes=codes)
    acks = load_acks(cfg, key)
    op = [x for x in items if x["tier"] == "must" and x["id"] not in acks]
    res.append((not op, "audit: no open findings", f"bpi.py audit {key}  ({len(op)} open) - fix or acknowledge each"))
    qa = load_qa(cfg, key)
    t_out = max((a.stat().st_mtime for a, _, _ in outs if a.exists()), default=0)
    if not qa or qa["time"] < t_out:
        res.append((False, "qa run on the current build", f"bpi.py qa {key}"))
    else:
        oq = [x for x in qa["items"] if x["id"] not in acks]
        res.append((not oq, "qa: no open hits", f"bpi.py qa {key}  ({len(oq)} open) - fix, or acknowledge verified false positives"))
    pd = cfg.work / "pub" / key
    sheets = sorted(pd.glob("pub_*.png")) if pd.exists() else []
    ok_sheets = bool(sheets) and min(s.stat().st_mtime for s in sheets) >= t_out and built
    res.append((ok_sheets, "Public sheets generated from the current build", f"bpi.py pubsheets {key}"))
    v = cfg.state().get("viewed", {}).get(key)
    ok_v = bool(ok_sheets and v and v["sheets"] == len(sheets) and v["time"] >= max(s.stat().st_mtime for s in sheets))
    res.append((ok_v, "every Public sheet looked at", f"look at all {len(sheets)} images in {pd}, then: bpi.py viewed {key} {len(sheets)}"
                if ok_sheets else f"after bpi.py pubsheets {key}: look at every image, then bpi.py viewed {key} N"))
    return res


def cmd_gate(args):
    import bpi as B
    cfg = C.Cfg()
    allok = True
    for key, folder, _ in B.targets(cfg, args, "gate"):
        res = gate_unit(cfg, key, folder)
        ok = all(r[0] for r in res)
        allok &= ok
        print(f"== gate {key}: {'PASS' if ok else 'FAIL'}")
        for o, item, todo in res:
            print(f"   [{'ok' if o else 'FAIL'}] {item}" + ("" if o else f"  ->  {todo}"))
        na = len(load_acks(cfg, key))
        if ok and na:
            print(f"   {na} acknowledged finding(s) - include them in the report to the user: bpi.py acks {key}")
    print("GATE:", "PASS" if allok else "FAIL - a unit is finished only when its gate passes")
    raise SystemExit(0 if allok else 1)


def cmd_viewed(args):
    cfg = C.Cfg()
    if len(args) != 2 or not args[1].isdigit():
        raise SystemExit("usage: bpi.py viewed KEY N   (N = number of Public sheet images you have looked at)")
    key, folder = cfg.unit(args[0])
    sheets = sorted((cfg.work / "pub" / key).glob("pub_*.png"))
    if not sheets:
        raise SystemExit(f"no Public sheets for {key} - run: bpi.py pubsheets {key}")
    if int(args[1]) != len(sheets):
        raise SystemExit(f"unit {key} has {len(sheets)} Public sheet images; all of them must be looked at (you said {args[1]})")
    st = cfg.state()
    st.setdefault("viewed", {})[key] = {"sheets": len(sheets), "time": time.time()}
    cfg.save_state(st)
    print(f"recorded: all {len(sheets)} Public sheets of unit {key} were looked at")


def cmd_samples_ok(args):
    cfg = C.Cfg()
    if not args or len(" ".join(args)) < 8:
        raise SystemExit('usage: bpi.py samples-ok "what the user said after reviewing the sample BPI / Public files"\n'
                         "Run this only after the USER has looked at the sample outputs and agreed to the rules.")
    st = cfg.state()
    st["samples_ok"] = {"note": " ".join(args), "time": time.strftime("%Y-%m-%d %H:%M")}
    cfg.save_state(st)
    print("recorded - volume work may start")


def cmd_next(_):
    """the single next thing to do in this matter"""
    from compat import fitz
    cfg = C.Cfg()
    if not cfg.src.exists():
        return print("NEXT: set source_dir in bpi_config.json (folder not found:", cfg.src, ")")
    if cfg["own_company_regex"] == C.DEFAULTS["own_company_regex"]:
        return print("NEXT: fill own_company_regex (and own_code_regex / own_seal_text_regex / own_seal_color) in bpi_config.json, then: bpi.py doctor")
    units = cfg.units()
    todo_ocr = 0
    for key, folder in units:
        for f, path, mode, _ in C.files(cfg, folder):
            if mode == "scan":
                n = len(fitz.open(path))
                todo_ocr += sum(not (cfg.work / "ocr" / C.safe(folder) / f / f"p{i + 1:03d}.json").exists() for i in range(n))
    if todo_ocr:
        return print(f"NEXT: bpi.py ocr     ({todo_ocr} scanned pages without OCR; run it in the background if it is long)")
    if not any(cfg.terms(k) for k, _ in units):
        return print("NEXT: bpi.py parties  -> write supplier regexes into _work/terms.json, then: bpi.py terms-check")
    if not (cfg.work / "rules.md").exists():
        return print("NEXT: agree the bracketing rules with the user (references/bracketing-rules.md) and write them to _work/rules.md")
    st = cfg.state()
    sizes = sorted(((unit_pages(cfg, d), k, d) for k, d in units))
    allowed = [x for x in sizes if cfg.may_write(x[1])]
    passed = []
    for n, key, folder in allowed:
        res = gate_unit(cfg, key, folder, codes="cached")
        if all(r[0] for r in res):
            passed.append(key); continue
        lim = int(cfg["sample_units_limit"] or 0)
        if lim and len(passed) >= lim and not st.get("samples_ok"):
            return print(f"NEXT: samples first - units {', '.join(passed)} pass the gate. Show their BPI / Public files to the user, "
                         f"adjust _work/rules.md to the feedback, then: bpi.py samples-ok \"<what the user said>\"")
        o, item, todo = next(r for r in res if not r[0])
        print(f"NEXT: unit {key} ({n} pages; {len(passed)} of {len(allowed)} units pass the gate) - {item}")
        print(f"      {todo}")
        return
    print(f"ALL {len(passed)} units pass the gate. NEXT: bpi.py log all ; bpi.py acks all ; report to the user (SKILL.md step 7)")
