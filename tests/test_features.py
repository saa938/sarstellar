"""Shared block features: series selection, validity, per-stratum ENL, omnibus p-values.

Offline tests feed `block_features` synthetic gamma-distributed block means through a fake
`read_passes`, a fake CMR search and a fake RTC read, so the whole path (search -> stack ->
composite -> stable mask -> ENL -> omnibus) runs with no network. The synthetic model is the
one the detector assumes: a block mean is `level * Gamma(n, 1/n)` with n looks. The `live`
test reads real Kaiser Canyon data (needs ~/_netrc, run with `-m live`).
"""

from __future__ import annotations

from datetime import date, timedelta

import numpy as np
import pytest
import rasterio
from pyproj import Transformer
from rasterio.transform import from_origin

from sarstellar import detect, features, refs
from sarstellar.grid import grid_for_bbox
from sarstellar.types import NoUsablePasses
from test_search import make_granule

BBOX = (-119.20, 48.15, -119.10, 48.22)  # 83 x 79 blocks in UTM zone 10
EPSG = 32610
GRID = grid_for_bbox(BBOX, EPSG)
NY, NX = GRID.shape
PATCH = np.s_[20:32, 20:32]  # 144 blocks
D0 = date(2026, 7, 13)
DAYS = [D0 + timedelta(days=12 * i) for i in range(3)]


# --- synthetic data -----------------------------------------------------------------------------


def _gamma(rng, level, enl):
    return level * rng.gamma(enl, 1.0 / enl, level.shape)


class Synth:
    """A synthetic NISAR + Sentinel-1 scene: one array set per date, with an optional HV patch."""

    def __init__(self, days, *, enl=100.0, enl30=25.0, enl_c=100.0, hv_drop_db=3.0, seed=1,
                 enl_map=None, drop_everywhere=False):
        rng = np.random.default_rng(seed)
        hh_db = rng.normal(-9.0, 2.0, (NY, NX))
        lvl = {"HH": 10 ** (hh_db / 10), "HV": 10 ** ((hh_db - 6.5) / 10)}
        lvl["VV"], lvl["VH"] = 10 ** ((hh_db - 2.0) / 10), 10 ** ((hh_db - 9.0) / 10)
        n = enl if enl_map is None else enl_map
        n30 = enl30 if enl_map is None else enl_map / 4.0
        self.L, self.C = {}, {}
        for i, d in enumerate(days):
            shift = 10 ** ((0.0, 0.3, -0.2)[i % 3] / 10)  # scene-wide per-date shift
            drop = 10 ** (-(hv_drop_db if i >= 1 else 0.0) / 10)
            hv_scale = np.full((NY, NX), drop if drop_everywhere else 1.0)
            if not drop_everywhere:
                hv_scale[PATCH] = drop
            self.L[d] = {
                "HH": _gamma(rng, lvl["HH"] * shift, n),
                "HV": _gamma(rng, lvl["HV"] * shift * hv_scale, n),
                "HH30": _gamma(rng, lvl["HH"] * shift, n30),
                "HV30": _gamma(rng, lvl["HV"] * shift * hv_scale, n30),
                "valid_frac": np.ones((NY, NX)),
            }
            vh_scale = np.ones((NY, NX))
            vh_scale[PATCH] = 10 ** (-3.0 / 10) if i >= 1 else 1.0
            self.C[d] = {
                "VV": _gamma(rng, lvl["VV"], enl_c),
                "VH": _gamma(rng, lvl["VH"] * vh_scale, enl_c),
            }


def _meta(g, epsg=EPSG):
    return {"date": g.start.isoformat(), "epsg": epsg, "granule": g.ur, "track": g.track}


