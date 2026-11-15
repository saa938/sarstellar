"""Tests for CMR search, de-duplication and stack building.

The fixtures in tests/fixtures/umm/ are real CMR UMM-G records recorded on 2026-11-14
(unmodified). Network tests are marked `live` and only run with `-m live`.
"""

from __future__ import annotations

import copy
import json
from datetime import UTC, date, datetime
from pathlib import Path

import pytest
import requests

from sarstellar import search
from sarstellar.types import Granule, Stack

FIXTURES = Path(__file__).parent / "fixtures" / "umm"
TULARE_BBOX = (-119.65, 36.00, -119.45, 36.15)
WINDOW = (date(2025, 10, 1), date(2026, 11, 14))

GCOV_FILES = [
    "gcov_t34_a_20251124_p05023.json",
    "gcov_t34_a_20260722_p05023.json",
    "gcov_t34_a_20261026_p05036_validated.json",
    "gcov_t114_d_20260622_p05023_001.json",
    "gcov_t114_d_20260622_p05023_002.json",
    "gcov_t114_d_20260716_p05023.json",
    "gcov_t114_d_20251212_5mhz_only.json",
    "gcov_t149_mixed_20260706_p05023.json",
]
RTC_FILES = [
    "rtc_t137_20260715_292328_iw2.json",
    "rtc_t137_20260715_292329_iw2.json",
    "rtc_t144_20260715_308014_iw2.json",
    "rtc_t144_20260721_308014_iw2.json",
]


def load_item(name: str) -> dict:
    """The full CMR item (`meta` + `umm`) as recorded."""
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))


def gran(name: str) -> Granule:
    return search.parse_umm(load_item(name)["umm"])


def make_granule(
    day: date, *, track=34, frame=20, bandwidth=40.0, crid="P05023", pol="DHDH"
) -> Granule:
    """A hand-built granule (real name format) for cases the recorded fixtures do not cover."""
    ur = (
        f"NISAR_L2_PR_GCOV_006_{track:03d}_A_{frame:03d}_4005_{pol}_A_"
        f"{day:%Y%m%d}T130000_{day:%Y%m%d}T130035_{crid}_N_F_J_001"
    )
    return Granule(
        ur=ur,
        url=f"https://example.invalid/{ur}.h5",
        collection="NISAR_L2_GCOV_PROVISIONAL_V1",
        start=datetime(day.year, day.month, day.day, 13, 0, 0, tzinfo=UTC),
        track=track,
        frame=frame,
        direction="A",
        bandwidth_mhz=bandwidth,
        crid=crid,
        counter=1,
        mixed_mode=False,
        size_gb=7.0,
    )


def D(month: int, day: int) -> date:
    return date(2026, month, day)


def fixture_stacks() -> list[Stack]:
    return search.build_stacks([gran(n) for n in GCOV_FILES])


# A fake CMR so unit tests never touch the network.
class FakeResponse:
    def __init__(self, items: list[dict], status: int = 200, headers: dict | None = None):
        self._items = items
        self.status_code = status
        self.headers = headers or {}

    def json(self) -> dict:
        return {"hits": len(self._items), "items": self._items}

    def raise_for_status(self) -> None:
        if self.status_code >= 400:
            raise requests.HTTPError(f"{self.status_code} from fake CMR")


class FakeCmr:
    """Replaces `requests.get`; records every call and replays queued responses."""

    def __init__(self, *responses: FakeResponse):
        self.responses = list(responses)
        self.calls: list[dict] = []

    def __call__(self, url, params=None, headers=None, timeout=None):
        self.calls.append({"url": url, "params": list(params), "headers": dict(headers or {})})
        return self.responses.pop(0)


def cmr(monkeypatch, *responses: FakeResponse) -> FakeCmr:
    fake = FakeCmr(*responses)
    monkeypatch.setattr(search.requests, "get", fake)
    return fake


@pytest.fixture
def no_sleep(monkeypatch):
    monkeypatch.setattr(search.time, "sleep", lambda _s: None)


