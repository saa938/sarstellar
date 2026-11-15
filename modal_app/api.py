"""The job API: pure FastAPI logic, no Modal import, so tests run without it.

`create_app(store, runner, ...)` returns the app. `store` holds job records, the result cache and
the rate-limit counters (a `modal.Dict` in production, a dict in tests); `runner.submit(job_id,
bbox, dates)` starts a job somewhere else (production: `run_job.spawn`).

Routes: `POST /jobs`, `GET /jobs/{id}`, `GET /exports/{job_id}/{name}` (attachment),
`GET /overlays/{job_id}/{name}` (inline PNG), `GET /health`.

POST checks, in order: the kill switch (env `SARSTELLAR_KILL=1`, 503), the box (422), the cache
(same rounded box and dates: reuse the queued, running or done job), then 10 new jobs an hour
per address and 200 a day in all (429). A cache hit costs nothing against either limit.
"""

from __future__ import annotations

import math
import os
import re
import threading
import time
import uuid
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, date, datetime
from typing import Any, Protocol

from fastapi import FastAPI, HTTPException, Request
from fastapi.concurrency import run_in_threadpool
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse

from sarstellar.types import Job

from . import jobs

JOB_TIMEOUT_S = jobs.JOB_TIMEOUT_S
MAX_SIDE_KM = 20.0
KM_PER_DEG = 111.32
US_LON = (-180.0, -60.0)
US_LAT = (17.0, 72.0)
KILL_MESSAGE = "Live analysis is paused; stories and scorecard still work."
RATE_MESSAGE = "Too many analyses from your address in the last hour; try again later."
DAILY_MESSAGE = "The daily limit of live analyses has been reached; stories and scorecard still work."
# Bump when result/export semantics change. Existing job IDs remain readable.
CACHE_REVISION = "cause-hypotheses-v2"

_JOB_ID = re.compile(r"[0-9a-f]{16}")
_EXPORT_TYPES = {
    "change.tif": "image/tiff",
    "areas.csv": "text/csv",
    "notebook.ipynb": "application/x-ipynb+json",
}
_OVERLAYS = {f"{n}.png" for n in jobs.OVERLAY_NAMES}


class Runner(Protocol):
    def submit(self, job_id: str, bbox: list[float], dates: list[str] | None) -> None: ...


@dataclass(frozen=True)
class Limits:
    per_ip_hour: int = 10
    per_day: int = 200


# --- request checks -----------------------------------------------------------------------------


def _number(v: Any) -> bool:
    return isinstance(v, (int, float)) and not isinstance(v, bool)


def parse_request(payload: Any) -> tuple[list[float], list[str] | None]:
    """Validate a POST body `{"bbox": [w, s, e, n], "dates": [start, end]?}`. ValueError if bad."""
    if not isinstance(payload, dict):
        raise ValueError(  # noqa: TRY004 - callers turn every ValueError into a 422
            'Send a JSON object like {"bbox": [west, south, east, north]}.'
        )
    box = payload.get("bbox")
    if not (isinstance(box, list) and len(box) == 4 and all(_number(v) for v in box)):
        raise ValueError("bbox must be four numbers: [west, south, east, north].")
    w, s, e, n = (float(v) for v in box)
    if not all(math.isfinite(v) for v in (w, s, e, n)):
        raise ValueError("bbox numbers must be finite.")
    if not (w < e and s < n):
        raise ValueError("The box needs west < east and south < north.")
    if not (US_LON[0] <= w and e <= US_LON[1] and US_LAT[0] <= s and n <= US_LAT[1]):
        raise ValueError("The box must be inside the United States "
                         "(longitude -180 to -60, latitude 17 to 72).")
    width = (e - w) * KM_PER_DEG * math.cos(math.radians((s + n) / 2))
    height = (n - s) * KM_PER_DEG
    if max(width, height) > MAX_SIDE_KM:
        raise ValueError(f"The box is {width:.0f} km by {height:.0f} km; "
                         f"each side must be {MAX_SIDE_KM:.0f} km or less.")
    return [w, s, e, n], _parse_dates(payload.get("dates"))


def _parse_dates(raw: Any) -> list[str] | None:
    if raw is None:
        return None
    try:
        if not (isinstance(raw, list) and len(raw) == 2):
            raise ValueError
        start, end = (date.fromisoformat(str(d)) for d in raw)
        if start > end:
            raise ValueError
    except ValueError:
        raise ValueError("dates must be [start, end] as YYYY-MM-DD, start not after end.") from None
    return [start.isoformat(), end.isoformat()]


def client_ip(request: Request) -> str:
    """The caller's address. Behind the platform proxy the right-most X-Forwarded-For entry is
    the one the proxy added; entries to its left are whatever the client sent."""
    forwarded = request.headers.get("x-forwarded-for", "")
    last = forwarded.split(",")[-1].strip()
    if last:
        return last
    return request.client.host if request.client else "unknown"


def _day(t: float) -> str:
    return datetime.fromtimestamp(t, UTC).strftime("%Y-%m-%d")


# --- the app ------------------------------------------------------------------------------------


