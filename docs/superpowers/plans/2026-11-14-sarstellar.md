# SARstellar Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ship "two radars, one map": a NISAR-vs-Sentinel-1 change engine on Modal, a React/MapLibre app with three stories, and a 300-site national scorecard whose headline is a held-out-state test of whether fusing both radars beats either alone, submitted by Sun 2026-11-15 15:00 PT.

**Priority (user decision):** radar comparison + rigorous scorecard (A2–A4, C1, C2) before AI features. The learned cause model is stretch S0; the LLM is a thin wording layer with templates as the default.

**Architecture:** A pure-Python package `sarstellar` (`core/`) does search → read → 1-ha blocks → omnibus test → rules → areas → render → explain, behind `run_box()`. `modal_app/` wraps it as a FastAPI job API plus batch jobs (stories, scorecard, training). `web/` is a static Vite app that reads static stories/scorecard JSON and talks to the job API. The `Result` JSON shape is the seam between tracks.

**Tech Stack:** Python 3.12 (numpy, scipy, h5py, fsspec+aiohttp, earthaccess, pyproj, rasterio, shapely, pillow, anthropic, nbformat, fastapi, lightgbm, pandas, pyarrow, pytest), Modal 1.6, Vite 8.3.8 + React 19.3.1 + TypeScript 5.9.3, maplibre-gl 6.18.0, @maplibre/maplibre-gl-compare 0.5.0, @watergis/maplibre-gl-terradraw 1.17.0, recharts 3.10.1, vitest.

**Spec:** `docs/superpowers/specs/2026-11-14-sarstellar-design.md`. Data facts: `docs/research/*.md`. Working reference code (insights only, do not import): `scripts/spikes/spike_lib.py`.

## Global Constraints

- Deadline: submitted by Sun 2026-11-15 15:00 PT (hard limit 17:00 PT).
- Ownership: Track A/C write only `core/`, `modal_app/`, `pyproject.toml`, `tests/`; Track B writes only `web/` except the generated drop folders `web/public/stories/` and `web/public/scorecard.json`, which only Track A/C jobs write. One writer per worktree. Teammate A merges to `main`.
- Files under 500 lines.
- NISAR collections: `NISAR_L2_GCOV_PROVISIONAL_V1`, `NISAR_L2_GCOV_V1`. Never BETA. Sentinel-1: `OPERA_L2_RTC-S1_V1`.
- Permanent NISAR gap: 2026-07-27T22:03Z → 2026-08-10T00:55Z.
- Block = 10×10 px at 10 m = 1 ha; a block needs ≥ 50% valid pixels. Valid NISAR pixel: `mask` in 1..254 on every date, value finite and > 0.
- Detection: BH-FDR q = 0.05; changed = significant AND |relative Δ| ≥ 2.0 dB; change areas ≥ 3 ha.
- Box limits: w < e, s < n, inside US bounds (lon −180..−60, lat 17..72), each side ≤ 20 km.
- API guards: 10 jobs/hour per IP, 200 jobs/day total, cache by (bbox rounded to 1e-4, dates), kill switch env `SARSTELLAR_KILL=1` → 503 `{"detail":"Live analysis is paused; stories and scorecard still work."}`.
- Colors: only NISAR `#f59e0b`, both `#a78bfa`, only Sentinel-1 `#22d3ee`.
- The LLM only writes `plain_text`; class, confidence and evidence come from rules/model. Template fallback on any LLM error or missing key. Model `claude-sonnet-5-5`.
- No secrets in the repo; never print `~/_netrc`. Modal secrets: `earthdata` (`EARTHDATA_USERNAME`, `EARTHDATA_PASSWORD`; created in A7 from `~/_netrc` by a script that never echoes values) and `anthropic` (`ANTHROPIC_API_KEY`, already created).
- Weather: Open-Meteo historical archive API (free, no key) for `min_temp_c` and `rain_mm` at pass dates.
- Domain: `sarstellar.earth` (claimed via Porkbun) → points at the Vercel deployment.
- Every number shown or pitched comes from this pipeline (spec §10b). Spike-derived fixtures carry `"fixture": true`.
- Network tests are marked `@pytest.mark.live` and skipped unless run with `-m live`.

## Review Focus

