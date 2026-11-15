"""Tests for the block-level omnibus change detector (Conradsen et al. 2016).

Synthetic data are gamma-distributed block intensities, `rng.gamma(n, mean / n)`, i.e. the
distribution of an n-look intensity with the given mean. All RNG seeds are fixed so every
statistical assertion is deterministic.
"""

import numpy as np
import pytest
from scipy import stats

from sarstellar.detect import (
    bh_fdr,
    changed,
    estimate_enl,
    omnibus,
    relative_delta,
    stable_mask,
)

# Any warning (divide-by-zero, invalid value in log, all-NaN slice, ...) is a test failure.
pytestmark = pytest.mark.filterwarnings("error")

GRID = (100, 200)  # 20,000 blocks


def gamma_stack(rng, n, T, shape=GRID, mean=1.0):
    """T dates of n-look gamma intensities with the given mean; shape [T, *shape]."""
    return rng.gamma(n, mean / n, size=(T, *shape))


def db(x):
    return 10.0 * np.log10(x)


def pipeline_enls(channels):
    """The path the engine takes: stable mask from last-vs-first deltas, then ENL per band."""
    stable = stable_mask([db(c[-1] / c[0]) for c in channels])
    return [estimate_enl(c, stable) for c in channels], stable


# --------------------------------------------------------------------------- reference formula


def reference_omnibus(channels, enls, alpha=0.01):
    """Literal transcription of the brief's formulas, one block at a time (slow, for checking).

    Adds the Conradsen 2016 small-sample factor rho_j to the R_j test as well as to Q.
    """
    k = channels[0].shape[0]
    p_ch = len(channels)
    ny, nx = channels[0].shape[1:]
    p_out = np.full((ny, nx), np.nan)
    idx_out = np.full((ny, nx), -1, dtype=int)
    for y in range(ny):
        for x in range(nx):
            q_stat = 0.0
            r_stat = np.zeros(k + 1)
            for ch, n in zip(channels, enls):
                s = ch[:, y, x]
                S = np.cumsum(s)
                lnq = n * (k * np.log(k) + np.sum(np.log(s)) - k * np.log(S[-1]))
                rho = 1 - (k / n - 1 / (n * k)) / (6 * (k - 1))
                q_stat += -2 * rho * lnq
                for j in range(2, k + 1):
                    lnr = n * (
                        j * np.log(j)
                        - (j - 1) * np.log(j - 1)
                        + (j - 1) * np.log(S[j - 2])
                        + np.log(s[j - 1])
                        - j * np.log(S[j - 1])
                    )
                    rho_j = 1 - (1 + 1 / (j * (j - 1))) / (6 * n)
                    r_stat[j] += -2 * rho_j * lnr
            p = stats.chi2.sf(q_stat, p_ch * (k - 1))
            p_out[y, x] = p
            if p < alpha:
                for j in range(2, k + 1):
                    if stats.chi2.sf(r_stat[j], p_ch) < alpha:
                        idx_out[y, x] = j - 1
                        break
    return p_out, idx_out


