"""Block-level change detection for SAR intensity stacks.

The statistical core of SARstellar:

1. ``stable_mask`` / ``relative_delta``: find blocks that did not change and remove the
   scene-wide shift (moisture, calibration) from the per-block change in dB.
2. ``estimate_enl``: the equivalent number of looks (ENL) of the *block means*, estimated from
   the data. It absorbs residual speckle and natural date-to-date variability, so it is not
   capped by the per-pixel ``numberOfLooks``.
3. ``omnibus``: the sequential omnibus likelihood-ratio test of Conradsen et al. (2016) per
   band, combined across bands by Bonferroni on the smallest band p-value (valid however the
   bands co-vary): one p-value per block plus the date of the first change.
4. ``bh_fdr`` / ``changed``: Benjamini-Hochberg FDR across the box, then a minimum-effect
   gate on the relative change.

All inputs are LINEAR intensities of 1-ha block means, one array of shape [T, ny, nx] per
band, NaN where a block is invalid. A block is valid only if every band is finite and > 0 on
every date; invalid blocks get p = NaN and change_idx = -1, with no numpy warnings.

The engine path, per sensor (bands = HH, HV or VV, VH):

    stable = stable_mask(deltas_db)                     # one delta per band, in dB
    rel = [relative_delta(d, stable) for d in deltas_db]
    enls = [estimate_enl(s, stable) for s in bands]     # normalises dates internally
    p, change_idx = omnibus(bands, enls, stable=stable)  # normalises dates the same way
    is_changed = changed(p, rel)

Both the ENL and the test must see date-normalised data (``normalise_dates``); otherwise a
moisture or calibration shift reads as change in every block.

Reference: K. Conradsen, A. A. Nielsen, H. Skriver, "Determining the points of change in time
series of polarimetric SAR data", IEEE TGRS 54(5):3007-3024, 2016,
doi:10.1109/TGRS.2015.2510160. For one intensity band (p = 1 in the paper) the complex
Wishart model reduces to Gamma(shape = n, scale = mean / n).
"""

from __future__ import annotations

import functools
from collections.abc import Sequence

import numpy as np
from scipy import special, stats

__all__ = [
    "ALPHA",
    "ENL_MAX",
    "ENL_MIN",
    "MAX_SHIFT_DB",
    "MIN_BLOCKS",
    "NoStableBlocks",
    "TooFewBlocks",
    "bh_fdr",
    "changed",
    "estimate_enl",
    "normalise_dates",
    "omnibus",
    "relative_delta",
    "stable_mask",
]

ALPHA = 0.01  # level of the omnibus test and of each change-date test R_j
ENL_MIN = 1.0
ENL_MAX = 1000.0  # 1-ha means across dates carry natural variability; more is not physical
ENL_CLIP_ALPHA = 0.2  # null-calibrated trimming level used to refine the ENL
ENL_SEED_RATIO = 1.25  # ENL >= corrected seed / ratio; never binds on a null scene (A4 report)
SEED_WINDOW_DB = 3.0  # one-sided last-vs-first delta window for the ENL seed
MIN_BLOCKS = 200  # fewer usable blocks give an ENL too noisy to control false alarms
MAX_SHIFT_DB = 1.5  # largest scene-wide shift the spikes saw; the offset never exceeds it
MODE_BANDWIDTH_DB = 0.3  # kernel width for locating the unchanged population
_MAX_ITER = 500
_SEED_MC_BLOCKS = 8000  # simulated blocks per grid point of the seed map
_SEED_MC_GRID = np.geomspace(1.0, 2.0 * ENL_MAX, 36)  # true ENLs of the seed map


class NoStableBlocks(ValueError):
    """No usable stable block: everything in the box changed, so there is no reference."""


class TooFewBlocks(ValueError):
    """Too few usable blocks for a reliable ENL estimate (the box is too small)."""


# --------------------------------------------------------------------------- helpers


def _valid_blocks(channels: Sequence[np.ndarray]) -> np.ndarray:
    """[ny, nx] bool: every band finite and > 0 on every date (NaN compares False, no warning)."""
    ok = [np.all(np.isfinite(c) & (c > 0), axis=0) for c in channels]
    return np.logical_and.reduce(ok)