1. Box with no usable NISAR stack (no coverage, BETA only, every pass mixed-mode) → job ends `error` with "No calibrated NISAR passes cover this box between {start} and {end}." (test in Task A6, UI in B4).
2. Box straddling a UTM zone boundary, or stacks whose EPSG differs → pick one stack, put Sentinel-1 on that stack's grid, never mix EPSGs in a series (test in Task A2).
3. Box mostly ocean/fill (fewer than 20% valid blocks) → `done` with zero areas and message "Most of this box has no valid radar data." (test in Task A6).
4. ASF 5xx/timeouts mid-read → 6 retries with exponential backoff, then job `error` with "NASA's data server didn't respond; try again in a few minutes." within 600 s (tests in A2 and A7).
5. Oversized/invalid box → HTTP 422 with a readable `detail`; the UI blocks boxes over 20 km a side before submitting (tests in A7 and B4).

---

## Contract (shared by all tracks)

`core/sarstellar/types.py` (Python) and `web/src/types.ts` (TS) define the same shape. JSON keys are exactly:

```
Result { bbox:[w,s,e,n], message:str|null, fixture:bool,
  nisar:{track:int, direction:"A"|"D", dates:[iso]}, s1:{track:int, dates:[iso]}|null,
  overlays:{change_png, l_png, c_png, before_png, after_png: url, bounds:[[lon,lat]x4 UL,UR,LR,LL]},
  areas:[ChangeArea], people:{svi_tracts:[{geoid, rpl_themes, name}]},
  exports:{geotiff:url|null, csv:url|null, notebook:url|null} }
ChangeArea { id:str, geometry:GeoJSON Polygon|MultiPolygon, agreement:"L"|"C"|"both", class:str,
  area_ha:float, confidence:float 0..1, confidence_label:"High"|"Medium"|"Low", p_value:float,
  change_date:iso|null, evidence:[{label, value, ci:[lo,hi]|null, unit, note}], plain_text:str,
  series:{dates:[iso], HH:[float|null], HV:[...], VV:[...], VH:[...]} }
Job { job_id, status:"queued"|"running"|"done"|"error", progress:0..1, message:str, result:Result|null }
```

Class strings: `forest_loss, burn, flood_open_water, flooded_vegetation, crop_cycle, harvest, low_veg_loss, soil_wetting, construction, landslide, wet_snow, uncertain` (freeze-up is suppressed, never emitted).

## Milestones (PT)

| When | Done |
|---|---|
| Sat 20:00 | A1–A4, B1–B2 merged; Modal secrets set |
| Sat 23:59 | A5–A7 deployed: live draw-a-box works end to end; C1 sites.json |
| Sun 06:00 | A8 stories, C2 scorecard run complete (overnight); B3–B5 |
| Sun 11:00 | C2 fusion results final, B6 pages with real numbers, B7 deployed; feature freeze |
| Sun 15:00 | D1 submitted |

Parallel start: A1, B1 immediately; A2/A3/A4/A5 as soon as A1 merges; Track B never waits (fixtures).

---

## Track A: core engine and API

### Task A1: Package scaffold and contract types

**Files:** Create `pyproject.toml`, `core/sarstellar/__init__.py`, `core/sarstellar/types.py`, `tests/test_types.py`, `tests/conftest.py`

**Interfaces:**
- Produces: dataclasses `Granule(ur, url, collection, start: datetime, track: int, frame: int, direction: str, bandwidth_mhz: float, crid: str, counter: int, mixed_mode: bool, size_gb: float)`, `Stack(track, direction, bandwidth_mhz, crid, granules: list[Granule])` with `.dates`, `Grid(epsg: int, xmin, xmax, ymin, ymax, res=100.0)` with `.shape -> (ny, nx)` and `.transform()`, `Evidence`, `ChangeArea`, `Result`, `Job` matching the Contract; `Result.to_json() -> dict` and `Result.from_json(d) -> Result`; exception `NoUsablePasses(Exception)`.

- [ ] Step 1: tests `test_result_roundtrip` (a Result with one ChangeArea survives `from_json(to_json())` unchanged and `to_json()["areas"][0]["class"] == "forest_loss"`, i.e. the Python attr `cls` serializes as `class`), `test_grid_shape` (`Grid(32610, 0, 1000, 0, 2000).shape == (20, 10)`), `test_conftest_marks_live` (live marker registered).
- [ ] Step 2: run `pytest -q` → fails (module missing).
- [ ] Step 3: implement; `pyproject.toml` with package dir `core`, optional groups `dev` (pytest, ruff) and `modal`; `conftest.py` adds `--run-live` / `-m live` skip logic.
- [ ] Step 4: `pip install -e .[dev]` then `pytest -q` → pass. Freeze resolved versions into `requirements.lock`.
- [ ] Step 5: commit `feat(core): package scaffold and Result contract`.

### Task A2: Grid, remote read, block averaging

