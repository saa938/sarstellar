# Throwaway spike: OPERA RTC-S1 (C-band) change on the same 100 m (1 ha) grid as the NISAR blocks.
import sys, os, json, glob, re
import numpy as np, rasterio
from rasterio.warp import reproject, Resampling
from rasterio.transform import from_origin
import matplotlib; matplotlib.use("Agg")
import matplotlib.pyplot as plt

HERE = os.path.dirname(os.path.abspath(__file__))
DATA = sys.argv[1]
st_ = json.load(open(os.path.join(HERE, "stats.json")))
B = np.load(os.path.join(HERE, "blocks.npz"))
inside, outside_buf = B["inside"], B["outside_buf"]
pb = st_["png_bounds"]; xmin, xmax, ymin, ymax = pb["utm_extent_xmin_xmax_ymin_ymax"]
ny, nx = pb["png_shape_rows_cols"]; res = pb["pixel_m"]
dst_tr = from_origin(xmin, ymax, res, res); dst_crs = f"EPSG:{pb['epsg']}"

# inspect mask encoding once
mf = sorted(glob.glob(os.path.join(DATA, "*_mask.tif")))[0]
with rasterio.open(mf) as ds:
    print("mask tags:", {k: v[:200] for k, v in ds.tags().items() if "mask" in k.lower() or "layover" in k.lower() or "shadow" in k.lower() or "desc" in k.lower()})
    print("mask band desc:", ds.descriptions, "dtype", ds.dtypes, "nodata", ds.nodata, "crs", ds.crs)
    a = ds.read(1); u, c = np.unique(a, return_counts=True); print("mask values:", dict(zip(u.tolist(), c.tolist())))

def mosaic(track, date, pol):
    acc = np.zeros((ny, nx)); cnt = np.zeros((ny, nx))
    for f in sorted(glob.glob(os.path.join(DATA, f"OPERA_L2_RTC-S1_{track}-*_{date}T*_{pol}.tif"))):
        with rasterio.open(f) as ds, rasterio.open(f.replace(f"_{pol}.tif", "_mask.tif")) as dm:
            v = ds.read(1).astype("float64"); m = dm.read(1)
            v[(m != 0) | ~np.isfinite(v) | (v <= 0)] = np.nan
            out = np.full((ny, nx), np.nan)
            reproject(v, out, src_transform=ds.transform, src_crs=ds.crs, src_nodata=np.nan,
                      dst_transform=dst_tr, dst_crs=dst_crs, dst_nodata=np.nan, resampling=Resampling.average)
            ok = np.isfinite(out); acc[ok] += out[ok]; cnt[ok] += 1
    return 10 * np.log10(np.where(cnt > 0, acc / np.maximum(cnt, 1), np.nan))

def stt(a, sel):
    a = a[sel & np.isfinite(a)]
    if a.size == 0: return dict(n_blocks=0)
    return dict(n_blocks=int(a.size), median=round(float(np.median(a)), 3), p10=round(float(np.percentile(a, 10)), 3), p90=round(float(np.percentile(a, 90)), 3))
def pct(a, sel, thr): a = a[sel & np.isfinite(a)]; return round(float((a <= thr).mean() * 100), 2) if a.size else None

res_all = {}
woody = B["pre_hv"] >= -14.0
for track, d1, d2, plat in (("T115", "20260713", "20260911", "S1D"), ("T166", "20260711", "20260909", "S1C")):
    vh1, vh2 = mosaic(track, d1, "VH"), mosaic(track, d2, "VH")
    vv1, vv2 = mosaic(track, d1, "VV"), mosaic(track, d2, "VV")
    dVH, dVV = vh2 - vh1, vv2 - vv1
    cov = float(np.isfinite(dVH[inside]).mean())
    r = dict(platform=plat, pre=d1, post=d2, perimeter_block_coverage=round(cov, 3),
             dVH_inside=stt(dVH, inside), dVH_outside=stt(dVH, outside_buf),
             dVV_inside=stt(dVV, inside), dVV_outside=stt(dVV, outside_buf),
             pct_inside_dVH_le_minus2dB=pct(dVH, inside, -2), pct_outside_dVH_le_minus2dB=pct(dVH, outside_buf, -2),
             pct_inside_dVV_le_minus2dB=pct(dVV, inside, -2),
             woody_dVH_inside=stt(dVH, inside & woody), woody_pct_inside_dVH_le_minus2dB=pct(dVH, inside & woody, -2))
    if r["dVH_inside"].get("n_blocks"):
        r["relative_median_dVH_inside_minus_outside"] = round(r["dVH_inside"]["median"] - r["dVH_outside"]["median"], 3)
    # same-block comparison with NISAR dHV
    both = inside & np.isfinite(dVH) & np.isfinite(B["dHV"])
    r["pearson_r_dVH_vs_NISAR_dHV_inside"] = round(float(np.corrcoef(dVH[both], B["dHV"][both])[0, 1]), 3) if both.sum() > 10 else None
    res_all[track] = r
    print(track, json.dumps(r))
    fg, ax = plt.subplots(figsize=(10, 7), dpi=110)
    im = ax.imshow(dVH, cmap="RdBu", vmin=-6, vmax=6, extent=[xmin, xmax, ymin, ymax], interpolation="nearest")
    ax.contour(np.flipud(inside.astype(float)), levels=[0.5], colors="k", linewidths=0.6, extent=[xmin, xmax, ymin, ymax])
    ax.set_title(f"OPERA RTC-S1 C-band dVH {track} {plat}: {d2} - {d1} (1 ha blocks)", fontsize=10)
    fg.colorbar(im, ax=ax, label="dB", shrink=0.8); fg.tight_layout()
    fg.savefig(os.path.join(HERE, f"dVH_S1_{track}.png")); plt.close(fg)

st_["opera_rtc_s1"] = dict(note="RTC-S1 gamma0 30 m bursts, mask==0 only, reprojected (average, linear) onto the NISAR 100 m block grid", tracks=res_all)
json.dump(st_, open(os.path.join(HERE, "stats.json"), "w"), indent=1, default=str)
print("done")
