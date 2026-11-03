"""Figures and reports/optimization.md from the optimizer's results (results/opt/).

    python3 -m whsim.opt_report
"""
from __future__ import annotations

import csv
import json
import math

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

from . import design  # noqa: E402
from .optimize import FIG, OUT, P95_MAX_S, ON_TIME_MIN  # noqa: E402
from .cli import ROOT  # noqa: E402

REPORT = ROOT / "reports" / "optimization.md"


def rd(path):
    with open(path) as f:
        return list(csv.DictReader(f))


def outline(ax):
    """Racks of the real building in grey, for map plots."""
    for x, y, r, c in design.read_bays():
        ax.add_patch(plt.Rectangle((x - design.CELL_W / 2, y - design.CELL_H / 2), design.CELL_W, design.CELL_H,
                                   color="#BDBDBD", lw=0))
    ax.set_aspect("equal")
    ax.set_xlabel("x (m)")
    ax.set_ylabel("y (m)")


def fig_depot_scan(summary):
    rows = rd(OUT / "depot_scan.csv")
    fig, axes = plt.subplots(1, 2, figsize=(9, 8.5), sharey=True)
    for ax, s in zip(axes, ("asis", "abc")):
        pts = [(float(r["x"]), float(r["y"]), float(r["mean_tour_m"])) for r in rows if r["slotting"] == s]
        outline(ax)
        sc = ax.scatter([p[0] for p in pts], [p[1] for p in pts], c=[p[2] for p in pts], cmap="viridis_r", s=22,
                        edgecolors="none")
        b = min(pts, key=lambda p: p[2])
        ax.plot(*design.BASELINE["depot"], marker="*", ms=16, color="#C62828", mec="white", label="as-is depot")
        ax.plot(b[0], b[1], marker="P", ms=13, color="#1565C0", mec="white", label=f"best: ({b[0]:.1f}, {b[1]:.1f})")
        ax.set_title(f"{s} storage: mean tour per real wave (m)")
        fig.colorbar(sc, ax=ax, shrink=0.6)
        ax.legend(loc="upper right", fontsize=8)
    fig.suptitle("Where should the pick-up / drop-off point be? (9.8k historical waves, static tours)")
    fig.tight_layout()
    fig.savefig(FIG / "opt_depot_scan.png", dpi=150)
    plt.close(fig)


def fig_ga():
    h = rd(OUT / "ga_history.csv")
    fig, ax = plt.subplots(figsize=(6, 3.5))
    ax.plot([int(r["generation"]) for r in h], [float(r["best_m"]) for r in h], marker="o", label="best")
    ax.plot([int(r["generation"]) for r in h], [float(r["mean_m"]) for r in h], marker=".", label="population mean")
    ax.set_xlabel("generation")
    ax.set_ylabel("mean tour per real wave (m)")
    ax.set_title("Genetic algorithm convergence")
    ax.legend()
    fig.tight_layout()
    fig.savefig(FIG / "opt_ga.png", dpi=150)
    plt.close(fig)


def fig_rank(summary):
    asis = summary["asis"]["asis"]
    kp = [("pick_m_per_order", "walk per order (m)"), ("fulfil_mean_s", "mean fulfilment (s)"),
          ("fulfil_p95_s", "p95 fulfilment (s)")]
    designs = list(summary["kpi_means"]["pick_m_per_order"].keys())
    fig, axes = plt.subplots(1, 3, figsize=(13, 4.2))
    for ax, (k, lab) in zip(axes, kp):
        d = summary["paired_vs_asis"][k]
        names = [x for x in designs if x != asis]
        ms = [d[x][0] for x in names]
        hs = [d[x][1] for x in names]
        cols = ["#2E7D32" if m + h < 0 else "#C62828" if m - h > 0 else "#9E9E9E" for m, h in zip(ms, hs)]
        ax.barh(range(len(names)), ms, xerr=hs, color=cols, capsize=3)
        ax.axvline(0, color="black", lw=0.8)
        ax.set_yticks(range(len(names)))
        ax.set_yticklabels(names if ax is axes[0] else [""] * len(names), fontsize=7)
        ax.set_title(f"{lab}\nchange vs as-is (Bonferroni 95% CI)", fontsize=9)
    fig.tight_layout()
    fig.savefig(FIG / "opt_rank.png", dpi=150)
    plt.close(fig)


