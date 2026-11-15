"""Notebook export: a reproducible .ipynb for one analysis.

`build(bbox, granule_urls, dates)` returns the bytes of a Jupyter notebook that installs
`sarstellar` from the repo and calls `run_box` on the same box and dates, so anyone can re-run the
numbers they saw in the app. The notebook carries no credentials: reading NISAR and Sentinel-1
data needs the reader's own free NASA Earthdata login.
"""

from __future__ import annotations

from datetime import date, datetime

import nbformat
from nbformat import v4

REPO_URL = "git+https://github.com/saa938/sarstellar.git"

_INTRO = """# SARstellar: re-run this analysis

This notebook repeats one box analysis from the app: NISAR L-band and Sentinel-1 C-band change
detection on 1-hectare blocks (Benjamini-Hochberg FDR q = 0.05, at least 2 dB relative change,
areas of 3 ha or more), cause rules, and plain-language text.

**Before you run it:** you need a free NASA Earthdata login (https://urs.earthdata.nasa.gov).
Put it in `~/.netrc` (on Windows `~/_netrc`) as a `urs.earthdata.nasa.gov` entry, or set the
`EARTHDATA_USERNAME` and `EARTHDATA_PASSWORD` environment variables. Set `ANTHROPIC_API_KEY` if
you want Claude to word the explanations; without it the notebook uses fixed templates with the
same numbers. Reading a box takes a few minutes."""

_SUMMARY = """print(result.message or "OK")
print("NISAR track", result.nisar["track"], result.nisar["direction"], "dates", result.nisar["dates"])
print("Sentinel-1:", result.s1)
rows = [
    {
        "id": a.id, "agreement": a.agreement, "class": a.cls, "area_ha": round(a.area_ha, 1),
        "confidence": a.confidence_label, "change_date": a.change_date,
    }
    for a in result.areas
]
pd.DataFrame(rows)"""

_BANDS = """for a in result.areas[:3]:
    print(a.id, a.cls, f"{a.area_ha:.1f} ha", "-", a.plain_text)
    for e in a.evidence:
        print("   ", e.label, e.value, e.unit, e.ci or "", "|", e.note)"""


def _iso(value) -> str | None:
    if value is None:
        return None
    if isinstance(value, (date, datetime)):
        return value.isoformat()[:10]
    return str(value)[:10]


def build(bbox, granule_urls, dates=None) -> bytes:
    """The notebook as .ipynb bytes.

    `bbox` is (west, south, east, north); `granule_urls` the NISAR granules the app used (shown
    for provenance; `run_box` searches again, so a newer reprocessing could change the stack);
    `dates` is (start, end) as dates or ISO strings, or None for the last 12 months.
    """
    box = [float(v) for v in bbox]
    span = None if dates is None else [_iso(d) for d in dates]
    urls = [str(u) for u in granule_urls]
    params = (
        "# Parameters (edit these to analyse another box)\n"
        f"BBOX = {box!r}  # west, south, east, north (lon/lat, at most 20 km a side)\n"
        f"DATES = {None if span is None else tuple(span)!r}  # (start, end) ISO dates; None = last 12 months\n"
        "GRANULE_URLS = [  # NISAR granules behind the original result (for reference)\n"
        + "".join(f"    {u!r},\n" for u in urls)
        + "]"
    )
    run = (
        "import pandas as pd\n"
        "from sarstellar.pipeline import run_box\n\n"
        "result = run_box(BBOX, DATES)"
    )
    cells = [
        v4.new_markdown_cell(_INTRO),
        v4.new_code_cell(f"%pip install -q {REPO_URL}"),
        v4.new_code_cell(params),
        v4.new_code_cell(run),
        v4.new_code_cell(_SUMMARY),
        v4.new_code_cell(_BANDS),
    ]
    nb = v4.new_notebook(cells=cells)
    nb.metadata["kernelspec"] = {"display_name": "Python 3", "language": "python", "name": "python3"}
    nb.metadata["language_info"] = {"name": "python"}
    nbformat.validate(nb)
    return nbformat.writes(nb).encode("utf-8")
