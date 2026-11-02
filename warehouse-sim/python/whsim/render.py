"""PNG preview of every candidate layout (same colours as the AnyLogic drawing), with the SKU
popularity of each shelf bay shaded, so candidates can be checked before running AnyLogic.

    python3 -m whsim.render          -> build/previews/<layout id>.png and build/previews/all.png
"""
from __future__ import annotations

import json

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
from matplotlib.patches import Rectangle  # noqa: E402

from . import scenario  # noqa: E402
from .cli import DATA, ROOT  # noqa: E402

COLORS = {"#": "#37474F", ".": "#FFFFFF", "A": "#ECEFF1", "S": "#A1887F", "DI": "#2E7D32", "DO": "#1565C0",
          "R": "#FFE082", "PK": "#FF9800", "G": "#B39DDB", "H": "#00897B"}


def draw(ax, lay, weight):
    m = lay["cell_m"]
    heat = {}
    for s in lay["slots"]:
        if s["sku"]:
            heat[(s["r"], s["c"])] = heat.get((s["r"], s["c"]), 0) + weight.get(s["sku"], 0)
    hmax = max(heat.values()) if heat else 1
    for r, row in enumerate(lay["grid"]):
        for c, t in enumerate(row.split()):
            col = COLORS[t]
            ax.add_patch(Rectangle((c * m, r * m), m, m, facecolor=col, edgecolor="white", linewidth=0.3))
            if t == "S" and (r, c) in heat:     # darker = more picks
                ax.add_patch(Rectangle((c * m, r * m), m, m, facecolor="#4E342E", alpha=0.8 * (heat[(r, c)] / hmax) ** 0.5,
                                       linewidth=0))
    for f in lay["facilities"]:
        if f["type"] in ("DI", "DO", "PK", "H"):
            ax.text(f["x"], f["y"], f["id"], ha="center", va="center", fontsize=5, color="white", weight="bold")
    ax.set_xlim(0, lay["cols"] * m)
    ax.set_ylim(lay["rows"] * m, 0)
    ax.set_aspect("equal")
    ax.set_xticks([])
    ax.set_yticks([])
    st = lay["stats"]
    ax.set_title(f"{lay['id']}\n{st['n_slots']} slots, mean depot->slot {st['mean_depot_to_used_slot_m']} m", fontsize=7)


def main():
    out = ROOT / "build" / "previews"
    out.mkdir(parents=True, exist_ok=True)
    weight = {s: w for s, w, _ in scenario.read_skus(DATA / "skus.csv")}
    names = (DATA / "layouts" / "index.txt").read_text().split()
    lays = [json.loads((DATA / "layouts" / n).read_text()) for n in names]
    for lay in lays:
        fig, ax = plt.subplots(figsize=(6, 5))
        draw(ax, lay, weight)
        fig.savefig(out / f"{lay['id']}.png", dpi=160, bbox_inches="tight")
        plt.close(fig)
    cols = 3
    rows = (len(lays) + cols - 1) // cols
    fig, axes = plt.subplots(rows, cols, figsize=(4 * cols, 3.4 * rows))
    for ax in axes.flat[len(lays):]:
        ax.axis("off")
    for ax, lay in zip(axes.flat, lays):
        draw(ax, lay, weight)
    fig.suptitle("Candidate layouts (shelf shading = pick frequency of the SKUs stored there)", fontsize=10)
    fig.savefig(out / "all.png", dpi=160, bbox_inches="tight")
    print(f"previews in {out}")


if __name__ == "__main__":
    main()
