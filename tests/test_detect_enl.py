"""Tests for the stable mask, the relative change and the empirical ENL of block means.

Synthetic data are gamma-distributed block intensities, `rng.gamma(n, mean / n)`. All RNG
seeds are fixed so every statistical assertion is deterministic.
"""

import numpy as np
import pytest

from sarstellar import detect
from sarstellar.detect import (
    ENL_MAX,
    MAX_SHIFT_DB,
    NoStableBlocks,
    TooFewBlocks,
    changed,
    estimate_enl,
    normalise_dates,
    omnibus,
    relative_delta,
    stable_mask,
)

pytestmark = pytest.mark.filterwarnings("error")

GRID = (100, 200)  # 20,000 blocks


def gamma_stack(rng, n, T, shape=GRID, mean=1.0):
    return rng.gamma(n, mean / n, size=(T, *shape))


def db(x):
    return 10.0 * np.log10(x)


# --------------------------------------------------------------------------- ENL


@pytest.mark.parametrize("n,T", [(60, 2), (60, 3), (60, 5), (60, 12), (20, 4), (500, 5)])
def test_enl_recovers_truth(n, T):
    rng = np.random.default_rng(100 + T)
    est = estimate_enl(gamma_stack(rng, n, T), np.ones(GRID, bool))
    assert abs(est / n - 1) <= 0.10, f"ENL {est:.1f} vs truth {n} (T={T})"


@pytest.mark.parametrize("n,T", [(20, 3), (60, 2), (60, 3), (60, 5)])
def test_enl_not_inflated_by_stable_selection(n, T):
    """A |delta| < 1 dB stable set truncates the noise; the seed alone overstates n 1.2-2.2x."""
    rng = np.random.default_rng(200 + n + T)
    series = gamma_stack(rng, n, T)
    stable = stable_mask([db(series[-1] / series[0])])
    assert stable.mean() < 0.99  # the window really does cut into the noise
    est = estimate_enl(series, stable)
    assert abs(est / n - 1) <= 0.10, f"ENL {est:.1f} vs truth {n}"


def test_enl_ignores_changed_blocks():
    rng = np.random.default_rng(3)
    series = gamma_stack(rng, 60, 5)
    moved = rng.random(GRID) < 0.3
    series[2:, moved] *= 10 ** (-6 / 10)
    est = estimate_enl(series, stable_mask([db(series[-1] / series[0])]))
    assert abs(est / 60 - 1) <= 0.10


@pytest.mark.parametrize("severe_frac", [0.1, 0.2])
@pytest.mark.parametrize("T,t0", [(2, 1), (3, 1), (3, 2)])
@pytest.mark.parametrize("n,moderate_db", [(20, -4.0), (40, -2.5)])
def test_enl_majority_moderate_change(n, moderate_db, T, t0, severe_frac):
    """Box drawn around a burn scar: 60% of blocks with a moderate HV drop, 10-20% at -6 dB.

    The trimmed refinement alone collapses here (HV ENL 1-13). The floor at corrected seed /
    1.25 stops the collapse without overstating n, so unchanged blocks stay clean (<= 0.03)
    in every cell, and -6 dB blocks are detected (>= 0.93) wherever the unchanged population
    is separable: T = 3, or n = 40 at T = 2. Known limits (measured, see the A4 report):
    - n = 20, T = 2: 0.22-0.53 detected. The moderate drop is 2.9 sigma from 0, the seed
      reads ~0.55x the truth, and even the true ENL gives only 0.93-0.94 here.
    - offset at the 1.5 dB cap (n = 40, 20% severe, t0 = 1): unchanged and moderate blocks
      merge, the date normalisation absorbs 1.5 dB, and even the true ENL turns 10-12% of
      unchanged blocks "changed"; the engine stays clean but detects less.
    The round-1 version passed 0.95 everywhere only because its ENL was overstated ~1.5x.
    """
    rng = np.random.default_rng(10 * n + T + t0)
    hh = gamma_stack(rng, n, T)
    hv = gamma_stack(rng, n, T, mean=0.1)
    r = rng.random(GRID)
    moderate = r < 0.6
    severe = (r >= 0.6) & (r < 0.6 + severe_frac)
    hv[t0:, moderate] *= 10 ** (moderate_db / 10)
    hv[t0:, severe] *= 10 ** (-6 / 10)
    channels = [hh, hv]
    deltas = [db(c[t0:].mean(0) / c[:t0].mean(0)) for c in channels]

    stable = stable_mask(deltas)
    rel = [relative_delta(d, stable) for d in deltas]
    enls = [estimate_enl(c, stable) for c in channels]
    out = changed(omnibus(channels, enls, stable=stable)[0], rel)

    unchanged = ~(moderate | severe)
    assert out[unchanged].mean() <= 0.03, f"unchanged 'changed' {out[unchanged].mean():.3f}"
    seed = estimate_enl(hv, stable, clip_alpha=None)
    assert enls[1] >= seed / detect.ENL_SEED_RATIO * (1 - 1e-12)
    assert enls[1] <= 1.25 * n, f"HV ENL {enls[1]:.1f} overstated"
    capped = abs(np.median(deltas[1][stable])) >= MAX_SHIFT_DB - 0.01
    if not capped and (T == 3 or n == 40):
        assert out[severe].mean() >= 0.93, f"-6 dB detected {out[severe].mean():.3f}"