@pytest.mark.parametrize("n_channels,k", [(1, 2), (1, 4), (2, 3), (2, 6)])
def test_omnibus_matches_reference_formula(n_channels, k):
    rng = np.random.default_rng(10 + k)
    shape = (6, 7)
    channels = [gamma_stack(rng, 12, k, shape) for _ in range(n_channels)]
    # make some blocks change so the change-index branch is exercised
    for c in channels:
        c[k // 2 :, :3, :] *= 0.2
    enls = [12.0, 7.5][:n_channels]
    p, idx = omnibus(channels, enls)
    p_ref, idx_ref = reference_omnibus(channels, enls)
    np.testing.assert_allclose(p, p_ref, rtol=1e-8, atol=1e-300)
    np.testing.assert_array_equal(idx, idx_ref)
    assert (idx_ref >= 0).any(), "fixture should contain detected changes"


# --------------------------------------------------------------------------- ENL


@pytest.mark.parametrize("n,T", [(60, 2), (60, 3), (60, 5), (60, 12), (20, 4), (500, 5)])
def test_enl_recovers_truth(n, T):
    rng = np.random.default_rng(100 + T)
    series = gamma_stack(rng, n, T)
    est = estimate_enl(series, np.ones(GRID, bool))
    assert abs(est / n - 1) <= 0.10, f"ENL {est:.1f} vs truth {n} (T={T})"


@pytest.mark.parametrize("n,T", [(20, 3), (60, 2), (60, 3), (60, 5)])
def test_enl_not_inflated_by_stable_selection(n, T):
    """Selecting 'stable' blocks by |delta| < 1 dB truncates the noise; ENL must not inherit that.

    The naive median over the selected blocks overstates n by 1.2x-2.2x in these cases, which
    multiplies the null false-alarm rate by 3-20x.
    """
    rng = np.random.default_rng(200 + n + T)
    series = gamma_stack(rng, n, T)
    stable = stable_mask([db(series[-1] / series[0])])
    assert stable.mean() < 0.99  # the window really does cut into the noise
    est = estimate_enl(series, stable)
    assert abs(est / n - 1) <= 0.10, f"ENL {est:.1f} vs truth {n}"


def test_enl_ignores_changed_blocks():
    rng = np.random.default_rng(3)
    n, T = 60, 5
    series = gamma_stack(rng, n, T)
    moved = rng.random(GRID) < 0.3
    series[2:, moved] *= 10 ** (-6 / 10)  # strong drops in 30% of blocks
    stable = stable_mask([db(series[-1] / series[0])])
    est = estimate_enl(series, stable)
    assert abs(est / n - 1) <= 0.10, f"ENL {est:.1f} vs truth {n}"


def test_enl_skips_invalid_blocks_and_clips():
    rng = np.random.default_rng(4)
    series = gamma_stack(rng, 60, 4)
    series[:, :10, :] = np.nan  # invalid rows
    series[1, 10:12, :] = 0.0  # non-positive values are invalid too
    est = estimate_enl(series, np.ones(GRID, bool))
    assert abs(est / 60 - 1) <= 0.10
    flat = np.ones((3, 20, 20))  # zero variance -> infinite ENL -> clipped
    assert estimate_enl(flat, np.ones((20, 20), bool)) == 10000.0
    wild = gamma_stack(rng, 0.2, 6, (50, 50))  # very heavy noise -> clipped at 1
    assert estimate_enl(wild, np.ones((50, 50), bool)) == 1.0


def test_enl_rejects_unusable_input():
    rng = np.random.default_rng(5)
    with pytest.raises(ValueError):
        estimate_enl(gamma_stack(rng, 60, 1, (10, 10)), np.ones((10, 10), bool))  # T < 2
    with pytest.raises(ValueError):
        estimate_enl(gamma_stack(rng, 60, 3, (10, 10)), np.zeros((10, 10), bool))  # no stable
    with pytest.raises(ValueError):
        estimate_enl(gamma_stack(rng, 60, 3, (10, 10)), np.ones((5, 5), bool))  # shape


# --------------------------------------------------------------------------- omnibus: null


@pytest.mark.parametrize("T", [2, 3, 6])
def test_null_false_alarm(T):
    """No change, 20,000 blocks, two bands (HH-like n=60, HV-like n=40), alpha = 0.01."""
    rng = np.random.default_rng(300 + T)
    channels = [gamma_stack(rng, 60, T), gamma_stack(rng, 40, T, mean=0.1)]

    p_true, idx_true = omnibus(channels, [60.0, 40.0])
    fa_true = np.mean(p_true < 0.01)
    assert 0.007 <= fa_true <= 0.013, f"FA with true ENL = {fa_true:.4f}"
    assert 0.04 <= np.mean(p_true < 0.05) <= 0.06
    assert np.mean(idx_true >= 0) <= fa_true  # a change date only where the omnibus fires

    enls, _ = pipeline_enls(channels)
    p_est, _ = omnibus(channels, enls)
    fa_est = np.mean(p_est < 0.01)
    assert fa_est <= 0.015, f"FA with estimated ENL = {fa_est:.4f} (ENLs {enls})"
    assert fa_est >= 0.005, f"test became far too conservative: {fa_est:.4f}"
    assert bh_fdr(p_est, q=0.05).mean() < 0.001  # complete null: BH rejects (almost) nothing


def test_omnibus_is_scale_invariant_per_block():
    """A constant per-block factor (e.g. the RTC area normalisation) must not change the test."""
    rng = np.random.default_rng(6)
    ch = gamma_stack(rng, 30, 5, (20, 20))
    factor = rng.uniform(0.01, 100.0, size=(20, 20))
    p1, i1 = omnibus([ch], [30.0])
    p2, i2 = omnibus([ch * factor], [30.0])
    np.testing.assert_allclose(p1, p2, rtol=1e-9)
    np.testing.assert_array_equal(i1, i2)


# --------------------------------------------------------------------------- omnibus: change


@pytest.mark.parametrize("n_channels,min_exact_date", [(1, 0.93), (2, 0.98)])
def test_detects_3db_step(n_channels, min_exact_date):
    """Half the blocks drop 3 dB from date index 2 of 4 (n = 60); full engine path.

    Detection is >= 99% either way. The exact date needs R_3 itself to fire: with one band its
    power at n = 60 is 0.93 (noncentral chi2), and R_2 false-fires at alpha = 0.01, so even
    with the true ENL ~95% of blocks get index 2 (the rest get 3, 1 or -1). Two bands (HH+HV,
    the NISAR case) put ~99% on index 2.
    """
    rng = np.random.default_rng(400 + n_channels)
    channels = [gamma_stack(rng, 60, 4) for _ in range(n_channels)]
    moved = np.zeros(GRID, bool)
    moved[:, : GRID[1] // 2] = True
    for c in channels:
        c[2:, moved] *= 10 ** (-3 / 10)

    enls, _ = pipeline_enls(channels)
    p, idx = omnibus(channels, enls)
    sig = bh_fdr(p, q=0.05)

    assert sig[moved].mean() >= 0.95, f"detected {sig[moved].mean():.3f}"
    exact = (sig & (idx == 2))[moved].mean()
    assert exact >= min_exact_date, f"change date index 2 for only {exact:.4f}"
    false_disc = (sig & ~moved).sum() / max(sig.sum(), 1)
    assert false_disc <= 0.05, f"false discovery proportion {false_disc:.4f}"


def test_change_idx_convention():
    """change_idx is the 0-based index of the first date after the change; -1 if none."""
    T = 6
    flat = np.ones((T, 1, 4))
    flat[3:, 0, 0] = 0.25  # change between dates 2 and 3 -> 3
    flat[1:, 0, 1] = 4.0  # change between dates 0 and 1 -> 1
    flat[5:, 0, 2] = 0.1  # change at the last date -> 5
    p, idx = omnibus([flat], [500.0])  # column 3 never changes
    assert idx.tolist() == [[3, 1, 5, -1]]
    assert p[0, 3] == pytest.approx(1.0)
    assert (p[0, :3] < 1e-10).all()

    two = np.ones((2, 1, 2))
    two[1, 0, 0] = 0.25
    p2, idx2 = omnibus([two], [500.0])  # k = 2: the step test equals the omnibus
    assert idx2.tolist() == [[1, -1]]
    assert p2[0, 0] < 1e-10 and p2[0, 1] == pytest.approx(1.0)


def test_omnibus_nan_blocks_without_warnings():
    rng = np.random.default_rng(7)
    a = gamma_stack(rng, 30, 4, (5, 6))
    b = gamma_stack(rng, 30, 4, (5, 6))
    a[2, 0, 0] = np.nan
    b[:, 1, 1] = np.nan
    a[0, 2, 2] = 0.0
    b[3, 3, 3] = -1.0
    a[1, 4, 4] = np.inf
    p, idx = omnibus([a, b], [30.0, 30.0])
    bad = [(0, 0), (1, 1), (2, 2), (3, 3), (4, 4)]
    for y, x in bad:
        assert np.isnan(p[y, x]) and idx[y, x] == -1
    good = np.ones((5, 6), bool)
    for y, x in bad:
        good[y, x] = False
    assert np.isfinite(p[good]).all()
    assert idx.dtype.kind == "i"


def test_omnibus_rejects_bad_input():
    rng = np.random.default_rng(8)
    a = gamma_stack(rng, 30, 4, (5, 5))
    with pytest.raises(ValueError):
        omnibus([a, a[:, :4]], [30.0, 30.0])  # shape mismatch
    with pytest.raises(ValueError):
        omnibus([a], [30.0, 30.0])  # one ENL per channel
    with pytest.raises(ValueError):
        omnibus([a[:1]], [30.0])  # need at least 2 dates
    with pytest.raises(ValueError):
        omnibus([a], [0.5])  # ENL below 1
    with pytest.raises(ValueError):
        omnibus([], [])


# --------------------------------------------------------------------------- BH-FDR


def test_bh_fdr_known_values():
    assert bh_fdr(np.array([0.001, 0.02, 0.5])).tolist() == [True, True, False]
    # step-up: the largest p passes its threshold, so every smaller p is rejected too
    assert bh_fdr(np.array([0.04, 0.04, 0.04])).tolist() == [True, True, True]
    assert bh_fdr(np.array([0.02, 0.03, 0.2, 0.3]), q=0.05).tolist() == [False] * 4
    # NaN blocks are never significant and do not count towards m
    assert bh_fdr(np.array([0.04, np.nan, np.nan])).tolist() == [True, False, False]
    assert bh_fdr(np.array([np.nan, np.nan])).tolist() == [False, False]


def test_bh_fdr_monotone():
    rng = np.random.default_rng(9)
    p = np.concatenate([rng.uniform(size=5000), rng.uniform(0, 1e-3, size=500)])
    p[::97] = np.nan
    p = p.reshape(50, 110)
    sig = bh_fdr(p, q=0.05)
    assert sig.shape == p.shape
    finite = np.isfinite(p)
    # monotone: anything with a p-value at or below a rejected one is rejected
    assert (p[finite & ~sig] > p[sig].max()).all()
    assert not sig[~finite].any()
    # a larger q never rejects fewer
    assert (bh_fdr(p, q=0.1) >= sig).all()
    with pytest.raises(ValueError):
        bh_fdr(p, q=0.0)


# --------------------------------------------------------------------------- min-effect gate


def test_min_effect_gate():
    """A highly significant 1 dB change is not 'changed'; 3 dB is."""
    rng = np.random.default_rng(11)
    n = 5000  # so precise that 1 dB is overwhelmingly significant
    series = gamma_stack(rng, n, 4, (20, 20))
    series[2:, :, :10] *= 10 ** (-1 / 10)
    series[2:, :, 10:] *= 10 ** (-3 / 10)
    p, _ = omnibus([series], [float(n)])
    assert bh_fdr(p).all()
    rel = db(series[2:].mean(0) / series[:2].mean(0))
    out = changed(p, rel)
    assert not out[:, :10].any()
    assert out[:, 10:].all()


def test_changed_handles_sign_nan_and_channels():
    p = np.array([1e-9, 1e-9, 1e-9, 1e-9, np.nan, 0.9])
    rel = np.array([2.5, -2.5, 1.9, np.nan, 5.0, 5.0])
    assert changed(p, rel).tolist() == [True, True, False, False, False, False]
    # several bands: the largest |relative change| decides
    hh = np.array([0.5, -0.5, np.nan, np.nan])
    hv = np.array([-3.0, 1.0, 2.2, np.nan])
    p4 = np.full(4, 1e-9)
    assert changed(p4, [hh, hv]).tolist() == [True, False, True, False]
    assert changed(p4, [hh, hv], min_db=0.4).tolist() == [True, True, True, False]


# --------------------------------------------------------------------------- stable / relative


def test_stable_mask_basic():
    # medians over the stable blocks are exactly 0, so re-centring leaves the window in place
    a = np.array([[0.0, 0.9, -0.9, 1.5], [np.nan, 0.1, -0.1, 0.0]])
    b = np.array([[0.2, -0.2, 0.0, 0.0], [0.0, 2.0, 0.1, -0.1]])
    assert stable_mask([a]).tolist() == [[True, True, True, False], [False, True, True, True]]
    assert stable_mask([a, b]).tolist() == [[True, True, True, False], [False, False, True, True]]
    assert stable_mask([a], thresh_db=0.5).tolist() == [
        [True, False, False, False],
        [False, True, True, True],
    ]


@pytest.mark.parametrize("shift", [0.5, 1.5])
def test_relative_delta_removes_shift(shift):
    """A scene-wide shift (moisture/calibration) is removed; real changes survive."""
    rng = np.random.default_rng(12)
    before = gamma_stack(rng, 60, 1)[0]
    after = gamma_stack(rng, 60, 1)[0] * 10 ** (shift / 10)
    moved = rng.random(GRID) < 0.2
    after[moved] *= 10 ** (-4 / 10)
    delta = db(after / before)

    stable = stable_mask([delta])
    rel = relative_delta(delta, stable)
    assert abs(np.median(rel[stable])) < 1e-9
    assert abs(np.median(rel[~moved])) < 0.05, f"residual shift {np.median(rel[~moved]):.3f} dB"
    assert abs(np.median(rel[moved]) + 4.0) < 0.1


def test_relative_delta_nan_and_errors():
    delta = np.array([[0.5, 0.7, np.nan], [0.6, 5.0, 0.4]])
    stable = np.array([[True, True, True], [True, False, True]])
    rel = relative_delta(delta, stable)
    np.testing.assert_allclose(rel[np.isfinite(rel)], delta[np.isfinite(delta)] - 0.55)
    assert np.isnan(rel[0, 2])
    with pytest.raises(ValueError):
        relative_delta(delta, np.zeros_like(stable))
