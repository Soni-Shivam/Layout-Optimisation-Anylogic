"""Input models fitted to the real footwear-warehouse data, and the workload generator built on them.

    python3 -m whsim.input_models      # fit, save input_models.json, write skus.csv + all day files + waves.csv

Model of one working day (model time 0 = 06:00, seconds):

  daily volume N   fitted parametric distribution (candidates Poisson / negative binomial / discretised
                   lognormal / discretised gamma, chosen by GoF + AIC), truncated to [5, 1.5 x max seen].
  release times    the WMS releases orders in BATCHES (1-5 per day, each a few minutes long; 07:1x is the
                   most common). Within-hour Poisson arrivals are rejected by the data (see the tests in
                   input_models.json), so arrivals are a batch process: the day's release pattern
                   (start, end, share of the day's orders of each release) is resampled from the 15 real
                   days whose volume is closest to N (volume and number of releases are correlated), the
                   N orders are split over the releases (multinomial) and spread uniformly inside each.
                   Alternative kept for comparison (arrival="nhpp"): a 07:xx batch of a Beta-distributed
                   share + the rest as a Poisson process with the fitted hour-of-day profile, given N.
  basket           a whole real order (SKUs + qty per SKU) drawn uniformly from the real orders created
                   within +-WINDOW_DAYS calendar days of the day whose release pattern was drawn (window
                   bootstrap): keeps lines/order, units/line, SKU co-occurrence inside an order AND the
                   seasonal / day-level SKU concentration (a plain bootstrap over the whole year gives
                   ~20% more distinct SKUs per day than reality). The fitted lines/order and units/line
                   distributions are reported only (all parametric fits are rejected).
  SKU mix          skus.csv weight = share of order lines of each SKU over the whole period (real).
  opening stock    ASSUMED: init_qty = max(2, ceil(COVER_DAYS x mean daily units), ceil(q90 of the SKU's
                   units on the days it is ordered)). The last term protects the many slow SKUs whose
                   demand is lumpy (mean < 1 unit/day, but several units when they sell).
  inbound          ASSUMED (no receipt data): a truck every 2 h from t = 1 h. At each truck the planner
                   sees the orders released before the next truck (2 h order book); every SKU whose
                   position (stock + received - ordered) minus that need would drop below
                   REORDER_FRAC x init_qty is brought back to init_qty + need.

make_real_day(date) replays one historical day instead: real orders at their real minute + U(0, 60) s.
"""
from __future__ import annotations

import csv
import functools
import json
import math
import pathlib

import numpy as np
import pandas as pd
from scipy import optimize, stats

from . import real_data as rd

ROOT = rd.ROOT
DATA = ROOT / "model" / "WarehouseSim" / "data"
MODEL_JSON = DATA / "config" / "input_models.json"
REAL_DIR = ROOT / "data" / "real"
POOL_CSV = REAL_DIR / "basket_pool.csv"
WAVES_CSV = REAL_DIR / "waves.csv"

HORIZON_S = 54000            # end of the model day (21:00), as in run_config.json (whsim.cli.RUN_CONFIG)
COVER_DAYS = 1.5             # ASSUMED opening stock cover (see input_report: stock-outs rare, not zero)
ACTIVE_DAY_Q = 0.9           # ASSUMED: opening stock covers the q90 of the SKU's units on a day it sells
MIN_STOCK = 2
TRUCK_FIRST_S, TRUCK_EVERY_S = 3600, 7200
REORDER_FRAC = 0.5
RELEASE_GAP_MIN = 5          # minutes without a new order that separate two releases
K_NEAREST = 15               # release pattern: resampled from the K days of closest volume
WINDOW_DAYS = 3              # baskets: drawn from real orders within +-3 calendar days of that day
N_BOOT = 300                 # parametric bootstrap replications for the KS p-values
SYNTH_SEEDS = range(1, 11)
N_REAL_DAYS = 10


# ----------------------------------------------------------------------------- distributions
def _nb_mle(x, shift=0):
    """Negative binomial (size r, prob p) MLE for x - shift >= 0. The MLE of the mean is the sample mean."""
    y = np.asarray(x) - shift
    m = y.mean()
    if y.var() <= m:                                   # no overdispersion: NB degenerates to Poisson
        return 1e6, 1e6 / (1e6 + m)
    nll = lambda lr: -stats.nbinom.logpmf(y, np.exp(lr), np.exp(lr) / (np.exp(lr) + m)).sum()
    lr = optimize.minimize_scalar(nll, bounds=(-8, 12), method="bounded").x
    r = float(np.exp(lr))
    return r, r / (r + m)


