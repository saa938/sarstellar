# SARstellar

**Earth is dancing. NISAR can see the steps.**

Every kind of change on Earth's surface moves in its own way through the radar of NISAR, the
NASA-ISRO L-band satellite that images nearly all of Earth's land every 12 days, through clouds and
darkness. SARstellar plots every hectare of a place as a dot on an HH-versus-HV "dance floor" and
plays NISAR's passes like beats: a forest that is cut **falls**, rice standing in water
**bounces**, a wheat field **waltzes**, a flood makes the land **vanish**, an ice sheet **melts**.
A model trained on independent US reference sites names the move for every hectare, anywhere
NISAR flies.

[Open the site](https://www.sarstellar.earth/) · [30-second demo](https://www.sarstellar.earth/demo/)
· NASA Space Apps Challenge 2026, "Dancing with the SARs"

## The moves

| Move | On the ground | In the radar | Carried by |
|---|---|---|---|
| The Fall | Forest cleared or logged | Canopy volume scattering disappears: HV drops several dB | HV |
| The Scorch | Wildfire | Like the Fall, over wide connected patches; grass fires barely register at L-band | HV, HH |
| The Bounce | Water under plants (flooded forest, rice) | Water-to-trunk double bounce: HH jumps, HV barely moves | HH |
| The Vanish | Open-water flood | Calm water mirrors the pulse away: both go dark | HH, HV |
| The Waltz | A crop grows and is harvested | Canopy volume grows, HV climbs, then falls at harvest | HV |
| The Shimmer | Rain wets the soil | The whole scene brightens a little in both channels | HH, HV |
| The Melt | Snow and ice melt | Liquid water absorbs the pulse: HH darkens, recovers at refreeze | HH |
| The Stillness | Nothing changes | Speckle jitter around a fixed point | none |

## What we measured

RESULTS_PLACEHOLDER

## How it works

1. **Find the passes.** `core/sarstellar/search.py` and `dance.py` query NASA's CMR for calibrated
   NISAR L2 GCOV granules (never the uncalibrated BETA releases), keep the latest delivery of
   each pass, and build same-mode series (one track, direction, bandwidth, polarization mode and
   processing release). Partial frames and the 77 MHz HH-only ice mode are accepted.
2. **Read only what is needed, in parallel.** Each granule is 2 to 9 GB. `read_stage_granule`
   reads just the stage's window through HTTPS range requests, one Modal container per granule,
   and averages it to 1-hectare blocks (the dance) and 20 m imagery (the map).
3. **Describe each hectare's dance** from radar alone (`moves.py`): the strongest before/after
   step, excursions and recovery, scene-wide offsets (the Shimmer), and the neighbourhood.
4. **Learn the moves** (`moves_model.py`) on reference sites with independent labels (OPERA
   DIST-ALERT-HLS forest loss, NIFC fire perimeters, OPERA DSWx water, USDA cropland), training on
   one set of states and measuring on 12 states it never saw. The same model is retrained with HH
   only and HV only to measure which polarization carries which move.
5. **Publish** each stage as a static bundle (`docs/v2/CONTRACT.md`) that the web app plays.

## Reproduce

Requires Python 3.11+, Node 22+, a Modal account with an `earthdata` secret
(`EARTHDATA_USERNAME`, `EARTHDATA_PASSWORD`), and the reference catalog `modal_app/data/sites.json`.

```bash
pip install -e ".[modal,ml]"
modal run modal_app/dance.py::main            # read every pass over the 15 stages
modal run modal_app/dance.py::refs            # full series for the reference sites + training table
modal run modal_app/dance.py::moves           # train, evaluate, apply the moves to every stage
modal run modal_app/dance.py::moves --refs-only   # optical references on stage grids
modal run modal_app/dance.py::stars           # the constellation (UMAP of every dance)
science/pull.sh                               # download outputs to ../raw
python science/export_stage.py --raw ../raw --web web/public
python science/make_site_data.py --raw ../raw --web web/public --scorecard web/public/scorecard.json
cd web && npm ci && npm run build
modal deploy modal_app/dance.py               # the live "dance any place" API
```

## Data

NASA: NISAR L2 GCOV (NASA-ISRO, via the Alaska Satellite Facility DAAC and NASA Earthdata CMR),
OPERA DIST-ALERT-HLS, OPERA DSWx-HLS and DSWx-S1, OPERA RTC-S1 (Sentinel-1 comparison), NASA GIBS
imagery. Others: NIFC WFIGS fire perimeters, USDA NASS Cropland Data Layer, USGS NLCD, OpenStreetMap
and CARTO basemaps. Every data provider keeps its own terms.

## AI use

We used AI coding assistants (Claude Code and OpenAI Codex) to write and test code, to draft text,
and in brainstorming the concept. No AI-generated images, audio or video are used; maps, charts and
the soundtrack are rendered from NISAR data.

## License

Apache-2.0. Built on the SARstellar radar engine (v1, NISAR vs Sentinel-1 change comparison).
