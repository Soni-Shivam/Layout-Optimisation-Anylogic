"""Test fixtures for the Java tests (written to build/fixtures/):

  tiny_layout.json        the 7 x 7 hand-checkable layout from tests/test_layout.py
  crosscheck_<id>.csv     Python's picking-tour length and station for every order of day_1 on every
                          candidate layout; the Java Router must reproduce them exactly
"""
from __future__ import annotations

import csv
import json
import pathlib

from . import scenario
from .cli import DATA, ROOT
from .layout import Grid, compile_layout, graph_of, pick_tour

TINY = [
    "# # # # # # #",
    "# A A A A A #",
    "# A S A S A #",
    "# A S A S A #",
    "# A A A A A #",
    "DI R A H PK G DO",
    "# # # # # # #",
]


def main():
    out = ROOT / "build" / "fixtures"
    out.mkdir(parents=True, exist_ok=True)
    lay = compile_layout(Grid.parse(TINY, cell_m=2.0, levels=1), [("X", 3.0), ("Y", 2.0), ("Z", 1.0)], "abc", "tiny")
    (out / "tiny_layout.json").write_text(json.dumps(lay))
    orders = {}
    for t, typ, oid, sku, q in scenario.read_day(DATA / "scenarios" / "day_1.csv"):
        if typ == "ORDER":
            orders.setdefault(oid, []).append(sku)
    for name in (DATA / "layouts" / "index.txt").read_text().split():
        lay = json.loads((DATA / "layouts" / name).read_text())
        g = graph_of(lay)
        node_of_sku = {}
        for s in lay["slots"]:
            if s["sku"] and s["sku"] not in node_of_sku:
                node_of_sku[s["sku"]] = s["node"]
        home = next(f["node"] for f in lay["facilities"] if f["type"] == "H")
        stations = [f["node"] for f in lay["facilities"] if f["type"] == "PK"]
        with open(out / f"crosscheck_{lay['id']}.csv", "w", newline="") as f:
            wr = csv.writer(f)
            wr.writerow(["order", "length", "station", "stops"])
            for oid, skus in orders.items():
                order, k, length = pick_tour(g, home, [node_of_sku[s] for s in skus], stations)
                wr.writerow([oid, repr(length), k, " ".join(map(str, order))])
    print(f"fixtures written to {out}")


if __name__ == "__main__":
    main()
