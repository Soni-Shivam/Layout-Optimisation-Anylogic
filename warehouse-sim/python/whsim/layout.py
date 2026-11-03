"""Grid layout -> validated, compiled layout JSON (the file AnyLogic reads).

A layout is a rectangular grid of cell tokens:

    #   wall / column (not walkable)          .   unused floor (not walkable)
    A   aisle (walkable)                      S   shelf bay: `levels` pick slots, picked from a walkable neighbour
    DI  inbound dock (on the outer wall)      DO  outbound dock (on the outer wall)
    R   receiving buffer cell                 PK  packing station (one station per cell)
    G   outbound staging cell                 H   picker depot (exactly one)

Cells are cell_w x cell_h metres (columns x rows) and cell (r, c) has its centre at
origin + ((c + 0.5) cell_w, (r + 0.5) cell_h), so layouts can use the coordinates of a real building.
Every token except '#', '.' and 'S' is walkable and becomes a node of the aisle graph. Edges join
walkable 4-neighbours (length cell_w across, cell_h along). All geometry is decided here; AnyLogic only
builds what the compiled file lists.
"""
from __future__ import annotations

import heapq
import json
import random
from dataclasses import dataclass, field

SCHEMA = "whsim.layout/1"
TOKENS = {"#", ".", "A", "S", "DI", "DO", "R", "PK", "G", "H"}
WALKABLE = {"A", "DI", "DO", "R", "PK", "G", "H"}
FACILITY_TYPES = ("DI", "DO", "R", "PK", "G", "H")
NEIGHBOURS = ((-1, 0), (1, 0), (0, -1), (0, 1))   # N, S, W, E: also the preference order for slot access


class LayoutError(ValueError):
    pass


@dataclass
class Grid:
    cells: list                      # list of rows, each a list of tokens
    cell_w: float = 1.5              # metres per column
    cell_h: float = 1.5              # metres per row
    levels: int = 2                  # pick slots per shelf bay
    origin: tuple = (0.0, 0.0)       # metres: position of the grid's (row 0, col 0) corner

    @property
    def rows(self):
        return len(self.cells)

    @property
    def cols(self):
        return len(self.cells[0]) if self.cells else 0

    @staticmethod
    def parse(text_rows, cell_w=1.5, levels=2, cell_h=None, origin=(0.0, 0.0)):
        """text_rows: list of strings with space-separated tokens (square cells unless cell_h is given)."""
        return Grid([r.split() for r in text_rows], cell_w, cell_h or cell_w, levels, tuple(origin))

    def xy(self, r, c):
        """Centre of cell (r, c) in metres."""
        return self.origin[0] + (c + 0.5) * self.cell_w, self.origin[1] + (r + 0.5) * self.cell_h

    def to_text(self):
        return [" ".join(r) for r in self.cells]

    def on_boundary(self, r, c):
        return r in (0, self.rows - 1) or c in (0, self.cols - 1)


def validate(g: Grid, n_skus: int | None = None):
    """Returns a list of error strings (empty = valid)."""
    err = []
    if g.rows < 3 or g.cols < 3:
        return ["grid must be at least 3 x 3"]
    if any(len(r) != g.cols for r in g.cells):
        return ["grid rows have different lengths"]
    if g.cell_w <= 0 or g.cell_h <= 0 or g.levels < 1:
        err.append("cell_w, cell_h must be > 0 and levels >= 1")
    count = {t: 0 for t in TOKENS}
    for r, row in enumerate(g.cells):
        for c, t in enumerate(row):
            if t not in TOKENS:
                err.append(f"unknown token {t!r} at ({r},{c})")
                continue
            count[t] += 1
            if g.on_boundary(r, c) and t not in ("#", "DI", "DO"):
                err.append(f"boundary cell ({r},{c}) must be '#', 'DI' or 'DO', found {t!r}")
            if t in ("DI", "DO") and not g.on_boundary(r, c):
                err.append(f"dock {t} at ({r},{c}) is not on the outer wall")
            if t in ("DI", "DO", "S"):
                if not any(_walkable(g, r + dr, c + dc) for dr, dc in NEIGHBOURS):
                    what = "shelf bay" if t == "S" else f"dock {t}"
                    err.append(f"{what} at ({r},{c}) has no walkable neighbour")
    if err:
        return err
    for t, need in (("DI", 1), ("DO", 1), ("PK", 1), ("G", 1), ("R", 1), ("S", 1)):
        if count[t] < need:
            err.append(f"need at least {need} '{t}' cell(s), found {count[t]}")
    if count["H"] != 1:
        err.append(f"need exactly one 'H' (picker depot), found {count['H']}")
    if err:
        return err
    # connectivity: every walkable cell reachable from the depot
    walk = [(r, c) for r in range(g.rows) for c in range(g.cols) if g.cells[r][c] in WALKABLE]
    start = next(p for p in walk if g.cells[p[0]][p[1]] == "H")
    seen, stack = {start}, [start]
    while stack:
        r, c = stack.pop()
        for dr, dc in NEIGHBOURS:
            q = (r + dr, c + dc)
            if q not in seen and _walkable(g, *q):
                seen.add(q)
                stack.append(q)
    unreached = [p for p in walk if p not in seen]
    if unreached:
        err.append(f"{len(unreached)} walkable cell(s) not connected to the depot, e.g. {unreached[:3]}")
    if n_skus is not None and count["S"] * g.levels < n_skus:
        err.append(f"{count['S'] * g.levels} slots for {n_skus} SKUs: every SKU needs a slot")
    return err