# parse_umm
def test_parse_umm_reads_a_normal_provisional_granule():
    g = gran("gcov_t34_a_20251124_p05023.json")
    assert g.ur.endswith("20251124T130858_20251124T130933_P05023_N_F_J_001")
    assert g.collection == "NISAR_L2_GCOV_PROVISIONAL_V1"
    assert g.start == datetime(2025, 11, 24, 13, 8, 58, tzinfo=UTC)
    assert (g.track, g.frame, g.direction) == (34, 20, "A")
    assert g.bandwidth_mhz == 40.0
    assert (g.crid, g.counter) == ("P05023", 1)
    assert g.mixed_mode is False
    assert g.size_gb == pytest.approx(7.11, abs=0.01)
    # the HDF5 itself over HTTPS: not the S3 link, not a browse PNG, not the QA_STATS.h5
    assert g.url.startswith("https://")
    assert g.url.endswith(g.ur + ".h5")


def test_parse_umm_reads_validated_crid_and_collection():
    g = gran("gcov_t34_a_20261026_p05036_validated.json")
    assert (g.collection, g.crid) == ("NISAR_L2_GCOV_V1", "P05036")


def test_parse_umm_5mhz_only_granule_reports_5_mhz():
    # No FREQUENCY_A_* attributes at all: only the 5 MHz frequency B was acquired.
    g = gran("gcov_t114_d_20251212_5mhz_only.json")
    assert (g.bandwidth_mhz, g.direction) == (5.0, "D")


def test_parse_umm_flags_the_mixed_mode_product():
    g = gran("gcov_t149_mixed_20260706_p05023.json")
    assert (g.mixed_mode, g.bandwidth_mhz) == (True, 20.0)


def test_parse_umm_partial_frame_counts_as_mixed():
    # Partial frames (FULL_FRAME FALSE) cover only part of the box, so they cannot join a series.
    umm = copy.deepcopy(load_item("gcov_t34_a_20251124_p05023.json")["umm"])
    for attr in umm["AdditionalAttributes"]:
        if attr["Name"] == "FULL_FRAME":
            attr["Values"] = ["FALSE"]
    assert search.parse_umm(umm).mixed_mode is True


def test_parse_umm_rejects_a_record_with_no_hdf5_link():
    umm = copy.deepcopy(load_item("gcov_t34_a_20251124_p05023.json")["umm"])
    umm["RelatedUrls"] = [u for u in umm["RelatedUrls"] if not u["URL"].endswith(".h5")]
    with pytest.raises(ValueError, match="HDF5"):
        search.parse_umm(umm)


# dedupe
def test_dedupe_keeps_highest_counter():
    first = gran("gcov_t114_d_20260622_p05023_001.json")
    second = gran("gcov_t114_d_20260622_p05023_002.json")
    assert (first.counter, second.counter) == (1, 2)
    for order in ([first, second], [second, first]):
        kept = search.dedupe(order)
        assert len(kept) == 1
        assert kept[0].counter == 2
        assert kept[0].ur.endswith("_002")


def test_dedupe_leaves_distinct_acquisitions_alone():
    # 8 records, one of which is the _002 duplicate of another
    assert len(search.dedupe([gran(n) for n in GCOV_FILES])) == 7


def test_dedupe_keeps_same_pass_under_different_crids():
    # A reprocessing under a new CRID is a different product, not a duplicate delivery.
    a = make_granule(date(2026, 10, 26), crid="P05023")
    b = make_granule(date(2026, 10, 26), crid="P05036")
    assert len(search.dedupe([a, b])) == 2


# build_stacks
def test_drops_5mhz_and_mixed():
    kept = [g for s in fixture_stacks() for g in s.granules]
    assert kept, "the normal granules must survive"
    assert all(g.bandwidth_mhz >= 20.0 for g in kept)
    assert not any(g.mixed_mode for g in kept)
    assert not any("NADV" in g.ur for g in kept), "5 MHz-only granule leaked into a stack"
    assert not any("_M_" in g.ur for g in kept), "mixed-mode granule leaked into a stack"
    # and the duplicate was removed on the way in
    assert sum(1 for g in kept if g.start.date() == date(2026, 6, 22)) == 1


