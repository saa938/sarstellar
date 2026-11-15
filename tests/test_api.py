"""The job API: guards, job lifecycle, exports. No Modal: a fake runner stands in for it.

`create_app` takes a Runner (`submit(job_id, bbox, dates)`). Here it runs the job inline with
`jobs.execute_job` and a fake `run_box`, so a POST has finished by the time it returns.
"""

from __future__ import annotations

import csv
import io
import sys
import time
from pathlib import Path
from types import SimpleNamespace

import nbformat
import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))  # for `modal_app`

import rasterio
from fastapi.testclient import TestClient
from modal_app import api, jobs

from sarstellar.detect import NoStableBlocks, TooFewBlocks
from sarstellar.types import ChangeArea, Evidence, Grid, Job, NoUsablePasses, Result

KAISER = [-119.3705, 48.0531, -118.7196, 48.3605]  # the real demo box (about 48 x 34 km: too big)
BOX = [-119.20, 48.15, -119.10, 48.22]  # about 7.4 x 7.8 km
DATA_SERVER = "NASA's data server didn't respond; try again in a few minutes."
GRID = Grid(epsg=32610, xmin=500_000.0, xmax=500_900.0, ymin=5_000_000.0, ymax=5_000_800.0)


def box(i: int = 0) -> list[float]:
    """A distinct valid box for each i (shifted well past the 1e-4 cache rounding)."""
    return [BOX[0] + 0.002 * i, BOX[1], BOX[2] + 0.002 * i, BOX[3]]


def fake_result(bbox, overlays: dict) -> Result:
    area = ChangeArea(
        id="a1", agreement="L", cls="forest_loss", area_ha=12.0, confidence=0.9,
        confidence_label="High", p_value=1e-4, change_date="2026-08-20", plain_text="Trees lost.",
        geometry={"type": "Polygon", "coordinates": [[[-119.2, 48.2], [-119.1, 48.2],
                                                       [-119.1, 48.1], [-119.2, 48.2]]]},
        evidence=[Evidence("HV change", -3.5, [-4.0, -3.0], "dB", "median")],
        series={"dates": ["2026-07-13", "2026-09-11"], "HH": [-9.0, -9.5], "HV": [-15.0, -18.5],
                "VV": [None, None], "VH": [None, None]},
    )
    return Result(
        bbox=list(bbox), nisar={"track": 71, "direction": "D", "dates": ["2026-07-13"]},
        overlays={**overlays, "bounds": [[bbox[0], bbox[3]], [bbox[2], bbox[3]],
                                         [bbox[2], bbox[1]], [bbox[0], bbox[1]]]},
        areas=[area],
    )


def fake_block_set():
    rng = np.random.default_rng(1)
    shape = GRID.shape
    return SimpleNamespace(
        grid=GRID, rel_dHH=rng.normal(size=shape), rel_dHV=rng.normal(size=shape),
        rel_dVV=np.full(shape, np.nan), rel_dVH=np.full(shape, np.nan),
        p_L=rng.uniform(size=shape), p_C=np.full(shape, np.nan),
    )


def fake_run_box(bbox, dates=None, *, read_passes=None, progress=None, png_sink=None,
                 blocks_sink=None):
    progress and progress(0.5, "Reading")
    urls = {f"{n}_png": png_sink(n, b"\x89PNG fake") for n in ("change", "l", "c", "before", "after")}
    bs = fake_block_set()
    changed_l = np.zeros(GRID.shape, dtype=bool)
    changed_l[2:5, 2:5] = True
    changed_c = np.zeros(GRID.shape, dtype=bool)
    changed_c[4:7, 4:7] = True  # overlaps the L patch at (4, 4)
    blocks_sink and blocks_sink(bs, changed_l, changed_c)
    return fake_result(bbox, urls)


