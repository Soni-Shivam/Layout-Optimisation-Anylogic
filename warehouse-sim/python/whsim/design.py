"""The real footwear warehouse (Mendeley pf2w725pw3, floor Z = 1) as a grid, and layout designs given
purely in coordinates (metres, in the dataset's own frame: x across, y along the building).

Building, from the data (Storage_Location.csv and Support_Points_Navigation.csv, decimetres -> metres):
  * 864 shelf bays (each holds 2-4 storage locations on 4 levels) in back-to-back double rows; the 18
    bays above the centre cross aisle are level-3/4 overhead shelves and are left out (36 of 2,292 locations),
  * 17 picking aisles along x at y = -2.9 + 9 k m (one wider gap at y = 63.1 m),
  * 3 cross aisles along y at x = 6.6, 40.3 and 68.6 m,
  * the central depot (pick-up / drop-off point) at (40.3, 63.1) m,
  * no racks in the lower-right quarter (x > 40.3, y < 60 m): used here as the dock and packing area
    (an ASSUMPTION - the dataset has no dock or packing-station positions).

Grid: one column per bay (cell_w = 5/3 m, three bays per 5 m) and one row per 3 m (aisle, rack, rack, ...),
so every bay sits on its own cell with at most 0.37 m snapping error. Row r / column c has its centre at
x = 6.6 + (c - 1) * 5/3, y = -2.9 + (r - 1) * 3.

A DESIGN is a dict of coordinates and one policy (all optional except slotting):
    depot         [x, y]          pick-up / drop-off point, snapped to the nearest open aisle cell
    n_pack        int             packing stations, put on the free aisle cells closest to the depot
    cross_aisles  [x, ...]        EXTRA cross aisles: the rack column nearest each x becomes an aisle
                                  (its bays are lost; every SKU must still get a slot)
    slotting      asis (real storage, from the picks) | random | class | abc
"""
from __future__ import annotations

import csv
import hashlib
import json
import pathlib

from .layout import SLOTTING as SLOTTING_POLICIES, Grid, NEIGHBOURS, compile_layout

ROOT = pathlib.Path(__file__).resolve().parents[2]
RAW = ROOT / "data_raw" / "mendeley"
BAYS = ROOT / "data" / "real" / "bays.csv"

CELL_W, CELL_H = 5.0 / 3.0, 3.0
X1, Y1 = 6.6, -2.9                      # metres at column 1 / row 1 (left cross aisle / first picking aisle)
ROWS, COLS = 53, 40                     # rows 1..51 and columns 1..38 are inside the walls
ORIGIN = (X1 - 1.5 * CELL_W, Y1 - 1.5 * CELL_H)
CROSS_COLS = (1, 21, 38)                # existing cross aisles (x = 6.6, 40.3, 68.6 m)
WIDE_COLS = (20, 22)                    # the central cross aisle is three cells wide
LEVELS = 4                              # SKU slots per bay in the model (real bays hold 2-4 locations x 18 cartons)
BASELINE = {"depot": [40.3, 63.1], "n_pack": 3, "cross_aisles": [], "slotting": "asis"}
ASIS = ROOT / "data" / "real" / "asis_slotting.csv"


def col_of(x):
    return int(round((x - X1) / CELL_W)) + 1


def row_of(y):
    return int(round((y - Y1) / CELL_H)) + 1


def export_bays():
    """Raw Storage_Location.csv (decimetres) -> data/real/bays.csv (one row per bay, metres, grid cell)."""
    count = {}
    with open(RAW / "Storage_Location.csv", encoding="utf-8-sig") as f:
        for r in csv.DictReader(f):
            k = (int(r["x"]), int(r["y"]))
            count[k] = count.get(k, 0) + 1
    BAYS.parent.mkdir(parents=True, exist_ok=True)
    with open(BAYS, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["x_m", "y_m", "locations", "row", "col"])
        for (x, y), n in sorted(count.items()):
            w.writerow([x / 10, y / 10, n, row_of(y / 10), col_of(x / 10)])


def export_asis_slotting():
    """Real storage: SKU -> the bay it was picked from most often (Picking_Wave.csv x Storage_Location.csv)."""
    loc = {}
    with open(RAW / "Storage_Location.csv", encoding="utf-8-sig") as f:
        for r in csv.DictReader(f):
            loc[r["originalLocation"].strip()] = (row_of(int(r["y"]) / 10), col_of(int(r["x"]) / 10))
    count = {}
    with open(RAW / "Picking_Wave.csv", encoding="utf-8-sig") as f:
        for r in csv.DictReader(f, delimiter=";"):
            r = {k.strip(): v for k, v in r.items()}
            bay = loc.get(r["locations"].strip())
            if bay is None or bay[1] in CROSS_COLS:
                continue
            sku = f"{r['reference'].strip()}_{format(float(r['Size (US)']), 'g')}"
            count.setdefault(sku, {}).setdefault(bay, 0)
            count[sku][bay] += 1
    ASIS.parent.mkdir(parents=True, exist_ok=True)
    with open(ASIS, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["sku", "row", "col", "picks_there", "picks_total"])
        for sku in sorted(count):
            bay, n = max(count[sku].items(), key=lambda kv: (kv[1], kv[0]))
            w.writerow([sku, bay[0], bay[1], n, sum(count[sku].values())])