class Fakes:
    """Patches search, read and refs on the `features` module; records what was asked."""

    def __init__(self, monkeypatch, synth, days, *, scenes=None, extra_granules=()):
        self.synth, self.days = synth, days
        self.granules = [make_granule(d, track=71) for d in days] + list(extra_granules)
        self.scenes = scenes if scenes is not None else self._scenes(days)
        self.searches, self.read_calls = [], []
        monkeypatch.setattr(features.search, "search_gcov", self._search_gcov)
        monkeypatch.setattr(features.search, "search_rtc_s1", self._search_rtc)
        monkeypatch.setattr(features.read, "https_fs", lambda: object())
        monkeypatch.setattr(features.read, "read_rtc_to_grid", self._read_rtc)
        monkeypatch.setattr(refs, "nlcd", lambda grid: np.full(grid.shape, "forest"))

    @staticmethod
    def _scenes(days, track=115, offsets=(0, 1)):
        out = [{"track": track, "date": days[0] + timedelta(days=offsets[0])},
               {"track": track, "date": days[-1] + timedelta(days=offsets[1])}]
        return [{**s, "urls_vv": [f"vv_{s['date']:%Y%m%d}"], "urls_vh": [f"vh_{s['date']:%Y%m%d}"]}
                for s in out]

    def _search_gcov(self, bbox, start, end):
        self.searches.append((tuple(bbox), start, end))
        return list(self.granules)

    def _search_rtc(self, bbox, around, max_days=6):
        hits = [s for s in self.scenes if abs((s["date"] - around).days) <= max_days]
        return sorted(hits, key=lambda s: abs((s["date"] - around).days))

    def _read_rtc(self, urls, grid, fs, max_retries=6):
        day = date(2000, 1, 1)
        for s in self.scenes:
            if urls[0] in s["urls_vv"] + s["urls_vh"]:
                day = s["date"]
        # the synthetic S1 pair is stored under the NISAR dates it was built for
        key = self.days[0] if day <= self.days[0] + timedelta(days=3) else self.days[-1]
        return {"VV": self.synth.C[key]["VV"], "VH": self.synth.C[key]["VH"]}

    def read_passes(self, granules, bbox, grid):
        self.read_calls.append((list(granules), grid))
        return [(_meta(g), dict(self.synth.L[g.start.date()])) for g in granules]


def _run(monkeypatch, *, days=DAYS, bbox=BBOX, dates=None, s1=True, progress=None, **synth_kw):
    synth = Synth(days, **synth_kw)
    fakes = Fakes(monkeypatch, synth, days)
    bs = features.block_features(bbox, dates, read_passes=fakes.read_passes, s1=s1,
                                 progress=progress)
    return bs, fakes


# --- tests --------------------------------------------------------------------------------------


def test_blockset_shapes(monkeypatch):
    ticks = []
    bs, fakes = _run(monkeypatch, progress=lambda f, m: ticks.append((f, m)))
    assert bs.grid == GRID and bs.grid.epsg == EPSG
    assert bs.dates == DAYS and bs.stack.track == 71
    assert bs.s1["track"] == 115
    assert bs.s1["dates"] == [DAYS[0], DAYS[-1] + timedelta(days=1)]
    assert bs.s1["offset_days"] == [0, 1]
    assert bs.landcover.shape == GRID.shape and set(np.unique(bs.landcover)) == {"forest"}
    assert bs.valid.dtype == bool and bs.valid.shape == GRID.shape and bs.valid.all()
    floats = ["pre_HH", "pre_HV", "post_HH", "post_HV", "rel_dHH", "rel_dHV", "rel_dVV",
              "rel_dVH", "p_L", "p_C", "p_L30"]
    for name in floats:
        arr = getattr(bs, name)
        assert arr.shape == GRID.shape and arr.dtype.kind == "f", name
        assert np.isfinite(arr).mean() > 0.99, name
    for name in ("change_idx_L", "change_idx_C"):
        arr = getattr(bs, name)
        assert arr.shape == GRID.shape and arr.dtype.kind == "i", name
    assert set(bs.enl) == {"HH", "HV", "HH30", "HV30", "VV", "VH"}
    assert all(detect.ENL_MIN <= v <= detect.ENL_MAX for v in bs.enl.values())
    assert 60 < bs.enl["HH"] < 160  # true ENL is 100
    assert bs.newer_validated_dates == []
    # pre/post are the first and last NISAR date, in dB
    hh = [10 * np.log10(fakes.synth.L[d]["HH"]) for d in (DAYS[0], DAYS[-1])]
    assert np.allclose(bs.pre_HH, hh[0]) and np.allclose(bs.post_HH, hh[1])
    # relative change has the scene-wide shift removed: stable blocks centre on zero
    assert abs(np.median(bs.rel_dHH)) < 0.5
    fracs = [f for f, _ in ticks]
    assert fracs == sorted(fracs) and 0 < fracs[0] and fracs[-1] <= 1
    # one read call, all granules in date order, no grid yet (the file decides the zone)
    assert len(fakes.read_calls) == 1 and fakes.read_calls[0][1] is None
    assert [g.start.date() for g in fakes.read_calls[0][0]] == DAYS


