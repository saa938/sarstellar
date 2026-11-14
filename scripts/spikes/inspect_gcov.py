import time, sys, json, h5py, numpy as np
sys.path.insert(0, r".")
from edl import https_fs, gcov_url
UR = sys.argv[1]; COLL = sys.argv[2]
t0=time.time(); fs=https_fs(); print(f"login {time.time()-t0:.2f}s")
url=gcov_url(UR, COLL)
t0=time.time()
f=fs.open(url, "rb", cache_type="blockcache", block_size=8*2**20)
try:
    h=h5py.File(f, "r", page_buf_size=16*2**20, rdcc_nbytes=4*2**20); pb="page_buf on"
except Exception as e:
    print("page_buf failed:", type(e).__name__, str(e)[:150])
    h=h5py.File(f, "r", rdcc_nbytes=4*2**20); pb="page_buf off"
t_open=time.time()-t0; print(f"open {t_open:.2f}s ({pb})")
try: print("file space strategy:", h.id.get_create_plist().get_file_space_strategy())
except Exception as e: print("fsstrategy n/a", e)
t0=time.time()
def visit(name, obj):
    if isinstance(obj, h5py.Dataset):
        a = {k:(v.decode() if isinstance(v,bytes) else v) for k,v in obj.attrs.items() if k in ("units","description","long_name","_FillValue","valid_min","valid_max","flag_values","flag_meanings","grid_mapping")}
        val = ""
        if obj.size<=4 and obj.dtype.kind in "SOiuf": 
            v=obj[()]; val = f" = {v.decode() if isinstance(v,bytes) else v}"
        print(f"  {name} {obj.shape} {obj.dtype} chunks={obj.chunks} comp={obj.compression}{val}")
        for k,v in a.items():
            s=str(v); print(f"      @{k}: {s[:300] if k!="description" or "ask" not in name else s}")
h["/science/LSAR/GCOV"].visititems(visit)
print(f"tree walk {time.time()-t0:.2f}s")
g=h["/science/LSAR/GCOV/grids/frequencyA"]
for k in g.attrs: print("frequencyA attr", k, g.attrs[k])
pr=h["/science/LSAR/identification"]
print("IDENT:", {k:(pr[k][()].decode() if isinstance(pr[k][()],bytes) else pr[k][()]) for k in pr if pr[k].size<=4})
hh=g["HHHH"]; ny,nx=hh.shape
y0,x0=ny//2-1000, nx//2-1000
t0=time.time(); w=hh[y0:y0+2000, x0:x0+2000]; t_read=time.time()-t0
t0=time.time(); w2=hh[y0+2000:y0+4000, x0:x0+2000]; t_read2=time.time()-t0
m=g["mask"][y0:y0+2000, x0:x0+2000]
w=w.astype("float64"); nanf=np.isnan(w).mean(); zf=(w==0).mean()
db=10*np.log10(np.where(w>0,w,np.nan))
print(f"HHHH window read {t_read:.2f}s (second adjacent window {t_read2:.2f}s); NaN frac {nanf:.3f}; zero frac {zf:.3f}; mean dB (of linear mean) {10*np.log10(np.nanmean(w)):.2f}; median dB {np.nanmedian(db):.2f}")
u,c=np.unique(m, return_counts=True); print("mask values in window:", dict(zip(u.tolist(), c.tolist())))
print("bytes fetched approx:", getattr(f, "cache", None) and len(getattr(f.cache,"_fetch_block_cached").cache_info()._asdict()) )
print(f.cache)
