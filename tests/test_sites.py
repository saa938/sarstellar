"""Site sampling for the national scorecard: helpers, pair search, and the generated sites.json."""

from __future__ import annotations

import json
import math
import re
import sys
from datetime import UTC, date, datetime, timedelta
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))  # `modal_app` sits beside `tests`, not under `core`

from modal_app import sites

from sarstellar.types import Granule

SITES_JSON = ROOT / "modal_app" / "data" / "sites.json"
KINDS = ("forest_loss", "fire", "flood", "crops", "stable")


# --- geometry helpers ----------------------------------------------------------------------------


def km(box):
    """(height, width) of a lon/lat box in km, near its centre latitude."""
    w, s, e, n = box
    return (n - s) * 111.32, (e - w) * 111.32 * math.cos(math.radians((s + n) / 2))


def test_box_around_is_ten_km_square():
    for lat in (30.0, 45.0, 60.0):
        box = sites.box_around(-100.0, lat)
        height, width = km(box)
        assert abs(height - 10) < 0.1 and abs(width - 10) < 0.1
        assert box[0] < -100 < box[2] and box[1] < lat < box[3]


def test_overlap_fraction_and_drop_overlaps():
    a = sites.box_around(-100.0, 40.0)
    shifted = sites.box_around(-100.0 + 0.05, 40.0)  # about 40% of the width overlaps... less
    far = sites.box_around(-99.0, 40.0)
    assert sites.overlap_fraction(a, a) == pytest.approx(1.0)
    assert sites.overlap_fraction(a, far) == 0.0
    assert 0.4 < sites.overlap_fraction(a, shifted) < 0.7
    kept = sites.drop_overlaps(
        [{"bbox": a, "id": 1}, {"bbox": shifted, "id": 2}, {"bbox": far, "id": 3}]
    )
    assert [s["id"] for s in kept] == [1, 3]  # first come, first kept
    nearly_touching = sites.box_around(-100.0 + 0.09, 40.0)  # shares well under 25%
    assert len(sites.drop_overlaps([{"bbox": a}, {"bbox": nearly_touching}])) == 2


def test_utm_epsg():
    assert sites.utm_epsg(-122.3, 47.6) == 32610
    assert sites.utm_epsg(-94.2, 30.3) == 32615
    assert sites.utm_epsg(-70.0, 44.0) == 32619


# --- site schema ---------------------------------------------------------------------------------


def good_site(**over):
    site = {
        "id": "fire-wa-01",
        "kind": "fire",
        "bbox": [-119.4, 48.1, -119.27, 48.19],
        "state": "WA",
        "nisar_pair": ["NISAR_pre", "NISAR_post"],
        "s1": {"track": 115, "dates": ["2026-07-13", "2026-09-11"], "offset_days": [0, 0]},
        "ref_window": ["2026-07-16", "2026-08-20"],
    }
    site.update(over)
    return site


def test_validate_site_accepts_a_good_site_and_a_site_without_sentinel1():
    assert sites.validate_site(good_site()) == []
    assert sites.validate_site(good_site(s1=None)) == []


@pytest.mark.parametrize(
    "over",
    [
        {"kind": "volcano"},
        {"state": "Washington"},
        {"bbox": [-119.3, 48.1, -119.4, 48.19]},  # west >= east
        {"bbox": [-119.4, 48.19, -119.27, 48.1]},  # south >= north
        {"bbox": [-200.0, 48.1, -199.9, 48.19]},  # outside US bounds
        {"bbox": [-119.8, 48.1, -119.27, 48.19]},  # wider than 20 km
        {"nisar_pair": ["only_one"]},
        {"ref_window": ["2026-09-01", "2026-08-01"]},
        {"ref_window": ["2026-07-16"]},
        {"s1": {"track": 115}},
        {"id": ""},
    ],
)
def test_validate_site_rejects_bad_sites(over):
    assert sites.validate_site(good_site(**over)), over


