# Throwaway spike A: Tropical Storm Edouard flooded forest (Neches / Village Creek bottomlands near Kountze, TX).
import os, sys, json, glob
import numpy as np, rasterio
import matplotlib; matplotlib.use("Agg")
import matplotlib.pyplot as plt

HERE = os.path.dirname(os.path.abspath(__file__)); ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)
from edl import https_fs, gcov_url
from spike_lib import nisar_pair, to_grid, rtc_mosaic, stats, pct, lonlat_corners

BBOX = [-94.45, 30.10, -94.00, 30.55]
S = json.load(open(os.path.join(HERE, "search.json")))
def ur(track, date):
    rs = [r for r in S["gcov"] if r["track"] == track and r["date"] == date]
    r = sorted(rs, key=lambda r: r["ctr"])[-1]  # keep highest _00N counter
    return gcov_url(r["ur"], r["coll"])

fs = https_fs()
pairs = {"L_T12D_0826_0907": ("12", "2026-08-26", "2026-09-07"), "L_T134A_0822_0903": ("134", "2026-08-22", "2026-09-03")}
L = {}; grid = None
for name, (trk, d1, d2) in pairs.items():
    meta, blk, g = nisar_pair(fs, ur(trk, d1), ur(trk, d2), BBOX)
    print(name, json.dumps({k: {kk: meta[k][kk] for kk in ("granule", "crid", "acquiredRangeBandwidth_freqA_Hz", "epsg", "t_read_3layers_s", "http_retries")} for k in ("pre", "post")}), flush=True)
    L[name] = dict(meta=meta, blk=blk, grid=g)
G = L["L_T12D_0826_0907"]["grid"]
assert L["L_T134A_0822_0903"]["grid"]["epsg"] == G["epsg"] and L["L_T134A_0822_0903"]["grid"]["shape"] == G["shape"], "secondary pair grid differs"

# ---- reference layers on the 1 ha grid
def frac_on_grid(path, classes, nodata_vals=(), extra_tiles=()):
    acc = None; cnt = None
    for p in [path, *extra_tiles]:
        with rasterio.open(p) as ds:
            a = ds.read(1); ind = np.isin(a, classes).astype("float64")
            ind[np.isin(a, list(nodata_vals))] = np.nan
            o = to_grid(ind, ds.transform, ds.crs, G)
        if acc is None: acc = np.zeros_like(o); cnt = np.zeros_like(o)
        ok = np.isfinite(o); acc[ok] += o[ok]; cnt[ok] += 1
    return np.where(cnt > 0, acc / np.maximum(cnt, 1), np.nan)

nl = os.path.join(HERE, "ref_data", "nlcd2021.tif")
f_wwet = frac_on_grid(nl, [90], (0,)); f_upf = frac_on_grid(nl, [41, 42, 43], (0,))
f_nwater = frac_on_grid(nl, [11], (0,)); f_emerg = frac_on_grid(nl, [95], (0,))
wtr = sorted(glob.glob(os.path.join(HERE, "ref_data", "*_B01_WTR.tif")))
f_open = frac_on_grid(wtr[0], [1], (250, 251, 252, 253, 254, 255), wtr[1:])
f_inv = frac_on_grid(wtr[0], [3], (250, 251, 252, 253, 254, 255), wtr[1:])

floodplain = (f_wwet >= 0.7) & (f_nwater < 0.05) & (f_open < 0.2)
upland = (f_upf >= 0.7) & (f_open < 0.05) & (f_wwet < 0.1)
print("blocks floodplain forest", int(floodplain.sum()), "upland forest", int(upland.sum()))

# ---- C-band
def rtc(date, pol):
    return rtc_mosaic(sorted(glob.glob(os.path.join(HERE, "rtc_data", f"OPERA_L2_RTC-S1_T136-*_{date}T*_{pol}.tif"))), G)
C = {}
for name, (d1, d2) in {"C_T136_0820_0913": ("20260820", "20260913"), "C_T136_0820_0901": ("20260820", "20260901")}.items():
    C[name] = {"dVV": rtc(d2, "VV") - rtc(d1, "VV"), "dVH": rtc(d2, "VH") - rtc(d1, "VH")}

# ---- stats (raw and relative to upland-forest median)
out = dict(bbox=BBOX, grid=dict(G, corners_lonlat=lonlat_corners(G)),
           strata=dict(floodplain_forest="NLCD2021 woody wetland (90) frac>=0.7, NLCD water<0.05, DSWx-S1 0913 open water<0.2",
                       upland_forest="NLCD2021 41/42/43 frac>=0.7, DSWx open water<0.05, woody wetland<0.1",
                       n_floodplain=int(floodplain.sum()), n_upland=int(upland.sum())),
           pairs={})
