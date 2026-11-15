"""Turn stages' Modal outputs (dance/<id>/ on the Volume, downloaded) into web bundles.

    python science/export_stage.py --raw ../raw --web web/public [--only punjab,iowa]

Writes web/public/stages/<id>/ per docs/v2/CONTRACT.md (via sarstellar.bundle) and rebuilds
web/public/stages/index.json from every stage present. Story text comes from science/stories.py.
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import UTC, datetime
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parent / "core"))
from stories import STORIES  # noqa: E402

from sarstellar.bundle import write_bundle  # noqa: E402


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--raw", type=Path, required=True)
    ap.add_argument("--web", type=Path, required=True)
    ap.add_argument("--only", default="")
    args = ap.parse_args()
    ids = [s for s in args.only.split(",") if s] or sorted(
        p.name for p in args.raw.iterdir() if (p / "stage.json").exists() and (p / "cube.npz").exists())
    ids = [i for i in ids if not STORIES.get(i, {}).get("hidden")]
    for sid in ids:
        entry = write_bundle(args.raw / sid, args.web / "stages" / sid, STORIES.get(sid, {}), sid)
        print(json.dumps(entry))
    entries = []
    for d in sorted((args.web / "stages").iterdir()):
        sj = d / "stage.json"
        if not sj.exists():
            continue
        s = json.loads(sj.read_text())
        story = STORIES.get(s["id"], {})
        if story.get("hidden"):
            continue
        entries.append({
            "id": s["id"], "name": s["name"], "country": s["country"],
            "center": [round((s["bbox"][0] + s["bbox"][2]) / 2, 4),
                       round((s["bbox"][1] + s["bbox"][3]) / 2, 4)],
            "move": story.get("move", "still"), "title": s["story"]["title"],
            "teaser": story.get("teaser", ""), "n_passes": len(s["dates"]),
            "first": s["dates"][0], "last": s["dates"][-1], "thumb": f"{s['id']}/img/thumb.webp",
            "order": story.get("order", 99),
        })
    entries.sort(key=lambda e: (e["order"], e["id"]))
    index = {"generated_at": datetime.now(UTC).isoformat(timespec="seconds"), "fixture": False,
             "stages": entries}
    (args.web / "stages" / "index.json").write_text(json.dumps(index, indent=1))
    print(f"index: {len(entries)} stages")


if __name__ == "__main__":
    main()