def _delta_slices(deltas_db) -> list[np.ndarray]:
    """Flatten a list of [..., ny, nx] delta arrays into a list of [ny, nx] float arrays."""
    arrays = [deltas_db] if isinstance(deltas_db, np.ndarray) else list(deltas_db)
    if not arrays:
        raise ValueError("stable_mask needs at least one delta array")
    arrays = [np.asarray(a, dtype=float) for a in arrays]
    if arrays[0].ndim < 2:
        raise ValueError("delta arrays must be at least 2-D [ny, nx]")
    grid = arrays[0].shape[-2:]
    slices: list[np.ndarray] = []
    for a in arrays:
        if a.ndim < 2 or a.shape[-2:] != grid:
            raise ValueError(f"delta arrays must share the grid {grid}, got {a.shape}")
        slices.extend(a.reshape(-1, *grid))
    return slices


def _nearest_mode(points: np.ndarray, bandwidth: float, cap: float) -> np.ndarray:
    """Gaussian mean-shift from 0 dB in the joint delta space; the centre stays within +-cap."""
    centre = np.zeros(points.shape[1])
    for _ in range(_MAX_ITER):
        w = np.exp(-0.5 * np.sum(((points - centre) / bandwidth) ** 2, axis=1))
        total = w.sum()
        if not total > 0:  # nothing within reach of the current centre
            break
        new = np.clip(w @ points / total, -cap, cap)
        done = np.max(np.abs(new - centre)) < 1e-4
        centre = new
        if done:
            break
    return centre


def _max_abs_median(deltas: list[np.ndarray], mask: np.ndarray) -> float:
    if not mask.any():
        return np.inf
    return max(abs(float(np.median(d[mask]))) for d in deltas)


def _enl_map(enl, grid: tuple[int, ...]) -> np.ndarray:
    """One band's ENL as a [ny, nx] map: a float, or an array broadcast to the grid."""
    arr = np.asarray(enl, dtype=float)
    if arr.ndim == 0:
        if not (np.isfinite(arr) and arr >= ENL_MIN):
            raise ValueError(f"ENL must be finite and >= {ENL_MIN}, got {float(arr)}")
        return np.full(grid, float(arr))
    try:
        arr = np.broadcast_to(arr, grid)
    except ValueError:
        raise ValueError(f"ENL map {arr.shape} does not broadcast to the grid {grid}") from None
    finite = np.isfinite(arr)
    if np.any(arr[finite] < ENL_MIN):
        raise ValueError(f"ENL map values must be >= {ENL_MIN} (NaN marks a block invalid)")
    return arr


# --------------------------------------------------------------------------- stable / relative


def stable_mask(
    deltas_db,
    thresh_db: float = 1.0,
    max_shift_db: float = MAX_SHIFT_DB,
    bandwidth_db: float = MODE_BANDWIDTH_DB,
) -> np.ndarray:
    """Blocks whose change is small in every band.

    ``deltas_db``: per-band changes in dB, each [ny, nx] (extra leading axes count as one
    delta per slice). Stable = every delta finite and within ``thresh_db`` of the scene offset:
    the joint delta-density mode nearest 0 dB (Gaussian mean-shift, ``bandwidth_db`` kernel,
    from 0, clamped to +-``max_shift_db``), with the window then pulled back towards 0 until
    its median (what ``relative_delta`` subtracts) is within the cap. A scene-wide shift up to
    the cap is removed. A majority change stays out of the reference only if it forms its own
    mode (n ~ 40-60, T = 2: >= 3 dB in one band, or HV -2.5 / HH -1.25 dB on <= ~70% of
    blocks); closer ones are indistinguishable from a shift and up to the cap is absorbed.
    """
    if not thresh_db > 0:
        raise ValueError(f"thresh_db must be > 0, got {thresh_db}")
    if not max_shift_db >= 0:
        raise ValueError(f"max_shift_db must be >= 0, got {max_shift_db}")
    if not bandwidth_db > 0:
        raise ValueError(f"bandwidth_db must be > 0, got {bandwidth_db}")
    slices = _delta_slices(deltas_db)
    finite = np.logical_and.reduce([np.isfinite(d) for d in slices])
    filled = [np.where(finite, d, 0.0) for d in slices]

    def window(centre: np.ndarray) -> np.ndarray:
        near = [np.abs(d - c) < thresh_db for d, c in zip(filled, centre)]
        return finite & np.logical_and.reduce(near)

    points = np.stack([d[finite] for d in slices], axis=1)  # [m, bands]
    centre = np.zeros(len(slices))
    if points.shape[0]:
        centre = _nearest_mode(points, bandwidth_db, max_shift_db)
    stable = window(centre)
    if _max_abs_median(filled, stable) > max_shift_db:
        lo, hi = 0.0, 1.0  # largest pull-back factor whose window median is within the cap
        for _ in range(40):
            mid = 0.5 * (lo + hi)
            if _max_abs_median(filled, window(mid * centre)) <= max_shift_db:
                lo = mid
            else:
                hi = mid
        stable = window(lo * centre)
    return stable


