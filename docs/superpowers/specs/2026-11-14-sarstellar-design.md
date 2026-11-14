# SARstellar: two radars, one map (design)

Date: 2026-11-14. Event: NASA Space Apps Challenge 2026, challenge "Dancing with the SARs".
Status: approved direction; this document is what the build plan is written from.
Research behind every number here: `docs/research/` (science, data access, stack, competitors, real-data spikes).

## 1. Intent

NISAR's L-band radar data has been public since July 2026, but almost nobody outside radar specialists can use it:
multi-GB HDF5 files, mode switches between passes, moving stripe gaps, duplicates, no HyP3 support, not in Google
Earth Engine. 60+ teams entered this challenge; most show 1–7 hand-picked sites, and the closest competitor
(NISAR Hazard Watch) answers "did this box change?" in 1–2.5 minutes and explicitly refuses to say why.

Nobody has measured **what NISAR (L-band, 24 cm) sees that Sentinel-1 (C-band, 5.6 cm) doesn't**. That is NASA's own
open question about the mission and the challenge asks it directly ("Which polarizations highlight these changes?
What future applications of NISAR are possible?").

SARstellar answers it three ways:
1. **An interactive map**: draw a box anywhere NISAR has imaged in the US and see what changed, which radar saw it
   (only NISAR / both / only Sentinel-1), why (radar physics), how sure, and who lives there.
2. **A national two-radar scorecard**: the same method run on 300+ US sites that have independent answers
   (optical disturbance alerts, fire perimeters, flood maps, crop maps), reported as "where NISAR beats Sentinel-1,
   by change type and land cover".
3. **The headline scientific test: does combining both radars beat either alone?** Fused detectors (a statistical
   combination of the two radars' tests, and a simple logistic fusion fit only on training states) are compared with
   NISAR-only and Sentinel-1-only on **held-out states**, with paired bootstrap confidence intervals on the
   improvement. Whatever the answer, it is reported as measured.

**Priority (user decision):** the radar comparison and a rigorous scorecard come before AI features. The learned
cause model is a stretch goal; the LLM only rewords text.

**Moat:** compute turned into scale and proof. Other teams processed a handful of sites by hand; we process hundreds
on Modal, and every claim in the pitch carries a measured number.

Real-data evidence gathered today (see `docs/research/kaiser-spike.md`, `clearcut-edouard-spike.md`):

| Test | Result |
|---|---|
| Clearcuts, Morton/Mineral WA (vs OPERA DIST-ALERT-HLS, 106 reference cuts) | NISAR precision 35.7% vs Sentinel-1 4.6% at similar recall (~51–53%); at equal flag count 56 vs 23 hits |
| Edouard flooded forest, Village Creek TX (USGS gauge 14.8 ft at NISAR pass) | NISAR HH +3..+6 dB ribbon along the creek; Sentinel-1 had no pass during the flood. Moderate evidence |
| Kaiser Canyon fire, Colville Reservation WA (NIFC perimeter) | Sentinel-1 wins: 40.6% vs 4.7% of burned blocks dropped ≥2 dB (grass/shrub fire) |

## 2. Who it serves

- **Primary: people who work with SAR / surface change** (researchers, resource and forest managers, flood and fire
  analysts). They need trustworthy change maps they can check, export and reproduce.
- **Secondary: judges, educators, the public**, reached through three precomputed stories and plain-English text.

## 3. Goals, non-goals, anti-goals

### Goals (MVP: must ship)
- **G1 Explore:** draw a box (US, ≤ ~20×20 km) → three-color L/C change map, a list of change areas each with class,
  confidence, plain-English explanation, evidence numbers, time series, SVI "who lives here", and exports
  (GeoTIFF, CSV, Jupyter notebook). Warm latency target ≤ 20 s.
- **G2 Stories:** three precomputed showcase sites that load instantly with no backend call: WA clearcuts (NISAR wins),
  Edouard TX flooded forest (only NISAR was there), Kaiser Canyon WA fire (Sentinel-1 wins).
- **G3 Scorecard:** ≥ 300 US sites, both radars, independent references; metrics per change class × land cover × band
  with bootstrap confidence intervals and a geographic hold-out; published as a page in the app and as JSON.
- **G4 Fusion test:** on held-out states, compare NISAR-only, Sentinel-1-only, NISAR-at-30 m, Fisher-combined
  (statistical fusion of both radars' p-values) and logistic fusion (fit on training states only) by precision,
  recall, F1 and area under the precision–recall curve, per change class, with paired bootstrap (by site) CIs on
  each difference. This is the pitch's headline result.
- **G5 Submission package:** live demo URL, public Apache-2.0 repo, ≤ 30 s video and/or ≤ 7 slides, project page with
  NASA data used, AI-use disclosure, full references.

### Accuracy and speed targets (proposed; the scorecard reports actuals whatever they are)
| Measure | Target |
|---|---|
| False alarms on known-stable ground | ≤ 1.5% at the 1% significance setting |
| Clearcut / forest loss vs DIST-ALERT-HLS, held-out sites | precision ≥ 40%, recall ≥ 50%; NISAR precision ≥ 3× Sentinel-1 |
| Open-water flood vs OPERA DSWx (near-same-day pairs) | F1 ≥ 0.7 |
| Fire, ≥ 5 NIFC perimeters | honest NISAR vs Sentinel-1 table, no target |
| Cause label matches reference class (held-out) | ≥ 70% |
| New box, warm | ≤ 20 s; stories < 1 s |

### Stretch (only after G1–G5 are safe, in this order)
- **S0 Learned cause model:** gradient-boosted trees on scorecard blocks, benchmarked against the rules on held-out
  states; used per class only where it wins.
- **S1 Regional atlas:** precompute changes for all of Washington + Oregon since 2025-11 so the map opens full.
- **S2 NISAR foundation model:** self-supervised pretraining on NISAR GCOV patches from the same read pipeline,
  plus "find more places like this" similarity search.

### Non-goals
- Interferometric displacement (GUNW/InSAR), RSLC/ISCE3 processing, polarimetric decompositions.
- Non-US references for the scorecard (the map may work elsewhere, but claims are US-only).
- Real-time alert feeds, accounts/login, mobile layout beyond "doesn't break".
- NISAR BETA-tier data (uncalibrated). This rules out the Dec 2025 WA floods.

### Anti-goals (would make it a failure even if it runs)
- Claiming NISAR always beats Sentinel-1. The Kaiser result must stay visible.
- Any number in the app or pitch that wasn't measured by our pipeline, or illustrative data shown as real.
- The LLM deciding or changing a classification. It only rewords the rule/model output.
- Quoting single-pixel numbers (speckle is ~±3 dB); all quoted numbers come from ≥ 1 ha aggregates.
- A demo that depends on the live backend being up; stories and scorecard are static.

## 4. Constraints

- **Time:** submission deadline Sunday 2026-11-15 17:00 PT (hard). Internal target: everything submitted by
  15:00 PT, leaving 2 h of buffer. Core work must happen during the event.
- **Team:** two people. Teammate A (Washington; backend + Modal + science) and Teammate B (New Jersey; web app),
  each running Claude Code and Codex agents through a shared Multica workspace. One writer per worktree; tasks
  split by directory (`core/`, `modal_app/`, `web/`); only the integration owner (Teammate A) edits shared manifests.
- **Rules:** must meaningfully use a dataset from the challenge Resources list. NISAR GCOV via ASF Vertex /
  Earthdata Search satisfies this. Cite every source. Disclose all AI use; AI-generated images need a visible watermark;
  no NASA logos in AI content. English. Public links. Apache-2.0.
- **Data access (verified):** Earthdata Login required (local `~/_netrc`; on Modal as a secret). HTTPS range reads with
  fsspec `blockcache` 8 MiB + h5py `page_buf_size` 16 MiB, `rdcc_nbytes` 4 MiB. Measured from a home desktop: open
  1–4 s, 2000×2000 window 3.8–4.6 s. ASF returned a transient 502 that crashed h5py: retries with backoff are required.
  Direct S3 works only from AWS us-west-2; Modal's region pin to us-west-2 is unconfirmed, so HTTPS is the baseline.
- **Modal limits:** web functions time out at 150 s and the 303 fallback breaks CORS → spawn a job and poll.
  `modal.Dict` entries expire after 7 idle days → anything that must survive goes to a Volume or the static site.
  Function I/O > 2 MiB routes via us-east → return small payloads.

## 5. Data rules (the "traps", all handled inside the engine)

NISAR GCOV (`/science/LSAR/GCOV/grids/frequencyA/`):
- Collections: `NISAR_L2_GCOV_PROVISIONAL_V1` (from 2025-10-29 for selected regions incl. many US sites; global from
  2026-06-17) and `NISAR_L2_GCOV_V1` (VALIDATED, from 2026-10-21). Search by collection short name; plain
  `asf_search` dataset filters silently include BETA. Permanent gap 2026-07-27 22:03 → 08-10 00:55 UTC.
- A time series uses **one track + direction + mode + processing version (CRID)**. Group by track and direction,
  query by bbox (frame numbers shift between passes). Filter on `FREQUENCY_A_RANGE_BANDWIDTH` (drop 5 MHz-only and
  mixed-mode granules). Dedupe `_001/_002` deliveries (keep highest). Flag series crossing CRID P05023 → P05036.
- Layers: `HHHH`, `HVHV` (linear γ⁰, dB = 10·log10), `mask` (1–254 valid, 0 partial, 255 fill),
  `numberOfLooks`, `rtcGammaToSigmaFactor`, `projection` (EPSG as uint32; UTM zone varies by track, e.g. 32610 for
  a zone-11 site), `xCoordinates`/`yCoordinates`. 10 m posting at 40 MHz; chunks 512² gzip. Use frequency A only.
  Ignore the RFI likelihood fields (values out of range).
- Valid pixel = mask valid on both dates. Noise floor: mask HV within 3 dB of the NESZ when available.

Sentinel-1: OPERA `OPERA_L2_RTC-S1_V1` (VV, VH COGs, HTTPS + EDL; ASF data-use agreement required), reprojected onto
the NISAR 1-ha grid; pair dates within ±6 days of the NISAR dates when possible and always record the offset.
OPERA DIST-ALERT-S1 has no Jun–Nov 2026 data: not usable.

References (scorecard and validation): OPERA `DIST-ALERT-HLS` (vegetation loss, optical), OPERA DSWx-HLS / DSWx-S1
(water), NIFC WFIGS 2026 perimeters (fire; geometries may be invalid → `make_valid`), NASA FIRMS (fire evidence),
USDA Cropland Data Layer (crops; latest available year), NLCD (land-cover strata), HAND (floodplain), CDC SVI 2022
(people). USGS gauges for flood stories.

## 6. Method

1. **Blocks:** average linear power over 10×10 pixels (1 ha) after masking; convert to dB. All quoted numbers are
   block or area aggregates.
2. **Relative change:** subtract the median change of unchanged surroundings in the same land-cover stratum
   (spikes saw scene-wide shifts of +0.1 to +1.5 dB from moisture/calibration).
3. **Detection (per band, per 1-ha block)** *(builder's call after review)*: the sequential omnibus test (Conradsen
   et al. 2016) runs on **block** means, not pixels. Its ENL is **estimated empirically per band and per scene** from
   blocks in the stable stratum (ENL = mean² / variance of the block-mean ratio between dates), so it absorbs both
   residual speckle and natural block-to-block variability. It is **not** capped by the per-pixel `numberOfLooks`.
   The test gives a p-value and the date of change; Benjamini–Hochberg FDR q = 0.05 across the box.
   A block is **changed** only if it is significant **and** its relative change magnitude is at least a minimum effect
   size (default 2 dB for every band; the scorecard's calibration split tunes it per band and class). The two-date
   view uses the same test with k = 2.
4. **Agreement class:** a change area is *only NISAR*, *both*, or *only Sentinel-1* by which band's blocks are
   "changed" under rule 3. NISAR is 10 m (≈100 px/ha) and RTC-S1 is 30 m (≈11 px/ha); the empirical ENL accounts for
   this, and the scorecard also reports a same-resolution variant (NISAR degraded to 30 m) so that wavelength
   effects can be separated from resolution effects.
5. **Cause rules** (`docs/research/science.md` table): flood (open water), flooded vegetation, forest loss/clearcut,
   burn (needs FIRMS or perimeter to say "fire"), crop cycle (labelled farming, not disturbance), soil wetting,
   construction, landslide (low confidence), wet snow (low confidence; C-band better), freeze-up (suppressed false
   positive). Thresholds marked "judgment" in the research are tuned by the scorecard's calibration split.
   **C-band rules for C-only areas** *(builder's call)*: VH drop ≥ 2 dB in low vegetation (NLCD grass/shrub/crop) →
   "low-vegetation loss", refined to "burn" only with FIRMS/perimeter support and to "harvest" only with a CDL crop
   class; VV/VH rise over flat low-HAND ground → "possible surface water/wetting". Anything else C-only is labelled
   "changed, cause uncertain (only Sentinel-1 saw it)". The learned model uses all four bands' features.
6. **Explanation:** the rule/model output is a JSON of class, confidence, evidence values with CIs, and the rule that
   fired. Claude turns it into 2–3 plain sentences. A template fallback is used if the LLM call fails. The LLM
   cannot change class or numbers.
7. **Change areas:** connected significant blocks ≥ 3 ha become polygons; each gets aggregate stats and a time series.

## 7. Scorecard and learned model

- **Sites:** ≥ 300 boxes (~10×10 km) across CONUS, stratified by change class and land cover: reference-positive sites
  (DIST-ALERT-HLS disturbance clusters, 2026 NIFC perimeters, DSWx flood events, CDL cropland) plus stable controls.
  Each site has a NISAR same-track pair (or stack) and the nearest Sentinel-1 pair with the offset recorded.
- **Output per block:** relative dHH, dHV, dVV, dVH, pre-event levels, ratios, test p-values, change date, land cover,
  HAND, slope, reference label.
- **Metrics:** precision, recall, F1 and stable-ground false-alarm rate per class × land cover × band, with bootstrap
  CIs. Geographic hold-out (split by state/ecoregion, never random blocks).
- **Operating points** *(builder's call)*: every radar comparison is reported (a) at the app's default operating point
  (rule 3 in §6) and (b) as precision–recall curves; the headline comparison and the "NISAR precision ≥ 3×
  Sentinel-1" target are read **at equal recall**, which is the fair comparison. Equal-flag-count numbers (as used in
  the spikes) are reported as a secondary view.
- **Learned model:** gradient-boosted trees as the first model; a small GPU model (MLP or temporal transformer) only if
  trees plateau. Same features, same split. Compare to the rule engine per class; ship the winner per class.
- **Publication:** `scorecard.json` + a Scorecard page; labels described honestly as reference products, not ground truth.

## 8. Architecture

```
web/ (Vite + React + TS, MapLibre)  ── static on Vercel ──┐
   stories/*.json, scorecard.json baked in                 │ POST /jobs {bbox, dates?}
                                                           ▼
modal_app/api.py  (one FastAPI asgi_app, warm during judging)
   └─ run_job.spawn() → job_id ; GET /jobs/{id} polled every 1 s
        run_job: search (CMR) → build stacks → read_window.map(passes) with retries
                 → core.blocks → core.detect → core.rules/model → core.render (PNGs + bounds)
                 → explain (Claude, template fallback) → exports to Volume
        state + small results in modal.Dict; exports/stories/scorecard on a Volume
modal_app/scorecard.py   batch over sites.json → blocks parquet → metrics → scorecard.json
modal_app/train.py       learned cause model on scorecard blocks (CPU trees; GPU optional)
core/ (pure Python package, imported by Modal, the scorecard, and exported notebooks)
```

- **API contract** (the seam between the two teammates; fixtures in `web/public/fixtures/` let the web app be built
  before the backend exists):
  - `POST /jobs {bbox:[w,s,e,n], dates?:[a,b]}` → `{job_id}`
  - `GET /jobs/{id}` → `{status: queued|running|done|error, progress: 0..1, message, result?}`
  - `result`: `{bbox, nisar:{track, direction, dates[]}, s1:{track, dates[]}, overlays:{change_png, l_png, c_png,
    before_png, after_png, bounds:[[lon,lat]×4]}, areas:[{id, geometry, agreement: L|C|both, class, area_ha,
    confidence, p_value, change_date, evidence:[{label, value, ci, unit, note}], plain_text, series:{dates, HH, HV,
    VV, VH}}], people:{svi_tracts[]}, exports:{geotiff, csv, notebook}}`
  - Stories use the identical `result` shape, stored as static JSON.
- **Overlays:** PNG images placed by corner coordinates (no tile server); reprojected from UTM to EPSG:3857; box
  capped so images stay ≤ ~2048 px a side. Zoom handled by rendering at block resolution.
- **Secrets:** Earthdata credentials and the Anthropic API key as Modal secrets; never in the repo. Note: the Modal
  workspace is shared (other people's secrets are visible there), so its owner can see ours.
- **Hosting:** web on Vercel (or GitHub Pages fallback), optionally on the free `.earth` domain from the Global Offers.
- **Uptime and guards** *(builder's call)*: judging runs into Dec 2026–Jan 2027, so the live endpoint stays up through
  January. Warm (`min_containers=1`) during the event and on demand for judging sessions, cold otherwise (adds
  ~5–15 s). The public, login-free `POST /jobs` gets: max box ~20×20 km, per-IP limit (10 jobs/hour), a global daily
  job cap (200), results cached by bbox + dates on the Volume, and a kill-switch env var that turns the endpoint into
  "stories only". Claude calls are cached per change area and fall back to templates on any error.
- **Weather context:** Open-Meteo historical archive API (free, no key) for rain and temperature at pass dates,
  feeding the soil-wetting and freeze-up rules. (Meteomatics sign-up failed, so it is not used.)
- **Domain:** `sarstellar.earth` (free Global Offer, registered via Porkbun) points at the web app.

## 9. The web app

Matches the approved mockup (`docs/mockups/app-mockup.html`, real-data pages in `docs/mockups/`):
- Header with name and tagline; left panel: "Draw a box", Stories list, box facts, three-color legend with hectares
  and toggles, "How sure are we?"; map center on a muted satellite basemap with change overlays and the fire/flood
  reference outline when present; view modes *Change map*, *Before | After* swipe, *L-band vs C-band* side by side;
  right panel opens on a change area (class chip, agreement chip, confidence bar, plain text, evidence list, time
  series chart, who's affected, exports); bottom timeline of passes with the data gap shaded.
- New: a **Scorecard** page (the national result) and an **About/Methods** page (data, method, limits, references,
  AI disclosure).
- Progress UI for live jobs ("finding passes → reading 11 passes → testing → explaining").
- Color meaning is fixed everywhere: amber = only NISAR, violet = both, cyan = only Sentinel-1.

## 10. Pitch

- Story order: open on Washington ("two radars over our home state": clearcuts NISAR wins, Kaiser Canyon Sentinel-1
  wins), Edouard (only NISAR was there), then the national scorecard number, then "draw a box anywhere".
- 30 s video (primary) and ≤ 7 slides (backup). The video shows the product working and names NISAR GCOV.
- Personal context: both teammates' home states; Kaiser Canyon's impact on the Colville Reservation (SVI).

## 10b. Which numbers are official *(builder's call)*

The spike numbers in §1 justified the direction; they are **not** the shipped numbers. The three stories are re-run
through the final `core` pipeline, and the app, scorecard and pitch use only those outputs. If the re-run changes a
story (e.g. a different clearcut ratio), the pipeline's number wins and the story text changes with it. Until then the
web app is built against fixtures in the final `result` shape, derived from the spike outputs and labelled as such.

## 11. Cut order if time runs short

S2 foundation model → S1 atlas → S0 learned cause model → LLM wording (templates stay) → notebook export → live
draw-a-box (stories + scorecard still ship). G2 stories, G3 scorecard, G4 fusion test and G5 submission are never cut.

## 12. Left to the builder

Library choices inside the stated stack, component structure, styling details, exact site-sampling procedure within
the stratification above, model hyperparameters, chart library, file layout inside each directory, test strategy.
