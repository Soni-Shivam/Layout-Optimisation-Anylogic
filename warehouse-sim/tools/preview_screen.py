"""Preview of the AnyLogic screen without AnyLogic: renders Main's static shapes from the generated .alp plus a
stand-in for what Main.drawLayout() draws at start-up, with sample values in the dynamic texts, and lists every
pair of texts whose boxes overlap (and texts that run out of the board).

Usage: python3 tools/preview_screen.py [layout.json] [out.png]      (after anylogic/build_model.py)
Needs Pillow and one of the fonts in build_model.FONTS (fc-match). Exit code 1 if anything overlaps.
"""
import json
import pathlib
import subprocess
import sys
import xml.etree.ElementTree as ET

from PIL import Image, ImageDraw, ImageFont

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "anylogic"))
import build_model as B  # noqa: E402

SAMPLE = {
    "dayText()": "Synthetic day 1, seed 1, 06:00 to 21:00", "clockText()": "10:41",
    "fastText()": "Skipping ahead to the first order release",
    "layoutTitle()": "As-is building, ABC storage by turnover",
    "figValue(0)": "148 m", "figValue(1)": "192 min", "figValue(2)": "100%",
    "figNote(0)": "12.2 km, 134 carts", "figNote(1)": "mean of 1197 orders", "figNote(2)": "of 1150 orders due",
    "inboundText()": "Receiving buffer holds 124 of 200 lines.\n122,549 units on the shelves.",
    "boardSoFar(0)": "113 held today", "boardSoFar(1)": "1189 released", "boardSoFar(2)": "1197 picked",
    "boardSoFar(3)": "1197 packed", "boardSoFar(4)": "1000 shipped",
}
for i in range(5):
    SAMPLE[f"boardNow({i})"] = "1190"
for k in range(4):
    SAMPLE[f"crewText({k})"] = "12 of 12 busy"


def sample(code):
    code = code.strip()
    if code in SAMPLE:
        return SAMPLE[code]
    if code == "layoutDetail()":
        return max((d for _, d in B.layout_names().values()), key=len)
    if "utilSoFar" in code:
        return "100% of the day"
    if "arrived" in code:
        return "1201 of 1201 arrived"
    if code.startswith("endLabel"):
        return B.END_ROWS[int(code[9:-1])][0]
    if code.startswith("endText"):
        return "1201 of 1201 arrived"
    if "dayText" in code:
        return "As-is building, ABC storage by turnover, Synthetic day 1, seed 1, 06:00 to 21:00"
    return "?" + code


def ui_fonts():
    """Font files of the first of build_model.FONTS that fontconfig has (what Main.pickFont() would choose)."""
    for fam in B.FONTS:
        path = {}
        for st in ("Regular", "Bold"):
            out = subprocess.run(["fc-match", "-f", "%{family}|%{file}", f"{fam}:style={st}"], capture_output=True, text=True)
            got, _, path[st] = out.stdout.partition("|")
        if fam in got.split(","):
            return path
    raise SystemExit("none of " + ", ".join(B.FONTS) + " is installed")


def rgb(v):
    v = int(v) & 0xFFFFFFFF
    return (v >> 16) & 255, (v >> 8) & 255, v & 255


def hexrgb(h):
    h = h.lstrip("#")
    return tuple(int(h[i:i + 2], 16) for i in (0, 2, 4))