# --- NISAR pair search (CMR and footprints replaced) ---------------------------------------------


def gran(track: int, day: date, frame: int = 64, crid: str = "P05023", direction: str = "D"):
    stamp = f"{day:%Y%m%d}T031853"
    ur = (
        f"NISAR_L2_PR_GCOV_020_{track:03d}_{direction}_{frame:03d}_4005_DHDH_A_{stamp}"
        f"_{day:%Y%m%d}T031928_{crid}_N_F_J_001"
    )
    return Granule(
        ur=ur, url="https://x/" + ur, collection="NISAR_L2_GCOV_PROVISIONAL_V1",
        start=datetime(day.year, day.month, day.day, 3, 18, tzinfo=UTC), track=track, frame=frame,
        direction=direction, bandwidth_mhz=40.0, crid=crid, counter=1, mixed_mode=False, size_gb=7.0,
    )  # fmt: skip


def passes(track, first: date, n: int, **kw):
    return [gran(track, first + timedelta(days=12 * i), **kw) for i in range(n)]


@pytest.fixture
def full_cover(monkeypatch):
    monkeypatch.setattr(sites, "box_coverage", lambda box, urs: 1.0)


def patch_search(monkeypatch, granules):
    monkeypatch.setattr(sites, "search_gcov", lambda box, start, end: list(granules))


BOX = sites.box_around(-119.0, 48.2)


def test_find_nisar_pair_brackets_the_window(monkeypatch, full_cover):
    patch_search(monkeypatch, passes(71, date(2026, 6, 1), 10))  # Jun 1, 13, 25, Jul 7, 19, 31, ...
    got = sites.find_nisar_pair(BOX, (date(2026, 7, 16), date(2026, 8, 20)))
    assert got is not None
    assert got["dates"] == ["2026-07-07", "2026-08-24"]  # last pass <= Jul 16, first >= Aug 20
    assert got["track"] == 71 and got["direction"] == "D"
    assert len(got["nisar_pair"]) == 2 and all(u.startswith("NISAR_") for u in got["nisar_pair"])
    assert got["slack_days"] == [9, 4]


def test_find_nisar_pair_prefers_the_tightest_stack(monkeypatch, full_cover):
    loose = passes(71, date(2026, 6, 1), 10)
    tight = passes(34, date(2026, 6, 14), 10, direction="A")  # Jun 14, 26, Jul 8, 20, Aug 1, 13, 25
    patch_search(monkeypatch, loose + tight)
    got = sites.find_nisar_pair(BOX, (date(2026, 7, 20), date(2026, 8, 13)))
    assert got["track"] == 34 and got["slack_days"] == [0, 0]


def test_find_nisar_pair_none_when_no_pass_on_one_side(monkeypatch, full_cover):
    patch_search(monkeypatch, passes(71, date(2026, 6, 1), 4))  # last pass Jul 7
    assert sites.find_nisar_pair(BOX, (date(2026, 7, 16), date(2026, 8, 20))) is None
    assert sites.find_nisar_pair(BOX, (date(2026, 5, 1), date(2026, 5, 20))) is None


def test_find_nisar_pair_none_when_slack_too_big(monkeypatch, full_cover):
    # Passes Jun 1 and Sep 1 only: a window in the middle has 40+ days of slack on both sides.
    patch_search(monkeypatch, [gran(71, date(2026, 6, 1)), gran(71, date(2026, 9, 1))])
    assert sites.find_nisar_pair(BOX, (date(2026, 7, 15), date(2026, 7, 25))) is None
    wide = sites.find_nisar_pair(BOX, (date(2026, 7, 15), date(2026, 7, 25)), slack=(60, 60))
    assert wide is not None and wide["dates"] == ["2026-06-01", "2026-09-01"]


