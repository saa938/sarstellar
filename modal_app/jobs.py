"""Job logic that does not need Modal: run a job, store its progress, write its exports.

`execute_job` is what the Modal function `run_job` calls. It runs `run_box` in a worker thread so
it can give up at a time budget and say why, keeps the job's record in `store` up to date, writes
the overlay PNGs and the three export files into `exports_root` (a Modal Volume in production, a
temp folder in tests) and ends the job as `done` or `error` with a readable message.

`store` is anything with `.get(key)` and `store[key] = value`: a plain dict in tests, a
`modal.Dict` in production. Records are plain JSON-like dicts under `job:{id}`.
"""

from __future__ import annotations

import csv
import logging
import threading
from collections.abc import Callable
from dataclasses import asdict
from pathlib import Path
from typing import Any

import numpy as np

from sarstellar import notebook, read, search
from sarstellar.detect import NoStableBlocks, TooFewBlocks
from sarstellar.pipeline import NO_VALID_MESSAGE
from sarstellar.types import Grid, Job, NoUsablePasses, Result

log = logging.getLogger(__name__)

JOB_TIMEOUT_S = 600  # Modal's limit on `run_job`, and how long the API lets a job stay open
JOB_BUDGET_S = 570  # `execute_job` gives up first, so it can write the reason itself
CMR_TIMEOUT_S = 30  # inside a job: one CMR request waits this long, at most twice
CMR_ATTEMPTS = 2

EXPORT_NAMES = {"geotiff": "change.tif", "csv": "areas.csv", "notebook": "notebook.ipynb"}
OVERLAY_NAMES = ("change", "l", "c", "before", "after")
TERMINAL = ("done", "error")

DATA_SERVER_MESSAGE = "NASA's data server didn't respond; try again in a few minutes."
TIMEOUT_MESSAGE = "The analysis took too long and was stopped; try a smaller box or try again."
GENERIC_MESSAGE = "Something went wrong analysing this box; try again."

Store = Any  # `.get(key)` and `store[key] = value`


class JobStopped(Exception):
    """The job already ended (it timed out), so the worker should stop reporting on it."""


def job_key(job_id: str) -> str:
    return f"job:{job_id}"


def error_message(exc: BaseException) -> str:
    """A readable job error for an exception from the pipeline. Never exposes internals."""
    if isinstance(exc, NoUsablePasses):
        return str(exc)
    if isinstance(exc, (TooFewBlocks, NoStableBlocks)):  # before ValueError: they subclass it
        return NO_VALID_MESSAGE
    if isinstance(exc, OSError):  # the read layer raises OSError once its retries run out
        return DATA_SERVER_MESSAGE
    if isinstance(exc, ValueError):  # e.g. `pick_pair`: the dates leave no pair of passes
        return f"This box and date range can't be analysed: {exc}"
    return GENERIC_MESSAGE


# --- the job record -----------------------------------------------------------------------------


def _update(store: Store, job_id: str, **fields) -> dict:
    """Change fields of a job that is still open; raise `JobStopped` if it already ended."""
    record = store.get(job_key(job_id))
    if record is None or record["status"] in TERMINAL:
        raise JobStopped(job_id)
    record = {**record, **fields}
    store[job_key(job_id)] = record
    return record


def _finish(store: Store, job_id: str, status: str, message: str, result: Result | None) -> None:
    """End a job (replacing any state, even a reaped one: a late result beats a timeout)."""
    job = Job(job_id=job_id, status=status, progress=1.0 if status == "done" else 0.0,
              message=message, result=result)
    old = store.get(job_key(job_id)) or {}
    if status == "error":
        job.progress = float(old.get("progress", 0.0))
    store[job_key(job_id)] = job.to_json()


# --- exports ------------------------------------------------------------------------------------