def test_stacks_group_by_track_direction_bandwidth_crid():
    stacks = fixture_stacks()
    keys = [(s.track, s.direction, s.bandwidth_mhz, s.crid) for s in stacks]
    assert len(keys) == len(set(keys))
    for s in stacks:
        assert {(g.track, g.direction, g.bandwidth_mhz, g.crid) for g in s.granules} == {
            (s.track, s.direction, s.bandwidth_mhz, s.crid)
        }
    assert (114, "D", 40.0, "P05023") in keys
    assert (34, "A", 40.0, "P05023") in keys


def test_stacks_split_by_crid():
    # P05023 (provisional) and P05036 (validated) may differ radiometrically, so their dates
    # must never share a series.
    by_crid = {s.crid: s for s in fixture_stacks() if s.track == 34}
    assert set(by_crid) == {"P05023", "P05036"}
    assert date(2026, 7, 22) in by_crid["P05023"].dates
    assert date(2026, 10, 26) not in by_crid["P05023"].dates
    assert by_crid["P05036"].dates == [date(2026, 10, 26)]


def test_stacks_sorted_by_date_count_descending():
    counts = [len(s.dates) for s in fixture_stacks()]
    assert counts == sorted(counts, reverse=True)
    # T114 D has 2 usable dates (Jun 22, Jul 16); T34 P05023 has 2 (Nov 24, Jul 22).
    assert counts[0] == 2


def test_stack_groups_several_frames_of_one_track_together():
    # Frame footprints shift between passes; the series is per track, not per frame.
    gs = [
        make_granule(date(2026, 5, 25), frame=64),
        make_granule(date(2026, 5, 13), frame=65),
        make_granule(date(2026, 5, 1), frame=64),
    ]
    stacks = search.build_stacks(gs)
    assert len(stacks) == 1
    assert stacks[0].dates == [date(2026, 5, 1), date(2026, 5, 13), date(2026, 5, 25)]
    assert [g.start.date() for g in stacks[0].granules] == stacks[0].dates  # in date order


def test_dual_pol_and_quad_pol_never_share_a_stack():
    # Same track, direction, bandwidth and CRID, but a dual-pol (DH) and a quad-pol (QP)
    # granule: different modes, so different series.
    pols = [(D(5, 1), "DHDH"), (D(5, 13), "QPDH"), (D(5, 25), "DHDH"), (D(6, 6), "QPDH")]
    stacks = search.build_stacks([make_granule(day, pol=pol) for day, pol in pols])
    assert len(stacks) == 2
    assert {(search.stack_polarization(s), len(s.dates)) for s in stacks} == {("DH", 2), ("QP", 2)}
    for s in stacks:
        assert {g.ur.split("_")[9][:2] for g in s.granules} == {search.stack_polarization(s)}
    # frequency B (the last two letters) does not matter: QPDH and QPQP are one mode
    same_a = [make_granule(D(5, 1), pol="QPDH"), make_granule(D(5, 13), pol="QPQP")]
    assert len(search.build_stacks(same_a)) == 1


def test_build_stacks_empty_input():
    assert search.build_stacks([]) == []


# pick_pair
def test_pick_pair_default_extremes():
    stack = fixture_stacks()[0]
    before, after = search.pick_pair(stack, None)
    assert before.start.date() == stack.dates[0]
    assert after.start.date() == stack.dates[-1]
    assert before.start < after.start


def pair_days(stack, asked) -> tuple[date, date]:
    before, after = search.pick_pair(stack, asked)
    return before.start.date(), after.start.date()


