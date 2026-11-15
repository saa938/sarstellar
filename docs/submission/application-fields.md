# Application fields

Prepared November 15, 2026. Copy the text beneath each field heading; preparation notes are outside the paste-ready fields.

## Project Name

SARstellar

## Summary

SARstellar is an interactive workspace for comparing surface change detected by NASA/ISRO NISAR L-band and Sentinel-1 C-band radar. Open three real examples or draw a US analysis area, compare before/after imagery, inspect each sensor's detections, and export measurements. Each selected area separates observed radar change, acquisition timing, provisional cause hypotheses, and independent checks needed to verify them. A reproducible benchmark uses one before-and-after pair per radar, with 224 eligible sites and 60 evaluation sites across 12 held-out states. Primary unsupervised fusion showed no demonstrated improvement over the training-selected single radar; the application reports that result alongside uncertainty, failed reads, and exclusions. SARstellar helps researchers and resource managers compare evidence without treating radar detections as confirmed events or sensor agreement as proof of accuracy.

## Project URL

https://www.sarstellar.earth/

## Demo URL

https://www.sarstellar.earth/demo/

## Project Details

SARstellar helps researchers, resource managers, and curious members of the public investigate surface change using two radar wavelengths. Its central question is practical: what does NISAR detect, what does Sentinel-1 detect, and what evidence supports an interpretation? The current live service supports US analysis boxes up to 20 km per side. Three saved examples provide immediate access to actual pipeline outputs without waiting for a new analysis.

The Python engine discovers calibrated NISAR GCOV and NASA JPL OPERA RTC-S1 acquisitions through NASA Earthdata. It reads geographic windows rather than downloading entire radar scenes, places observations on a shared one-hectare grid, and measures relative backscatter change. Statistical change tests, false-discovery-rate control, and a minimum 2 dB effect threshold identify candidate blocks. Adjacent detections form areas of at least three hectares. These are radar detections, not verified event boundaries.

The map distinguishes NISAR-only, both-sensor, and Sentinel-1-only detections. Before/after swipe and synchronized radar views help users compare observations. Class filters and an acquisition timeline make individual findings easier to locate. Selecting an area answers four questions: what changed, when it was observed, why a cause hypothesis was suggested, and what to check next. Rule-based labels remain provisional. The first flagged acquisition is an observation date, not a confirmed event date; detector p-values and heuristic confidence labels are not calibrated probabilities that a cause is correct.

Measurements, uncertainty intervals, backscatter series, and supporting context remain available beneath those answers. Context can include land cover, fire perimeters, and optional weather or active-fire observations. Census-tract social vulnerability is presented as context, not an estimate of affected people. Completed live analyses offer GeoTIFF, CSV, and notebooks that embed the engine source and its checksum. A React/MapLibre interface serves the workspace, with analysis jobs executed on Modal.

We also evaluated whether combining the radars improves detection. Of 254 attempted sites, 242 processed successfully and 224 had comparable radar and reference data. We used 164 training sites and evaluated 60 sites across 12 held-out states. Primary comparisons use one before-and-after pair per radar on 2,173,521 common blocks. Comparator selection uses training states; paired site-bootstrap intervals use 500 draws. The published report retains all 12 failed reads and 18 exclusions.

Primary unsupervised fusion showed no demonstrated gain over the selected single radar for any reference category; forest-loss fusion performed worse. A separate supervised comparison improved a cultivated-land proxy, which does not establish improved crop-change detection. Only three held-out flood sites were eligible, and a Sentinel-1-derived water reference limits independent flood validation. Selected event sites do not establish national prevalence. Some demonstration examples contain unequal acquisition counts, so their detected-area totals are not sensor-accuracy comparisons. SARstellar's contribution is an inspectable comparison and a reproducible, candid evaluation, including results that do not support a fusion advantage.

## SI use: paste-ready disclosure

We used Claude Code and OpenAI Codex to assist with software implementation, debugging, tests, and written content. An optional runtime Anthropic language model can rewrite supplied numerical evidence into plain language; it does not determine the structured detection, rule-based class, or confidence label. Saved example explanations use deterministic templates because the Anthropic API was unavailable during their generation. Benchmark logistic models provide a separate supervised fusion comparison with equally trained single-sensor controls. No generative-AI photos, audio, or video were created for this submission. Radar overlays and charts are rendered from data; the satellite basemap is credited to its imagery providers.

