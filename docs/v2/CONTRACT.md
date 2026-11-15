# SARstellar v2 data contract (science track -> web track)

Everything the site shows comes from static files under `web/public/stages/` (and two top-level
JSON files). The science track writes them; the web track only reads them. Files marked
`"fixture": true` are synthetic placeholders and must be labeled as such if ever shown.

Coordinates are lon/lat (EPSG:4326) unless stated. Dates are ISO `YYYY-MM-DD` (UTC acquisition day).

## 1. `stages/index.json`

```json
{
  "generated_at": "2026-11-15T18:00:00Z",
  "fixture": false,
  "stages": [
    {
      "id": "punjab",
      "name": "Punjab",
      "country": "India",
      "center": [75.80, 30.78],
      "move": "waltz",
      "title": "Two waltzes a year",
      "teaser": "Rice in the monsoon, wheat in the winter: the same fields dance twice.",
      "n_passes": 24,
      "first": "2025-11-21",
      "last": "2026-10-11",
      "thumb": "punjab/img/thumb.webp"
    }
  ]
}
```

## 2. `stages/<id>/stage.json`

```json
{
  "id": "punjab",
  "fixture": false,
  "name": "Punjab",
  "country": "India",
  "bbox": [75.6, 30.6, 76.0, 30.95],
  "corners": [[75.59, 30.96], [76.01, 30.96], [76.01, 30.59], [75.59, 30.59]],
  "grid": { "nx": 380, "ny": 390, "res_m": 100, "epsg": 32643 },
  "stack": {
    "track": 156, "direction": "A", "bandwidth_mhz": 40, "mode": "DH",
    "pols": ["HH", "HV"], "crid": "P05023", "n_granules": 24
  },
  "dates": ["2025-11-21", "2025-12-15", "..."],
  "blocks": {
    "file": "blocks.bin",
    "encoding": "uint8",
    "scale": 0.2,
    "offset": -40.0,
    "nodata": 255,
    "layout": "TPN",
    "pols": ["HH", "HV"]
  },
  "images": {
    "res_m": 20,
    "nx": 1900,
    "ny": 1950,
    "files": ["img/000.webp", "img/001.webp", "..."],
    "thumb": "img/thumb.webp"
  },
  "moves": null,
  "story": {
    "title": "Two waltzes a year",
    "lede": "One sentence a judge reads first.",
    "body": ["Paragraph.", "Paragraph."],
    "beats": [ { "date": "2026-06-20", "caption": "Paddies flood: the fields go dark." } ],
    "highlight": { "blocks": [12345, 12346], "label": "A rice paddy" }
  },
  "sources": [ { "name": "NISAR L2 GCOV (NASA/ISRO, ASF DAAC)", "url": "https://asf.alaska.edu/" } ],
  "stats": { "valid_blocks": 120000, "km2": 1450 }
}
```

- `corners`: top-left, top-right, bottom-right, bottom-left of the grid. The grid is north-up in
  UTM (`epsg`), so in lon/lat it is a slightly rotated quadrilateral. Images cover exactly these
  corners (use a MapLibre image source with these four coordinates). A block's center can be
  found by bilinear interpolation of the corners at ((col + 0.5) / nx, (row + 0.5) / ny).
- `blocks.bin`: one byte per value. `dB = offset + scale * byte`; `byte == nodata` means no data.
  Layout `TPN`: index = (t * P + p) * N + n, with N = nx * ny and n = row * nx + col, row 0 =
  north. `P = blocks.pols.length` (2 for HH, HV; 1 for HH-only ice stages).
- `images.files[t]`: radar false color for `dates[t]`: R = HH, G = HV, B = HH/HV (standard dual-pol
  composite: forests green, double bounce and cities magenta/pink, water black). Transparent where
  there is no data. HH-only stages get a grayscale image.
- `moves` (null until the science track ships it):

```json
"moves": {
  "file": "moves.bin",
  "ids": ["still", "fall", "scorch", "bounce", "vanish", "waltz", "shimmer", "melt"],
  "layout": "N2 then TN",
  "note": "First N*2 bytes: per block (move index, confidence 0-100). Then T*N bytes: move index per beat (255 = none)."
}
```

- `story.highlight.blocks`: a few hand-picked block indices worth drawing trails for.

## 3. `moves.json` (top level, `web/public/moves.json`)

```json
{
  "fixture": true,
  "floor": {
    "x": { "pol": "HH", "min": -30, "max": 5 },
    "y": { "pol": "HV", "min": -38, "max": -5 },
    "zones": [
      { "id": "water",  "label": "Open water",     "center": [-24, -32] },
      { "id": "soil",   "label": "Bare soil",      "center": [-13, -25] },
      { "id": "crops",  "label": "Grass and crops","center": [-10, -19] },
      { "id": "forest", "label": "Forest",         "center": [-7,  -13] },
      { "id": "bounce", "label": "Double bounce: flooded forest, cities", "center": [0, -11] }
    ]
  },
  "moves": [
    {
      "id": "fall",
      "name": "The Fall",
      "what": "A forest is cleared or logged.",
      "physics": "Leaves and branches scatter the radar in every direction, which is what HV hears. Remove the canopy and HV drops 3 to 6 dB; HH drops less.",
      "carried_by": ["HV"],
      "path": [ { "HH": -7.0, "HV": -12.5 }, { "HH": -9.0, "HV": -17.5 } ],
      "metrics": null,
      "stages": ["morton", "rondonia"],
      "future": "Deforestation alerts through the clouds of the tropical wet season."
    }
  ]
}
```

`path` is the canonical trajectory on the floor (median of reference sites once measured).

## 4. `proof.json` (top level)

Produced by the science track. Shape to be fixed when the evaluation runs; the web track builds the
proof page against the fields listed in `docs/v2/PROOF_FIELDS.md` when it exists, and shows a
"measurements in progress" state otherwise. Never invent numbers.
