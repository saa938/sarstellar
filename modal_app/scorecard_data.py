"""Collect a scorecard site's block table without changing the app's defaults."""

from __future__ import annotations

import io
from datetime import date

import numpy as np
import pandas as pd

from sarstellar import features, scoring


def collect_site(site: dict, *, feature_fn=None, label_fn=None) -> pd.DataFrame:
    """Pin both radars to the catalogued pairs; retain full-series L as a separate extra.

    Primary comparisons use the intersection of valid L, C and L30 blocks. Sites without
    Sentinel-1 remain in the audit but cannot enter the fusion headline. Flags are computed
    over the whole valid box before reference availability or class subsetting.
    """
    feature_fn = feature_fn or features.block_features
    label_fn = label_fn or scoring.block_labels
    meta = site["meta"]
    days = [date.fromisoformat(d) for d in meta["pair_dates"]]
    key = (meta["track"], meta["direction"], meta["crid"])
    cache = {}

    def cached_read(granules, bbox, grid):
        out = []
        for g in granules:
            if g.ur not in cache:
                cache[g.ur] = features._read_sequential([g], bbox, grid)
            out.extend(cache[g.ur])
        return out

    bs = feature_fn(site["bbox"], days, stack_key=key, only_dates=days,
                    read_passes=cached_read, s1=site.get("s1") is not None,
                    s1_pair=site.get("s1"), pair_urs=site["nisar_pair"])
    labels = label_fn(site, bs.grid)
    if labels.shape != bs.grid.shape or not np.any(labels != ""):
        raise ValueError("no valid independent reference labels for this site")
    table = pd.DataFrame({
        "site": site["id"], "state": site["state"], "kind": site["kind"],
        "split": site["split"], "label": labels.ravel(), "valid": bs.valid.ravel(),
        "landcover": bs.landcover.ravel(), "p_L": bs.p_L.ravel(),
        "p_C": bs.p_C.ravel(), "p_L30": bs.p_L30.ravel(),
    })
    for pol in ("HH", "HV", "VV", "VH", "HH30", "HV30"):
        values = getattr(bs, f"rel_d{pol}", None)
        table[f"rel_{pol}"] = np.nan if values is None else values.ravel()
    table["p_Ls"] = np.nan
    try:
        series = feature_fn(site["bbox"], days, stack_key=key, pair_urs=site["nisar_pair"],
                            read_passes=cached_read, s1=False)
        if series.grid != bs.grid:
            raise ValueError("series and paired block grids differ")
        table["p_Ls"] = series.p_L.ravel()
        table["series_dates"] = len(series.dates)
        table["series_error"] = ""
    except Exception as exc:  # noqa: BLE001 - optional series never invalidates the primary pair
        table["series_dates"] = 0
        table["series_error"] = f"{type(exc).__name__}: {exc}"
    table["y"] = table["label"].isin(scoring.KIND_CLASS.values())
    for det in ("L", "C", "L30", "L_series", "fused_fisher", "fused_bonferroni"):
        table[f"s_{det}"] = scoring.neg_log10(scoring.pvalue(table, det))
        table[f"flag_{det}"] = scoring.flags(table, det)
    table["comparable"] = (
        table["valid"] & table["label"].ne("")
        & np.isfinite(table[["p_L", "p_C", "p_L30", "rel_HH", "rel_HV",
                               "rel_VV", "rel_VH", "rel_HH30", "rel_HV30"]]).all(axis=1)
    )
    return table


def parquet_bytes(table: pd.DataFrame) -> bytes:
    stream = io.BytesIO()
    table.to_parquet(stream, index=False)
    return stream.getvalue()
