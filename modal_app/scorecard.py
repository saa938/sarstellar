"""Run/resume the real scorecard: modal run modal_app/scorecard.py [--limit 5].

Per-site parquet checkpoints survive failed invocations on the sarstellar-data Volume.
The merged blocks.parquet stays outside git; only aggregate scorecard.json is publishable.
"""

from __future__ import annotations

import hashlib
import json
import logging
from pathlib import Path

from modal_app.app import DATA, ROOT, app, earthdata, image, volume
from modal_app.scorecard_paths import SCHEMA_VERSION, checkpoint_name, remote_checkpoint_path

batch_image = image  # site dicts are passed as inputs; never upload the large local block table


@app.function(image=batch_image, secrets=[earthdata], volumes={DATA: volume},
              timeout=1800, max_containers=64, cpu=1, memory=4096)
def score_site(site: dict, refresh: bool = False) -> dict:
    from modal_app import jobs
    from modal_app.scorecard_data import collect_site, parquet_bytes

    logging.basicConfig(level=logging.INFO)
    logging.getLogger("modal_app").setLevel(logging.DEBUG)
    logging.getLogger("fsspec").setLevel(logging.WARNING)
    jobs.limit_search()
    path = Path(DATA) / "scorecard" / SCHEMA_VERSION / checkpoint_name(site)
    if path.exists() and not refresh:
        return {"id": site["id"], "path": str(path), "cached": True}
    try:
        table = collect_site(site)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(parquet_bytes(table))
        volume.commit()
        return {"id": site["id"], "path": str(path), "n_blocks": len(table),
                "n_comparable": int(table.comparable.sum())}
    except Exception as exc:  # noqa: BLE001 - each failed site is retained in the batch audit
        error = {"id": site["id"], "error": f"{type(exc).__name__}: {exc}"}
        path.parent.mkdir(parents=True, exist_ok=True)
        path.with_suffix(".error.json").write_text(json.dumps(error))
        volume.commit()
        return error


@app.function(image=batch_image, volumes={DATA: volume}, timeout=3600, cpu=4, memory=16384)
def finish(sites: list[dict], outcomes: list[dict], n_boot: int = 500) -> dict:
    import pandas as pd

    from modal_app.scorecard_report import build_report

    volume.reload()
    tables, failures = [], []
    previous_path = Path(DATA) / "scorecard" / "scorecard.json"
    previous = json.loads(previous_path.read_text()) if previous_path.exists() else {}
    previous_failures = {item["id"]: item for item in previous.get("failed_sites", [])}
    for result in outcomes:
        if "error" in result:
            failures.append(result)
        else:
            try:
                tables.append(pd.read_parquet(result["path"]))
            except FileNotFoundError:
                error_path = Path(result["path"]).with_suffix(".error.json")
                failures.append(json.loads(error_path.read_text()) if error_path.exists() else
                                previous_failures.get(result["id"],
                                    {"id": result["id"], "error": "No completed site checkpoint"}))
    table = pd.concat(tables, ignore_index=True) if tables else pd.DataFrame()
    report = build_report(table, sites, failures=failures, n_boot=n_boot)
    out = Path(DATA) / "scorecard"
    out.mkdir(parents=True, exist_ok=True)
    if len(table):
        block_path = out / "blocks.parquet"
        table.to_parquet(block_path, index=False)
        with block_path.open("rb") as stream:
            report["provenance"]["blocks_sha256"] = hashlib.file_digest(stream, "sha256").hexdigest()
    text = json.dumps(report, indent=2, allow_nan=False)
    (out / "scorecard.json").write_text(text)
    volume.commit()
    return report


def download_blocks(destination: Path) -> None:
    """Stream large block tables from the Volume, avoiding a giant serialized function return."""
    partial = destination.with_suffix(".parquet.part")
    with partial.open("wb") as stream:
        for chunk in volume.read_file("scorecard/blocks.parquet"):
            stream.write(chunk)
    partial.replace(destination)


@app.function(image=batch_image, secrets=[earthdata], timeout=600, cpu=1, memory=2048)
def reference_check(site: dict) -> dict:
    """Check a reference provider on a real site without rereading either raw radar stack."""
    import numpy as np

    from sarstellar.grid import grid_for_bbox
    from sarstellar.scoring import block_labels

    lon = (site["bbox"][0] + site["bbox"][2]) / 2
    grid = grid_for_bbox(site["bbox"], 32600 + int((lon + 180) // 6) + 1)
    try:
        labels = block_labels(site, grid)
        return {"id": site["id"], "kind": site["kind"], "known": int((labels != "").sum()),
                "positive": int(np.isin(labels, ["forest_loss", "burn", "flood_open_water",
                                                 "crop_cycle"]).sum())}
    except Exception as exc:  # noqa: BLE001 - diagnostic retains unavailable provider explicitly
        return {"id": site["id"], "kind": site["kind"], "error": f"{type(exc).__name__}: {exc}"}


def reference_smoke():
    sites = json.loads((ROOT / "modal_app" / "data" / "sites.json").read_text())
    for kind in ("fire", "flood", "crops", "stable"):
        site = next(s for s in sites if s["kind"] == kind)
        print(json.dumps(reference_check.remote(site)))


@app.local_entrypoint()
def main(limit: int = 0, refresh: bool = False, n_boot: int = 500, aggregate_only: bool = False,
         check_references: bool = False):
    from sarstellar.scoring import assign_split, choose_holdout_states

    if check_references:
        reference_smoke()
        return
    sites = json.loads((ROOT / "modal_app" / "data" / "sites.json").read_text())
    sites = assign_split(sites, choose_holdout_states(sites))
    # Choose the split before limiting so smoke runs cannot change the eventual holdout.
    if limit:
        sites = sites[:limit]
    outcomes = []
    if aggregate_only:
        outcomes = [{"id": site["id"], "path": remote_checkpoint_path(site, DATA)} for site in sites]
    else:
        for i, result in enumerate(score_site.map(sites, kwargs={"refresh": refresh},
                                                  return_exceptions=True)):
            site = sites[i]
            if isinstance(result, BaseException):
                result = {"id": site["id"], "error": f"{type(result).__name__}: {result}"}
            outcomes.append(result)
            print(json.dumps(result))
    report = finish.remote(sites, outcomes, n_boot)
    destination = ROOT / "web" / "public" / "scorecard.json"
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(json.dumps(report, indent=2, allow_nan=False), encoding="utf-8")
    if report["n_processed_sites"]:
        local = ROOT / "modal_app" / "data" / "blocks.parquet"
        download_blocks(local)
        with local.open("rb") as stream:
            downloaded_hash = hashlib.file_digest(stream, "sha256").hexdigest()
        if downloaded_hash != report["provenance"]["blocks_sha256"]:
            raise OSError("Downloaded block table checksum differs from the scorecard provenance")
    print(f"Saved {destination}: {report['n_sites']}/{len(sites)} eligible sites, {report['status']}")
