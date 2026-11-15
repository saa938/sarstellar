# SARstellar v2 web: build notes

Branch `v2-web`, Vite root `web/`. `npm run build` writes `web/dist/`. Node 22+.

## Screens

| Route | What |
|---|---|
| `#/` | Story scroll: night globe overture, the two partners (scattering diagrams), scroll-driven dance floor, the moves, world tour, how we know, your stage, the next season |
| `#/stage/<id>` | Stage view: MapLibre map with crossfading radar images, WebGL2 dance floor, timeline with story beats and choreography score, brush (box/lasso) and map box select, solo card. `?t=<pass>` start pass, `?play=0` no autoplay, `?block=<n>` open a hectare |
| `#/stage/live:<id>` | A bundle computed by the live API (same contract), base `${VITE_API_URL}/dance/<id>/files/` |
| `#/moves`, `#/moves/<id>` | Field guide |
| `#/proof` | Renders `proof.json` per `docs/v2/PROOF_FIELDS.md` (dot-and-interval charts, base rates, polarization report card, Sentinel-1, cross-continent, confusion, limits); in-progress state without it |
| `#/explore` | Interactive night globe of all stages; live mode when `VITE_API_URL` is set |
| `#/constellation` | Every hectare placed by the shape of its dance (UMAP); zoom, pan, hover, click opens the stage at that block |
| `#/present` | 28 s chrome-free sequence for the demo video at 1920x1080 |
| `#/about` | How it works, data credits, source repository |

## Data loading (never edits science-owned files)

- `/stages/index.json` first; if it is missing (404 or an HTML fallback page) the app uses `/stages-fixture/`.
  Once a real index exists, synthetic stages are never shown (an id not in the real index is "not found").
- `/moves.json` then `/moves-fixture.json`; `/proof.json` (no fixture: absent means "measured results arrive here").
- `/constellation.json` + its `.bin` then `/constellation-fixture.*`.
- Every screen showing fixture data shows the "Synthetic preview data" tag.
- Stages are ordered by an optional `order` field in index entries.

## Fixtures

- `npm run fixtures` (= `uv run --no-project --with numpy --with pillow python scripts/make_fixtures.py`) writes
  three synthetic stages (Rondonia fall + scorch, Punjab two waltzes with vanish/bounce, Village Creek bounce with
  `moves: null`), their WebP false-color images and `moves-fixture.json`. Deterministic seeds.
  Physically shaped: forest ~HH -7 / HV -13, crops ~-10 / -19, water ~-24 / -32, double bounce ~0 / -11, 0.6 dB speckle,
  per-pass calibration jitter, rain shimmer passes, swath-edge nodata.
- `uv run --no-project --with numpy python scripts/make_constellation_fixture.py` writes the constellation fixture from
  those stages (hand-made clusters, not UMAP).

## Contract interpretations (confirmed by the science track)

1. `moves.bin` head layout `N2`: read as interleaved per block, `byte[2n] = move`, `byte[2n+1] = confidence`
   (last letter varies fastest, like `TPN`). Per-beat section `TN`: `byte[2N + t*N + n]`.
2. `blocks.bin` `layout: "TPN"` exactly as specified; gaps are forward-filled for drawing, original validity kept for charts.
3. HH-only stages (`blocks.pols = ["HH"]`): the floor shows x = HH on the first pass, y = HH on this pass, so dots only move
   vertically and the diagonal means "no change". Axis range comes from the data (0.5 to 99.5 percentile).
4. `story.highlight.blocks` are grid indices `n = row * nx + col`; constellation `block` is the same index.
5. `constellation.json`: `{count, stages[], moves?[], file?, layout}`. The binary is read as planar
   (N x (x, y) float32, then N uint8 move, N uint8 stage, N uint32 block) unless `layout` contains "interleaved"
   (14 bytes per point). Little-endian, y up.
6. Extra fields (`images.stretch`, index `order`) are ignored or used as noted; nothing else is required.

## Things the contract does not carry that would help

- A per-stage `move` legend subset or counts (computed client-side from `moves.bin` today).
- Optical before/after for the solo card (not built).
- A `date` per story beat that is guaranteed to be one of `dates` (the app snaps to the nearest pass).

## Design decisions