def fig_operate(summary):
    rows = rd(OUT / "operate.csv")
    carts = sorted({int(r["cart_cfg"]) for r in rows})
    pick = sorted({int(r["pickers_cfg"]) for r in rows})
    fig, axes = plt.subplots(1, 2, figsize=(11, 4))
    for cu in carts:
        f95, ot = [], []
        for k in pick:
            rs = [r for r in rows if int(r["pickers_cfg"]) == k and int(r["cart_cfg"]) == cu]
            f95.append(sum(float(r["fulfil_p95_s"]) for r in rs) / len(rs) / 60)
            ot.append(sum(float(r["on_time_pct"]) for r in rs) / len(rs))
        lab = "single-order" if cu == 0 else f"cart {cu} units"
        axes[0].plot(pick, f95, marker="o", label=lab)
        axes[1].plot(pick, ot, marker="o", label=lab)
    axes[0].axhline(P95_MAX_S / 60, color="#C62828", ls="--", label="target")
    axes[1].axhline(ON_TIME_MIN, color="#C62828", ls="--", label="target")
    axes[0].set_ylabel("p95 fulfilment (min)")
    axes[1].set_ylabel("on time (%)")
    for ax in axes:
        ax.set_xlabel("pickers")
        ax.legend(fontsize=8)
    axes[0].set_yscale("log")
    fig.suptitle("Staffing x wave batching on the recommended layout (mean of 10 days)")
    fig.tight_layout()
    fig.savefig(FIG / "opt_operate.png", dpi=150)
    plt.close(fig)


def fmt(x, nd=1):
    return "-" if x is None or (isinstance(x, float) and math.isnan(x)) else f"{x:.{nd}f}"


def write_md(summary):
    asis = summary["asis"]["asis"]
    rec = summary["recommended"]
    m = summary["kpi_means"]
    pd = summary["paired_vs_asis"]
    lines = ["# Simulation-based optimisation", "",
             "All numbers come from `python3 -m whsim.optimize` (results/opt/). Designs are named by their coordinates: "
             "`D<x>_<y>` = depot position in metres (dataset frame), `P` = packing stations, `X` = extra cross aisles "
             "(x in metres, `none` = as built), last part = storage policy.", "",
             "## Stage 1 - screening on the real historical waves", "",
             f"Static objective: mean tour length of the 9.8k historical picking waves (real cart contents) on each layout. "
             f"The genetic algorithm evaluated {summary['ga_evaluated']} distinct designs; best: `{summary['ga_best']}`.", "",
             "| as-is layout, storage policy | mean tour per wave (m) |", "|---|---|"]
    for s, did in summary["asis"].items():
        lines.append(f"| {did} | {fmt(summary['static_asis'][did])} |")
    lines += ["", "![depot scan](figures/opt_depot_scan.png)", "", "![GA](figures/opt_ga.png)", "",
              "## Stage 2 - DES ranking (10 synthetic days, common random numbers)", "",
              "| design | walk / order (m) | tour (s) | fulfil mean (s) | fulfil p95 (s) | on time (%) | picker util |",
              "|---|---|---|---|---|---|---|"]
    for did in m["pick_m_per_order"]:
        lines.append(f"| {did}{' (as-is)' if did == asis else ' **(recommended)**' if did == rec else ''} | "
                     f"{fmt(m['pick_m_per_order'][did])} | {fmt(m['tour_s_mean'][did], 0)} | {fmt(m['fulfil_mean_s'][did], 0)} | "
                     f"{fmt(m['fulfil_p95_s'][did], 0)} | {fmt(m['on_time_pct'][did])} | {fmt(m['util_pick'][did], 2)} |")
    lines += ["", "Paired difference vs the as-is layout (same days, same service-time streams), Bonferroni 95% CI:", "",
              "| design | walk / order (m) | fulfil mean (s) |", "|---|---|---|"]
    for did, (d, h) in pd["pick_m_per_order"].items():
        f, fh = pd["fulfil_mean_s"][did]
        lines.append(f"| {did} | {d:+.1f} ± {h:.1f} | {f:+.0f} ± {fh:.0f} |")
    lines += ["", "![ranking](figures/opt_rank.png)", "", "## Stage 3 - pickers and wave batching", ""]
    oc = summary["operate_choice"]
    if oc:
        k, walk, cu, ot, p95 = oc
        lines.append(f"Fewest pickers meeting on-time >= {ON_TIME_MIN:.0f}% and p95 fulfilment <= {P95_MAX_S / 60:.0f} min, "
                     f"then least walking: **{k} pickers** with **{'single-order picking' if cu == 0 else f'{cu}-unit carts'}** "
                     f"(on time {ot:.1f}%, p95 {p95 / 60:.0f} min, {walk / 1000:.1f} km walked per day).")
    else:
        lines.append("No picker count in the grid met both service targets.")
    lines += ["", "![operate](figures/opt_operate.png)", "", "## Stage 4 - robustness to the assumed pick time", "",
              "| pick time x | as-is fulfil mean (s) | recommended fulfil mean (s) | difference (Bonferroni 95% CI) |",
              "|---|---|---|---|"]
    for s, v in summary["robust"].items():
        f = v["fulfil_mean_s"]
        d = v["paired_fulfil"].get(rec, [math.nan, math.nan])
        lines.append(f"| {s} | {fmt(f.get(asis), 0)} | {fmt(f.get(rec), 0)} | {d[0]:+.0f} ± {d[1]:.0f} |")
    REPORT.write_text("\n".join(lines) + "\n")


def main():
    summary = json.loads((OUT / "summary.json").read_text())
    fig_depot_scan(summary)
    fig_ga()
    fig_rank(summary)
    fig_operate(summary)
    write_md(summary)
    print(f"wrote {REPORT}")


if __name__ == "__main__":
    main()
