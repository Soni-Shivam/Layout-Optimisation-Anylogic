"""Input-data audit (whsim.input_audit): the test statistics behave as they should on known data."""
import json

import numpy as np
from scipy import stats

from whsim import input_audit as ia
from whsim import input_models as im


def test_acf_and_ljung_box_detect_dependence():
    rng = np.random.default_rng(2)
    e = rng.normal(size=400)
    ar = np.zeros(400)
    for t in range(1, 400):
        ar[t] = 0.7 * ar[t - 1] + e[t]
    assert abs(ia.acf(e)[0]) < 3 * 1.96 / np.sqrt(400) and ia.acf(ar)[0] > 0.5
    assert ia.ljung_box(e)[1] > 0.01 and ia.ljung_box(ar)[1] < 1e-6


def test_runs_test():
    assert ia.runs_test(np.r_[np.zeros(50), np.ones(50)])[3] < 1e-10      # two long runs: not random
    assert ia.runs_test(np.random.default_rng(2).normal(size=300))[3] > 0.01


def test_discrete_anderson_darling_bootstrap():
    """Right family is accepted, a wrong one (Poisson for overdispersed counts) is rejected."""
    rng = np.random.default_rng(3)
    x = stats.nbinom.rvs(2.5, 2.5 / (2.5 + 190), size=160, random_state=rng)
    x = np.maximum(x, 1)
    assert ia.ad_bootstrap(x, "nbinom", rng, n_boot=60)["p_boot"] > 0.05
    assert ia.ad_bootstrap(x, "poisson", rng, n_boot=60)["p_boot"] < 0.05


def test_ad_statistic_zero_for_perfect_fit():
    d = stats.poisson(4)
    x = np.repeat(np.arange(0, 30), np.round(d.pmf(np.arange(0, 30)) * 1e5).astype(int))
    assert ia.ad_discrete(x, d.cdf, d.pmf) < 0.05


def test_audit_results_are_current():
    """reports/input_audit.json exists and agrees with the fitted model (re-run whsim.input_audit if not)."""
    R = json.loads(ia.AUDIT_JSON.read_text())
    m = im.load_model()
    assert set("ABCDEF") <= set(R)
    assert R["A"]["pick_timestamps_present"] is False
    assert abs(R["C"]["nbinom"]["params"]["r"] - m["daily_volume"]["candidates"]["nbinom"]["params"]["r"]) < 1e-6
    assert R["B"]["n_days"] == m["n"]["regular_days"]
