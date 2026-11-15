# SARstellar

Two radars, one map: compare surface change seen by NISAR L-band and Sentinel-1
C-band on a shared one-hectare grid. The Python engine searches calibrated radar
passes, reads windowed data, tests for change, groups changed blocks, and exports
maps and evidence. A Modal API serves live analyses; saved stories work offline.

[Open the app](https://www.sarstellar.earth/) ·
[Measured scorecard](web/public/scorecard.json) ·
[Demo script and submission draft](docs/submission/demo-script.md)

The web app includes the change map, before/after swipe, synchronized L/C views,
evidence panels, a pass timeline, live box analysis, and the measured scorecard.
For local web development, use Node 22.12 or newer:

```powershell
cd web
npm ci
$env:VITE_API_URL = 'https://tejas-16842--sarstellar-web.us-east.modal.run'
npm run dev
```

`npm test` runs the frontend checks; `npm run build` creates the static site.
Vercel builds `web/` from GitHub's `main` branch with the same API URL configured.
When that environment variable is absent, drawn boxes use disclosed saved examples.

Requires Python 3.11 or newer. From the repository root, using PowerShell:

```powershell
python -m venv .venv
.venv\Scripts\python.exe -m pip install -e ".[dev,modal,ml]"
.venv\Scripts\python.exe -m pytest -q
```

Network tests are skipped by default. With Earthdata credentials configured:

```powershell
.venv\Scripts\python.exe -m pytest -m live
```

If an old pytest temporary directory is unreadable, choose a new repository-local
directory with `--basetemp=.pytest_tmp_new -p no:cacheprovider`.

The core package also runs locally:

```python
from sarstellar.pipeline import run_box

result = run_box(
    [-119.248, 48.119, -118.992, 48.290],
    ("2026-07-13", "2026-09-11"),
)
payload = result.to_json()
```

Earthdata access uses environment variables `EARTHDATA_USERNAME` and
`EARTHDATA_PASSWORD`, or a local netrc file. Keep credentials outside the repo.
Explanations fall back to templates when Anthropic access is unavailable.

The deployed API is
[SARstellar on Modal](https://tejas-16842--sarstellar-web.us-east.modal.run).
`GET /health` checks availability; `POST /jobs` accepts `bbox` and optional
`dates`; `GET /jobs/{job_id}` reports progress and the final result. Completed
jobs expose PNG overlays and GeoTIFF, CSV, and notebook downloads. Boxes must be
within the configured US bounds and no more than 20 km on either side.
Exported notebooks include the engine's Python source and its SHA-256 digest;
they do not depend on an unpublished Git branch. They install runtime dependencies
and use the reader's Earthdata login. NASA reprocessing can change later results.

To deploy from this checkout, configure Modal and its `earthdata` and `anthropic`
secrets, then run:

```powershell
$env:PYTHONUTF8 = '1'
$env:PYTHONIOENCODING = 'utf-8'
.venv\Scripts\modal.exe deploy modal_app/app.py
```

`SARSTELLAR_KILL=1` at deployment pauses live submissions. The API enforces
10 submissions per hour per IP and 200 per day overall. Frontend builds use
`VITE_API_URL=https://tejas-16842--sarstellar-web.us-east.modal.run`.

The three real pipeline stories and their overlay PNGs are in
`web/public/stories/`. Rebuild all three, or one story, with:

```powershell
.venv\Scripts\modal.exe run modal_app/stories.py
.venv\Scripts\modal.exe run modal_app/stories.py --only kaiser
```

Each story's source run and file hashes are recorded in
`web/public/stories/provenance.json`.

Story summaries use their saved pipeline outputs. Some stories compare several
NISAR dates with a Sentinel-1 pair; those area totals alone do not establish which
radar is better. The national scorecard uses one before-and-after pair per radar,
splits training and evaluation by state, and reports paired uncertainty on held-out
states. NISAR sampled every third pixel (the L30 comparison) and the full NISAR
series are separate comparisons. Stable
false-alarm rates come from independently selected stable sites. Missing data and
failed sites must be reported, and fixtures must remain marked `fixture: true`.

The site catalog is `modal_app/data/sites.json`; reference labels come from
DIST-ALERT-HLS, NIFC fire perimeters, DSWx water change, and CDL crops. Research,
scientific limitations, and the implementation plan are under `docs/`.

Run a small scorecard check, then the full catalog, with:

```powershell
.venv\Scripts\modal.exe run modal_app/scorecard.py --limit 5 --n-boot 20
.venv\Scripts\modal.exe run modal_app/scorecard.py
```

Per-site checkpoints on the `sarstellar-data` Volume let repeated runs reuse
successful reads. Use `--refresh` to recalculate them. The aggregate is written to
`web/public/scorecard.json`; the block table is saved as `modal_app/data/blocks.parquet`
and kept outside git. A smoke run reports `status: incomplete`; the full benchmark
requires at least 150 comparable sites and evaluable held-out results for all four
reference classes. Missing results remain unavailable rather than becoming zeros.
Use `--aggregate-only` to rebuild the statistics from saved site checkpoints without
reading the radar files again. Successful sites with no common comparison blocks
are listed separately from failed reads.

CDL labels cultivated land rather than confirmed crop change. DSWx-S1 flood
references also use Sentinel-1, so they are not independent sensor validation.
The selected event sites do not represent national change prevalence.

Recorded benchmark, November 15, 2026: 254 sites attempted, 242 processed, and
224 eligible for the paired comparison. The held-out set contains 60 sites in
12 states; 164 sites are used for training. The comparison covers 2,173,521 common
blocks. All 12 failures and 18 exclusions are listed in `scorecard.json`, alongside
source hashes, dependency versions, and the block-table checksum.

Primary fusion did not show a supported improvement over the better single radar
for any reference class. The table reports AUPRC differences, fusion minus the
single radar selected on training states, with paired site-bootstrap 95% intervals
from 500 draws:

| Reference class | Best single radar | AUPRC difference | 95% interval |
| --- | --- | ---: | --- |
| Forest loss | NISAR | -0.0731 | -0.1569 to -0.0091 |
| Burn | NISAR | +0.0368 | -0.0196 to +0.0893 |
| Open-water flood | Sentinel-1 | -0.0875 | -0.1510 to +0.0007 |
| Cropland proxy | NISAR | -0.0222 | -0.0770 to +0.0604 |

Only three held-out flood sites are eligible. Default stable-ground false-alarm
rates are 1.58% for NISAR, 3.36% for Sentinel-1, 4.26% for Fisher fusion, and 4.29%
for Bonferroni fusion; these exceed the original 1.5% target. The supplementary
learned fusion comparison improves the cropland-label proxy, which does not
establish improved detection of actual crop change. These limits are retained
in the report rather than tuning on the held-out results.
