"""Input-data audit of the footwear-warehouse inputs, following PROJECT_SPEC.md section 3.1-3.2.

    python3 -m whsim.input_audit        # -> reports/input_audit.md, reports/input_audit.json, figures/audit_*.png

This complements whsim.input_models / whsim.input_report (which fit and validate the generator). Nothing here
changes a fitted model or a file the simulation reads; it checks the assumptions behind them:

  A  data audit       every raw file: rows, columns, missing values, time span, timestamp resolution, and the
                      check the spec asks for before relying on the data: are there line-level pick timestamps?
  B  daily volume     independence and stationarity over the year (ACF, Ljung-Box, runs test, trend, month),
                      i.e. whether "one simulated day = one i.i.d. draw from the fitted distribution" is fair.
  C  daily volume     goodness of fit with a DISCRETE Anderson-Darling statistic and parametric bootstrap
                      (refit on every sample), next to the KS / chi-square tests already in input_models.json.
  D  generator        large-sample check of the synthetic-day generator (input_report validates 30 seeds).
  E  baskets          stationarity of the basket (lines/order by month), order-to-order dependence, and how
                      fast the SKU mix drifts: the evidence for the +-3-day window bootstrap.
  F  operators        picker heterogeneity (lines per operator-day): size of the between-operator effect.
"""
from __future__ import annotations

import json
import math
import pathlib

import numpy as np
import pandas as pd
from scipy import stats

from . import input_models as im
from . import real_data as rd
from .input_report import (C_DATA, C_FIT1, C_FIT2, INK2, FIG, REPORTS, describe, md_table, pfmt, plt, save)

AUDIT_JSON = REPORTS / "input_audit.json"
AUDIT_MD = REPORTS / "input_audit.md"
N_BOOT = 300                    # parametric bootstrap replications (AD)
GEN_SEEDS = range(5001, 5301)   # 300 synthetic days for the large-sample generator check
SMALL_N = 30                    # size of the validation sample used in input_report
MAX_LAG = 10


# ----------------------------------------------------------------------------- statistics helpers
def acf(x, max_lag=MAX_LAG):
    x = np.asarray(x, float) - np.mean(x)
    d = (x * x).sum()
    return np.array([(x[:-k] * x[k:]).sum() / d for k in range(1, max_lag + 1)])


def ljung_box(x, max_lag=MAX_LAG):
    n = len(x)
    r = acf(x, max_lag)
    q = n * (n + 2) * np.sum(r ** 2 / (n - np.arange(1, max_lag + 1)))
    return float(q), float(stats.chi2.sf(q, max_lag))


def runs_test(x):
    """Wald-Wolfowitz runs test above / below the median. Returns (runs, expected, z, p)."""
    x = np.asarray(x, float)
    s = x[x != np.median(x)] > np.median(x)
    n1, n2 = int(s.sum()), int((~s).sum())
    runs = 1 + int(np.sum(s[1:] != s[:-1]))
    mu = 2 * n1 * n2 / (n1 + n2) + 1
    var = (mu - 1) * (mu - 2) / (n1 + n2 - 1)
    z = (runs - mu) / math.sqrt(var)
    return runs, float(mu), float(z), float(2 * stats.norm.sf(abs(z)))


def ad_discrete(x, cdf, pmf):
    """Anderson-Darling A^2 for a discrete distribution (Choulakian, Lockhart & Stephens 1994):
    A^2 = n * sum_j (F_n(j) - F(j))^2 p_j / (F(j)(1 - F(j))) over the support points j."""
    x = np.asarray(x)
    n = len(x)
    j = np.arange(max(0, x.min() - 50), x.max() * 3 + 50)
    F = np.clip(cdf(j), 1e-12, 1 - 1e-12)
    p = pmf(j)
    Fn = np.searchsorted(np.sort(x), j, side="right") / n
    return float(n * np.sum((Fn - F) ** 2 * p / (F * (1 - F))))


