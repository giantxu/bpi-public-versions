"""BPI / Public version generator (PDF).

Region spec (normalized coordinates of the displayed page, origin top-left):
    {"r": [x0, y0, x1, y1], "label": "Supplier name and address", "rot": 0}
rot = 90 for content printed sideways (reads bottom-to-top).

BPI version   : original page kept intact; red single brackets drawn around each region;
                BPI header on every page.
Public version: scanned pages are re-rasterized and the bracketed pixels are painted
                white (nothing of the original survives inside the brackets); native-text
                pages use true redaction (text + image pixels removed). Black brackets and a
                public summary label are drawn in place; PUBLIC VERSION header on every page.
"""
from compat import fitz

HEADER = {"left": "", "bpi": "BUSINESS CONFIDENTIAL  -  Bracketed Information Is Business Confidential",
          "public": "PUBLIC VERSION  -  Business Confidential Information Deleted"}
JPEG_Q = 82
RED = (0.85, 0.0, 0.0)
BLACK = (0, 0, 0)
DPI = 200


def configure(cfg):
    global DPI, JPEG_Q
    HEADER.update(left=cfg["header_left"], bpi=cfg["bpi_header"], public=cfg["public_header"])
    DPI = int(cfg["dpi"]); JPEG_Q = int(cfg["jpeg_quality"])


def _abs(page, r):
    W, H = page.rect.width, page.rect.height
    return fitz.Rect(r[0] * W, r[1] * H, r[2] * W, r[3] * H)


def _brackets(page, rect, color, rot=0, width=1.1):
    t = max(3.0, min(7.0, (rect.height if rot == 0 else rect.width) * 0.25))
    s = page.new_shape()
    x0, y0, x1, y1 = rect
    if rot == 0:  # [ on left, ] on right
        s.draw_polyline([(x0 + t, y0), (x0, y0), (x0, y1), (x0 + t, y1)])
        s.draw_polyline([(x1 - t, y0), (x1, y0), (x1, y1), (x1 - t, y1)])
    else:  # text reads bottom-to-top: "[" at bottom edge, "]" at top edge
        s.draw_polyline([(x0, y1 - t), (x0, y1), (x1, y1), (x1, y1 - t)])
        s.draw_polyline([(x0, y0 + t), (x0, y0), (x1, y0), (x1, y0 + t)])
    s.finish(color=color, width=width, closePath=False)
    s.commit()


SHORT = {"Invoice No. (contains supplier abbreviation)": "Invoice No.",
         "Bank account / tax ID information": "Bank/tax info",
         "Supplier contact information": "Contact info",
         "Supplier name and address": "Supplier",
         "Supplier name": "Supplier",
         "Quantities, unit prices and amounts": "Qty/price",
         "Payment terms (percentages, amounts and timing)": "Payment terms",
         "Payment terms (percentages and timing)": "Payment terms",
         "Liquidated damages terms": "LD terms",
         "Liquidated damages rates": "LD rates",
         "Supplier logo": "Logo", "Supplier letterhead": "Letterhead",
         "Total contract price": "Price", "Payment ratio": "Ratio", "Signature": "Sig."}


def _fits(rect, text, rot, fs):
    probe = fitz.Rect(0, 0, rect.width, rect.height)
    return fitz.open().new_page(width=3000, height=3000).insert_textbox(
        probe, text, fontname="tiro", fontsize=fs, align=1, rotate=rot)


def _label(page, rect, text, rot=0):
    # narrow tall boxes (table columns) read better with a rotated label
    if rot == 0 and fitz.get_text_length(text, fontname="tiro", fontsize=6) > rect.width - 6 \
            and rect.height > 2.2 * rect.width and rect.width < 60:
        rot = 90
    if rot == 0 and _fits(fitz.Rect(0, 0, rect.width - 6, rect.height - 1), text, 0, 5.5) < 0 and text in SHORT:
        text = SHORT[text]
    if rot == 90 and _fits(fitz.Rect(0, 0, rect.width - 1, rect.height - 6), text, 90, 5.5) < 0 and text in SHORT:
        text = SHORT[text]
    _label_raw(page, rect, text, rot)


