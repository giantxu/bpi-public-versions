"""Automatic proposal of BCI (business confidential information) regions for one PDF page from OCR lines (or native text lines).

Each proposal: {"r":[x0,y0,x1,y1], "label":str, "rot":0|90, "src":rule}
Coordinates normalized to the displayed page (top-left origin).
"""
import re, unicodedata

# ---------------------------------------------------------------- helpers
def _w(ch):
    return 1.0 if unicodedata.east_asian_width(ch) in "WF" else 0.55


def is_vertical(d):
    return d["h"] > d["w"] * 1.6 and len(d["t"]) >= 3


def sub_box(d, a, b, pad=0.003):
    """box of characters t[a:b] inside OCR line d (proportional estimate)."""
    t = d["t"]
    tot = sum(_w(c) for c in t) or 1
    fa = sum(_w(c) for c in t[:a]) / tot
    fb = sum(_w(c) for c in t[:b]) / tot
    if is_vertical(d):  # reads bottom-to-top (rotated page) -> start at bottom
        y1 = d["y"] + d["h"] - fa * d["h"]
        y0 = d["y"] + d["h"] - fb * d["h"]
        return [d["x"] - pad, y0 - pad, d["x"] + d["w"] + pad, y1 + pad], 90
    x0 = d["x"] + fa * d["w"]
    x1 = d["x"] + fb * d["w"]
    return [x0 - pad, d["y"] - pad, x1 + pad, d["y"] + d["h"] + pad], 0


def line_box(d, pad=0.004):
    return [d["x"] - pad, d["y"] - pad, d["x"] + d["w"] + pad, d["y"] + d["h"] + pad], (90 if is_vertical(d) else 0)


def union(bs):
    return [min(b[0] for b in bs), min(b[1] for b in bs), max(b[2] for b in bs), max(b[3] for b in bs)]


def overlap(a, b):
    return not (a[2] <= b[0] or b[2] <= a[0] or a[3] <= b[1] or b[3] <= a[1])


# ---------------------------------------------------------------- patterns
# Text belonging to the submitting company itself; set from bpi_config.json "own_company_regex" via set_own().
OWN = re.compile(r"(?!x)x")


def set_own(regex):
    global OWN
    OWN = re.compile(regex, re.I)
NUM = r"\d{1,3}(?:[,，]\d{3})+(?:\.\d+)?|\d+(?:\.\d+)?"
AMOUNT_RES = [
    re.compile(r"(?:¥|￥|RMB|CNY|USD|US\$|RM|MYR|\$)\s*[:：]?\s*(?:" + NUM + r")(?:\s*(?:元|万元|yuan))?", re.I),
    re.compile(r"(?:" + NUM + r")\s*(?:万美元|万元|美元|元|yuan|RMB|CNY|USD|US\s*dollars?|dollars?|ringgit|RM)", re.I),
    re.compile(r"[零壹贰叁肆伍陆柒捌玖拾佰仟万亿圆元角分整]{4,}"),
    re.compile(r"(?i)(?:ringgit malaysia|say\s*(?:us\s*dollars|rmb|renminbi|usd))[A-Z \-]+only"),
    re.compile(r"(?i)\b(?:one|two|three|four|five|six|seven|eight|nine|ten|eleven|twelve|thirteen|fourteen|fifteen|sixteen|seventeen|eighteen|nineteen|twenty|thirty|forty|fifty|sixty|seventy|eighty|ninety|hundred|thousand|million|billion)(?:[\s\-]+(?:and|one|two|three|four|five|six|seven|eight|nine|ten|eleven|twelve|thirteen|fourteen|fifteen|sixteen|seventeen|eighteen|nineteen|twenty|thirty|forty|fifty|sixty|seventy|eighty|ninety|hundred|thousand|million|billion|yuan|ringgit|dollars?|only)){3,}", ),
]
BANK_RE = re.compile(r"(?i)账\s*号|帐\s*号|account\s*(?:no|number|name)?|a/c|swift|iban|税\s*号|纳税人识别号|统一社会信用代码|tax\s*(?:no|id|registration)|gst\s*id|sst|开户(?:行|银行)|银行|bank|行号|routing|beneficiary")
CONTACT_RE = re.compile(r"(?i)\btel\b|电\s*话|\bfax\b|传\s*真|e-?mail|邮\s*箱|手\s*机|mobile|phone|联系人|contact\s*person|地\s*址|address|邮\s*编|post\s*code|zip")
PERSON_RE = re.compile(r"(?i)法定代表人|委托代理人|授权代表|代表人|负责人|经办人|联系人|项目经理|签\s*字|签\s*名|signature|signed\s*by|legal\s*(?:person|representative)|authori[sz]ed\s*(?:agent|representative|signatory)|entrusted\s*agent|salesman|attn|prepared\s*by|approved\s*by|checked\s*by|manager")
PAY_RE = re.compile(r"(?i)付款|支付|预付|进度款|结算款|尾款|质保金|保证金|保修金|履约|定金|货款|payment|advance|retention|warranty\s*(?:bond|money|deposit)|deposit|instal(?:l)?ment|balance")
LD_RE = re.compile(r"(?i)违约金|扣罚|罚款|赔偿.*%|liquidated|penalt")
PCT_RE = re.compile(r"\d+(?:\.\d+)?\s*[%％‰]|百分之|千分之|万分之|[一二三四五六七八九十]成|per\s*cent")
PRICE_HDR = re.compile(r"(?i)单\s*价|合\s*价|总\s*价|金\s*额|价\s*格|价\s*款|造\s*价|费\s*用|小\s*计|合\s*计|总\s*计|含税|不含税|unit\s*price|amount|total|price|sum|value|subtotal")
QTY_HDR = re.compile(r"(?i)^(?:数\s*量|工\s*程\s*量|qty\.?|quantity|数量\s*\(.*\)|数量（.*）)$|^数\s*量")
NUMERIC = re.compile(r"^[\s¥￥$]*[-+]?(?:\d{1,3}(?:[,，]\d{3})+|\d+)(?:[.．]\d+)?\s*(?:元|万元|%)?$")


