"""Build web/public/fixtures/ (Task B1) from the real-data spike figures in docs/mockups/.

Fixtures are stand-ins in the final Result shape (`"fixture": true`) so the web app can be built before
the pipeline's stories exist (Task A8 replaces them in web/public/stories/). What comes from where:
  - change maps, change areas, area_ha, dB medians/CIs, p-values: decoded from the spike PNGs
    (colormap inverted back to dB, resampled to the 100 m block grid, spike thresholds applied);
  - dates, tracks, thresholds, gauge stage, perimeter facts: docs/research/*-spike.md;
  - people.svi_tracts: live query of the CDC SVI 2022 FeatureServer (docs/research/stack.md);
  - series pre-event levels and before/after images are PLACEHOLDERS (no levels/backscatter PNGs in the repo).

Run from the repo root:  python web/scripts/build_fixtures.py
Needs: pillow numpy scipy shapely pyproj matplotlib (not part of the web build).
"""
import datetime
import json
import pathlib
import urllib.parse
import urllib.request
import warnings

import matplotlib
import numpy as np
from PIL import Image, ImageDraw, ImageFont
from pyproj import Transformer
from scipy import ndimage, stats
from scipy.spatial import cKDTree
import shapely
from shapely.geometry import MultiPolygon, Polygon, box, mapping
from shapely.geometry.polygon import orient
from shapely.ops import unary_union

ROOT = pathlib.Path(__file__).resolve().parents[2]
MOCKUPS = ROOT / "docs" / "mockups"
OUT = ROOT / "web" / "public" / "fixtures"
SVI_URL = ("https://onemap.cdc.gov/onemapservices/rest/services/SVI/"
           "CDC_ATSDR_Social_Vulnerability_Index_2022_USA/FeatureServer/2/query")
RES = 100.0          # block size in metres (1 ha)
MIN_HA = 3           # minimum change area
TOP_PER_KIND = 10    # areas kept per agreement kind
RNG = np.random.default_rng(20261114)

# Evidence notes by (band, direction); direction is "down"/"up" for |change| >= 2 dB, else "flat".
NOTES = {
    ("HV", "down"): "L-band HV echoes come from branches and trunks; a drop this size means much of that volume is gone.",
    ("HV", "up"): "L-band HV rose: more volume scattering from branches, or wetter vegetation.",
    ("HV", "flat"): "L-band HV barely changed here.",
    ("HH", "up"): "Water under trees bounces the radar off trunks and straight back (double bounce), so HH brightens.",
    ("HH", "down"): "L-band HH fell: less trunk-ground bounce, as when trees are removed.",
    ("HH", "flat"): "L-band HH barely changed here.",
    ("VH", "down"): "C-band (5.6 cm) scatters off leaves, twigs, grass and shrubs; a drop like this means that layer thinned or burned.",
    ("VH", "up"): "C-band VH rose: denser or wetter low vegetation.",
    ("VH", "flat"): "Sentinel-1 VH barely changed here.",
    ("VV", "up"): "C-band VV rose: a wetter or rougher surface.",
    ("VV", "down"): "C-band VV fell: a smoother or drier surface, or open water.",
    ("VV", "flat"): "Sentinel-1 VV barely changed here.",
}
EDOUARD_S1 = " Sentinel-1 had no pass during the flood: its dates are Aug 20 (before) and Sep 13 (after recession)."

