"""Machine checks that do not depend on anyone's eyes: audit, acknowledgements, gate, next step.

audit   reads the SOURCE text (OCR cache / text layer) and the final brackets and lists
        - text cut by a bracket edge (half a name or number left visible),
        - sensitive-looking content that no bracket covers (supplier terms, company names, amounts,
          bank / contact / ID numbers, names after "Legal representative:", payment and late-delivery
          clauses, invoice numbers with a counterparty code, remarks naming manufacturers, seals, QR codes),
        - inconsistencies: a number bracketed on one page and visible on another, a clause bracketed in
          the original but not in its translation,
        - over-bracketing: the submitter's own details inside a bracket, one bracket over a third of a
          page, labels that name nothing confidential.
        Every finding is either fixed in the review file or acknowledged with a written reason.
gate    PASS / FAIL per unit: clean edit file, fresh build, audit and qa with no open findings,
        Public sheets regenerated after the build and attested as viewed. "Done" means gate PASS.
"""
import hashlib, json, os, re, time
from pathlib import Path

import cfg as C
import edits as E

MUST = ("term", "company", "cut", "bank", "contact", "person", "pay", "ld", "amount", "amtwords", "invno",
        "remark", "number", "same", "pair", "qty", "seal", "code", "own", "wide", "label")