def _cont_disc_fit(x, family):
    """MLE of a continuous family (lognormal / gamma) discretised to integers: P(n) = F(n+.5) - F(n-.5)."""
    x = np.asarray(x, dtype=float)
    if family == "lognormal":
        th0 = [np.log(x).mean(), np.log(x).std()]
        mk = lambda th: stats.lognorm(s=th[1], scale=np.exp(th[0]))
    else:
        k = x.mean() ** 2 / x.var()
        th0 = [k, x.mean() / k]
        mk = lambda th: stats.gamma(a=th[0], scale=th[1])

    def nll(th):
        if min(th[1:]) <= 0 or (family == "gamma" and th[0] <= 0):
            return 1e12
        d = mk(th)
        p = np.clip(d.cdf(x + 0.5) - d.cdf(x - 0.5), 1e-300, None)
        return -np.log(p).sum()
    th = optimize.minimize(nll, th0, method="Nelder-Mead", options={"xatol": 1e-6, "fatol": 1e-8}).x
    return [float(v) for v in th]


def count_family(name, params):
    """Frozen-like helper: returns (pmf(n), cdf(n), sample(rng, size)) for an integer distribution."""
    if name == "poisson":
        d = stats.poisson(params["lam"])
        return d.pmf, d.cdf, lambda rng, k: rng.poisson(params["lam"], k)
    if name == "nbinom":
        d = stats.nbinom(params["r"], params["p"])
        return d.pmf, d.cdf, lambda rng, k: rng.negative_binomial(params["r"], params["p"], k)
    if name == "lognormal":
        d = stats.lognorm(s=params["sigma"], scale=math.exp(params["mu"]))
        smp = lambda rng, k: np.rint(rng.lognormal(params["mu"], params["sigma"], k)).astype(int)
    elif name == "gamma":
        d = stats.gamma(a=params["shape"], scale=params["scale"])
        smp = lambda rng, k: np.rint(rng.gamma(params["shape"], params["scale"], k)).astype(int)
    else:
        raise ValueError(name)
    pmf = lambda n: d.cdf(np.asarray(n) + 0.5) - d.cdf(np.asarray(n) - 0.5)
    cdf = lambda n: d.cdf(np.asarray(n) + 0.5)
    return pmf, cdf, smp


def fit_count(x, name):
    """Fit one daily-volume family. Returns (params, n_params)."""
    x = np.asarray(x)
    if name == "poisson":
        return {"lam": float(x.mean())}, 1
    if name == "nbinom":
        r, p = _nb_mle(x)
        return {"r": r, "p": p, "mean": float(x.mean())}, 2
    th = _cont_disc_fit(x, name)
    return ({"mu": th[0], "sigma": th[1]} if name == "lognormal" else {"shape": th[0], "scale": th[1]}), 2


def chi2_gof(x, pmf, n_par, k_bins=10, support=None):
    """Chi-square GoF on (approximately) equiprobable bins of the fitted integer pmf, expected >= 5."""
    x = np.asarray(x)
    hi = int(max(x.max(), 1) * 4 + 50) if support is None else support
    grid = np.arange(0, hi + 1)
    p = pmf(grid)
    p[-1] += max(0.0, 1 - p.sum())                    # tail mass into the last cell
    cum = np.cumsum(p)
    edges = [0]
    for j in range(1, k_bins):
        e = int(np.searchsorted(cum, j / k_bins)) + 1
        if e > edges[-1]:
            edges.append(e)
    edges.append(hi + 1)
    obs, exp = [], []
    for a, b in zip(edges[:-1], edges[1:]):
        obs.append(int(((x >= a) & (x < b)).sum()))
        exp.append(len(x) * p[a:b].sum())
    obs, exp = _merge_small(obs, exp)
    chi = float(((np.array(obs) - exp) ** 2 / exp).sum())
    dof = len(obs) - 1 - n_par
    return {"chi2": chi, "dof": int(dof), "p": float(stats.chi2.sf(chi, dof)) if dof > 0 else None,
            "bins": len(obs)}


def _merge_small(obs, exp, min_exp=5.0):
    obs, exp = list(obs), list(exp)
    i = 0
    while i < len(exp) and len(exp) > 1:
        if exp[i] < min_exp:
            j = i + 1 if i + 1 < len(exp) else i - 1
            obs[j] += obs[i]
            exp[j] += exp[i]
            del obs[i], exp[i]
            i = 0
        else:
            i += 1
    return obs, np.array(exp)


def ks_discrete(x, cdf):
    """KS distance between the empirical cdf and an integer cdf, checked just before and at each value."""
    x = np.sort(np.asarray(x))
    v = np.unique(x)
    ecdf_at = np.searchsorted(x, v, side="right") / len(x)
    ecdf_before = np.searchsorted(x, v, side="left") / len(x)
    return float(max(np.abs(ecdf_at - cdf(v)).max(), np.abs(ecdf_before - cdf(v - 1)).max()))


