# Throwaway spike: NISAR GCOV pre/post fire change over Kaiser Canyon.
import sys, os, json, time
import numpy as np, h5py
from pyproj import Transformer
from shapely import make_valid, contains_xy
from shapely.geometry import shape, box
from shapely.ops import transform as shp_transform
import matplotlib; matplotlib.use("Agg")
import matplotlib.pyplot as plt

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
from edl import https_fs, gcov_url

COLL = "NISAR_L2_GCOV_PROVISIONAL_V1"
PRE = "NISAR_L2_PR_GCOV_025_071_D_064_4005_DHDH_A_20260713T030956_20260713T031031_P05023_N_F_J_001"
POST = "NISAR_L2_PR_GCOV_030_071_D_064_4005_DHDH_A_20260911T030953_20260911T031028_P05023_N_F_J_001"
BLOCK = 10  # 10x10 px at 10 m = 1 ha
MIN_VALID_FRAC = 0.5

cand = json.load(open(os.path.join(HERE, "candidates.json")))
bbox = cand["bbox"]  # lon/lat W,S,E,N
perim_ll = make_valid(shape(json.load(open(os.path.join(HERE, "kaiser_perimeter.geojson")))["features"][0]["geometry"]))

def s(v):
    v = v[()] if hasattr(v, "shape") else v
    return v.decode() if isinstance(v, bytes) else (v.item() if hasattr(v, "item") else v)

fs = https_fs()
meta, data = {}, {}
RETRIES = []
for tag, ur in (("pre", PRE), ("post", POST)):
    t0 = time.time()
    f = fs.open(gcov_url(ur, COLL), "rb", cache_type="blockcache", block_size=8 * 2**20)
    _orig = f.cache.fetcher
    def _retry(start, stop, _orig=_orig):
        for i in range(6):
            try:
                return _orig(start, stop)
            except Exception as e:  # ASF 502/503 seen mid-read
                RETRIES.append(f"{type(e).__name__}:{str(e)[:40]}")
                time.sleep(2 ** i)
        return _orig(start, stop)
    f.cache.fetcher = _retry
    h = h5py.File(f, "r", page_buf_size=16 * 2**20, rdcc_nbytes=4 * 2**20)
    t_open = time.time() - t0
    idn = h["/science/LSAR/identification"]
    g = h["/science/LSAR/GCOV/grids/frequencyA"]
    sw = h["/science/LSAR/GCOV/metadata/sourceData/swaths/frequencyA"]
    epsg = int(g["projection"][()])
    x = g["xCoordinates"][:]; y = g["yCoordinates"][:]
    tr = Transformer.from_crs(4326, epsg, always_xy=True)
    xs, ys = tr.transform([bbox[0], bbox[2], bbox[0], bbox[2]], [bbox[1], bbox[1], bbox[3], bbox[3]])
    X0, X1, Y0, Y1 = min(xs), max(xs), min(ys), max(ys)
    # snap to a common 100 m lattice so both dates and 10x10 blocks align
    X0 = np.floor(X0 / 100) * 100; X1 = np.ceil(X1 / 100) * 100
    Y0 = np.floor(Y0 / 100) * 100; Y1 = np.ceil(Y1 / 100) * 100
    dx = float(g["xCoordinateSpacing"][()]); dy = float(g["yCoordinateSpacing"][()])
    # pixel-centre or edge convention: find index of the first coordinate >= X0
    c0 = int(np.searchsorted(x, X0 + dx / 2 - 1e-6)); c1 = c0 + int(round((X1 - X0) / dx))
    r0 = int(np.searchsorted(-y, -(Y1 + dy / 2) - 1e-6)); r1 = r0 + int(round((Y1 - Y0) / -dy))
    t0 = time.time()
    hh = g["HHHH"][r0:r1, c0:c1]; t_hh = time.time() - t0
    hv = g["HVHV"][r0:r1, c0:c1]
    mk = g["mask"][r0:r1, c0:c1]
    nl = g["numberOfLooks"][r0:r1, c0:c1]
    t_read = time.time() - t0
    meta[tag] = dict(
        granule=ur, collection=COLL,
        date=s(idn["zeroDopplerStartTime"])[:19],
        track=s(idn["trackNumber"]), frame=s(idn["frameNumber"]), direction=s(idn["orbitPassDirection"]),
        absoluteOrbit=s(idn["absoluteOrbitNumber"]), crid=s(idn["compositeReleaseId"]),
        isMixedMode=s(idn["isMixedMode"]), isFullFrame=s(idn["isFullFrame"]),
        productVersion=s(idn["productVersion"]),
        acquiredRangeBandwidth_freqA_Hz=float(sw["acquiredRangeBandwidth"][()]),
        processedRangeBandwidth_freqA_Hz=float(sw["processedRangeBandwidth"][()]),
        polarizations=[p.decode() for p in g["listOfPolarizations"][:]],
        epsg=epsg, spacing_m=[dx, dy],
        window_rows_cols=[r0, r1, c0, c1], window_shape=list(hh.shape),
        window_x_first_center=float(x[c0]), window_y_first_center=float(y[r0]),
        t_open_s=round(t_open, 2), t_read_HHHH_s=round(t_hh, 2), t_read_4layers_s=round(t_read, 2),
        mask_values={int(k): int(v) for k, v in zip(*np.unique(mk, return_counts=True))},
        median_looks=float(np.nanmedian(nl)),
        http_retries=list(RETRIES),
    )
    RETRIES.clear()
    data[tag] = dict(hh=hh, hv=hv, mk=mk)
    print(tag, json.dumps({k: v for k, v in meta[tag].items() if k != "mask_values"}), flush=True)
    h.close(); f.close()

