"""Parametric layout templates: same building, different internal arrangements.

The building is `cols` x `rows` cells with an outer wall. The bottom 4 interior rows are the
operations strip (receiving, packing, staging, depot); everything above it is storage.

    flow        I: DI on the left wall, DO on the right wall (flow-through)
                U: DI and DO both on the bottom wall
                L: DI at the back of the left wall (receiving there), DO on the bottom wall
    racks       v: vertical aisles (racks run top-bottom)   h: horizontal aisles
    cross       number of extra cross aisles through the storage block (0, 1 or 2)
    pack        near_out: packing stations next to the outbound docks   central: centred in the strip
"""
from __future__ import annotations

from .layout import Grid

OPS_ROWS = 4


def parallel_aisle(cols=30, rows=24, flow="I", racks="v", cross=0, pack="central",
                   n_in=2, n_out=2, n_pack=3, cell_m=1.5, levels=2):
    if cols < 12 or rows < 12:
        raise ValueError("building must be at least 12 x 12 cells")
    if n_pack < 1 or n_in < 1 or n_out < 1:
        raise ValueError("n_pack, n_in and n_out must be >= 1")
    if pack == "central":
        c0 = cols // 2 - n_pack
    elif pack == "near_out":
        c0 = cols - 8 - 2 * n_pack
    else:
        raise ValueError(f"pack must be central or near_out, got {pack!r}")
    # packing stations at c0, c0+2, ..., the depot 2 cells after the last one: all inside the walls
    if c0 < 1 or c0 + 2 * n_pack > cols - 2:
        raise ValueError(f"{n_pack} packing stations ({pack}) do not fit in {cols} columns")
    if 2 + max(n_in, n_out) > rows - 1 - OPS_ROWS or 3 + n_in + n_out + 6 > cols:
        raise ValueError(f"{n_in} inbound + {n_out} outbound docks do not fit a {cols} x {rows} building")
    g = [["#"] * cols for _ in range(rows)]
    top, bottom = 1, rows - 2 - OPS_ROWS            # storage block rows top..bottom (inclusive)
    left, right = 1, cols - 2
    # storage block
    for r in range(top, bottom + 1):
        for c in range(left, right + 1):
            g[r][c] = _storage_cell(r - top, c - left, bottom - top + 1, right - left + 1, racks, cross)
    # operations strip: all aisle, then facilities in its last two rows
    for r in range(bottom + 1, rows - 1):
        for c in range(left, right + 1):
            g[r][c] = "A"
    r1, r2 = rows - 3, rows - 2                     # the two facility rows
    # docks + the receiving buffer next to the inbound docks, staging next to the outbound docks
    if flow == "I":
        in_cells = [(r2 - i, 0) for i in range(n_in)]
        out_cells = [(r2 - i, cols - 1) for i in range(n_out)]
        recv = [(r2, 1), (r2, 2), (r1, 1), (r1, 2)]
        stage = [(r2, right), (r2, right - 1), (r1, right)]
    elif flow == "U":
        in_cells = [(rows - 1, 2 + i) for i in range(n_in)]
        out_cells = [(rows - 1, cols - 3 - i) for i in range(n_out)]
        recv = [(r1, 2), (r1, 3), (r1, 4), (r1, 5)]
        stage = [(r1, cols - 3), (r1, cols - 4), (r1, cols - 5)]
    elif flow == "L":
        in_cells = [(top + 1 + i, 0) for i in range(n_in)]
        out_cells = [(rows - 1, cols - 3 - i) for i in range(n_out)]
        recv = [(top + i, left) for i in range(4)]        # along the left aisle, next to the docks
        stage = [(r1, cols - 3), (r1, cols - 4), (r1, cols - 5)]
    else:
        raise ValueError(f"flow must be I, U or L, got {flow!r}")
    for p in in_cells:
        g[p[0]][p[1]] = "DI"
    for p in out_cells:
        g[p[0]][p[1]] = "DO"
    for p in recv:
        g[p[0]][p[1]] = "R"
    for p in stage:
        g[p[0]][p[1]] = "G"
    # packing stations on the upper facility row (the row below stays aisle so stations are reachable
    # from both sides), spaced 2 cells apart, plus the picker depot next to them
    pk_cols = [c0 + 2 * i for i in range(n_pack)]
    for c in pk_cols:
        g[r1 - 1][c] = "PK"
    g[r1 - 1][pk_cols[-1] + 2] = "H"
    return Grid(g, cell_m, levels)


def _storage_cell(i, j, h, w, racks, cross):
    """Token of storage-block cell (i, j) in an h x w block: back-to-back racks with 1-cell aisles."""
    if racks == "h":                                 # same pattern with the axes swapped
        i, j, h, w = j, i, w, h
    if i == 0 or i == h - 1:                         # cross aisles at both ends of the racks
        return "A"
    if cross and i in _cross_rows(h, cross):
        return "A"
    if j == w - 1:                                   # last column is always an aisle
        return "A"
    return "A" if j % 3 == 0 else "S"                # A S S A S S ... every bay faces an aisle


def _cross_rows(h, cross):
    return {round(h * (k + 1) / (cross + 1)) for k in range(cross)}


# the default candidate set used by the experiments (id -> template parameters)
CANDIDATES = {
    "I_v_c0_central_abc": dict(flow="I", racks="v", cross=0, pack="central", slotting="abc"),
    "I_v_c0_central_random": dict(flow="I", racks="v", cross=0, pack="central", slotting="random"),
    "I_v_c1_central_abc": dict(flow="I", racks="v", cross=1, pack="central", slotting="abc"),
    "I_h_c0_central_abc": dict(flow="I", racks="h", cross=0, pack="central", slotting="abc"),
    "U_v_c1_near_out_abc": dict(flow="U", racks="v", cross=1, pack="near_out", slotting="abc"),
    "L_v_c1_central_abc": dict(flow="L", racks="v", cross=1, pack="central", slotting="abc"),
}