def fit_daily_volume(x, rng, n_boot=N_BOOT):
    """All candidate families for orders/day with log-likelihood, AIC, chi-square and bootstrap-KS."""
    out = {}
    for name in ["poisson", "nbinom", "lognormal", "gamma"]:
        par, k = fit_count(x, name)
        pmf, cdf, smp = count_family(name, par)
        ll = float(np.log(np.clip(pmf(x), 1e-300, None)).sum())
        d = ks_discrete(x, cdf)
        boot = []
        for _ in range(n_boot):                       # parametric bootstrap: refit on each sample
            y = np.maximum(smp(rng, len(x)), 1)
            p2, _ = fit_count(y, name)
            boot.append(ks_discrete(y, count_family(name, p2)[1]))
        out[name] = {"params": par, "k": k, "loglik": ll, "aic": 2 * k - 2 * ll,
                     "ks_D": d, "ks_p_boot": float(np.mean(np.array(boot) >= d)), "n_boot": n_boot,
                     "chi2": chi2_gof(x, pmf, k)}
    ok = [n for n, r in out.items() if r["ks_p_boot"] >= 0.05 and (r["chi2"]["p"] or 0) >= 0.05]
    chosen = min(ok, key=lambda n: out[n]["aic"]) if ok else "empirical"
    return out, chosen


def fit_shifted(x, name):
    """Families on {1, 2, ...} for lines/order and units/line. Returns (params, k, pmf)."""
    x = np.asarray(x)
    if name == "geometric":
        p = 1.0 / x.mean()
        return {"p": p}, 1, lambda n: stats.geom.pmf(n, p)
    if name == "nbinom":
        r, p = _nb_mle(x, shift=1)
        return {"r": r, "p": p}, 2, lambda n: stats.nbinom.pmf(np.asarray(n) - 1, r, p)
    if name == "zeta":
        la = np.log(x).sum()
        a = optimize.minimize_scalar(lambda a: a * la + len(x) * np.log(stats.zipf(a).pmf(1) ** -1),
                                     bounds=(1.01, 8), method="bounded").x
        return {"a": float(a)}, 1, lambda n: stats.zipf.pmf(n, a)
    raise ValueError(name)


def fit_basket_dist(x):
    """Fits for lines/order or units/line (n is large: chi-square on bins 1..10, 11-20, 21-50, 51+)."""
    x = np.asarray(x)
    edges = [1, 2, 3, 4, 5, 6, 7, 8, 9, 10, 11, 21, 51, 10 ** 6]
    obs = [int(((x >= a) & (x < b)).sum()) for a, b in zip(edges[:-1], edges[1:])]
    out = {"n": int(len(x)), "mean": float(x.mean()), "sd": float(x.std(ddof=1)), "max": int(x.max()),
           "quantiles": {str(q): float(np.quantile(x, q)) for q in (0.5, 0.75, 0.9, 0.95, 0.99)},
           "pmf_1_10": [float((x == k).mean()) for k in range(1, 11)], "fits": {}}
    for name in ["geometric", "nbinom", "zeta"]:
        par, k, pmf = fit_shifted(x, name)
        ll = float(np.log(np.clip(pmf(x), 1e-300, None)).sum())
        grid = np.arange(1, 10 ** 5)
        pg = pmf(grid)
        exp = [len(x) * pg[a - 1:min(b, 10 ** 5) - 1].sum() for a, b in zip(edges[:-1], edges[1:])]
        o, e = _merge_small(obs, exp)
        chi = float(((np.array(o) - e) ** 2 / e).sum())
        dof = len(o) - 1 - k
        out["fits"][name] = {"params": par, "loglik": ll, "aic": 2 * k - 2 * ll,
                             "chi2": {"chi2": chi, "dof": dof, "p": float(stats.chi2.sf(chi, dof))}}
    out["best_aic"] = min(out["fits"], key=lambda n: out["fits"][n]["aic"])
    out["any_accepted"] = any(f["chi2"]["p"] >= 0.05 for f in out["fits"].values())
    return out


