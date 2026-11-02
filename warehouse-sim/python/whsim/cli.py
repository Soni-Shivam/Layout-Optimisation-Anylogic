"""Writes every input file the AnyLogic model reads into model/WarehouseSim/data/.

    python3 -m whsim.cli all            # skus + scenarios + layouts + run config
    python3 -m whsim.cli layouts        # only the layout candidates (uses data/skus.csv)
    python3 -m whsim.cli scenarios      # only skus.csv and the day files (placeholder generator)
    python3 -m whsim.cli check FILE     # validate a hand-drawn grid file (one row of tokens per line)
"""
from __future__ import annotations

import argparse
import json
import pathlib
import sys

from . import scenario, templates
from .layout import Grid, LayoutError, compile_layout, graph_of, pick_tour, save, validate

ROOT = pathlib.Path(__file__).resolve().parents[2]
DATA = ROOT / "model" / "WarehouseSim" / "data"

RUN_CONFIG = {
    "schema": "whsim.run/1",
    "horizon_s": 57900,                          # end of the day; KPIs are written then
    "cutoffs_s": [14400, 28800, 43200, 57600],   # carrier departures (4 h, 8 h, 12 h, 16 h)
    "promise_lead_s": 1800,                      # an order is due at the first cut-off >= arrival + lead
    "resources": {"pickers": 6, "packers": 3, "receivers": 2, "putaway": 2},
    "walk_speed_mps": 1.0,                       # picker with cart
    "putaway_speed_mps": 1.2,
    "recv_buffer_per_cell": 25,                  # receipt lines one receiving cell holds
    "times": {                                   # replace with the fitted input models
        "pick_per_line_s": {"dist": "lognormal", "mean": 12.0, "sd": 5.0},
        "pack_per_order_s": {"dist": "triangular", "min": 40.0, "mode": 60.0, "max": 120.0},
        "pack_per_unit_s": {"dist": "const", "value": 4.0},
        "receive_per_line_s": {"dist": "gamma", "shape": 4.0, "scale": 12.0},
        "putaway_handling_s": {"dist": "uniform", "min": 20.0, "max": 40.0},
    },
}


def write_scenarios(n_days=5, n_skus=400):
    (DATA / "scenarios").mkdir(parents=True, exist_ok=True)
    skus = scenario.make_skus(n_skus)
    scenario.write_skus(skus, DATA / "skus.csv")
    for seed in range(1, n_days + 1):
        rows = scenario.make_day(skus, seed)
        scenario.write_day(rows, DATA / "scenarios" / f"day_{seed}.csv")
        n_o = len({r[2] for r in rows if r[1] == "ORDER"})
        n_t = len({r[2] for r in rows if r[1] == "RECEIPT"})
        print(f"day_{seed}.csv: {n_o} orders, {sum(r[1] == 'ORDER' for r in rows)} order lines, "
              f"{n_t} trucks, {sum(r[1] == 'RECEIPT' for r in rows)} receipt lines")


def write_layouts(candidates=templates.CANDIDATES):
    out = DATA / "layouts"
    out.mkdir(parents=True, exist_ok=True)
    skus = [(s, w) for s, w, _ in scenario.read_skus(DATA / "skus.csv")]
    names = []
    for lid, p in candidates.items():
        p = dict(p)
        slotting = p.pop("slotting")
        g = templates.parallel_aisle(**p)
        lay = compile_layout(g, skus, slotting=slotting, layout_id=lid, template="parallel_aisle",
                             params={**p, "slotting": slotting})
        save(lay, out / f"{lid}.json")
        names.append(f"{lid}.json")
        st = lay["stats"]
        print(f"{lid:28s} nodes {st['n_nodes']:4d}  slots {st['n_slots']:4d}  "
              f"mean depot->slot {st['mean_depot_to_used_slot_m']:6.1f} m  "
              f"static pick m/order {static_pick_m(lay):6.1f}")
    (out / "index.txt").write_text("\n".join(names) + "\n")


def static_pick_m(layout, day=DATA / "scenarios" / "day_1.csv"):
    """Mean tour length per order on one day's orders (no simulation): the screening score."""
    g = graph_of(layout)
    node_of_sku = {}
    for s in layout["slots"]:
        if s["sku"] and s["sku"] not in node_of_sku:
            node_of_sku[s["sku"]] = s["node"]
    home = next(f["node"] for f in layout["facilities"] if f["type"] == "H")
    stations = [f["node"] for f in layout["facilities"] if f["type"] == "PK"]
    orders = {}
    for t, typ, oid, sku, q in scenario.read_day(day):
        if typ == "ORDER":
            orders.setdefault(oid, []).append(node_of_sku[sku])
    tot = sum(pick_tour(g, home, stops, stations)[2] for stops in orders.values())
    return tot / max(1, len(orders))


def write_run_config():
    (DATA / "config").mkdir(parents=True, exist_ok=True)
    (DATA / "config" / "run_config.json").write_text(json.dumps(RUN_CONFIG, indent=2) + "\n")


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("cmd", choices=["all", "layouts", "scenarios", "config", "check"])
    ap.add_argument("file", nargs="?")
    ap.add_argument("--days", type=int, default=5)
    ap.add_argument("--skus", type=int, default=400)
    ap.add_argument("--cell-m", type=float, default=1.5, help="check: cell size in metres")
    ap.add_argument("--levels", type=int, default=2, help="check: pick slots per shelf bay")
    a = ap.parse_args(argv)
    if a.cmd in ("all", "scenarios"):
        write_scenarios(a.days, a.skus)
    if a.cmd in ("all", "config"):
        write_run_config()
    if a.cmd in ("all", "layouts"):
        write_layouts()
    if a.cmd == "check":
        rows = [ln for ln in pathlib.Path(a.file).read_text().splitlines() if ln.strip()]
        sku_file = DATA / "skus.csv"
        n_skus = len(scenario.read_skus(sku_file)) if sku_file.exists() else None
        errs = validate(Grid.parse(rows, a.cell_m, a.levels), n_skus)
        if n_skus is None:
            print(f"(no {sku_file}: slot count not checked against the SKUs)")
        print("\n".join(errs) if errs else "OK")
        return 1 if errs else 0
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except LayoutError as e:
        sys.exit(f"invalid layout: {e}")