## NASA Data: link text and URLs

Each row supplies a link-text / URL pair for the form. Product identifiers describe the actual collections queried. FIRMS is optional context, not a required input or evidence guaranteed to be present in the saved examples.

| Link text | Full URL | Actual use |
|---|---|---|
| NASA/ISRO NISAR | https://science.nasa.gov/mission/nisar/ | L-band GCOV; collections `NISAR_L2_GCOV_PROVISIONAL_V1` and `NISAR_L2_GCOV_V1`. BETA products are excluded. |
| NASA JPL OPERA RTC-S1 | https://www.jpl.nasa.gov/go/opera/products/ | Terrain-corrected Sentinel-1 VV/VH radar; `OPERA_L2_RTC-S1_V1`. |
| NASA JPL OPERA DIST-ALERT-HLS | https://www.jpl.nasa.gov/go/opera/products/ | Optical vegetation-disturbance reference for the benchmark; `OPERA_L3_DIST-ALERT-HLS_V1`. |
| NASA JPL OPERA DSWx-S1 and DSWx-HLS | https://www.jpl.nasa.gov/go/opera/products/ | Before/after water-reference masks; `OPERA_L3_DSWX-S1_V1` with `OPERA_L3_DSWX-HLS_V1` fallback. DSWx-S1 is not independent of Sentinel-1. |
| NASA Earthdata Common Metadata Repository | https://cmr.earthdata.nasa.gov/ | Programmatic granule discovery for radar and OPERA references. |
| NASA Earthdata Login | https://urs.earthdata.nasa.gov/ | Authentication for protected Earthdata reads. |
| Alaska Satellite Facility DAAC | https://asf.alaska.edu/ | NASA radar data archive/access infrastructure. |
| NASA FIRMS | https://firms.modaps.eosdis.nasa.gov/ | Optional VIIRS active-fire context when credentials and observations are available; not a benchmark ground-truth label. |

## Other data and resources: link text and URLs

