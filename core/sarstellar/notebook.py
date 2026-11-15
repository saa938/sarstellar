"""Notebook export: a reproducible .ipynb for one analysis.

`build(bbox, granule_urls, dates)` returns a notebook carrying the installed engine's Python
source and default dependency requirements. It does not need an unpublished Git branch to
repeat an analysis. The notebook carries no credentials: reading NISAR and Sentinel-1 data
needs the reader's own free NASA Earthdata login.
"""

from __future__ import annotations

import base64
import hashlib
import io
import re
import zipfile
from datetime import date, datetime
from importlib import metadata
from pathlib import Path

import nbformat
from nbformat import v4

_INTRO = """# SARstellar: re-run this analysis

This notebook repeats one box analysis from the app: NISAR L-band and Sentinel-1 C-band change
detection on 1-hectare blocks (Benjamini-Hochberg FDR q = 0.05, at least 2 dB relative change,
areas of 3 ha or more), cause rules, and plain-language text.

**Before you run it:** you need a free NASA Earthdata login (https://urs.earthdata.nasa.gov).
Put it in `~/.netrc` (on Windows `~/_netrc`) as a `urs.earthdata.nasa.gov` entry, or set the
`EARTHDATA_USERNAME` and `EARTHDATA_PASSWORD` environment variables. Set `ANTHROPIC_API_KEY` if
you want Claude to word the explanations; without it the notebook uses fixed templates with the
same numbers. Reading a box takes a few minutes.

The engine source used to export this notebook is embedded below, with a SHA-256 checksum.
The setup cell loads that copy instead of downloading a Git branch. Install the listed runtime
dependencies once; if they are already installed, skip the dependency-install cell. The source
and parameters are captured, but NASA data and reference products may later be reprocessed.
`GRANULE_URLS` records the original inputs; `run_box` searches the catalog again."""

_BOOTSTRAP = '''import base64
import hashlib
import importlib
import io
from pathlib import Path, PurePosixPath
import sys
import tempfile
import zipfile

archive = base64.b64decode(SOURCE_ARCHIVE_B64, validate=True)
if hashlib.sha256(archive).hexdigest() != SOURCE_SHA256:
    raise ValueError("Embedded SARstellar source checksum does not match")
SOURCE_DIR_HANDLE = tempfile.TemporaryDirectory(prefix="sarstellar-source-")
SOURCE_ROOT = Path(SOURCE_DIR_HANDLE.name)
with zipfile.ZipFile(io.BytesIO(archive)) as package:
    for member in package.infolist():
        path = PurePosixPath(member.filename)
        if (path.is_absolute() or ".." in path.parts or "\\\\" in member.orig_filename
                or ":" in member.filename
                or not path.parts or path.parts[0] != "sarstellar" or path.suffix != ".py"):
            raise ValueError("Unsafe path in embedded source archive")
        target = SOURCE_ROOT.joinpath(*path.parts)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(package.read(member))
sys.path.insert(0, str(SOURCE_ROOT))
for name in list(sys.modules):
    if name == "sarstellar" or name.startswith("sarstellar."):
        del sys.modules[name]
importlib.invalidate_caches()
from sarstellar.pipeline import run_box
print("Loaded embedded SARstellar engine", SOURCE_SHA256[:12])
'''


def _source_archive() -> bytes:
    """Only package Python files, in deterministic order, with no filesystem paths or secrets."""
    root = Path(__file__).resolve().parent
    stream = io.BytesIO()
    with zipfile.ZipFile(stream, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for source in sorted(root.rglob("*.py")):
            if source.is_symlink():
                continue
            name = "sarstellar/" + source.relative_to(root).as_posix()
            info = zipfile.ZipInfo(name, date_time=(1980, 1, 1, 0, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            archive.writestr(info, source.read_bytes())
    return stream.getvalue()


def _runtime_requirements() -> list[str]:
    """Published package metadata supplies default requirements; optional extras stay optional."""
    requirements = metadata.requires("sarstellar") or []
    return [r for r in requirements if not re.search(r"\bextra\b", r.partition(";")[2])]

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
    archive = _source_archive()
    digest = hashlib.sha256(archive).hexdigest()
    requirements = _runtime_requirements()
    install = (
        "# Optional: pip install the default runtime dependencies (no Git checkout needed).\n"
        "import subprocess\nimport sys\n"
        f"RUNTIME_REQUIREMENTS = {requirements!r}\n"
        'subprocess.check_call([sys.executable, "-m", "pip", "install", *RUNTIME_REQUIREMENTS])'
    )
    setup = (
        f"SOURCE_SHA256 = {digest!r}\n"
        f"SOURCE_ARCHIVE_B64 = {base64.b64encode(archive).decode('ascii')!r}\n"
        + _BOOTSTRAP
    )
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
        v4.new_code_cell(install, metadata={"tags": ["install-dependencies"]}),
        v4.new_code_cell(setup, metadata={"tags": ["embedded-source"]}),
        v4.new_code_cell(params),
        v4.new_code_cell(run),
        v4.new_code_cell(_SUMMARY),
        v4.new_code_cell(_BANDS),
    ]
    nb = v4.new_notebook(cells=cells)
    nb.metadata["kernelspec"] = {"display_name": "Python 3", "language": "python", "name": "python3"}
    nb.metadata["language_info"] = {"name": "python"}
    nb.metadata["sarstellar"] = {"source_sha256": digest, "source_format": "zip-python-v1",
                                 "runtime_requirements": requirements,
                                 "provenance": "Installed engine source at export time"}
    nbformat.validate(nb)
    return nbformat.writes(nb).encode("utf-8")
