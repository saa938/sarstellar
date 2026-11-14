import requests, json, re, collections
bbox="-119.3705,48.0531,-118.7196,48.3605"
CMR="https://cmr.earthdata.nasa.gov/search/granules.umm_json"
items=[]; sa=None
while True:
    h={"CMR-Search-After":sa} if sa else {}
    r=requests.get(CMR,params={"collection_concept_id":"C2777436413-ASF","bounding_box":bbox,"temporal":"2026-06-15T00:00:00Z,2026-09-30T23:59:59Z","page_size":2000},headers=h,timeout=120)
    items+=r.json()["items"]; sa=r.headers.get("CMR-Search-After")
    if not sa or len(r.json()["items"])<2000: break
rows=[]
for it in items:
    u=it["umm"]; ur=u["GranuleUR"]
    m=re.match(r"OPERA_L2_RTC-S1_(T\d+-\d+-IW\d)_(\d{8})T(\d{6})Z_(\d{8}T\d{6})Z_(S1[A-D])_30_(v[\d.]+)",ur)
    urls=[x["URL"] for x in u.get("RelatedUrls",[]) if x["URL"].startswith("https") and x["URL"].endswith((".tif",))]
    rows.append(dict(ur=ur,burst=m.group(1),date=m.group(2),plat=m.group(5),ver=m.group(6),prod=m.group(4),urls=urls))
print("granules", len(rows))
g=collections.defaultdict(lambda: collections.defaultdict(set))
for r in rows: g[r["burst"].split("-")[0]][r["date"]+"_"+r["plat"]].add(r["burst"])
for trk,d in sorted(g.items()):
    print(trk, {k:len(v) for k,v in sorted(d.items())})
json.dump(rows,open("kaiser/rtc_rows.json","w"),indent=0)
print(rows[0]["urls"])