# Panel frames are approximate pixel boxes (left, top, right, bottom) in the figure; refined automatically.
STORIES = {
    "clearcuts": dict(
        title="Clearcuts NISAR caught", place="Morton / Mineral, WA",
        summary=("Spike vs OPERA DIST-ALERT-HLS: at similar recall, 35.7% of NISAR flags were clearcuts "
                 "vs 4.6% for Sentinel-1."),
        bbox=[-122.45, 46.55, -122.05, 46.80], epsg=32610,
        nisar=dict(track=172, direction="D", dates=["2026-05-21", "2026-09-30"]),
        s1=dict(track=137, dates=["2026-05-27", "2026-09-19"]), message=None,
        panels={"HV": ("clearcut_side.png", (238, 171, 584, 485), "RdBu", 6),
                "VH": ("clearcut_side.png", (757, 171, 1104, 485), "RdBu", 6)},
        l_band="HV", c_band="VH", l_thr=-3.0, c_thr=-2.0, smooth=1,
        pre_db={"HV": -12.5, "VH": -12.0},
        extra=[dict(label="Scene-wide forest HV shift removed", value=0.11, ci=None, unit="dB",
                    note="Changes are measured relative to unchanged forest in the same scene.")],
    ),
    "kaiser": dict(
        title="Kaiser Canyon Fire", place="Colville Reservation, WA",
        summary=("Sentinel-1 wins here: 40.6% of burned 1-ha blocks dropped at least 2 dB in C-band VH vs "
                 "4.7% in NISAR HV. Mostly a grass and shrub fire."),
        bbox=[-119.3705, 48.0531, -118.7196, 48.3605], epsg=32610,
        nisar=dict(track=71, direction="D", dates=["2026-07-13", "2026-09-11"]),
        s1=dict(track=166, dates=["2026-07-11", "2026-09-09"]), message=None,
        panels={"HV": ("kaiser_L_dHV.png", (94, 94, 886, 675), "RdBu", 6),
                "VH": ("kaiser_C_dVH.png", (72, 88, 881, 682), "RdBu", 6)},
        l_band="HV", c_band="VH", l_thr=-2.0, c_thr=-2.0, smooth=3, perimeter_from="HV",
        pre_db={"HV": -17.0, "VH": -17.5},
        extra=[],
    ),
    "edouard": dict(
        title="Edouard floods under forest", place="Village Creek near Kountze, TX",
        summary=("NISAR HH brightened 3 to 6 dB along the flooded creek bottomland; Sentinel-1 had no pass "
                 "during the flood."),
        bbox=[-94.45, 30.10, -94.00, 30.55], epsg=32615,
        nisar=dict(track=12, direction="D", dates=["2026-08-26", "2026-09-07"]),
        s1=dict(track=136, dates=["2026-08-20", "2026-09-13"]),
        message="Sentinel-1 passed before (Aug 20) and after (Sep 13) the flood peak, not during it.",
        panels={"HH": ("edouard_side.png", (275, 158, 572, 499), "RdBu_r", 8),
                "HV": ("edouard_side.png", (631, 158, 927, 499), "RdBu_r", 8),
                "VV": ("edouard_side.png", (987, 158, 1283, 499), "RdBu_r", 8),
                "VH": ("edouard_side.png", (1342, 158, 1639, 499), "RdBu_r", 8)},
        l_band="HH", c_band="VV", l_thr=3.0, c_thr=3.0, smooth=3,
        pre_db={"HH": -7.5, "HV": -12.5, "VV": -8.0, "VH": -13.5},
        extra=[dict(label="Village Creek stage at the NISAR pass", value=14.8, ci=None, unit="ft",
                    note="USGS gauge near Kountze, 2026-09-07 (peak 22.2 ft on 09-04, 5.6 ft by 09-13).")],
    ),
}


# ------------------------------------------------------------------ geometry of the block grid

def block_grid(bbox, epsg):
    """UTM window enclosing the bbox, snapped outward to 100 m (same rule as scripts/spikes/spike_lib.py)."""
    tr = Transformer.from_crs(4326, epsg, always_xy=True)
    xs, ys = tr.transform([bbox[0], bbox[2], bbox[0], bbox[2]], [bbox[1], bbox[1], bbox[3], bbox[3]])
    x0, x1 = np.floor(min(xs) / RES) * RES, np.ceil(max(xs) / RES) * RES
    y0, y1 = np.floor(min(ys) / RES) * RES, np.ceil(max(ys) / RES) * RES
    return dict(epsg=epsg, x0=x0, x1=x1, y0=y0, y1=y1, nx=int((x1 - x0) / RES), ny=int((y1 - y0) / RES))


def corners_lonlat(g):
    to_ll = Transformer.from_crs(g["epsg"], 4326, always_xy=True)
    pts = [(g["x0"], g["y1"]), (g["x1"], g["y1"]), (g["x1"], g["y0"]), (g["x0"], g["y0"])]  # UL UR LR LL
    return [[round(v, 6) for v in to_ll.transform(x, y)] for x, y in pts]


