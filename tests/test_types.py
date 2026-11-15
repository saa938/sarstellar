"""Tests for the shared contract types (core/sarstellar/types.py) and the test harness."""

import json
import subprocess
import sys
import tempfile
import textwrap
from datetime import UTC, date, datetime
from pathlib import Path

from sarstellar.types import (
    ChangeArea,
    Evidence,
    Granule,
    Grid,
    Job,
    NoUsablePasses,
    Result,
    Stack,
)

CONFTEST = Path(__file__).with_name("conftest.py")


def make_granule(day: int, frame: int = 71) -> Granule:
    return Granule(
        ur=f"NISAR_L2_PR_GCOV_025_{frame:03d}_D_064_4005_DHDH_A_202607{day:02d}T030956",
        url=f"https://example.invalid/gcov_{day}.h5",
        collection="NISAR_L2_GCOV_PROVISIONAL_V1",
        start=datetime(2026, 7, day, 3, 9, 56, tzinfo=UTC),
        track=25,
        frame=frame,
        direction="D",
        bandwidth_mhz=20.0,
        crid="P05023",
        counter=1,
        mixed_mode=False,
        size_gb=2.5,
    )


def make_area() -> ChangeArea:
    return ChangeArea(
        id="a1",
        geometry={
            "type": "Polygon",
            "coordinates": [[[-120.0, 47.0], [-119.99, 47.0], [-119.99, 47.01], [-120.0, 47.0]]],
        },
        agreement="both",
        cls="forest_loss",
        area_ha=12.5,
        confidence=0.82,
        confidence_label="High",
        p_value=1e-6,
        change_date="2026-08-14",
        evidence=[
            Evidence(label="HV change", value=-4.1, ci=[-4.6, -3.6], unit="dB", note="cross-pol"),
            Evidence(label="In fire perimeter", value=0.0, ci=None, unit="", note="WFIGS"),
        ],
        plain_text="Most of the forest canopy here was removed.",
        series={
            "dates": ["2026-07-13", "2026-09-11"],
            "HH": [-8.0, -9.5],
            "HV": [-14.0, -18.0],
            "VV": [None, None],
            "VH": [None, None],
        },
    )


def make_result(s1=None) -> Result:
    return Result(
        bbox=[-120.05, 47.0, -119.95, 47.1],
        message=None,
        fixture=False,
        nisar={"track": 25, "direction": "D", "dates": ["2026-07-13", "2026-09-11"]},
        s1=s1,
        overlays={
            "change_png": "/stories/x/change.png",
            "l_png": "/stories/x/l.png",
            "c_png": "/stories/x/c.png",
            "before_png": "/stories/x/before.png",
            "after_png": "/stories/x/after.png",
            "bounds": [[-120.05, 47.1], [-119.95, 47.1], [-119.95, 47.0], [-120.05, 47.0]],
        },
        areas=[make_area()],
        people={"svi_tracts": [{"geoid": "53007000100", "rpl_themes": 0.61, "name": "Tract 1"}]},
        exports={"geotiff": None, "csv": "/exports/x.csv", "notebook": None},
    )


def test_result_roundtrip():
    result = make_result(s1={"track": 166, "dates": ["2026-07-15", "2026-09-09"]})
    payload = result.to_json()

    assert payload["areas"][0]["class"] == "forest_loss"
    assert "cls" not in payload["areas"][0]
    # Survives a real JSON wire trip, not just a dict copy.
    assert Result.from_json(json.loads(json.dumps(payload))) == result
    assert Result.from_json(payload) == result


def test_result_roundtrip_without_s1():
    result = make_result(s1=None)
    payload = result.to_json()
    assert payload["s1"] is None
    assert Result.from_json(payload) == result