@pytest.mark.parametrize("T", [2, 3])
@pytest.mark.parametrize("n", [10, 15, 20, 30])
def test_null_low_enl(n, T):
    """Complete null on low-ENL ground (the Sentinel-1 two-date view), full engine path.

    The old floor (uncorrected +-1 dB seed / 2.5) pinned the T = 2 ENL near 30 whatever the
    truth: 20% of blocks 'changed' at n = 10, 4% at n = 15.
    """
    rng = np.random.default_rng(600 + 10 * n + T)
    channels = [gamma_stack(rng, n, T), gamma_stack(rng, n, T, mean=0.1)]
    deltas = [db(c[-1] / c[0]) for c in channels]
    stable = stable_mask(deltas)
    enls = [estimate_enl(c, stable) for c in channels]
    p, _ = omnibus(channels, enls, stable=stable)
    out = changed(p, [relative_delta(d, stable) for d in deltas])
    assert out.mean() <= 0.015, f"changed {out.mean():.4f}"
    assert np.mean(p < 0.01) <= 0.015, f"p < 0.01 on {np.mean(p < 0.01):.4f}"
    assert max(enls) <= 1.2 * n, f"ENLs {enls}"


@pytest.mark.parametrize("n", [10, 15, 20])
def test_burn_scar_box_unchanged_blocks(n):
    """T = 2; 60% of blocks at HV -4 dB, 20% at -6 dB, HH unchanged: the unchanged 20% stay clean.

    With the old floor 11-29% of them were 'changed'. (At n = 40 even the true ENL gives
    ~0.04 here: BH at 80% prevalence plus the 2 dB gate on 1 dB noise, not the estimator.)
    """
    rng = np.random.default_rng(800 + n)
    hh = gamma_stack(rng, n, 2)
    hv = gamma_stack(rng, n, 2, mean=0.1)
    r = rng.random(GRID)
    moderate = r < 0.6
    severe = (r >= 0.6) & (r < 0.8)
    hv[1:, moderate] *= 10 ** (-4 / 10)
    hv[1:, severe] *= 10 ** (-6 / 10)
    channels = [hh, hv]
    deltas = [db(c[1] / c[0]) for c in channels]
    stable = stable_mask(deltas)
    enls = [estimate_enl(c, stable) for c in channels]
    p, _ = omnibus(channels, enls, stable=stable)
    out = changed(p, [relative_delta(d, stable) for d in deltas])
    unchanged = ~(moderate | severe)
    assert out[unchanged].mean() <= 0.03, f"unchanged 'changed' {out[unchanged].mean():.3f}"


def test_enl_removes_scene_shift():
    """A +1.5 dB scene-wide shift from date 2 is not noise: the ENL stays near the truth."""
    rng = np.random.default_rng(13)
    series = gamma_stack(rng, 60, 4)
    series[2:] *= 10 ** (1.5 / 10)
    for stable in (np.ones(GRID, bool), stable_mask([db(series[-1] / series[0])])):
        est = estimate_enl(series, stable)
        assert abs(est / 60 - 1) <= 0.10, f"ENL {est:.1f}"


