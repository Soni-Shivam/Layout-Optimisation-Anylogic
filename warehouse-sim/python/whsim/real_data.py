"""Loads and cleans the real WMS extract of a footwear warehouse (Mendeley Data pf2w725pw3 v1, CC BY 4.0).

Source: R. Furlan de Assis, "Order Picking Dataset from a Warehouse of a Footwear Manufacturing Company",
Mendeley Data, v1, 2024, doi:10.17632/pf2w725pw3.1. Files live in data_raw/mendeley/ (untrusted data:
read as text only).

What we use
  Customer_Order.csv   one row per order line: order, customer, reference, size, qty, creation minute,
                       wave, operator. -> arrivals, baskets, SKU mix, daily volume.
  Picking_Wave.csv     one row per UNIT picked: wave, reference, size, location, operator.
                       -> historical pick lists (waves.csv) and the reconciliation check below.
  Product.csv          reference -> ABC class (A/B/C) of the company.
  Storage_Location.csv location -> x, y, z. The README says metres, but the values are DECIMETRES
                       (x 86..666, y 0..1440 would make a 1.4 km building); z is the shelf level 1..4.

Cleaning rules (each one is counted in the log returned by load_lines):
  C1  UTF-8 byte-order mark on the first header (read with utf-8-sig).
  C2  trailing blanks in codCustomer / Sector / locations are stripped.
  C3  Size encoding: Customer_Order writes half sizes without the decimal point (105 = 10.5, 95 = 9.5,
      35..125); Picking_Wave and the storage files write 10.5. Sizes 30 <= s < 200 are divided by 10.
      Sizes >= 200 (one reference, PY5UPB, sizes 215..305) are a different size scale and are kept, as
      Picking_Wave keeps them. With this rule every unit in Picking_Wave matches a Customer_Order line.
  C4  lines with an empty size (16 lines, references 4E1WTK / UMKYTJ, never picked) are dropped.
  C5  lines with quantity 0 are dropped.
  C6  rows that are completely identical are KEPT: they are real repeated lines (the same SKU is split
      into several pick tasks). Dropping them breaks the unit reconciliation with Picking_Wave.
      Repeated (order, SKU) lines are merged by summing qty when an order is turned into a basket.
  C7  day classification: a "regular" day is Monday-Friday with at least MIN_ORDERS_DAY orders.
      Sundays (5 dates) and stray dates with 1-3 orders (data fragments) are kept in the order pool
      but excluded from the daily-volume and arrival-time fits.
  Outlier orders (very large B2B orders, up to 408 SKUs) are real and kept; they are flagged.

SKU id = f"{Reference}_{size:g}" with the corrected size, e.g. 8N10W9_9, 8N10W9_9.5, PY5UPB_235.
"""
from __future__ import annotations

import pathlib

import numpy as np
import pandas as pd

ROOT = pathlib.Path(__file__).resolve().parents[2]
RAW = ROOT / "data_raw" / "mendeley"
MIN_ORDERS_DAY = 5           # C7: fewer orders than this on a date = data fragment, not a working day
OUTLIER_LINES = 100          # orders with more distinct SKUs than this are flagged (not removed)
SHIFT_START_H = 6            # model time 0 = 06:00 of the day


def sku_id(ref, size):
    """SKU identifier: reference + '_' + size printed without trailing zeros (9.0 -> 9, 9.5 -> 9.5)."""
    return f"{str(ref).strip()}_{format(float(size), 'g')}"


def fix_size(s):
    """C3: Customer_Order half sizes without decimal point (35..125) -> 3.5..12.5. Works on arrays."""
    s = np.asarray(s, dtype=float)
    return np.where((s >= 30) & (s < 200), s / 10.0, s)


def _read(raw, name, sep=";"):
    return pd.read_csv(pathlib.Path(raw) / name, sep=sep, encoding="utf-8-sig", dtype=str)


