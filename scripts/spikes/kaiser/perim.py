import requests, json
base="https://services3.arcgis.com/T4QMspbfLg3qTGWY/arcgis/rest/services/{}/FeatureServer/0/query"
for svc in ["WFIGS_Interagency_Perimeters_YearToDate","WFIGS_Interagency_Perimeters"]:
    p={"where":"UPPER(poly_IncidentName) LIKE '%KAISER%'","outFields":"poly_IncidentName,attr_IncidentName,poly_GISAcres,attr_IncidentSize,attr_FireDiscoveryDateTime,poly_DateCurrent,attr_POOState,attr_POOCounty,attr_ContainmentDateTime,poly_PolygonDateTime,attr_UniqueFireIdentifier","outSR":4326,"f":"geojson"}
    r=requests.get(base.format(svc),params=p,timeout=120)
    print(svc, r.status_code)
    try: j=r.json()
    except Exception: print(r.text[:300]); continue
    if "error" in j: print(j["error"]); continue
    for ft in j.get("features",[]):
        pr=ft["properties"]; print("  ", {k:v for k,v in pr.items()})
    if j.get("features"):
        json.dump(j, open(f"kaiser/perim_{svc}.geojson","w"))