def relative_delta(delta_db, stable) -> np.ndarray:
    """Change in dB minus the median change of the stable blocks (per leading slice).

    ``delta_db`` is [ny, nx] (or [..., ny, nx]); NaN blocks stay NaN. Raises NoStableBlocks
    when no stable block has a finite delta, since the scene offset is then unknown.
    """
    delta = np.asarray(delta_db, dtype=float)
    stable = np.asarray(stable, dtype=bool)
    if delta.ndim < 2 or delta.shape[-2:] != stable.shape:
        raise ValueError(f"delta {delta.shape} and stable {stable.shape} grids differ")
    flat = delta.reshape(-1, *stable.shape)
    out = np.empty_like(flat)
    for i, d in enumerate(flat):
        use = stable & np.isfinite(d)
        if not use.any():
            raise NoStableBlocks("no stable block with a finite delta; scene offset is unknown")
        out[i] = d - np.median(d[use])
    return out.reshape(delta.shape)


# --------------------------------------------------------------------------- ENL


def normalise_dates(series_lin, stable) -> np.ndarray:
    """Remove scene-wide per-date shifts (moisture, calibration) from a [T, ny, nx] series.

    Each date is divided by the median factor, relative to their temporal mean, of stable
    blocks that are valid and vary in time; factors are centred (idempotent). Use it on BOTH
    paths: ``estimate_enl`` calls it, and ``omnibus(..., stable=)`` applies it to the input.
    Invalid blocks pass through. Raises NoStableBlocks when no stable block qualifies.
    """
    s = np.asarray(series_lin, dtype=float)
    stable = np.asarray(stable, dtype=bool)
    if s.ndim != 3:
        raise ValueError(f"series must be [T, ny, nx], got shape {s.shape}")
    if stable.shape != s.shape[1:]:
        raise ValueError(f"stable {stable.shape} does not match the series grid {s.shape[1:]}")
    use = stable & _valid_blocks([s])
    blocks = s[:, use]
    if s.shape[0] > 1:
        blocks = blocks[:, blocks.var(axis=0, ddof=1) > 0]
    if blocks.shape[1] == 0:
        raise NoStableBlocks("no valid, time-varying stable block to normalise the dates with")
    logs = np.log(blocks)
    offset = np.median(logs - logs.mean(axis=0), axis=1)
    offset -= offset.mean()
    return s * np.exp(-offset)[:, None, None]


def _seed_statistic(blocks: np.ndarray, df: int) -> float:
    """median over blocks of mean^2 / var (ddof = 1), times median(chi2(df)) / df."""
    mean = blocks.mean(axis=0)
    var = blocks.var(axis=0, ddof=1)
    ratio = np.divide(mean**2, var, out=np.full(var.shape, np.inf), where=var > 0)
    return float(np.median(ratio)) * stats.chi2.median(df) / df


@functools.lru_cache(maxsize=64)
def _seed_map(T: int, window_db: float) -> tuple[np.ndarray, np.ndarray]:
    """Monte-Carlo map log(true ENL) -> log(expected seed): Gamma(n) series of length T, no
    change, blocks with 0 < |last-vs-first delta| < window_db (either half, by symmetry),
    same seed statistic as the data. Fixed RNG seed: deterministic."""
    rng = np.random.default_rng(20261114)
    log_expected = np.empty(_SEED_MC_GRID.size)
    for i, n in enumerate(_SEED_MC_GRID):
        x = rng.gamma(n, 1.0 / n, size=(T, _SEED_MC_BLOCKS))
        d = np.abs(10.0 * np.log10(x[-1] / x[0]))
        log_expected[i] = np.log(_seed_statistic(x[:, (d > 0) & (d < window_db)], T - 1))
    log_expected = np.maximum.accumulate(log_expected) + 1e-12 * np.arange(log_expected.size)
    return np.log(_SEED_MC_GRID), log_expected