**Files:** Create `core/sarstellar/grid.py`, `core/sarstellar/read.py`, `tests/test_grid.py`, `tests/test_read.py`

**Interfaces:**
- Consumes: `Grid`.
- Produces: `grid_for_bbox(bbox, epsg) -> Grid` (snapped outward to 100 m), `valid_mask(mask, *arrs) -> ndarray[bool]`, `block_mean(a, valid, block=10, min_valid_frac=0.5) -> ndarray` (linear, NaN where too few valid), `to_grid(src, transform, crs, grid) -> ndarray` (average resampling), `lonlat_corners(grid) -> [[lon,lat]x4]`, `open_remote_h5(url, fs, max_retries=6) -> (fileobj, h5py.File)`, `read_gcov_window(url, bbox, fs, grid=None) -> (meta: dict, arrays: {"HH","HV","mask"}, Grid)`, `read_rtc_to_grid(urls: list[str], grid, fs) -> {"VV": ndarray, "VH": ndarray}` (linear, block grid), `https_fs() -> fsspec filesystem` (earthaccess netrc/env login).

- [ ] Step 1: tests: `test_block_mean_masks` (4×4 ones with one quadrant invalid, block=2 → that block NaN when min_valid_frac=1.0), `test_grid_snaps_100m`, `test_utm_zone_straddle` (bbox −120.05..−119.95 at 47°N with epsg 32610 gives a grid whose `lonlat_corners` contain the bbox), `test_retry_then_succeed` (fake fetcher raises twice then returns bytes; result correct, 2 retries logged), `test_retry_exhausted_raises` (always raises → `IOError` after 6 tries, sleep patched), live `test_live_kaiser_window` (Kaiser pre granule from `docs/research/kaiser-spike.md`, small bbox; `meta["crid"] == "P05023"`, HH shape divisible by 10).
- [ ] Step 2: `pytest tests/test_grid.py tests/test_read.py -q` → fail.
- [ ] Step 3: implement. Port the windowing/lattice logic and retrying fetcher idea from `scripts/spikes/spike_lib.py` (fsspec `blockcache` 8 MiB; h5py `page_buf_size=16 MiB`, `rdcc_nbytes=4 MiB`); `read_gcov_window` raises `ValueError("EPSG differs")` if `grid.epsg` ≠ file EPSG.
- [ ] Step 4: tests pass; `pytest -m live tests/test_read.py` passes locally with `_netrc`.
- [ ] Step 5: commit `feat(core): grid, remote GCOV/RTC read with retries`.

### Task A3: Search and stack building

**Files:** Create `core/sarstellar/search.py`, `tests/test_search.py`, `tests/fixtures/umm/*.json` (5–8 recorded CMR UMM-G records: two `_001/_002` duplicates, one 5 MHz-only, one mixed-mode, one BETA, normal pairs on two tracks)

**Interfaces:**
- Produces: `parse_umm(umm: dict) -> Granule`, `search_gcov(bbox, start: date, end: date) -> list[Granule]` (CMR by the two short names only), `dedupe(gs) -> list[Granule]` (keep highest counter per acquisition), `build_stacks(gs) -> list[Stack]` (group by track, direction, bandwidth, crid; drop bandwidth < 20 MHz and mixed-mode; sort by date count desc), `pick_pair(stack, dates: tuple[date,date] | None) -> tuple[Granule, Granule]` (default: earliest and latest), `search_rtc_s1(bbox, around: date, max_days=6) -> list[dict]` (`{"track", "date", "urls_vv", "urls_vh"}` grouped by track and date, nearest date first).

- [ ] Step 1: tests on fixtures: `test_dedupe_keeps_highest_counter`, `test_drops_5mhz_and_mixed`, `test_beta_never_returned` (search builds CMR params with only the two short names), `test_stacks_split_by_crid` (P05023 and P05036 dates land in different stacks), `test_pick_pair_default_extremes`, `test_pair_never_spans_gap_as_same_date`, live `test_live_search_tulare` (≥ 20 granules in Tulare bbox, none with "BETA" in collection).
- [ ] Step 2: fail. Step 3: implement (UMM `AdditionalAttributes` names in `docs/research/data-spike.md`). Step 4: pass.
- [ ] Step 5: commit `feat(core): CMR search, dedupe, stacks`.

### Task A4: Detection

**Files:** Create `core/sarstellar/detect.py`, `tests/test_detect.py`