def _label_raw(page, rect, text, rot=0):
    if rot == 0:
        inner = fitz.Rect(rect.x0 + 3, rect.y0 + 0.5, rect.x1 - 3, rect.y1 - 0.5)
    else:
        inner = fitz.Rect(rect.x0 + 0.5, rect.y0 + 3, rect.x1 - 0.5, rect.y1 - 3)
    for fs in (10, 9, 8, 7, 6, 5, 4, 3.5):
        probe = fitz.Rect(0, 0, inner.width, inner.height)
        rc = fitz.open().new_page(width=3000, height=3000).insert_textbox(
            probe, text, fontname="tiro", fontsize=fs, align=1, rotate=rot)
        if rc >= 0:
            break
    rc = max(rc, 0)
    if rot == 0:  # center vertically
        r = fitz.Rect(inner.x0, inner.y0 + rc / 2, inner.x1, inner.y1)
    else:  # rot 90: unused space is on the right side -> shift right by half
        r = fitz.Rect(inner.x0 + rc / 2, inner.y0, inner.x1, inner.y1)
    page.insert_textbox(r, text, fontname="tiro", fontsize=fs, color=BLACK, align=1, rotate=rot)


def _header(page, public):
    W = page.rect.width
    band = fitz.Rect(0, 0, W, 16)
    page.draw_rect(band, color=None, fill=(1, 1, 1), overlay=True)
    if HEADER["left"]:
        page.insert_text((18, 11), HEADER["left"], fontname="tibo", fontsize=7.5, color=BLACK)
    if public:
        txt, col = HEADER["public"], BLACK
    else:
        txt, col = HEADER["bpi"], RED
    tl = fitz.get_text_length(txt, fontname="tibo", fontsize=7.5)
    page.insert_text((W - 18 - tl, 11), txt, fontname="tibo", fontsize=7.5, color=col)


def make_bpi(src, dst, spec):
    doc = fitz.open(src)
    for i, page in enumerate(doc):
        if page.rotation:
            page.remove_rotation()
        for reg in spec.get(i + 1, []):
            _brackets(page, _abs(page, reg["r"]), RED, reg.get("rot", 0))
        _header(page, public=False)
    doc.save(dst, garbage=3, deflate=True)


def _scan_page_to_image(page, regions):
    pix = page.get_pixmap(dpi=DPI)
    sx, sy = pix.width / page.rect.width, pix.height / page.rect.height
    for reg in regions:
        r = _abs(page, reg["r"])
        ir = fitz.IRect(int(r.x0 * sx) + 1, int(r.y0 * sy) + 1, int(r.x1 * sx) - 1, int(r.y1 * sy) - 1)
        pix.set_rect(ir, (255, 255, 255))
    return pix.tobytes("jpeg", jpg_quality=JPEG_Q)


def make_public(src, dst, spec, mode="scan"):
    sdoc = fitz.open(src)
    if mode == "text":
        doc = sdoc
        # comments, stamps and other annotations become page content first, so that the redaction below also
        # removes whatever of them lies inside a bracket (a sticky note or stamp is otherwise carried over intact)
        doc.bake(annots=True, widgets=True)
        for i, page in enumerate(doc):
            for reg in spec.get(i + 1, []):
                r = _abs(page, reg["r"])
                # shrink vertically so glyphs of neighbouring lines are not caught
                inset = min(r.height * 0.3, 2.5)
                page.add_redact_annot(fitz.Rect(r.x0, r.y0 + inset, r.x1, r.y1 - inset), fill=(1, 1, 1))
            page.apply_redactions(images=fitz.PDF_REDACT_IMAGE_PIXELS,
                                  graphics=fitz.PDF_REDACT_LINE_ART_NONE,
                                  text=fitz.PDF_REDACT_TEXT_REMOVE)
    else:
        doc = fitz.open()
        for i, sp in enumerate(sdoc):
            if sp.rotation:
                sp.remove_rotation()
            img = _scan_page_to_image(sp, spec.get(i + 1, []))
            np_ = doc.new_page(width=sp.rect.width, height=sp.rect.height)
            np_.insert_image(np_.rect, stream=img)
    for i, page in enumerate(doc):
        for reg in spec.get(i + 1, []):
            r = _abs(page, reg["r"])
            _brackets(page, r, BLACK, reg.get("rot", 0))
            _label(page, r, reg["label"], reg.get("rot", 0))
        _header(page, public=True)
    doc.set_metadata({})
    # bookmarks and attached files of the source often name the counterparty: the Public file carries none
    doc.set_toc([])
    for name in list(doc.embfile_names()):
        doc.embfile_del(name)
    try:
        doc.del_xml_metadata()
    except Exception:
        pass
    doc.save(dst, garbage=4, deflate=True, clean=True)