def main():
    layout = pathlib.Path(sys.argv[1] if len(sys.argv) > 1 else
                          ROOT / "model/WarehouseSim/data/layouts/D40.3_63.1-P3-Xnone-asis.json")
    out = pathlib.Path(sys.argv[2] if len(sys.argv) > 2 else ROOT / "build/screen_preview.png")
    show_end = "--end" in sys.argv
    fonts, cache = ui_fonts(), {}

    def font(sz, bold):
        if (sz, bold) not in cache:
            cache[sz, bold] = ImageFont.truetype(fonts["Bold" if bold else "Regular"], sz)
        return cache[sz, bold]

    img = Image.new("RGB", (B.PAGE_W, B.PAGE_H + 20), "white")
    d = ImageDraw.Draw(img)
    boxes = []                                   # (x0, y0, x1, y1, text, layer)
    rules = []                                   # thin rects (rules, cell dividers) and outlined boxes' edges

    def text(x, y, t, sz, bold, col, align="LEFT", layer="base"):
        f = font(sz, bold)
        for j, line in enumerate(t.split("\n")):
            tw = d.textlength(line, font=f)
            xx = x - tw if align == "RIGHT" else x - tw / 2 if align == "CENTER" else x
            yy = y + j * round(sz * 1.25)
            d.text((xx, yy), line, font=f, fill=col)
            boxes.append((xx, yy, xx + tw, yy + sz * 1.15, line, layer))

    # ---- what drawLayout() draws (same arithmetic)
    L = json.loads(layout.read_text())
    grid = [r.split() if isinstance(r, str) else r for r in L["grid"]]
    cw, ch = L["cell_w"], L["cell_h"]
    Wm, Hm = L["cols"] * cw, L["rows"] * ch
    px = min((B.COL_A_W - 16 - 18 - B.KEY_W) / Wm, (B.FRAME_H - 16) / Hm)
    W, H = Wm * px, Hm * px
    d.rectangle([0, 0, B.PAGE_W, B.PAGE_H], fill=hexrgb(B.PAPER))
    d.rectangle([B.COL_A, B.FRAME_Y, B.COL_A + W + 16, B.FRAME_Y + H + 16], fill=hexrgb(B.PAPER3),
                outline=hexrgb(B.INK), width=2)
    cells = {"#": B.INK, "A": B.PAPER3, "S": "#A7ADB6", "DI": B.INK2, "DO": B.INK2, "R": "#F6DC97", "PK": B.AMBER,
             "G": "#C3CFF3", "H": B.ACCENT}
    ox, oy = B.COL_A + 8, B.FRAME_Y + 8
    for r, row in enumerate(grid):
        for q, t in enumerate(row):
            x0, y0 = ox + q * cw * px, oy + (L["rows"] - 1 - r) * ch * px
            d.rectangle([x0, y0, x0 + cw * px - 0.5, y0 + ch * px - 0.5], fill=hexrgb(cells.get(t, B.PAPER3)))
    x, y = B.COL_A + W + 16 + 18, B.FRAME_Y
    text(x, y, "Floor", 12, True, hexrgb(B.INK))
    y += 24
    for n in ["aisle", "shelf", "wall", "receiving", "packing station", "staging", "dock", "picker depot"]:
        d.rectangle([x, y + 1, x + 12, y + 13], outline=hexrgb(B.INK))
        text(x + 20, y, n, 11, False, hexrgb(B.INK2))
        y += 20
    y += 16
    text(x, y, "Workers", 12, True, hexrgb(B.INK))
    y += 24
    for n, how in [("picker", "walks a cart tour"), ("putaway", "walks to the slot"),
                   ("packer", "works at a packing station"), ("receiver", "works at receiving"),
                   ("idle", "waits at its station")]:
        d.ellipse([x + 0.5, y + 1.5, x + 11.5, y + 12.5], fill=hexrgb(B.ACCENT))
        text(x + 20, y, n, 11, False, hexrgb(B.INK2))
        text(x + 20, y + 14, how, 9, False, hexrgb(B.MUTED))
        y += 32
    y += 16
    text(x, y, f"{L['cols']} x {L['rows']} cells\n{cw:.2f} x {ch:.2f} m each\n{len(L['slots'])} slots", 10, False,
         hexrgb(B.MUTED))

    # ---- static shapes, in their z order
    R = ET.parse(ROOT / "build" / f"{B.NAME}.generated.alp").getroot()
    mainc = [c for c in R.iter("ActiveObjectClass") if c.findtext("Name") == "Main"][0]
    for sh in mainc.find("./Presentation/Level/Presentation"):
        vis = sh.findtext("VisibleCode") or ""
        if ("done" in vis) != show_end and "done" in vis:
            continue
        x, y = float(sh.findtext("X") or 0), float(sh.findtext("Y") or 0)
        if y > B.PAGE_H:
            continue                             # the flowchart section, below the board
        layer = "end" if "done" in vis else "base"
        if sh.tag in ("Rectangle", "RoundedRectangle"):
            w, h = float(sh.findtext("Width")), float(sh.findtext("Height"))
            if sh.findtext("WidthCode"):
                w *= 0.6
            fc, lc = sh.findtext("FillColor"), sh.findtext("LineColor")
            d.rectangle([x, y, x + w, y + h], fill=rgb(fc) if fc else None, outline=rgb(lc) if lc else None,
                        width=int(float(sh.findtext("LineWidth") or 1)) if lc else 0)
            if not sh.findtext("WidthCode"):
                if min(w, h) <= 3:
                    rules.append((x, y, x + w, y + h, layer))
                elif lc:
                    rules += [(x, y, x + w, y, layer), (x, y + h, x + w, y + h, layer),
                              (x, y, x, y + h, layer), (x + w, y, x + w, y + h, layer)]
        elif sh.tag == "Text":
            t = sh.findtext("Text") or ""
            if sh.findtext("TextCode"):
                t = sample(sh.findtext("TextCode"))
            col = rgb(sh.findtext("Color"))
            if "boardNow(0) > 0" in (sh.findtext("ColorCode") or ""):
                col = hexrgb(B.INK)
            text(x, y, t, int(sh.findtext("./Font/Size")), sh.findtext("./Font/Style") == "1", col,
                 sh.findtext("Alignment"), layer)
        elif sh.tag == "TimePlot":
            w, h = float(sh.findtext("Width")), float(sh.findtext("Height"))
            ca = sh.find("ChartArea")
            cx, cy = x + float(ca.findtext("XOffset")), y + float(ca.findtext("YOffset"))
            d.rectangle([cx, cy, cx + float(ca.findtext("Width")), cy + float(ca.findtext("Height"))],
                        fill=hexrgb(B.PAPER3), outline=hexrgb(B.RULE))
    img.save(out)

    bad = 0
    for i, a in enumerate(boxes):
        if a[2] > B.PAGE_W - 8 or a[0] < 0:
            print(f"OFF BOARD: {a[4]!r}")
            bad += 1
        for r in rules:
            if r[4] == a[5] and a[0] < r[2] + 2 and r[0] - 2 < a[2] and a[1] < r[3] and r[1] < a[3]:
                print(f"CROSSES A RULE: {a[4]!r}")
                bad += 1
                break
        for b in boxes[i + 1:]:
            if a[5] == b[5] and a[0] < b[2] - 1 and b[0] < a[2] - 1 and a[1] < b[3] - 1 and b[1] < a[3] - 1:
                print(f"OVERLAP: {a[4]!r} x {b[4]!r}")
                bad += 1
    print(f"wrote {out}; {bad} problem(s)")
    sys.exit(1 if bad else 0)


if __name__ == "__main__":
    main()