# ----------------------------------------------------------------------------- arrival structure
def release_clusters(order_table, gap_min=RELEASE_GAP_MIN):
    """Groups each day's orders into releases (gaps > gap_min minutes). One row per (date, release)."""
    o = order_table[["order", "date", "created"]].copy()
    o["m"] = o.created.dt.hour * 60 + o.created.dt.minute
    o = o.sort_values(["date", "m"])
    o["rel"] = o.groupby("date").m.transform(lambda m: (m.diff() > gap_min).cumsum())
    c = o.groupby(["date", "rel"]).agg(start_m=("m", "min"), end_m=("m", "max"), n=("order", "size"))
    c = c.reset_index()
    c["share"] = c.n / c.groupby("date").n.transform("sum")
    c["start_s"] = c.start_m * 60.0 - rd.SHIFT_START_H * 3600
    c["end_s"] = c.end_m * 60.0 + 60.0 - rd.SHIFT_START_H * 3600
    return c


def jittered_times(order_table, rng):
    """Model times (s) of orders with the minute stamp jittered uniformly inside the minute."""
    return rd.t_seconds(order_table.created).values + rng.uniform(0, 60, len(order_table))


def arrival_tests(reg_orders, rng):
    """Tests of the within-day arrival process on regular days (jittered minute stamps)."""
    t = jittered_times(reg_orders, rng)
    u = (t % 3600) / 3600.0
    ks_u = stats.kstest(u, "uniform")
    gaps, cvs = [], []
    for _, idx in reg_orders.groupby("date").indices.items():
        g = np.diff(np.sort(t[idx]))
        if len(g) >= 2:
            gaps.append(g)
            cvs.append(g.std() / g.mean())
    gaps = np.concatenate(gaps)
    ks_e = stats.kstest(gaps, "expon", args=(0, gaps.mean()))
    # index of dispersion of counts in 10-min bins between 06:00 and 21:00 over all regular days
    counts = []
    for _, idx in reg_orders.groupby("date").indices.items():
        counts.append(np.histogram(t[idx], bins=np.arange(0, 15 * 3600 + 1, 600))[0])
    counts = np.concatenate(counts)
    disp = counts.var(ddof=1) / counts.mean()
    chi = (len(counts) - 1) * disp
    return {
        "within_hour_uniform_ks": {"D": float(ks_u.statistic), "p": float(ks_u.pvalue), "n": int(len(u))},
        "interarrival_exponential_ks": {"D": float(ks_e.statistic), "p": float(ks_e.pvalue),
                                        "n": int(len(gaps)), "mean_gap_s": float(gaps.mean()),
                                        "cv_pooled": float(gaps.std() / gaps.mean()),
                                        "cv_daily_median": float(np.median(cvs)),
                                        "note": "exponential has CV = 1; mean estimated from data"},
        "dispersion_10min": {"index": float(disp), "chi2": float(chi), "dof": int(len(counts) - 1),
                             "p": float(stats.chi2.sf(chi, len(counts) - 1)),
                             "note": "Poisson counts have index 1"},
        "verdict": "rejected: orders are released in batches, not as a Poisson stream",
    }


def morning_batch(clusters):
    """The 07:xx release as a separate component: presence probability and Beta share."""
    first = clusters.sort_values("start_m").groupby("date").head(1)
    hit = first[(first.start_m >= 7 * 60) & (first.start_m < 8 * 60)]
    s = hit.share.values
    m, v = s.mean(), s.var(ddof=1)
    c = m * (1 - m) / v - 1                           # Beta method of moments
    return {"p_present": float(len(hit) / len(first)), "n_days": int(len(first)),
            "share_mean": float(m), "share_sd": float(np.sqrt(v)),
            "share_beta": {"a": float(m * c), "b": float((1 - m) * c)},
            "start_s": [float(x) for x in hit.start_s], "dur_s": [float(x) for x in hit.end_s - hit.start_s]}


# ----------------------------------------------------------------------------- fit everything
def load_all(raw=rd.RAW):
    """Cleaned tables used by the fits and the report."""
    lines, log = rd.load_lines(raw)
    bk = rd.baskets(lines)
    ot = rd.orders(lines)
    dt = rd.days(ot)
    log += rd.day_log(dt)
    picks = rd.load_picks(raw)
    return {"lines": lines, "baskets": bk, "orders": ot, "days": dt, "log": log, "picks": picks}


def sku_table(T, cover_days=COVER_DAYS, min_stock=MIN_STOCK, active_q=ACTIVE_DAY_Q):
    """SKU master: weight = share of order lines (whole period); init_qty = ASSUMED cover rule."""
    bk = T["baskets"]
    reg_dates = set(T["days"].date[T["days"].regular])
    n_reg = len(reg_dates)
    lines = bk.groupby("sku").size()
    units = bk[bk.date.isin(reg_dates)].groupby("sku").qty.sum().reindex(lines.index, fill_value=0)
    active = bk.groupby(["sku", "date"]).qty.sum().groupby("sku").quantile(active_q)
    s = pd.DataFrame({"lines": lines, "daily_units": units / n_reg, "active_day_q": active})
    s["weight"] = s.lines / s.lines.sum()
    s["init_qty"] = np.maximum(min_stock, np.maximum(np.ceil(cover_days * s.daily_units),
                                                     np.ceil(s.active_day_q))).astype(int)
    return s.sort_values(["weight", "daily_units"], ascending=False)