def asis_slotting():
    if not ASIS.exists():
        export_asis_slotting()
    with open(ASIS) as f:
        return {r["sku"]: (int(r["row"]), int(r["col"])) for r in csv.DictReader(f)}


def read_bays():
    if not BAYS.exists():
        export_bays()
    with open(BAYS) as f:
        return [(float(r["x_m"]), float(r["y_m"]), int(r["row"]), int(r["col"])) for r in csv.DictReader(f)]


def base_cells():
    """Walls, aisles and racks of the real building (no facilities yet)."""
    g = [["#"] * COLS for _ in range(ROWS)]
    bays = read_bays()
    rack_rows = {r for _, _, r, _ in bays}
    for r in range(1, ROWS - 1):
        for c in range(1, COLS - 1):
            open_floor = r not in rack_rows or c in CROSS_COLS or c in WIDE_COLS
            g[r][c] = "A" if open_floor else "."
    for _, _, r, c in bays:
        if c in CROSS_COLS:          # 18 level-3/4 bays above the centre aisle: overhead, not modelled
            continue
        if g[r][c] != ".":
            raise ValueError(f"bay at row {r}, col {c} falls on an aisle")
        g[r][c] = "S"
    # the rack-free lower-right quarter is open floor
    for r in range(1, ROWS - 1):
        for c in range(22, COLS - 1):
            if g[r][c] == ".":
                g[r][c] = "A"
    return g


def rack_columns():
    """Columns that hold racks (where an extra cross aisle can go), with their x in metres."""
    g = base_cells()
    cols = sorted({c for row in g for c, t in enumerate(row) if t == "S"})
    return [(c, X1 + (c - 1) * CELL_W) for c in cols if c not in CROSS_COLS + WIDE_COLS]


def open_cells(cross_aisles=()):
    """Centres (x, y) in metres of the free aisle cells, i.e. where a depot can be placed."""
    g = _fixed_cells(cross_aisles)
    grid = Grid(g, CELL_W, CELL_H, LEVELS, ORIGIN)
    return [grid.xy(r, c) for r in range(1, ROWS - 1) for c in range(1, COLS - 1) if g[r][c] == "A"]


def _fixed_cells(cross_aisles):
    """Building + extra cross aisles + the fixed (assumed) dock and receiving / staging area."""
    g = base_cells()
    for x in cross_aisles:
        c = col_of(x)
        if not 2 <= c <= COLS - 3 or c in CROSS_COLS + WIDE_COLS:
            raise ValueError(f"cross aisle at x = {x} m is outside the rack area or on an existing aisle")
        for r in range(1, ROWS - 1):
            if g[r][c] in ("S", "."):
                g[r][c] = "A"
    # fixed operations area (ASSUMED): docks on the right wall of the rack-free quarter
    for r in (4, 5):
        g[r][COLS - 1] = "DI"
    for r in (12, 13):
        g[r][COLS - 1] = "DO"
    for r in (3, 4, 5, 6):
        for c in (36, 37):
            g[r][c] = "R"
    for r in (11, 12, 13, 14):
        g[r][37] = "G"
    return g


def apply_design(design, skus, seed=0):
    """design (coordinates) -> compiled layout dict. skus: [(sku, weight)]."""
    d = {**BASELINE, **design}
    g = _fixed_cells(d["cross_aisles"])
    # depot and packing stations next to it
    free = [(r, c) for r in range(1, ROWS - 1) for c in range(1, COLS - 1) if g[r][c] == "A"]
    grid = Grid(g, CELL_W, CELL_H, LEVELS, ORIGIN)
    dx, dy = d["depot"]
    hr, hc = min(free, key=lambda p: ((grid.xy(*p)[0] - dx) ** 2 + (grid.xy(*p)[1] - dy) ** 2, p))
    g[hr][hc] = "H"
    near = sorted((p for p in free if p != (hr, hc)),
                  key=lambda p: (abs(p[0] - hr) * CELL_H + abs(p[1] - hc) * CELL_W, p))
    placed = 0
    for r, c in near:
        if placed == d["n_pack"]:
            break
        # keep the depot's own neighbours free so it stays reachable
        if (r, c) in [(hr + a, hc + b) for a, b in NEIGHBOURS]:
            continue
        g[r][c] = "PK"
        placed += 1
    lid = design_id(d)
    fixed = asis_slotting() if d["slotting"] == "asis" else None
    return compile_layout(grid, skus, slotting=d["slotting"], layout_id=lid, template="footwear_z1",
                          params={**d, "depot_snapped": [round(v, 2) for v in grid.xy(hr, hc)]}, seed=seed, fixed=fixed)


def design_id(d):
    """Readable id from the coordinates, e.g. 'D40.3_63.1-P3-X-random' (X lists extra cross aisles)."""
    xs = "_".join(f"{x:g}" for x in sorted(d["cross_aisles"])) or "none"
    return f"D{d['depot'][0]:g}_{d['depot'][1]:g}-P{d['n_pack']}-X{xs}-{d['slotting']}"


def short_hash(d):
    return hashlib.sha1(json.dumps(d, sort_keys=True).encode()).hexdigest()[:8]
