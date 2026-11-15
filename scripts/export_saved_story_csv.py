"""Export recorded saved-story areas as CSV; no radar or reference data are reread.

    python scripts/export_saved_story_csv.py
    python scripts/export_saved_story_csv.py --check

Result JSON and overlay files are never modified. Class/date column names state their actual
meaning. The manifest and supplemental provenance tie each CSV to its exact source JSON.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import io
import json
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
STORIES = ROOT / "web" / "public" / "stories"
IDS = ("clearcuts", "kaiser", "edouard")
BANDS = ("HH", "HV", "VV", "VH")
COLUMNS = (
    "id", "cause_hypothesis", "agreement", "area_ha", "confidence", "confidence_label",
    "p_value", "first_flagged_acquisition", "plain_text",
    *(f"{band}_{stat}_db" for band in BANDS for stat in ("change", "ci_low", "ci_high")),
    "evidence_json", "series_json", "geometry_geojson", "interpretation_note",
)
NOTE = (
    "Recorded radar detections, not verified event extents. Cause labels are hypotheses; "
    "confidence is a heuristic rule score, not a calibrated cause probability. "
    "first_flagged_acquisition is an observation date, not a confirmed event date. "
    "Agreement labels summarize block majorities: L/C does not mean the other radar detected "
    "nothing; both includes shared majorities or split patches. Raw rule evidence is retained. "
    "Band changes and intervals are the saved evidence values in dB. "
    "CSV only; notebook and GeoTIFF are unavailable for these saved results. No scientific rerun."
)


def digest(blob: bytes) -> str:
    return hashlib.sha256(blob).hexdigest()


def encode_json(value) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"), allow_nan=False)


def area_row(area: dict) -> dict:
    row = {key: area[key] for key in ("id", "agreement", "area_ha", "confidence",
                                     "confidence_label", "p_value", "plain_text")}
    row["cause_hypothesis"] = area["class"]
    row["first_flagged_acquisition"] = area["change_date"]
    for band in BANDS:
        evidence = next((e for e in area["evidence"] if e["label"] == f"{band} change"), None)
        interval = evidence["ci"] if evidence else None
        row[f"{band}_change_db"] = evidence["value"] if evidence else None
        row[f"{band}_ci_low_db"] = interval[0] if interval else None
        row[f"{band}_ci_high_db"] = interval[1] if interval else None
    row["evidence_json"] = encode_json(area["evidence"])
    row["series_json"] = encode_json(area["series"])
    row["geometry_geojson"] = encode_json(area["geometry"])
    row["interpretation_note"] = NOTE
    return row


def make_csv(areas: list[dict]) -> bytes:
    stream = io.StringIO(newline="")
    writer = csv.DictWriter(stream, fieldnames=COLUMNS)
    writer.writeheader()
    writer.writerows(area_row(area) for area in areas)
    return stream.getvalue().encode("utf-8")


def verify_csv(blob: bytes, areas: list[dict]) -> None:
    reader = csv.DictReader(io.StringIO(blob.decode("utf-8"), newline=""))
    assert tuple(reader.fieldnames) == COLUMNS
    rows = list(reader)
    assert len(rows) == len(areas)
    assert len({row["id"] for row in rows}) == len(rows)
    for actual, area in zip(rows, areas, strict=True):
        expected = {key: "" if value is None else str(value) for key, value in area_row(area).items()}
        assert actual == expected, area["id"]
        assert actual["id"] == area["id"]
        assert actual["cause_hypothesis"] == area["class"]
        assert actual["first_flagged_acquisition"] == (area["change_date"] or "")
        for key in ("area_ha", "confidence", "p_value"):
            assert float(actual[key]) == area[key]
        for evidence in area["evidence"]:
            band = evidence["label"].removesuffix(" change")
            if band in BANDS and evidence["unit"] == "dB":
                assert float(actual[f"{band}_change_db"]) == evidence["value"]
                if evidence["ci"]:
                    assert float(actual[f"{band}_ci_low_db"]) == evidence["ci"][0]
                    assert float(actual[f"{band}_ci_high_db"]) == evidence["ci"][1]
        assert json.loads(actual["evidence_json"]) == area["evidence"]
        assert json.loads(actual["series_json"]) == area["series"]
        assert json.loads(actual["geometry_geojson"]) == area["geometry"]


def export(*, check: bool = False) -> dict:
    sources = {story: (STORIES / f"{story}.json").read_bytes() for story in IDS}
    provenance_path = STORIES / "provenance.json"
    provenance = json.loads(provenance_path.read_text(encoding="utf-8"))
    scientific_provenance = {key: value for key, value in provenance.items()
                             if key != "supplemental_exports"}
    recorded = {story["id"]: story for story in provenance["stories"]}
    manifest, artifacts = {}, {}
    for story_id, original in sources.items():
        source_sha = digest(original)
        assert recorded[story_id]["sha256"][f"{story_id}.json"] == source_sha
        payload = json.loads(original)
        blob = make_csv(payload["areas"])
        verify_csv(blob, payload["areas"])
        manifest[story_id] = {
            "csv": f"/stories/{story_id}/areas.csv", "sha256": digest(blob),
            "source_json": f"/stories/{story_id}.json", "source_json_sha256": source_sha,
            "row_count": len(payload["areas"]), "note": NOTE,
        }
        artifacts[story_id] = blob
    manifest_path = STORIES / "exports.json"
    manifest_blob = (json.dumps(manifest, indent=2, ensure_ascii=False) + "\n").encode("utf-8")
    if check:
        assert manifest_path.read_bytes() == manifest_blob
        supplemental = provenance["supplemental_exports"]
        assert supplemental["generator_sha256"] == digest(Path(__file__).read_bytes())
        assert supplemental["manifest_sha256"] == digest(manifest_blob)
        assert supplemental["stories"] == manifest
        for story_id, blob in artifacts.items():
            assert (STORIES / story_id / "areas.csv").read_bytes() == blob
            verify_csv(blob, json.loads(sources[story_id])["areas"])
    else:
        for story_id, blob in artifacts.items():
            (STORIES / story_id / "areas.csv").write_bytes(blob)
        manifest_path.write_bytes(manifest_blob)
        provenance["supplemental_exports"] = {
            "generated_at": datetime.now(UTC).isoformat(),
            "generator": "scripts/export_saved_story_csv.py",
            "generator_sha256": digest(Path(__file__).read_bytes()),
            "scientific_rerun": False, "manifest": "exports.json",
            "manifest_sha256": digest(manifest_blob), "stories": manifest,
            "notes": "CSV serialization of existing saved areas only. Original result JSON, "
                     "overlay hashes, pipeline source and prose-revision provenance are unchanged.",
        }
        assert {key: value for key, value in provenance.items()
                if key != "supplemental_exports"} == scientific_provenance
        provenance_path.write_text(json.dumps(provenance, indent=2, ensure_ascii=False) + "\n",
                                   encoding="utf-8")
    assert all((STORIES / f"{story}.json").read_bytes() == original
               for story, original in sources.items())
    for record in provenance["stories"]:
        for filename, expected_sha in record["sha256"].items():
            assert digest((STORIES / filename).read_bytes()) == expected_sha
    return {"mode": "check" if check else "exported", "total_rows": sum(
        entry["row_count"] for entry in manifest.values()), "stories": manifest,
        "original_results_and_overlays_unchanged": True}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    print(json.dumps(export(check=args.check), indent=2))
