"""Tests for the block-level omnibus change detector (Conradsen et al. 2016) and its decisions.

Synthetic data are gamma-distributed block intensities, `rng.gamma(n, mean / n)`, i.e. the
distribution of an n-look intensity with the given mean. All RNG seeds are fixed so every
statistical assertion is deterministic. ENL / stable-mask tests live in test_detect_enl.py.
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
    """Literal transcription of the brief's per-band formulas, one block at a time (slow).

    Adds the Conradsen 2016 factor rho_j to R_j as well as rho to Q, and combines bands by
    Bonferroni on the smallest band p-value; the change date comes from that band.
    """
    k = channels[0].shape[0]
    ny, nx = channels[0].shape[1:]
    maps = [np.broadcast_to(np.asarray(e, dtype=float), (ny, nx)) for e in enls]
    p_out = np.full((ny, nx), np.nan)
    idx_out = np.full((ny, nx), -1, dtype=int)
    for y in range(ny):
        for x in range(nx):
            p_bands, step_bands = [], []
            for ch, enl in zip(channels, maps):
                n = enl[y, x]
                s = ch[:, y, x]
                S = np.cumsum(s)
                lnq = n * (k * np.log(k) + np.sum(np.log(s)) - k * np.log(S[-1]))
                rho = 1 - (k / n - 1 / (n * k)) / (6 * (k - 1))
                p_bands.append(stats.chi2.sf(-2 * rho * lnq, k - 1))
                steps = []
                for j in range(2, k + 1):
                    lnr = n * (
                        j * np.log(j)
                        - (j - 1) * np.log(j - 1)
                        + (j - 1) * np.log(S[j - 2])
                        + np.log(s[j - 1])
                        - j * np.log(S[j - 1])
                    )
                    rho_j = 1 - (1 + 1 / (j * (j - 1))) / (6 * n)
                    steps.append(stats.chi2.sf(-2 * rho_j * lnr, 1))
                step_bands.append(steps)
            best = int(np.argmin(p_bands))
            p = min(1.0, len(channels) * p_bands[best])
            p_out[y, x] = p
            if p < alpha:
                for j, pj in enumerate(step_bands[best], start=2):
                    if pj < alpha:
                        idx_out[y, x] = j - 1
                        break
    return p_out, idx_out


@pytest.mark.parametrize(
    "n_channels,k,enl_map",
    [(1, 2, False), (1, 4, False), (2, 3, False), (2, 6, False), (2, 4, True)],
)
def test_omnibus_matches_reference_formula(n_channels, k, enl_map):
    rng = np.random.default_rng(10 + k)
    shape = (6, 7)
    channels = [gamma_stack(rng, 12, k, shape) for _ in range(n_channels)]
    for c in channels:  # some blocks change, so the change-index branch is exercised
        c[k // 2 :, :3, :] *= 0.2
    channels[-1][k // 2 :, 3, :] *= 0.4  # and some change in one band only
    enls = [12.0, 7.5][:n_channels]
    if enl_map:
        enls = [rng.uniform(5, 50, size=shape), rng.uniform(5, 50, size=(1, 7))]
    p, idx = omnibus(channels, enls)
    p_ref, idx_ref = reference_omnibus(channels, enls)
    np.testing.assert_allclose(p, p_ref, rtol=1e-8, atol=1e-300)
    np.testing.assert_array_equal(idx, idx_ref)
    assert (idx_ref >= 0).any(), "fixture should contain detected changes"


def test_bands_combine_by_bonferroni_min():
    rng = np.random.default_rng(18)
    hh = gamma_stack(rng, 30, 4, (40, 50))
    hv = gamma_stack(rng, 20, 4, (40, 50))
    hv[2:, :20] *= 0.5
    p_hh, i_hh = omnibus([hh], [30.0])
    p_hv, i_hv = omnibus([hv], [20.0])
    p, idx = omnibus([hh, hv], [30.0, 20.0])
    np.testing.assert_allclose(p, np.minimum(1.0, 2 * np.minimum(p_hh, p_hv)), rtol=1e-12)
    fired = p < 0.01
    from_band = np.where(p_hv < p_hh, i_hv, i_hh)  # ties go to the first band, like argmin
    np.testing.assert_array_equal(idx[fired], from_band[fired])
    assert (idx[~fired] == -1).all()


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

    enls, stable = pipeline_enls(channels)
    p_est, _ = omnibus(channels, enls, stable=stable)
    fa_est = np.mean(p_est < 0.01)
    assert fa_est <= 0.015, f"FA with estimated ENL = {fa_est:.4f} (ENLs {enls})"
    assert fa_est >= 0.005, f"test became far too conservative: {fa_est:.4f}"
    assert bh_fdr(p_est, q=0.05).mean() < 0.001  # complete null: BH rejects (almost) nothing


@pytest.mark.parametrize("T", [2, 6])
def test_null_false_alarm_shared_variation(T):
    """Moisture/phenology move HH and HV together: 0.4 dB per-block, per-date shared factor.

    The summed two-band statistic gave 2.6-2.8% false alarms here; Bonferroni stays nominal.
    """
    rng = np.random.default_rng(11)
    common = 10 ** (rng.normal(0, 0.4, size=(T, *GRID)) / 10)
    channels = [gamma_stack(rng, 300, T) * common, gamma_stack(rng, 300, T, mean=0.1) * common]
    enls, stable = pipeline_enls(channels)
    fa = np.mean(omnibus(channels, enls, stable=stable)[0] < 0.01)
    assert 0.005 <= fa <= 0.015, f"two-band FA {fa:.4f}"


@pytest.mark.parametrize("T,shifted_dates", [(2, [1]), (3, [2]), (6, [3, 4, 5])])
def test_scene_shift_null_end_to_end(T, shifted_dates):
    """A +1.5 dB moisture/calibration shift with no real change is not 'changed'.

    The ENL is estimated on date-normalised data; testing raw intensities made 3.2-4.4% of
    blocks 'changed' here. With the same normalisation before the test: 0.
    """
    rng = np.random.default_rng(900 + T)
    channels = [gamma_stack(rng, 60, T), gamma_stack(rng, 40, T, mean=0.1)]
    for c in channels:
        c[shifted_dates] *= 10 ** (1.5 / 10)
    deltas = [db(c[-1] / c[0]) for c in channels]
    stable = stable_mask(deltas)
    enls = [estimate_enl(c, stable) for c in channels]
    p, _ = omnibus(channels, enls, stable=stable)
    out = changed(p, [relative_delta(d, stable) for d in deltas])
    assert out.mean() <= 0.015, f"changed {out.mean():.4f}"
    assert out.mean() <= 0.001  # measured 0.0000


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


@pytest.mark.parametrize("n_channels,min_exact_date", [(1, 0.93), (2, 0.95)])
def test_detects_3db_step(n_channels, min_exact_date):
    """Half the blocks drop 3 dB from date index 2 of 4 (n = 60); full engine path.

    Detection is >= 99% either way. The exact date needs R_3 of one band to fire (the band
    with the smallest p): its power at n = 60 is ~0.93-0.95 (noncentral chi2(1), lambda ~
    16.5-17.5), and R_2 false-fires at alpha = 0.01. Measured: one band 0.947, two bands
    0.978 (picking the stronger band helps); the true ENL gives the same.
    """
    rng = np.random.default_rng(400 + n_channels)
    channels = [gamma_stack(rng, 60, 4) for _ in range(n_channels)]
    moved = np.zeros(GRID, bool)
    moved[:, : GRID[1] // 2] = True
    for c in channels:
        c[2:, moved] *= 10 ** (-3 / 10)

    enls, stable = pipeline_enls(channels)
    p, idx = omnibus(channels, enls, stable=stable)
    sig = bh_fdr(p, q=0.05)

    assert sig[moved].mean() >= 0.99, f"detected {sig[moved].mean():.3f}"
    exact = (sig & (idx == 2))[moved].mean()
    assert exact >= min_exact_date, f"change date index 2 for only {exact:.4f}"
    false_disc = (sig & ~moved).sum() / max(sig.sum(), 1)
    assert false_disc <= 0.05, f"false discovery proportion {false_disc:.4f}"


def test_change_idx_convention():
    """change_idx is the 0-based index of the first date after the change; -1 if none."""
    flat = np.ones((6, 1, 4))
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

    hh = np.ones((5, 1, 1))
    hv = np.ones((5, 1, 1))
    hh[1:] = 0.8  # weak change at index 1 in HH
    hv[3:] = 0.1  # strong change at index 3 in HV: the date comes from HV
    assert omnibus([hh, hv], [500.0, 500.0])[1].tolist() == [[3]]


@pytest.mark.parametrize("T", [3, 6])
def test_enl_map_two_strata(T):
    """Half the box at ENL 20 (e.g. crops), half at 200 (forest); no change.

    One scene-wide ENL floods the low-ENL half with false alarms; a per-stratum ENL map,
    each estimated on its own stratum, keeps both nominal.
    """
    rng = np.random.default_rng(500 + T)
    low = np.zeros(GRID, bool)
    low[:, : GRID[1] // 2] = True
    enl_true = np.where(low, 20.0, 200.0)
    series = rng.gamma(enl_true, 1.0 / enl_true, size=(T, *GRID))
    stable = stable_mask([db(series[-1] / series[0])])

    enl_map = np.empty(GRID)
    for stratum in (low, ~low):
        enl_map[stratum] = estimate_enl(np.where(stratum, series, np.nan), stable & stratum)
    p_map, _ = omnibus([series], [enl_map])
    for stratum in (low, ~low):
        assert np.mean(p_map[stratum] < 0.01) <= 0.015

    p_one, _ = omnibus([series], [estimate_enl(series, stable)])
    assert np.mean(p_one[low] < 0.01) > 0.1


def test_enl_map_matches_scalar_and_marks_nan_invalid():
    rng = np.random.default_rng(19)
    a = gamma_stack(rng, 30, 4, (5, 6))
    b = gamma_stack(rng, 30, 4, (5, 6))
    p_scalar, i_scalar = omnibus([a, b], [30.0, 25.0])
    p_map, i_map = omnibus([a, b], [np.full((5, 6), 30.0), np.full((1, 6), 25.0)])
    np.testing.assert_array_equal(p_scalar, p_map)
    np.testing.assert_array_equal(i_scalar, i_map)
    holes = np.full((5, 6), 30.0)
    holes[2, 3] = np.nan
    p_h, i_h = omnibus([a, b], [holes, 25.0])
    assert np.isnan(p_h[2, 3]) and i_h[2, 3] == -1
    assert np.isfinite(p_h).sum() == 29


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
    good = np.ones((5, 6), bool)
    for y, x in [(0, 0), (1, 1), (2, 2), (3, 3), (4, 4)]:
        assert np.isnan(p[y, x]) and idx[y, x] == -1
        good[y, x] = False
    assert np.isfinite(p[good]).all()
    assert idx.dtype.kind == "i"


def test_omnibus_rejects_bad_input():
    rng = np.random.default_rng(8)
    a = gamma_stack(rng, 30, 4, (5, 5))
    for channels, enls in [
        ([a, a[:, :4]], [30.0, 30.0]),  # shape mismatch
        ([a], [30.0, 30.0]),  # one ENL per channel
        ([a[:1]], [30.0]),  # need at least 2 dates
        ([a], [0.5]),  # ENL below 1
        ([a], [np.nan]),  # scalar ENL must be finite
        ([a], [np.full((5, 5), 0.5)]),  # map value below 1
        ([a], [np.ones((3, 3)) * 30]),  # map does not broadcast to the grid
        ([], []),
    ]:
        with pytest.raises(ValueError):
            omnibus(channels, enls)


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
    assert (p[finite & ~sig] > p[sig].max()).all()  # monotone in p
    assert not sig[~finite].any()
    assert (bh_fdr(p, q=0.1) >= sig).all()  # a larger q never rejects fewer
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
    out = changed(p, db(series[2:].mean(0) / series[:2].mean(0)))
    assert not out[:, :10].any()
    assert out[:, 10:].all()


def test_changed_handles_sign_nan_and_channels():
    p = np.array([1e-9, 1e-9, 1e-9, 1e-9, np.nan, 0.9])
    rel = np.array([2.5, -2.5, 1.9, np.nan, 5.0, 5.0])
    assert changed(p, rel).tolist() == [True, True, False, False, False, False]
    # several bands: any band past the threshold counts
    hh = np.array([0.5, -0.5, np.nan, np.nan])
    hv = np.array([-3.0, 1.0, 2.2, np.nan])
    p4 = np.full(4, 1e-9)
    assert changed(p4, [hh, hv]).tolist() == [True, False, True, False]
    assert changed(p4, [hh, hv], min_db=0.4).tolist() == [True, True, True, False]


def test_changed_per_band_min_db():
    p = np.full(3, 1e-9)
    hh = np.array([2.5, 1.0, 0.5])
    hv = np.array([0.5, 3.5, 2.5])
    assert changed(p, [hh, hv], min_db=(2.0, 3.0)).tolist() == [True, True, False]
    assert changed(p, np.stack([hh, hv]), min_db=[3.0, 2.0]).tolist() == [False, True, True]
    assert changed(p, [hh, hv], min_db=2.0).tolist() == [True, True, True]
    assert changed(p, hh, min_db=[2.0]).tolist() == [True, False, False]
    with pytest.raises(ValueError):
        changed(p, [hh, hv], min_db=(2.0, 2.0, 2.0))