**Interfaces:**
- Produces: `stable_mask(deltas_db: list[ndarray], thresh_db=1.0) -> ndarray[bool]`, `relative_delta(delta_db, stable) -> ndarray` (subtract median over stable), `estimate_enl(series_lin: ndarray[T,ny,nx], stable) -> float` (median over stable blocks of mean²/var across time, ddof=1, clipped to [1, 10000]), `omnibus(channels: list[ndarray[T,ny,nx]], enls: list[float]) -> (p: ndarray, change_idx: ndarray[int])` (change_idx = index of first date after the change, −1 if none), `bh_fdr(p, q=0.05) -> ndarray[bool]`, `changed(p, rel_delta_db, q=0.05, min_db=2.0) -> ndarray[bool]`.

- [ ] Step 1: tests with synthetic gamma blocks (`rng.gamma(n, mean/n)`): `test_enl_recovers_truth` (n=60 → estimate within ±20%), `test_null_false_alarm` (no change, 3 dates, 20,000 blocks, α=0.01 → FA rate ≤ 0.015), `test_detects_3db_step` (half the blocks drop 3 dB at date 2 of 4 with n=60 → ≥ 95% detected, `change_idx == 2`), `test_bh_fdr_monotone`, `test_min_effect_gate` (significant 1 dB change → `changed` False), `test_relative_delta_removes_shift` (+0.5 dB scene shift → median relative Δ over stable ≈ 0).
- [ ] Step 2: fail.
- [ ] Step 3: implement the Conradsen 2016 sequential omnibus for diagonal covariance (per channel, summed):

```
k dates, intensities s_1..s_k, ENL n, S_j = s_1+...+s_j
omnibus:  -2lnQ = -2n[k ln k + Σ ln s_i - k ln S_k]          df = p(k-1), summed over p channels
rho = 1 - (k/n - 1/(n k)) / (6(k-1))   (per channel; use -2 rho lnQ)
step j=2..k: -2lnR_j = -2n[j ln j - (j-1)ln(j-1) + (j-1)ln S_{j-1} + ln s_j - j ln S_j]   df = p
change_idx = first j (0-based j-1) with p_j < 0.01 when omnibus p < 0.01; else -1
```

- [ ] Step 4: pass. Step 5: commit `feat(core): omnibus change test with empirical ENL`.

### Task A5: Rules, areas, render, explain

**Files:** Create `core/sarstellar/rules.py`, `core/sarstellar/areas.py`, `core/sarstellar/render.py`, `core/sarstellar/explain.py`, `tests/test_rules.py`, `tests/test_areas.py`, `tests/test_explain.py`