# ------------------------------------------------------------------ decoding the spike figures

def refine_frame(img, approx, search=4):
    """Snap each frame edge to the darkest nearby line (the matplotlib axes spine)."""
    dark = img.max(2) < 90
    l, t, r, b = approx
    def best(cands, score):
        return max(cands, key=score)
    l = best(range(l - search, l + search + 1), lambda c: dark[t:b, c].mean())
    r = best(range(r - search, r + search + 1), lambda c: dark[t:b, c].mean())
    t = best(range(t - search, t + search + 1), lambda y: dark[y, l:r].mean())
    b = best(range(b - search, b + search + 1), lambda y: dark[y, l:r].mean())
    return l, t, r, b


def decode_panel(path, approx, cmap_name, vmax):
    """Crop a panel and invert its colormap to dB. Pixels not on the colormap (contours) become NaN."""
    img = np.asarray(Image.open(MOCKUPS / path).convert("RGB")).astype(float)
    l, t, r, b = refine_frame(img, approx)
    crop = img[t + 1:b, l + 1:r]
    lut = matplotlib.colormaps[cmap_name](np.linspace(0, 1, 256))[:, :3] * 255
    dist, idx = cKDTree(lut).query(crop.reshape(-1, 3))
    vals = (-vmax + (idx + 0.5) / 256 * 2 * vmax).reshape(crop.shape[:2])
    off_map = dist.reshape(crop.shape[:2]) > 25
    vals[off_map] = np.nan
    return vals, off_map


def resample(a, ny, nx):
    """Nearest-neighbour resample of a panel onto the block grid."""
    rows = np.minimum((np.arange(ny) + 0.5) / ny * a.shape[0], a.shape[0] - 1).astype(int)
    cols = np.minimum((np.arange(nx) + 0.5) / nx * a.shape[1], a.shape[1] - 1).astype(int)
    return a[np.ix_(rows, cols)]


def fill_nan(a):
    bad = np.isnan(a)
    if not bad.any():
        return a
    _, (ri, ci) = ndimage.distance_transform_edt(bad, return_indices=True)
    return a[ri, ci]


def perimeter_mask(off_map, ny, nx):
    """Kaiser figures draw the NIFC perimeter as a thin dark line (off the colormap): close gaps, fill it."""
    line = ndimage.binary_dilation(off_map, iterations=2)
    inside = ndimage.binary_erosion(ndimage.binary_fill_holes(line), iterations=2)
    return resample(inside, ny, nx)


# ------------------------------------------------------------------ areas

def component_polygon(mask, g, to_ll):
    """Union of per-row pixel runs -> simplified polygon in lon/lat (exterior counter-clockwise)."""
    boxes = []
    for r in np.unique(np.nonzero(mask)[0]):
        cols = np.nonzero(mask[r])[0]
        starts = cols[np.r_[True, np.diff(cols) > 1]]
        ends = cols[np.r_[np.diff(cols) > 1, True]] + 1
        boxes += [box(s, r, e, r + 1) for s, e in zip(starts, ends)]
    shape = unary_union(boxes).simplify(0.6, preserve_topology=True)
    def to_lonlat(cr):
        return np.column_stack(to_ll.transform(g["x0"] + cr[:, 0] * RES, g["y1"] - cr[:, 1] * RES))
    shape = shapely.transform(shape, to_lonlat)
    polys = list(shape.geoms) if isinstance(shape, MultiPolygon) else [shape]
    polys = [orient(p, 1.0) for p in polys if isinstance(p, Polygon) and not p.is_empty]
    geom = mapping(polys[0] if len(polys) == 1 else MultiPolygon(polys))
    return json.loads(json.dumps(geom), parse_float=lambda s: round(float(s), 6))


def median_ci(v):
    v = v[np.isfinite(v)]
    boots = np.median(RNG.choice(v, size=(200, v.size)), axis=1)
    return round(float(np.median(v)), 1), [round(float(np.percentile(boots, 2.5)), 1),
                                          round(float(np.percentile(boots, 97.5)), 1)]