@pytest.mark.parametrize(
    ("asked", "expected"),
    [
        ((D(5, 13), D(5, 25)), (D(5, 13), D(5, 25))),  # passes on the requested days: as is
        ((D(5, 14), D(5, 20)), (D(5, 13), D(5, 25))),  # last pass on or before, first on or after
        ((D(5, 20), D(5, 14)), (D(5, 13), D(5, 25))),  # either order
        ((D(5, 15), D(5, 17)), (D(5, 13), D(5, 25))),  # both between two passes: bracketed
        ((D(4, 1), D(5, 20)), (D(5, 1), D(5, 25))),  # before the stack starts: first pass
        ((D(5, 14), D(6, 30)), (D(5, 13), D(5, 25))),  # after it ends: last pass
    ],
)
def test_pick_pair_with_explicit_dates_brackets_the_requested_interval(asked, expected):
    stack = search.build_stacks([make_granule(D(5, d)) for d in (1, 13, 25)])[0]
    assert pair_days(stack, asked) == expected


def test_pair_never_spans_gap_as_same_date():
    # NISAR has no data between 2026-07-27 22:03Z and 2026-08-10 00:55Z. A change that happens
    # inside the gap (Aug 1) must be bracketed by the last pass before it and the first pass
    # after it, and a pair must never be two granules of one date.
    stack = search.build_stacks([make_granule(D(m, d)) for m, d in ((7, 10), (7, 22), (8, 15))])[0]
    around_gap = (D(7, 22), D(8, 15))

    # Event on Aug 1: the "after" pass is never earlier than Aug 1 and the "before" pass is
    # never later than the date asked for (a pass day or not).
    assert pair_days(stack, (D(7, 10), D(8, 1))) == (D(7, 10), D(8, 15))
    assert pair_days(stack, (D(7, 20), D(8, 1))) == (D(7, 10), D(8, 15))
    # both requested dates inside the gap still give the two passes around it
    assert pair_days(stack, (D(7, 30), D(8, 1))) == around_gap
    assert pair_days(stack, (D(7, 30), D(8, 12))) == around_gap
    assert pair_days(stack, None) == (D(7, 10), D(8, 15))

    # no ordered pair of two different passes exists: refuse instead of returning one date twice
    for asked in ((D(7, 22), D(7, 22)), (D(6, 1), D(6, 5)), (D(9, 1), D(9, 5))):
        with pytest.raises(ValueError, match="same acquisition"):
            search.pick_pair(stack, asked)  # one day twice; wholly before; wholly after the data


def test_pick_pair_refuses_a_single_date_stack_even_with_two_frames():
    gs = [make_granule(date(2026, 5, 1), frame=64), make_granule(date(2026, 5, 1), frame=65)]
    stack = search.build_stacks(gs)[0]
    assert len(stack.granules) == 2 and len(stack.dates) == 1
    with pytest.raises(ValueError, match="two"):
        search.pick_pair(stack, None)


def test_pick_pair_picks_the_lowest_frame_when_frames_share_a_date():
    gs = [
        make_granule(date(2026, 5, 1), frame=65),
        make_granule(date(2026, 5, 1), frame=64),
        make_granule(date(2026, 5, 13), frame=64),
    ]
    stack = search.build_stacks(gs)[0]
    before, _ = search.pick_pair(stack, None)
    assert before.frame == 64
    assert [g.frame for g in search.granules_on(stack, date(2026, 5, 1))] == [64, 65]


# search_gcov: the CMR query
def test_beta_never_returned(monkeypatch):
    # Even if CMR hands back a BETA granule, it must not come out of search_gcov.
    items = [load_item("gcov_t34_a_20251124_p05023.json")]
    items.append(load_item("gcov_beta_t5_a_20251017_x05009.json"))
    fake = cmr(monkeypatch, FakeResponse(items))

    out = search.search_gcov(TULARE_BBOX, *WINDOW)

    params = fake.calls[0]["params"]
    short_names = [v for k, v in params if k == "short_name"]
    assert sorted(short_names) == ["NISAR_L2_GCOV_PROVISIONAL_V1", "NISAR_L2_GCOV_V1"]
    assert not any("BETA" in str(v) for _k, v in params)
    assert [g.collection for g in out] == ["NISAR_L2_GCOV_PROVISIONAL_V1"]


