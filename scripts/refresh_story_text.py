"""Refresh saved story prose without reading NASA data or rerunning any science.

    python scripts/refresh_story_text.py
    python scripts/refresh_story_text.py --check

Only area plain_text strings change. Scientific JSON is canonically identical before and after;
PNG hashes and original pipeline provenance are preserved. The revision records original/current
file hashes and the explanation source digest. --check verifies text and provenance without writes.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
from datetime import UTC, datetime
from pathlib import Path

from sarstellar import explain
from sarstellar.types import ChangeArea

ROOT = Path(__file__).resolve().parents[1]
STORIES = ROOT / "web" / "public" / "stories"
TEXT_FIELD = re.compile(r'("plain_text"\s*:\s*)"(?:\\.|[^"\\])*"')


def digest(blob: bytes) -> str:
    return hashlib.sha256(blob).hexdigest()


def scientific_json(payload: dict) -> bytes:
    scientific = {
        **payload,
        "areas": [{key: value for key, value in area.items() if key != "plain_text"}
                  for area in payload["areas"]],
    }
    return json.dumps(scientific, sort_keys=True, separators=(",", ":"), ensure_ascii=False,
                      allow_nan=False).encode("utf-8")


def refresh(*, check: bool = False) -> dict:
    path = STORIES / "provenance.json"
    provenance = json.loads(path.read_text(encoding="utf-8"))
    template_sha = digest(Path(explain.__file__).read_bytes())
    original_source = provenance["source_commit"]
    prepared, revisions = [], []
    n_areas = n_changed = 0
    for record in provenance["stories"]:
        story_id = record["id"]
        if story_id not in {"clearcuts", "kaiser", "edouard"}:
            raise ValueError(f"unexpected story ID: {story_id}")
        name = f"{story_id}.json"
        story_path = STORIES / name
        before = story_path.read_bytes()
        assert digest(before) == record["sha256"][name], f"stale provenance: {name}"
        for filename, expected in record["sha256"].items():
            assert digest((STORIES / filename).read_bytes()) == expected, filename
        payload = json.loads(before)
        expected = [explain.template_text(ChangeArea.from_json(area)) for area in payload["areas"]]
        changed = sum(area["plain_text"] != text for area, text in zip(payload["areas"], expected,
                                                                      strict=True))
        n_areas += len(expected)
        n_changed += changed
        iterator = iter(expected)
        revised, count = TEXT_FIELD.subn(
            lambda match, texts=iterator: match[1] + json.dumps(next(texts), ensure_ascii=False),
            before.decode("utf-8"),
        )
        assert count == len(payload["areas"]), f"unexpected plain_text count: {name}"
        after = revised.encode("utf-8")
        canonical = scientific_json(payload)
        assert scientific_json(json.loads(after)) == canonical, f"scientific JSON changed: {name}"
        assert all("Cause hypothesis:" in text and "independent verification is needed" in text
                   for text in expected)
        revision = {"file": name, "areas_checked": count, "areas_changed": changed,
                    "original_sha256": digest(before), "new_sha256": digest(after),
                    "scientific_sha256_before": digest(canonical),
                    "scientific_sha256_after": digest(scientific_json(json.loads(after)))}
        revisions.append(revision)
        prepared.append((story_path, after, record))
    if check:
        assert n_changed == 0, f"{n_changed} saved explanations differ from the current template"
        revisions_saved = provenance.get("text_revisions", [])
        assert revisions_saved and revisions_saved[-1]["template_sha256"] == template_sha
        latest = {record["file"]: record for record in revisions_saved[-1]["files"]}
        for record in revisions:
            saved = latest[record["file"]]
            assert saved["scientific_sha256_before"] == saved["scientific_sha256_after"]
            assert record["scientific_sha256_after"] == saved["scientific_sha256_after"]
            assert record["new_sha256"] == saved["new_sha256"]
        return {"mode": "check", "areas_checked": n_areas, "areas_changed": 0,
                "template_sha256": template_sha, "scientific_json_unchanged": True}
    if not n_changed:
        return {"mode": "unchanged", "areas_checked": n_areas, "areas_changed": 0}
    for story_path, after, record in prepared:
        story_path.write_bytes(after)
        record["sha256"][story_path.name] = digest(after)
    provenance.setdefault("text_revisions", []).append({
        "revised_at": datetime.now(UTC).isoformat(), "template_module": "sarstellar.explain",
        "template_sha256": template_sha, "original_source_commit": original_source,
        "scientific_rerun": False,
        "notes": "Prose only; no scientific rerun. Only area plain_text strings changed. "
                 "Original pipeline source, measurements, labels, dates, confidence and PNGs are retained.",
        "files": revisions,
    })
    assert provenance["source_commit"] == original_source
    path.write_text(json.dumps(provenance, indent=2, ensure_ascii=False) + "\n", encoding="utf-8",
                    newline="\n")
    return {"mode": "refreshed", "areas_checked": n_areas, "areas_changed": n_changed,
            "template_sha256": template_sha, "scientific_json_unchanged": True,
            "files": revisions}


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    print(json.dumps(refresh(check=args.check), indent=2))
