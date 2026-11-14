# Throwaway spike B: forest clearcuts around Morton/Mineral WA. NISAR L-band dHV vs S1 C-band dVH vs OPERA DIST-ALERT-HLS.
import os, sys, json, glob, datetime as dt
import numpy as np, rasterio
import matplotlib; matplotlib.use("Agg")
import matplotlib.pyplot as plt

HERE = os.path.dirname(os.path.abspath(__file__)); ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)
from edl import https_fs, gcov_url
from spike_lib import nisar_pair, to_grid, rtc_mosaic, stats, pct, lonlat_corners

BBOX = [-122.45, 46.55, -122.05, 46.80]
PRE, POST = "2026-05-21", "2026-09-30"
S = json.load(open(os.path.join(HERE, "search.json")))
def ur(track, date):
    r = sorted([r for r in S["gcov"] if r["track"] == track and r["date"] == date], key=lambda r: r["ctr"])[-1]
    return gcov_url(r["ur"], r["coll"])

fs = https_fs()
meta, blk, G = nisar_pair(fs, ur("172", PRE), ur("172", POST), BBOX)
for k in ("pre", "post"):
    print(k, {kk: meta[k][kk] for kk in ("granule", "crid", "productVersion", "acquiredRangeBandwidth_freqA_Hz", "epsg", "t_read_3layers_s", "http_retries")}, flush=True)
dHV = blk["post_hv"] - blk["pre_hv"]; dHH = blk["post_hh"] - blk["pre_hh"]

def frac(path, cond):
    with rasterio.open(path) as ds:
        a = ds.read(1); ind = cond(a).astype("float64")
        if ds.nodata is not None: ind[a == ds.nodata] = np.nan
        return to_grid(ind, ds.transform, ds.crs, G)
f_forest = frac(os.path.join(HERE, "ref_data", "nlcd2021.tif"), lambda a: np.isin(a, [41, 42, 43]))
forest = f_forest >= 0.7

# OPERA DIST-ALERT-HLS reference: >=50 % veg loss, not a first-only detection, dated inside the pair window
rd = os.path.join(HERE, "ref_data")
st_f = glob.glob(os.path.join(rd, "*VEG-DIST-STATUS.tif"))[0]
d0 = (dt.date.fromisoformat(PRE) - dt.date(2020, 12, 31)).days; d1 = (dt.date(2026, 10, 11) - dt.date(2020, 12, 31)).days
with rasterio.open(st_f) as s_, rasterio.open(st_f.replace("VEG-DIST-STATUS", "VEG-DIST-DATE")) as d_, \
     rasterio.open(st_f.replace("VEG-DIST-STATUS", "VEG-ANOM-MAX")) as a_:
    stt, dd, am = s_.read(1), d_.read(1), a_.read(1)
    ind = ((am >= 50) & (am <= 100) & np.isin(stt, [2, 3, 5, 6, 7, 8]) & (dd >= d0) & (dd <= d1)).astype("float64")
    ind[stt == 255] = np.nan
    f_dist = to_grid(ind, s_.transform, s_.crs, G)
dist_ref = forest & (f_dist >= 0.5)
print("forest blocks", int(forest.sum()), "DIST-HLS reference clearcut blocks", int(dist_ref.sum()))

# C-band on the same grid; choose the S1 track pair with best forest coverage
C = {}
for trk, a, b in (("T064", "20260522", "20260926"), ("T137", "20260527", "20260919")):
    def m(date, pol):
        return rtc_mosaic(sorted(glob.glob(os.path.join(HERE, "rtc_data", f"OPERA_L2_RTC-S1_{trk}-*_{date}T*_{pol}.tif"))), G)
    dvh = m(b, "VH") - m(a, "VH"); dvv = m(b, "VV") - m(a, "VV")
    C[trk] = dict(pre=a, post=b, dVH=dvh, dVV=dvv, forest_cov=round(float(np.isfinite(dvh[forest]).mean()), 3))
    print(trk, "forest coverage", C[trk]["forest_cov"])

