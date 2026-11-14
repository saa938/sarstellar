import json, requests, collections, sys
sys.path.insert(0,".")
from shapely.geometry import shape
j=json.load(open("kaiser/perim_WFIGS_Interagency_Perimeters_YearToDate.geojson"))
ft=[f for f in j["features"] if f["properties"]["poly_IncidentName"]=="Kaiser Canyon"][0]
from shapely import make_valid
g=make_valid(shape(ft["geometry"])); print("perimeter type", g.geom_type, "valid", g.is_valid, "bounds", g.bounds, "area deg2", g.area)
minx,miny,maxx,maxy=g.bounds; mx=0.03; my=0.02
bbox=(round(minx-mx,4),round(miny-my,4),round(maxx+mx,4),round(maxy+my,4)); print("bbox with margin", bbox)
json.dump({"type":"FeatureCollection","features":[ft]}, open("kaiser/kaiser_perimeter.geojson","w"))
CMR="https://cmr.earthdata.nasa.gov/search/granules.umm_json"
p=[("short_name","NISAR_L2_GCOV_PROVISIONAL_V1"),("short_name","NISAR_L2_GCOV_V1"),("bounding_box",",".join(map(str,bbox))),("temporal","2026-06-01T00:00:00Z,2026-10-31T23:59:59Z"),("page_size",2000)]
items=requests.get(CMR,params=p,timeout=120).json()["items"]
rows=[]
from shapely.geometry import Polygon
for it in items:
    u=it["umm"]; a={x["Name"]:",".join(x["Values"]) for x in u["AdditionalAttributes"]}
    pts=u["SpatialExtent"]["HorizontalSpatialDomain"]["Geometry"]["GPolygons"][0]["Boundary"]["Points"]
    fp=Polygon([(q["Longitude"],q["Latitude"]) for q in pts])
    cov=fp.intersection(g).area/g.area
    rows.append(dict(ur=u["GranuleUR"],coll=u["CollectionReference"]["ShortName"],date=u["TemporalExtent"]["RangeDateTime"]["BeginningDateTime"][:10],
      track=a["TRACK_NUMBER"],frame=a["FRAME_NUMBER"],dir=a["ASCENDING_DESCENDING"][0],bw=a.get("RANGE_BANDWIDTH_CONCAT"),pol=a.get("FREQUENCY_A_POLARIZATION_CONCAT"),full=a.get("FULL_FRAME"),crid=u["GranuleUR"].split("_")[-4],cov=round(cov,3)))
for r in sorted(rows,key=lambda r:(r["track"],r["frame"],r["date"])): print(r["track"],r["frame"],r["dir"],r["date"],r["bw"],r["pol"],r["full"],r["crid"],"perimCov=",r["cov"],r["coll"][14:],r["ur"][-5:])
json.dump(dict(bbox=bbox,rows=rows),open("kaiser/candidates.json","w"),indent=0)