**Interfaces:**
- Produces: `AreaStats` dataclass (`dHH, dHV, dVV, dVH` median relative dB or None; `ci` per band; `pre_HH, pre_HV`; `agreement`; `landcover: str`; `hand_m, slope_deg: float|None`; `firms_count: int`; `in_fire_perimeter: bool`; `cdl_crop: bool`; `min_temp_c, rain_mm: float|None`), `classify(stats, model=None) -> (cls: str, confidence_label: str, evidence: list[Evidence])` (`model` is C3's `CauseModel`; ignored when None); `label_areas(changed_L, changed_C, grid, min_ha=3) -> list[(geometry, block_mask, agreement)]`; `render_png(values, grid, kind: "delta"|"agreement"|"backscatter") -> (png_bytes, bounds)` (reprojected to EPSG:3857, ≤ 2048 px a side, transparent NaN); `template_text(area: ChangeArea) -> str`; `explain(area, client=None) -> str`.

- [ ] Step 1: tests:
  - rules (one per row of the table in `docs/research/science.md` plus the spec's C-only rules): `test_clearcut` (dHV −3.5, dHH −0.5 → `forest_loss`), `test_flooded_veg` (dHH +4, dHV +0.5 → `flooded_vegetation`), `test_open_water` (post HH·HV < 5e-5 linear, dHH −7 → `flood_open_water`), `test_burn_needs_fire_evidence` (dHV −3, dHH −1, firms 0, no perimeter → `forest_loss`; with firms 12 → `burn`), `test_c_only_low_veg` (agreement C, dVH −2.5, landcover grass → `low_veg_loss`; with perimeter → `burn`; cdl_crop → `harvest`), `test_freeze_suppressed` (both down, min_temp −4 → not emitted, returns `uncertain` with evidence note "possible freeze"), `test_c_only_other_is_uncertain`.
  - areas: `test_min_area` (2-block blob dropped, 3-block kept), `test_agreement_majority`.
  - explain: `test_template_contains_numbers` (text includes the dHV value and "only NISAR"), `test_llm_error_falls_back` (client raising → template text), `test_llm_cannot_change_class` (area.cls unchanged after explain).
- [ ] Step 2: fail. Step 3: implement. Confidence label: High if ≥ 80% of the area's blocks are significant and |median Δ| ≥ 3 dB; Medium ≥ 50%; else Low. LLM prompt: system "Rewrite this radar change finding in 2–3 plain sentences for a non-expert. Use only the numbers given. Do not change the classification." + the evidence JSON; `max_tokens=200`.
- [ ] Step 4: pass. Step 5: commit `feat(core): cause rules, change areas, overlays, explanations`.

### Task A6: References and `run_box` pipeline

**Files:** Create `core/sarstellar/refs.py`, `core/sarstellar/pipeline.py`, `core/sarstellar/notebook.py`, `tests/test_pipeline.py`

**Interfaces:**
- Consumes: A2–A5.
- Produces: `refs.svi_tracts(bbox) -> list[dict]` (CDC SVI 2022 FeatureServer from `docs/research/stack.md`), `refs.nifc_perimeters(bbox, year=2026)`, `refs.firms_count(geometry, start, end)`, `refs.nlcd(grid) -> ndarray[str]`, `refs.weather(lon, lat, when) -> {"min_temp_c", "rain_mm"}` (Open-Meteo archive; None values on any error); `run_box(bbox, dates=None, *, read_passes=None, progress=None, explain_client=None) -> Result` where `read_passes(granules, bbox, grid) -> list[(meta, arrays)]` defaults to sequential local reads; `notebook.build(bbox, granule_urls, dates) -> bytes` (.ipynb that pip-installs `sarstellar` from the repo and calls `run_box`).

- [ ] Step 1: tests with a fake `read_passes` returning synthetic arrays and monkeypatched refs: `test_no_stack_raises` (search returns only BETA/mixed → `NoUsablePasses` with the Review Focus 1 message), `test_mostly_invalid_box` (90% mask=255 → `done`-style Result with 0 areas and Review Focus 3 message), `test_no_s1_pair` (no RTC within 6 days → `result.s1 is None`, message "No Sentinel-1 pass within 6 days; showing NISAR only.", all agreements `L`), `test_end_to_end_synthetic` (a 3 dB HV drop patch of 20 blocks → one `forest_loss` area, agreement `L`, area_ha ≈ 20), `test_notebook_valid` (nbformat validates). Live `test_live_kaiser_direction`: Kaiser bbox and dates from `docs/research/kaiser-spike.md` → summed area with agreement `C` exceeds area with agreement `L` (the spike's direction).
- [ ] Step 2: fail. Step 3: implement `run_box`: search → stacks → pair → grid → read → blocks (HH, HV; S1 VV, VH onto the same grid) → stable mask → relative Δ → ENL per band → omnibus → changed per sensor → areas → AreaStats with refs → classify → render overlays → explain → Result. Report progress fractions 0.1 search, 0.2–0.7 reads, 0.8 test, 0.9 explain, 1.0.
- [ ] Step 4: pass (`pytest -q` and `pytest -m live tests/test_pipeline.py`).
- [ ] Step 5: commit `feat(core): run_box pipeline, references, notebook export`.

### Task A7: Modal app and job API

**Files:** Create `modal_app/app.py`, `modal_app/jobs.py`, `modal_app/api.py`, `tests/test_api.py`

**Interfaces:**
- Consumes: `run_box`, `Result`, `Job`.
- Produces: Modal app `sarstellar` (image: debian_slim python 3.12 + `pip install .` from repo + system GDAL via rasterio wheels; secrets `earthdata`, `anthropic`, optional `meteomatics`; Volume `sarstellar-data`; Dict `sarstellar-jobs`), `read_pass(url, bbox, grid_dict) -> (meta, arrays)` remote function (`retries=2`, `timeout=300`), `run_job(job_id, bbox, dates)` (`timeout=600`), FastAPI routes `POST /jobs`, `GET /jobs/{id}`, `GET /exports/{job_id}/{name}`, `GET /health`; env `SARSTELLAR_KILL`.

- Exports: on `done`, `run_job` writes `exports/{job_id}/change.tif` (bands: agreement code 0 none/1 L/2 C/3 both, rel dHH, rel dHV, rel dVV, rel dVH, min p; on the block grid with CRS), `areas.csv` (one row per ChangeArea, no geometry), and `notebook.ipynb` (A6) to the Volume, and sets `result.exports` to `/exports/{job_id}/{name}` URLs.
- Secret setup: `scripts/make_earthdata_secret.py` reads `~/_netrc` and calls `modal secret create earthdata ...` via subprocess without printing values.
- [ ] Step 1: tests with FastAPI `TestClient` and an injected fake runner: `test_exports_written` (fake result → three files exist and URLs set), `test_post_returns_job_id`, `test_invalid_bbox_422` (w ≥ e; NaN; outside US), `test_oversize_422` (25 km side → detail mentions "20 km"), `test_rate_limit_429` (11th POST in an hour from one IP), `test_daily_cap_429`, `test_cache_hit_reuses_job` (same bbox/dates → same job_id while done), `test_kill_switch_503`, `test_job_error_message` (runner raises `IOError` → status `error`, message Review Focus 4), `test_job_timeout` (runner exceeds 600 s → `error`).
- [ ] Step 2: fail. Step 3: implement; `api.py` holds pure FastAPI logic with a `Runner` protocol so tests don't need Modal; `app.py` wires `run_job.spawn`. CORS allow-all origins for GET/POST.
- [ ] Step 4: `pytest tests/test_api.py -q` passes; `modal deploy modal_app/app.py`; `curl $API/health` → `{"ok":true}`; POST the Kaiser bbox and poll to `done`.
- [ ] Step 5: commit `feat(modal): job API with guards`; post the deployed URL in the Multica issue for B4.

### Task A8: Story builds

**Files:** Create `modal_app/stories.py`; generated `web/public/stories/{clearcuts,edouard,kaiser}.json` + PNGs

**Interfaces:**
- Consumes: `run_box`. Story inputs (bbox, dates) from `docs/research/clearcut-edouard-spike.md` and `kaiser-spike.md`.
- Produces: three `Result` JSON files with relative overlay URLs, plus `web/public/stories/index.json` (`[{id, title, place, dates, summary}]`).

- [ ] Step 1: test `tests/test_stories.py::test_story_files_valid` (each JSON parses with `Result.from_json`, `fixture` is false, overlays exist on disk).
- [ ] Step 2: run `modal run modal_app/stories.py` → writes to Volume and downloads into `web/public/stories/`.
- [ ] Step 3: compare headline numbers with the spikes; if a story's direction flips, update its `summary` to the pipeline's numbers (spec §10b) and tell the team.
- [ ] Step 4: test passes. Step 5: commit `data: precomputed stories`.

## Track C: scorecard and learned model

### Task C1: Site sampling

**Files:** Create `modal_app/sites.py`, `tests/test_sites.py`; generated `modal_app/data/sites.json`

**Interfaces:**
- Produces: `sites.json` = `[{id, kind: "forest_loss"|"fire"|"flood"|"crops"|"stable", bbox, state, nisar_pair:[ur_pre, ur_post], s1:{track, dates}|null, ref_window:[start,end]}]` with targets forest_loss 120, fire 60, flood 40, crops 40, stable 60 (≥ 300 total; ≥ 6 states per kind where possible). Sources: OPERA DIST-ALERT-HLS disturbance clusters (2026), NIFC WFIGS 2026 perimeters ≥ 1,000 acres, 2026 flood events (Edouard, Indiana, Isaias corridors + DSWx water gain), CDL cropland (Central Valley, Columbia Basin, Midwest), stable controls (NLCD urban core / interior forest with no DIST alerts). Boxes 10×10 km; each must have a usable stack pair spanning the ref window.

- [ ] Step 1: test `test_sites_schema_and_counts` (schema, ≥ 300 total, no two boxes overlap > 25%, every kind ≥ 30). Step 2: run `modal run modal_app/sites.py`. Step 3: test passes. Step 4: commit.

### Task C2: Scorecard batch

**Files:** Create `modal_app/scorecard.py`, `core/sarstellar/scoring.py`, `tests/test_scoring.py`; generated `web/public/scorecard.json`, Volume `blocks.parquet`

**Interfaces:**
- Consumes: `sites.json`, core A2–A6.
- Produces: `scoring.block_labels(site, grid) -> ndarray[str]` (`forest_loss` if ≥ 50% of the block's DIST-HLS pixels lost ≥ 50% vegetation in the window; `burn` inside NIFC perimeter; `flood_open_water` DSWx water gain; `crop_cycle` CDL crop; `stable` otherwise in stable sites), `scoring.metrics(df, band, min_db) -> {precision, recall, f1, n_flags, n_ref}`, `scoring.pr_curve(df, band) -> list[(recall, precision, min_db)]`, `scoring.at_equal_recall(curve_a, curve_b, recall) -> (pa, pb)`, `scoring.bootstrap_ci(df, fn, n=500, by="site")`. Bands scored: `L` (HV or HH per class), `C` (VH or VV), `L30` (NISAR from every 3rd pixel per axis before block averaging). Holdout: states listed in `scorecard.json["holdout_states"]`, chosen so every kind has holdout sites.
- **Fusion (the headline):** `scoring.fisher_p(p_L, p_C) -> ndarray` (Fisher's method, χ² with 4 df; falls back to the available band's p where one is NaN), `scoring.fit_logistic_fusion(train_df) -> FusionModel` (features: rel Δ for HH, HV, VV, VH and −log10 p for each sensor; fit on training states only), `scoring.paired_bootstrap_delta(df, det_a, det_b, metric, n=1000, by="site") -> {delta, ci_low, ci_high, p_gt0}`. Detectors compared on holdout states per class: `L`, `C`, `L30`, `fused_fisher`, `fused_logistic`. Metrics: precision, recall, F1 at the default operating point, and AUPRC from threshold sweeps.
- `scorecard.json` = `{generated_at, n_sites, operating_point:{q:0.05, min_db:2.0}, stable_fa:{L, C, L30, fused_fisher, fused_logistic}, classes:[{class, landcover, detector, precision, recall, f1, auprc, ci_low, ci_high, n_ref, n_flags}], equal_recall:[{class, recall, precision_L, precision_C, precision_L30, ratio_L_over_C}], fusion:[{class, best_single, fused, metric:"auprc", delta, ci_low, ci_high, p_gt0}], model:null, holdout_states:[...], sites:[{id, kind, bbox, state, split}]}`.

- [ ] Step 1: tests on a synthetic DataFrame: `test_metrics_known_counts`, `test_equal_recall_interpolates`, `test_bootstrap_ci_brackets_point`, `test_holdout_by_state` (no state in both splits), `test_fisher_combines` (p_L=p_C=0.05 → fused p < 0.05; NaN C → equals p_L), `test_logistic_fit_uses_train_only` (fitting raises if any holdout-state row is passed), `test_paired_bootstrap_detects_gain` (synthetic detector B strictly better on every site → ci_low > 0), `test_paired_bootstrap_null` (identical detectors → CI contains 0).
- [ ] Step 2: fail; Step 3: implement; Step 4: pass.
- [ ] Step 5: `modal run modal_app/scorecard.py` (fan-out `.map` over sites, concurrency ≤ 64 to spare ASF, `return_exceptions=True`; failed sites listed in output). Expected: ≥ 270 sites succeed.
- [ ] Step 6: commit code and `web/public/scorecard.json`.

### Task C3 (stretch S0, start only after the Sun 11:00 freeze is safe): Learned cause model

**Files:** Create `modal_app/train.py`, `core/sarstellar/model.py`, `tests/test_model.py`; artifact `modal_app/artifacts/cause_lgbm.txt`

**Interfaces:**
- Consumes: `blocks.parquet`, `scorecard.json`.
- Produces: `model.features(df) -> DataFrame` (dHH, dHV, dVV, dVH relative; pre_HH, pre_HV; HH−HV ratio; p-values; change_idx; landcover one-hot; hand_m; slope_deg), `model.CauseModel.load(path, winners: list[str])`, `.predict(df) -> ndarray[str]`; `classify` in `rules.py` accepts an optional `CauseModel` and uses it only for classes in `winners`. Writes `scorecard.json["model"] = {per_class:[{class, rules_f1, model_f1, winner}], macro_f1_rules, macro_f1_model}`.

- [ ] Step 1: tests: `test_features_columns`, `test_winner_gate` (class not in winners → rules label kept).
- [ ] Step 2–4: implement LightGBM multiclass (train states vs holdout states from C2); pass.
- [ ] Step 5: `modal run modal_app/train.py` → per-class held-out F1 for rules and model printed and written to `scorecard.json`.
- [ ] Step 6: commit code, artifact, updated `scorecard.json`; redeploy A7 so the API uses the gate.

## Track B: web app (teammate B)

Mockup to match: `docs/mockups/app-mockup.html` (layout, colors, panels). Real-data page style: `docs/mockups/real-results.html`.

### Task B1: Scaffold, types, fixtures, API client

**Files:** Create `web/` (Vite React TS, pinned versions from Tech Stack), `web/src/types.ts`, `web/src/api.ts`, `web/public/fixtures/{clearcuts,edouard,kaiser}.json` + PNGs (built from `docs/mockups/*.png` and spike stats, `"fixture": true`), `web/src/api.test.ts`

**Interfaces:**
- Produces: TS types matching the Contract; `createJob(bbox, dates?) -> Promise<{job_id}>`, `pollJob(id, onProgress, intervalMs=1000) -> Promise<Result>` (rejects with the job's `message` on `error`), `loadStory(id) -> Promise<Result>` (from `/stories/{id}.json`, falling back to `/fixtures/{id}.json`), `loadScorecard() -> Promise<Scorecard|null>`; `VITE_API_URL` unset → mock mode resolving a fixture after a simulated 3 s.
- [ ] Step 1: vitest: `pollJob resolves on done`, `pollJob rejects with server message on error`, `loadStory falls back to fixture`. Step 2: fail. Step 3: implement. Step 4: `npm test` passes; `npm run build` succeeds. Step 5: commit.

### Task B2: Map shell, stories, legend

**Files:** `web/src/App.tsx`, `web/src/components/{MapView,Sidebar,Legend}.tsx`, tests alongside

- Layout and copy as in the mockup (header tagline "What only NISAR can see, and why" → change to "Two radars, one map"). Muted Esri imagery basemap; overlays as MapLibre `image` sources at `overlays.bounds`; areas as GeoJSON fill colored by agreement; legend toggles filter by agreement and show hectare sums; stories list from `/stories/index.json`.
- [ ] Tests: `legend toggle hides agreement`, `hectare sums match areas`. Build passes. Commit.

### Task B3: Change panel and timeline

**Files:** `web/src/components/{ChangePanel,SeriesChart,Timeline}.tsx`, tests

- Panel per mockup: class + agreement chips, confidence bar + label, `plain_text`, evidence list (value, CI, unit, note), Recharts series (HH/HV amber, VV/VH cyan, NISAR gap shaded), people block (SVI), export buttons (disabled when URL null). Timeline of `nisar.dates` with the gap striped; selecting two dates sets `dates` for the next job.
- [ ] Tests: `renders evidence with CI`, `export buttons disabled when null`, `gap drawn between 2026-07-27 and 2026-08-10`. Commit.

### Task B4: Draw a box and live jobs

**Files:** `web/src/components/{DrawBox,JobProgress}.tsx`, tests

- terra-draw rectangle; live size readout; block submit with message "Boxes are limited to 20 km a side." when over; progress stages from `progress`; error and "no passes" messages shown verbatim from the server; result replaces the current map content.
- [ ] Tests: `oversize box blocked before submit`, `server error message shown`. Manual check against the deployed API from A7. Commit.

### Task B5: Swipe and L-vs-C views

**Files:** `web/src/components/{SwipeView,LvsCView}.tsx`

- Swipe: maplibre-gl-compare with `before_png` / `after_png`. L vs C: two synced maps with `l_png` and `c_png` and per-sensor hectare totals.
- [ ] Test: `mode switch renders the right view`. Commit.

### Task B6: Scorecard and About pages

**Files:** `web/src/pages/{Scorecard,About}.tsx`

- Scorecard: **headline = the fusion result** ("On N held-out sites in K states, combining NISAR and Sentinel-1 improved {class} detection by Δ AUPRC [CI]", or the honest null), then per-class detector bars (L, C, L30, fused) with CIs, equal-recall ratios, stable false-alarm rates, site map with train/holdout coloring, a "how to read this" note. Rules-vs-model table only if `model` is non-null. Hidden until `scorecard.json` exists. About: data used (NISAR GCOV via ASF/Earthdata, OPERA RTC-S1, DIST-ALERT-HLS, DSWx, NIFC, FIRMS, CDL, NLCD, SVI, Meteomatics), method summary, limits (incl. Kaiser), AI-use disclosure, references, license.
- [ ] Test: `scorecard renders from sample json`. Commit.

### Task B7: Deploy

- [ ] Vercel project from `web/`, `VITE_API_URL` set to the A7 URL; custom `.earth` domain if claimed; Lighthouse check that first story renders < 3 s. Record the URL in the Multica project.

## Track D: submission (both humans)

### Task D1: Pitch and submission

- [ ] Sun 09:00: write the 30 s video script (WA two stories → Edouard → scorecard headline → draw a box; names "NISAR GCOV") and ≤ 7 slides from final numbers only.
- [ ] Sun 11:00–13:00: record the screen capture, edit, add captions; AI-generated visuals (if any) watermarked.
- [ ] Sun 13:00–14:30: project page (title, summary, demo link, repo link, NASA data, partner data, AI use, references), README with run instructions, LICENSE (Apache-2.0).
- [ ] Sun 15:00: submit; verify every link in a private window.

## Stretch (only after Sun 11:00 freeze is safe)

- S1 regional atlas: `modal_app/atlas.py` runs `run_box` over a WA+OR tile grid into `web/public/atlas/`.
- S2 foundation model: MAE pretraining on GCOV patches read by `read_pass`; similarity search endpoint.