def write_change_tif(path: Path, bs, changed_l: np.ndarray, changed_c: np.ndarray) -> None:
    """Six float32 bands on the block grid: agreement code, relative dHH, dHV, dVV, dVH, min p.

    The code is 0 no change, 1 changed in L-band only, 2 in C-band only, 3 in both. Changes are
    relative (scene offset removed), in dB, last date minus first. NaN means no data.
    """
    import rasterio
    from rasterio.crs import CRS

    code = np.asarray(changed_l, dtype=np.float32) + 2.0 * np.asarray(changed_c, dtype=np.float32)
    bands = {
        "agreement (0 none, 1 L only, 2 C only, 3 both)": code,
        "relative change HH (dB)": bs.rel_dHH,
        "relative change HV (dB)": bs.rel_dHV,
        "relative change VV (dB)": bs.rel_dVV,
        "relative change VH (dB)": bs.rel_dVH,
        "min p (L-band, C-band)": np.fmin(bs.p_L, bs.p_C),
    }
    ny, nx = bs.grid.shape
    with rasterio.open(
        path, "w", driver="GTiff", height=ny, width=nx, count=len(bands), dtype="float32",
        crs=CRS.from_epsg(bs.grid.epsg), transform=bs.grid.transform(), nodata=float("nan"),
        compress="deflate",
    ) as dst:
        for i, (name, arr) in enumerate(bands.items(), start=1):
            dst.write(np.asarray(arr, dtype=np.float32), i)
            dst.set_band_description(i, name)


_CSV_COLUMNS = ("id", "class", "agreement", "area_ha", "confidence", "confidence_label",
                "p_value", "change_date", "plain_text")


def write_areas_csv(path: Path, result: Result) -> None:
    """One row per change area, without geometry."""
    with open(path, "w", newline="", encoding="utf-8") as f:
        out = csv.DictWriter(f, fieldnames=_CSV_COLUMNS)
        out.writeheader()
        for area in result.areas:
            row = area.to_json()
            out.writerow({k: row[k] for k in _CSV_COLUMNS})


def write_exports(root: Path, job_id: str, result: Result, blocks, bbox, dates, granule_urls) -> dict:
    """Write change.tif / areas.csv / notebook.ipynb; return the `result.exports` URLs.

    An export that fails is logged and left null: the map result is still worth showing.
    """
    folder = root / "exports" / job_id
    folder.mkdir(parents=True, exist_ok=True)
    makers = {
        "csv": lambda p: write_areas_csv(p, result),
        "notebook": lambda p: p.write_bytes(notebook.build(bbox, granule_urls, dates)),
    }
    if blocks is not None:
        makers["geotiff"] = lambda p: write_change_tif(p, *blocks)
    exports: dict[str, str | None] = {k: None for k in EXPORT_NAMES}
    for key, make in makers.items():
        name = EXPORT_NAMES[key]
        try:
            make(folder / name)
            exports[key] = f"/exports/{job_id}/{name}"
        except Exception:
            log.exception("could not write %s for job %s", name, job_id)
    return exports


# --- running a job ------------------------------------------------------------------------------