- Rendering: raw WebGL2 rather than deck.gl. All passes live in one RG16F texture (texel `t * K + k`); the vertex shader
  interpolates between beats with a smootherstep so dots step on the beat. Dots and trails add up in a half-float buffer,
  then tone-map plus a light bloom, so dense clusters glow instead of clipping. 170k dots hold 60 fps on an M3.
- uint8 quantization (0.2 dB) showed as a lattice; each block gets one fixed sub-bin dither offset (constant in time).
- Selection is by identity: brush the floor at any pass, then play, and the same hectares stay lit. The map shows a
  spotlight (veil outside the selection) instead of painting over the radar.
- Basemap: CARTO raster tiles now return an "API key required" image, so the dark basemap is Esri Dark Gray Canvas
  (attributed); satellite is Esri World Imagery; the globe is NASA GIBS VIIRS Black Marble.
- Colors: one per move, validated with the dataviz CVD checker on the night surface for moves that share a stage
  (fall + scorch; vanish + bounce + waltz pass all-pairs). Fall gold sits slightly above the lightness band on purpose
  (emitters on a night sky). Every color also carries a text label. HH = peach, HV = teal everywhere.
- Copy: no em dashes, no hype words; HH/HV explained as two ways the radar listens. The solo card's text is either the
  move's physics (when moves exist) or a rule-based "textbook reading" labeled as such, never a model claim.
- No team names, faces or voices anywhere; no NASA insignia; footer credits data and basemaps and says NISAR is NASA-ISRO.

## Present mode (demo video)

- `#/present` preloads every stage and image, then a single master clock drives all scenes (deterministic). Real stages only.
  Scenes: globe (3 s, "Earth is dancing. NISAR can see the steps."), Punjab (6 s, the whole year, "Wheat waltzes in HV.
  Rice bounces in HH." + "Same fields, two crops, two polarizations"), Morton (4 s, the Fall), Edouard (4 s: holds the pass
  before, steps onto 2026-09-03, holds), Greenland (3 s), proof (5.5 s), end card (2.5 s). Missing scenes are dropped and
  the rest stretched to 28 s.
- Proof claims are computed from `proof.json` at runtime: HV-only vs HH-only AUPRC for the Fall (6x), `sentinel1.ratio`
  (7.8x), `headline.train_sites` and `test_states` (170 sites, 12 states).
- Trails per scene are the hectares that best show the move (largest HV range for the waltz, largest HH jump for the
  bounce, largest HV drop for the fall), colored by their move.
- Recording hooks: `window.__present = { ready, started, duration, start(), t }`; `?wait=1` holds until `start()`.
  `node scripts/record_present.mjs [--base URL] [--video]` saves key frames (and a WebM) to `web/screenshots/`.

## Proof page

- Per move: AUPRC with its interval against the base rate on a log axis (the gap is the skill), lift as "N x better than
  chance", "interval includes chance" when the lower bound touches the base rate (Scorch), "no better than chance" for the
  Vanish; gated map precision and recall with `model.note`; any-move precision vs base rate; macro F1; polarization report
  card; feature gain; Sentinel-1; Rondonia (never trained on) and Morton (in a training state); confusion; limits.

## Performance

- The landing ships in the main bundle (about 98 KB gzip with React); MapLibre (about 290 KB gzip) loads after first paint
  for the globe and only on map pages. Local FCP is about 85 ms.
- No stage data loads at first paint. The landing's floor story and finding fetch their stage about one screen before
  they scroll into view; stage pages fetch on open. Blocks decode in a worker.

## Live mode

- Hidden unless `VITE_API_URL` is set. Draw a 1 to 25 km box (size shown live), POST `{bbox}` to `/dance`, poll
  `/dance/{id}` every 1.5 s, show progress as beats, then open `#/stage/live:{id}`.
- `node scripts/mock_api.mjs` + `VITE_API_URL=http://localhost:5299 npx vite` tests the whole flow locally.

## Verification

- `node scripts/shoot.mjs [--base URL] [ids...]` screenshots every screen at 1440x900 and 390x844 (Metal ANGLE so
  WebGL renders headless) and prints console errors. Output in `web/screenshots/` (git-ignored).

## Known issues / next

- The map's story card covers part of the radar image at 1440 px; it can be minimized.
- Explore's live drawing switches the globe to mercator and satellite imagery; there is no place search yet.
- The repository link (https://github.com/saa938/sarstellar) is in the footer and About page; it 404s until the repo is public.
- The constellation uses its synthetic fixture until `constellation.json` / `.bin` land (no code change needed).