HINT = {
    "cut": "a bracket edge cuts this text - extend the bracket (text / lines / grow edit) so the whole item is inside",
    "same": "this number is inside a bracket elsewhere in the unit - bracket it here too (or remove the other bracket if it is public)",
    "pair": "an original and its translation must be bracketed alike - bracket the same clause in this file",
    "pay": "a payment clause is not inside any bracket (bracket the whole clause, in every language version)",
    "ld": "a late-delivery / liquidated-damages clause is not inside any bracket (whole clause, every language version)",
    "amount": "an amount / total is not inside any bracket",
    "qty": "quantities are bracketed elsewhere in this unit - include the quantity column in the bracket here too",
    "own": "over-bracketing: the submitter's own name, address, logo and seal are public - shrink the bracket or split it "
           "so that only the confidential part is inside (its own account numbers stay bracketed)",
    "wide": "over-bracketing: bracket only the confidential columns / lines (table: {\"table\": ...}; clause: {\"span\": ...}); "
            "headings, item names, specifications and the submitter's own details stay public. Never enlarge a bracket "
            "to make other findings disappear",
    "label": "over-bracketing: scan edges, punch holes, blank fields and the submitter's own logo are not confidential",
    "term": "a supplier term is not inside any bracket",
    "company": "a company name that is not the submitter's is not inside any bracket",
    "number": "a long number (account, phone, ID ...) is not inside any bracket",
    "seal": "a seal / seal fragment is not inside any bracket - read its text on a zoomed page image to identify whose it "
            "is (colour and position do not tell): the counterparty's seal is bracketed with its own rectangle, the "
            "submitter's own seal is acknowledged, quoting the words read on it",
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
NUMTOK = re.compile(r"(?<![A-Za-z\d])\d[\d,，]*(?:\.\d+)?")
PICT = re.compile(r"(?i)signature|initial|seal|stamp|chop|logo|handwrit")
THEIRS = re.compile(r"(?i)supplier|seller|vendor|contractor|manufacturer|third|counterpart")
BADLABEL = re.compile(r"(?i)scan\s*edge|page\s*edge|punch|\bholes?\b|\bblank\b|\bempty\b|noise|artefact|artifact|margin|stain|shadow|"
                      r"\b(?:buyer|purchaser|importer|own|submitter)(?:'s)?\s+(?:logo|name|address|seal|letterhead)")
PAIR_SUFFIX = re.compile(r"(?i)[\s_\-]*[(（]?(?:en|eng|english|cn|chinese|中文|英文|译文|翻译|translation|translated)[)）]?$")
PAIR_CATS = (("Payment terms", re.compile(r"(?i)payment")), ("Liquidated damages terms", re.compile(r"(?i)liquidated|penalt")))
PAIR_KEY = {"Payment terms": re.compile(r"(?i)付款|支付|payment|settlement"),
            "Liquidated damages terms": re.compile(r"(?i)违[约的]金|liquidated|penalt|late\s*delivery|延期|逾期|拖延|per\s*day")}
WIDE, WIDE_PAGE = 0.35, 0.55


def _share(rx, t):
    """share of the letters / digits of `t` that `rx` matches"""
    n = len(re.findall(r"\w", t))
    return sum(len(re.findall(r"\w", m.group(0))) for m in rx.finditer(t)) / n if n else 0.0


def canon_num(tok):
    s = tok.replace(",", "").replace("，", "")
    if "." in s:
        a, b = s.split(".", 1)
        s = a + b.rstrip("0")                     # 57600.0000 = 57600 ; 1,234.50 = 1234.5
    return s.lstrip("0")


def num_tokens(t, skip=None):
    """numbers of 5+ digits in a text line that are not dates, document codes or round figures -> [(canonical, start, end)]"""
    dates = [m.span() for m in DATE.finditer(t)]
    out = []
    for m in NUMTOK.finditer(t):
        a, b = m.span()
        if any(a < e and s_ < b for s_, e in dates):
            continue
        if re.search(r"[A-Za-z][-–_/.]$|\d[-–/]$", t[:a]) or re.match(r"[-–/]\d|[A-Za-z]{2}", t[b:]):
            continue                              # part of a document code, a date or a phone number
        c = canon_num(m.group(0))
        if len(c) < 5 or (len(c) < 7 and re.fullmatch(r"[1-9]\d?0{3,}", c)):
            continue                              # short, or a round figure that occurs everywhere
        if re.fullmatch(r"(?:19|20)\d\d(?:0[1-9]|1[0-2])(?:[0-2]\d|3[01])", c):
            continue
        if skip is not None:
            w0 = t.rfind(" ", 0, a) + 1
            if skip.search(t[w0:b]):
                continue
        out.append((c, a, b))
    return out


def same_number(v, secrets):
    """the secret that `v` equals (or differs from by at most two misread digits at an end)"""
    if v in secrets:
        return v
    if len(v) >= 6:
        for s in secrets:
            if len(s) >= 6 and abs(len(s) - len(v)) <= 2 and (s in v or v in s):
                return s
    return None


def _boundary(t, i):
    """is position i (between t[i-1] and t[i]) a word / field boundary?"""
    if i <= 0 or i >= len(t):
        return True
    a, b = t[i - 1], t[i]
    if not a.isalnum() or not b.isalnum():
        return True

    def cls(c):
        return "d" if c.isdigit() else ("c" if "一" <= c <= "鿿" else "l")
    return cls(a) != cls(b)


def _joined(t, i):
    """do t[i-1] and t[i] belong to the same word / name / number? (a bracket edge there cuts it)"""
    if i <= 0 or i >= len(t):
        return False
    a, b = t[i - 1], t[i]
    if a.isdigit() and b in ",.，" and i + 1 < len(t) and t[i + 1].isdigit():
        return True                               # 12|,345,600.00
    if a in ",.，" and b.isdigit() and i >= 2 and t[i - 2].isdigit():
        return True
    if not (a.isalnum() and b.isalnum()) or _boundary(t, i):
        return False
    if "一" <= a <= "鿿":                # CJK has no word spaces: only a short run after a label is one name
        j = i
        while j > 0 and "一" <= t[j - 1] <= "鿿":
            j -= 1
        return i - j <= 2
    return not (a.islower() and b.isupper())      # "SellerNORTHSTAR": a lost space, not one word


NUMCELL = re.compile(r"^[\s|｜:：]*\d[\d,，.]*[\s|｜:：]*$")
QTY_HEAD = re.compile(r"(?i)^[\s|｜]*(?:数\s*量|工\s*程\s*量|q['’]?ty\.?|quantit(?:y|ies)|no\.?\s*of\s*units)\s*(?:[(（][^)）]{0,12}[)）])?[\s|｜]*$")
NUMLABEL = re.compile(r"(?i)quantit|price|amount")
NOT_NUMLABEL = re.compile(r"(?i)name|term|clause|account|seal|sign|descri|payment|address|contact|manufactur|bank|tax|number|\bno\b")
UNITWORD = re.compile(r"(?i)^(?:cny|usd|rmb|myr|rm|eur|sets?|pcs?|pieces?|kgs?|tons?|mt|m[23]?|t|ea|units?|lots?|nos?|台|套|个|件|吨|米|项|批|只|块|支|根|张|组|面|元|万元)$")


def qty_cells(lines):
    """numeric cells under a quantity header -> [(header line, [cell lines])]"""
    import propose as P
    out = []
    nums = [d for d in lines if NUMCELL.match(d["t"]) and not P.is_vertical(d)]
    for h in lines:
        if not QTY_HEAD.match(h["t"]) or P.is_vertical(h):
            continue
        col = [d for d in nums if h["x"] - 0.02 <= d["x"] + d["w"] / 2 <= h["x"] + h["w"] + 0.02
               and h["y"] + h["h"] * 0.5 < d["y"] < h["y"] + 0.6]
        if col:
            out.append((h, col))
    return out


def _ink(page, dpi=200):
    """bool ink mask of a page. Black print is darker than 140 grey. Red or blue print (translations, stamps) is
    lighter - about 150 grey, thin strokes lighter still - so a clearly coloured pixel counts as ink up to 175 in
    its darkest channel. Yellow highlighter is never ink."""
    import numpy as np
    from compat import fitz
    pc = page.get_pixmap(dpi=dpi, colorspace=fitz.csRGB, alpha=False)
    rgb = np.frombuffer(pc.samples, dtype=np.uint8).reshape(pc.height, pc.width, 3).astype(np.int16)
    mn, sat = rgb.min(2), rgb.max(2) - rgb.min(2)
    return ((mn < 140) | ((sat > 50) & (mn < 175))) & ~((rgb[:, :, 0] > 180) & (rgb[:, :, 1] > 180))


def _line_mask(ink, gap=6, frac=0.03, vertical_only=False):
    """pixels of table rules, so that a character touching a rule is not joined to it and a bracket edge lying on a
    rule does not count as cutting the character. Vertical rules: runs of ink at least frac of the page height after
    bridging breaks of up to gap pixels (scanned rules are broken). Horizontal rules: runs at least frac of the page
    width with no bridging - letters of a word are separated by a pixel or two, and bridging would turn a line of
    small text into a 'rule'. One pixel either side of a rule is included (blurred scan edges)."""
    import numpy as np

    def runs(m, n):            # m: bool [rows, cols]; -> pixels in vertical runs >= n
        fw = np.zeros(m.shape, np.int32); bw = np.zeros(m.shape, np.int32)
        c = np.zeros(m.shape[1], np.int32)
        for y in range(m.shape[0]):
            c = (c + 1) * m[y]; fw[y] = c
        c[:] = 0
        for y in range(m.shape[0] - 1, -1, -1):
            c = (c + 1) * m[y]; bw[y] = c
        return m & (fw + bw - 1 >= n)
    H, W = ink.shape
    a = ink | np.roll(ink, 1, 1) | np.roll(ink, -1, 1)          # a skewed rule steps one column sideways
    d = a.copy()                                               # close vertical breaks of up to gap pixels
    for k in range(1, gap // 2 + 1):
        d |= np.roll(a, k, 0) | np.roll(a, -k, 0)
    e = d.copy()
    for k in range(1, gap // 2 + 1):
        e &= np.roll(d, k, 0) & np.roll(d, -k, 0)
    v = runs(e | a, int(frac * H))
    v |= np.roll(v, 1, 1) | np.roll(v, -1, 1)
    if vertical_only:
        return ink & v
    h = runs(ink.T, int(frac * W)).T
    h |= np.roll(h, 1, 0) | np.roll(h, -1, 0)
    return ink & (v | h)


def vertical_rules(page, y0=0.0, y1=1.0, dpi=200):
    """vertical table rules between y0 and y1 -> [(fit, ya, yb)]: fit(y) = x of the rule at height y (page
    fractions, a straight line fitted to the rule, so a skewed scan shows as a drift), ya..yb = where it runs."""
    import numpy as np
    ink = _ink(page, dpi)
    H, W = ink.shape
    v = _line_mask(ink, vertical_only=True)
    a, b = int(y0 * H), max(int(y0 * H) + 1, int(y1 * H))
    prof = v[a:b].sum(0)
    out, x = [], 0
    while x < W:
        if prof[x] < 0.15 * (b - a):
            x += 1; continue
        x2 = x
        while x2 + 1 < W and prof[x2 + 1] >= 0.02 * (b - a):
            x2 += 1
        lo, hi = max(0, x - 8), min(W, x2 + 9)
        ys, xs = np.nonzero(v[a:b, lo:hi])
        if len(ys) > 20:
            ys = (ys + a + 0.5) / H; xs = (xs + lo + 0.5) / W
            m, c = np.polyfit(ys, xs, 1)
            out.append((lambda y, m=m, c=c: m * y + c, float(ys.min()), float(ys.max())))
        x = x2 + 9
    return out


def cmd_columns(args):
    """columns KEY FILE PAGE [Y0 Y1]: the vertical rules of a table with their drift, and where a column bracket's
    left / right edge has to be in each band of rows. A scanned table is rarely straight: one rectangle with
    straight edges fits the top rows and cuts the characters of the bottom ones (or the reverse)."""
    import bpi as B
    from compat import fitz
    cfg = C.Cfg()
    if len(args) < 3:
        raise SystemExit("usage: bpi.py columns KEY FILE PAGE [Y0 Y1]   (Y0 Y1 = the rows of the table, page fractions)")
    key, folder = cfg.unit(args[0])
    f, path, mode, out = B._find_file(cfg, folder, args[1])
    pg = int(args[2])
    y0, y1 = (float(args[3]), float(args[4])) if len(args) > 4 else (0.0, 1.0)
    page = fitz.open(path)[pg - 1]
    if page.rotation:
        page.remove_rotation()
    rl = vertical_rules(page, y0, y1)
    if not rl:
        print("no vertical rules found in that range - a table without ruled columns: place edges by text (table / text edits)")
        return
    ya, yb = max(y0, min(r[1] for r in rl)), min(y1, max(r[2] for r in rl))
    drift = max(abs(r[0](yb) - r[0](ya)) for r in rl)
    n = max(1, min(12, int(drift / 0.002 + 0.999)))
    print(f"{out} p{pg}: {len(rl)} vertical rules, y {ya:.3f}-{yb:.3f}, drift up to {drift:.4f} of the page width")
    for i, (fx, a, b) in enumerate(rl):
        print(f"   R{i + 1:<2d} x {fx(a):.4f} (y {a:.3f})  ->  {fx(b):.4f} (y {b:.3f})")
    if n == 1:
        print("one rectangle per column is enough: x0 = the rule left of the column, x1 = the rule right of it")
        return
    print(f"split each column bracket into {n} rectangles, one per band of rows - x0 / x1 = the rules either side "
          f"of the column in that band (same label on each; they must touch, not overlap):")
    e = [ya + (yb - ya) * k / n for k in range(n + 1)]
    for a, b in zip(e[:-1], e[1:]):
        m = (a + b) / 2
        print(f"   y {a:.4f}-{b:.4f}:  " + "  ".join(f"R{i + 1} {fx(m):.4f}" for i, (fx, _, _) in enumerate(rl)))


def edge_cuts(cfg, page, regs, lines, backend=None, dpi=200):
    """A bracket that starts one character late or ends one early: "Invoice No.: N[ST-2023-01]", "Total 12[,345.00]".
    Character positions estimated from line boxes are too coarse to see that, so this reads the page again: for
    every text line that a bracket starts or ends in, the strip just INSIDE the bracket edge (taken from the
    source page, where the text is intact) is OCR-ed and located in the source line. If the bracketed text begins
    or ends in the middle of a word, name or number, the other part is visible in the Public version. An edge that
    runs through the ink of a character is reported as well.   page = the SOURCE page.   -> [(rect, message)]"""
    import ocr, os, tempfile
    import propose as P
    from PIL import Image
    from compat import fitz
    tasks = []
    W, H = page.rect.width, page.rect.height
    for d in lines:
        t = d["t"]
        if P.is_vertical(d) or len(re.findall(r"\w", t)) < 3:
            continue
        x0, y0, x1, y1 = d["x"], d["y"], d["x"] + d["w"], d["y"] + d["h"]
        cw = d["h"] * H / W * 0.6                 # about one character, in page-width units
        for q in regs:
            r = q["r"]
            if PICT.search(q["label"]) or min(y1, r[3]) - max(y0, r[1]) < 0.6 * d["h"] or r[0] >= x1 or r[2] <= x0:
                continue
            a, b = P.char_span(d, r)
            others = [o for o in regs if o is not q]
            if r[0] - x0 > cw * 0.7 and cover([r[0] - cw, y0, r[0], y1], others) < 0.5:
                tasks.append(("L", d, q, r[0], min(x1, r[0] + 14 * cw), a))     # runs on past a short bracket:
            if x1 - r[2] > cw * 0.7 and cover([r[2], y0, r[2] + cw, y1], others) < 0.5:   # context helps the OCR
                tasks.append(("R", d, q, max(x0, r[2] - 14 * cw), r[2], b))
    if not tasks:
        return []
    pm = page.get_pixmap(dpi=dpi, colorspace=fitz.csGRAY)
    img = Image.frombytes("L", (pm.width, pm.height), pm.samples)
    import numpy as np
    # ink: black print darker than 140 grey. Red or blue print (translations, stamps) is lighter - about 150 grey,
    # thin strokes lighter still - so a clearly coloured pixel counts as ink up to 175 in its darkest channel.
    # Yellow highlighter is never ink.
    ink = _ink(page, dpi)
    rules = _line_mask(ink)
    crops, through, glyph = [], [], []
    for side, d, q, xa, xb, _ in tasks:
        pad = d["h"] * 0.3
        box = (int(round(xa * pm.width)), int((d["y"] - pad) * pm.height),
               int(round(xb * pm.width)), int((d["y"] + d["h"] + pad) * pm.height))
        crops.append(img.crop(box) if box[2] - box[0] > 6 and box[3] - box[1] > 6 else None)
        # does the edge run through a character? (one blob of ink reaching 2+ pixels to both sides of it)
        xe = box[0] if side == "L" else box[2]
        cp = max(6, int(d["h"] * pm.height * 0.6))
        ya, yb = max(0, int(d["y"] * pm.height)), min(pm.height, int((d["y"] + d["h"]) * pm.height) + 1)
        # a character: 30% of the line height - but an OCR box often spans two printed rows, so never more than
        # about a small letter (0.6% of the page height)
        tall_ = min(0.3 * (yb - ya), 0.006 * pm.height)
        win = ink[ya:yb, max(0, xe - cp):min(pm.width, xe + cp)].copy()
        c0 = xe - max(0, xe - cp)
        win &= ~rules[ya:yb, max(0, xe - cp):min(pm.width, xe + cp)]
        hit_ = False
        if win.size and 2 <= c0 < win.shape[1] - 2:
            win &= ~(win.sum(0) > 0.85 * win.shape[0])[None, :]       # cell borders
            win[win.sum(1) > 0.8 * win.shape[1], :] = False           # rules, underlines
            stack = [(int(y_), c0) for y_ in np.flatnonzero(win[:, c0])]
            seen_ = set(stack); lo_ = hi_ = c0; ys_ = [y_ for y_, _ in stack]
            while stack:
                cy_, cx_ = stack.pop()
                lo_, hi_ = min(lo_, cx_), max(hi_, cx_); ys_.append(cy_)
                for ny, nx in ((cy_ + 1, cx_), (cy_ - 1, cx_), (cy_, cx_ + 1), (cy_, cx_ - 1)):
                    if 0 <= ny < win.shape[0] and 0 <= nx < win.shape[1] and win[ny, nx] and (ny, nx) not in seen_:
                        seen_.add((ny, nx)); stack.append((ny, nx))
            hit_ = bool(ys_) and c0 - lo_ >= 3 and hi_ - c0 >= 3 and max(ys_) - min(ys_) + 1 >= tall_
        through.append(hit_)
        # is the last thing on the visible side of the edge a character (not a colon, a comma or blank paper)?
        hw = max(5, int(d["h"] * pm.height * 0.5))
        va, vb = (max(0, xe - hw), xe) if side == "L" else (xe, min(pm.width, xe + hw))
        vwin = ink[ya:yb, va:vb] & ~rules[ya:yb, va:vb]
        vwin = vwin & ~(vwin.sum(0) > 0.85 * max(1, vwin.shape[0]))[None, :] if vwin.size else vwin
        rows_ = np.flatnonzero(vwin.sum(1) >= 1) if vwin.size else []
        span_ = (rows_[-1] - rows_[0] + 1) if len(rows_) else 0
        glyph.append(bool(span_ >= tall_ and len(rows_) >= 0.75 * span_))
    gap, y, tops = 40, 40, []
    wmax = max((c.width for c in crops if c), default=0)
    if not wmax:
        return []
    sheet = Image.new("L", (wmax + 80, sum((c.height + gap) for c in crops if c) + 80), 255)
    for c in crops:
        if c is None:
            tops.append(None); continue
        sheet.paste(c, (40, y)); tops.append(y); y += c.height + gap
    fd, png = tempfile.mkstemp(suffix=".png"); os.close(fd)
    try:
        sheet.save(png)
        got = ocr.ocr_png(cfg, png, backend)
    finally:
        if os.path.exists(png):
            os.remove(png)
    seen = [[] for _ in tasks]
    for g in got:
        cy = (g["y"] + g["h"] / 2) * sheet.height
        for k, (tp, c) in enumerate(zip(tops, crops)):
            if c is not None and tp - gap / 2 <= cy < tp + c.height + gap / 2:
                seen[k].append((g["x"], g["t"])); break

    def aln(s_):
        ix = [i for i, c in enumerate(s_) if c.isalnum()]
        return "".join(s_[i] for i in ix).lower(), ix
    out, edges = [], {}
    for (side, d, q, xa, xb, pos), sv, thru, gl in zip(tasks, seen, through, glyph):
        t = d["t"]
        tn, ix = aln(t)
        vn, _ = aln(" ".join(v for _, v in sorted(sv)))
        est = sum(1 for ch in t[:pos] if ch.isalnum())
        cut = None
        for o in (0, 1):                           # o = 1: the character at the very edge was clipped and misread
            for m in (3, 2):
                key = vn[o:o + m] if side == "L" else vn[len(vn) - o - m:len(vn) - o]
                if len(key) < m:
                    continue
                ks = [k for k in range(max(0, est - 4), min(len(tn), est + 4) + 1)
                      if (tn[k:k + m] == key if side == "L" else (k >= m and tn[k - m:k] == key))]
                if ks:
                    k = min(ks, key=lambda v: abs(v - est))
                    # o = 1: the source character k-1 (L) / k (R) lies across the edge, so the cut is on its far side
                    # (only trusted for CJK, where half a character reads as another one; a digit or letter next
                    # to the bracket stroke is misread too easily)
                    half = tn[k - 1] if side == "L" and k > 0 else (tn[k] if side == "R" and k < len(tn) else "")
                    if o and not ("一" <= half <= "鿿"):
                        break
                    if side == "L" and 0 < k < len(ix):
                        cut = ix[k]
                    elif side == "R" and 0 < k < len(ix):
                        cut = ix[k - 1] + 1
                    break
            if cut is not None or len(vn) < 3:
                break
        box = [d["x"], d["y"], d["x"] + d["w"], d["y"] + d["h"]]
        nhit = len(out)
        if cut is not None and _joined(t, cut) and gl:
            out.append((box, f"{t[max(0, cut - 16):cut]}|{t[cut:cut + 16]}   - the bracket '{q['label'][:28]}' "
                        f"{'starts' if side == 'L' else 'ends'} at | , inside one word / name / number: the part "
                        f"{'before' if side == 'L' else 'after'} it stays visible"))
        elif thru and 0 < est < len(ix):
            cut = ix[est]
            out.append((box, f"{t[max(0, cut - 16):cut]}|{t[cut:cut + 16]}   - the {'left' if side == 'L' else 'right'} edge of "
                        f"the bracket '{q['label'][:28]}' (near |) runs through a character: half of it stays visible"))
        if len(out) > nhit:
            edges.setdefault((id(q), side), []).append(len(out) - 1)
    # one bracket edge that cuts many lines (a table column placed across the text) is one finding, not twenty
    drop = set()
    for (_, side), ids in edges.items():
        if len(ids) >= 3:
            ex = "; ".join(out[i][1].split("   - ")[0].strip() for i in ids[:3])
            lab = out[ids[0]][1].split("bracket '")[1].split("'")[0]
            u = [min(out[i][0][0] for i in ids), min(out[i][0][1] for i in ids), max(out[i][0][2] for i in ids), max(out[i][0][3] for i in ids)]
            out[ids[0]] = (u, f"the {'left' if side == 'L' else 'right'} edge of the bracket '{lab}' cuts through {len(ids)} text lines "
                              f"(e.g. {ex}) - move that edge into the gap between the columns / words")
            drop.update(ids[1:])
    return [o for i, o in enumerate(out) if i not in drop]


def page_ink(cfg, folder, f, path, pages_lines):
    """non-text ink of every page of a scanned file (cached per source file) -> {page: [blob]}"""
    import seals
    from compat import fitz
    cp = cfg.work / "ink" / folder / (f + ".json")
    mt = os.path.getmtime(path)
    if cp.exists():
        try:
            c = json.loads(cp.read_text(encoding="utf-8"))
            if c.get("mtime") == mt and c.get("v") == 2:
                return c["pages"]
        except Exception:
            pass
    doc, res = fitz.open(str(path)), {}
    for pg, lines in pages_lines.items():
        page = doc[int(pg) - 1]
        if page.rotation:
            page.remove_rotation()
        tb = [[d["x"], d["y"], d["x"] + d["w"], d["y"] + d["h"]] for d in lines]
        bl = seals.ink_boxes(page, tb)
        bl += [b for b in seals.faint_edge_marks(page, tb) if cover(b["r"], [{"r": o["r"]} for o in bl]) < 0.5]
        res[str(pg)] = bl
    cp.parent.mkdir(parents=True, exist_ok=True)
    cp.write_text(json.dumps({"v": 2, "mtime": mt, "pages": res}), encoding="utf-8")
    return res


def unit_ink(cfg, folder, pages):
    """{(file, page): [blob]} for the scanned pages of a unit"""
    by = {}
    for p in pages:
        if p["mode"] == "scan":
            by.setdefault((p["f"], str(p["path"])), {})[p["pg"]] = p["lines"]
    out = {}
    for (f, path), pl in by.items():
        try:
            for pg, bl in page_ink(cfg, folder, f, path, pl).items():
                out[(f, str(pg))] = bl
        except Exception:
            continue
    return out


def unit_pages_spec(cfg, key, folder):
    """every page of the unit with its final brackets and text lines"""
    res, notes = [], []
    for f, path, mode, out in C.files(cfg, folder):
        if not E.auto_path(cfg, folder, f).exists():
            notes.append(f"{f}: no proposals yet (run propose)"); continue
        spec = E.final_spec(cfg, key, folder, f, quiet=True)
        auto = json.loads(E.auto_path(cfg, folder, f).read_text(encoding="utf-8"))
        for pg in sorted(spec["pages"], key=int):
            res.append({"f": f, "out": out, "path": path, "mode": mode, "pg": pg, "regs": spec["pages"][pg],
                        "lines": E.lines_cached(cfg, folder, f, spec, int(pg)), "auto": auto["pages"].get(pg, []),
                        "n": len(spec["pages"])})
    return res, notes


def unit_secrets(pages, own_code):
    """numbers lying inside a bracket somewhere in the unit -> {canonical: (file, page)}"""
    import propose as P
    sec = {}
    for p in pages:
        regs = [q for q in p["regs"] if not PICT.search(q["label"])]   # a signature / seal box covers text only by accident
        if not regs:
            continue
        for d in p["lines"]:
            if cover([d["x"], d["y"], d["x"] + d["w"], d["y"] + d["h"]], regs) <= 0:
                continue
            for c, a, b in num_tokens(d["t"], own_code):
                bx, _ = P.sub_box(d, a, b)
                if cover(bx, regs) >= 0.8:
                    sec.setdefault(c, (p["out"], p["pg"]))
    return sec


def audit_unit(cfg, key, folder, only=None, codes=True):
    """-> (items, notes). item = {id, kind, file, out, page, r, text, tier}"""
    import propose as P
    P.set_own(cfg["own_company_regex"], cfg["own_code_regex"])
    own, own_code = cfg.own_re, C.rx_join(cfg["own_code_regex"])
    own_seal = C.rx_join(cfg["own_seal_text_regex"])
    terms = cfg.terms(key)
    term_rx = [re.compile(p) for p, _ in terms]
    items, seen = [], set()
    nocodes = False

    def add(kind, f, out, pg, r, text, tier="must"):
        i = fid(kind, f, pg, text, r)
        if i in seen:
            return
        seen.add(i)
        items.append({"id": i, "kind": kind, "file": f, "out": out, "page": int(pg), "r": [round(v, 3) for v in r],
                      "text": text.strip()[:150], "tier": tier})

    pages, notes = unit_pages_spec(cfg, key, folder)
    secrets = unit_secrets(pages, own_code)
    unit_qty = any(re.search(r"(?i)quantit", q["label"]) for p in pages for q in p["regs"])
    import seals
    ink = unit_ink(cfg, folder, [p for p in pages if not only or p["f"] in only])
    cds_by = {}
    for p in pages:
        f, out, pg, regs, lines, mode = p["f"], p["out"], p["pg"], p["regs"], p["lines"], p["mode"]
        if only and f not in only:
            continue
        if f not in cds_by:
            cds = page_codes(cfg, folder, f, p["path"], p["n"], compute=codes is True) if codes else {}
            if cds is None:
                nocodes, cds = True, {}
            cds_by[f] = cds
        # 1. text cut by a bracket edge
        for d in lines:
            t = d["t"]
            x0, y0, x1, y1 = d["x"], d["y"], d["x"] + d["w"], d["y"] + d["h"]
            if NUMCELL.match(t) and not P.is_vertical(d):
                # a table cell holding one number: its box is exact, so a bracket edge across it is a cut
                for q in regs:
                    r = q["r"]
                    al = (min(x1, r[2]) - max(x0, r[0])) / max(1e-6, d["w"])
                    ac = (min(y1, r[3]) - max(y0, r[1])) / max(1e-6, d["h"])
                    if ac >= 0.6 and min(al, 1 - al) * len(t.strip()) >= 0.35 and not PICT.search(q["label"]) \
                            and cover([x0, y0, x1, y1], [o for o in regs if o is not q]) < 0.3:
                        add("cut", f, out, pg, [x0, y0, x1, y1],
                            f"the number {t.strip()} is only {al * 100:.0f}% inside '{q['label'][:28]}' - the rest stays visible")
                continue
            if len(t.strip()) < 3 or own.search(t):
                continue                      # the submitter's own details may be visible
            vert = P.is_vertical(d)
            for q in regs:
                r = q["r"]
                along = (min(y1, r[3]) - max(y0, r[1])) / max(1e-6, d["h"]) if vert else (min(x1, r[2]) - max(x0, r[0])) / max(1e-6, d["w"])
                across = (min(x1, r[2]) - max(x0, r[0])) / max(1e-6, d["w"]) if vert else (min(y1, r[3]) - max(y0, r[1])) / max(1e-6, d["h"])
                if along <= 0 or across <= 0:
                    continue
                if across >= 0.6 and 0.06 < along < 0.94:
                    if PICT.search(q["label"]):
                        continue                  # a signature / seal box lies over the text by nature
                    n = len(t)
                    a, b = P.char_span(d, r)
                    vis = t[:a] + t[b:]
                    if len(re.findall(r"[0-9A-Za-z一-鿿]", vis)) < 2 or not re.search(r"[0-9A-Za-z一-鿿]", t[a:b]):
                        continue
                    # a block spanning many rows (a table column, a clause) ends at a column / field edge: the
                    # estimated character position is only a cut when no boundary lies near it
                    tall = ((r[2] - r[0]) if vert else (r[3] - r[1])) >= 4 * (d["w"] if vert else d["h"])
                    tol = 2 if tall else 0

                    def is_cut(i):
                        return 0 < i < n and not any(_boundary(t, j) for j in range(i - tol, i + tol + 1))
                    if (is_cut(a) or is_cut(b)) and cover([x0, y0, x1, y1], [o for o in regs if o is not q]) < 0.3:
                        add("cut", f, out, pg, [x0, y0, x1, y1], f"{t[:a]}⟦{t[a:b]}⟧{t[b:]}   (⟦ ⟧ = inside '{q['label'][:28]}')")
                elif along >= 0.5 and 0.3 < across < 0.6 and not vert and not PICT.search(q["label"]) \
                        and cover([x0, y0, x1, y1], regs) < 0.6 and len(re.findall(r"[0-9A-Za-z一-鿿]", t)) >= 6:
                    add("half", f, out, pg, [x0, y0, x1, y1], t, tier="info")
        # 2. automatic text proposals that ended up outside every bracket
        reported = []
        for q in P.propose(lines, terms, mode):
            if q["src"] in ("term", "bank", "contact", "person", "pay", "ld", "amount", "amtwords", "invno", "remark") \
                    and cover(q["r"], regs) < 0.6:
                add(q["src"], f, out, pg, q["r"], _inside_text(lines, q["r"]) or q["label"])
                reported.append({"r": q["r"]})
        # 3. company names, long numbers, e-mail / web addresses, numbers bracketed elsewhere in the unit
        for d in lines:
            t = d["t"]
            for c, a, b in num_tokens(t, own_code):
                s_ = same_number(c, secrets)
                if not s_:
                    continue
                bx, _ = P.sub_box(d, a, b)
                if cover(bx, regs) < 0.3 and cover([d["x"], d["y"], d["x"] + d["w"], d["y"] + d["h"]], regs) < 0.3 \
                        and cover(bx, reported) < 0.5:
                    sf, sp = secrets[s_]
                    add("same", f, out, pg, bx, f"{t[:70]}   (the number {t[a:b]} is bracketed in {sf} p{sp} but visible here)")
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
                    continue                      # part of a document code (INV-2023-..., PO1234...), not a number
                s0 = t.rfind(" ", 0, m.start()) + 1
                word = t[s0:m.end()]
                if own_code.search(word) or own.search(word):
                    continue
                b, _ = P.sub_box(d, m.start(), m.end())
                if cover(b, regs) < 0.6:
                    add("number" if plain else "contact", f, out, pg, b, t)
        # 3b. a quantity column left outside while the prices on the same rows are bracketed
        if unit_qty:
            numregs = [q for q in regs if NUMLABEL.search(q["label"])]
            for h, col in (qty_cells(lines) if numregs else []):
                vis = []
                for d in col:
                    bx = [d["x"], d["y"], d["x"] + d["w"], d["y"] + d["h"]]
                    if cover(bx, regs) >= 0.3:
                        continue
                    row = [d["y"] - d["h"] * 0.2, d["y"] + d["h"] * 1.2]
                    if any(q["r"][1] <= row[0] + d["h"] * 0.6 and q["r"][3] >= row[1] - d["h"] * 0.6 for q in numregs):
                        vis.append(d)
                if vis and len(vis) >= max(1, len(col) // 3):
                    u = P.union([[d["x"], d["y"], d["x"] + d["w"], d["y"] + d["h"]] for d in vis])
                    add("qty", f, out, pg, u, f"the quantities under '{h['t'].strip()[:20]}' are visible ("
                        + ", ".join(d["t"].strip() for d in vis[:8]) + ") while the prices in the same rows are bracketed")
        # 4. seals proposed automatically but not bracketed; handwriting candidates (information only)
        for q in p["auto"]:
            r = q["r"]
            if q["src"] in ("seal-red", "seal-sup", "seal-edge?") and cover(r, regs) < 0.6:
                if q["src"] == "seal-red" and _red_text(r, lines):
                    continue                      # red text (e.g. an overlay translation), not a seal
                add("seal", f, out, pg, r, f"{q['src']} {_inside_text(lines, r)}")
            elif q["src"] == "hand?" and cover(r, regs) < 0.5:
                add("hand", f, out, pg, r, "handwriting candidate not bracketed", tier="info")
        # 4b. faint marks at the page edge that are not text: a grey cross-page seal has no colour to detect it by
        for b in ink.get((f, str(pg)), []):
            if seals.edge_seal_like(b) and cover(b["r"], regs) < 0.5 \
                    and not any(cover(b["r"], [{"r": q["r"]}]) > 0.5 for q in p["auto"] if q["src"].startswith("seal")):
                r = b["r"]
                z = f"{max(0, r[0] - .03):.2f} {max(0, r[1] - .03):.2f} {min(1, r[2] + .03):.2f} {min(1, r[3] + .03):.2f}"
                add("seal", f, out, pg, r, (f"very faint mark at the page edge, hardly visible at normal size - a pale "
                    f"cross-page seal? zoom in: bpi.py page KEY \"{out}\" {pg} {z} - and read it" if b.get("faint") else
                    "faint mark at the page edge that is not text - a cross-page seal fragment? zoom in (bpi.py page) and read it"))
        # 5. QR codes / barcodes
        for c in cds_by[f].get(int(pg), []):
            if cover(c["r"], regs) < 0.6:
                add("code", f, out, pg, c["r"], f"{c['s']}: {c['t'][:70]}")
        # 6. over-bracketing: only confidential items may be bracketed - the submitter's own name and address,
        #    headings, item descriptions and empty paper stay public
        for q in regs:
            r, label = q["r"], q["label"]
            inside = [d for d in lines if cover([d["x"], d["y"], d["x"] + d["w"], d["y"] + d["h"]], [q]) >= 0.8]
            mb = BADLABEL.search(label)
            if mb:
                add("label", f, out, pg, r, f"'{mb.group(0)}' in the label '{label[:50]}' is not confidential - remove that bracket")
            pict = bool(PICT.search(label))
            theirs = bool(THEIRS.search(label))
            mine = []
            for d in inside:
                t = d["t"].strip()
                if len(t) < 4 or any(rx.search(t) for rx in term_rx):
                    continue
                if pict and theirs and re.search(r"(?i)seal|stamp|chop", label) and _share(own_seal, t) >= 0.6:
                    mine.append(t)                # "Supplier seal" lying on the submitter's own seal
                elif not pict and _share(own, t) >= 0.33 and not (P.BANK_RE.search(t) and re.search(r"\d{5,}", t)) \
                        and not re.search(r"\d[\d \-]{7,}\d", own.sub("", t)) and not COMPANY.search(own.sub("", t)):
                    mine.append(t)                # a name / address line of the submitter, not a sentence mentioning it
            if mine:
                add("own", f, out, pg, r, f"'{label[:40]}' covers the submitter's own details: " + " | ".join(mine)[:90])
            if NUMLABEL.search(label) and not NOT_NUMLABEL.search(label):
                # a bracket for numbers only: item names, specifications and column headings do not belong inside
                wordy = []
                for d in inside:
                    t = d["t"].strip()
                    al = re.findall(r"[A-Za-z一-鿿]", t)
                    if len(al) >= 4 and len(al) >= 0.6 * len(re.findall(r"\w", t)) and not UNITWORD.match(t) \
                            and not P.WORDS_NUM.search(t) and not P.CN_WORDS.search(t) and not P.PRICE_HDR.search(t):
                        wordy.append(t)
                if len(wordy) >= 12 and len(wordy) >= 0.3 * len(inside):
                    add("wide", f, out, pg, r, f"'{label[:40]}' also covers {len(wordy)} lines of descriptive text out of {len(inside)} "
                        f"(e.g. '{wordy[0][:30]}', '{wordy[1][:30]}') - bracket the number columns only")
            area = (r[2] - r[0]) * (r[3] - r[1])
            if area >= WIDE:
                add("wide", f, out, pg, r, f"one bracket ('{label[:40]}') covers {area * 100:.0f}% of the page and {len(inside)} text lines")
        total = sum((q["r"][2] - q["r"][0]) * (q["r"][3] - q["r"][1]) for q in regs)
        if total >= WIDE_PAGE and not any((q["r"][2] - q["r"][0]) * (q["r"][3] - q["r"][1]) >= WIDE for q in regs):
            add("wide", f, out, pg, [0, 0, 1, 1], f"the brackets on this page cover {total * 100:.0f}% of it in total")
    # 7. an original and its translation must be bracketed alike
    groups = {}
    for p in pages:
        groups.setdefault(PAIR_SUFFIX.sub("", Path(p["f"]).stem), {}).setdefault(p["f"], []).append(p)
    for base, fs in groups.items():
        if len(fs) < 2:
            continue
        for name, rx in PAIR_CATS:
            have = {f: next(((p["pg"], q["label"]) for p in ps for q in p["regs"] if rx.search(q["label"])), None) for f, ps in fs.items()}
            src = next(((f, v) for f, v in have.items() if v), None)
            if not src:
                continue
            for f, v in have.items():
                if v is None and (not only or f in only) and any(PAIR_KEY[name].search(d["t"]) for p in fs[f] for d in p["lines"]):
                    add("pair", f, fs[f][0]["out"], 1, [0, 0, 0, 0],
                        f"no bracket for {name.lower()} in this file, but {src[0]} p{src[1][0]} has '{src[1][1][:40]}'")
    if nocodes:
        notes.append("QR / barcode detection is not available on this machine (macOS with swiftc, or pip install "
                     "opencv-python-headless) - check codes by eye on the Public sheets")
    return items, notes


def rect_share(cfg, key):
    """(hand-placed rectangles, all additions) in the unit's review file"""
    n = r = 0
    for f, pgs in E.load_review(cfg, key).items():
        if not isinstance(pgs, dict):
            continue
        for e in pgs.values():
            for a in (e.get("add", []) if isinstance(e, dict) else []):
                n += 1
                r += "r" in a and not PICT.search(str(a.get("label", "")))
    return r, n


# --------------------------------------------------------------------------- acknowledgements
def ack_path(cfg, key):
    return cfg.work / "ack" / f"{key}.json"


# findings that are measured, not estimated: a bracket edge that runs through a character / starts inside a word is
# always wrong (half a character is either a leak or a damaged public word). The fix is to move the edge; such a
# finding can be acknowledged only with the user's own approval (--user), never on the reviewer's word alone.
NO_ACK = {"qa-cut"}


def load_acks(cfg, key, raw=False):
    """-> {id: ack}. Without raw, acknowledgements of NO_ACK kinds that lack the user's approval do not count."""
    p = ack_path(cfg, key)
    a = json.loads(p.read_text(encoding="utf-8")) if p.exists() else {}
    return a if raw else {i: x for i, x in a.items() if x.get("kind") not in NO_ACK or x.get("user")}


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
        hand = [x for x in info if x["kind"] == "hand"]
        half = [x for x in info if x["kind"] == "half"]
        if hand and not show_acked:
            byf = {(x["file"], x["page"]) for x in hand}
            print(f"   info: {len(hand)} handwriting candidates are not bracketed on {len(byf)} pages - make sure none is a signature / initials")
        if half and not show_acked:
            print(f"   info: {len(half)} line(s) are half covered by a bracket edge - if the line belongs to the bracketed item, extend the bracket:")
            for x in half[:8]:
                print(f"         {x['file']} p{x['page']}: {x['text'][:70]}")
        rr, rn = rect_share(cfg, key)
        if rn and rr / rn > 0.5 and rr >= 5:
            print(f"   info: {rr} of {rn} added brackets over text are hand-placed rectangles (\"r\") - text / after / span / lines / "
                  f"table follow the text exactly and do not over- or under-cover")
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
       ack KEY --kind pay [--file F] [--pages 52-116] -m "reason"   acknowledge all current open findings matching
       qa-cut findings: only with --user "what the user said after looking at that edge" """
    cfg = C.Cfg()
    user = ""
    if "--user" in args:
        j = args.index("--user")
        if j + 1 >= len(args):
            raise SystemExit('--user needs the words of the user, e.g. --user "checked p5 row 21, the edge only touches the table rule"')
        user = args[j + 1].strip()
        args = args[:j] + args[j + 2:]
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
    acks = load_acks(cfg, key, raw=True)
    n, refused = 0, []
    for i_ in ids:
        if i_ not in known:
            print(f"   unknown id {i_} (run audit / qa first; ids change when the text or box changes)"); continue
        x = known[i_]
        if x["kind"] in NO_ACK and not user:
            refused.append(x); continue
        acks[i_] = {"reason": reason, "kind": x["kind"], "file": x["file"], "page": x["page"], "text": x["text"][:80],
                    "time": time.strftime("%Y-%m-%d %H:%M")}
        if x["kind"] in NO_ACK:
            acks[i_]["user"] = user
        n += 1
    if refused:
        print(f"   NOT acknowledged: {len(refused)} qa-cut finding(s) - a bracket edge that runs through a character or starts "
              f"inside a word cannot be acknowledged. The measurement found ink on both sides of the edge; half a "
              f"character is either a leak (the rest of a name or number) or a damaged public word. Move the edge "
              f"into the gap, then rebuild and run qa again:")
        for x in refused:
            print(f"      [{x['id']}] {x['file']} p{x['page']}: {x['text'][:90]}")
        print("   A column that drifts across a skewed scan needs one rectangle per group of rows (or a table edit), not one "
              "straight edge for the whole column. Only if the edge still cannot be placed: show the spot to the user "
              "(bpi.py page KEY FILE PAGE public X0 Y0 X1 Y1) and, with their approval, ack ... --user \"their words\" -m \"why\".")
    ack_path(cfg, key).parent.mkdir(exist_ok=True)
    ack_path(cfg, key).write_text(json.dumps(acks, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"acknowledged {n} finding(s) in unit {key}. They are listed in the final report (bpi.py acks {key}).")


def cmd_acks(args):
    cfg = C.Cfg()
    import bpi as B
    for key, folder, _ in B.targets(cfg, args, "acks", need=False):
        acks = load_acks(cfg, key, raw=True)
        if not acks:
            continue
        void = {i for i, a in acks.items() if a.get("kind") in NO_ACK and not a.get("user")}
        print(f"== {key}: {len(acks) - len(void)} acknowledged finding(s)")
        if void:
            print(f"   {len(void)} qa-cut acknowledgement(s) without the user's approval do NOT count - fix those edges: "
                  + " ".join(sorted(void)))
        by = {}
        for i, a in acks.items():
            if i not in void:
                by.setdefault((a["reason"], a.get("user", "")), []).append((i, a))
        for (reason, user), lst in by.items():
            print(f"   reason: {reason}  ({len(lst)})" + (f"\n   approved by the user: {user}" if user else ""))
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
        nc = sum(1 for x in oq if x["kind"] in NO_ACK)
        res.append((not oq, "qa: no open hits", f"bpi.py qa {key}  ({len(oq)} open" + (f", {nc} qa-cut: move those edges, they cannot be "
                    f"acknowledged" if nc else "") + ") - fix, or acknowledge verified false positives"))
    pd = cfg.work / "pub" / key
    sheets = sorted(pd.glob("pub_*.png")) if pd.exists() else []
    ok_sheets = bool(sheets) and min(s.stat().st_mtime for s in sheets) >= t_out and built
    res.append((ok_sheets, "Public sheets generated from the current build", f"bpi.py pubsheets {key}"))
    v = cfg.state().get("viewed", {}).get(key)
    ok_v = bool(ok_sheets and v and v["sheets"] == len(sheets) and v["time"] >= max(s.stat().st_mtime for s in sheets))
    res.append((ok_v, "every Public sheet looked at", f"look at all {len(sheets)} images in {pd}, then: bpi.py viewed {key} CODE CODE ... "
                f"(the code shown on each image)" if ok_sheets else f"after bpi.py pubsheets {key}: look at every image, then bpi.py viewed {key} CODE ..."))
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
    if len(args) < 2:
        raise SystemExit("usage: bpi.py viewed KEY CODE [CODE ...]   (the code printed in the top right corner of EVERY Public "
                         "sheet image, in any order)")
    key, folder = cfg.unit(args[0])
    pd = cfg.work / "pub" / key
    sheets = sorted(pd.glob("pub_*.png"))
    if not sheets:
        raise SystemExit(f"no Public sheets for {key} - run: bpi.py pubsheets {key}")
    cj = pd / "codes.json"
    if not cj.exists():
        raise SystemExit(f"these Public sheets were made by an older version - run: bpi.py pubsheets {key}")
    cd = json.loads(cj.read_text(encoding="utf-8"))
    given = {hashlib.sha1((cd["salt"] + a.strip().upper()).encode()).hexdigest() for a in args[1:]}
    ok = given & set(cd["hashes"])
    if len(ok) != len(cd["hashes"]) or len(given) != len(ok):
        raise SystemExit(f"unit {key} has {len(sheets)} Public sheet images; {len(ok)} of the codes given are right"
                         + (f", {len(given) - len(ok)} wrong" if len(given) > len(ok) else "")
                         + ". Open every image in " + str(pd) + " and read the code in its top right corner. If you cannot "
                           "view images, say so to the user: the visual check must then be done by a person.")
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