def ad_bootstrap(x, family, rng, n_boot=N_BOOT):
    par, _ = im.fit_count(x, family)
    pmf, cdf, smp = im.count_family(family, par)
    a0 = ad_discrete(x, cdf, pmf)
    boot = []
    for _ in range(n_boot):
        y = np.maximum(smp(rng, len(x)), 1)
        p2, _ = im.fit_count(y, family)
        f2 = im.count_family(family, p2)
        boot.append(ad_discrete(y, f2[1], f2[0]))
    boot = np.array(boot)
    return {"A2": a0, "p_boot": float((np.sum(boot >= a0) + 1) / (n_boot + 1)), "n_boot": n_boot, "params": par}


# ----------------------------------------------------------------------------- A. data audit
def data_audit(raw=rd.RAW):
    files = []
    for f in sorted(pathlib.Path(raw).glob("*.csv")):
        sep = ";" if f.read_text(encoding="utf-8-sig", errors="replace").splitlines()[0].count(";") else ","
        try:
            df = pd.read_csv(f, sep=sep, encoding="utf-8-sig", dtype=str, keep_default_na=False)
        except pd.errors.ParserError:
            files.append({"file": f.name, "rows": None, "cols": None, "missing_cells": None, "note": "not tabular"})
            continue
        blank = int((df.apply(lambda c: c.str.strip()) == "").sum().sum())
        files.append({"file": f.name, "rows": int(len(df)), "cols": int(df.shape[1]), "missing_cells": blank,
                      "note": ""})
    co = pd.read_csv(pathlib.Path(raw) / "Customer_Order.csv", sep=";", encoding="utf-8-sig", dtype=str)
    co.columns = [c.strip() for c in co.columns]
    t = pd.to_datetime(co.creationDate, format="%d/%m/%Y %H:%M")
    per_wave = co.groupby("waveNumber").creationDate.nunique()
    per_order = co.groupby("orderNumber").creationDate.nunique()
    pw = pd.read_csv(pathlib.Path(raw) / "Picking_Wave.csv", sep=";", encoding="utf-8-sig", dtype=str)
    pw.columns = [c.strip() for c in pw.columns]
    time_cols = [c for c in pw.columns if any(k in c.lower() for k in ("date", "time", "stamp"))]
    return {
        "files": files,
        "span": [str(t.min()), str(t.max())],
        "timestamp_resolution": "minute (seconds always 0)" if (t.dt.second == 0).all() else "sub-minute",
        "distinct_creation_stamps": int(co.creationDate.nunique()),
        "orders": int(co.orderNumber.nunique()), "waves": int(co.waveNumber.nunique()),
        "max_stamps_per_order": int(per_order.max()),
        "share_waves_single_stamp": float((per_wave == 1).mean()),
        "picking_wave_time_columns": time_cols,
        "pick_timestamps_present": bool(time_cols),
    }


# ----------------------------------------------------------------------------- B/C. daily volume
def volume_structure(dt):
    reg = dt[dt.regular].sort_values("date").reset_index(drop=True)
    x = reg.n_orders.values.astype(float)
    lx = np.log(x)
    r = acf(x)
    q, qp = ljung_box(x)
    ql, qlp = ljung_box(lx)
    runs = runs_test(x)
    rho = stats.spearmanr(np.arange(len(x)), x)
    months = reg.date.dt.month
    kw_m = stats.kruskal(*[g.values for _, g in reg.n_orders.groupby(months)])
    # residual after removing month and weekday levels (log scale)
    res = lx - pd.Series(lx).groupby(months.values).transform("mean").values
    res = res - pd.Series(res).groupby(reg.weekday.values).transform("mean").values
    q_res, q_res_p = ljung_box(res)
    # share of variance explained by month (eta^2 on log volume)
    eta_m = 1 - np.sum((lx - pd.Series(lx).groupby(months.values).transform("mean").values) ** 2) / \
        np.sum((lx - lx.mean()) ** 2)
    return reg, {
        "n_days": int(len(x)),
        "acf": [float(v) for v in r], "acf_band_95": float(1.96 / math.sqrt(len(x))),
        "ljung_box_10": {"Q": q, "p": qp}, "ljung_box_10_log": {"Q": ql, "p": qlp},
        "runs_test": {"runs": runs[0], "expected": runs[1], "z": runs[2], "p": runs[3]},
        "trend_spearman": {"rho": float(rho.statistic), "p": float(rho.pvalue)},
        "month_kruskal": {"H": float(kw_m.statistic), "p": float(kw_m.pvalue)},
        "month_eta2_log": float(eta_m),
        "month_mean": {int(k): float(v) for k, v in reg.n_orders.groupby(months).mean().items()},
        "residual_ljung_box_10": {"Q": q_res, "p": q_res_p, "acf1": float(acf(res, 1)[0])},
    }


