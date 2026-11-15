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

## Data loading (never edits science-owned files)

- `/stages/index.json` first; if it is missing (404 or an HTML fallback page) the app uses `/stages-fixture/`.
  A stage id not in the real index still resolves from the fixtures (so old links keep working).
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

## Contract interpretations (please confirm)

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

- `#/present` preloads every stage and image, then a single master clock drives all scenes (deterministic).
  Scenes: globe (3 s), Punjab waltz/bounce (6), Rondonia fall (4), Sylhet/Indiana vanish (4), Greenland melt (3),
  proof numbers (5, only if `proof.json` exists), outro (3); missing scenes are dropped and the rest stretched to 28 s.
- Real stages only, unless the index itself is a fixture or `?fixtures=1`.
- Recording hooks: `window.__present = { ready, started, duration, start() }`; `?wait=1` holds until `start()`.
  `node scripts/record_present.mjs [--video] [--fixtures]` saves key frames (and a WebM) to `web/screenshots/`.

## Live mode

- Hidden unless `VITE_API_URL` is set. Draw a 1 to 25 km box (size shown live), POST `{bbox}` to `/dance`, poll
  `/dance/{id}` every 1.5 s, show progress as beats, then open `#/stage/live:{id}`.
- `node scripts/mock_api.mjs` + `VITE_API_URL=http://localhost:5299 npx vite` tests the whole flow locally.

## Verification

- `node scripts/shoot.mjs [--base URL] [ids...]` screenshots every screen at 1440x900 and 390x844 (Metal ANGLE so
  WebGL renders headless) and prints console errors. Output in `web/screenshots/` (git-ignored).

## Known issues / next

- Fixture Punjab is used by present mode and the landing floor only until the real Punjab bundle lands.
- The map's story card covers part of the radar image at 1440 px; it can be minimized.
- Explore's live drawing switches the globe to mercator and satellite imagery; there is no place search yet.
- The repository link is not in the footer (the repo is private); add it when it is public.
