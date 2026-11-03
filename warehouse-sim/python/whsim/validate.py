"""Validation of the as-is layout model against the real picks.

Picking_Wave.csv says, for every historical wave, the storage LOCATION each unit was really picked from.
We route each wave over those real locations (same nearest-neighbour tour, same aisle graph, as-is depot)
and compare the tour lengths with the model's tours for the same waves under the modelled storage
policies. If the model's 'random' storage matches the real tours, the as-is baseline is credible.

    python3 -m whsim.validate        -> results/validation_tours.csv, reports/validation.md, reports/figures/val_*.png
"""
from __future__ import annotations

import csv
import json
import statistics

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

from . import design  # noqa: E402
from .cli import DATA, ROOT  # noqa: E402
from .layout import graph_of, pick_tour  # noqa: E402

RAW = design.RAW
OUT_CSV = ROOT / "results" / "validation_tours.csv"
REPORT = ROOT / "reports" / "validation.md"
FIG = ROOT / "reports" / "figures"


def real_wave_nodes(layout):
    """wave -> access nodes of the locations its units were really picked from (locations we can place)."""
    loc_xy = {}
    with open(RAW / "Storage_Location.csv", encoding="utf-8-sig") as f:
        for r in csv.DictReader(f):
            loc_xy[r["originalLocation"].strip()] = (int(r["x"]) / 10, int(r["y"]) / 10)
    access = {(s["r"], s["c"]): s["node"] for s in layout["slots"]}
    waves, units, placed = {}, 0, 0
    with open(RAW / "Picking_Wave.csv", encoding="utf-8-sig") as f:
        for r in csv.DictReader(f, delimiter=";"):
            r = {k.strip(): v for k, v in r.items()}
            units += 1
            xy = loc_xy.get(r["locations"].strip())
            if xy is None:
                continue
            cell = (design.row_of(xy[1]), design.col_of(xy[0]))
            if cell not in access:          # overhead bays above the centre aisle
                continue
            placed += 1
            waves.setdefault(r["waveNumber"].strip(), set()).add(access[cell])
    return waves, units, placed


def main():
    lays = {p.stem: json.loads(p.read_text()) for p in (DATA / "layouts").glob("*.json")}
    asis = next(l for l in lays.values() if l["id"] == design.design_id(design.BASELINE))
    g = graph_of(asis)
    home = next(f["node"] for f in asis["facilities"] if f["type"] == "H")
    stations = [f["node"] for f in asis["facilities"] if f["type"] == "PK"]
    waves, units, placed = real_wave_nodes(asis)
    real = {w: pick_tour(g, home, list(nodes), stations)[2] for w, nodes in waves.items()}
    # model tours of the same waves (same SKU lists) for each storage policy at the as-is depot
    model = {}
    with open(ROOT / "data" / "real" / "waves.csv") as f:
        wave_skus = {r["wave"]: r["skus"].split() for r in csv.DictReader(f)}
    for pol in design.SLOTTING_POLICIES:
        lay = lays.get(design.design_id({**design.BASELINE, "slotting": pol}))
        if lay is None:
            continue
        gg = graph_of(lay)
        node = {}
        for s in lay["slots"]:
            if s["sku"] and s["sku"] not in node:
                node[s["sku"]] = s["node"]
        hh = next(f["node"] for f in lay["facilities"] if f["type"] == "H")
        ss = [f["node"] for f in lay["facilities"] if f["type"] == "PK"]
        model[pol] = {w: pick_tour(gg, hh, [node[k] for k in skus], ss)[2] for w, skus in wave_skus.items() if w in real}
    common = sorted(set(real) & set.intersection(*(set(v) for v in model.values())))
    OUT_CSV.parent.mkdir(parents=True, exist_ok=True)
    with open(OUT_CSV, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(["wave", "real_m", *[f"model_{p}_m" for p in model]])
        for wv in common:
            w.writerow([wv, f"{real[wv]:.2f}", *[f"{model[p][wv]:.2f}" for p in model]])
    rv = [real[w] for w in common]
    fig, ax = plt.subplots(figsize=(7, 4))
    bins = range(0, 1200, 25)
    ax.hist(rv, bins=bins, histtype="step", lw=2, color="black", label=f"real picks (mean {statistics.mean(rv):.0f} m)")
    for p, col in zip(model, ("#C62828", "#F9A825", "#2E7D32")):
        mv = [model[p][w] for w in common]
        ax.hist(mv, bins=bins, histtype="step", lw=1.5, color=col, label=f"model, {p} storage (mean {statistics.mean(mv):.0f} m)")
    ax.set_xlabel("tour length per historical wave (m)")
    ax.set_ylabel("waves")
    ax.set_title("Validation: real pick locations vs modelled storage, same waves, as-is layout")
    ax.legend(fontsize=8)
    fig.tight_layout()
    FIG.mkdir(parents=True, exist_ok=True)
    fig.savefig(FIG / "val_tours.png", dpi=150)
    plt.close(fig)
    lines = ["# Validation of the as-is model against the real picks", "",
             f"Units in Picking_Wave.csv: {units:,}; placed on a modelled bay: {placed:,} ({100 * placed / units:.1f}%; "
             "the rest are at locations without coordinates, e.g. 'RC-..', or on the overhead bays). "
             f"Waves compared: {len(common):,}.", "",
             "| tours of the same historical waves | mean (m) | median (m) | p95 (m) |", "|---|---|---|---|"]
    def row(name, v):
        v = sorted(v)
        return f"| {name} | {statistics.mean(v):.1f} | {statistics.median(v):.1f} | {v[int(0.95 * (len(v) - 1))]:.1f} |"
    lines.append(row("real pick locations", rv))
    for p in model:
        lines.append(row(f"model, {p} storage", [model[p][w] for w in common]))
    lines += ["", "![validation](figures/val_tours.png)", ""]
    REPORT.write_text("\n".join(lines) + "\n")
    print("\n".join(lines))


if __name__ == "__main__":
    main()
