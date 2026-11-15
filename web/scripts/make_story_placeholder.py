#!/usr/bin/env python3
"""A placeholder story.json (web/public/story-placeholder/) so the story page can be built before the
science track's web/public/story/story.json lands. Images and dot clouds come from the real stage
bundles; every sentence and number is marked as a placeholder and the UI labels it as such.

Run from web/:  uv run --no-project --with numpy python scripts/make_story_placeholder.py
"""
import json
from pathlib import Path

import numpy as np

web = Path(__file__).resolve().parent.parent
stages = web / "public" / "stages"
out = web / "public" / "story-placeholder"
out.mkdir(parents=True, exist_ok=True)
rng = np.random.default_rng(3)


def stage(sid):
    m = json.loads((stages / sid / "stage.json").read_text())
    nx, ny, T = m["grid"]["nx"], m["grid"]["ny"], len(m["dates"])
    P = len(m["blocks"]["pols"])
    b = np.frombuffer((stages / sid / "blocks.bin").read_bytes(), np.uint8).reshape(T, P, nx * ny)
    return m, b


def cloud(b, t, n=700):
    P = b.shape[1]
    ok = (b[t] != 255).all(axis=0)
    idx = rng.choice(np.flatnonzero(ok), size=n, replace=False)
    hh = -40 + 0.2 * b[t, 0, idx].astype(float)
    hv = -40 + 0.2 * b[t, 1, idx].astype(float) if P > 1 else None
    return idx, [[round(float(hh[i]), 2), round(float(hv[i]), 2)] for i in range(n)] if hv is not None else None


def img(sid, t):
    return f"stages/{sid}/img/{t:03d}.webp"


examples = []
plan = [
    ("punjab", 2, 15, "Punjab, India", "Crop growth and harvest"),
    ("morton", 4, 24, "Morton, Washington", "Forest loss"),
    ("edouard", 23, 24, "Village Creek, Texas", "Flood under vegetation"),
    ("sylhet", 1, 5, "Sylhet, Bangladesh", "Open-water flood"),
    ("kaiser", 2, 7, "Kaiser Canyon, Washington", "Fire"),
]
for sid, t0, t1, kicker, title in plan:
    m, b = stage(sid)
    idx, cb = cloud(b, t0)
    ca = [[round(float(-40 + 0.2 * b[t1, 0, i]), 2), round(float(-40 + 0.2 * b[t1, 1, i]), 2)] for i in idx]
    med = []
    for t in range(t0, t1 + 1, max(1, (t1 - t0) // 5)):
        med.append({"date": m["dates"][t], "HH": round(float(np.median(-40 + 0.2 * b[t, 0, idx])), 2), "HV": round(float(np.median(-40 + 0.2 * b[t, 1, idx])), 2)})
    examples.append({
        "id": sid, "kicker": f"[placeholder] {kicker}", "title": f"[placeholder] {title}",
        "text": "[placeholder] Two or three sentences from the science track explain what happened here and which echo carried it.",
        "measure": {"value": "?", "unit": "", "label": "[placeholder] measured number"},
        "channel": "HV", "before": {"date": m["dates"][t0], "image": img(sid, t0)}, "after": {"date": m["dates"][t1], "image": img(sid, t1)},
        "path": med, "cloud_before": cb, "cloud_after": ca, "one_d": False,
    })
m, b = stage("greenland")
ok = (b[0] != 255).all(axis=0)
idx = rng.choice(np.flatnonzero(ok), size=900, replace=False)
series = [{"date": d, "HH": round(float(np.median(-40 + 0.2 * b[t, 0, idx])), 2)} for t, d in enumerate(m["dates"])]
examples.append({
    "id": "greenland", "kicker": "[placeholder] Kangerlussuaq, Greenland", "title": "[placeholder] Ice surface change",
    "text": "[placeholder] Over ice NISAR listens with HH only, so this example is a single line.",
    "measure": {"value": "?", "unit": "", "label": "[placeholder]"}, "channel": "HH",
    "before": {"date": m["dates"][0], "image": img("greenland", 0)}, "after": {"date": m["dates"][4], "image": img("greenland", 4)},
    "one_d": True, "series": series,
})

m, b = stage("punjab")
frames = [{"date": d, "image": img("punjab", t)} for t, d in enumerate(m["dates"])][::2]
_, chcloud = cloud(b, 10, 1500)
chips = [
    {"id": "water", "label": "Open water", "place": "[placeholder]", "date": m["dates"][3], "image": "stages/sylhet/img/thumb.webp", "HH": -24, "HV": -32, "text": "[placeholder] One line."},
    {"id": "field", "label": "Bare field", "place": "[placeholder]", "date": m["dates"][3], "image": "stages/punjab/img/thumb.webp", "HH": -13, "HV": -25, "text": "[placeholder] One line."},
    {"id": "crop", "label": "Growing crop", "place": "[placeholder]", "date": m["dates"][6], "image": "stages/iowa/img/thumb.webp", "HH": -10, "HV": -19, "text": "[placeholder] One line."},
    {"id": "forest", "label": "Forest", "place": "[placeholder]", "date": m["dates"][3], "image": "stages/morton/img/thumb.webp", "HH": -7, "HV": -13, "text": "[placeholder] One line."},
    {"id": "city", "label": "City", "place": "[placeholder]", "date": m["dates"][3], "image": "stages/central_valley/img/thumb.webp", "HH": 0, "HV": -11, "text": "[placeholder] One line."},
]
doc = {
    "placeholder": True,
    "hero": {"title": "[placeholder] Earth is dancing", "subtitle": "[placeholder] Subtitle from story.json.", "place": "Punjab, India", "frames": frames},
    "channels": {"title": "Two ways it listens", "text": ["[placeholder] HH sentence.", "[placeholder] HV sentence."], "chips": chips, "cloud": chcloud},
    "examples": examples,
    "proof": {
        "title": "Does it work?", "intro": "[placeholder] Intro.",
        "items": [
            {"id": "any", "kind": "dots", "statement": "[placeholder] Statement with a model and a guess.", "model": 0.5, "baseline": 0.2, "model_label": "[placeholder] model", "baseline_label": "[placeholder] guessing", "detail": "[placeholder] exact figures"},
            {"id": "s1", "kind": "bars", "statement": "[placeholder] Two bars.", "bars": [{"label": "[placeholder] A", "value": 0.3}, {"label": "[placeholder] B", "value": 0.05}], "detail": "[placeholder]"},
        ],
        "limits": ["[placeholder] A limit, in one sentence."],
    },
    "applications": [{"title": "[placeholder] Application", "text": "[placeholder] One line."}] * 3,
}
(out / "story.json").write_text(json.dumps(doc))
print("wrote", out / "story.json")