def summarize(name, d):
    r = {}
    for k, a in d.items():
        ref = np.nanmedian(a[upland])
        rel = a - ref
        r[k] = dict(floodplain=stats(a, floodplain), upland=stats(a, upland), upland_median_shift=round(float(ref), 2),
                    pct_floodplain_ge3_raw=pct(a, floodplain, ">=", 3), pct_upland_ge3_raw=pct(a, upland, ">=", 3),
                    pct_floodplain_ge3_rel=pct(rel, floodplain, ">=", 3), pct_upland_ge3_rel=pct(rel, upland, ">=", 3),
                    relative_median_floodplain_minus_upland=round(float(np.nanmedian(a[floodplain]) - ref), 2))
    return r
for name, v in L.items():
    b = v["blk"]
    d = {"dHH": b["post_hh"] - b["pre_hh"], "dHV": b["post_hv"] - b["pre_hv"]}
    v["d"] = d
    out["pairs"][name] = dict(meta=v["meta"], **summarize(name, d))
for name, d in C.items():
    out["pairs"][name] = summarize(name, d)

# agreement with DSWx-S1 inundated vegetation (C-band product, 09-13) inside floodplain forest
dHH = L["L_T12D_0826_0907"]["d"]["dHH"]; relHH = dHH - np.nanmedian(dHH[upland])
inv = f_inv >= 0.5
out["dswx_s1_0913"] = dict(
    pct_floodplain_blocks_inundated_veg_ge50=pct(f_inv, floodplain, ">=", 0.5),
    pct_floodplain_blocks_open_water_ge20=pct(f_open, (f_wwet >= 0.7), ">=", 0.2),
    pct_upland_blocks_inundated_veg_ge50=pct(f_inv, upland, ">=", 0.5),
    L_relHH_ge3_and_floodplain=int((floodplain & (relHH >= 3)).sum()),
    of_those_dswx_inundated_veg=int((floodplain & (relHH >= 3) & inv).sum()))
json.dump(out, open(os.path.join(HERE, "stats.json"), "w"), indent=1, default=str)
np.savez_compressed(os.path.join(HERE, "blocks.npz"), floodplain=floodplain, upland=upland, f_inv=f_inv, f_open=f_open,
                    f_wwet=f_wwet, **{f"{n}_{k}": a for n, v in L.items() for k, a in v["d"].items()},
                    **{f"{n}_{k}": a for n, d in C.items() for k, a in d.items()},
                    **{f"{n}_{k}": a for n, v in L.items() for k, a in v["blk"].items()})

# ---- figures: side by side L dHH | L dHV | C dVV | C dVH with floodplain contour
ext = [G["xmin"], G["xmax"], G["ymin"], G["ymax"]]
panels = [("NISAR L dHH 08-26>09-07", L["L_T12D_0826_0907"]["d"]["dHH"]), ("NISAR L dHV 08-26>09-07", L["L_T12D_0826_0907"]["d"]["dHV"]),
          ("S1 C dVV 08-20>09-13", C["C_T136_0820_0913"]["dVV"]), ("S1 C dVH 08-20>09-13", C["C_T136_0820_0913"]["dVH"])]
fg, axs = plt.subplots(1, 4, figsize=(22, 6.5), dpi=100)
for ax, (t, a) in zip(axs, panels):
    im = ax.imshow(a, cmap="RdBu_r", vmin=-8, vmax=8, extent=ext, interpolation="nearest")
    ax.contour(np.flipud(floodplain.astype(float)), levels=[0.5], colors="k", linewidths=0.4, extent=ext)
    ax.set_title(t, fontsize=10); ax.set_xticks([]); ax.set_yticks([])
fg.colorbar(im, ax=axs, label="dB (red = brighter after storm)", shrink=0.8)
fg.suptitle("Edouard: Neches/Village Creek bottomlands; black = NLCD woody-wetland floodplain blocks", fontsize=11)
fg.savefig(os.path.join(HERE, "side_by_side.png")); plt.close(fg)
for (t, a), fn in zip(panels, ["L_dHH.png", "L_dHV.png", "C_dVV.png", "C_dVH.png"]):
    plt.imsave(os.path.join(HERE, fn.replace(".png", "_overlay.png")), a, cmap="RdBu_r", vmin=-8, vmax=8)
# RGB for L-band HH: R=post, G=pre, B=pre (red = brightening)
b = L["L_T12D_0826_0907"]["blk"]
def sc(x, lo=-22, hi=2): return np.clip((x - lo) / (hi - lo), 0, 1)
rgb = np.dstack([sc(b["post_hh"]), sc(b["pre_hh"]), sc(b["pre_hh"])]); rgb[~np.isfinite(rgb)] = 0
plt.imsave(os.path.join(HERE, "L_HH_change_RGB.png"), rgb)
print(json.dumps({k: v for k, v in out.items() if k not in ("grid",)}, indent=1, default=str)[:9000])
