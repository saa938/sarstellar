# Throwaway spike helpers shared by the edouard/ and clearcut/ spikes.
# Reads NISAR GCOV windows remotely, block-averages to 1 ha, and puts other rasters on the same grid.
import time, json
import numpy as np, h5py
from pyproj import Transformer

BLOCK = 10           # 10 x 10 px at 10 m = 1 ha
MIN_VALID_FRAC = 0.5


def _s(v):
    v = v[()] if hasattr(v, "shape") else v
    return v.decode() if isinstance(v, bytes) else (v.item() if hasattr(v, "item") else v)


def open_gcov(fs, url, retries):
    """Open a remote GCOV with block cache + retrying fetcher (ASF returned a 502 mid-read once)."""
    f = fs.open(url, "rb", cache_type="blockcache", block_size=8 * 2**20)
    orig = f.cache.fetcher

    def fetch(start, stop):
        for i in range(6):
            try:
                return orig(start, stop)
            except Exception as e:
                retries.append(f"{type(e).__name__}:{str(e)[:40]}")
                time.sleep(2 ** i)
        return orig(start, stop)

    f.cache.fetcher = fetch
    return f, h5py.File(f, "r", page_buf_size=16 * 2**20, rdcc_nbytes=4 * 2**20)


def read_window(fs, url, bbox, grid=None):
    """Read freqA HHHH/HVHV/mask for a lon/lat bbox snapped to a 100 m lattice.
    If grid is given (from a previous date), reuse its UTM window so dates align exactly."""
    retries = []
    t0 = time.time(); f, h = open_gcov(fs, url, retries); t_open = time.time() - t0
    idn = h["/science/LSAR/identification"]; g = h["/science/LSAR/GCOV/grids/frequencyA"]
    sw = h["/science/LSAR/GCOV/metadata/sourceData/swaths/frequencyA"]
    epsg = int(g["projection"][()]); dx = float(g["xCoordinateSpacing"][()]); dy = float(g["yCoordinateSpacing"][()])
    x = g["xCoordinates"][:]; y = g["yCoordinates"][:]
    if grid is None:
        tr = Transformer.from_crs(4326, epsg, always_xy=True)
        xs, ys = tr.transform([bbox[0], bbox[2], bbox[0], bbox[2]], [bbox[1], bbox[1], bbox[3], bbox[3]])
        X0 = np.floor(min(xs) / 100) * 100; X1 = np.ceil(max(xs) / 100) * 100
        Y0 = np.floor(min(ys) / 100) * 100; Y1 = np.ceil(max(ys) / 100) * 100
        grid = dict(epsg=epsg, xmin=float(X0), xmax=float(X1), ymin=float(Y0), ymax=float(Y1), res=BLOCK * dx)
    assert grid["epsg"] == epsg, f"EPSG differs between dates: {grid['epsg']} vs {epsg}"
    # first pixel whose centre lies inside [xmin, xmax)
    c0 = int(np.searchsorted(x, grid["xmin"] + dx / 2 - 1e-6)); c1 = c0 + int(round((grid["xmax"] - grid["xmin"]) / dx))
    r0 = int(np.searchsorted(-y, -(grid["ymax"] + dy / 2) - 1e-6)); r1 = r0 + int(round((grid["ymax"] - grid["ymin"]) / -dy))
    assert abs(x[c0] - (grid["xmin"] + dx / 2)) < 1e-3 and abs(y[r0] - (grid["ymax"] + dy / 2)) < 1e-3, "grid not on 10 m lattice"
    assert c0 >= 0 and r0 >= 0 and c1 <= len(x) and r1 <= len(y), "window exceeds frame"
    t0 = time.time()
    hh = g["HHHH"][r0:r1, c0:c1]; hv = g["HVHV"][r0:r1, c0:c1]; mk = g["mask"][r0:r1, c0:c1]
    t_read = time.time() - t0
    meta = dict(granule=_s(idn["granuleId"]), date=_s(idn["zeroDopplerStartTime"])[:19],
                track=_s(idn["trackNumber"]), frame=_s(idn["frameNumber"]), direction=_s(idn["orbitPassDirection"]),
                crid=_s(idn["compositeReleaseId"]), productVersion=_s(idn["productVersion"]),
                isMixedMode=_s(idn["isMixedMode"]), isFullFrame=_s(idn["isFullFrame"]),
                acquiredRangeBandwidth_freqA_Hz=float(sw["acquiredRangeBandwidth"][()]),
                processedRangeBandwidth_freqA_Hz=float(sw["processedRangeBandwidth"][()]),
                polarizations=[p.decode() for p in g["listOfPolarizations"][:]], epsg=epsg,
                window_shape=list(hh.shape), t_open_s=round(t_open, 2), t_read_3layers_s=round(t_read, 2),
                http_retries=retries)
    h.close(); f.close()
    return meta, dict(hh=hh, hv=hv, mk=mk), grid