def test_enl_excludes_zero_variance_blocks():
    """Constant blocks (fill values, quantised data) used to send the ENL to its maximum."""
    rng = np.random.default_rng(14)
    series = gamma_stack(rng, 60, 4)
    flat = rng.random(GRID) < 0.6
    series[:, flat] = 0.05
    est = estimate_enl(series, np.ones(GRID, bool))
    assert abs(est / 60 - 1) <= 0.10, f"ENL {est:.1f}"
    with pytest.raises(TooFewBlocks):
        estimate_enl(np.ones((3, 20, 20)), np.ones((20, 20), bool))


def test_enl_too_few_blocks():
    rng = np.random.default_rng(15)
    with pytest.raises(TooFewBlocks):
        estimate_enl(gamma_stack(rng, 60, 3, (10, 10)), np.ones((10, 10), bool))  # 100 blocks
    assert estimate_enl(gamma_stack(rng, 60, 3, (10, 20)), np.ones((10, 20), bool)) > 1
    small = gamma_stack(rng, 60, 3, (10, 10))
    assert estimate_enl(small, np.ones((10, 10), bool), min_blocks=50) > 1
    few_stable = np.zeros(GRID, bool)
    few_stable[0, :150] = True  # plenty of valid blocks, only 150 stable
    with pytest.raises(TooFewBlocks):
        estimate_enl(gamma_stack(rng, 60, 3), few_stable)
    assert issubclass(TooFewBlocks, ValueError)


def test_no_stable_blocks():
    rng = np.random.default_rng(16)
    with pytest.raises(NoStableBlocks):
        estimate_enl(gamma_stack(rng, 60, 3), np.zeros(GRID, bool))
    with pytest.raises(NoStableBlocks):
        relative_delta(np.zeros(GRID), np.zeros(GRID, bool))
    assert issubclass(NoStableBlocks, ValueError)


def test_enl_clips_to_range():
    rng = np.random.default_rng(17)
    assert ENL_MAX == 1000.0
    precise = gamma_stack(rng, 1e6, 4, (20, 20))
    assert estimate_enl(precise, np.ones((20, 20), bool)) == ENL_MAX
    wild = gamma_stack(rng, 0.2, 6, (50, 50))
    assert estimate_enl(wild, np.ones((50, 50), bool)) == 1.0


def test_enl_skips_invalid_blocks():
    rng = np.random.default_rng(4)
    series = gamma_stack(rng, 60, 4)
    series[:, :10, :] = np.nan
    series[1, 10:12, :] = 0.0  # non-positive values are invalid too
    assert abs(estimate_enl(series, np.ones(GRID, bool)) / 60 - 1) <= 0.10


def test_enl_rejects_bad_input():
    rng = np.random.default_rng(5)
    ok = np.ones(GRID, bool)
    with pytest.raises(ValueError):
        estimate_enl(gamma_stack(rng, 60, 1), ok)  # T < 2
    with pytest.raises(ValueError):
        estimate_enl(gamma_stack(rng, 60, 3), np.ones((5, 5), bool))  # grid mismatch
    with pytest.raises(ValueError):
        estimate_enl(gamma_stack(rng, 60, 3), ok, clip_alpha=1.5)
    with pytest.raises(ValueError):
        estimate_enl(gamma_stack(rng, 60, 3), ok, min_blocks=0)


# --------------------------------------------------------------------------- corrected seed


def test_seed_map_is_cached_fast_and_monotone():
    import time

    detect._seed_map.cache_clear()
    t0 = time.perf_counter()
    log_grid, log_expected = detect._seed_map(25, 3.0)
    assert time.perf_counter() - t0 < 1.0  # the longest stack expected; T = 2 is ~0.03 s
    assert (np.diff(log_expected) > 0).all()
    assert detect._seed_map(25, 3.0) is detect._seed_map(25, 3.0)  # cached per (T, window)
    # above n ~ 15 the one-sided window barely truncates: the map is close to the identity
    big = log_grid > np.log(15)
    np.testing.assert_allclose(log_expected[big], log_grid[big], atol=0.08)