def test_find_nisar_pair_none_when_footprints_miss_the_box(monkeypatch):
    patch_search(monkeypatch, passes(71, date(2026, 6, 1), 10))
    monkeypatch.setattr(sites, "box_coverage", lambda box, urs: 0.4)
    assert sites.find_nisar_pair(BOX, (date(2026, 7, 16), date(2026, 8, 20))) is None


def test_find_nisar_pair_never_mixes_stacks(monkeypatch, full_cover):
    # Track 71 has only the early pass, track 34 only the late one: no same-stack pair.
    patch_search(
        monkeypatch, [gran(71, date(2026, 7, 1)), gran(34, date(2026, 8, 30), direction="A")]
    )
    assert sites.find_nisar_pair(BOX, (date(2026, 7, 10), date(2026, 8, 25))) is None


def test_find_season_pair_uses_the_stacks_own_dates(monkeypatch, full_cover):
    # A stack that only runs Jun 14 - Oct 15 (no pass before June or after October) still pairs.
    patch_search(
        monkeypatch, passes(71, date(2026, 6, 14), 9)
    )  # Jun 14, 26, Jul 8, ... Sep 20, Oct 2
    got = sites.find_season_pair(BOX)
    d0, d1 = (date.fromisoformat(d) for d in got["dates"])
    assert 36 <= (d1 - d0).days <= 120 and got["slack_days"] == [0, 0] and got["track"] == 71
    assert abs((d1 - d0).days - 84) <= 12  # closest to seven repeat cycles


def test_find_season_pair_none_without_two_passes_far_enough_apart(monkeypatch, full_cover):
    patch_search(monkeypatch, passes(71, date(2026, 6, 14), 2))  # 12 days apart: too short
    assert sites.find_season_pair(BOX) is None
    monkeypatch.setattr(sites, "box_coverage", lambda box, urs: 0.2)
    patch_search(monkeypatch, passes(71, date(2026, 6, 14), 9))
    assert sites.find_season_pair(BOX) is None


# --- Sentinel-1 pair -----------------------------------------------------------------------------


def scene(track, day):
    return {"track": track, "date": day, "urls_vv": ["a_VV.tif"], "urls_vh": ["a_VH.tif"]}


def test_find_s1_pair_picks_one_track_nearest_both_dates(monkeypatch):
    pre, post = date(2026, 7, 7), date(2026, 8, 24)

    def fake(box, around, max_days=6):
        if around == pre:
            return [
                scene(115, date(2026, 7, 7)),
                scene(166, date(2026, 7, 5)),
                scene(64, date(2026, 7, 9)),
            ]
        return [
            scene(166, date(2026, 8, 22)),
            scene(115, date(2026, 8, 28)),
            scene(40, date(2026, 8, 24)),
        ]

    monkeypatch.setattr(sites, "search_rtc_s1", fake)
    got = sites.find_s1_pair(BOX, pre, post)
    # Track 166 is off by 2 + 2 = 4 days; track 115 by 0 + 4 = 4. Tie goes to the lower track.
    assert got == {"track": 115, "dates": ["2026-07-07", "2026-08-28"], "offset_days": [0, 4]}


def test_find_s1_pair_none_without_a_shared_track(monkeypatch):
    monkeypatch.setattr(
        sites,
        "search_rtc_s1",
        lambda b, a, max_days=6: [scene(115, a)] if a.month == 7 else [scene(166, a)],
    )
    assert sites.find_s1_pair(BOX, date(2026, 7, 7), date(2026, 8, 24)) is None


# --- fire windows and boxes ----------------------------------------------------------------------


