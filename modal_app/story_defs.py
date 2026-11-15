"""The three precomputed stories: their boxes, and how their files are written.

No Modal in here, so the tests can import it. `modal_app/stories.py` runs the pipeline and calls
`write_story` for each result; `rebuild_index` then lists whatever story files exist.

Each story's `bbox` is at most 20 km a side (the live API's limit), so a visitor can redraw the
same box and get the same answer. Where the research spike used a bigger box, `bbox` is a 19 km
square cut from it, centred on the densest change found in the spike's 100 m block maps:
clearcuts on the window holding the most L-band forest-loss flags, Kaiser Canyon on the window
holding the most blocks inside the fire perimeter, Edouard on the window holding the most
floodplain blocks that brightened 3 dB or more in HH. `full_bbox` is the spike's box.
"""

from __future__ import annotations

import json
import math
from dataclasses import dataclass
from pathlib import Path

from sarstellar.types import Result

KM_PER_DEG = 111.32  # the same figure the job API uses to measure a box
OVERLAY_NAMES = ("change", "l", "c", "before", "after")
STORIES_DIR = Path(__file__).resolve().parents[1] / "web" / "public" / "stories"


@dataclass(frozen=True)
class Story:
    id: str
    title: str
    place: str
    bbox: tuple[float, float, float, float]  # west, south, east, north: what the pipeline runs on
    full_bbox: tuple[float, float, float, float]  # the research spike's box
    dates: tuple[str, str]  # NISAR search window (the spike's first and last pass)


STORIES: dict[str, Story] = {
    s.id: s
    for s in (
        Story(
            id="clearcuts", title="Forest change near Morton / Mineral", place="Morton / Mineral, WA",
            bbox=(-122.450, 46.618, -122.203, 46.788),
            full_bbox=(-122.45, 46.55, -122.05, 46.80),
            dates=("2026-05-21", "2026-09-30"),
        ),
        Story(
            id="kaiser", title="Kaiser Canyon Fire", place="Colville Reservation, WA",
            bbox=(-119.248, 48.119, -118.992, 48.290),
            full_bbox=(-119.3705, 48.0531, -118.7196, 48.3605),
            dates=("2026-07-13", "2026-09-11"),
        ),
        Story(
            id="edouard", title="Edouard floods under forest", place="Village Creek near Kountze, TX",
            bbox=(-94.255, 30.130, -94.058, 30.301),
            full_bbox=(-94.45, 30.10, -94.00, 30.55),
            dates=("2026-08-26", "2026-09-07"),
        ),
    )
}


def box_km(bbox) -> tuple[float, float]:
    """(width, height) of a lon/lat box in km, measured as the job API measures it."""
    w, s, e, n = bbox
    return (e - w) * KM_PER_DEG * math.cos(math.radians((s + n) / 2)), (n - s) * KM_PER_DEG


# --- the index entry ----------------------------------------------------------------------------


def _crop_note(story: Story) -> str:
    full_w, full_h = box_km(story.full_bbox)
    w, h = box_km(story.bbox)
    if max(full_w, full_h) <= 20:
        return ""
    return (f" Cropped from the {full_w:.0f} by {full_h:.0f} km box of the research spike to "
            f"{w:.0f} by {h:.0f} km, so you can rerun it live.")


def summarize(story: Story, result: Result) -> str:
    """One paragraph written from the pipeline's own numbers (spec 10b), plus the crop note."""
    note = _crop_note(story)
    if result.s1 and len(result.nisar["dates"]) != len(result.s1["dates"]):
        note += (
            f" NISAR uses {len(result.nisar['dates'])} passes and Sentinel-1 uses "
            f"{len(result.s1['dates'])}; these detection areas are not an equal-date "
            "accuracy comparison. Use the held-out scorecard for that comparison."
        )
    areas = result.areas
    if not areas:
        return f"{result.message or 'No change areas passed the tests in this box.'}{note}"
    by_agreement = {"L": 0.0, "both": 0.0, "C": 0.0}
    by_class: dict[str, float] = {}
    for a in areas:
        by_agreement[a.agreement] += a.area_ha
        by_class[a.cls] = by_class.get(a.cls, 0.0) + a.area_ha
    top = sorted(by_class.items(), key=lambda kv: -kv[1])[:2]
    classes = " and ".join(f"{name.replace('_', ' ')} ({ha:,.0f} ha)" for name, ha in top)
    total = sum(by_agreement.values())
    n = len(areas)
    return (
        f"{n} change area{'' if n == 1 else 's'} covering {total:,.0f} ha: "
        f"{by_agreement['L']:,.0f} ha seen only by NISAR L-band, {by_agreement['both']:,.0f} ha by "
        f"both sensors, {by_agreement['C']:,.0f} ha only by Sentinel-1 C-band. "
        f"Largest {'class' if len(top) == 1 else 'classes'}: {classes}.{note}"
    )


def index_entry(story: Story, result: Result) -> dict:
    """`{id, title, place, dates, summary}`; `dates` are the first and last NISAR pass compared."""
    dates = result.nisar["dates"]
    return {
        "id": story.id, "title": story.title, "place": story.place,
        "dates": [dates[0], dates[-1]], "summary": summarize(story, result),
    }


# --- files --------------------------------------------------------------------------------------


def write_story(out_dir: Path, story: Story, result_json: dict, pngs: dict[str, bytes]) -> None:
    """Write `{id}.json` and `{id}/{name}.png` for the five overlays under `out_dir`."""
    if set(pngs) != set(OVERLAY_NAMES):
        raise ValueError(f"expected overlays {sorted(OVERLAY_NAMES)}, got {sorted(pngs)}")
    result = Result.from_json(result_json)
    if result.fixture:
        raise ValueError("precomputed stories require real pipeline results, not fixtures")
    for name in OVERLAY_NAMES:
        if result.overlays[f"{name}_png"] != f"{story.id}/{name}.png":
            raise ValueError(f"unexpected {name} overlay URL for story {story.id}")
    folder = out_dir / story.id
    folder.mkdir(parents=True, exist_ok=True)
    for name, png in pngs.items():
        (folder / f"{name}.png").write_bytes(png)
    (out_dir / f"{story.id}.json").write_text(
        json.dumps(result_json, indent=1, ensure_ascii=False, allow_nan=False) + "\n",
        encoding="utf-8",
    )


def rebuild_index(out_dir: Path) -> list[dict]:
    """Write `index.json` for the story files that exist, in `STORIES` order; return its entries."""
    entries = []
    for story in STORIES.values():
        path = out_dir / f"{story.id}.json"
        if path.exists():
            result = Result.from_json(json.loads(path.read_text(encoding="utf-8")))
            entries.append(index_entry(story, result))
    (out_dir / "index.json").write_text(
        json.dumps(entries, indent=1, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    return entries
