"""Modal app `sarstellar`: the job API, the job runner and the granule reader.

    modal deploy modal_app/app.py        (from the repo root)

* `web` serves the FastAPI app from `api.py` (`POST /jobs`, `GET /jobs/{id}`, `/exports`,
  `/overlays`, `/health`). It lives in one container so its rate-limit lock is real.
* `run_job(job_id, bbox, dates)` runs one analysis (`run_box`) and records progress in the Dict
  `sarstellar-jobs`. Its files (overlays, exports) go to the Volume `sarstellar-data`.
* `read_pass(url, bbox, grid_dict)` reads one NISAR granule; `run_job` fans out to it, one
  container per granule, so a 12-date series reads in about the time of one date.

Secrets: `earthdata` (made by `scripts/make_earthdata_secret.py`) and `anthropic` are required;
`firms` (FIRMS_MAP_KEY) and `meteomatics` are attached only if they exist when you deploy.
Kill switch: deploy with `SARSTELLAR_KILL=1` in the environment and POST /jobs answers 503.
"""

from __future__ import annotations

import os
from pathlib import Path

import modal

ROOT = Path(__file__).resolve().parents[1]
DATA = "/data"
KILL = os.environ.get("SARSTELLAR_KILL", "") if modal.is_local() else ""

# The repo's own code is pip-installed (rasterio, h5py and pyproj ship their GDAL / HDF5 / PROJ
# in their wheels, so no apt packages are needed). `modal_app` is added last, as a plain mount.
image = (
    modal.Image.debian_slim(python_version="3.12")
    .add_local_file(ROOT / "pyproject.toml", "/repo/pyproject.toml", copy=True)
    .add_local_dir(ROOT / "core", "/repo/core", copy=True,
                   ignore=["**/__pycache__", "**/*.pyc", "**/*.egg-info"])
    .run_commands("pip install /repo fastapi")
    .env({"SARSTELLAR_KILL": KILL})
    .add_local_python_source("modal_app")
)

app = modal.App("sarstellar", image=image)
jobs_dict = modal.Dict.from_name("sarstellar-jobs", create_if_missing=True)
volume = modal.Volume.from_name("sarstellar-data", create_if_missing=True)
earthdata = modal.Secret.from_name("earthdata")
anthropic = modal.Secret.from_name("anthropic")


def _optional_secrets(*names: str) -> list:
    """The named secrets that exist now. Checked at deploy time only; the container gets the list."""
    if not modal.is_local():
        return []
    found = []
    for name in names:
        try:
            found.append(modal.Secret.from_name(name).hydrate())
        except modal.exception.NotFoundError:
            print(f"optional secret '{name}' not found; deploying without it")
    return found


OPTIONAL = _optional_secrets("firms", "meteomatics")


@app.function(secrets=[earthdata], timeout=300, retries=2, cpu=1.0, memory=4096)
def read_pass(url: str, bbox: list[float], grid_dict: dict | None = None):
    """One NISAR granule as 1-ha blocks: `(meta, blocks)`, or None if the box misses it."""
    from modal_app import jobs

    return jobs.read_one(url, bbox, grid_dict)


def _read_all(args: list[tuple]) -> list:
    """Every granule in parallel, results in order. A lost container or a timeout is an OSError."""
    try:
        return list(read_pass.starmap(args))
    except modal.exception.Error as exc:  # the read layer's own failures already are OSError
        raise OSError(f"remote read failed: {type(exc).__name__}") from exc


@app.function(secrets=[earthdata, anthropic, *OPTIONAL], volumes={DATA: volume},
              timeout=600, cpu=1.0, memory=2048)
def run_job(job_id: str, bbox: list[float], dates: list[str] | None = None) -> None:
    """Run one analysis and record the outcome under `job:{job_id}`."""
    from modal_app import jobs
    from sarstellar import pipeline

    jobs.limit_search()
    jobs.execute_job(
        jobs_dict, job_id, bbox, dates, pipeline.run_box, exports_root=DATA,
        read_passes=jobs.make_read_passes(_read_all), commit=volume.commit,
    )


class ModalRunner:
    """Starts `run_job` in its own container and returns at once."""

    def submit(self, job_id: str, bbox: list[float], dates: list[str] | None) -> None:
        run_job.spawn(job_id, bbox, dates)


def _reload_volume() -> None:
    volume.reload()  # see files other containers committed


@app.function(volumes={DATA: volume}, max_containers=1, scaledown_window=300)
@modal.concurrent(max_inputs=50)
@modal.asgi_app()
def web():
    from modal_app import api

    return api.create_app(jobs_dict, ModalRunner(), exports_root=DATA,
                          before_file_read=_reload_volume)