def test_search_gcov_builds_the_box_and_time_window(monkeypatch):
    fake = cmr(monkeypatch, FakeResponse([]))
    search.search_gcov((-119.65, 36.0, -119.45, 36.15), date(2026, 6, 1), date(2026, 10, 31))
    params = {k: v for k, v in fake.calls[0]["params"] if k != "short_name"}
    assert params["bounding_box"] == "-119.65,36.0,-119.45,36.15"
    assert params["temporal"] == "2026-06-01T00:00:00Z,2026-10-31T23:59:59Z"
    assert fake.calls[0]["url"].endswith("/granules.umm_json")


def test_search_gcov_skips_records_it_cannot_parse(monkeypatch):
    bad = copy.deepcopy(load_item("gcov_t34_a_20251124_p05023.json"))
    bad["umm"]["GranuleUR"] = "NISAR_not_a_gcov_name"
    cmr(monkeypatch, FakeResponse([bad, load_item("gcov_t34_a_20260722_p05023.json")]))
    assert len(search.search_gcov(TULARE_BBOX, *WINDOW)) == 1


def test_cmr_paging_follows_search_after_and_results_come_back_oldest_first(monkeypatch):
    monkeypatch.setattr(search, "PAGE_SIZE", 2)
    page1 = [
        load_item("gcov_t34_a_20260722_p05023.json"),
        load_item("gcov_t34_a_20251124_p05023.json"),
    ]
    page2 = [load_item("gcov_t114_d_20260716_p05023.json")]
    fake = cmr(
        monkeypatch,
        FakeResponse(page1, headers={"CMR-Search-After": "cursor-1"}),
        FakeResponse(page2),
    )
    out = search.search_gcov(TULARE_BBOX, *WINDOW)
    assert [g.start.date() for g in out] == [
        date(2025, 11, 24),
        date(2026, 7, 16),
        date(2026, 7, 22),
    ]
    assert "CMR-Search-After" not in fake.calls[0]["headers"]
    assert fake.calls[1]["headers"]["CMR-Search-After"] == "cursor-1"


def test_cmr_retries_a_transient_server_error(monkeypatch, no_sleep):
    ok = FakeResponse([load_item("gcov_t34_a_20251124_p05023.json")])
    fake = cmr(monkeypatch, FakeResponse([], status=503), ok)
    assert len(search.search_gcov(TULARE_BBOX, *WINDOW)) == 1
    assert len(fake.calls) == 2


def test_cmr_gives_up_after_repeated_errors(monkeypatch, no_sleep):
    fake = cmr(monkeypatch, *[FakeResponse([], status=502) for _ in range(search.CMR_ATTEMPTS)])
    with pytest.raises(requests.HTTPError):
        search.search_gcov(TULARE_BBOX, *WINDOW)
    assert len(fake.calls) == search.CMR_ATTEMPTS


@pytest.mark.parametrize(
    ("bbox", "start", "end"),
    [
        ((-119.45, 36.0, -119.65, 36.15), date(2026, 1, 1), date(2026, 2, 1)),  # west > east
        ((-119.65, 36.15, -119.45, 36.0), date(2026, 1, 1), date(2026, 2, 1)),  # south > north
        ((-119.65, 36.0, -119.45), date(2026, 1, 1), date(2026, 2, 1)),  # three numbers
        (TULARE_BBOX, date(2026, 2, 1), date(2026, 1, 1)),  # end before start
    ],
)
def test_search_rejects_bad_input_before_calling_cmr(monkeypatch, bbox, start, end):
    fake = cmr(monkeypatch)
    with pytest.raises(ValueError):
        search.search_gcov(bbox, start, end)
    assert fake.calls == []