def load_lines(raw=RAW):
    """Cleaned order lines and the cleaning log.

    Returns (lines, log). lines has one row per raw order line that survives C4/C5, columns:
    order, customer, seq, ref, size, sku, qty, created (Timestamp, minute resolution), date, wave, operator.
    log is a list of dicts {rule, rows, action}.
    """
    log = []
    with open(pathlib.Path(raw) / "Customer_Order.csv", "rb") as f:
        bom = f.read(3) == b"\xef\xbb\xbf"
    df = _read(raw, "Customer_Order.csv")
    n0 = len(df)
    log.append({"rule": "C0 raw Customer_Order lines", "rows": n0, "action": "read"})
    log.append({"rule": "C1 UTF-8 BOM on header", "rows": int(bom), "action": "read with utf-8-sig"})
    padded = int((df["codCustomer"] != df["codCustomer"].str.strip()).sum())
    log.append({"rule": "C2 trailing blanks in codCustomer", "rows": padded, "action": "stripped"})
    out = pd.DataFrame({
        "order": df["orderNumber"].astype(int),
        "customer": df["codCustomer"].str.strip(),
        "seq": df["orderToCollect"].astype(int),
        "ref": df["Reference"].str.strip(),
        "size_raw": pd.to_numeric(df["Size (US)"], errors="coerce"),
        "qty": df["quantity (units)"].astype(int),
        "created": pd.to_datetime(df["creationDate"], format="%d/%m/%Y %H:%M"),
        "wave": df["waveNumber"].astype(int),
        "operator": df["operator"].str.strip(),
    })
    shifted = int(((out.size_raw >= 30) & (out.size_raw < 200)).sum())
    log.append({"rule": "C3 half size written without decimal point (105 -> 10.5)", "rows": shifted,
                "action": "size / 10"})
    na = out.size_raw.isna()
    log.append({"rule": "C4 empty size", "rows": int(na.sum()), "action": "dropped"})
    out = out[~na]
    zero = out.qty <= 0
    log.append({"rule": "C5 quantity 0", "rows": int(zero.sum()), "action": "dropped"})
    out = out[~zero].copy()
    dup = int(out.duplicated(["order", "seq", "ref", "size_raw", "qty", "wave", "operator"]).sum())
    log.append({"rule": "C6 fully identical rows (split pick tasks)", "rows": dup, "action": "kept"})
    rep = int(out.duplicated(["order", "ref", "size_raw"]).sum())
    log.append({"rule": "C6 repeated (order, SKU) lines", "rows": rep,
                "action": "merged (qty summed) in baskets"})
    out["size"] = fix_size(out.size_raw)
    out["sku"] = [sku_id(r, s) for r, s in zip(out.ref, out["size"])]
    out["date"] = out.created.dt.normalize()
    out = out.drop(columns="size_raw").reset_index(drop=True)
    log.append({"rule": "clean order lines", "rows": len(out), "action": "kept"})
    return out, log


def baskets(lines):
    """One row per (order, SKU): qty summed over repeated lines (C6). Columns order, sku, qty, created, date."""
    g = lines.groupby(["order", "sku"], sort=False)
    b = g.agg(qty=("qty", "sum"), created=("created", "first"), date=("date", "first")).reset_index()
    return b.sort_values(["created", "order"], kind="stable").reset_index(drop=True)


def orders(lines):
    """One row per order: order, customer, created, date, n_lines (distinct SKUs), n_units, n_waves."""
    b = baskets(lines)
    o = b.groupby("order").agg(created=("created", "first"), date=("date", "first"),
                               n_lines=("sku", "size"), n_units=("qty", "sum"))
    extra = lines.groupby("order").agg(customer=("customer", "first"), n_waves=("wave", "nunique"))
    o = o.join(extra).reset_index()
    o["outlier"] = o.n_lines > OUTLIER_LINES
    return o.sort_values(["created", "order"]).reset_index(drop=True)


def days(order_table):
    """One row per calendar date with data: date, weekday (0 = Mon), n_orders, n_lines, n_units, regular (C7)."""
    d = order_table.groupby("date").agg(n_orders=("order", "size"), n_lines=("n_lines", "sum"),
                                        n_units=("n_units", "sum")).reset_index()
    d["weekday"] = d.date.dt.dayofweek
    d["regular"] = (d.weekday <= 4) & (d.n_orders >= MIN_ORDERS_DAY)
    return d