SUFFIX = re.compile(r"[\w\s.,&()（）'-]{0,45}?(?:co\.?\s*,?\s*ltd\.?|limited|corp(?:oration)?\.?(?:\s*,?\s*ltd\.?)?|sdn\.?\s*bhd\.?|有限责任公司|有限公司|集团公司)", re.I)

# ---------------------------------------------------------------- rules
def propose(lines, terms, page_kind="scan"):
    """lines: OCR dicts {t,x,y,w,h}; terms: list of (regex_string, label) supplier-specific sensitive terms"""
    out = []

    def add(box, rot, label, src):
        out.append({"r": [round(max(0, box[0]), 4), round(max(0, box[1]), 4), round(min(1, box[2]), 4), round(min(1, box[3]), 4)],
                    "label": label, "rot": rot, "src": src})

    # 1. supplier-specific terms (names, abbreviations, addresses, phone numbers, doc numbers with abbreviations)
    LABEL_RE = re.compile(r"^\s*[^：:]{0,22}[：:]\s*")
    for pat, label in terms:
        rx = re.compile(pat)
        for d in lines:
            t = d["t"]
            ms = list(rx.finditer(t))
            if not ms:
                continue
            if label.startswith("Supplier name") and len(t) <= 48 and not OWN.search(t):
                # short line (name / address line): bracket everything after a leading label like "卖方："
                lm = LABEL_RE.match(t)
                a = lm.end() if (lm and lm.end() <= ms[0].start()) else 0
                if a == 0 and "address" not in label:
                    a = min(m.start() for m in ms) if re.search(r"[A-Za-z一-鿿]", t[:min(m.start() for m in ms)]) and len(t[:min(m.start() for m in ms)]) > 12 else 0
                b, rot = sub_box(d, a, len(t))
                add(b, rot, label, "term")
            else:
                for m in ms:
                    end = m.end()
                    if label.startswith("Supplier"):
                        ext = SUFFIX.match(t, end)
                        if ext:
                            end = ext.end()
                    b, rot = sub_box(d, m.start(), end)
                    add(b, rot, label, "term")

    for d in lines:
        t = d["t"]
        own = bool(OWN.search(t))
        # 2. bank / tax lines -> whole line (own company too: account numbers must be bracketed)
        if BANK_RE.search(t) and (re.search(r"\d{5,}|[A-Z]{6}[A-Z0-9]{2,5}\b", t) or (not own and re.search(r"[：:]\s*\S{2,}", t))):
            if not (own and not re.search(r"\d{5,}", t)):  # the submitting company's bank *name* alone stays public
                b, rot = line_box(d)
                add(b, rot, "Bank account / tax ID information", "bank")
                continue
        # 3. supplier contact lines (not the submitting company's own)
        if CONTACT_RE.search(t) and not own and (re.search(r"\d{4,}|@|[省市区县路号]|road|street|district|province|city|china", t, re.I)):
            b, rot = line_box(d)
            add(b, rot, "Supplier contact information", "contact")
            continue
        # 4. personal names after keyword
        m = PERSON_RE.search(t)
        if m and not (re.match(r"\s*[（(]?[^：:]{0,6}[）)]?\s*[:：]", t[m.end():]) or (len(t) <= 28 and m.start() <= 3)):
            m = None
        if m:
            rest = t[m.end():]
            rest_s = re.sub(r"^[\s:：（）()/、]*", "", rest)
            if len(re.sub(r"[\s:：()（）/_.\-]", "", rest_s)) >= 2 and not re.match(r"(?i)(签字|盖章|签章|and\s*(?:seal|stamp)|&\s*(?:seal|stamp)|seal|stamp|\(?\s*signature|及|和|or\b)", rest_s) and not re.search(r"(?i)^[^A-Za-z\u4e00-\u9fff]*$", rest_s):
                a = m.end() + (len(rest) - len(rest_s))
                b, rot = sub_box(d, a, len(t))
                add(b, rot, "Name", "person")
        # 5. payment / LD clauses with percentages or amounts -> whole line
        if PCT_RE.search(t) and LD_RE.search(t):
            b, rot = line_box(d); add(b, rot, "Liquidated damages terms", "ld"); continue
        if PCT_RE.search(t) and PAY_RE.search(t):
            b, rot = line_box(d); add(b, rot, "Payment terms (percentages and timing)", "pay"); continue
        # 6. amounts inside text
        for rx in AMOUNT_RES:
            for mm in rx.finditer(t):
                if len(re.sub(r"\D", "", mm.group(0))) == 0 and rx is AMOUNT_RES[0]:
                    continue
                e_ = mm.end()
                if re.fullmatch(r"[A-Za-z \-,]*", t[e_:]) and re.search(r"(?i)only|thousand|hundred|million", t[e_:] + mm.group(0)):
                    e_ = len(t)
                b, rot = sub_box(d, mm.start(), e_)
                add(b, rot, "Amount", "amount")

    # 6a. signature fields: keyword line with nothing (or only a few chars) after it -> area to its right
    for d in lines:
        t = d["t"].strip()
        if is_vertical(d) or len(t) > 40:
            continue
        m = re.search(r"(?i)(authori[sz]ed\s*signature|signature|signed|签\s*字|签\s*名|签\s*章|法定代表人|委托代理人|授权代表|代表签字|legal\s*(?:person|representative)|entrusted\s*agent|authori[sz]ed\s*representative)[^：:]{0,12}[：:]?\s*$", t)
        if m and not OWN.search(t):
            x1 = d["x"] + d["w"]
            add([x1 - 0.005, d["y"] - d["h"] * 1.6, min(1, x1 + 0.2), d["y"] + d["h"] * 2.2], 0, "Signature", "sigfield")

    # 6b. stand-alone percentages on pages with a payment-ratio column
    if any(re.search(r"(?i)付款比例|支付比例|payment\s*ratio|比例", d["t"]) for d in lines):
        for d in lines:
            if re.fullmatch(r"\s*\d+(?:\.\d+)?\s*[%％]\s*", d["t"]):
                b, rot = line_box(d); add(b, rot, "Payment ratio", "pay")

    # 7. price tables: numeric cells under price / quantity headers
    hdrs = [d for d in lines if (PRICE_HDR.search(d["t"]) or QTY_HDR.search(d["t"].strip())) and len(d["t"]) <= 30]
    nums_all = [d for d in lines if NUMERIC.match(d["t"].strip())]
    nums_big = [d for d in nums_all if not re.fullmatch(r"\s*\d{1,2}\s*", d["t"])]
    for h in hdrs:
        vert = is_vertical(h)
        col = []
        for d in (nums_all if QTY_HDR.search(h["t"].strip()) else nums_big):
            if not vert:
                cx = d["x"] + d["w"] / 2
                if h["x"] - 0.02 <= cx <= h["x"] + h["w"] + 0.02 and d["y"] > h["y"] + h["h"] * 0.5:
                    col.append(d)
            else:
                cy = d["y"] + d["h"] / 2
                if h["y"] - 0.02 <= cy <= h["y"] + h["h"] + 0.02 and d["x"] > h["x"] + h["w"] * 0.5:
                    col.append(d)
        if not col:
            continue
        bs = [line_box(d, pad=0.006)[0] for d in col]
        u = union(bs)
        # include the header's horizontal extent so the column is continuous
        if not vert:
            u = [min(u[0], h["x"] - 0.004), u[1], max(u[2], h["x"] + h["w"] + 0.004), u[3]]
        else:
            u = [u[0], min(u[1], h["y"] - 0.004), u[2], max(u[3], h["y"] + h["h"] + 0.004)]
        add(u, 90 if vert else 0, "Quantities, unit prices and amounts", "table")
    return merge(out)


def merge(props, gap=0.012):
    """merge overlapping proposals of the same rule family; table cells merged into blocks."""
    res = []
    for p in props:
        r = p["r"]
        done = False
        for q in res:
            if q["src"] == p["src"] or {q["src"], p["src"]} <= {"amount", "table"}:
                a = q["r"]
                grown = [a[0] - gap, a[1] - gap, a[2] + gap, a[3] + gap]
                if overlap(grown, r) and (p["src"] in ("table",) or overlap(a, r)):
                    q["r"] = union([a, r])
                    if p["src"] == "table":
                        q["label"] = p["label"]; q["src"] = "table"
                    done = True
                    break
        if not done:
            res.append(dict(p))
    # second pass until stable
    changed = True
    while changed:
        changed = False
        for i in range(len(res)):
            for j in range(i + 1, len(res)):
                if res[i]["src"] == res[j]["src"] and overlap(res[i]["r"], res[j]["r"]):
                    res[i]["r"] = union([res[i]["r"], res[j]["r"]])
                    res.pop(j); changed = True; break
            if changed:
                break
    return res
