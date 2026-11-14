# Re-stratify Edouard blocks by HAND (height above nearest drainage) instead of NLCD class alone.
import os, sys, json
import numpy as np, rasterio
import matplotlib; matplotlib.use("Agg")
import matplotlib.pyplot as plt
HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, os.path.dirname(HERE))
from spike_lib import to_grid, stats, pct

S = json.load(open(os.path.join(HERE, "stats.json"))); G = S["grid"]
B = dict(np.load(os.path.join(HERE, "blocks.npz")))
with rasterio.open(os.path.join(HERE, "ref_data", "hand_N30W095.tif")) as ds:
    h = ds.read(1).astype("float64")
    if ds.nodata is not None: h[h == ds.nodata] = np.nan
    hand = to_grid(h, ds.transform, ds.crs, G)
print("HAND block stats: median", np.nanmedian(hand), "pct<=2m", np.nanmean(hand <= 2) * 100)

wwet = B["f_wwet"]; ow = B["f_open"]
strata = {
    "floodplain_forest_HAND_le2m": (wwet >= 0.5) & (hand <= 2) & (ow < 0.2),
    "floodplain_forest_HAND_2to5m": (wwet >= 0.5) & (hand > 2) & (hand <= 5) & (ow < 0.2),
    "upland_forest_HAND_ge10m": B["upland"] & (hand >= 10),
}
ref_sel = strata["upland_forest_HAND_ge10m"]
layers = {"L_T12D_0826_0907": ["dHH", "dHV"], "L_T134A_0822_0903": ["dHH", "dHV"],
          "C_T136_0820_0913": ["dVV", "dVH"], "C_T136_0820_0901": ["dVV", "dVH"]}
res = {k: int(v.sum()) for k, v in strata.items()}
out = {"n_blocks": res, "ref": "relative = value minus median of upland_forest_HAND_ge10m"}
for pair, ks in layers.items():
    for k in ks:
        a = B[f"{pair}_{k}"]; ref = float(np.nanmedian(a[ref_sel])); rel = a - ref
        out[f"{pair}_{k}"] = {"upland_ref_median": round(ref, 2), **{
            s: dict(rel_median=stats(rel, m).get("median"), rel_p90=stats(rel, m).get("p90"),
                    pct_rel_ge3=pct(rel, m, ">=", 3), pct_raw_ge3=pct(a, m, ">=", 3)) for s, m in strata.items()}}
fp = strata["floodplain_forest_HAND_le2m"]
relHH = B["L_T12D_0826_0907_dHH"] - np.nanmedian(B["L_T12D_0826_0907_dHH"][ref_sel])
relVV = B["C_T136_0820_0913_dVV"] - np.nanmedian(B["C_T136_0820_0913_dVV"][ref_sel])
Lflag = fp & (relHH >= 3)
out["overlap_HAND_le2m"] = dict(L_relHH_ge3=int(Lflag.sum()), of_which_C_relVV_ge3=int((Lflag & (relVV >= 3)).sum()),
                                of_which_DSWx_inundated_veg_ge50=int((Lflag & (B["f_inv"] >= 0.5)).sum()),
                                of_which_DSWx_open_water_ge20=int((Lflag & (B["f_open"] >= 0.2)).sum()))
S["hand_stratified"] = out
json.dump(S, open(os.path.join(HERE, "stats.json"), "w"), indent=1, default=str)
print(json.dumps(out, indent=1))

ext = [G["xmin"], G["xmax"], G["ymin"], G["ymax"]]
fg, axs = plt.subplots(1, 3, figsize=(18, 6.5), dpi=100)
for ax, (t, a) in zip(axs, [("NISAR L-band dHH 2026-08-26 > 09-07 (T12 D)", relHH),
                            ("NISAR L-band dHV (same pair)", B["L_T12D_0826_0907_dHV"] - np.nanmedian(B["L_T12D_0826_0907_dHV"][ref_sel])),
                            ("Sentinel-1 C-band dVV 2026-08-20 > 09-13 (T136)", relVV)]):
    im = ax.imshow(a, cmap="RdBu_r", vmin=-6, vmax=6, extent=ext, interpolation="nearest")
    ax.contour(np.flipud(fp.astype(float)), levels=[0.5], colors="k", linewidths=0.35, extent=ext)
    ax.set_title(t, fontsize=10); ax.set_xticks([]); ax.set_yticks([])
fg.colorbar(im, ax=axs, label="dB relative to upland forest (red = brighter after storm)", shrink=0.8)
fg.suptitle("Edouard, Neches/Village Creek near Kountze TX; black = woody wetland with HAND <= 2 m", fontsize=11)
fg.savefig(os.path.join(HERE, "side_by_side_HAND.png")); plt.close(fg)