def choose_real_days(day_table, n=N_REAL_DAYS):
    """n regular weekdays close to the 10th..90th volume percentiles, at most one per month if possible."""
    reg = day_table[day_table.regular].copy()
    reg["month"] = reg.date.dt.month
    chosen, used = [], set()
    for q in np.linspace(0.10, 0.90, n):
        target = float(np.quantile(reg.n_orders, q))
        cand = reg[~reg.date.isin(chosen)].assign(dist=lambda d: (d.n_orders - target).abs())
        cand = cand.sort_values(["dist", "date"])
        near = cand[cand.dist <= max(5.0, 0.08 * target)]
        free = near[~near.month.isin(used)]
        row = (free if len(free) else cand).iloc[0]
        chosen.append(row.date)
        used.add(row.month)
    out = reg.set_index("date").loc[chosen]
    return [{"date": d.strftime("%Y-%m-%d"), "weekday": int(r.weekday), "n_orders": int(r.n_orders),
             "n_lines": int(r.n_lines), "n_units": int(r.n_units), "target_quantile": float(q)}
            for (d, r), q in zip(out.iterrows(), np.linspace(0.10, 0.90, n))]


def fit_all(raw=rd.RAW, path=MODEL_JSON, seed=305, T=None):
    """Fits every input model, saves input_models.json and returns the dict."""
    rng = np.random.default_rng(seed)
    T = T or load_all(raw)
    ot, dt = T["orders"], T["days"]
    reg = dt[dt.regular]
    reg_orders = ot[ot.date.isin(set(reg.date))]
    x = reg.n_orders.values
    fits, chosen = fit_daily_volume(x, rng)
    # day of week
    groups = [reg.n_orders[reg.weekday == w].values for w in range(5)]
    kw = stats.kruskal(*groups)
    an = stats.f_oneway(*[np.log(g) for g in groups])
    dow = {"names": ["Mon", "Tue", "Wed", "Thu", "Fri"], "n_days": [int(len(g)) for g in groups],
           "mean": [float(g.mean()) for g in groups], "factor": [float(g.mean() / x.mean()) for g in groups],
           "kruskal": {"H": float(kw.statistic), "p": float(kw.pvalue)},
           "anova_log": {"F": float(an.statistic), "p": float(an.pvalue)}}
    dow["significant"] = bool(kw.pvalue < 0.05)
    # hour-of-day profile (share of orders by hour of creation)
    h = reg_orders.created.dt.hour.value_counts(normalize=True).sort_index()
    profile = {str(int(k)): float(v) for k, v in h.items()}
    # releases
    cl = release_clusters(reg_orders)
    per_day = cl.groupby("date").agg(K=("n", "size"), N=("n", "sum")).reset_index()
    kvals = per_day.K.values
    pois = stats.poisson(kvals.mean() - 1)
    k_obs = [int((kvals == k).sum()) for k in range(1, 5)] + [int((kvals >= 5).sum())]
    k_exp = [len(kvals) * pois.pmf(k - 1) for k in range(1, 5)] + [len(kvals) * pois.sf(3)]
    o2, e2 = _merge_small(k_obs, k_exp)
    chi_k = float(((np.array(o2) - e2) ** 2 / e2).sum())
    sp = stats.spearmanr(per_day.K, per_day.N)
    patterns = []
    for d, g in cl.groupby("date"):
        patterns.append({"date": d.strftime("%Y-%m-%d"), "n": int(g.n.sum()),
                         "rel": [[float(a), float(b), float(c)] for a, b, c in zip(g.start_s, g.end_s, g.share)]})
    releases = {
        "gap_min": RELEASE_GAP_MIN, "n_releases": int(len(cl)), "k_nearest": K_NEAREST,
        "per_day_K": {str(k): int((kvals == k).sum()) for k in sorted(set(kvals))},
        "K_minus_1_poisson_chi2": {"chi2": chi_k, "dof": len(o2) - 2,
                                   "p": float(stats.chi2.sf(chi_k, len(o2) - 2)) if len(o2) > 2 else None},
        "spearman_K_vs_N": {"rho": float(sp.correlation), "p": float(sp.pvalue)},
        "duration_min": {"mean": float(((cl.end_s - cl.start_s) / 60).mean()),
                         "max": float(((cl.end_s - cl.start_s) / 60).max())},
        "start_hour_counts": {str(int(k)): int(v) for k, v in (cl.start_m // 60).value_counts().sort_index().items()},
        "patterns": patterns,
    }
    mb = morning_batch(cl)
    first_rel = cl.sort_values("start_m").groupby("date").head(1)
    first_rel = first_rel[(first_rel.start_m >= 420) & (first_rel.start_m < 480)].set_index("date")
    m = reg_orders.created.dt.hour * 60 + reg_orders.created.dt.minute
    lo = reg_orders.date.map(first_rel.start_m)
    hi = reg_orders.date.map(first_rel.end_m)
    in_batch = (m >= lo) & (m <= hi)                  # NaN bounds (no 07:xx batch that day) -> False
    rest_h = reg_orders[~in_batch].created.dt.hour.value_counts(normalize=True).sort_index()
    mb["rest_profile"] = {str(int(k)): float(v) for k, v in rest_h.items()}
    # baskets
    bk = T["baskets"]
    lpo = fit_basket_dist(ot.n_lines.values)
    upl = fit_basket_dist(bk.qty.values)
    model = {
        "schema": "whsim.inputs/1",
        "source_data": "Mendeley Data pf2w725pw3 v1 (doi:10.17632/pf2w725pw3.1), CC BY 4.0",
        "period": [dt.date.min().strftime("%Y-%m-%d"), dt.date.max().strftime("%Y-%m-%d")],
        "time_origin": "model t = 0 at 06:00 of the day, seconds",
        "horizon_s": HORIZON_S,
        "n": {"order_lines_clean": int(len(T["lines"])), "orders": int(len(ot)), "skus": int(bk.sku.nunique()),
              "dates": int(len(dt)), "regular_days": int(len(reg))},
        "cleaning_log": T["log"],
        "daily_volume": {"source": "real", "n_days": int(len(x)), "mean": float(x.mean()),
                         "sd": float(x.std(ddof=1)), "min": int(x.min()), "max": int(x.max()),
                         "candidates": fits, "chosen": chosen, "empirical": [int(v) for v in x],
                         "truncate": [rd.MIN_ORDERS_DAY, int(1.5 * x.max())]},
        "day_of_week": {"source": "real", **dow,
                        "use": "optional weekday= argument scales the daily-volume mean; day files are pooled"},
        "hour_profile": {"source": "real", "share_by_hour": profile},
        "arrival_tests": {"source": "real", **arrival_tests(reg_orders, rng)},
        "releases": {"source": "real", "chosen": "empirical release patterns, nearest-volume resampling",
                     **releases},
        "morning_batch": {"source": "real", "use": "alternative arrival='nhpp' only", **mb},
        "basket": {"source": "real", "chosen": "window bootstrap of whole real orders", "window_days": WINDOW_DAYS,
                   "pool": str(POOL_CSV.relative_to(ROOT)),
                   "pool_orders": int(len(ot)), "outlier_orders_over_100_lines": int(ot.outlier.sum()),
                   "lines_per_order": lpo, "units_per_line": upl},
        "opening_stock": {"source": "assumed",
                          "rule": "max(min_stock, ceil(cover_days * mean daily units), ceil(q_active of units on selling days))",
                          "cover_days": COVER_DAYS, "min_stock": MIN_STOCK, "q_active": ACTIVE_DAY_Q},
        "inbound": {"source": "assumed", "first_truck_s": TRUCK_FIRST_S, "every_s": TRUCK_EVERY_S,
                    "reorder_frac": REORDER_FRAC,
                    "rule": "at each truck, SKUs with position - need(until next truck) < reorder_frac * init_qty "
                            "get init_qty + need - position"},
        "service_times": {"source": "assumed", "note": "no pick/pack timestamps in the data; see run_config.json "
                                                       "and reports/input_analysis.md (sensitivity parameters)"},
    }
    model["real_days"] = choose_real_days(dt)
    path = pathlib.Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(model, indent=1) + "\n")
    return model


# ----------------------------------------------------------------------------- generator
@functools.lru_cache(maxsize=4)
def load_model(path=MODEL_JSON):
    return json.loads(pathlib.Path(path).read_text())


@functools.lru_cache(maxsize=4)
def load_pool(path=POOL_CSV):
    """Basket pool: (baskets, dates). baskets[i] = tuple of (sku, qty); dates[i] = creation date (datetime64[D])."""
    df = pd.read_csv(path, dtype={"order": int, "date": str, "sku": str, "qty": int})
    g = df.groupby("order", sort=True)
    baskets = tuple(tuple(zip(x.sku, x.qty)) for _, x in g)
    dates = pd.to_datetime(g.date.first()).values.astype("datetime64[D]")
    return baskets, dates


def read_sku_master(path=DATA / "skus.csv"):
    """skus.csv -> {sku: init_qty} (insertion order = file order)."""
    with open(path) as f:
        return {r["sku"]: int(r["init_qty"]) for r in csv.DictReader(f)}


def sample_volume(model, rng, weekday=None):
    """Daily order count from the chosen fitted family (or the empirical days), truncated."""
    dv = model["daily_volume"]
    lo, hi = dv["truncate"]
    fam = dv["chosen"]
    scale = 1.0 if weekday is None else model["day_of_week"]["factor"][weekday]
    for _ in range(1000):
        if fam == "empirical":
            n = int(rng.choice(dv["empirical"]) * scale)
        else:
            par = dict(dv["candidates"][fam]["params"])
            if scale != 1.0:
                if fam == "nbinom":                       # keep size r, scale the mean
                    m = par["r"] * (1 - par["p"]) / par["p"] * scale
                    par["p"] = par["r"] / (par["r"] + m)
                elif fam == "poisson":
                    par["lam"] *= scale
                elif fam == "lognormal":
                    par["mu"] += math.log(scale)
                else:
                    par["scale"] *= scale
            n = int(count_family(fam, par)[2](rng, 1)[0])
        if lo <= n <= hi:
            return n
    return int(round(dv["mean"] * scale))


def pick_pattern(model, n, rng):
    """A real day's release pattern, drawn from the K_NEAREST regular days with volume closest to n."""
    pats = model["releases"]["patterns"]
    dist = np.array([abs(p["n"] - n) for p in pats], dtype=float)
    near = np.argsort(dist, kind="stable")[:model["releases"]["k_nearest"]]
    return pats[int(rng.choice(near))]


def arrival_times(model, n, rng, arrival="releases", pattern=None):
    """n order times (s, unsorted) for one day."""
    if arrival == "releases":
        rel = (pattern or pick_pattern(model, n, rng))["rel"]
        shares = np.array([r[2] for r in rel])
        counts = rng.multinomial(n, shares / shares.sum())
        return np.concatenate([rng.uniform(a, b, c) for (a, b, _), c in zip(rel, counts)])
    if arrival == "nhpp":
        mb = model["morning_batch"]
        nb = 0
        if rng.random() < mb["p_present"]:
            nb = int(rng.binomial(n, rng.beta(mb["share_beta"]["a"], mb["share_beta"]["b"])))
        k = int(rng.integers(len(mb["start_s"])))
        t_b = rng.uniform(mb["start_s"][k], mb["start_s"][k] + mb["dur_s"][k], nb)
        hrs = np.array([int(h) for h in mb["rest_profile"]])
        w = np.array(list(mb["rest_profile"].values()))
        hh = rng.choice(hrs, size=n - nb, p=w / w.sum())
        t_r = (hh - rd.SHIFT_START_H) * 3600.0 + rng.uniform(0, 3600, n - nb)
        return np.concatenate([t_b, t_r])
    raise ValueError(arrival)


def add_receipts(order_rows, init, horizon=HORIZON_S, first=TRUCK_FIRST_S, every=TRUCK_EVERY_S,
                 reorder_frac=REORDER_FRAC):
    """ASSUMED inbound rule. order_rows: (t, 'ORDER', id, sku, qty). Returns receipt rows (t, 'RECEIPT', truck, sku, qty)."""
    dem = sorted((r[0], r[3], r[4]) for r in order_rows)
    pos = dict(init)
    trucks = list(np.arange(first, horizon, every, dtype=float))
    out, di = [], 0
    for k, tt in enumerate(trucks):
        nxt = trucks[k + 1] if k + 1 < len(trucks) else horizon
        while di < len(dem) and dem[di][0] < tt:
            pos[dem[di][1]] -= dem[di][2]
            di += 1
        need = {}
        j = di
        while j < len(dem) and dem[j][0] < nxt:
            need[dem[j][1]] = need.get(dem[j][1], 0) + dem[j][2]
            j += 1
        cand = set(need) | {s for s, p in pos.items() if p < reorder_frac * init[s]}
        for s in sorted(cand):
            p = pos[s] - need.get(s, 0)
            if p < reorder_frac * init[s]:
                q = int(math.ceil(init[s] + need.get(s, 0) - pos[s]))
                out.append((float(tt), "RECEIPT", f"T{k + 1:03d}", s, q))
                pos[s] += q
    return out


def _finish(order_rows, init):
    rows = order_rows + add_receipts(order_rows, init)
    rows.sort(key=lambda r: (r[0], r[1] != "RECEIPT", r[2]))
    return rows


def make_synthetic_day(seed, model=None, pool=None, init=None, weekday=None, arrival="releases"):
    """One synthetic day from the fitted model only. Deterministic per seed. Rows (t_s, type, id, sku, qty)."""
    model = model or load_model()
    pool = pool or load_pool()
    init = init or read_sku_master()
    rng = np.random.default_rng(seed)
    n = sample_volume(model, rng, weekday)
    pattern = pick_pattern(model, n, rng)              # also the anchor day of the basket window
    times = np.sort(arrival_times(model, n, rng, arrival, pattern))
    baskets, dates = pool
    w = model["basket"]["window_days"]
    anchor = np.datetime64(pattern["date"], "D")
    cand = np.flatnonzero(np.abs((dates - anchor).astype(int)) <= w)
    picks = cand[rng.integers(0, len(cand), n)]
    rows = []
    for k, (t, b) in enumerate(zip(times, picks)):
        t = round(float(t), 3)
        for sku, q in baskets[int(b)]:
            rows.append((t, "ORDER", f"O{k + 1:06d}", sku, int(q)))
    return _finish(rows, init)


def make_real_day(date, baskets=None, init=None):
    """Replays one historical day: real orders, real minute + U(0, 60) s jitter (rng seeded by the date)."""
    d = pd.Timestamp(date).normalize()
    if baskets is None:
        lines, _ = rd.load_lines()
        baskets = rd.baskets(lines)
    init = init or read_sku_master()
    b = baskets[baskets.date == d]
    if b.empty:
        raise ValueError(f"no orders on {d.date()}")
    rng = np.random.default_rng(int(d.strftime("%Y%m%d")))
    first = b.drop_duplicates("order")
    t0 = rd.t_seconds(first.created).values + rng.uniform(0, 60, len(first))
    tmap = dict(zip(first.order, np.round(t0, 3)))
    rows = [(float(tmap[o]), "ORDER", f"O{o}", s, int(q)) for o, s, q in zip(b.order, b.sku, b.qty)]
    return _finish(rows, init)


# ----------------------------------------------------------------------------- files
def write_skus(s, path=DATA / "skus.csv"):
    with open(path, "w", newline="") as f:
        wr = csv.writer(f)
        wr.writerow(["sku", "weight", "init_qty"])
        for sku, r in s.iterrows():
            wr.writerow([sku, f"{r.weight:.8f}", int(r.init_qty)])


def write_day(rows, path):
    with open(path, "w", newline="") as f:
        wr = csv.writer(f)
        wr.writerow(["t_s", "type", "id", "sku", "qty"])
        wr.writerows(rows)


def day_summary(rows):
    o = [r for r in rows if r[1] == "ORDER"]
    rc = [r for r in rows if r[1] == "RECEIPT"]
    return (f"{len({r[2] for r in o})} orders, {len(o)} lines, {sum(r[4] for r in o)} units, "
            f"{len({r[2] for r in rc})} trucks, {len(rc)} receipt lines")


def main():
    T = load_all()
    REAL_DIR.mkdir(parents=True, exist_ok=True)
    (DATA / "scenarios").mkdir(parents=True, exist_ok=True)
    pool = T["baskets"][["order", "date", "sku", "qty"]].copy()
    pool["date"] = pool.date.dt.strftime("%Y-%m-%d")
    pool.to_csv(POOL_CSV, index=False)
    print(f"basket pool: {POOL_CSV}")
    model = fit_all(T=T)
    print(f"input models: {MODEL_JSON}  (daily volume: {model['daily_volume']['chosen']})")
    s = sku_table(T)
    write_skus(s)
    init = dict(zip(s.index, s.init_qty))
    print(f"skus.csv: {len(s)} SKUs")
    load_model.cache_clear()
    load_pool.cache_clear()
    for seed in SYNTH_SEEDS:
        rows = make_synthetic_day(seed, init=init)
        write_day(rows, DATA / "scenarios" / f"day_{seed}.csv")
        print(f"day_{seed}.csv: {day_summary(rows)}")
    for d in model["real_days"]:
        rows = make_real_day(d["date"], T["baskets"], init)
        name = f"real_{d['date'].replace('-', '')}.csv"
        write_day(rows, DATA / "scenarios" / name)
        print(f"{name}: {day_summary(rows)}")
    w = rd.waves(T["lines"], T["picks"])
    missing = set(" ".join(w.skus).split()) - set(s.index)
    assert not missing, f"wave SKUs missing from skus.csv: {sorted(missing)[:5]}"
    w.to_csv(WAVES_CSV, index=False)
    print(f"waves.csv: {len(w)} historical waves -> {WAVES_CSV}")


if __name__ == "__main__":
    main()