def _walkable(g, r, c):
    return 0 <= r < g.rows and 0 <= c < g.cols and g.cells[r][c] in WALKABLE


# ----------------------------------------------------------------------------- graph
@dataclass
class Graph:
    adj: list = field(default_factory=list)          # adj[u] = [(v, length), ...]
    _cache: dict = field(default_factory=dict)

    def dist_from(self, s):
        if s not in self._cache:
            d = [float("inf")] * len(self.adj)
            d[s] = 0.0
            pq = [(0.0, s)]
            while pq:
                du, u = heapq.heappop(pq)
                if du > d[u]:
                    continue
                for v, w in self.adj[u]:
                    if du + w < d[v]:
                        d[v] = du + w
                        heapq.heappush(pq, (d[v], v))
            self._cache[s] = d
        return self._cache[s]

    def dist(self, a, b):
        return self.dist_from(a)[b]


def pick_tour(graph: Graph, home: int, stops, stations):
    """Nearest-neighbour picking tour: home -> stops -> nearest packing station -> home.

    Ties are broken by the smaller node id. The Java Router implements exactly the same rule,
    so both give the same length on the same layout (checked by the cross-check test).
    Returns (stop order, station index, total length in metres).
    """
    rest = sorted(set(stops))
    cur, order, length = home, [], 0.0
    while rest:
        d = graph.dist_from(cur)
        nxt = min(rest, key=lambda v: (d[v], v))
        length += d[nxt]
        order.append(nxt)
        rest.remove(nxt)
        cur = nxt
    d = graph.dist_from(cur)
    k = min(range(len(stations)), key=lambda i: (d[stations[i]], i))
    length += d[stations[k]]                      # two separate additions, as in the Java Router
    length += graph.dist(stations[k], home)
    return order, k, length


# ----------------------------------------------------------------------------- compile
def compile_layout(g: Grid, skus, slotting="abc", layout_id="layout", template="custom", params=None, seed=0, fixed=None):
    """skus: list of (sku_id, weight), any order. fixed: {sku: (r, c)} bay of every SKU for slotting 'asis'.
    Returns the layout dict (schema whsim.layout/1)."""
    errors = validate(g, len(skus))
    if errors:
        raise LayoutError("; ".join(errors))
    node_of, nodes = {}, []
    for r in range(g.rows):
        for c in range(g.cols):
            if g.cells[r][c] in WALKABLE:
                node_of[(r, c)] = len(nodes)
                nodes.append([r, c, *(round(v, 4) for v in g.xy(r, c))])
    edges, graph = [], Graph([[] for _ in nodes])
    for (r, c), u in node_of.items():
        for dr, dc, w in ((1, 0, g.cell_h), (0, 1, g.cell_w)):    # each undirected edge once
            v = node_of.get((r + dr, c + dc))
            if v is not None:
                edges.append([u, v, w])
                graph.adj[u].append((v, w))
                graph.adj[v].append((u, w))
    facilities, counters = [], {t: 0 for t in FACILITY_TYPES}
    for (r, c), u in node_of.items():
        t = g.cells[r][c]
        if t in counters:
            counters[t] += 1
            x, y = g.xy(r, c)
            facilities.append(dict(id=f"{t}{counters[t]}", type=t, r=r, c=c, x=round(x, 4), y=round(y, 4), node=u))
    home = next(f["node"] for f in facilities if f["type"] == "H")
    stations = [f["node"] for f in facilities if f["type"] == "PK"]
    # slots: one per (shelf bay, level); picked from the first walkable neighbour in N, S, W, E order
    slots = []
    for r in range(g.rows):
        for c in range(g.cols):
            if g.cells[r][c] != "S":
                continue
            acc = next(node_of[(r + dr, c + dc)] for dr, dc in NEIGHBOURS if (r + dr, c + dc) in node_of)
            for lv in range(1, g.levels + 1):
                slots.append(dict(id=f"S{r:02d}{c:02d}-{lv}", r=r, c=c, level=lv, node=acc, sku=None))
    assign_skus(slots, skus, slotting, graph, home, stations, seed, fixed)
    d_home = graph.dist_from(home)
    used = [s for s in slots if s["sku"]]
    return {
        "schema": SCHEMA, "id": layout_id, "template": template, "params": params or {},
        "slotting": slotting, "cell_w": g.cell_w, "cell_h": g.cell_h, "origin": list(g.origin),
        "rows": g.rows, "cols": g.cols, "levels": g.levels,
        "grid": g.to_text(), "nodes": nodes, "edges": edges, "facilities": facilities, "slots": slots,
        "stats": {
            "n_nodes": len(nodes), "n_edges": len(edges), "n_slots": len(slots), "n_skus": len(used),
            "floor_m2": round(g.rows * g.cols * g.cell_w * g.cell_h, 2),
            "mean_depot_to_used_slot_m": round(sum(d_home[s["node"]] for s in used) / len(used), 3),
        },
    }


