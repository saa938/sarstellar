"""Block-level change detection for SAR intensity stacks.

The statistical core of SARstellar:

1. ``stable_mask`` / ``relative_delta``: find blocks that did not change and remove the
   scene-wide shift (moisture, calibration) from the per-block change in dB.
2. ``estimate_enl``: the equivalent number of looks (ENL) of the *block means*, estimated from
   the data. It absorbs residual speckle and natural date-to-date variability, so it is not
   capped by the per-pixel ``numberOfLooks``.
3. ``omnibus``: the sequential omnibus likelihood-ratio test of Conradsen et al. (2016) for
   diagonal covariance (independent bands, summed): one p-value per block plus the date of
   the first change.
4. ``bh_fdr`` / ``changed``: Benjamini-Hochberg FDR across the box, then a minimum-effect
   gate on the relative change.

All inputs are LINEAR intensities of 1-ha block means, one array of shape [T, ny, nx] per
band, NaN where a block is invalid. A block is valid only if every band is finite and > 0 on
every date; invalid blocks get p = NaN and change_idx = -1, with no numpy warnings.

Reference: K. Conradsen, A. A. Nielsen, H. Skriver, "Determining the points of change in time
series of polarimetric SAR data", IEEE TGRS 54(5):3007-3024, 2016,
doi:10.1109/TGRS.2015.2510160. For one intensity band (p = 1 in the paper) the complex
Wishart model reduces to Gamma(shape = n, scale = mean / n).
"""

from __future__ import annotations

from collections.abc import Sequence

import numpy as np
from scipy import stats

__all__ = [
    "ALPHA",
    "ENL_MAX",
    "ENL_MIN",
    "bh_fdr",
    "changed",
    "estimate_enl",
    "omnibus",
    "relative_delta",
    "stable_mask",
]

ALPHA = 0.01  # level of the omnibus test and of each change-date test R_j
ENL_MIN = 1.0
ENL_MAX = 10000.0
ENL_CLIP_ALPHA = 0.2  # null-calibrated trimming level used to refine the ENL
_MAX_ITER = 200


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


# --------------------------------------------------------------------------- stable / relative


def stable_mask(deltas_db, thresh_db: float = 1.0) -> np.ndarray:
    """Blocks whose change is small in every band.

    ``deltas_db`` is a list of per-band changes in dB, each [ny, nx] (an array with extra
    leading axes counts as one delta per leading slice). A block is stable when every delta is
    finite and within ``thresh_db`` of the scene offset.

    The window starts centred on 0 dB, so it is anchored on "no change" even when most of
    the box changed (a flood). It is then re-centred on the median delta of the stable blocks
    until it settles. Without that, a scene-wide shift keeps only one tail of the unchanged
    blocks: at +1.5 dB (the spikes saw +0.1..+1.5 dB) the offset estimate is off by ~1 dB.
    """
    if not thresh_db > 0:
        raise ValueError(f"thresh_db must be > 0, got {thresh_db}")
    slices = _delta_slices(deltas_db)
    finite = np.logical_and.reduce([np.isfinite(d) for d in slices])
    filled = [np.where(finite, d, 0.0) for d in slices]

    def window(offsets: np.ndarray) -> np.ndarray:
        near = [np.abs(d - o) < thresh_db for d, o in zip(filled, offsets)]
        return finite & np.logical_and.reduce(near)

    offsets = np.zeros(len(filled))
    stable = window(offsets)
    for _ in range(_MAX_ITER):
        if not stable.any():
            break
        new = np.array([np.median(d[stable]) for d in filled])
        if np.all(np.abs(new - offsets) < 1e-4):
            break
        offsets = new
        stable = window(offsets)
    return stable