| Link text | Full URL | Actual use |
|---|---|---|
| NIFC Open Data / WFIGS | https://data-nifc.opendata.arcgis.com/ | Fire perimeters for benchmark masks and optional cause context. |
| USDA NASS Cropland Data Layer | https://www.nass.usda.gov/research-and-science/cropland/sars1a | Cultivated-land proxy and site selection through CropScape. CDL does not label confirmed crop change. |
| USGS/MRLC National Land Cover Database | https://www.mrlc.gov/ | NLCD 2021 land-cover context and detector strata when available; scene-wide fallback if unavailable. |
| CDC/ATSDR Social Vulnerability Index | https://www.atsdr.cdc.gov/place-health/php/svi/index.html | Optional 2022 census-tract context; no affected-population estimate. |
| US Census Bureau TIGERweb | https://tigerweb.geo.census.gov/ | State boundaries for benchmark-site geography. |
| Open-Meteo Historical Weather API | https://open-meteo.com/en/docs/historical-weather-api | Optional minimum-temperature and rainfall context. This implementation does not use IMERG rainfall. |
| Esri World Imagery | https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer | Satellite basemap, with Esri and imagery-provider attribution retained in the app. |
| Python | https://www.python.org/ | Analysis engine and batch jobs. |
| NumPy | https://numpy.org/ | Numerical arrays and calculations. |
| SciPy | https://scipy.org/ | Statistical tests and numerical methods. |
| h5py | https://www.h5py.org/ | NISAR HDF5 reads. |
| fsspec | https://filesystem-spec.readthedocs.io/ | Windowed remote-file access. |
| aiohttp | https://docs.aiohttp.org/ | HTTP transport for remote-file access. |
| earthaccess | https://earthaccess.readthedocs.io/ | Earthdata authentication and HTTPS sessions. |
| pyproj | https://pyproj4.github.io/pyproj/ | Coordinate transforms. |
| Rasterio | https://rasterio.readthedocs.io/ | Raster sampling and GeoTIFF exports. |
| Shapely | https://shapely.readthedocs.io/ | Geographic geometry operations. |
| Pillow | https://pillow.readthedocs.io/ | Data-rendered PNG overlays. |
| Requests | https://requests.readthedocs.io/ | Data-service HTTP queries. |
| pandas | https://pandas.pydata.org/ | Benchmark block tables and aggregation. |
| Apache Arrow / PyArrow | https://arrow.apache.org/docs/python/ | Parquet checkpoint and block-table storage. |
| scikit-learn | https://scikit-learn.org/ | Logistic fusion and matched supervised single-sensor controls. |
| Jupyter nbformat | https://nbformat.readthedocs.io/ | Reproducible notebook export. |
| Modal | https://modal.com/ | Hosted analysis API, parallel batch execution, and persistent checkpoints. |
| FastAPI | https://fastapi.tiangolo.com/ | Analysis API endpoints. |
| HTTPX | https://www.python-httpx.org/ | API testing/client support. |
| React | https://react.dev/ | Interactive application interface. |
| React DOM | https://react.dev/reference/react-dom | Browser rendering. |
| React Is | https://www.npmjs.com/package/react-is | React compatibility support for the chart stack. |
| MapLibre GL JS | https://maplibre.org/maplibre-gl-js/docs/ | Interactive maps and data layers. |
| MapLibre GL Compare | https://github.com/maplibre/maplibre-gl-compare | Before/after swipe. |
| Terra Draw | https://terradraw.io/ | Drawing analysis areas through the MapLibre drawing integration. |
| Terra Draw MapLibre GL Adapter | https://www.npmjs.com/package/terra-draw-maplibre-gl-adapter | Connects drawn shapes to MapLibre. |
| MapLibre GL Terra Draw | https://github.com/watergis/maplibre-gl-terradraw | Map drawing integration. |
| events | https://www.npmjs.com/package/events | Browser event-emitter compatibility for the comparison integration. |
| Recharts | https://recharts.org/ | Measurement time-series charts. |
| TypeScript | https://www.typescriptlang.org/ | Typed frontend implementation. |
| Vite | https://vite.dev/ | Frontend development and production build. |
| Vitest | https://vitest.dev/ | Frontend checks. |
| Testing Library | https://testing-library.com/ | Interface behavior tests. |
| Happy DOM | https://github.com/capricorn86/happy-dom | DOM test environment. |
| pytest | https://docs.pytest.org/ | Python checks. |
| Ruff | https://docs.astral.sh/ruff/ | Python lint checks. |
| Vercel | https://vercel.com/ | Public website hosting. |
| Claude Code | https://claude.com/product/claude-code | AI-assisted code, tests, debugging, and draft text. |
| OpenAI Codex | https://openai.com/codex/ | AI-assisted code, tests, debugging, and draft text. |
| Anthropic Python SDK | https://github.com/anthropics/anthropic-sdk-python | Optional runtime evidence-to-text rewrite; deterministic fallback. |

## Preparation notes — do not paste as application fields

- **Summary validation:** 123 whitespace-separated words; 920 characters including spaces. Project Details: 454 words. The summary satisfies 50–200 words and fewer than 1,500 characters. Revalidate after editing.
- **SI selection:** If the form offers corresponding choices, select the equivalents of code and written content. No exact option names were supplied. Do not select generated photos/audio/video on the basis of data-rendered maps or charts.
- **Private source:** The user explicitly chose to keep the repository private. The public website is the Project URL; these fields do not claim publicly available source code. The challenge's desired open-source outcome remains a submission-readiness gap while the repository is private. Do not change repository visibility without a new instruction.
- **Demo readiness:** The Demo URL is a reserved destination for the six-slide deck. Confirm that it loads publicly before submitting; this document does not assert that the deck is already hosted.
- **Scope:** Live analysis and this benchmark cover selected US locations. Do not describe the delivered service as global or the benchmark as a representative national survey.
- **Resource scope:** Data-source rows reflect implemented readers and measured-benchmark inputs; optional context is labeled. LightGBM and the learned cause classifier are not shipped features. No external photographs, audio tracks, video clips, or generated media are claimed here.
- **Evidence:** Counts and statistical conclusions were checked against `README.md`, `web/public/scorecard.json`, and the submission project description; collection names and optional behavior against `core/sarstellar/search.py`, `refs.py`, `refs_scoring.py`, and `explain.py`. Software credits follow `pyproject.toml` and `web/package.json`.