def create_app(
    store,
    runner: Runner,
    *,
    exports_root,
    limits: Limits = Limits(),
    now: Callable[[], float] = time.time,
    killed: Callable[[], bool] | None = None,
    before_file_read: Callable[[], None] | None = None,
) -> FastAPI:
    """`killed()` defaults to env `SARSTELLAR_KILL == "1"`, read per request.
    `before_file_read()` runs before a file is served (production: reload the Modal Volume)."""
    is_killed = killed or (lambda: os.environ.get("SARSTELLAR_KILL") == "1")
    root = exports_root
    lock = threading.Lock()
    app = FastAPI(title="SARstellar job API")
    app.add_middleware(
        CORSMiddleware, allow_origins=["*"], allow_methods=["GET", "POST"], allow_headers=["*"],
        expose_headers=["Content-Disposition"],
    )

    def load(job_id: str) -> dict | None:
        """The job record; an open job older than the timeout is closed as an error first."""
        record = store.get(jobs.job_key(job_id))
        if record is None or record["status"] in jobs.TERMINAL:
            return record
        created = (store.get(f"meta:{job_id}") or {}).get("created")
        if created is not None and now() - created >= JOB_TIMEOUT_S:
            record = Job(job_id, "error", record["progress"], jobs.TIMEOUT_MESSAGE).to_json()
            store[jobs.job_key(job_id)] = record
        return record

    def cache_key(bbox: list[float], dates: list[str] | None) -> str:
        box = ",".join(f"{round(v, 4):.4f}" for v in bbox)
        span = "|".join(dates) if dates else f"default|{_day(now())}"  # "last 12 months" moves daily
        return f"cache:{CACHE_REVISION}:{box}|{span}"

    def reuse(key: str) -> dict | None:
        job_id = store.get(key)
        record = load(job_id) if job_id else None
        return record if record and record["status"] != "error" else None

    def create(bbox, dates, ip: str) -> str:
        """Count the job against both limits and open its record. Caller holds the lock."""
        t = now()
        recent = [x for x in (store.get(f"rl:{ip}") or []) if x > t - 3600]
        if len(recent) >= limits.per_ip_hour:
            wait = max(1, math.ceil(recent[0] + 3600 - t))
            raise HTTPException(429, RATE_MESSAGE, headers={"Retry-After": str(wait)})
        day_key = f"daily:{_day(t)}"
        used = store.get(day_key) or 0
        if used >= limits.per_day:
            raise HTTPException(429, DAILY_MESSAGE, headers={"Retry-After": "3600"})
        job_id = uuid.uuid4().hex[:16]
        store[f"rl:{ip}"] = [*recent, t]
        store[day_key] = used + 1
        store[f"meta:{job_id}"] = {"created": t}
        store[jobs.job_key(job_id)] = Job(job_id).to_json()
        store[cache_key(bbox, dates)] = job_id
        return job_id

    def submit_job(payload: Any, ip: str) -> dict:
        if is_killed():
            raise HTTPException(503, KILL_MESSAGE)
        try:
            bbox, dates = parse_request(payload)
        except ValueError as exc:
            raise HTTPException(422, str(exc)) from None
        key = cache_key(bbox, dates)
        with lock:
            hit = reuse(key)
            if hit is not None:
                return hit
            job_id = create(bbox, dates, ip)
        try:
            runner.submit(job_id, bbox, dates)
        except Exception:  # noqa: BLE001 - whatever the runner raised, the job ends as an error
            jobs.log.exception("could not start job %s", job_id)
            store[jobs.job_key(job_id)] = Job(job_id, "error", 0.0, jobs.GENERIC_MESSAGE).to_json()
        return store.get(jobs.job_key(job_id))

    @app.post("/jobs")
    async def post_job(request: Request):
        try:
            payload = await request.json()
        except ValueError:
            raise HTTPException(422, "The request body must be JSON.") from None
        return await run_in_threadpool(submit_job, payload, client_ip(request))

    @app.get("/jobs/{job_id}")
    def get_job(job_id: str):
        record = load(job_id) if _JOB_ID.fullmatch(job_id) else None
        if record is None:
            raise HTTPException(404, "No such job.")
        return record

    def serve(job_id: str, folder: str, name: str, **kw) -> FileResponse:
        if not _JOB_ID.fullmatch(job_id):
            raise HTTPException(404, "No such file.")
        if before_file_read is not None:
            try:
                before_file_read()
            except Exception:  # noqa: BLE001 - serve the file we have if the reload fails
                jobs.log.warning("volume reload failed", exc_info=True)
        path = os.path.join(root, folder, job_id, name)
        if not os.path.isfile(path):
            raise HTTPException(404, "No such file.")
        return FileResponse(path, **kw)

    @app.get("/exports/{job_id}/{name}")
    def get_export(job_id: str, name: str):
        if name not in _EXPORT_TYPES:
            raise HTTPException(404, "No such file.")
        return serve(job_id, "exports", name, media_type=_EXPORT_TYPES[name], filename=name)

    @app.get("/overlays/{job_id}/{name}")
    def get_overlay(job_id: str, name: str):
        if name not in _OVERLAYS:
            raise HTTPException(404, "No such file.")
        return serve(job_id, "overlays", name, media_type="image/png",
                     headers={"Cache-Control": "public, max-age=86400"})

    @app.get("/health")
    def health():
        return JSONResponse({"ok": True})

    return app