def test_drop_patch_low_p_L(monkeypatch):
    bs, _ = _run(monkeypatch)
    outside = np.ones(GRID.shape, bool)
    outside[PATCH] = False
    assert np.nanpercentile(bs.p_L[PATCH], 90) < 1e-3
    assert np.nanmedian(bs.p_L[outside]) > 0.1
    assert np.median(bs.rel_dHV[PATCH]) == pytest.approx(-3.0, abs=0.5)
    assert np.median(bs.rel_dHH[PATCH]) == pytest.approx(0.0, abs=0.6)
    assert (bs.change_idx_L[PATCH] == 1).mean() > 0.9  # the drop starts at the second date
    # C sees its own (3 dB VH) drop in the same patch
    assert np.nanpercentile(bs.p_C[PATCH], 90) < 1e-3 and np.nanmedian(bs.p_C[outside]) > 0.1
    assert np.median(bs.rel_dVH[PATCH]) == pytest.approx(-3.0, abs=0.7)


def test_l30_has_higher_p_than_l(monkeypatch):
    bs, _ = _run(monkeypatch)
    assert np.nanmedian(bs.p_L30[PATCH]) >= np.nanmedian(bs.p_L[PATCH])
    assert 1.0 <= bs.enl["HH30"] < bs.enl["HH"]  # the 30 m lattice is noisier: fewer looks


def test_no_stack_raises(monkeypatch):
    start, end = date(2026, 7, 1), date(2026, 10, 1)
    msg = f"No calibrated NISAR passes cover this box between {start} and {end}."
    for granules in ([], [make_granule(date(2026, 7, 13))],
                     [replace_mixed(make_granule(d)) for d in DAYS]):
        monkeypatch.setattr(features.search, "search_gcov", lambda b, s, e, g=granules: g)
        with pytest.raises(NoUsablePasses) as exc:
            features.block_features(BBOX, (start, end), read_passes=pytest.fail)
        assert str(exc.value) == msg


def replace_mixed(g):
    g.mixed_mode = True
    return g


def test_no_s1_sets_none(monkeypatch):
    synth = Synth(DAYS)
    for scenes in ([], Fakes._scenes(DAYS, offsets=(7, 0))):  # none / first end 7 days away
        fakes = Fakes(monkeypatch, synth, DAYS, scenes=scenes)
        bs = features.block_features(BBOX, read_passes=fakes.read_passes)
        assert bs.s1 is None
        assert np.isnan(bs.p_C).all() and np.isnan(bs.rel_dVV).all() and np.isnan(bs.rel_dVH).all()
        assert (bs.change_idx_C == -1).all()
        assert np.isfinite(bs.p_L).any()
    fakes = Fakes(monkeypatch, synth, DAYS)  # s1=False never searches
    monkeypatch.setattr(features.search, "search_rtc_s1", pytest.fail)
    assert features.block_features(BBOX, read_passes=fakes.read_passes, s1=False).s1 is None


def test_s1_needs_one_track_at_both_ends(monkeypatch):
    synth = Synth(DAYS)
    a, b = Fakes._scenes(DAYS, track=115), Fakes._scenes(DAYS, track=166, offsets=(2, 3))
    split = [a[0], b[1]]  # track 115 only near the first date, 166 only near the last
    fakes = Fakes(monkeypatch, synth, DAYS, scenes=split)
    assert features.block_features(BBOX, read_passes=fakes.read_passes).s1 is None
    both = Fakes(monkeypatch, synth, DAYS, scenes=a + b)  # 115 is closer in total
    s1 = features.block_features(BBOX, read_passes=both.read_passes).s1
    assert s1["track"] == 115 and s1["offset_days"] == [0, 1]