class InlineRunner:
    """Runs the job in the POST handler, with the real `execute_job` and a fake `run_box`."""

    def __init__(self, store, root, run=fake_run_box, **kw):
        self.store, self.root, self.run, self.kw, self.submitted = store, root, run, kw, []

    def submit(self, job_id, bbox, dates):
        self.submitted.append(job_id)
        jobs.execute_job(self.store, job_id, bbox, dates, self.run, exports_root=self.root,
                         **self.kw)


class NullRunner:
    """Accepts jobs and never runs them (the container died, or Modal timed out)."""

    def submit(self, job_id, bbox, dates):
        pass


class Clock:
    def __init__(self, t=1_800_000_000.0):
        self.t = t

    def __call__(self):
        return self.t


@pytest.fixture
def env(tmp_path, monkeypatch):
    monkeypatch.delenv("SARSTELLAR_KILL", raising=False)
    store: dict = {}
    clock = Clock()
    runner = InlineRunner(store, tmp_path)

    def make(runner=runner, **kw):
        app = api.create_app(store, runner, exports_root=tmp_path, now=clock, **kw)
        return TestClient(app)

    return SimpleNamespace(store=store, clock=clock, runner=runner, root=tmp_path, make=make,
                           client=make())


def post(client, bbox, dates=None, ip=None):
    body = {"bbox": bbox, **({"dates": dates} if dates else {})}
    return client.post("/jobs", json=body, headers={"x-forwarded-for": ip} if ip else {})


# --- lifecycle and exports ----------------------------------------------------------------------


def test_health(env):
    r = env.client.get("/health")
    assert r.status_code == 200 and r.json() == {"ok": True}


def test_post_returns_job_id(env):
    r = post(env.client, BOX)
    assert r.status_code == 200
    job_id = r.json()["job_id"]
    assert isinstance(job_id, str) and len(job_id) >= 8
    got = env.client.get(f"/jobs/{job_id}").json()
    assert set(got) == {"job_id", "status", "progress", "message", "result"}
    assert got["status"] == "done" and got["progress"] == 1.0
    assert Job.from_json(got).result.areas[0].cls == "forest_loss"


def test_unknown_job_404(env):
    assert env.client.get("/jobs/nope").status_code == 404


def test_exports_written(env):
    job_id = post(env.client, BOX).json()["job_id"]
    result = env.client.get(f"/jobs/{job_id}").json()["result"]
    base = env.root / "exports" / job_id
    names = ("change.tif", "areas.csv", "notebook.ipynb")
    assert all((base / n).is_file() for n in names)
    assert result["exports"] == {
        "geotiff": f"/exports/{job_id}/change.tif",
        "csv": f"/exports/{job_id}/areas.csv",
        "notebook": f"/exports/{job_id}/notebook.ipynb",
    }
    with rasterio.open(base / "change.tif") as tif:
        assert tif.count == 6 and tif.crs.to_epsg() == 32610
        assert (tif.height, tif.width) == GRID.shape
        assert tif.transform.c == GRID.xmin and tif.transform.f == GRID.ymax
        agree = tif.read(1)
        assert agree[3, 3] == 1 and agree[5, 5] == 2 and agree[4, 4] == 3 and agree[0, 0] == 0
        assert np.isnan(tif.read(4)).all()  # no Sentinel-1: dVV is empty
    rows = list(csv.DictReader(io.StringIO((base / "areas.csv").read_text(encoding="utf-8"))))
    assert len(rows) == 1 and rows[0]["class"] == "forest_loss" and rows[0]["id"] == "a1"
    assert "geometry" not in rows[0]
    nb = nbformat.reads((base / "notebook.ipynb").read_text(encoding="utf-8"), as_version=4)
    assert list(nb.cells)


def test_export_download_has_attachment_header(env):
    job_id = post(env.client, BOX).json()["job_id"]
    r = env.client.get(f"/exports/{job_id}/areas.csv")
    assert r.status_code == 200
    assert r.headers["content-disposition"].startswith("attachment")
    assert 'filename="areas.csv"' in r.headers["content-disposition"]
    assert env.client.get(f"/exports/{job_id}/change.tif").status_code == 200