# search_rtc_s1
def test_rtc_groups_bursts_by_track_and_date(monkeypatch):
    cmr(monkeypatch, FakeResponse([load_item(n) for n in RTC_FILES]))
    out = search.search_rtc_s1(TULARE_BBOX, date(2026, 7, 15))
    assert {(r["track"], r["date"]) for r in out} == {
        (137, date(2026, 7, 15)),
        (144, date(2026, 7, 15)),
        (144, date(2026, 7, 21)),
    }
    t137 = next(r for r in out if r["track"] == 137)
    assert set(t137) == {"track", "date", "urls_vv", "urls_vh"}
    # two bursts of the same pass end up in the same group, VV and VH aligned by burst
    assert len(t137["urls_vv"]) == len(t137["urls_vh"]) == 2
    for vv, vh in zip(t137["urls_vv"], t137["urls_vh"], strict=True):
        assert vv.endswith("_VV.tif") and vh.endswith("_VH.tif")
        assert vv[: -len("_VV.tif")] == vh[: -len("_VH.tif")]
        assert vv.startswith("https://")


def test_rtc_nearest_date_first_and_max_days(monkeypatch):
    items = [load_item(n) for n in RTC_FILES]
    cmr(monkeypatch, FakeResponse(items), FakeResponse(items))
    out = search.search_rtc_s1(TULARE_BBOX, date(2026, 7, 20))
    deltas = [abs((r["date"] - date(2026, 7, 20)).days) for r in out]
    assert deltas == sorted(deltas)
    assert out[0]["date"] == date(2026, 7, 21)
    near = search.search_rtc_s1(TULARE_BBOX, date(2026, 7, 20), max_days=2)
    assert [r["date"] for r in near] == [date(2026, 7, 21)]


def test_rtc_queries_only_the_rtc_collection_in_a_window_around_the_date(monkeypatch):
    fake = cmr(monkeypatch, FakeResponse([]))
    search.search_rtc_s1(TULARE_BBOX, date(2026, 7, 20), max_days=6)
    params = fake.calls[0]["params"]
    assert [v for k, v in params if k == "short_name"] == ["OPERA_L2_RTC-S1_V1"]
    assert (
        next(v for k, v in params if k == "temporal") == "2026-07-14T00:00:00Z,2026-07-26T23:59:59Z"
    )


def test_rtc_keeps_the_newest_reprocessing_of_a_burst(monkeypatch):
    old = load_item("rtc_t137_20260715_292328_iw2.json")
    newer = copy.deepcopy(old)
    # same burst and acquisition, produced later -> the superseded delivery is dropped
    swap = lambda s: s.replace("20261010T052116Z", "20261101T000000Z")
    newer["umm"]["GranuleUR"] = swap(newer["umm"]["GranuleUR"])
    for link in newer["umm"]["RelatedUrls"]:
        link["URL"] = swap(link["URL"])
    cmr(monkeypatch, FakeResponse([old, newer]))
    out = search.search_rtc_s1(TULARE_BBOX, date(2026, 7, 15))
    assert len(out) == 1
    assert len(out[0]["urls_vv"]) == 1
    assert "20261101T000000Z" in out[0]["urls_vv"][0]


def test_rtc_no_scenes_gives_an_empty_list(monkeypatch):
    cmr(monkeypatch, FakeResponse([]))
    assert search.search_rtc_s1(TULARE_BBOX, date(2026, 7, 15)) == []


# live (network)
@pytest.mark.live
def test_live_search_tulare():
    gs = search.search_gcov(TULARE_BBOX, date(2025, 10, 29), date(2026, 11, 14))
    assert len(gs) >= 20
    assert not any("BETA" in g.collection for g in gs)
    stacks = search.build_stacks(gs)
    assert stacks, "Tulare has two dense tracks"
    assert len(stacks[0].dates) >= 10
    before, after = search.pick_pair(stacks[0], None)
    assert before.start < after.start


@pytest.mark.live
def test_live_search_rtc_tulare():
    out = search.search_rtc_s1(TULARE_BBOX, date(2026, 7, 15))
    assert out, "OPERA RTC-S1 covers Tulare within 6 days of 2026-07-15"
    assert all(r["urls_vv"] for r in out)
    assert out == sorted(out, key=lambda r: abs((r["date"] - date(2026, 7, 15)).days))
