"""The precomputed stories: the generated files in web/public/stories/, and the code that writes them.

`test_story_files_valid` checks what the build produced (run `modal run modal_app/stories.py`
to make it). The remaining tests also run offline, without requiring the separate web checkout.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest
from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))  # for `modal_app`

from modal_app import api, story_defs
from modal_app.story_defs import OVERLAY_NAMES, STORIES

from sarstellar.types import Result

STORIES_DIR = ROOT / "web" / "public" / "stories"
SAVED_RESULT = STORIES_DIR / "kaiser.json"
COLORS = {"L": "seen only by NISAR", "both": "by both", "C": "only by Sentinel-1"}


def _load(path: Path) -> Result:
    return Result.from_json(json.loads(path.read_text(encoding="utf-8")))


@pytest.mark.parametrize("story_id", list(STORIES))
def test_story_files_valid(story_id):
    path = STORIES_DIR / f"{story_id}.json"
    assert path.exists(), "run `modal run modal_app/stories.py` to build the stories"
    result = _load(path)
    assert result.fixture is False
    assert result.nisar["dates"] and len(result.nisar["dates"]) >= 2
    assert result.areas, "a story with no change areas has nothing to show"
    for key in ("change_png", "l_png", "c_png", "before_png", "after_png"):
        url = result.overlays[key]
        assert not url.startswith(("/", "http", "data:")), f"{key} must be relative: {url}"
        assert (STORIES_DIR / url).is_file(), f"{key} missing on disk: {url}"
        with Image.open(STORIES_DIR / url) as image:
            assert image.format == "PNG"
            assert 1 < image.width <= 2048 and 1 < image.height <= 2048
            image.verify()
    assert len(result.overlays["bounds"]) == 4
    assert result.exports == {"geotiff": None, "csv": None, "notebook": None}
    assert [round(v, 3) for v in result.bbox] == list(STORIES[story_id].bbox)


def test_story_index_matches_story_files():
    index = json.loads((STORIES_DIR / "index.json").read_text(encoding="utf-8"))
    assert [e["id"] for e in index] == list(STORIES)
    for entry in index:
        assert set(entry) == {"id", "title", "place", "dates", "summary"}
        result = _load(STORIES_DIR / f"{entry['id']}.json")
        assert entry["dates"] == [result.nisar["dates"][0], result.nisar["dates"][-1]]
        assert entry["summary"] == story_defs.summarize(STORIES[entry["id"]], result)


@pytest.mark.parametrize("story", STORIES.values(), ids=list(STORIES))
def test_story_boxes_are_valid_live_boxes(story):
    """A visitor can redraw each story's box: the job API accepts it as it is."""
    bbox, dates = api.parse_request({"bbox": list(story.bbox), "dates": list(story.dates)})
    assert bbox == list(story.bbox) and dates == list(story.dates)
    assert max(story_defs.box_km(story.bbox)) <= 20.0


@pytest.mark.parametrize("story", STORIES.values(), ids=list(STORIES))
def test_story_box_lies_inside_the_spike_box(story):
    w, s, e, n = story.bbox
    fw, fs, fe, fn = story.full_bbox
    assert fw <= w < e <= fe and fs <= s < n <= fn


def test_summary_is_written_from_the_result():
    result = _load(SAVED_RESULT)
    story = STORIES["kaiser"]
    text = story_defs.summarize(story, result)
    ha = {k: sum(a.area_ha for a in result.areas if a.agreement == k) for k in ("L", "both", "C")}
    assert f"{len(result.areas)} change areas covering {sum(ha.values()):,.0f} ha" in text
    for key, phrase in COLORS.items():
        assert f"{ha[key]:,.0f} ha {phrase}" in text
    biggest = max({a.cls for a in result.areas},
                  key=lambda c: sum(a.area_ha for a in result.areas if a.cls == c))
    assert biggest.replace("_", " ") in text
    assert "Cropped from the 48 by 34 km box" in text  # the Kaiser spike box is over 20 km
    assert "NISAR uses 5 passes and Sentinel-1 uses 2" in text
    assert "not an equal-date accuracy comparison" in text


def test_summary_without_areas_says_why():
    result = _load(SAVED_RESULT)
    result.areas = []
    result.message = "Most of this box has no valid radar data."
    assert story_defs.summarize(STORIES["edouard"], result).startswith(result.message)


def test_write_story_and_rebuild_index(tmp_path):
    payload = json.loads(SAVED_RESULT.read_text(encoding="utf-8"))
    pngs = {name: b"png-" + name.encode() for name in OVERLAY_NAMES}
    story_defs.write_story(tmp_path, STORIES["kaiser"], payload, pngs)
    for name in OVERLAY_NAMES:
        assert (tmp_path / "kaiser" / f"{name}.png").read_bytes() == pngs[name]
    assert json.loads((tmp_path / "kaiser.json").read_text(encoding="utf-8")) == payload

    entries = story_defs.rebuild_index(tmp_path)  # only the stories that exist are listed
    assert [e["id"] for e in entries] == ["kaiser"]
    assert json.loads((tmp_path / "index.json").read_text(encoding="utf-8")) == entries
    assert entries[0]["dates"] == [payload["nisar"]["dates"][0], payload["nisar"]["dates"][-1]]


def test_write_story_needs_all_five_overlays(tmp_path):
    with pytest.raises(ValueError, match="expected overlays"):
        story_defs.write_story(tmp_path, STORIES["kaiser"], {}, {"change": b"x"})


def test_write_story_rejects_fixtures(tmp_path):
    payload = json.loads(SAVED_RESULT.read_text(encoding="utf-8"))
    payload["fixture"] = True
    with pytest.raises(ValueError, match="real pipeline results"):
        story_defs.write_story(tmp_path, STORIES["kaiser"], payload,
                               {name: b"x" for name in OVERLAY_NAMES})