def fmt_date(iso):
    d = datetime.date.fromisoformat(iso)
    return f"{d:%b} {d.day}"


def classify(sid, agreement, inside_frac):
    if sid == "clearcuts":
        return "forest_loss" if agreement != "C" else "uncertain"
    if sid == "edouard":
        return "flooded_vegetation" if agreement != "C" else "uncertain"
    if inside_frac >= 0.5:
        return "burn"
    return "forest_loss" if agreement != "C" else "uncertain"


def plain_text(sid, cls, agreement, ha, ev, cfg):
    lb, cb = cfg["l_band"], cfg["c_band"]
    l_v, c_v = ev[lb], ev[cb]
    d0, d1 = (fmt_date(d) for d in (cfg["nisar"]["dates"][0], cfg["nisar"]["dates"][-1]))
    s0, s1 = (fmt_date(d) for d in (cfg["s1"]["dates"][0], cfg["s1"]["dates"][-1]))
    l_only = f"Sentinel-1 {cb} barely moved ({c_v:+.1f} dB), so only NISAR saw it."
    if sid == "edouard":
        l_only = f"Sentinel-1 {cb} barely moved ({c_v:+.1f} dB), but it had no pass during the flood."
    who = {"L": l_only,
           "both": f"Sentinel-1 {cb} changed too ({c_v:+.1f} dB), so both radars saw it.",
           "C": ""}[agreement]
    if cls == "forest_loss":
        lead = f"About {ha:,} ha of forest darkened in NISAR's {lb} channel ({l_v:+.1f} dB) between {d0} and {d1}, the pattern of trees being removed."
    elif cls == "burn":
        if agreement == "C":
            return (f"About {ha:,} ha inside the Kaiser Canyon Fire perimeter darkened in Sentinel-1 {cb} ({c_v:+.1f} dB) "
                    f"between {s0} and {s1}, while NISAR {lb} moved only {l_v:+.1f} dB: burned grass and shrubs "
                    "show up in C-band more than in L-band.")
        lead = f"About {ha:,} ha inside the Kaiser Canyon Fire perimeter darkened in NISAR {lb} ({l_v:+.1f} dB) between {d0} and {d1}, the pattern of burned trees."
    elif cls == "flooded_vegetation":
        lead = f"About {ha:,} ha of bottomland forest brightened in NISAR {lb} ({l_v:+.1f} dB) between {d0} and {d1}, the double-bounce signal of floodwater under trees."
    else:
        return (f"About {ha:,} ha changed in Sentinel-1 {cb} ({c_v:+.1f} dB) between {s0} and {s1} while NISAR {lb} "
                f"moved {l_v:+.1f} dB. The cause is uncertain (only Sentinel-1 saw it).")
    return f"{lead} {who}".strip()


def evidence_for(sid, cfg, meds, inside_pct):
    out = []
    for band, (v, ci) in meds.items():
        sensor = "NISAR" if band in ("HH", "HV") else "Sentinel-1"
        note = NOTES[(band, "flat" if abs(v) < 2 else "up" if v > 0 else "down")]
        if sid == "edouard" and band == "VV":
            note += EDOUARD_S1
        out.append(dict(label=f"{sensor} {band} change", value=v, ci=ci, unit="dB", note=note))
    if inside_pct is not None:
        out.append(dict(label="Share inside the NIFC fire perimeter", value=inside_pct, ci=None, unit="%",
                        note="Kaiser Canyon Fire 2026-WACOA-260140, 138,285 acres. Radar alone can't tell fire "
                             "from logging; the perimeter is why this says burn."))
    return out + cfg["extra"]


