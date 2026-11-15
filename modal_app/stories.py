"""Build the three precomputed stories with the real pipeline, then download them.

    modal run modal_app/stories.py                  (from the repo root; all three stories)
    modal run modal_app/stories.py --only kaiser    (one story)

Each story is one `run_box` call on Modal, the same code path as a live job (Modal fans the NISAR
reads out, one container per granule). Its five overlay PNGs and `result.json` are written to the
Volume `sarstellar-data` under `stories/{id}/`. This script then copies them into
`web/public/stories/` (`{id}.json`, `{id}/*.png`) and rewrites `index.json`. Overlay URLs in the
JSON are relative to the JSON file, like the fixtures', and `fixture` is false.

The boxes and dates live in `story_defs.py`.
"""

from __future__ import annotations

import json
from pathlib import Path

from modal_app.app import DATA, OPTIONAL, _read_all, anthropic, app, earthdata, volume

STORY_TIMEOUT_S = 1500  # a story reads up to a dozen granules; a live job gets 600 s


@app.function(secrets=[earthdata, anthropic, *OPTIONAL], volumes={DATA: volume},
              timeout=STORY_TIMEOUT_S, cpu=1.0, memory=2048)
def build_story(story_id: str) -> dict:
    """Run one story and return its `Result` as JSON; the files are on the Volume."""
    from modal_app import jobs, story_defs
    from sarstellar import pipeline

    story = story_defs.STORIES[story_id]
    folder = Path(DATA) / "stories" / story_id
    folder.mkdir(parents=True, exist_ok=True)

    def png_sink(name: str, png: bytes) -> str:
        (folder / f"{name}.png").write_bytes(png)
        return f"{story_id}/{name}.png"  # relative to the story JSON, as the fixtures do

    result = pipeline.run_box(
        list(story.bbox), story.dates, read_passes=jobs.make_read_passes(_read_all),
        png_sink=png_sink,
    )
    payload = result.to_json()
    (folder / "result.json").write_text(json.dumps(payload), encoding="utf-8")
    volume.commit()
    return payload


def _download(story_id: str, names: tuple[str, ...]) -> dict[str, bytes]:
    """The story's overlay PNGs, read back from the Volume."""
    return {
        name: b"".join(volume.read_file(f"stories/{story_id}/{name}.png")) for name in names
    }


@app.local_entrypoint()
def main(only: str = "") -> None:
    from modal_app import story_defs

    ids = [only] if only else list(story_defs.STORIES)
    unknown = [i for i in ids if i not in story_defs.STORIES]
    if unknown:
        raise SystemExit(f"unknown story {unknown}; choose from {list(story_defs.STORIES)}")

    out_dir = story_defs.STORIES_DIR
    out_dir.mkdir(parents=True, exist_ok=True)
    failed = []
    for story_id, outcome in zip(ids, build_story.map(ids, return_exceptions=True), strict=True):
        if isinstance(outcome, BaseException):
            failed.append(story_id)
            print(f"{story_id}: FAILED ({type(outcome).__name__}: {outcome})")
            continue
        story = story_defs.STORIES[story_id]
        pngs = _download(story_id, story_defs.OVERLAY_NAMES)
        story_defs.write_story(out_dir, story, outcome, pngs)
        print(f"{story_id}: {len(outcome['areas'])} areas -> {out_dir / (story_id + '.json')}")

    for entry in story_defs.rebuild_index(out_dir):
        print(f"{entry['id']}: {entry['dates'][0]} to {entry['dates'][1]}: {entry['summary']}")
    if failed:
        raise SystemExit(f"stories that failed: {failed}")
