"""Grid layout -> validated, compiled layout JSON (the file AnyLogic reads).

A layout is a rectangular grid of cell tokens:

    #   wall / column (not walkable)          .   unused floor (not walkable)
    A   aisle (walkable)                      S   shelf bay: `levels` pick slots, picked from a walkable neighbour
    DI  inbound dock (on the outer wall)      DO  outbound dock (on the outer wall)
    R   receiving buffer cell                 PK  packing station (one station per cell)
    G   outbound staging cell                 H   picker depot (exactly one)

Every token except '#', '.' and 'S' is walkable and becomes a node of the aisle graph. Edges join
walkable 4-neighbours and have length cell_m. All geometry is decided here; AnyLogic only builds
what the compiled file lists.
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
    cell_m: float = 1.5
    levels: int = 2                  # pick slots per shelf bay

    @property
    def rows(self):
        return len(self.cells)

    @property
    def cols(self):
        return len(self.cells[0]) if self.cells else 0

    @staticmethod
    def parse(text_rows, cell_m=1.5, levels=2):
        """text_rows: list of strings with space-separated tokens."""
        return Grid([r.split() for r in text_rows], cell_m, levels)

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
    if g.cell_m <= 0 or g.levels < 1:
        err.append("cell_m must be > 0 and levels >= 1")
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
    length += d[stations[k]] + graph.dist(stations[k], home)
    return order, k, length


# ----------------------------------------------------------------------------- compile
def compile_layout(g: Grid, skus, slotting="abc", layout_id="layout", template="custom", params=None, seed=0):
    """skus: list of (sku_id, weight), any order. Returns the layout dict (schema whsim.layout/1)."""
    errors = validate(g, len(skus))
    if errors:
        raise LayoutError("; ".join(errors))
    m = g.cell_m
    node_of, nodes = {}, []
    for r in range(g.rows):
        for c in range(g.cols):
            if g.cells[r][c] in WALKABLE:
                node_of[(r, c)] = len(nodes)
                nodes.append([r, c, (c + 0.5) * m, (r + 0.5) * m])
    edges, graph = [], Graph([[] for _ in nodes])
    for (r, c), u in node_of.items():
        for dr, dc in ((1, 0), (0, 1)):            # each undirected edge once
            v = node_of.get((r + dr, c + dc))
            if v is not None:
                edges.append([u, v, m])
                graph.adj[u].append((v, m))
                graph.adj[v].append((u, m))
    facilities, counters = [], {t: 0 for t in FACILITY_TYPES}
    for (r, c), u in node_of.items():
        t = g.cells[r][c]
        if t in counters:
            counters[t] += 1
            facilities.append(dict(id=f"{t}{counters[t]}", type=t, r=r, c=c, x=(c + 0.5) * m, y=(r + 0.5) * m, node=u))
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
    assign_skus(slots, skus, slotting, graph, home, stations, seed)
    d_home = graph.dist_from(home)
    used = [s for s in slots if s["sku"]]
    return {
        "schema": SCHEMA, "id": layout_id, "template": template, "params": params or {},
        "slotting": slotting, "cell_m": m, "rows": g.rows, "cols": g.cols, "levels": g.levels,
        "grid": g.to_text(), "nodes": nodes, "edges": edges, "facilities": facilities, "slots": slots,
        "stats": {
            "n_nodes": len(nodes), "n_edges": len(edges), "n_slots": len(slots), "n_skus": len(used),
            "floor_m2": g.rows * g.cols * m * m,
            "mean_depot_to_used_slot_m": round(sum(d_home[s["node"]] for s in used) / len(used), 3),
        },
    }


def slot_score(graph: Graph, home: int, stations, node: int):
    """Distance cost of a slot for ABC slotting: depot -> slot -> nearest packing station."""
    d = graph.dist_from(node)
    return d[home] + min(d[p] for p in stations)


def assign_skus(slots, skus, slotting, graph, home, stations, seed=0):
    """abc: most-picked SKU -> cheapest slot. random: seeded shuffle. Exactly one slot per SKU."""
    ranked = sorted(skus, key=lambda s: (-s[1], s[0]))
    order = list(range(len(slots)))
    if slotting == "abc":
        order.sort(key=lambda i: (slot_score(graph, home, stations, slots[i]["node"]), i))
    elif slotting == "random":
        random.Random(seed).shuffle(order)
    else:
        raise LayoutError(f"unknown slotting {slotting!r} (use 'abc' or 'random')")
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