def relative_delta(delta_db, stable) -> np.ndarray:
    """Change in dB minus the median change of the stable blocks (per leading slice).

    ``delta_db`` is [ny, nx] (or [..., ny, nx]); NaN blocks stay NaN. Raises ValueError when no
    stable block has a finite delta, since the scene offset is then unknown.
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
            raise ValueError("no stable block with a finite delta; scene offset is unknown")
        out[i] = d - np.median(d[use])
    return out.reshape(delta.shape)


# --------------------------------------------------------------------------- ENL


def estimate_enl(series_lin, stable, clip_alpha: float | None = ENL_CLIP_ALPHA) -> float:
    """Equivalent number of looks of one band's block-mean series, [T, ny, nx] linear.

    Seed (the brief's estimator): median over valid stable blocks of mean^2 / var across time
    (ddof = 1), times the small-sample factor median(chi2(T-1)) / (T-1). Without that factor
    the median of mean^2/var overstates n by 1.44x at T = 3 and 1.20x at T = 5, because the
    sample variance of a short series is right-skewed (its median is below its mean).

    Refinement (``clip_alpha``, default 0.2): the seed is biased whenever ``stable`` was chosen
    from the same data. A |delta| < 1 dB window cuts off the noise tails and overstates n by
    1.4x (n = 60, T = 3) to 2.2x (n = 20, T = 3), which multiplies the omnibus false-alarm
    rate by 5-20x. So the estimate is refined over *all* valid blocks: with u = (T-1)var/mean^2,
    n*u ~ chi2(T-1) under no change, keep blocks with n*u <= chi2 quantile (1 - clip_alpha) and
    set n = chi2 quantile ((1 - clip_alpha)/2) / median(kept u), iterating from the seed to the
    fixed point. Changed blocks have large u and are trimmed; the trimming of null blocks is
    accounted for exactly. Weak changes that survive trimming can only lower n (fewer false
    alarms, slightly less power). Pass ``clip_alpha=None`` for the seed alone. To keep blocks
    out of the estimate entirely (e.g. permanent water), set them to NaN.

    Returns the ENL clipped to [1, 10000]. Raises ValueError for T < 2, a grid mismatch, or no
    valid stable block.
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

    valid = _valid_blocks([s])
    blocks = s[:, valid]  # [T, m]
    mean = blocks.mean(axis=0)
    var = blocks.var(axis=0, ddof=1)
    seed_var = var[stable[valid]]
    if seed_var.size == 0:
        raise ValueError("no valid stable block to estimate the ENL from")
    seed_mean = mean[stable[valid]]
    ratio = np.divide(
        seed_mean**2, seed_var, out=np.full(seed_var.shape, np.inf), where=seed_var > 0
    )
    df = T - 1
    n = float(np.median(ratio)) * stats.chi2.median(df) / df
    n = min(max(n, ENL_MIN), ENL_MAX)

    if clip_alpha is not None:
        u = df * var / mean**2  # mean > 0 on valid blocks
        upper = stats.chi2.ppf(1 - clip_alpha, df)
        middle = stats.chi2.ppf((1 - clip_alpha) / 2, df)
        for _ in range(_MAX_ITER):
            kept = u[n * u <= upper]
            if kept.size == 0:  # n far too high: lower it until the least variable block fits
                new = upper / u.min()
            else:
                med = float(np.median(kept))
                new = middle / med if med > 0 else ENL_MAX
            new = min(max(new, ENL_MIN), ENL_MAX)
            if abs(new - n) <= 1e-9 * n:
                break
            n = new
        n = new
    return float(min(max(n, ENL_MIN), ENL_MAX))


# --------------------------------------------------------------------------- omnibus test


def omnibus(channels, enls, alpha: float = ALPHA) -> tuple[np.ndarray, np.ndarray]:
    """Sequential omnibus change test on block means (Conradsen et al. 2016, diagonal case).

    For each band with ENL n, k dates s_1..s_k and S_j = s_1 + ... + s_j:

        -2 ln Q   = -2n [k ln k + sum ln s_i - k ln S_k]                       (no change at all)
        -2 ln R_j = -2n [j ln j - (j-1) ln(j-1) + (j-1) ln S_{j-1}
                         + ln s_j - j ln S_j]                    (s_j equals s_1..s_{j-1})

    Each statistic is scaled by its small-sample factor, rho = 1 - (k/n - 1/(nk)) / (6(k-1))
    for Q and rho_j = 1 - (1 + 1/(j(j-1))) / (6n) for R_j (Conradsen 2016; both make the
    expectation exact to O(1/n^2)), then summed over the P bands: Q ~ chi2(P(k-1)) and
    R_j ~ chi2(P). Note ln Q = sum_j ln R_j. The test is invariant to a constant per-block
    factor (e.g. RTC area normalisation) but NOT to per-date scene-wide shifts.

    Returns ``(p, change_idx)``: p is the omnibus p-value [ny, nx]; change_idx is the 0-based
    index of the first date after the change, i.e. j-1 for the first j = 2..k with
    p_j < alpha, and only where the omnibus p < alpha; otherwise -1. Only the first change
    is located (no restart after it).
    """
    if not 0 < alpha < 1:
        raise ValueError(f"alpha must be in (0, 1), got {alpha}")
    chans = [np.asarray(c, dtype=float) for c in channels]
    enl = [float(e) for e in enls]
    if not chans:
        raise ValueError("omnibus needs at least one band")
    if len(enl) != len(chans):
        raise ValueError(f"{len(chans)} bands but {len(enl)} ENLs")
    shape = chans[0].shape
    if len(shape) != 3 or any(c.shape != shape for c in chans):
        raise ValueError(
            f"every band must be [T, ny, nx] with one shape, got {[c.shape for c in chans]}"
        )
    k = shape[0]
    if k < 2:
        raise ValueError("need at least 2 dates")
    if not all(np.isfinite(n) and n >= ENL_MIN for n in enl):
        raise ValueError(f"ENLs must be finite and >= {ENL_MIN}, got {enl}")

    valid = _valid_blocks(chans)
    q_stat = np.zeros(shape[1:])
    r_stat = np.zeros((k - 1, *shape[1:]))  # row j-2 holds -2 rho_j ln R_j, j = 2..k
    for s, n in zip(chans, enl):
        s = np.where(valid, s, 1.0)  # neutral fill; invalid blocks are masked below
        csum = np.cumsum(s, axis=0)
        # k ln k + sum ln s_i - k ln S_k == sum ln(s_i / mean)
        ln_q = n * np.log(s / (csum[-1] / k)).sum(axis=0)
        rho = 1.0 - (k / n - 1.0 / (n * k)) / (6.0 * (k - 1))
        q_stat += -2.0 * rho * ln_q
        for j in range(2, k + 1):
            prev = csum[j - 2] / (j - 1)  # mean of s_1..s_{j-1}
            pooled = csum[j - 1] / j  # mean of s_1..s_j
            # j ln j - (j-1)ln(j-1) + (j-1)ln S_{j-1} + ln s_j - j ln S_j, rearranged
            ln_r = n * ((j - 1) * np.log(prev / pooled) + np.log(s[j - 1] / pooled))
            rho_j = 1.0 - (1.0 + 1.0 / (j * (j - 1))) / (6.0 * n)
            r_stat[j - 2] += -2.0 * rho_j * ln_r

    bands = len(chans)
    p = stats.chi2.sf(np.maximum(q_stat, 0.0), bands * (k - 1))
    p_step = stats.chi2.sf(np.maximum(r_stat, 0.0), bands)
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


def changed(p, rel_delta_db, q: float = 0.05, min_db: float = 2.0) -> np.ndarray:
    """Changed = BH-significant at ``q`` AND |relative change| >= ``min_db``.

    ``rel_delta_db`` is [ny, nx], or a list / leading axis of per-band arrays, in which case
    the largest |relative change| over the bands is used. NaN changes are never "changed".
    """
    p = np.asarray(p, dtype=float)
    if isinstance(rel_delta_db, (list, tuple)):
        rel = np.stack([np.asarray(r, dtype=float) for r in rel_delta_db])
    else:
        rel = np.asarray(rel_delta_db, dtype=float)
    if rel.ndim == p.ndim + 1:
        magnitude = np.fmax.reduce(np.abs(rel), axis=0)  # ignores NaN bands, no warning
    elif rel.ndim == p.ndim:
        magnitude = np.abs(rel)
    else:
        raise ValueError(f"rel_delta_db {rel.shape} does not match p {p.shape}")
    if magnitude.shape != p.shape:
        raise ValueError(f"rel_delta_db {rel.shape} does not match p {p.shape}")
    return bh_fdr(p, q) & (magnitude >= min_db)