def test_export_paths_are_confined(env):
    job_id = post(env.client, BOX).json()["job_id"]
    for url in (f"/exports/{job_id}/secret.txt", "/exports/..%2f..%2fx/areas.csv",
                "/exports/nope/areas.csv", f"/overlays/{job_id}/evil.png"):
        assert env.client.get(url).status_code == 404


def test_overlay_served_inline(env):
    job_id = post(env.client, BOX).json()["job_id"]
    result = env.client.get(f"/jobs/{job_id}").json()["result"]
    assert result["overlays"]["change_png"] == f"/overlays/{job_id}/change.png"
    r = env.client.get(result["overlays"]["change_png"])
    assert r.status_code == 200 and r.headers["content-type"] == "image/png"
    assert "attachment" not in r.headers.get("content-disposition", "")


def test_cors_allows_any_origin(env):
    r = env.client.get("/health", headers={"Origin": "https://sarstellar.earth"})
    assert r.headers["access-control-allow-origin"] == "*"
    pre = env.client.options("/jobs", headers={"Origin": "https://x.example",
                                               "Access-Control-Request-Method": "POST",
                                               "Access-Control-Request-Headers": "content-type"})
    assert pre.status_code == 200 and "POST" in pre.headers["access-control-allow-methods"]


# --- validation ---------------------------------------------------------------------------------


@pytest.mark.parametrize("bbox", [
    [-119.1, 48.1, -119.2, 48.2],  # west >= east
    [-119.2, 48.2, -119.1, 48.1],  # south >= north
    [-119.2, 48.1, -119.2, 48.2],  # zero width
    [-50.0, 40.0, -49.9, 40.1],  # east of the US bounds
    [-119.2, 80.0, -119.1, 80.1],  # north of the US bounds
    [-119.2, 10.0, -119.1, 10.1],  # south of the US bounds
    [-119.2, 48.1, -119.1],  # three numbers
    "not a box",
])
def test_invalid_bbox_422(env, bbox):
    r = post(env.client, bbox)
    assert r.status_code == 422 and isinstance(r.json()["detail"], str) and r.json()["detail"]
    assert env.store == {}  # nothing was created


@pytest.mark.parametrize("raw", ['{"bbox":[NaN,48.1,-119.1,48.2]}',
                                 '{"bbox":[-119.2,48.1,Infinity,48.2]}', "{not json", "[]", "{}"])
def test_nan_and_garbage_422(env, raw):
    r = env.client.post("/jobs", content=raw, headers={"content-type": "application/json"})
    assert r.status_code == 422 and isinstance(r.json()["detail"], str)


def test_oversize_422(env):
    wide = [-119.5, 48.1, -119.5 + 25 / (111.32 * np.cos(np.radians(48.2))), 48.2]
    tall = [-119.2, 48.0, -119.1, 48.0 + 25 / 111.32]
    for bbox in (wide, tall, KAISER):
        r = post(env.client, bbox)
        assert r.status_code == 422 and "20 km" in r.json()["detail"]


def test_box_just_under_20_km_is_accepted(env):
    ok = [-119.5, 48.1, -119.5 + 19.5 / (111.32 * np.cos(np.radians(48.2))), 48.1 + 19.5 / 111.32]
    assert post(env.client, ok).status_code == 200


def test_bad_dates_422(env):
    for dates in (["2026-09-01", "2026-07-01"], ["soon", "2026-07-01"], ["2026-07-01"]):
        assert post(env.client, BOX, dates).status_code == 422


# --- guards -------------------------------------------------------------------------------------


def test_default_limits():
    assert api.Limits() == api.Limits(per_ip_hour=10, per_day=200)


