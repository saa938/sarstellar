"""The `run_box` pipeline, the reference lookups and the notebook export.

Offline tests run the whole path (search -> stack -> read -> blocks -> change test -> areas ->
rules -> overlays -> explanation -> Result) on a synthetic scene with fake reads, a fake CMR search
and monkeypatched reference lookups. `test_features` supplies the fakes. The `live` test runs the
real Kaiser Canyon box (needs ~/_netrc, run with `-m live`).
"""

from __future__ import annotations

import base64
from datetime import date
from types import SimpleNamespace

import nbformat
import numpy as np
import pytest

from sarstellar import notebook, pipeline, refs
from sarstellar.grid import grid_for_bbox
from sarstellar.types import ChangeArea, Evidence, NoUsablePasses, Result
from test_features import BBOX, DAYS, EPSG, Fakes, _gamma
from test_search import make_granule

REAL = SimpleNamespace(**{n: getattr(refs, n) for n in
                          ("svi_tracts", "nifc_perimeters", "firms_count", "weather")})
NO_VALID = "Most of this box has no valid radar data."
NO_S1 = "No Sentinel-1 pass within 6 days; showing NISAR only."
PATCH = np.s_[20:24, 20:25]  # 20 blocks


class Scene:
    """Synthetic NISAR + Sentinel-1 scene: HV drop patches (L), VH drop patches (C), an ocean."""

    def __init__(self, days, bbox=BBOX, *, patches=(PATCH,), hv_drop_db=3.5, hh_drop_db=0.0, c_patches=(),
                 ocean_cols=0, seed=3, enl=100.0):
        rng = np.random.default_rng(seed)
        ny, nx = grid_for_bbox(bbox, EPSG).shape
        hh_db = rng.normal(-9.0, 2.0, (ny, nx))
        lvl = {"HH": 10 ** (hh_db / 10), "HV": 10 ** ((hh_db - 6.5) / 10),
               "VV": 10 ** ((hh_db - 2.0) / 10), "VH": 10 ** ((hh_db - 9.0) / 10)}
        self.L, self.C = {}, {}
        for i, d in enumerate(days):
            hv_scale, hh_scale = np.ones((ny, nx)), np.ones((ny, nx))
            vh_scale = np.ones((ny, nx))
            for patch in patches:
                hv_scale[patch] = 10 ** (-hv_drop_db / 10) if i >= 1 else 1.0
                hh_scale[patch] = 10 ** (-hh_drop_db / 10) if i >= 1 else 1.0
            for patch in c_patches:
                vh_scale[patch] = 10 ** (-3.5 / 10) if i >= 1 else 1.0
            frac = np.ones((ny, nx))
            frac[:, :ocean_cols] = 0.0
            self.L[d] = {
                "HH": _gamma(rng, lvl["HH"] * hh_scale, enl), "HV": _gamma(rng, lvl["HV"] * hv_scale, enl),
                "HH30": _gamma(rng, lvl["HH"] * hh_scale, enl / 4), "HV30": _gamma(rng, lvl["HV"] * hv_scale, enl / 4),
                "valid_frac": frac,
            }
            self.C[d] = {"VV": _gamma(rng, lvl["VV"], enl),
                         "VH": _gamma(rng, lvl["VH"] * vh_scale, enl)}