def valid_px(d):
    return (d["mk"] >= 1) & (d["mk"] <= 254) & np.isfinite(d["hh"]) & np.isfinite(d["hv"]) & (d["hh"] > 0) & (d["hv"] > 0)


def block_lin(a, v):
    ny, nx = (a.shape[0] // BLOCK) * BLOCK, (a.shape[1] // BLOCK) * BLOCK
    a = np.where(v, a, 0.0)[:ny, :nx].astype("float64"); vv = v[:ny, :nx]
    s = a.reshape(ny // BLOCK, BLOCK, nx // BLOCK, BLOCK).sum(axis=(1, 3))
    n = vv.reshape(ny // BLOCK, BLOCK, nx // BLOCK, BLOCK).sum(axis=(1, 3))
    return np.where(n >= MIN_VALID_FRAC * BLOCK * BLOCK, s / np.maximum(n, 1), np.nan)


def db(x):
    return 10 * np.log10(x)


def nisar_pair(fs, url_pre, url_post, bbox):
    m1, d1, grid = read_window(fs, url_pre, bbox)
    m2, d2, _ = read_window(fs, url_post, bbox, grid)
    v = valid_px(d1) & valid_px(d2)
    out = {f"{t}_{p}": db(block_lin(d[p], v)) for t, d in (("pre", d1), ("post", d2)) for p in ("hh", "hv")}
    grid["shape"] = list(out["pre_hh"].shape)
    return dict(pre=m1, post=m2, valid_px_frac=round(float(v.mean()), 4)), out, grid


def grid_transform(grid):
    from rasterio.transform import from_origin
    return from_origin(grid["xmin"], grid["ymax"], grid["res"], grid["res"])


def to_grid(src_arr, src_transform, src_crs, grid, resampling="average"):
    """Reproject a float array (NaN = nodata) onto the 1 ha block grid."""
    from rasterio.warp import reproject, Resampling
    out = np.full(tuple(grid["shape"]), np.nan)
    reproject(src_arr.astype("float64"), out, src_transform=src_transform, src_crs=src_crs, src_nodata=np.nan,
              dst_transform=grid_transform(grid), dst_crs=f"EPSG:{grid['epsg']}", dst_nodata=np.nan,
              resampling=getattr(Resampling, resampling))
    return out


def rtc_mosaic(files, grid):
    """Mosaic OPERA RTC-S1 burst GeoTIFFs (linear gamma0) onto the grid; mask!=0 dropped. Returns dB."""
    import rasterio
    acc = np.zeros(tuple(grid["shape"])); cnt = np.zeros(tuple(grid["shape"]))
    for f in files:
        mf = f.rsplit("_", 1)[0] + "_mask.tif"
        with rasterio.open(f) as ds, rasterio.open(mf) as dm:
            v = ds.read(1).astype("float64"); m = dm.read(1)
            v[(m != 0) | ~np.isfinite(v) | (v <= 0)] = np.nan
            o = to_grid(v, ds.transform, ds.crs, grid)
        ok = np.isfinite(o); acc[ok] += o[ok]; cnt[ok] += 1
    return db(np.where(cnt > 0, acc / np.maximum(cnt, 1), np.nan))


def stats(a, sel):
    a = a[sel & np.isfinite(a)]
    if a.size == 0:
        return dict(n=0)
    return dict(n=int(a.size), median=round(float(np.median(a)), 2), p10=round(float(np.percentile(a, 10)), 2),
                p90=round(float(np.percentile(a, 90)), 2))


def pct(a, sel, op, thr):
    a = a[sel & np.isfinite(a)]
    if a.size == 0:
        return None
    return round(float(((a >= thr) if op == ">=" else (a <= thr)).mean() * 100), 2)


def lonlat_corners(grid):
    tr = Transformer.from_crs(grid["epsg"], 4326, always_xy=True)
    pts = dict(upper_left=(grid["xmin"], grid["ymax"]), upper_right=(grid["xmax"], grid["ymax"]),
               lower_right=(grid["xmax"], grid["ymin"]), lower_left=(grid["xmin"], grid["ymin"]))
    return {k: [round(c, 6) for c in tr.transform(*xy)] for k, xy in pts.items()}