ref_hv = float(np.nanmedian(dHV[forest])); relHV = dHV - ref_hv
Lflag = forest & (relHV <= -3)
out = dict(bbox=BBOX, grid=dict(G, corners_lonlat=lonlat_corners(G)), nisar=meta,
           forest_def="NLCD2021 41/42/43 fraction >= 0.7 per 1 ha block",
           dist_ref_def=f"OPERA DIST-ALERT-HLS T10TES 2026-10-11 S2B granule: VEG-ANOM-MAX>=50 %, status in 2,3,5,6,7,8, VEG-DIST-DATE {PRE}..2026-10-11; block = >=50 % of pixels",
           n_forest_blocks=int(forest.sum()), n_dist_ref_blocks=int(dist_ref.sum()),
           L=dict(forest_median_shift_dHV=round(ref_hv, 2), dHV_forest=stats(dHV, forest), dHH_forest=stats(dHH, forest),
                  n_flag_relHV_le_minus3=int(Lflag.sum()), n_flag_rawHV_le_minus3=int((forest & (dHV <= -3)).sum()),
                  flagged_that_are_DIST=int((Lflag & dist_ref).sum()),
                  DIST_detected_by_L=int((dist_ref & (relHV <= -3)).sum()),
                  dHV_rel_in_DIST_blocks=stats(relHV, dist_ref)), C={})
for trk, c in C.items():
    rvh = c["dVH"] - np.nanmedian(c["dVH"][forest]); rvv = c["dVV"] - np.nanmedian(c["dVV"][forest])
    Cflag = forest & (rvh <= -2)
    both = Lflag & np.isfinite(rvh)
    out["C"][trk] = dict(pre=c["pre"], post=c["post"], forest_coverage=c["forest_cov"],
                         forest_median_shift_dVH=round(float(np.nanmedian(c["dVH"][forest])), 2),
                         L_flags_with_C_data=int(both.sum()), of_which_C_relVH_le_minus2=int((both & (rvh <= -2)).sum()),
                         of_which_C_relVV_le_minus2=int((both & (rvv <= -2)).sum()),
                         n_C_flags_relVH_le_minus2=int(Cflag.sum()), C_flags_that_are_DIST=int((Cflag & dist_ref).sum()),
                         DIST_detected_by_C_relVH_le_minus2=int((dist_ref & (rvh <= -2)).sum()),
                         DIST_with_C_data=int((dist_ref & np.isfinite(rvh)).sum()),
                         dVH_rel_in_DIST_blocks=stats(rvh, dist_ref), dVH_rel_in_L_flags=stats(rvh, Lflag))
    c["rvh"] = rvh
json.dump(out, open(os.path.join(HERE, "stats.json"), "w"), indent=1, default=str)
np.savez_compressed(os.path.join(HERE, "blocks.npz"), dHV=dHV, dHH=dHH, forest=forest, f_dist=f_dist, **blk,
                    **{f"{t}_dVH": c["dVH"] for t, c in C.items()}, **{f"{t}_dVV": c["dVV"] for t, c in C.items()})
print(json.dumps({k: v for k, v in out.items() if k not in ("grid", "nisar")}, indent=1, default=str))

best = max(C, key=lambda t: C[t]["forest_cov"])
ext = [G["xmin"], G["xmax"], G["ymin"], G["ymax"]]
fg, axs = plt.subplots(1, 3, figsize=(19, 6.5), dpi=100)
for ax, (t, a, cm, lo, hi) in zip(axs, [
        (f"NISAR L-band dHV {PRE} > {POST} (T172 D), rel. to forest", relHV, "RdBu", -6, 6),
        (f"S1 C-band dVH {C[best]['pre']} > {C[best]['post']} ({best}), rel. to forest", C[best]["rvh"], "RdBu", -6, 6),
        ("OPERA DIST-ALERT-HLS: fraction >=50 % veg loss in window", np.where(forest, f_dist, np.nan), "magma", 0, 1)]):
    im = ax.imshow(a, cmap=cm, vmin=lo, vmax=hi, extent=ext, interpolation="nearest")
    ax.set_title(t, fontsize=9); ax.set_xticks([]); ax.set_yticks([]); fg.colorbar(im, ax=ax, shrink=0.7)
fg.suptitle("Clearcuts near Morton/Mineral WA (1 ha blocks; blue/red = brighter/darker)", fontsize=11)
fg.savefig(os.path.join(HERE, "side_by_side.png")); plt.close(fg)
def sc(x, lo=-24, hi=-8): return np.clip((x - lo) / (hi - lo), 0, 1)
rgb = np.dstack([sc(blk["pre_hv"]), sc(blk["post_hv"]), sc(blk["post_hv"])]); rgb[~np.isfinite(rgb)] = 0
plt.imsave(os.path.join(HERE, "L_HV_change_RGB.png"), rgb)  # red = HV loss (pre bright, post dark)
plt.imsave(os.path.join(HERE, "L_dHV_rel_overlay.png"), relHV, cmap="RdBu", vmin=-6, vmax=6)
plt.imsave(os.path.join(HERE, "C_dVH_rel_overlay.png"), C[best]["rvh"], cmap="RdBu", vmin=-6, vmax=6)