def test_series_window_and_cap(monkeypatch):
    days = [D0 + timedelta(days=12 * i) for i in range(20)]
    bs, fakes = _run(monkeypatch, days=days, dates=("2026-12-31", date(2026, 7, 1)))
    assert fakes.searches == [(BBOX, date(2026, 7, 1), date(2026, 12, 31))]  # sorted, ISO ok
    assert len(bs.dates) == features.MAX_DATES == 12
    inside = [d for d in days if d <= date(2026, 12, 31)]  # the fake search ignores the window
    assert bs.dates[0] == inside[0] and bs.dates[-1] == inside[-1]  # the interval keeps both ends
    assert bs.dates == sorted(set(bs.dates))
    monkeypatch.setattr(features, "_today", lambda: date(2026, 11, 14))
    _, fakes = _run(monkeypatch)
    assert fakes.searches == [(BBOX, date(2025, 11, 14), date(2026, 11, 14))]


def test_newer_validated_dates(monkeypatch):
    days = [D0 + timedelta(days=12 * i) for i in range(4)]  # ends 2026-08-18
    other = [
        make_granule(date(2026, 10, 21), track=71, crid="P05036"),  # later, same track: counts
        make_granule(date(2026, 11, 2), track=71, crid="P05036"),
        make_granule(date(2026, 10, 25), track=34, crid="P05036"),  # another track: no
        make_granule(date(2026, 8, 1), track=71, crid="P05036"),  # before the series ends: no
    ]
    synth = Synth(days)
    fakes = Fakes(monkeypatch, synth, days, extra_granules=other)
    bs = features.block_features(BBOX, read_passes=fakes.read_passes)
    assert bs.stack.crid == "P05023" and bs.dates == days
    assert bs.newer_validated_dates == [date(2026, 10, 21), date(2026, 11, 2)]


def test_two_frames_on_one_date_are_composited(monkeypatch):
    synth = Synth(DAYS)
    left = np.arange(NX) < NX // 2
    Fakes(monkeypatch, synth, DAYS, extra_granules=[make_granule(DAYS[1], track=71, frame=65)])

    def read_passes(granules, bbox, grid):
        out = []
        for g in granules:
            blocks = {k: v.copy() for k, v in synth.L[g.start.date()].items()}
            if g.start.date() == DAYS[1]:  # frame 20 covers the left half, 65 the right half
                keep = left[None, :] if g.frame == 20 else ~left[None, :]
                for k, v in blocks.items():
                    blocks[k] = np.where(keep, v, 0.0 if k == "valid_frac" else np.nan)
            out.append((_meta(g), blocks))
        return out

    bs = features.block_features(BBOX, read_passes=read_passes)
    assert bs.dates == DAYS and bs.valid.all()
    assert np.isfinite(bs.p_L).all()


def test_pass_in_another_zone_is_dropped(monkeypatch):
    days = [D0 + timedelta(days=12 * i) for i in range(4)]
    synth = Synth(days)
    Fakes(monkeypatch, synth, days)

    def read_passes(granules, bbox, grid):
        return [(_meta(g, 32611 if i == 2 else EPSG), dict(synth.L[g.start.date()]))
                for i, g in enumerate(granules)]

    bs = features.block_features(BBOX, read_passes=read_passes)
    assert bs.dates == [days[0], days[1], days[3]] and bs.grid.epsg == EPSG

    def one_zone(granules, bbox, grid):  # every pass but the first is in zone 11
        return [(_meta(g, EPSG if i == 0 else 32611), dict(synth.L[g.start.date()]))
                for i, g in enumerate(granules)]

    with pytest.raises(NoUsablePasses):
        features.block_features(BBOX, read_passes=one_zone)


def test_valid_needs_half_the_block_on_every_date(monkeypatch):
    synth = Synth(DAYS)
    Fakes(monkeypatch, synth, DAYS)
    hole = np.s_[5:15, 40:50]
    synth.L[DAYS[1]]["valid_frac"][hole] = 0.4  # one date under 50%: the block is out
    synth.L[DAYS[2]]["HH"][60:64, 5:9] = np.nan  # a NaN mean also invalidates the block
    bs = features.block_features(BBOX, read_passes=lambda g, b, grid: [
        (_meta(x), dict(synth.L[x.start.date()])) for x in g])
    assert not bs.valid[hole].any() and not bs.valid[60:64, 5:9].any()
    assert bs.valid.sum() == GRID.shape[0] * GRID.shape[1] - 100 - 16
    assert np.isnan(bs.p_L[hole]).all() and np.isnan(bs.rel_dHV[hole]).all()
    assert np.isnan(bs.pre_HH[hole]).all() and np.isnan(bs.p_L30[hole]).all()