def test_rate_limit_429(env):
    for i in range(10):
        assert post(env.client, box(i)).status_code == 200
    r = post(env.client, box(10))
    assert r.status_code == 429 and "hour" in r.json()["detail"]
    assert int(r.headers["retry-after"]) > 0
    assert post(env.client, box(11), ip="9.9.9.9").status_code == 200  # another address is fine
    env.clock.t += 3601
    assert post(env.client, box(12)).status_code == 200  # the hour has passed


def test_rate_limit_ignores_a_spoofed_forwarded_for(env):
    # the right-most entry is the one the platform's proxy added; the client controls the rest
    for i in range(10):
        post(env.client, box(i), ip=f"1.1.1.{i}, 8.8.8.8")
    assert post(env.client, box(10), ip="2.2.2.2, 8.8.8.8").status_code == 429


def test_daily_cap_429(env):
    client = env.make(limits=api.Limits(per_ip_hour=1000, per_day=3))
    for i in range(3):
        assert post(client, box(i), ip=f"10.0.0.{i}").status_code == 200
    r = post(client, box(3), ip="10.0.0.99")
    assert r.status_code == 429 and "stories and scorecard" in r.json()["detail"]
    env.clock.t += 86_400
    assert post(client, box(3), ip="10.0.0.99").status_code == 200  # a new day


def test_cache_hit_reuses_job(env):
    first = post(env.client, BOX).json()["job_id"]
    again = post(env.client, [v + 0.00001 for v in BOX]).json()["job_id"]  # rounds to the same box
    assert again == first and len(env.runner.submitted) == 1
    other = post(env.client, BOX, ["2026-07-01", "2026-09-30"]).json()["job_id"]
    assert other != first
    assert post(env.client, BOX, ["2026-07-01", "2026-09-30"]).json()["job_id"] == other
    assert post(env.client, box(5)).json()["job_id"] != first


def test_cache_hit_does_not_use_the_rate_limit(env):
    for _ in range(15):
        assert post(env.client, BOX).status_code == 200


def test_errored_job_is_not_reused(env):
    def boom(*a, **k):
        raise OSError("down")

    client = env.make(runner=InlineRunner(env.store, env.root, run=boom))
    first = post(client, BOX).json()["job_id"]
    assert env.client.get(f"/jobs/{first}").json()["status"] == "error"
    assert post(client, BOX).json()["job_id"] != first


def test_kill_switch_503(env, monkeypatch):
    done = post(env.client, BOX).json()["job_id"]
    monkeypatch.setenv("SARSTELLAR_KILL", "1")
    r = post(env.client, box(1))
    assert r.status_code == 503
    assert r.json() == {"detail": "Live analysis is paused; stories and scorecard still work."}
    assert post(env.client, BOX).status_code == 503  # even a cached box: the app is paused
    assert env.client.get("/health").json() == {"ok": True}
    assert env.client.get(f"/jobs/{done}").status_code == 200


# --- failures and timeouts ----------------------------------------------------------------------


def run_raising(exc):
    def run(*a, **k):
        raise exc

    return run


def test_job_error_message(env):
    client = env.make(runner=InlineRunner(env.store, env.root, run=run_raising(OSError("502"))))
    job = env.client.get(f"/jobs/{post(client, BOX).json()['job_id']}").json()
    assert job["status"] == "error" and job["message"] == DATA_SERVER and job["result"] is None


@pytest.mark.parametrize("exc, expected", [
    (OSError("remote read failed after 6 tries"), DATA_SERVER),
    (ConnectionError("reset"), DATA_SERVER),
    (NoUsablePasses("No calibrated NISAR passes cover this box between 2026-01-01 and 2026-02-01."),
     "No calibrated NISAR passes cover this box between 2026-01-01 and 2026-02-01."),
    (TooFewBlocks("only 3 usable blocks"), "Most of this box has no valid radar data."),
    (NoStableBlocks("none"), "Most of this box has no valid radar data."),
    (ValueError("requested dates resolve to the same acquisition"),
     "This box and date range can't be analysed: requested dates resolve to the same acquisition"),
    (RuntimeError("secret detail"), "Something went wrong analysing this box; try again."),
])
def test_error_messages(exc, expected):
    assert jobs.error_message(exc) == expected
    assert "secret detail" not in jobs.error_message(exc)