@pytest.fixture(autouse=True)
def offline_refs(monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.setattr("time.sleep", lambda s: None)  # reference lookups retry with a pause
    monkeypatch.setattr(refs, "svi_tracts", lambda bbox: [])
    monkeypatch.setattr(refs, "nifc_perimeters", lambda bbox, year=2026: [])
    monkeypatch.setattr(refs, "firms_count", lambda geometry, start, end: 0)
    monkeypatch.setattr(refs, "weather",
                        lambda lon, lat, when: {"min_temp_c": 12.0, "rain_mm": 0.0})


def run(monkeypatch, scene=None, *, bbox=BBOX, days=DAYS, scenes=None, **kw):
    scene = scene or Scene(days, bbox)
    fakes = Fakes(monkeypatch, scene, days, scenes=scenes)
    result = pipeline.run_box(bbox, read_passes=fakes.read_passes, **kw)
    return result, fakes


# --- the brief's cases --------------------------------------------------------------------------


def test_no_stack_raises(monkeypatch):
    start, end = date(2026, 7, 1), date(2026, 10, 1)
    mixed = make_granule(DAYS[0])
    mixed.mixed_mode = True
    for granules in ([], [make_granule(DAYS[0])], [mixed]):
        monkeypatch.setattr(pipeline.features.search, "search_gcov", lambda b, s, e, g=granules: g)
        with pytest.raises(NoUsablePasses) as exc:
            pipeline.run_box(BBOX, (start, end), read_passes=pytest.fail)
        assert str(exc.value) == (
            f"No calibrated NISAR passes cover this box between {start} and {end}."
        )


def test_mostly_invalid_box_few_blocks(monkeypatch):
    """90% of the mask is fill: under 200 usable blocks, so the ENL cannot be estimated."""
    result, _ = run(monkeypatch, Scene(DAYS, ocean_cols=71))  # 71 of 79 columns
    assert result.areas == [] and result.message == NO_VALID
    assert result.nisar["track"] == 71 and result.nisar["dates"] == [d.isoformat() for d in DAYS]
    assert result.s1 is None and result.people == {"svi_tracts": []}
    assert set(result.overlays) == {"change_png", "l_png", "c_png", "before_png", "after_png",
                                    "bounds"}
    assert len(result.overlays["bounds"]) == 4
    Result.from_json(result.to_json())  # a valid Result, not a half-built one


def test_mostly_invalid_box_under_20_percent(monkeypatch):
    """A big box where 85% is fill: plenty of blocks left, but under 20% of the box is valid."""
    big = (-119.25, 48.12, -119.05, 48.27)
    ny, nx = grid_for_bbox(big, EPSG).shape
    result, _ = run(monkeypatch, Scene(DAYS, big, ocean_cols=int(nx * 0.85)), bbox=big)
    assert ny * nx * 0.15 > 1000  # so TooFewBlocks is not what fires
    assert result.areas == [] and result.message == NO_VALID
    assert result.nisar["track"] == 71


def test_half_valid_box_still_runs(monkeypatch):
    big = (-119.25, 48.12, -119.05, 48.27)
    _, nx = grid_for_bbox(big, EPSG).shape
    scene = Scene(DAYS, big, ocean_cols=nx // 2, patches=(np.s_[40:44, 100:105],))
    result, _ = run(monkeypatch, scene, bbox=big)
    assert result.message is None and len(result.areas) == 1


def test_no_s1_pair(monkeypatch):
    scenes = Fakes._scenes(DAYS, offsets=(10, 10))  # RTC passes exist, but 10 days away
    result, _ = run(monkeypatch, scenes=scenes)
    assert result.s1 is None and result.message == NO_S1
    assert result.areas and all(a.agreement == "L" for a in result.areas)
    for a in result.areas:
        assert all(v is None for v in a.series["VV"] + a.series["VH"])


def test_end_to_end_synthetic(monkeypatch):
    ticks = []
    result, _ = run(monkeypatch, progress=lambda f, m: ticks.append((f, m)))
    assert result.message is None and result.fixture is False
    assert result.bbox == list(BBOX)
    assert len(result.areas) == 1
    a = result.areas[0]
    assert a.cls == "forest_loss" and a.agreement == "L"
    assert a.area_ha == pytest.approx(20, abs=2)
    assert a.geometry["type"] in ("Polygon", "MultiPolygon")
    assert a.id and a.p_value < 1e-3 and a.change_date == DAYS[1].isoformat()
    # nisar / s1 blocks of the contract
    assert result.nisar == {"track": 71, "direction": "A", "dates": [d.isoformat() for d in DAYS]}
    assert result.s1["track"] == 115 and len(result.s1["dates"]) == 2
    # series: one timeline holding every NISAR and Sentinel-1 date, nulls where a sensor is absent
    s = a.series
    assert set(s) == {"dates", "HH", "HV", "VV", "VH"}
    assert all(len(s[k]) == len(s["dates"]) for k in ("HH", "HV", "VV", "VH"))
    assert {d.isoformat() for d in DAYS} <= set(s["dates"])
    assert sorted(s["dates"]) == s["dates"]
    hv = [v for d, v in zip(s["dates"], s["HV"]) if d in {x.isoformat() for x in DAYS}]
    assert hv[1] - hv[0] == pytest.approx(-3.5, abs=0.6) and None not in hv
    assert any(v is not None for v in s["VH"])
    # overlays: five data URLs and four lon/lat corners
    for k in ("change_png", "l_png", "c_png", "before_png", "after_png"):
        assert result.overlays[k].startswith("data:image/png;base64,")
    base64.b64decode(result.overlays["change_png"].split(",", 1)[1])
    assert len(result.overlays["bounds"]) == 4 and len(result.overlays["bounds"][0]) == 2
    # progress runs 0..1, in order, ending at 1.0
    fracs = [f for f, _ in ticks]
    assert fracs == sorted(fracs) and fracs[-1] == 1.0 and 0.9 in fracs
    # the JSON round trip the API relies on
    assert Result.from_json(result.to_json()).to_json() == result.to_json()


def test_carry_forward_stats_are_set(monkeypatch):
    """frac_significant, landcover and the evidence reach the label (A5 carry-forward)."""
    result, _ = run(monkeypatch)
    a = result.areas[0]
    labels = [e.label for e in a.evidence]
    assert "Rule fired" in labels and "HV change" in labels and "Land cover" in labels
    assert a.confidence_label in ("High", "Medium") and 0.5 <= a.confidence <= 1.0
    hv = next(e for e in a.evidence if e.label == "HV change")
    assert hv.ci is not None and hv.ci[0] <= hv.value <= hv.ci[1]
    assert a.plain_text and "ha" in a.plain_text  # template text, no key


def test_both_sensors_agree(monkeypatch):
    scene = Scene(DAYS, c_patches=(PATCH,))
    result, _ = run(monkeypatch, scene)
    assert [a.agreement for a in result.areas] == ["both"]


def test_c_only_area(monkeypatch):
    scene = Scene(DAYS, patches=(), c_patches=(PATCH,))
    result, _ = run(monkeypatch, scene)
    assert [a.agreement for a in result.areas] == ["C"]
    assert result.areas[0].change_date == result.s1["dates"][1]  # C changes at its second date


def test_fire_evidence_makes_a_burn(monkeypatch):
    monkeypatch.setattr(refs, "nifc_perimeters", lambda bbox, year=2026: [
        {"name": "Test fire", "acres": 100.0,
         "geometry": {"type": "Polygon", "coordinates": [[
             [BBOX[0] - 1, BBOX[1] - 1], [BBOX[2] + 1, BBOX[1] - 1], [BBOX[2] + 1, BBOX[3] + 1],
             [BBOX[0] - 1, BBOX[3] + 1], [BBOX[0] - 1, BBOX[1] - 1]]]}}])
    result, _ = run(monkeypatch, Scene(DAYS, hh_drop_db=1.0))
    a = result.areas[0]
    assert a.cls == "burn"
    assert next(e for e in a.evidence if e.label == "Inside fire perimeter").value == "yes"


def test_people_are_tracts_under_areas(monkeypatch):
    around = {"type": "Polygon", "coordinates": [[[-119.3, 48.0], [-119.0, 48.0], [-119.0, 48.3],
                                                   [-119.3, 48.3], [-119.3, 48.0]]]}
    far = {"type": "Polygon", "coordinates": [[[-100, 40], [-99, 40], [-99, 41], [-100, 41],
                                               [-100, 40]]]}
    monkeypatch.setattr(refs, "svi_tracts", lambda bbox: [
        {"geoid": "1", "rpl_themes": 0.2, "name": "near", "geometry": around},
        {"geoid": "2", "rpl_themes": 0.9, "name": "far", "geometry": far}])
    result, _ = run(monkeypatch)
    assert result.people == {"svi_tracts": [{"geoid": "1", "rpl_themes": 0.2, "name": "near"}]}


def test_png_sink_replaces_data_urls(monkeypatch):
    seen = {}
    def sink(name, png):
        seen[name] = png
        return f"/files/{name}.png"
    result, _ = run(monkeypatch, png_sink=sink)
    assert set(seen) == {"change", "l", "c", "before", "after"}
    assert result.overlays["change_png"] == "/files/change.png"
    assert seen["change"][:8] == b"\x89PNG\r\n\x1a\n"


def test_weather_failure_does_not_break_the_run(monkeypatch):
    monkeypatch.setattr(refs, "weather", lambda lon, lat, when: {"min_temp_c": None, "rain_mm": None})
    result, _ = run(monkeypatch)
    assert result.areas[0].cls == "forest_loss"


# --- the LLM guard: cap, timeout, circuit breaker -----------------------------------------------


def make_areas(n):
    return [
        ChangeArea(id=f"a{i}", geometry={"type": "Polygon", "coordinates": []}, agreement="L",
                   cls="forest_loss", area_ha=float(100 - i), confidence=0.9,
                   confidence_label="High", p_value=1e-6, change_date=None,
                   evidence=[Evidence("HV change", -3.5, [-4.0, -3.0], "dB", "NISAR L-band")],
                   plain_text="", series={"dates": [], "HH": [], "HV": [], "VV": [], "VH": []})
        for i in range(n)
    ]


class FakeClient:
    """`outcomes`: one entry per call, an Exception to raise or a string to return."""

    def __init__(self, outcomes):
        self.outcomes, self.calls = list(outcomes), []
        self.messages = self

    def create(self, **kwargs):
        self.calls.append(kwargs)
        out = self.outcomes[min(len(self.calls), len(self.outcomes)) - 1]
        if isinstance(out, Exception):
            raise out
        return SimpleNamespace(content=[SimpleNamespace(type="text", text=out)])


def test_explain_caps_at_ten_largest():
    areas = make_areas(12)
    client = FakeClient(["LLM text."])
    pipeline.explain_areas(areas, client)
    assert len(client.calls) == 10
    assert [a.plain_text for a in areas[:10]] == ["LLM text."] * 10
    assert all("ha" in a.plain_text and a.plain_text != "LLM text." for a in areas[10:])


def test_explain_picks_largest_not_first():
    areas = list(reversed(make_areas(12)))  # smallest first
    client = FakeClient(["LLM text."])
    pipeline.explain_areas(areas, client)
    assert {a.id for a in areas if a.plain_text == "LLM text."} == {f"a{i}" for i in range(10)}


def test_breaker_opens_after_two_failures():
    areas = make_areas(8)
    client = FakeClient([RuntimeError("boom")])
    pipeline.explain_areas(areas, client)
    assert len(client.calls) == 2
    assert all("ha" in a.plain_text for a in areas)  # every area still has template text


def test_breaker_counts_only_consecutive_failures():
    areas = make_areas(6)
    client = FakeClient([RuntimeError("x"), "ok", RuntimeError("x"), "ok", RuntimeError("x"), "ok"])
    pipeline.explain_areas(areas, client)
    assert len(client.calls) == 6
    assert [a.plain_text for a in areas][1::2] == ["ok"] * 3


def test_empty_reply_counts_as_a_failure():
    client = FakeClient([""])
    pipeline.explain_areas(make_areas(5), client)
    assert len(client.calls) == 2


def test_real_client_gets_a_five_second_timeout():
    seen = {}

    class Real(FakeClient):
        def with_options(self, **kw):
            seen.update(kw)
            return self

    client = Real(["ok"])
    areas = make_areas(1)
    pipeline.explain_areas(areas, client)
    assert seen == {"timeout": 5.0, "max_retries": 0} and areas[0].plain_text == "ok"


def test_run_box_uses_the_explain_client(monkeypatch):
    client = FakeClient(["Plain words."])
    result, _ = run(monkeypatch, explain_client=client)
    assert result.areas[0].plain_text == "Plain words."
    assert result.areas[0].cls == "forest_loss"  # the LLM never changes the class


# --- the notebook -------------------------------------------------------------------------------


def test_notebook_valid():
    urls = ["https://example.invalid/a.h5", "https://example.invalid/b.h5"]
    raw = notebook.build(BBOX, urls, (date(2026, 7, 13), "2026-09-11"))
    nb = nbformat.reads(raw.decode("utf-8"), as_version=4)
    nbformat.validate(nb)
    text = "\n".join(c.source for c in nb.cells)
    assert "pip install" in text and "run_box" in text
    assert str(BBOX[0]) in text and urls[0] in text and "2026-09-11" in text
    assert "password=" not in text.lower().replace(" ", "")  # it never carries credentials
    compile("\n".join(c.source for c in nb.cells if c.cell_type == "code"
                      and not c.source.lstrip().startswith(("%", "!"))), "nb", "exec")


def test_notebook_without_dates():
    nb = nbformat.reads(notebook.build(BBOX, [], None).decode(), as_version=4)
    nbformat.validate(nb)


# --- references (fake HTTP) ---------------------------------------------------------------------


class FakeResponse:
    def __init__(self, payload=None, text=""):
        self._payload, self.text, self.status_code = payload, text, 200

    def json(self):
        return self._payload

    def raise_for_status(self):
        pass


def fake_get(monkeypatch, *responses):
    calls = []

    def get(url, params=None, timeout=None, **kw):
        calls.append((url, dict(params or {})))
        out = responses[min(len(calls), len(responses)) - 1]
        if isinstance(out, Exception):
            raise out
        return out

    monkeypatch.setattr(refs.requests, "get", get)
    return calls


SQUARE = {"type": "Polygon", "coordinates": [[[0, 0], [1, 0], [1, 1], [0, 1], [0, 0]]]}


def test_svi_tracts(monkeypatch):
    feats = [
        {"geometry": SQUARE, "properties": {"FIPS": "53047940100", "RPL_THEMES": 0.89,
                                            "LOCATION": "Census Tract 9401; Okanogan"}},
        {"geometry": SQUARE, "properties": {"FIPS": "53047940200", "RPL_THEMES": -999,
                                            "LOCATION": "no population"}},
    ]
    calls = fake_get(monkeypatch, FakeResponse({"features": feats}))
    out = REAL.svi_tracts((-119.1, 48.1, -119.0, 48.2))
    assert out == [{"geoid": "53047940100", "rpl_themes": 0.89, "name": "Census Tract 9401; Okanogan",
                    "geometry": SQUARE}]  # the -999 tract has no ranking, so it is dropped
    assert calls[0][1]["geometry"] == "-119.1,48.1,-119.0,48.2"


def test_svi_failure_gives_empty(monkeypatch):
    fake_get(monkeypatch, OSError("down"))
    assert REAL.svi_tracts((-119.1, 48.1, -119.0, 48.2)) == []


def test_nifc_perimeters(monkeypatch):
    props = {"poly_IncidentName": "Kaiser Canyon", "poly_GISAcres": 138285.3,
             "attr_FireDiscoveryDateTime": 1784205000000}  # 2026-07-16
    old = {"poly_IncidentName": "Old", "poly_GISAcres": 5.0,
           "attr_FireDiscoveryDateTime": 1500000000000}  # 2017
    feats = [{"geometry": SQUARE, "properties": props}, {"geometry": SQUARE, "properties": old}]
    fake_get(monkeypatch, FakeResponse({"features": feats}))
    out = REAL.nifc_perimeters((-119.1, 48.1, -119.0, 48.2), year=2026)
    assert out == [{"name": "Kaiser Canyon", "acres": 138285.3, "geometry": SQUARE}]


def test_nifc_failure_gives_empty(monkeypatch):
    fake_get(monkeypatch, OSError("down"))
    assert REAL.nifc_perimeters((-119.1, 48.1, -119.0, 48.2)) == []


def test_firms_count(monkeypatch):
    monkeypatch.setenv("FIRMS_MAP_KEY", "k")
    csv = ("latitude,longitude,acq_date\n0.5,0.5,2026-07-20\n0.9,0.1,2026-07-21\n"
           "5.0,5.0,2026-07-21\n")  # the last one is outside the geometry
    calls = fake_get(monkeypatch, FakeResponse(text=csv))
    assert REAL.firms_count(SQUARE, date(2026, 7, 13), date(2026, 7, 22)) == 2
    assert "k" in calls[0][0] and "2026-07-13" in calls[0][0]


def test_firms_without_key_or_on_error_is_none(monkeypatch):
    monkeypatch.delenv("FIRMS_MAP_KEY", raising=False)
    fake_get(monkeypatch, FakeResponse(text="latitude,longitude\n"))
    assert REAL.firms_count(SQUARE, date(2026, 7, 13), date(2026, 7, 22)) is None
    monkeypatch.setenv("FIRMS_MAP_KEY", "k")
    fake_get(monkeypatch, OSError("down"))
    assert REAL.firms_count(SQUARE, date(2026, 7, 13), date(2026, 7, 22)) is None


def test_weather(monkeypatch):
    payload = {"daily": {"time": ["2026-09-11"], "temperature_2m_min": [8.7],
                         "precipitation_sum": [0.4]}}
    calls = fake_get(monkeypatch, FakeResponse(payload))
    assert REAL.weather(-119.0, 48.2, date(2026, 9, 11)) == {"min_temp_c": 8.7, "rain_mm": 0.4}
    assert calls[0][1]["start_date"] == calls[0][1]["end_date"] == "2026-09-11"


def test_weather_failure_gives_none_values(monkeypatch):
    fake_get(monkeypatch, OSError("down"))
    assert REAL.weather(-119.0, 48.2, date(2026, 9, 11)) == {"min_temp_c": None, "rain_mm": None}
    fake_get(monkeypatch, FakeResponse({"daily": {"time": [], "temperature_2m_min": [],
                                                  "precipitation_sum": []}}))
    assert REAL.weather(-119.0, 48.2, "2026-09-11") == {"min_temp_c": None, "rain_mm": None}


# --- live ---------------------------------------------------------------------------------------


@pytest.mark.live
def test_live_kaiser_direction(monkeypatch):
    """Real Kaiser Canyon centre box: both sensors find change, and the pieces are all there.

    The spike's direction (C area > L area) is only expected on equal dates; the default series
    gives L five dates and C two, so L can out-detect C here. Per-agreement areas are printed.
    """
    monkeypatch.undo()  # real reference lookups and real retry pauses, not the offline fakes
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)  # template text, no paid calls
    bbox = (-119.115, 48.157, -118.975, 48.257)
    result = pipeline.run_box(bbox, (date(2026, 7, 13), date(2026, 9, 11)))
    ha = {k: sum(a.area_ha for a in result.areas if a.agreement == k) for k in ("L", "C", "both")}
    print("areas (ha) by agreement:", ha, "| n areas:", len(result.areas),
          "| classes:", sorted({a.cls for a in result.areas}),
          "| tracts:", len(result.people["svi_tracts"]), "| s1:", result.s1)
    assert result.s1 is not None and result.nisar["track"] == 71
    assert ha["L"] + ha["both"] > 0 and ha["C"] + ha["both"] > 0
    assert result.people["svi_tracts"]  # Okanogan County tracts sit under the areas
    assert Result.from_json(result.to_json()).to_json() == result.to_json()
    assert all(a.plain_text for a in result.areas)