def _corrected_seed(blocks: np.ndarray, window_db: float, min_side: int) -> float:
    """Truncation-corrected seed ENL from date-normalised usable blocks [T, m].

    Each half of the last-vs-first delta (0 < d < window_db, and the mirror) is inverted
    through ``_seed_map``; the larger wins. Unchanged blocks are symmetric about 0, while most
    changes go one way (burn, clearcut, open flood darken) and only lower their half's
    estimate. ENL_MIN when neither half has ``min_side`` blocks.
    """
    T = blocks.shape[0]
    d = 10.0 * np.log10(blocks[-1] / blocks[0])
    log_grid, log_expected = _seed_map(T, float(window_db))
    best = ENL_MIN
    for half in ((d > 0) & (d < window_db), (d < 0) & (d > -window_db)):
        if half.sum() < min_side:
            continue
        observed = np.log(_seed_statistic(blocks[:, half], T - 1))
        best = max(best, float(np.exp(np.interp(observed, log_expected, log_grid))))
    return min(best, ENL_MAX)


def estimate_enl(
    series_lin,
    stable,
    clip_alpha: float | None = ENL_CLIP_ALPHA,
    min_blocks: int = MIN_BLOCKS,
) -> float:
    """Equivalent number of looks of one band's block-mean series, [T, ny, nx] linear.

    Usable blocks are valid on every date and vary in time (zero variance = fill, excluded).
    The series goes through ``normalise_dates`` first: the ENL describes noise, not a shift.

    Seed: the brief's statistic (median of mean^2 / var, ddof = 1, times median(chi2(T-1)) /
    (T-1)) on one half of the last-vs-first delta (0..3 dB or -3..0 dB), corrected for that
    truncation through a cached Monte-Carlo map (``_corrected_seed``). The old seed used the
    +-1 dB stable window, which at T = 2 set its value (73-78 for true n = 10-20) by itself.

    Refinement (``clip_alpha``): over all usable blocks, u = (T-1)var/mean^2 with n*u ~
    chi2(T-1) under no change; keep n*u <= chi2 quantile (1 - clip_alpha), set n = chi2
    quantile ((1 - clip_alpha)/2) / median(kept u), iterate to the fixed point. A majority of
    moderately changed blocks leaks into the kept set and collapses it (n ~ 1-13), so the
    result is never below ``seed / ENL_SEED_RATIO``.

    ``clip_alpha=None`` returns the corrected seed. Set blocks to NaN to keep them out (other
    strata, water). Clipped to [1, 1000]. Raises TooFewBlocks below ``min_blocks`` usable (or
    usable stable) blocks, NoStableBlocks when none is stable, ValueError on bad input.
    """
    s = np.asarray(series_lin, dtype=float)
    stable = np.asarray(stable, dtype=bool)
    if s.ndim != 3:
        raise ValueError(f"series must be [T, ny, nx], got shape {s.shape}")
    T = s.shape[0]
    if T < 2:
        raise ValueError("need at least 2 dates to estimate the ENL")
    if stable.shape != s.shape[1:]:
        raise ValueError(f"stable {stable.shape} does not match the series grid {s.shape[1:]}")
    if clip_alpha is not None and not 0 < clip_alpha < 1:
        raise ValueError(f"clip_alpha must be in (0, 1) or None, got {clip_alpha}")
    if not min_blocks >= 1:
        raise ValueError(f"min_blocks must be >= 1, got {min_blocks}")

    valid = _valid_blocks([s])
    usable = np.zeros(stable.shape, dtype=bool)
    usable[valid] = s[:, valid].var(axis=0, ddof=1) > 0
    n_usable = int(usable.sum())
    if n_usable < min_blocks:
        raise TooFewBlocks(f"only {n_usable} usable blocks for the ENL; need {min_blocks}")
    n_stable = int((stable & usable).sum())
    if n_stable == 0:
        raise NoStableBlocks("no usable stable block to estimate the ENL from")
    if n_stable < min_blocks:
        raise TooFewBlocks(f"only {n_stable} usable stable blocks for the ENL; need {min_blocks}")

    blocks = normalise_dates(s, stable)[:, usable]  # [T, m]
    seed = _corrected_seed(blocks, SEED_WINDOW_DB, min_side=max(min_blocks // 4, 1))
    if clip_alpha is None:
        return float(seed)

    df = T - 1
    mean = blocks.mean(axis=0)
    u = df * blocks.var(axis=0, ddof=1) / mean**2  # >= 0 (the median block can be constant)
    upper = stats.chi2.ppf(1 - clip_alpha, df)
    middle = stats.chi2.ppf((1 - clip_alpha) / 2, df)
    n = max(seed, _seed_statistic(blocks, df))  # start from above the truth
    n = min(max(n, ENL_MIN), ENL_MAX)
    for _ in range(_MAX_ITER):
        kept = u[n * u <= upper]  # never empty while some u == 0
        if kept.size == 0:  # n is far too high: lower it until the least variable block fits
            new = upper / float(u.min())
        else:
            med = float(np.median(kept))
            new = middle / med if med > 0 else ENL_MAX
        new = min(max(new, ENL_MIN), ENL_MAX)
        if abs(new - n) <= 1e-9 * n:
            n = new
            break
        n = new
    n = max(n, seed / ENL_SEED_RATIO)
    return float(min(max(n, ENL_MIN), ENL_MAX))


# --------------------------------------------------------------------------- omnibus test


def omnibus(channels, enls, alpha: float = ALPHA, stable=None) -> tuple[np.ndarray, np.ndarray]:
    """Sequential omnibus change test on block means (Conradsen et al. 2016), per band.

    Pass date-normalised bands, or ``stable`` to normalise here (``normalise_dates``): the
    test is invariant to a constant per-block factor but NOT to per-date scene-wide shifts.
    For each band with ENL n, k dates s_1..s_k and S_j = s_1 + ... + s_j:

        -2 ln Q   = -2n [k ln k + sum ln s_i - k ln S_k]                       (no change at all)
        -2 ln R_j = -2n [j ln j - (j-1) ln(j-1) + (j-1) ln S_{j-1}
                         + ln s_j - j ln S_j]                    (s_j equals s_1..s_{j-1})

    scaled by rho = 1 - (k/n - 1/(nk)) / (6(k-1)) and rho_j = 1 - (1 + 1/(j(j-1))) / (6n)
    (Conradsen 2016): Q ~ chi2(k-1), R_j ~ chi2(1). Bands combine by Bonferroni on the
    smallest band p, p = min(1, P * min_b p_b), valid however HH and HV co-vary (the summed
    statistic was 2.5-3.5x liberal under shared natural variability). ``enls``: per band, a
    float or a map broadcasting to [ny, nx] (e.g. per land-cover stratum); NaN = invalid.

    Returns ``(p, change_idx)``: change_idx is the 0-based index of the first date after the
    change, from the band with the smallest p: j-1 for the first j = 2..k with that band's
    p_j < alpha, only where p < alpha; otherwise -1. Only the first change is located.
    """
    if not 0 < alpha < 1:
        raise ValueError(f"alpha must be in (0, 1), got {alpha}")
    chans = [np.asarray(c, dtype=float) for c in channels]
    enls = list(enls)
    if not chans:
        raise ValueError("omnibus needs at least one band")
    if len(enls) != len(chans):
        raise ValueError(f"{len(chans)} bands but {len(enls)} ENLs")
    shape = chans[0].shape
    if len(shape) != 3 or any(c.shape != shape for c in chans):
        raise ValueError(
            f"every band must be [T, ny, nx] with one shape, got {[c.shape for c in chans]}"
        )
    if stable is not None:
        chans = [normalise_dates(c, stable) for c in chans]
    k = shape[0]
    if k < 2:
        raise ValueError("need at least 2 dates")
    grid = shape[1:]
    maps = [_enl_map(e, grid) for e in enls]

    valid = _valid_blocks(chans) & np.logical_and.reduce([np.isfinite(m) for m in maps])
    p_band, r_band = [], []
    for s, n in zip(chans, maps):
        s = np.where(valid, s, 1.0)  # neutral fill; invalid blocks are masked below
        n = np.where(valid, n, 1.0)
        csum = np.cumsum(s, axis=0)
        # k ln k + sum ln s_i - k ln S_k == sum ln(s_i / mean)
        ln_q = n * np.log(s / (csum[-1] / k)).sum(axis=0)
        rho = 1.0 - (k / n - 1.0 / (n * k)) / (6.0 * (k - 1))
        r_stat = np.empty((k - 1, *grid))  # row j-2 holds -2 rho_j ln R_j, j = 2..k
        for j in range(2, k + 1):
            prev = csum[j - 2] / (j - 1)  # mean of s_1..s_{j-1}
            pooled = csum[j - 1] / j  # mean of s_1..s_j
            # j ln j - (j-1)ln(j-1) + (j-1)ln S_{j-1} + ln s_j - j ln S_j, rearranged
            ln_r = n * ((j - 1) * np.log(prev / pooled) + np.log(s[j - 1] / pooled))
            rho_j = 1.0 - (1.0 + 1.0 / (j * (j - 1))) / (6.0 * n)
            r_stat[j - 2] = -2.0 * rho_j * ln_r
        p_band.append(stats.chi2.sf(np.maximum(-2.0 * rho * ln_q, 0.0), k - 1))
        r_band.append(r_stat)

    p_band = np.stack(p_band)  # [P, ny, nx]
    best = np.argmin(p_band, axis=0)
    p = np.minimum(1.0, len(chans) * p_band.min(axis=0))
    r_best = np.take_along_axis(np.stack(r_band), best[None, None], axis=0)[0]
    p_step = special.erfc(np.sqrt(np.maximum(r_best, 0.0) / 2.0))  # chi2(1) survival
    hit = (p_step < alpha) & (p < alpha)
    change_idx = np.where(hit.any(axis=0), np.argmax(hit, axis=0) + 1, -1)
    p = np.where(valid, p, np.nan)
    change_idx = np.where(valid, change_idx, -1).astype(np.int64)
    return p, change_idx


# --------------------------------------------------------------------------- decisions


def bh_fdr(p, q: float = 0.05) -> np.ndarray:
    """Benjamini-Hochberg step-up: True where the block is significant at FDR ``q``.

    NaN p-values are never significant and do not count towards the number of tests.
    """
    if not 0 < q <= 1:
        raise ValueError(f"q must be in (0, 1], got {q}")
    p = np.asarray(p, dtype=float)
    out = np.zeros(p.shape, dtype=bool)
    finite = np.isfinite(p)
    vals = p[finite]
    m = vals.size
    if m == 0:
        return out
    ranked = np.sort(vals)
    passes = ranked <= q * np.arange(1, m + 1) / m
    if not passes.any():
        return out
    cutoff = ranked[np.flatnonzero(passes)[-1]]
    out[finite] = vals <= cutoff
    return out


def changed(p, rel_delta_db, q: float = 0.05, min_db=2.0) -> np.ndarray:
    """Changed = BH-significant at ``q`` AND some band's |relative change| >= its ``min_db``.

    ``rel_delta_db`` is [ny, nx], or a list / leading axis of per-band arrays. ``min_db`` is a
    float for every band or a sequence with one threshold per band (the scorecard tunes them
    per band). NaN changes never pass the gate.
    """
    p = np.asarray(p, dtype=float)
    if isinstance(rel_delta_db, (list, tuple)):
        rel = np.stack([np.asarray(r, dtype=float) for r in rel_delta_db])
    else:
        rel = np.asarray(rel_delta_db, dtype=float)
    if rel.ndim == p.ndim:
        rel = rel[None]
    if rel.ndim != p.ndim + 1 or rel.shape[1:] != p.shape:
        raise ValueError(f"rel_delta_db {rel.shape} does not match p {p.shape}")
    mins = np.atleast_1d(np.asarray(min_db, dtype=float))
    if mins.ndim != 1 or mins.size not in (1, rel.shape[0]):
        raise ValueError(f"min_db needs 1 or {rel.shape[0]} thresholds, got {mins.size}")
    mins = np.broadcast_to(mins, (rel.shape[0],))
    big = np.zeros(p.shape, dtype=bool)
    for r, m in zip(rel, mins):
        big |= np.abs(r) >= m  # NaN compares False
    return bh_fdr(p, q) & big