def test_fire_window_uses_containment_then_out_date_then_a_short_default():
    rec = {
        "discovered": date(2026, 7, 16),
        "contained": date(2026, 8, 5),
        "out": None,
        "acres": 5000,
    }
    assert sites.fire_window(rec) == (date(2026, 7, 16), date(2026, 8, 5))
    rec["contained"], rec["out"] = None, date(2026, 8, 10)
    assert sites.fire_window(rec) == (date(2026, 7, 16), date(2026, 8, 10))
    rec["out"] = None
    assert sites.fire_window(rec) == (date(2026, 7, 16), date(2026, 7, 30))  # discovery + 14 d
    assert sites.fire_window({**rec, "acres": 50000}) is None  # big and undated: end unknown
    long_fire = {**rec, "contained": date(2026, 12, 1)}
    assert sites.fire_window(long_fire) == (date(2026, 7, 16), date(2026, 8, 30))  # capped at 45 d
    assert sites.fire_window({**rec, "discovered": None}) is None


def test_fire_boxes_centre_small_fires_and_take_the_edge_of_big_ones():
    from shapely.geometry import box as shp_box

    small = shp_box(-119.05, 48.15, -119.00, 48.19)  # about 4 x 4.5 km
    (b,) = sites.fire_boxes(small.__geo_interface__, acres=2500)
    assert b[0] < -119.0 < b[2] and b[1] < 48.17 < b[3]  # the box takes in the whole burn

    big = shp_box(-120.0, 47.0, -118.0, 48.0)  # about 150 x 110 km
    boxes = sites.fire_boxes(big.__geo_interface__, acres=900_000)
    assert len(boxes) == 2
    edge, inner = (shp_box(*b) for b in boxes)
    assert 0.2 < big.intersection(edge).area / edge.area < 0.8  # straddles the perimeter
    assert big.intersection(inner).area / inner.area > 0.95  # entirely burned


# --- the generated file --------------------------------------------------------------------------


@pytest.fixture(scope="module")
def generated():
    if not SITES_JSON.exists():
        pytest.fail("modal_app/data/sites.json is missing: run `python modal_app/sites.py`")
    return json.loads(SITES_JSON.read_text())


def ur_date(ur: str) -> date:
    return datetime.strptime(re.search(r"_(\d{8})T\d{6}_\d{8}T\d{6}_", ur)[1], "%Y%m%d").date()


def test_sites_schema_and_counts(generated):
    # Relaxed from the brief's 300 / 30 per kind / 4 states per kind / 15 states by the controller
    # (ruling: 150 / 20 / 3 / 8), because the data supports fewer verified sites. See the report.
    assert len(generated) >= 150
    assert len({s["id"] for s in generated}) == len(generated)
    for s in generated:
        assert sites.validate_site(s) == [], s["id"]
    by_kind = {k: [s for s in generated if s["kind"] == k] for k in KINDS}
    for kind, group in by_kind.items():
        assert len(group) >= 20, kind
        assert len({s["state"] for s in group}) >= 3, f"{kind} needs 3+ states for the hold-out"
    assert len({s["state"] for s in generated}) >= 8


def test_sites_do_not_overlap_more_than_a_quarter(generated):
    boxes = [s["bbox"] for s in generated]
    for i, a in enumerate(boxes):
        for b in boxes[i + 1 :]:
            assert sites.overlap_fraction(a, b) <= sites.MAX_OVERLAP, (a, b)


def test_every_site_pair_spans_its_ref_window(generated):
    for s in generated:
        pre, post = (ur_date(u) for u in s["nisar_pair"])
        start, end = (date.fromisoformat(d) for d in s["ref_window"])
        assert pre < post, s["id"]
        assert pre <= start and post >= end, s["id"]
        assert (start - pre).days <= 30 and (post - end).days <= 30, s["id"]
        assert all(re.search(r"_P0\d{4}_", u) for u in s["nisar_pair"])
        crids = {re.search(r"_(P0\d{4})_", u)[1] for u in s["nisar_pair"]}
        assert len(crids) == 1, f"{s['id']} mixes processing versions"
        track_pre, track_post = (re.search(r"_(\d{3})_[AD]_", u)[1] for u in s["nisar_pair"])
        assert track_pre == track_post, s["id"]