def test_job_timeout_inside_the_job(env):
    def slow(*a, **k):
        time.sleep(2.0)

    runner = InlineRunner(env.store, env.root, run=slow, timeout_s=0.2)
    client = env.make(runner=runner)
    t0 = time.monotonic()
    job_id = post(client, BOX).json()["job_id"]
    assert time.monotonic() - t0 < 1.5  # gave up at the budget, did not wait for the runner
    job = client.get(f"/jobs/{job_id}").json()
    assert job["status"] == "error" and "too long" in job["message"]
    time.sleep(2.2)  # the abandoned runner finishes; it must not undo the error
    assert client.get(f"/jobs/{job_id}").json()["status"] == "error"


def test_job_timeout_when_the_container_is_lost(env):
    client = env.make(runner=NullRunner())
    job_id = post(client, BOX).json()["job_id"]
    assert client.get(f"/jobs/{job_id}").json()["status"] == "queued"
    env.clock.t += api.JOB_TIMEOUT_S - 1
    assert client.get(f"/jobs/{job_id}").json()["status"] == "queued"
    env.clock.t += 2  # past 600 s
    job = client.get(f"/jobs/{job_id}").json()
    assert job["status"] == "error" and "too long" in job["message"]
    assert api.JOB_TIMEOUT_S == 600


def test_progress_is_visible_while_running(env):
    seen = []

    def run(bbox, dates=None, *, progress=None, **k):
        progress(0.4, "Reading NISAR")
        seen.append(env.client.get(f"/jobs/{job_ids[0]}").json())
        raise OSError("stop here")

    job_ids = []
    runner = InlineRunner(env.store, env.root, run=run)
    orig = runner.submit
    runner.submit = lambda job_id, *a: (job_ids.append(job_id), orig(job_id, *a))
    post(env.make(runner=runner), BOX)
    assert seen[0]["status"] == "running" and seen[0]["progress"] == 0.4
    assert seen[0]["message"] == "Reading NISAR"


# --- the Modal read helpers (pure parts) --------------------------------------------------------


def test_read_one_skips_a_granule_the_box_misses(monkeypatch):
    calls = []

    def fake_read(url, bbox, fs, grid):
        calls.append(grid)
        if url == "other_zone":
            raise ValueError("EPSG differs: grid is 32610, granule is 32611")
        if url == "elsewhere":
            raise ValueError("the grid window does not overlap this granule's frame")
        if url == "bad":
            raise ValueError("expected a north-up grid")
        return {"epsg": 32610}, {"HH": 1}, grid

    monkeypatch.setattr(jobs.read, "read_gcov_blocks", fake_read)
    grid = {"epsg": 32610, "xmin": 0.0, "xmax": 100.0, "ymin": 0.0, "ymax": 100.0, "res": 100.0}
    assert jobs.read_one("ok", BOX, grid, fs=object()) == ({"epsg": 32610}, {"HH": 1})
    assert calls[0] == Grid(**grid)
    assert jobs.read_one("other_zone", BOX, grid, fs=object()) is None
    assert jobs.read_one("elsewhere", BOX, None, fs=object()) is None
    with pytest.raises(ValueError):
        jobs.read_one("bad", BOX, None, fs=object())


def test_read_passes_fans_out_and_drops_skipped(monkeypatch):
    got = []

    def starmap(args):
        got.extend(args)
        return [({"date": i}, {}) if i != 1 else None for i in range(len(args))]

    gs = [SimpleNamespace(url=f"u{i}") for i in range(3)]
    out = jobs.make_read_passes(starmap)(gs, BOX, None)
    assert [m["date"] for m, _ in out] == [0, 2]
    assert got == [("u0", BOX, None), ("u1", BOX, None), ("u2", BOX, None)]