def build_areas(sid, cfg, g, raw, smooth, inside):
    lb, cb = cfg["l_band"], cfg["c_band"]
    hit = lambda a, thr: a <= thr if thr < 0 else a >= thr
    L = hit(smooth[lb], cfg["l_thr"])
    C = hit(smooth[cb], cfg["c_thr"])
    kinds = {"L": L & ~C, "both": L & C, "C": C & ~L}
    to_ll = Transformer.from_crs(g["epsg"], 4326, always_xy=True)
    dates = sorted(set(cfg["nisar"]["dates"]) | set(cfg["s1"]["dates"]))
    areas = []
    for agreement, mask in kinds.items():
        lab, n = ndimage.label(mask)
        sizes = ndimage.sum_labels(mask, lab, index=np.arange(1, n + 1))
        order = [i + 1 for i in np.argsort(-sizes) if sizes[i] >= MIN_HA][:TOP_PER_KIND]
        for k in order:
            comp = lab == k
            ha = int(comp.sum())
            meds = {b: median_ci(raw[b][comp]) for b in raw}
            prim = lb if agreement != "C" else cb
            thr = cfg["l_thr"] if prim == lb else cfg["c_thr"]
            frac = float(hit(raw[prim][comp], thr).mean())
            label = "High" if frac >= 0.8 and abs(meds[prim][0]) >= 3 else "Medium" if frac >= 0.5 else "Low"
            with warnings.catch_warnings(), np.errstate(all="ignore"):
                warnings.simplefilter("ignore")
                p = float(stats.ttest_1samp(raw[prim][comp], 0.0).pvalue)
            if not np.isfinite(p):  # all values identical (saturated colormap bin)
                p = 1e-12 if abs(meds[prim][0]) > 0 else 1.0
            inside_frac = float(inside[comp].mean()) if inside is not None else 0.0
            cls = classify(sid, agreement, inside_frac)
            ev_vals = {b: meds[b][0] for b in meds}
            series = {"dates": dates}
            for b in ("HH", "HV", "VV", "VH"):
                own = cfg["nisar"]["dates"] if b in ("HH", "HV") else cfg["s1"]["dates"]
                if b not in raw:
                    series[b] = [None] * len(dates)
                    continue
                pre, post = cfg["pre_db"][b], round(cfg["pre_db"][b] + meds[b][0], 1)
                series[b] = [(pre if d == own[0] else post) if d in own else None for d in dates]
            areas.append(dict(
                id=f"{sid}-{agreement.lower()}-{len(areas) + 1}",
                geometry=component_polygon(comp, g, to_ll),
                agreement=agreement, **{"class": cls}, area_ha=float(ha),
                confidence=round(frac, 2), confidence_label=label,
                p_value=float(f"{max(p, 1e-12):.3g}"),
                change_date=(cfg["s1"] if agreement == "C" else cfg["nisar"])["dates"][-1],
                evidence=evidence_for(sid, cfg, meds, round(inside_frac * 100) if inside is not None else None),
                plain_text=plain_text(sid, cls, agreement, ha, ev_vals, cfg),
                series=series,
            ))
    return areas, kinds


# ------------------------------------------------------------------ rendering

def rgba(a):
    return Image.fromarray(a.astype(np.uint8), "RGBA")


def render_delta(v):
    """Diverging render: red = darker, blue = brighter; stable ground fades to transparent."""
    norm = np.clip((v + 6) / 12, 0, 1)
    rgb = matplotlib.colormaps["RdBu"](norm)[..., :3] * 255
    alpha = np.clip(np.abs(v) / 3, 0, 1) * 220
    return rgba(np.dstack([rgb, alpha]))


def render_change(kinds, shape):
    out = np.zeros((*shape, 4))
    for k, color in (("C", "#22d3ee"), ("both", "#a78bfa"), ("L", "#f59e0b")):
        out[kinds[k]] = [int(color[i:i + 2], 16) for i in (1, 3, 5)] + [220]
    return rgba(out)


