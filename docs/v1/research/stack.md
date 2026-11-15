# Stack/architecture brief (from `stack` agent, 2026-11-14). [V]=verified live, [I]=inference

## Architecture
Vercel SPA (Vite+React+TS, MapLibre) --POST /jobs {bbox}--> Modal asgi_app "api" (one FastAPI app, min_containers=1)
  poll GET /jobs/{id} every 1 s; api does run_job.spawn() -> job_id
  run_job: CMR search (earthaccess) -> read_window.map(~12 GCOV URLs) [cloud="aws", region="us-west"]
           -> ancillary.spawn(): DSWx-S1 / RTC-S1 COG windows, S2/HLS, SVI
           -> numpy change -> PNG + lon/lat corners, per-pixel cube JSON
           -> Claude phrases rule-engine output
  status + small results in modal.Dict; GeoTIFF/CSV/.ipynb exports in Volume v2
Showcase sites: same pipeline offline, outputs committed to frontend /public; demo never calls Modal.

## Modal
- Web fn 150 s hard timeout, 303 fallback breaks with CORS -> spawn + poll. [V]
- @app.function(cloud="aws", region=..., min_containers=, scaledown_window 2s-20min, enable_memory_snapshot=True). [V]
- Region pin: documented options stop at "us-west"; finer = sales; narrow regions 1.75x; Starter has region selection. region="us-west-2" unconfirmed -> try it. [V/I]
- NISAR direct S3 only from us-west-2 (Access Denied elsewhere). HTTPS+EDL baseline; S3 fast path w/ fallback. S3 creds expire 1 h -> cache in Dict. earthaccess.get_s3_credentials(endpoint="https://nisar.asf.earthdatacloud.nasa.gov/s3credentials") (daac='ASF' errors). [V]
- HDF5: fsspec cache_type="blockcache", block_size=8MB; h5py page_buf_size=16MB, rdcc_nbytes=4MB. Open datatree 52 s -> ~2 s. [V]
- Dict: 100 MiB cap (<5 MiB recommended), 7-day idle expiry. Volume v2 (version=2): writers commit(), readers reload(). [V]
- Fan-out: read_window.map(urls, kwargs={"bbox": b}, return_exceptions=True). I/O >2 MiB routed via us-east -> return downsampled arrays. [V]
- Cron: schedule=modal.Cron("0 */6 * * *"); Starter 5 crons, limited web fns -> one asgi_app; 100 concurrent containers. [V]
- Req body up to 4 GiB, responses unlimited, 200 req/s per fn. [V]

## Tiles
Skip TiTiler. Render each date + change map as PNG; MapLibre `image` source with 4 corners. Reproject UTM -> 4326/3857 w/ rioxarray. Cap ~2048 px/side. titiler.core 2.4.0 later only if zoomable full-res needed.

## Frontend [V versions]
- maplibre-gl 6.18.0 via React ref (skip react-map-gl; compare needs 2 maps)
- @maplibre/maplibre-gl-compare 0.5.0
- @watergis/maplibre-gl-terradraw 1.17.0 (rectangle)
- recharts 3.10.1
- Vite 8.3.8, React 19.3.1, TypeScript pinned 5.9.3 (7.x native compiler new)
- Basemaps no key: OpenFreeMap https://tiles.openfreemap.org/styles/liberty ; Esri World_Imagery /tile/{z}/{y}/{x} ; EOX s2cloudless-2024_3857
- GIBS NISAR layer (CORS *): https://gibs.earthdata.nasa.gov/wmts/epsg3857/best/NISAR_L2_Geocoded_Polarimetric_Covariance/default/{YYYY-MM-DD}/GoogleMapsCompatible_Level13/{z}/{y}/{x}.png  (z<=13; time 2025-10-29..2026-11-12, gap 07-27..08-10). Orbit tracks MVT: OrbitTracks_NISAR_Ascending / _Descending (z<=6). Capabilities saved: scratchpad\gibs3857.xml

## Ancillary (CMR live) [V]
- NISAR_L2_GCOV_V1 = C3622241360-ASF (validated from 2026-10-21); PROVISIONAL + BETA collections exist
- OPERA_L3_DIST-ALERT-S1_V1 (ASF; STAC OPERA_L3_DIST-ALERT-S1_V1_1) -- but no Jun-Nov 2026 data per data-spike
- OPERA_L3_DSWX-S1_V1 (POCLOUD)
- OPERA_L2_RTC-S1_V1 (ASF)
- HLSS30/HLSL30 v2.0 (LPCLOUD; STAC cmr.earthdata.nasa.gov/stac/LPCLOUD, HLSS30_2.0)
- Sentinel-2: https://earth-search.aws.element84.com/v1 collection sentinel-2-l2a (public)
- Read ancillary COGs over HTTPS+EDL (different DAAC S3 endpoints).
- SVI: https://onemap.cdc.gov/onemapservices/rest/services/SVI/CDC_ATSDR_Social_Vulnerability_Index_2022_USA/FeatureServer/2/query f=geojson + envelope bbox; RPL_THEMES; 2000/page; -999 missing.

## Notebook
One pure-Python core.py imported by Modal + notebook. nbformat 5.11.1 (v4.new_notebook/new_code_cell): params cell (bbox, granule URLs, dates) then core calls. Write to Volume, serve.

## Hosting
Static SPA on Vercel/CF Pages w/ VITE_API_URL. Judging: min_containers=1 on api + run_job, scaledown_window=1200.

## Latency (warm, inferred)
CMR 0.5-2 s; 12 parallel window reads 3-8 s HTTPS / 2-4 s S3; change+PNG ~1 s; first overlay ~6-12 s; Claude +2-5 s streamed; cold +5-15 s; showcase <1 s.