SLOTTING = ("asis", "random", "class", "abc")
CLASS_SHARES = (0.2, 0.3, 0.5)         # class storage: A = fastest 20% of SKUs, B = next 30%, C = the rest


def slot_scores(graph: Graph, home: int, stations):
    """Distance cost of every node as a slot: depot -> slot -> nearest packing station (graph is undirected)."""
    dh = graph.dist_from(home)
    ds = [graph.dist_from(p) for p in stations]
    return [dh[v] + min(d[v] for d in ds) for v in range(len(dh))]


def assign_skus(slots, skus, slotting, graph, home, stations, seed=0, fixed=None):
    """Storage assignment, exactly one slot per SKU (SKUs ranked by pick frequency):
      asis    the real storage: each SKU in the bay it was really picked from most often (fixed);
              a bay takes more SKUs than `levels` if the data says so (extra slots are added there),
              SKUs with no known bay get a random free slot
      random  seeded random slot for every SKU (the dataset's 'random storage' strategy)
      class   slots ranked by distance cost and cut into zones A/B/C with the same sizes as the SKU
              classes (CLASS_SHARES); each SKU gets a random slot inside its class zone
      abc     dedicated by turnover: the most-picked SKU gets the cheapest slot, and so on
    """
    ranked = sorted(skus, key=lambda s: (-s[1], s[0]))
    order = list(range(len(slots)))
    rng = random.Random(seed)
    if slotting == "asis":
        if fixed is None:
            raise LayoutError("slotting 'asis' needs the real SKU -> bay assignment")
        free = {}
        for i, sl in enumerate(slots):
            free.setdefault((sl["r"], sl["c"]), []).append(i)
        rest = []
        for sku, _ in ranked:
            bay = fixed.get(sku)
            if bay is None or bay not in free:          # no known bay, or the bay was removed (new aisle)
                rest.append(sku)
                continue
            if free[bay]:
                slots[free[bay].pop(0)]["sku"] = sku
            else:                                       # the real bay holds more SKUs than the model's levels
                base = next(sl for sl in slots if (sl["r"], sl["c"]) == bay)
                lv = 1 + max(sl["level"] for sl in slots if (sl["r"], sl["c"]) == bay)
                slots.append(dict(base, id=f"S{bay[0]:02d}{bay[1]:02d}-{lv}", level=lv, sku=sku))
        empty = [i for idx in free.values() for i in idx]
        rng.shuffle(empty)
        if len(empty) < len(rest):
            raise LayoutError(f"{len(rest)} SKUs without a known bay but only {len(empty)} free slots")
        for sku, i in zip(rest, empty):
            slots[i]["sku"] = sku
        return
    if slotting in ("abc", "class"):
        cost = slot_scores(graph, home, stations)
        order.sort(key=lambda i: (cost[slots[i]["node"]], i))
        order = order[:len(ranked)]                  # the cheapest slots are the ones used
        if slotting == "class":
            n, start = len(ranked), 0
            for k, share in enumerate(CLASS_SHARES):
                end = n if k == len(CLASS_SHARES) - 1 else start + round(share * n)
                zone = order[start:end]
                rng.shuffle(zone)
                order[start:end] = zone
                start = end
    elif slotting == "random":
        rng.shuffle(order)
    else:
        raise LayoutError(f"unknown slotting {slotting!r} (use one of {SLOTTING})")
    for (sku, _), i in zip(ranked, order):
        slots[i]["sku"] = sku


def graph_of(layout: dict) -> Graph:
    g = Graph([[] for _ in layout["nodes"]])
    for a, b, w in layout["edges"]:
        g.adj[a].append((b, w))
        g.adj[b].append((a, w))
    return g


def save(layout: dict, path):
    with open(path, "w") as f:
        json.dump(layout, f, separators=(",", ":"))
