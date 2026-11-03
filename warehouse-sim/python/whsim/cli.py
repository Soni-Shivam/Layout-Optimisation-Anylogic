"""Writes every input file the AnyLogic model reads into model/WarehouseSim/data/.

    python3 -m whsim.cli all            # run config + workload (fitted input models) + layouts
    python3 -m whsim.cli config         # data/config/run_config.json
    python3 -m whsim.cli scenarios      # skus.csv + day files from the fitted input models (whsim.input_models)
    python3 -m whsim.cli layouts        # one layout JSON per design in data/config/designs.json (+ index.txt)
    python3 -m whsim.cli check FILE     # validate a hand-drawn grid file (one row of tokens per line)

Layouts are DESIGNS in coordinates (see whsim.design): depot position, extra cross aisles, packing
stations and slotting policy on the real footwear warehouse. Their file names are made from those values.
"""
from __future__ import annotations

import argparse
import json
import pathlib
import sys

from . import design, scenario
from .layout import Grid, LayoutError, save, validate

ROOT = pathlib.Path(__file__).resolve().parents[2]
DATA = ROOT / "model" / "WarehouseSim" / "data"
DESIGNS = DATA / "config" / "designs.json"

# Model time 0 = 06:00. Real orders are created 06:00-20:30 (data); carrier cut-offs are ASSUMED.
RUN_CONFIG = {
    "schema": "whsim.run/1",
    "horizon_s": 54000,                          # 21:00, end of the day; KPIs are written then
    "cutoffs_s": [25200, 43200, 52200],          # carrier departures 13:00, 18:00, 20:30 (assumed)
    "promise_lead_s": 3600,                      # an order is due at the first cut-off >= arrival + 1 h
    "resources": {"pickers": 7, "packers": 2, "receivers": 2, "putaway": 2},   # data: 6.6 operators active per day
    "walk_speed_mps": 1.0,                       # picker pushing a cart (assumed)
    "putaway_speed_mps": 1.2,
    "recv_buffer_per_cell": 25,                  # receipt lines one receiving cell holds
    "batching": {                                # real waves: ~4 orders, ~24 units per cart (data)
        "cart_units": 24, "max_orders": 0, "max_wait_s": 900, "tick_s": 10,
    },
    "times": {                                   # no timestamps in the data: ASSUMED, varied in the what-ifs
        "pick_per_line_s": {"dist": "lognormal", "mean": 12.0, "sd": 5.0},
        "pack_per_order_s": {"dist": "triangular", "min": 40.0, "mode": 60.0, "max": 120.0},
        "pack_per_unit_s": {"dist": "const", "value": 4.0},
        "receive_per_line_s": {"dist": "gamma", "shape": 4.0, "scale": 12.0},
        "putaway_handling_s": {"dist": "uniform", "min": 20.0, "max": 40.0},
    },
}

# designs written when designs.json does not exist yet: the as-is warehouse with each storage policy
DEFAULT_DESIGNS = [{**design.BASELINE, "slotting": s} for s in design.SLOTTING_POLICIES]


def write_scenarios():
    from . import input_models          # fitted on the real data (data_raw/mendeley)
    input_models.main()
    write_real_index()


def write_real_index():
    """data/scenarios/real_index.txt: the replayed historical days, for the AnyLogic parameter realDay."""
    days = sorted(p.name for p in (DATA / "scenarios").glob("real_*.csv"))
    (DATA / "scenarios" / "real_index.txt").write_text("\n".join(days) + "\n")
    return days


def read_designs():
    if DESIGNS.exists():
        return json.loads(DESIGNS.read_text())["designs"]
    return DEFAULT_DESIGNS


def write_designs(designs, note=""):
    DESIGNS.parent.mkdir(parents=True, exist_ok=True)
    DESIGNS.write_text(json.dumps({"note": note, "designs": designs}, indent=2) + "\n")


def write_layouts(designs=None):
    out = DATA / "layouts"
    out.mkdir(parents=True, exist_ok=True)
    for old in out.glob("*.json"):
        old.unlink()
    skus = [(s, w) for s, w, _ in scenario.read_skus(DATA / "skus.csv")]
    names = []
    for d in designs or read_designs():
        lay = design.apply_design(d, skus)
        save(lay, out / f"{lay['id']}.json")
        names.append(f"{lay['id']}.json")
        st = lay["stats"]
        print(f"{lay['id']:40s} nodes {st['n_nodes']:5d}  slots {st['n_slots']:5d}  "
              f"mean depot->slot {st['mean_depot_to_used_slot_m']:6.1f} m")
    (out / "index.txt").write_text("\n".join(names) + "\n")
    return names


def write_run_config():
    (DATA / "config").mkdir(parents=True, exist_ok=True)
    (DATA / "config" / "run_config.json").write_text(json.dumps(RUN_CONFIG, indent=2) + "\n")


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("cmd", choices=["all", "layouts", "scenarios", "config", "check"])
    ap.add_argument("file", nargs="?")
    ap.add_argument("--cell-w", type=float, default=1.5, help="check: cell width in metres")
    ap.add_argument("--cell-h", type=float, default=None, help="check: cell height in metres (default = width)")
    ap.add_argument("--levels", type=int, default=2, help="check: pick slots per shelf bay")
    a = ap.parse_args(argv)
    if a.cmd in ("all", "config"):
        write_run_config()
    if a.cmd in ("all", "scenarios"):
        write_scenarios()
    if a.cmd in ("all", "layouts"):
        write_layouts()
        write_real_index()
    if a.cmd == "check":
        rows = [ln for ln in pathlib.Path(a.file).read_text().splitlines() if ln.strip()]
        sku_file = DATA / "skus.csv"
        n_skus = len(scenario.read_skus(sku_file)) if sku_file.exists() else None
        errs = validate(Grid.parse(rows, a.cell_w, a.levels, a.cell_h), n_skus)
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