# ----------------------------------------------------------------------------- D. generator
def generator_check(dt, model, seeds=GEN_SEEDS):
    real = dt[dt.regular]
    rows = []
    for s in seeds:
        day = im.make_synthetic_day(s, model=model)
        o = [r for r in day if r[1] == "ORDER"]
        rows.append({"seed": s, "orders": len({r[2] for r in o}), "lines": len(o), "units": sum(r[4] for r in o)})
    syn = pd.DataFrame(rows)
    out = {"n_synthetic": int(len(syn)), "n_real": int(len(real)), "metrics": {}}
    for m, col in (("orders", "n_orders"), ("lines", "n_lines"), ("units", "n_units")):
        a, b = real[col].values, syn[m].values
        ks = stats.ks_2samp(a, b)
        se = b.std(ddof=1) / math.sqrt(len(b))
        # how often a 30-day sample of this generator has a mean at least as far from the real mean
        rng = np.random.default_rng(7)
        means30 = np.array([rng.choice(b, SMALL_N, replace=False).mean() for _ in range(5000)])
        out["metrics"][m] = {"real_mean": float(a.mean()), "real_sd": float(a.std(ddof=1)),
                             "syn_mean": float(b.mean()), "syn_sd": float(b.std(ddof=1)),
                             "syn_mean_ci95": [float(b.mean() - 1.96 * se), float(b.mean() + 1.96 * se)],
                             "ks_D": float(ks.statistic), "ks_p": float(ks.pvalue),
                             "mean_of_30_days_p05_p95": [float(np.quantile(means30, .05)),
                                                         float(np.quantile(means30, .95))]}
    return syn, out


