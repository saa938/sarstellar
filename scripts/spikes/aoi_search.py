import requests, json, collections, statistics, sys
CMR="https://cmr.earthdata.nasa.gov/search/granules.umm_json"
AOIS = {
 "a_seattle":   (-122.40,47.50,-122.20,47.70),
 "b_rainier":   (-121.85,46.80,-121.70,46.90),
 "c_moseslake": (-119.40,47.05,-119.20,47.20),
 "d_pinebarrens":(-74.65,39.75,-74.45,39.90),
 "e_meadowlands":(-74.10,40.76,-74.02,40.83),
 "f_barnegat":  (-74.20,39.75,-74.05,39.95),
 "g_tulare":    (-119.65,36.00,-119.45,36.15),
 "h_bihar":     (84.60,26.20,84.80,26.40),
}
def search(short_names, bbox):
    out=[]; sa=None
    while True:
        p=[("short_name",s) for s in short_names]+[("bounding_box",",".join(map(str,bbox))),("page_size",2000)]
        h={"CMR-Search-After":sa} if sa else {}
        r=requests.get(CMR,params=p,headers=h,timeout=120); r.raise_for_status()
        items=r.json()["items"]; out+=items
        sa=r.headers.get("CMR-Search-After")
        if not items or not sa or len(items)<2000: break
    return out
def attrs(u):
    return {a["Name"]:",".join(a["Values"]) for a in u.get("AdditionalAttributes",[])}
def summarize(items):
    rows=[]
    for it in items:
        u=it["umm"]; a=attrs(u)
        size=[x.get("SizeInBytes") for x in u["DataGranule"]["ArchiveAndDistributionInformation"] if x["Name"].endswith(".h5")]
        rows.append(dict(ur=u["GranuleUR"], coll=u["CollectionReference"]["ShortName"],
            date=u["TemporalExtent"]["RangeDateTime"]["BeginningDateTime"][:10],
            dir=a.get("ASCENDING_DESCENDING","?")[0], track=a.get("TRACK_NUMBER"), frame=a.get("FRAME_NUMBER"),
            bw=a.get("RANGE_BANDWIDTH_CONCAT"), polA=a.get("FREQUENCY_A_POLARIZATION_CONCAT"), polB=a.get("FREQUENCY_B_POLARIZATION_CONCAT"),
            full=a.get("FULL_FRAME"), size=(size[0] if size else None)))
    return rows
res={}
mode=sys.argv[1] if len(sys.argv)>1 else "GCOV"
names={"GCOV":["NISAR_L2_GCOV_PROVISIONAL_V1","NISAR_L2_GCOV_V1"],
       "GUNW":["NISAR_L2_GUNW_PROVISIONAL_V1","NISAR_L2_GUNW_V1"]}[mode]
aois = AOIS if len(sys.argv)<3 else {k:AOIS[k] for k in sys.argv[2].split(",")}
for k,bb in aois.items():
    rows=summarize(search(names,bb)); res[k]=rows
    dates=sorted({r["date"] for r in rows})
    print(f"\n=== {k} {bb} granules={len(rows)} distinct_dates={len(dates)} first={dates[0] if dates else '-'} last={dates[-1] if dates else '-'}")
    print("  by tier:", dict(collections.Counter(r["coll"] for r in rows)))
    g=collections.defaultdict(list)
    for r in rows: g[(r["track"],r["frame"],r["dir"])].append(r)
    for key,rs in sorted(g.items(), key=lambda kv:-len(kv[1])):
        ds=sorted({r["date"] for r in rs}); sz=[r["size"] for r in rs if r["size"]]
        print(f"  T{key[0]} F{key[1]} {key[2]}: n={len(rs)} dates={len(ds)} {ds[0]}..{ds[-1]} bw={dict(collections.Counter(r['bw'] for r in rs))} polA={dict(collections.Counter(r['polA'] for r in rs))} polB={dict(collections.Counter(r['polB'] for r in rs))} full={dict(collections.Counter(r['full'] for r in rs))} sizeGB med={statistics.median(sz)/1e9 if sz else 0:.2f} min={min(sz)/1e9 if sz else 0:.2f} max={max(sz)/1e9 if sz else 0:.2f}")
        print("     dates:", " ".join(d[5:] if d.startswith("2026") else d for d in ds))
json.dump(res, open(f"aoi_{mode}.json","w"), indent=0)