def execute_job(
    store: Store,
    job_id: str,
    bbox,
    dates,
    run: Callable[..., Result],
    *,
    exports_root,
    read_passes=None,
    timeout_s: float = JOB_BUDGET_S,
    commit: Callable[[], None] | None = None,
) -> None:
    """Run `run(bbox, dates, ...)` (that is `run_box`) as job `job_id` and record the outcome.

    `read_passes` is handed to `run` (None: its default reader). `commit()` is called after the
    files are written and before the job is marked done (a Modal Volume needs it to publish them).
    The job always ends `done` or `error`; this never raises for a pipeline failure.
    """
    root = Path(exports_root)
    try:
        _update(store, job_id, status="running", message="Starting")
    except JobStopped:
        return
    cancelled = threading.Event()
    granule_urls: list[str] = []
    blocks: list = []
    outcome: dict[str, Any] = {}

    def progress(fraction: float, message: str) -> None:
        if cancelled.is_set():
            raise JobStopped(job_id)
        _update(store, job_id, status="running", progress=round(float(fraction), 3),
                message=message)

    def png_sink(name: str, png: bytes) -> str:
        if cancelled.is_set():
            raise JobStopped(job_id)
        try:
            folder = root / "overlays" / job_id
            folder.mkdir(parents=True, exist_ok=True)
            (folder / f"{name}.png").write_bytes(png)
        except OSError as exc:  # a full disk is not "NASA did not respond"
            raise RuntimeError("could not store an overlay image") from exc
        return f"/overlays/{job_id}/{name}.png"

    def blocks_sink(bs, changed_l, changed_c) -> None:
        blocks[:] = [bs, changed_l, changed_c]

    def recording(granules, box, grid):
        granule_urls.extend(g.url for g in granules)
        return read_passes(granules, box, grid)

    def work() -> None:
        try:
            outcome["result"] = run(
                bbox, tuple(dates) if dates else None,
                read_passes=None if read_passes is None else recording,
                progress=progress, png_sink=png_sink, blocks_sink=blocks_sink,
            )
        except BaseException as exc:  # noqa: BLE001 - reported below, from the main thread
            outcome["error"] = exc

    worker = threading.Thread(target=work, name=f"job-{job_id}", daemon=True)
    worker.start()
    worker.join(timeout_s)
    if worker.is_alive():  # cannot kill a thread; it stops at its next progress call
        cancelled.set()
        log.error("job %s ran past its %s s budget", job_id, timeout_s)
        _finish(store, job_id, "error", TIMEOUT_MESSAGE, None)
        return
    if "error" in outcome:
        exc = outcome["error"]
        if isinstance(exc, JobStopped):
            return  # the API already ended this job
        log.error("job %s failed: %s: %s", job_id, type(exc).__name__, exc,
                  exc_info=(type(exc), exc, exc.__traceback__))
        _finish(store, job_id, "error", error_message(exc), None)
        return

    result: Result = outcome["result"]
    result.exports = write_exports(root, job_id, result, blocks or None, bbox, dates, granule_urls)
    if commit is not None:
        try:
            commit()
        except Exception:
            log.exception("volume commit failed for job %s", job_id)
    _finish(store, job_id, "done", result.message or "Done", result)


# --- reading NISAR granules on other containers -------------------------------------------------


def limit_search() -> None:
    """Shorten the CMR timeout and retries so a slow search cannot eat the job's 600 s."""
    search.CMR_TIMEOUT_S = CMR_TIMEOUT_S
    search.CMR_ATTEMPTS = CMR_ATTEMPTS


def read_one(url: str, bbox, grid_dict: dict | None = None, *, fs=None):
    """Read one GCOV granule as 1-ha blocks: `(meta, blocks)`, or None if the box misses it.

    `grid_dict` is a `Grid` as a dict (None: build it from the file's own UTM zone). A granule
    in another UTM zone than the grid, or whose frame does not reach the box, is skipped.
    Network failures arrive as `OSError` after the read layer's six tries.
    """
    grid = None if grid_dict is None else Grid(**grid_dict)
    try:
        meta, blocks, _ = read.read_gcov_blocks(url, bbox, fs or read.https_fs(), grid)
    except ValueError as exc:
        if "does not overlap" in str(exc) or "EPSG differs" in str(exc):
            log.warning("skipping %s: %s", url, exc)
            return None
        raise
    return meta, blocks


def make_read_passes(starmap: Callable[[list[tuple]], list]) -> Callable:
    """A `read_passes(granules, bbox, grid)` that reads every granule through `starmap`.

    `starmap(list of (url, bbox, grid_dict))` returns one `read_one` result per input, in order
    (production: `read_pass.starmap`, one container per granule). Skipped granules are dropped.
    """

    def read_passes(granules, bbox, grid):
        grid_dict = None if grid is None else asdict(grid)
        results = starmap([(g.url, list(bbox), grid_dict) for g in granules])
        return [r for r in results if r is not None]

    return read_passes