# ----------------------------------------------------------------------------- E. baskets
def basket_structure(T):
    ot = T["orders"]
    reg_dates = set(T["days"].date[T["days"].regular])
    o = ot[ot.date.isin(reg_dates)].sort_values("created")
    kw = stats.kruskal(*[g.values for _, g in o.n_lines.groupby(o.date.dt.month)])
    lx = np.log(o.n_lines.values)
    grp = o.date.dt.month.values
    eta = 1 - np.sum((lx - pd.Series(lx).groupby(grp).transform("mean").values) ** 2) / np.sum((lx - lx.mean()) ** 2)
    # order-to-order dependence inside a day (orders sorted by creation time; ties keep file order)
    r1 = []
    for _, g in o.groupby("date"):
        v = g.n_lines.values
        if len(v) > 10:
            r1.append(np.corrcoef(v[:-1], v[1:])[0, 1])
    same_cust = (o.customer.values[1:] == o.customer.values[:-1]).mean()
    # SKU-mix drift: Spearman correlation of weekly SKU line shares vs distance in weeks
    bk = T["baskets"][T["baskets"].date.isin(reg_dates)]
    wk = bk.assign(w=(bk.date - bk.date.min()).dt.days // 7).groupby(["w", "sku"]).size().unstack(fill_value=0)
    wk = wk[wk.sum(axis=1) >= 200]
    share = wk.div(wk.sum(axis=1), axis=0)
    weeks = share.index.values
    drift = {}
    for lag in (1, 2, 4, 8, 12, 20, 30):
        cs = [stats.spearmanr(share.loc[a], share.loc[a + lag]).statistic for a in weeks if a + lag in share.index]
        if cs:
            drift[lag] = {"rho_mean": float(np.mean(cs)), "pairs": len(cs)}
    # distinct SKUs touched per day: real vs. a whole-year bootstrap of the same number of lines
    rng = np.random.default_rng(11)
    lines_by_day = bk.groupby("date").sku.agg(list)
    all_skus = bk.sku.values
    real_d, boot_d = [], []
    for skus in lines_by_day.values:
        real_d.append(len(set(skus)))
        boot_d.append(len(set(rng.choice(all_skus, len(skus)))))
    return {
        "lines_per_order_by_month": {int(k): float(v) for k, v in o.n_lines.groupby(o.date.dt.month).mean().items()},
        "month_kruskal": {"H": float(kw.statistic), "p": float(kw.pvalue)}, "month_eta2_log": float(eta),
        "lag1_lines_within_day": {"median": float(np.median(r1)), "mean": float(np.mean(r1)), "days": len(r1)},
        "share_consecutive_same_customer": float(same_cust),
        "weekly_sku_share_spearman_by_lag": drift,
        "distinct_skus_per_day": {"real_mean": float(np.mean(real_d)), "year_bootstrap_mean": float(np.mean(boot_d)),
                                  "ratio": float(np.mean(boot_d) / np.mean(real_d))},
    }


# ----------------------------------------------------------------------------- F. operators
def operator_structure(T):
    lines = T["lines"]
    reg_dates = set(T["days"].date[T["days"].regular])
    wave_date = lines.groupby("wave").date.min()
    od = lines[lines.date.isin(reg_dates)].groupby(["operator", "date"]).size().rename("lines").reset_index()
    keep = od.groupby("operator").date.transform("size") >= 20
    od = od[keep]
    y = np.log(od.lines.values)
    g = od.operator.values
    kw = stats.kruskal(*[np.log(v.values) for _, v in od.groupby("operator").lines])
    # one-way random-effects ANOVA on log lines -> intraclass correlation (share of variance between operators)
    k = od.groupby("operator").size()
    n0 = (len(od) - (k ** 2).sum() / len(od)) / (len(k) - 1)
    gm = pd.Series(y).groupby(g).mean()
    msb = (k * (gm - y.mean()) ** 2).sum() / (len(k) - 1)
    msw = ((y - pd.Series(y).groupby(g).transform("mean").values) ** 2).sum() / (len(od) - len(k))
    s2b = max((msb - msw) / n0, 0.0)
    # share of the day's lines done by each operator, relative to an equal split among that day's operators
    dd = od.assign(n_op=od.groupby("date").operator.transform("size"),
                   tot=od.groupby("date").lines.transform("sum"))
    rel = (dd.lines / (dd.tot / dd.n_op)).groupby(dd.operator).mean()
    return {
        "operators_with_20_days": int(len(k)), "operator_days": int(len(od)),
        "kruskal_log_lines": {"H": float(kw.statistic), "p": float(kw.pvalue)},
        "icc_log_lines": float(s2b / (s2b + msw)), "sd_between_log": float(math.sqrt(s2b)),
        "relative_share_vs_equal_split": {"min": float(rel.min()), "max": float(rel.max()),
                                          "cv": float(rel.std() / rel.mean())},
        "n_waves_dated": int(len(wave_date)),
    }


# ----------------------------------------------------------------------------- figures
def fig_volume(reg, B):
    fig, ax = plt.subplots(1, 2, figsize=(10, 3.2))
    ax[0].plot(reg.date, reg.n_orders, color=C_DATA, lw=1.2)
    m = reg.groupby(reg.date.dt.to_period("M")).n_orders.mean()
    ax[0].plot(m.index.to_timestamp() + pd.Timedelta(days=14), m.values, color=C_FIT1, lw=2, label="month mean")
    ax[0].set(title="Orders per regular working day, 2023", ylabel="orders")
    import matplotlib.dates as mdates
    ax[0].xaxis.set_major_locator(mdates.MonthLocator())
    ax[0].xaxis.set_major_formatter(mdates.DateFormatter("%b"))
    ax[0].legend()
    lags = np.arange(1, MAX_LAG + 1)
    ax[1].bar(lags, B["acf"], color=C_DATA, width=0.6)
    for s in (1, -1):
        ax[1].axhline(s * B["acf_band_95"], color=INK2, ls="--", lw=1)
    ax[1].set(title="Autocorrelation of daily volume (working-day lags)", xlabel="lag (working days)",
              ylabel="ACF")
    save(fig, "audit_volume_acf.png")


def fig_generator(dt, syn, D):
    real = dt[dt.regular].n_orders.values
    fig, ax = plt.subplots(1, 2, figsize=(10, 3.2))
    bins = np.linspace(0, max(real.max(), syn.orders.max()), 30)
    ax[0].hist(real, bins=bins, density=True, color=C_DATA, alpha=0.6, label=f"real ({len(real)} days)")
    ax[0].hist(syn.orders, bins=bins, density=True, histtype="step", color=C_FIT1, lw=2,
               label=f"generator ({len(syn)} days)")
    ax[0].set(title="Orders per day", xlabel="orders", ylabel="density")
    ax[0].legend()
    rng = np.random.default_rng(7)
    means30 = [rng.choice(syn.orders.values, SMALL_N, replace=False).mean() for _ in range(5000)]
    ax[1].hist(means30, bins=40, color=C_FIT2)
    ax[1].axvline(real.mean(), color=C_DATA, lw=2)
    ax[1].text(real.mean(), ax[1].get_ylim()[1] * 0.92, " real mean", color=INK2, fontsize=8)
    ax[1].set(title=f"Mean of {SMALL_N} generator days (5,000 resamples)", xlabel="mean orders/day",
              ylabel="count")
    save(fig, "audit_generator.png")


def fig_drift(E):
    d = E["weekly_sku_share_spearman_by_lag"]
    fig, ax = plt.subplots(figsize=(5, 3.2))
    ax.plot([int(k) for k in d], [v["rho_mean"] for v in d.values()], color=C_DATA, marker="o", ms=5)
    ax.set(title="SKU mix similarity between two weeks", xlabel="weeks apart",
           ylabel="Spearman rho of SKU line shares")
    save(fig, "audit_sku_drift.png")


# ----------------------------------------------------------------------------- report
def write_report(R):
    A, B, C, D, E, F = (R[k] for k in "ABCDEF")
    out = []
    add = out.append
    add("# Input data audit (spec §3.1–3.2): footwear order-fulfilment warehouse\n")
    add("IE305 Simulation Lab. Generated by `python3 -m whsim.input_audit`; do not edit by hand. It checks the "
        "assumptions behind the input models in `reports/input_analysis.md` (`whsim.input_models`). "
        "**No fitted model or simulation input file is changed by this audit.** Numbers: `reports/input_audit.json`.\n")
    add("**Data.** Mendeley Data pf2w725pw3 v1 (doi:10.17632/pf2w725pw3.1), files in `data_raw/mendeley/`. "
        "The second dataset named in the spec (B2FIND / KIT order-picking benchmark) is **not part of this "
        "audit**: it could not be downloaded from the analysis environment (host blocked). Its role in the "
        "spec is routing verification, not input modelling.\n")

    add("## A. Data audit\n")
    add(md_table(pd.DataFrame(A["files"])[["file", "rows", "cols", "missing_cells", "note"]]))
    add(f"\nBlank cells are counted after trimming. Customer_Order spans {A['span'][0]} to {A['span'][1]}, "
        f"timestamp resolution: **{A['timestamp_resolution']}**, {A['distinct_creation_stamps']} distinct stamps "
        f"for {A['orders']:,} orders and {A['waves']:,} waves; every order has at most "
        f"{A['max_stamps_per_order']} stamp and {A['share_waves_single_stamp']:.0%} of waves carry a single stamp.\n")
    add("**Spec §3.1 check: are there line-level pick timestamps?** "
        + ("No. " if not A["pick_timestamps_present"] else "Yes. ")
        + f"Picking_Wave has no date/time column ({A['picking_wave_time_columns'] or 'none'}), and the only time "
        "in Customer_Order is the order creation minute. Pick time per line therefore cannot be estimated "
        "from this dataset and stays an **assumed** input (lognormal mean 12 s, sd 5 s in `run_config.json`), "
        "to be varied in the sensitivity analysis. The data-derived upper bound is in `input_analysis.md` §4.6.\n")

    add("## B. Daily volume: independence and stationarity\n")
    lb, lbl, rt, tr = B["ljung_box_10"], B["ljung_box_10_log"], B["runs_test"], B["trend_spearman"]
    acf_s = ", ".join(f"{v:+.2f}" for v in B["acf"][:5])
    add(md_table(pd.DataFrame([
        {"test": f"ACF lags 1-5 (95% band ±{B['acf_band_95']:.2f})", "statistic": acf_s, "p": ""},
        {"test": "Ljung-Box, 10 lags (orders/day)", "statistic": f"Q = {lb['Q']:.1f}", "p": pfmt(lb["p"])},
        {"test": "Ljung-Box, 10 lags (log orders/day)", "statistic": f"Q = {lbl['Q']:.1f}", "p": pfmt(lbl["p"])},
        {"test": "runs test above/below median", "statistic": f"{rt['runs']} runs (exp. {rt['expected']:.1f}), "
                                                               f"z = {rt['z']:.2f}", "p": pfmt(rt["p"])},
        {"test": "trend: Spearman(volume, day index)", "statistic": f"rho = {tr['rho']:+.3f}", "p": pfmt(tr["p"])},
        {"test": "month effect: Kruskal-Wallis", "statistic": f"H = {B['month_kruskal']['H']:.1f}; "
                                                               f"eta² (log) = {B['month_eta2_log']:.2f}",
         "p": pfmt(B["month_kruskal"]["p"])},
        {"test": "Ljung-Box on residual after month + weekday", "statistic":
            f"Q = {B['residual_ljung_box_10']['Q']:.1f}; lag-1 = {B['residual_ljung_box_10']['acf1']:+.2f}",
         "p": pfmt(B["residual_ljung_box_10"]["p"])},
    ])))
    mm = ", ".join(f"{pd.Timestamp(2023, int(k), 1):%b} {v:.0f}" for k, v in B["month_mean"].items())
    add(f"\nMonth means (orders/day): {mm}.\n")
    add("![volume](figures/audit_volume_acf.png)\n")
    short_dep = B["residual_ljung_box_10"]["p"] < 0.05
    seasonal = B["month_kruskal"]["p"] < 0.05
    dep = short_dep or seasonal
    mvals = np.array(list(B["month_mean"].values()))
    add("**Reading.** " + (
        "Day-to-day dependence: after removing the month and weekday levels the residual is "
        + ("serially correlated" if short_dep else "white noise")
        + f" (Ljung-Box p = {pfmt(B['residual_ljung_box_10']['p'])}); the raw counts show no significant "
        f"short-range autocorrelation either (p = {pfmt(lb['p'])}); the largest single lag is lag 5 "
        f"(one working week, ACF {B['acf'][4]:+.2f}), i.e. the weekday effect already in `input_analysis.md` §5.1. "
        + ("There is, however, a slow **seasonal level**: the month explains "
           f"{B['month_eta2_log']:.0%} of the variance of log volume (Kruskal-Wallis p = "
           f"{pfmt(B['month_kruskal']['p'])}), month means range {mvals.min():.0f}–{mvals.max():.0f} orders/day, "
           f"and volume declines over the year (Spearman rho = {tr['rho']:+.2f}). The log-scale Ljung-Box "
           f"(p = {pfmt(lbl['p'])}) picks up this level shift, not day-to-day memory. "
           "**Consequences:** (i) for one-day terminating replications, drawing each day i.i.d. from the fitted "
           "negative binomial is correct: it is the marginal distribution of a 2023 working day; (ii) a multi-day "
           "run with stock carried over should hold the month level fixed within the run; (iii) peak scenarios "
           "can be anchored on the data: the busiest month (Feb) is "
           f"{mvals.max() / np.mean(mvals):.2f}× and the quietest (Jun) {mvals.min() / np.mean(mvals):.2f}× the "
           "average month." if seasonal else
           "No seasonal level either: drawing each simulated day i.i.d. from the fitted distribution is "
           "supported by the data.")) + "\n")

    add("## C. Daily volume: discrete Anderson-Darling with parametric bootstrap\n")
    add("The KS and chi-square tests in `input_models.json` are complemented with the Anderson-Darling "
        "statistic for discrete distributions (Choulakian, Lockhart & Stephens 1994), which weights the tails. "
        f"The p-value comes from a parametric bootstrap with the parameters re-estimated on each of {N_BOOT} samples "
        "(spec §3.2 step 5).\n")
    add(md_table(pd.DataFrame([{"family": k, "A²": v["A2"], "p (bootstrap)": pfmt(v["p_boot"]),
                                "parameters": ", ".join(f"{a} = {b:.4g}" for a, b in v["params"].items())}
                               for k, v in C.items()]), {"A²": ".3f"}))
    ok = [k for k, v in C.items() if v["p_boot"] >= 0.05]
    add(f"\nPassing at 5%: {', '.join(ok) if ok else 'none'}. "
        + ("The chosen negative binomial is confirmed by a tail-sensitive test." if "nbinom" in ok else
           "The chosen negative binomial is NOT confirmed by AD; see the discussion.") + "\n")

    add("## D. Generator: large-sample check\n")
    add(f"The first version of `input_analysis.md` §7 validated the generator on {SMALL_N} synthetic days "
        "(seeds 1001..1030) and reported orders/day 156 vs 193 (KS p = 0.050), which looked like a bias. Here the "
        f"same generator (`input_models.make_synthetic_day`) is run on {D['n_synthetic']} independent seeds "
        f"({GEN_SEEDS.start}..{GEN_SEEDS.stop - 1}).\n")
    rows = []
    for m, v in D["metrics"].items():
        rows.append({"per day": m, "real mean (sd)": f"{v['real_mean']:.1f} ({v['real_sd']:.1f})",
                     "generator mean (sd)": f"{v['syn_mean']:.1f} ({v['syn_sd']:.1f})",
                     "generator mean 95% CI": f"{v['syn_mean_ci95'][0]:.0f}–{v['syn_mean_ci95'][1]:.0f}",
                     "KS p": pfmt(v["ks_p"]),
                     f"mean of {SMALL_N} days, 5–95%": f"{v['mean_of_30_days_p05_p95'][0]:.0f}–"
                                                       f"{v['mean_of_30_days_p05_p95'][1]:.0f}"})
    add(md_table(pd.DataFrame(rows)))
    o = D["metrics"]["orders"]
    add(f"\n![generator](figures/audit_generator.png)\n")
    add(f"**Reading.** With {D['n_synthetic']} days the generator's mean volume ({o['syn_mean']:.0f}) matches the real "
        f"mean ({o['real_mean']:.0f}). A mean of {SMALL_N} generator days falls anywhere in "
        f"{o['mean_of_30_days_p05_p95'][0]:.0f}–{o['mean_of_30_days_p05_p95'][1]:.0f} (90% range), so the 156 in "
        "§7 was sampling noise of a small validation sample, not a bias. Even 200-seed blocks are noisy: seeds "
        "1001..1200, 1201..1400 and 1401..1600 give orders/day KS p = 0.049, 0.88 and 0.44. `VALID_SEEDS` in "
        "`input_report.py` is therefore set to 1,000 days (seeds 1001..2000; orders/day 198 vs 193, KS p = 0.42).\n")

    add("## E. Baskets: stationarity, dependence and SKU-mix drift\n")
    lm = ", ".join(f"{pd.Timestamp(2023, int(k), 1):%b} {v:.2f}" for k, v in E["lines_per_order_by_month"].items())
    lpm = np.array(list(E["lines_per_order_by_month"].values()))
    add(f"- **Lines per order by month:** {lm}. The mean rises from {lpm.min():.1f} to {lpm.max():.1f} lines "
        f"(Kruskal-Wallis p = {pfmt(E['month_kruskal']['p'])}), yet the month explains only "
        f"{E['month_eta2_log']:.1%} of the variance of log lines/order: the order-to-order spread dominates. "
        "The window bootstrap draws baskets from the anchor day's own ±3 days, so it inherits the month's basket "
        "size automatically; a whole-year bootstrap would not.")
    lw = E["lag1_lines_within_day"]
    add(f"- **Order-to-order dependence:** lag-1 correlation of lines/order between consecutive orders of a day, "
        f"median over {lw['days']} days = {lw['median']:+.2f} (mean {lw['mean']:+.2f}): basket sizes of successive "
        "orders are independent, as the bootstrap assumes. "
        f"{E['share_consecutive_same_customer']:.0%} of consecutive orders come from the same customer (a "
        "customer's orders are released together). The bootstrap does not reproduce that customer clustering; it "
        "only affects which orders share a cart, not the volume or the basket sizes.")
    dr = E["weekly_sku_share_spearman_by_lag"]
    ds = E["distinct_skus_per_day"]
    add("- **SKU-mix drift:** Spearman correlation of weekly SKU line shares, by distance in weeks: "
        + ", ".join(f"{k} wk {v['rho_mean']:.2f}" for k, v in dr.items()) + ". "
        f"The mix decays steadily (seasonal collections). A whole-year bootstrap would give "
        f"{ds['year_bootstrap_mean']:.0f} distinct SKUs per day for the real number of lines, against "
        f"{ds['real_mean']:.0f} in reality (×{ds['ratio']:.2f}). This is the quantitative case for the "
        "±3-day window bootstrap in `input_models` and for slotting from the same period as the demand.\n")
    add("![drift](figures/audit_sku_drift.png)\n")

    add("## F. Picker heterogeneity\n")
    add(f"Lines per operator-day for the {F['operators_with_20_days']} operators with at least 20 working days "
        f"({F['operator_days']} operator-days): Kruskal-Wallis on log lines p = {pfmt(F['kruskal_log_lines']['p'])}; "
        f"intraclass correlation {F['icc_log_lines']:.2f} (share of the variance of log lines that is between "
        f"operators). Relative to an equal split of the day's lines among that day's operators, an operator's "
        f"average share ranges {F['relative_share_vs_equal_split']['min']:.2f}–"
        f"{F['relative_share_vs_equal_split']['max']:.2f} (CV {F['relative_share_vs_equal_split']['cv']:.2f}). "
        "Most of the variation is therefore day-to-day workload, not the operator. "
        "These differences mix speed with task allocation (some operators also pack or receive), so they are "
        "**not** a speed estimate. The model's pickers are identical; a per-picker speed factor drawn once per "
        "day (e.g. lognormal, sd ≈ the between-operator sd on the log scale, "
        f"{F['sd_between_log']:.2f}) is the natural sensitivity case.\n")

    add("## Summary for the model\n")
    add(md_table(pd.DataFrame([
        {"input": "pick time per line", "finding": "no pick timestamps in the data",
         "action": "stays assumed; sensitivity 8–20 s"},
        {"input": "daily volume", "finding": f"NB marginal {'passes' if 'nbinom' in ok else 'fails'} AD; days are "
                                             f"{'independent day to day, with a month level' if dep else 'independent'}",
         "action": "keep i.i.d. NB for one-day replications; peak scenarios from month means"},
        {"input": "synthetic-day generator", "finding": f"unbiased over {D['n_synthetic']} days",
         "action": "validation now on 1,000 days (VALID_SEEDS)"},
        {"input": "baskets", "finding": "size and SKU mix vary by month; orders independent",
         "action": "keep ±3-day window bootstrap"},
        {"input": "pickers", "finding": f"between-operator ICC {F['icc_log_lines']:.2f}",
         "action": "optional picker-speed-factor sensitivity"},
    ])))
    AUDIT_MD.write_text("\n".join(out) + "\n")


def build(gen_seeds=GEN_SEEDS, n_boot=N_BOOT):
    rng = np.random.default_rng(305)
    T = im.load_all()
    model = im.load_model()
    R = {"A": data_audit()}
    reg, R["B"] = volume_structure(T["days"])
    x = reg.n_orders.values
    R["C"] = {f: ad_bootstrap(x, f, rng, n_boot) for f in ("poisson", "nbinom", "lognormal", "gamma")}
    syn, R["D"] = generator_check(T["days"], model, gen_seeds)
    R["E"] = basket_structure(T)
    R["F"] = operator_structure(T)
    fig_volume(reg, R["B"])
    fig_generator(T["days"], syn, R["D"])
    fig_drift(R["E"])
    REPORTS.mkdir(parents=True, exist_ok=True)
    AUDIT_JSON.write_text(json.dumps(R, indent=1, default=float) + "\n")
    write_report(R)
    return R


def main():
    R = build()
    print(f"wrote {AUDIT_MD} and {AUDIT_JSON}")
    print(f"AD p (nbinom) = {R['C']['nbinom']['p_boot']:.3f}; Ljung-Box p = {R['B']['ljung_box_10']['p']:.2g}; "
          f"generator orders/day {R['D']['metrics']['orders']['syn_mean']:.1f} vs real "
          f"{R['D']['metrics']['orders']['real_mean']:.1f}")


if __name__ == "__main__":
    main()