def render_placeholder(shape, lines):
    ny, nx = shape
    img = Image.new("RGBA", (nx, ny), (40, 44, 52, 200))
    draw = ImageDraw.Draw(img)
    font = ImageFont.load_default(size=max(12, nx // 28))
    y = ny // 2 - len(lines) * nx // 40
    for line in lines:
        w = draw.textlength(line, font=font)
        draw.text(((nx - w) / 2, y), line, fill=(230, 234, 242, 255), font=font)
        y += nx // 20
    return img


# ------------------------------------------------------------------ people

def svi_tracts(bbox):
    q = dict(where="1=1", geometry=",".join(map(str, bbox)), geometryType="esriGeometryEnvelope", inSR=4326,
             spatialRel="esriSpatialRelIntersects", outFields="FIPS,LOCATION,RPL_THEMES",
             returnGeometry="false", f="json")
    try:
        with urllib.request.urlopen(SVI_URL + "?" + urllib.parse.urlencode(q), timeout=60) as r:
            feats = json.load(r).get("features", [])
    except OSError as e:
        print("  SVI query failed, leaving tracts empty:", e)
        return []
    rows = [f["attributes"] for f in feats if (f["attributes"].get("RPL_THEMES") or -999) >= 0]
    rows.sort(key=lambda a: -a["RPL_THEMES"])
    return [dict(geoid=a["FIPS"], rpl_themes=round(a["RPL_THEMES"], 4), name=a["LOCATION"].replace("; ", ", "))
            for a in rows[:15]]


# ------------------------------------------------------------------ main

def build(sid, cfg):
    g = block_grid(cfg["bbox"], cfg["epsg"])
    print(f"{sid}: block grid {g['nx']}x{g['ny']} EPSG:{g['epsg']} x {g['x0']:.0f}..{g['x1']:.0f} y {g['y0']:.0f}..{g['y1']:.0f}")
    raw, smooth, inside = {}, {}, None
    for band, (png, approx, cmap, vmax) in cfg["panels"].items():
        vals, off_map = decode_panel(png, approx, cmap, vmax)
        a = fill_nan(resample(vals, g["ny"], g["nx"]))
        raw[band] = a - np.median(a)  # relative change: remove the scene-wide shift (spec section 6.2)
        smooth[band] = ndimage.median_filter(raw[band], size=cfg["smooth"]) if cfg["smooth"] > 1 else raw[band]
        if cfg.get("perimeter_from") == band:
            inside = perimeter_mask(off_map, g["ny"], g["nx"])
            print(f"  perimeter covers {inside.mean():.1%} of the box")
    areas, kinds = build_areas(sid, cfg, g, raw, smooth, inside)
    shape = (g["ny"], g["nx"])
    d = OUT / sid
    d.mkdir(parents=True, exist_ok=True)
    render_change(kinds, shape).save(d / "change.png", optimize=True)
    render_delta(raw[cfg["l_band"]]).save(d / "l.png", optimize=True)
    render_delta(raw[cfg["c_band"]]).save(d / "c.png", optimize=True)
    for name, idx in (("before", 0), ("after", -1)):
        render_placeholder(shape, ["FIXTURE PLACEHOLDER", f"NISAR {name} pass {cfg['nisar']['dates'][idx]}",
                                   "Real backscatter image comes from the pipeline"]).save(d / f"{name}.png", optimize=True)
    result = dict(
        bbox=cfg["bbox"], message=cfg["message"], fixture=True,
        nisar=cfg["nisar"], s1=cfg["s1"],
        overlays=dict(change_png=f"{sid}/change.png", l_png=f"{sid}/l.png", c_png=f"{sid}/c.png",
                      before_png=f"{sid}/before.png", after_png=f"{sid}/after.png", bounds=corners_lonlat(g)),
        areas=areas, people=dict(svi_tracts=svi_tracts(cfg["bbox"])),
        exports=dict(geotiff=None, csv=None, notebook=None),
    )
    (OUT / f"{sid}.json").write_text(json.dumps(result, separators=(",", ":")), encoding="utf-8")
    totals = {k: int(sum(a["area_ha"] for a in areas if a["agreement"] == k)) for k in ("L", "both", "C")}
    print(f"  {len(areas)} areas, ha by agreement {totals}, changed blocks "
          f"{ {k: int(m.sum()) for k, m in kinds.items()} }, {len(result['people']['svi_tracts'])} SVI tracts")
    return dict(id=sid, title=cfg["title"], place=cfg["place"],
                dates=[cfg["nisar"]["dates"][0], cfg["nisar"]["dates"][-1]], summary=cfg["summary"])


if __name__ == "__main__":
    OUT.mkdir(parents=True, exist_ok=True)
    index = [build(sid, cfg) for sid, cfg in STORIES.items()]
    (OUT / "index.json").write_text(json.dumps(index, indent=1), encoding="utf-8")