pre, post = data["pre"], data["post"]
assert meta["pre"]["window_x_first_center"] == meta["post"]["window_x_first_center"], "grid x misaligned"
assert meta["pre"]["window_y_first_center"] == meta["post"]["window_y_first_center"], "grid y misaligned"
assert pre["hh"].shape == post["hh"].shape

def valid(d):
    return (d["mk"] >= 1) & (d["mk"] <= 254) & np.isfinite(d["hh"]) & np.isfinite(d["hv"]) & (d["hh"] > 0) & (d["hv"] > 0)
v = valid(pre) & valid(post)  # union of invalid = intersection of valid
print("valid frac (both dates)", v.mean())

def blockmean(a, v):
    ny, nx = (a.shape[0] // BLOCK) * BLOCK, (a.shape[1] // BLOCK) * BLOCK
    a = np.where(v, a, 0.0)[:ny, :nx].astype("float64"); vv = v[:ny, :nx]
    s_ = a.reshape(ny // BLOCK, BLOCK, nx // BLOCK, BLOCK).sum(axis=(1, 3))
    n = vv.reshape(ny // BLOCK, BLOCK, nx // BLOCK, BLOCK).sum(axis=(1, 3))
    m = np.where(n >= MIN_VALID_FRAC * BLOCK * BLOCK, s_ / np.maximum(n, 1), np.nan)
    return 10 * np.log10(m)

db = {f"{t}_{p}": blockmean(data[t][p], v) for t in ("pre", "post") for p in ("hh", "hv")}
dHH = db["post_hh"] - db["pre_hh"]; dHV = db["post_hv"] - db["pre_hv"]

# block-centre coordinates and perimeter membership
epsg = meta["pre"]["epsg"]; dx, dy = meta["pre"]["spacing_m"]
x0e = meta["pre"]["window_x_first_center"] - dx / 2; y0e = meta["pre"]["window_y_first_center"] - dy / 2  # top-left edge
nby, nbx = dHV.shape
bx = x0e + (np.arange(nbx) + 0.5) * BLOCK * dx; byy = y0e + (np.arange(nby) + 0.5) * BLOCK * dy
BX, BY = np.meshgrid(bx, byy)
to_utm = Transformer.from_crs(4326, epsg, always_xy=True)
perim_utm = shp_transform(lambda xx, yy, z=None: to_utm.transform(xx, yy), perim_ll)
inside = contains_xy(perim_utm, BX, BY)
outside_buf = ~contains_xy(perim_utm.buffer(500), BX, BY)  # >500 m from perimeter

def st(a, sel):
    a = a[sel & np.isfinite(a)]
    return dict(n_blocks=int(a.size), median=round(float(np.median(a)), 3), mean=round(float(np.mean(a)), 3),
                p10=round(float(np.percentile(a, 10)), 3), p90=round(float(np.percentile(a, 90)), 3))
def frac_le(a, sel, thr):
    a = a[sel & np.isfinite(a)]; return round(float((a <= thr).mean() * 100), 2)

stats = dict(
    pair=dict(pre=meta["pre"], post=meta["post"]),
    method=dict(frequency="A", layers=["HHHH", "HVHV"], backscatter="gamma0 RTC, linear power -> block mean (linear) -> dB",
                block_px=BLOCK, block_m=BLOCK * dx, min_valid_frac=MIN_VALID_FRAC,
                mask="valid if mask in 1..254 and finite>0 on BOTH dates", outside="bbox blocks >500 m outside perimeter",
                perimeter="WFIGS_Interagency_Perimeters_YearToDate, Kaiser Canyon, 2026-WACOA-260140, make_valid applied",
                bbox_lonlat=bbox),
    valid_pixel_frac_both=round(float(v.mean()), 4),
    blocks_total=int(dHV.size), blocks_inside=int((inside & np.isfinite(dHV)).sum()),
    dHV_inside=st(dHV, inside), dHV_outside=st(dHV, outside_buf),
    dHH_inside=st(dHH, inside), dHH_outside=st(dHH, outside_buf),
    pre_HV_db_inside=st(db["pre_hv"], inside), post_HV_db_inside=st(db["post_hv"], inside),
)
stats.update({
    "pct_inside_dHV_le_minus2dB": frac_le(dHV, inside, -2), "pct_outside_dHV_le_minus2dB": frac_le(dHV, outside_buf, -2),
    "pct_inside_dHH_le_minus2dB": frac_le(dHH, inside, -2), "pct_outside_dHH_le_minus2dB": frac_le(dHH, outside_buf, -2),
    "pct_inside_dHV_ge_plus2dB": round(float((dHV[inside & np.isfinite(dHV)] >= 2).mean() * 100), 2),
})
woody = db["pre_hv"] >= -14.0; open_ = db["pre_hv"] < -18.0
stats["stratified_by_preHV"] = {
    "woody_preHV_ge_-14dB": dict(dHV_inside=st(dHV, inside & woody), dHV_outside=st(dHV, outside_buf & woody),
                                 dHH_inside=st(dHH, inside & woody), dHH_outside=st(dHH, outside_buf & woody),
                                 pct_inside_dHV_le_minus2dB=frac_le(dHV, inside & woody, -2),
                                 pct_outside_dHV_le_minus2dB=frac_le(dHV, outside_buf & woody, -2)),
    "open_preHV_lt_-18dB": dict(dHV_inside=st(dHV, inside & open_), dHV_outside=st(dHV, outside_buf & open_),
                                pct_inside_dHV_le_minus2dB=frac_le(dHV, inside & open_, -2)),
}
stats["relative_median_inside_minus_outside"] = dict(
    dHV=round(stats["dHV_inside"]["median"] - stats["dHV_outside"]["median"], 3),
    dHH=round(stats["dHH_inside"]["median"] - stats["dHH_outside"]["median"], 3))
np.savez_compressed(os.path.join(HERE, "blocks.npz"), dHV=dHV, dHH=dHH, inside=inside, outside_buf=outside_buf,
                    **{k: v for k, v in db.items()}, BX=BX, BY=BY)
# bounds
x1e =x0e + nbx * BLOCK * dx; y1e = y0e + nby * BLOCK * dy
to_ll = Transformer.from_crs(epsg, 4326, always_xy=True)
corners = {k: [round(c, 6) for c in to_ll.transform(*xy)] for k, xy in
           dict(upper_left=(x0e, y0e), upper_right=(x1e, y0e), lower_right=(x1e, y1e), lower_left=(x0e, y1e)).items()}
stats["png_bounds"] = dict(epsg=epsg, utm_extent_xmin_xmax_ymin_ymax=[x0e, x1e, y1e, y0e],
                           corners_lonlat=corners, png_shape_rows_cols=[nby, nbx], pixel_m=BLOCK * dx,
                           note="PNGs are in native UTM grid (north-up), not reprojected to lon/lat")
json.dump(stats, open(os.path.join(HERE, "stats.json"), "w"), indent=1, default=str)
print(json.dumps({k: v for k, v in stats.items() if k not in ("pair", "method", "png_bounds")}, indent=1, default=str))

# PNGs
ext = [x0e, x1e, y1e, y0e]
px, py = [], []
for geom in getattr(perim_utm, "geoms", [perim_utm]):
    for poly in getattr(geom, "geoms", [geom]):
        if poly.geom_type == "Polygon":
            xx, yy = poly.exterior.xy; px.append(xx); py.append(yy)
def fig(a, cmap, vmin, vmax, title, fname, label):
    fg, ax = plt.subplots(figsize=(10, 7), dpi=110)
    im = ax.imshow(a, cmap=cmap, vmin=vmin, vmax=vmax, extent=ext, interpolation="nearest")
    for xx, yy in zip(px, py): ax.plot(xx, yy, color="k" if cmap == "RdBu" else "yellow", lw=0.7)
    ax.set_title(title, fontsize=10); ax.set_xlabel(f"Easting (m, EPSG:{epsg})"); ax.set_ylabel("Northing (m)")
    fg.colorbar(im, ax=ax, label=label, shrink=0.8); fg.tight_layout(); fg.savefig(os.path.join(HERE, fname)); plt.close(fg)
    plt.imsave(os.path.join(HERE, fname.replace(".png", "_overlay.png")), a, cmap=cmap, vmin=vmin, vmax=vmax)
d1, d2 = meta["pre"]["date"][:10], meta["post"]["date"][:10]
fig(db["pre_hv"], "gray", -25, -8, f"NISAR L-band HV gamma0 {d1} (T71 F64 D, 1 ha blocks)", "before_HV.png", "dB")
fig(db["post_hv"], "gray", -25, -8, f"NISAR L-band HV gamma0 {d2} (T71 F64 D, 1 ha blocks)", "after_HV.png", "dB")
fig(dHV, "RdBu", -6, 6, f"dHV = HV({d2}) - HV({d1}); Kaiser Canyon perimeter", "dHV.png", "dB")
fig(dHH, "RdBu", -6, 6, f"dHH = HH({d2}) - HH({d1}); Kaiser Canyon perimeter", "dHH.png", "dB")
print("done")
