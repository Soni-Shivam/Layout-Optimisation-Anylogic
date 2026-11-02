"""PLACEHOLDER workload generator: writes the two files the model reads.

The fitted input models (being built separately) replace this module. They only have to write the
same two files:

  skus.csv           sku,weight,init_qty          weight = relative pick frequency (used for slotting)
  day_<seed>.csv     t_s,type,id,sku,qty          one row per order line (type ORDER, id = order id) or
                                                  per receipt line (type RECEIPT, id = truck id).
                                                  Rows sorted by t_s; all lines of one order share t_s.

Assumed (not fitted) processes used here:
  orders     non-homogeneous Poisson, piecewise-constant hourly rate (thinning)
  lines      Geometric on {1, 2, ...} with P(stop) = 1 - p_line, at most max_lines distinct SKUs,
             drawn by weight without replacement
  qty/line   Geometric on {1, 2, ...} with P(stop) = 1 - p_qty
  SKU mix    Zipf weights 1 / rank^zipf_s
  inbound    a truck every truck_every_s; it brings each SKU whose projected stock (opening stock +
             receipts - this day's demand up to the next truck) would drop below 0.5 x daily demand,
             topped up to 1.5 x daily demand
"""
from __future__ import annotations

import csv
import math

import numpy as np

# orders per hour by hour of the day (hour 0 = model time 0)
DEFAULT_PROFILE = [60, 80, 110, 130, 120, 110, 100, 120, 140, 130, 100, 80, 60, 40]
P_LINE, P_QTY, MAX_LINES = 0.55, 0.3, 8


def units_per_order(p_line=P_LINE, p_qty=P_QTY):
    """Approximate mean units per order (mean lines x mean quantity, ignoring the max_lines cap)."""
    return 1.0 / (1 - p_line) / (1 - p_qty)


def make_skus(n_skus=400, zipf_s=0.9, cover_days=0.6, profile=DEFAULT_PROFILE):
    """SKU master: id, weight, opening stock = cover_days x expected daily demand (at least 2)."""
    rank = np.arange(1, n_skus + 1)
    w = 1.0 / rank ** zipf_s
    w = w / w.sum()
    daily_units = sum(profile) * units_per_order()
    return [(f"SKU{i + 1:04d}", float(w[i]), max(2, int(math.ceil(cover_days * w[i] * daily_units))))
            for i in range(n_skus)]


def make_day(skus, seed, profile=DEFAULT_PROFILE, p_line=P_LINE, max_lines=MAX_LINES, p_qty=P_QTY,
             truck_every_s=7200, first_truck_s=3600, demand_scale=1.0):
    rng = np.random.default_rng(seed)
    ids = [s[0] for s in skus]
    w = np.array([s[1] for s in skus])
    w = w / w.sum()
    rows = []
    # --- orders: thinning of a Poisson process at the peak rate
    lam = [r * demand_scale / 3600.0 for r in profile]
    lam_max, horizon = max(lam), 3600.0 * len(profile)
    t, k = 0.0, 0
    demand = []                                   # (t, sku index, qty) for the inbound rule
    while True:
        t += rng.exponential(1.0 / lam_max)
        if t >= horizon:
            break
        if rng.random() * lam_max > lam[int(t // 3600)]:
            continue
        k += 1
        n = min(max_lines, len(ids), int(rng.geometric(1 - p_line)))
        lines = rng.choice(len(ids), size=n, replace=False, p=w)
        for j in lines:
            q = int(rng.geometric(1 - p_qty))      # >= 1
            rows.append((round(t, 3), "ORDER", f"O{k:06d}", ids[j], q))
            demand.append((t, j, q))
    # --- inbound trucks
    daily = np.zeros(len(ids))
    for _, j, q in demand:
        daily[j] += q
    exp_daily = w * sum(profile) * units_per_order(p_line, p_qty) * demand_scale
    target = np.maximum(daily, exp_daily)
    stock = np.array([s[2] for s in skus], dtype=float)
    truck_times = list(np.arange(first_truck_s, horizon, truck_every_s))
    di = 0
    for n, tt in enumerate(truck_times):
        nxt = truck_times[n + 1] if n + 1 < len(truck_times) else horizon
        while di < len(demand) and demand[di][0] < tt:
            stock[demand[di][1]] -= demand[di][2]
            di += 1
        future = np.zeros(len(ids))
        for t2, j, q in demand[di:]:
            if t2 >= nxt:
                break
            future[j] += q
        for j in range(len(ids)):
            if stock[j] - future[j] < 0.5 * target[j]:
                q = int(math.ceil(1.5 * target[j] - (stock[j] - future[j])))
                if q > 0:
                    rows.append((float(tt), "RECEIPT", f"T{n + 1:03d}", ids[j], q))
                    stock[j] += q
    rows.sort(key=lambda r: (r[0], r[1] != "RECEIPT", r[2]))
    return rows


def write_skus(skus, path):
    with open(path, "w", newline="") as f:
        wr = csv.writer(f)
        wr.writerow(["sku", "weight", "init_qty"])
        for s, wgt, q in skus:
            wr.writerow([s, f"{wgt:.8f}", q])


def read_skus(path):
    with open(path) as f:
        return [(r["sku"], float(r["weight"]), int(r["init_qty"])) for r in csv.DictReader(f)]


def write_day(rows, path):
    with open(path, "w", newline="") as f:
        wr = csv.writer(f)
        wr.writerow(["t_s", "type", "id", "sku", "qty"])
        wr.writerows(rows)


def read_day(path):
    with open(path) as f:
        return [(float(r["t_s"]), r["type"], r["id"], r["sku"], int(r["qty"])) for r in csv.DictReader(f)]