def test_per_stratum_enl_controls_false_alarms(monkeypatch):
    """R13: two land covers with different true ENL; each keeps its own false-alarm rate."""
    left = np.broadcast_to(np.arange(NX) < NX // 2, (NY, NX))
    enl_map = np.where(left, 8.0, 40.0)
    synth = Synth(DAYS, enl_map=enl_map, hv_drop_db=0.0)  # no change anywhere
    fakes = Fakes(monkeypatch, synth, DAYS)
    monkeypatch.setattr(refs, "nlcd", lambda grid: np.where(left, "forest", "crops"))
    bs = features.block_features(BBOX, read_passes=fakes.read_passes, s1=False)
    for name, mask in (("forest", left), ("crops", ~left)):
        fa = float((bs.p_L[mask] < detect.ALPHA).mean())
        assert fa <= 0.015, (name, fa)
    low, high = bs.enl_by_stratum["HH"]["forest"], bs.enl_by_stratum["HH"]["crops"]
    assert low < 16 and high > 25  # each stratum recovered its own ENL (true 8 and 40)
    # control: one scene-wide ENL would over-alarm the noisy half (the reason for strata)
    chans = [np.stack([synth.L[d][b] for d in DAYS]) for b in ("HH", "HV")]
    stable = detect.stable_mask([10 * np.log10(c[-1] / c[0]) for c in chans])
    p_scene, _ = detect.omnibus(chans, [bs.enl["HH"], bs.enl["HV"]], stable=stable)
    assert (p_scene[left] < detect.ALPHA).mean() > 0.03


def test_small_strata_use_the_scene_enl(monkeypatch):
    synth = Synth(DAYS)
    fakes = Fakes(monkeypatch, synth, DAYS)
    lc = np.full(GRID.shape, "forest", dtype="<U12")
    lc[:5, :20] = "water"  # 100 blocks: under the 200-block stratum minimum
    monkeypatch.setattr(refs, "nlcd", lambda grid: lc)
    bs = features.block_features(BBOX, read_passes=fakes.read_passes, s1=False)
    assert "water" not in bs.enl_by_stratum["HH"] and "forest" in bs.enl_by_stratum["HH"]


def test_too_few_blocks_propagates(monkeypatch):
    tiny = (-119.20, 48.15, -119.18, 48.17)  # 24 x 17 = 408 blocks, 40 of them valid
    g = grid_for_bbox(tiny, EPSG)
    rng = np.random.default_rng(3)

    def read_passes(granules, bbox, grid):
        out = []
        for gr in granules:
            lvl = 10 ** (rng.normal(-9, 2, g.shape) / 10)
            vf = np.zeros(g.shape)
            vf[:5, :8] = 1.0
            blocks = {k: np.where(vf > 0, lvl * rng.gamma(20, 1 / 20, g.shape), np.nan)
                      for k in ("HH", "HV", "HH30", "HV30")}
            out.append((_meta(gr), {**blocks, "valid_frac": vf}))
        return out

    Fakes(monkeypatch, Synth(DAYS), DAYS)
    with pytest.raises(detect.TooFewBlocks):
        features.block_features(tiny, read_passes=read_passes)


def test_no_stable_blocks_propagates(monkeypatch):
    synth = Synth(DAYS, enl=2000.0, enl30=2000.0, hv_drop_db=6.0, drop_everywhere=True)
    fakes = Fakes(monkeypatch, synth, DAYS)  # every block's HV falls 6 dB: nothing is stable
    with pytest.raises(detect.NoStableBlocks):
        features.block_features(BBOX, read_passes=fakes.read_passes)


# --- NLCD ----------------------------------------------------------------------------------------


def test_nlcd_majority_and_groups(monkeypatch):
    """Fake the MRLC WCS: a 30 m raster in the requested box; codes map to groups by majority."""
    calls = []

    class Resp:
        status_code = 200

        def __init__(self, content):
            self.content = content

        def raise_for_status(self):
            pass

    def fake_get(url, params=None, timeout=None, **kw):
        calls.append(params)
        x0, y0, x1, y1 = (float(v) for v in params["bbox"].split(","))
        w, h = int(params["width"]), int(params["height"])
        tf = from_origin(x0, y1, (x1 - x0) / w, (y1 - y0) / h)
        cc, rr = np.meshgrid(np.arange(w) + 0.5, np.arange(h) + 0.5)
        px, py = tf.c + tf.a * cc, tf.f + tf.e * rr  # Albers pixel centres; classes follow GRID
        gx, gy = Transformer.from_crs(5070, EPSG, always_xy=True).transform(px, py)
        col, row = (gx - GRID.xmin) / 100.0, (GRID.ymax - gy) / 100.0  # block coordinates
        codes = np.where(col < NX / 2, 42, 82).astype("uint8")  # forest | cultivated crops
        codes[row < NY / 4] = 11  # open water along the north
        codes[(row > NY - 8) & (col < 6)] = 0  # nodata in one corner
        with rasterio.MemoryFile() as mem:
            with mem.open(driver="GTiff", height=h, width=w, count=1, dtype="uint8",
                          crs=params["crs"], transform=tf, nodata=0) as ds:
                ds.write(codes, 1)
            return Resp(mem.read())

    monkeypatch.setattr(refs.requests, "get", fake_get)
    lc = refs.nlcd(GRID)
    assert lc.shape == GRID.shape and lc.dtype.kind == "U"
    assert calls and calls[0]["crs"] == "EPSG:5070" and calls[0]["service"] == "WCS"
    assert (lc[: NY // 4 - 2, 3:-3] == "water").all()
    assert (lc[NY // 2 : NY - 10, 8 : NX // 2 - 2] == "forest").all()
    assert (lc[NY // 2 : NY - 10, NX // 2 + 2 : -3] == "crops").all()
    assert (lc[NY - 4 :, :4] == "").all()  # the nodata corner is unknown, not a guess
    assert set(np.unique(lc)) <= set(refs.NLCD_GROUPS_ALL) | {""}
    assert refs.nlcd_group(42) == "forest" and refs.nlcd_group(52) == "shrub_grass"
    assert refs.nlcd_group(90) == "wetland" and refs.nlcd_group(23) == "developed"
    assert refs.nlcd_group(31) == "barren" and refs.nlcd_group(0) == ""


def test_nlcd_failure_gives_unknown(monkeypatch):
    def boom(*a, **k):
        raise OSError("no network")

    monkeypatch.setattr(refs.requests, "get", boom)
    monkeypatch.setattr(refs.read.time, "sleep", lambda s: None)
    lc = refs.nlcd(GRID)
    assert lc.shape == GRID.shape and (lc == "").all()  # unknown: features uses the scene ENL


# --- live ----------------------------------------------------------------------------------------


@pytest.mark.live
def test_live_nlcd_kaiser():
    lc = refs.nlcd(grid_for_bbox((-119.20, 48.15, -119.15, 48.19), 32610))
    names, counts = np.unique(lc, return_counts=True)
    assert "" not in names, dict(zip(names, counts))
    assert names[np.argmax(counts)] == "shrub_grass"  # Kaiser Canyon is shrub-steppe


@pytest.mark.live
def test_live_kaiser_blockset():
    """Kaiser Canyon fire (docs/research/kaiser-spike.md): the middle of the burn."""
    box = (-119.115, 48.157, -118.975, 48.257)  # ~10 x 11 km inside the perimeter
    bs = features.block_features(box, (date(2026, 7, 13), date(2026, 9, 11)))
    assert bs.stack.track == 71 and bs.stack.crid == "P05023"
    assert bs.dates[0] == date(2026, 7, 13) and bs.dates[-1] == date(2026, 9, 11)
    assert bs.s1 is not None and abs(bs.s1["offset_days"][0]) <= 6
    assert bs.valid.mean() > 0.9
    dvh, dhv = np.nanmedian(bs.rel_dVH), np.nanmedian(bs.rel_dHV)
    print("rel dVH", dvh, "rel dHV", dhv, "enl", bs.enl, "s1", bs.s1)
    assert dvh < dhv  # C-band VH falls further than L-band HV (the spike's direction)