@pytest.mark.parametrize("T", [2, 3, 6])
@pytest.mark.parametrize("n", [15, 20, 30, 60, 200])
def test_corrected_seed_recovers_truth(n, T):
    """The seed alone (clip_alpha=None) is unbiased under no change, whatever the window."""
    rng = np.random.default_rng(50 + n + T)
    series = gamma_stack(rng, n, T)
    stable = stable_mask([db(series[-1] / series[0])])
    seed = estimate_enl(series, stable, clip_alpha=None)
    assert abs(seed / n - 1) <= 0.10, f"corrected seed {seed:.1f} vs truth {n}"


def test_normalise_dates():
    rng = np.random.default_rng(22)
    series = gamma_stack(rng, 60, 4, (40, 50))
    shifted = series * (10 ** (np.array([0.0, 0.5, -0.3, 1.2]) / 10))[:, None, None]
    shifted[:, 0, :3] = np.nan
    stable = np.ones((40, 50), bool)
    out = normalise_dates(shifted, stable)
    ratio = db(out[:, 1:, :] / series[:, 1:, :]).reshape(4, -1)
    assert np.ptp(np.median(ratio, axis=1)) < 0.1  # 0.5-1.5 dB per-date shifts are gone
    assert np.isnan(out[:, 0, :3]).all()  # invalid blocks pass through
    np.testing.assert_allclose(normalise_dates(out, stable), out, rtol=1e-12)  # idempotent
    p_norm, i_norm = omnibus([out], [60.0])
    p_kw, i_kw = omnibus([shifted], [60.0], stable=stable)
    np.testing.assert_array_equal(p_norm, p_kw)
    np.testing.assert_array_equal(i_norm, i_kw)
    with pytest.raises(NoStableBlocks):
        normalise_dates(shifted, np.zeros((40, 50), bool))


# --------------------------------------------------------------------------- stable / relative


def test_stable_mask_basic():
    # the stable blocks are centred on 0, so the offset stays at ~0
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


@pytest.mark.parametrize("seed", [0, 4, 5, 8])
def test_stable_mask_majority_moderate_change(seed):
    """70% of blocks at HV -2.5 dB / HH -1.25 dB (T = 2): the offset must not follow them.

    The median re-centring walked to about -2.47 dB on 12 of 16 seeds (4, 5 and 8 among
    them), which erased the change. The mode-seeking offset stayed within 0.34 dB on all 16.
    """
    rng = np.random.default_rng(seed)
    hh = gamma_stack(rng, 60, 2)
    hv = gamma_stack(rng, 40, 2)
    moved = rng.random(GRID) < 0.7
    hv[1, moved] *= 10 ** (-2.5 / 10)
    hh[1, moved] *= 10 ** (-1.25 / 10)
    deltas = [db(hh[1] / hh[0]), db(hv[1] / hv[0])]
    stable = stable_mask(deltas)
    assert abs(np.median(deltas[1][stable])) <= MAX_SHIFT_DB
    rel = relative_delta(deltas[1], stable)
    assert np.median(rel[moved]) <= -1.0, f"changed blocks at {np.median(rel[moved]):.2f} dB"


@pytest.mark.parametrize("frac,mag", [(0.8, -2.5), (0.7, -2.0), (1.0, -2.0), (1.0, 3.0)])
def test_stable_mask_offset_never_exceeds_cap(frac, mag):
    """Where no unchanged mode is separable, the absorbed offset is still at most 1.5 dB."""
    rng = np.random.default_rng(21)
    hh = gamma_stack(rng, 60, 2)
    hv = gamma_stack(rng, 40, 2)
    moved = rng.random(GRID) < frac
    hv[1, moved] *= 10 ** (mag / 10)
    hh[1, moved] *= 10 ** (mag / 20)
    deltas = [db(hh[1] / hh[0]), db(hv[1] / hv[0])]
    stable = stable_mask(deltas)
    assert stable.any()
    for d in deltas:
        assert abs(np.median(d[stable])) <= MAX_SHIFT_DB + 1e-9


def test_relative_delta_nan_and_errors():
    delta = np.array([[0.5, 0.7, np.nan], [0.6, 5.0, 0.4]])
    stable = np.array([[True, True, True], [True, False, True]])
    rel = relative_delta(delta, stable)
    np.testing.assert_allclose(rel[np.isfinite(rel)], delta[np.isfinite(delta)] - 0.55)
    assert np.isnan(rel[0, 2])
    with pytest.raises(ValueError):
        relative_delta(delta, np.ones((2, 2), bool))