def day_log(day_table):
    """Cleaning-log rows for C7."""
    sun = day_table.weekday >= 5
    stray = (~sun) & (day_table.n_orders < MIN_ORDERS_DAY)
    return [
        {"rule": "C7 dates with data", "rows": len(day_table), "action": "classified"},
        {"rule": "C7 Saturday/Sunday dates", "rows": int(sun.sum()),
         "action": f"excluded from volume/arrival fits ({int(day_table.n_orders[sun].sum())} orders kept in pool)"},
        {"rule": f"C7 weekday dates with < {MIN_ORDERS_DAY} orders (fragments)", "rows": int(stray.sum()),
         "action": f"excluded from volume/arrival fits ({int(day_table.n_orders[stray].sum())} orders kept in pool)"},
        {"rule": "C7 regular working days", "rows": int(day_table.regular.sum()), "action": "used for fits"},
    ]


def load_picks(raw=RAW):
    """Picking_Wave: one row per unit picked. Columns wave, ref, size, sku, location, operator, pos (row order)."""
    df = _read(raw, "Picking_Wave.csv")
    pk = pd.DataFrame({
        "wave": df["waveNumber"].astype(int),
        "ref": df["reference"].str.strip(),
        "size": df["Size (US)"].astype(float),
        "qty": df["quantityToPick (units)"].astype(int),
        "location": df["locations"].str.strip(),
        "operator": df["operator"].str.strip(),
    })
    pk["sku"] = [sku_id(r, s) for r, s in zip(pk.ref, pk["size"])]
    pk["pos"] = np.arange(len(pk))
    return pk


def reconcile(lines, picks):
    """Units ordered vs units picked per (wave, SKU). Returns a dict of counts (checks rule C3)."""
    a = lines.groupby(["wave", "sku"]).qty.sum()
    b = picks.groupby(["wave", "sku"]).qty.sum()
    j = pd.concat([a.rename("ordered"), b.rename("picked")], axis=1)
    both = j.dropna()
    return {
        "wave_sku_cells": int(len(j)),
        "exact_match": int((both.ordered == both.picked).sum()),
        "picked_less": int((both.ordered > both.picked).sum()),
        "picked_more": int((both.ordered < both.picked).sum()),
        "ordered_never_picked": int(j.picked.isna().sum()),
        "picked_not_ordered": int(j.ordered.isna().sum()),
        "units_ordered": int(lines.qty.sum()),
        "units_picked": int(picks.qty.sum()),
        "units_never_picked": int(j.ordered[j.picked.isna()].sum()),
    }


def waves(lines, picks):
    """Historical waves: wave, n_orders, n_lines, n_units, skus, operator, date.

    n_orders / n_lines (distinct (order, SKU)) / date come from Customer_Order; n_units, the SKU list
    (distinct SKUs in pick-list order) and the operator (most frequent) from Picking_Wave. Waves that
    have no picks are left out.
    """
    lw = lines.groupby("wave").agg(n_orders=("order", "nunique"), date=("date", "first"))
    lw["n_lines"] = lines.drop_duplicates(["wave", "order", "sku"]).groupby("wave").size()
    pk = picks.sort_values("pos")
    pw = pk.groupby("wave").agg(n_units=("qty", "sum"),
                                operator=("operator", lambda s: s.value_counts().index[0]))
    pw["skus"] = pk.drop_duplicates(["wave", "sku"]).groupby("wave").sku.apply(" ".join)
    w = lw.join(pw, how="inner").reset_index()
    w["date"] = w.date.dt.strftime("%Y-%m-%d")
    return w[["wave", "n_orders", "n_lines", "n_units", "skus", "operator", "date"]].sort_values("wave")


def load_products(raw=RAW):
    """Product.csv: ref, abc, sector."""
    df = _read(raw, "Product.csv")
    return pd.DataFrame({"ref": df["Reference"].str.strip(), "abc": df["ABCCOD"].str.strip(),
                         "sector": df["Sector"].str.strip()})


def load_locations(raw=RAW):
    """Storage_Location.csv: location, x_m, y_m (converted from decimetres), level (z)."""
    df = pd.read_csv(pathlib.Path(raw) / "Storage_Location.csv", dtype=str, encoding="utf-8-sig")
    return pd.DataFrame({"location": df["originalLocation"].str.strip(),
                         "x_m": df["x"].astype(float) / 10.0, "y_m": df["y"].astype(float) / 10.0,
                         "level": df["z"].astype(int)})


def t_seconds(created):
    """Model time of a creation timestamp: seconds since 06:00 of the same day."""
    created = pd.to_datetime(created)
    return (created - created.dt.normalize()).dt.total_seconds() - SHIFT_START_H * 3600