def test_contract_json_keys():
    payload = make_result().to_json()
    assert set(payload) == {
        "bbox",
        "message",
        "fixture",
        "nisar",
        "s1",
        "overlays",
        "areas",
        "people",
        "exports",
    }
    assert set(payload["areas"][0]) == {
        "id",
        "geometry",
        "agreement",
        "class",
        "area_ha",
        "confidence",
        "confidence_label",
        "p_value",
        "change_date",
        "evidence",
        "plain_text",
        "series",
    }
    assert set(payload["areas"][0]["evidence"][0]) == {"label", "value", "ci", "unit", "note"}


def test_job_roundtrip():
    done = Job(job_id="j1", status="done", progress=1.0, message="ok", result=make_result())
    payload = done.to_json()
    assert payload["result"]["areas"][0]["class"] == "forest_loss"
    assert Job.from_json(json.loads(json.dumps(payload))) == done

    queued = Job(job_id="j2", status="queued", progress=0.0, message="", result=None)
    assert queued.to_json()["result"] is None
    assert Job.from_json(queued.to_json()) == queued


def test_job_json_keys():
    job = Job(job_id="j1", status="running", progress=0.5, message="working", result=None)
    assert set(job.to_json()) == {"job_id", "status", "progress", "message", "result"}


def test_grid_shape():
    assert Grid(32610, 0, 1000, 0, 2000).shape == (20, 10)


def test_grid_transform_is_north_up():
    grid = Grid(32610, 500_000, 501_000, 5_200_000, 5_202_000)
    transform = grid.transform()
    assert transform @ (0, 0) == (500_000, 5_202_000)  # upper-left pixel corner
    assert transform @ (10, 20) == (501_000, 5_200_000)  # lower-right corner
    assert Grid(32610, 0, 1000, 0, 2000, res=10.0).shape == (200, 100)


def test_stack_dates_sorted_unique():
    stack = Stack(
        track=25,
        direction="D",
        bandwidth_mhz=20.0,
        crid="P05023",
        granules=[make_granule(30), make_granule(13), make_granule(13, frame=72)],
    )
    assert stack.dates == [date(2026, 7, 13), date(2026, 7, 30)]


def test_no_usable_passes_is_exception_with_message():
    err = NoUsablePasses("No calibrated NISAR passes cover this box between a and b.")
    assert isinstance(err, Exception)
    assert str(err) == "No calibrated NISAR passes cover this box between a and b."


def test_conftest_marks_live(pytestconfig):
    markers = pytestconfig.getini("markers")
    assert any(m.split(":")[0].strip() == "live" for m in markers)


def _run_inner_pytest(*args: str) -> str:
    """Run pytest on a throwaway project that has our conftest and one live test.

    Uses tempfile rather than the tmp_path fixture so this test does not depend on
    pytest's shared per-user temp folder, which can be unreadable on some machines.
    """
    with tempfile.TemporaryDirectory(prefix="sarstellar-conftest-") as tmp:
        root = Path(tmp)
        (root / "conftest.py").write_text(CONFTEST.read_text(encoding="utf-8"), encoding="utf-8")
        (root / "test_inner.py").write_text(
            textwrap.dedent(
                """
                import pytest

                @pytest.mark.live
                def test_network():
                    pass

                def test_plain():
                    pass
                """
            ),
            encoding="utf-8",
        )
        proc = subprocess.run(
            [
                sys.executable,
                "-m",
                "pytest",
                "-p",
                "no:cacheprovider",
                "--basetemp",
                str(root / "bt"),
                "-q",
                "-rs",
                *args,
            ],
            cwd=root,
            capture_output=True,
            text=True,
            timeout=120,
            check=False,
        )
    return proc.stdout + proc.stderr


def test_live_tests_skipped_by_default():
    assert "1 passed, 1 skipped" in _run_inner_pytest()


def test_live_tests_run_with_marker_or_flag():
    assert "1 passed, 1 deselected" in _run_inner_pytest("-m", "live")
    assert "2 passed" in _run_inner_pytest("--run-live")
