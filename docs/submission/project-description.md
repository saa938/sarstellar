# SARstellar: Radar Change Comparison

Submission draft, November 15, 2026. [Application](https://www.sarstellar.earth/). [Public six-slide demo](https://www.sarstellar.earth/demo/) (publication pending). [Editable presentation](sarstellar-presentation-public.pptx). The source repository remains private by the user's choice. The approved Light-default release is live; the final selected-area workflow and public slide viewer still need production verification.

## Project summary

SARstellar compares NISAR L-band and Sentinel-1 C-band backscatter changes on a one-hectare grid. Open one of three saved examples or draw a US box up to 20 km per side. Filter the detected areas, adjust layer opacity, compare before/after images and inspect each sensor's relative change. Select an area to review the measurements, timing, possible cause and uncertainty. Cause labels are rule-based hypotheses. A completed live analysis offers GeoTIFF, CSV and reproducible-notebook exports.

The interface separates Map, Benchmark and Methods. It opens with the user-selected Light appearance and retains a Charcoal option. Detection categories mean NISAR only, both sensors or Sentinel-1 only; they describe the pipeline's detections rather than verified absence in the other sensor.

We also tested whether combining the radars improves detection on states excluded from fitting. We attempted 254 sites, processed 242 and retained 224 with comparable radar and reference data. We trained on 164 sites and evaluated 60 across 12 held-out states. The primary comparison uses one pair per radar on 2,173,521 common one-hectare blocks. The saved output lists 12 failed reads and 18 processed sites excluded from comparison. [Benchmark and methods notes](../../web/public/scorecard.json).

## Measured result

The primary unsupervised fusion comparisons show no demonstrated gain at the 95% interval level. We selected the single-sensor comparator and fusion method using training states, then evaluated their AUPRC difference on held-out sites:

| Reference category | Fusion − selected single sensor, AUPRC | Site-bootstrap 95% interval |
|---|---:|---:|
| Forest loss | −0.073 | [−0.157, −0.009] |
| Burn | +0.037 | [−0.020, +0.089] |
| Open-water flood | −0.088 | [−0.151, +0.001] |
| Cultivated-land proxy | −0.022 | [−0.077, +0.060] |

Forest-loss fusion performed worse than the selected single radar. In a separate supervised comparison against equally trained single-sensor controls, logistic fusion improved the cultivated-land proxy by +0.048 AUPRC, interval [+0.018, +0.101]. CDL labels cultivated land, so this does not establish crop-change detection accuracy. We attempted 500 site-bootstrap draws per comparison and report valid-draw counts in the JSON. [Measured outputs](../../web/public/scorecard.json).

## NASA and partner data

| Source | Use in SARstellar |
|---|---|
| [NASA/ISRO NISAR](https://science.nasa.gov/mission/nisar/), accessed through ASF/Earthdata | Calibrated L-band GCOV: `NISAR_L2_GCOV_PROVISIONAL_V1` and `NISAR_L2_GCOV_V1`; exclude BETA and incompatible stacks. |
| [NASA JPL OPERA](https://www.jpl.nasa.gov/go/opera/) | RTC-S1 VV/VH comparison radar; DIST-ALERT-HLS optical vegetation-loss reference; DSWx-HLS and DSWx-S1 water references. |
| [NIFC WFIGS](https://data-nifc.opendata.arcgis.com/) and [NASA FIRMS](https://firms.modaps.eosdis.nasa.gov/) | Mapped fire perimeters for scoring and cause evidence; optional active-fire context when available. |
| [USDA NASS CDL](https://www.nass.usda.gov/Research_and_Science/Cropland/SARS1a.php) and [USGS/MRLC NLCD](https://www.mrlc.gov/) | Cultivated-land reference and land-cover context. |
| [CDC/ATSDR SVI 2022](https://www.atsdr.cdc.gov/place-health/php/svi/index.html) | Census-tract social-vulnerability context, rather than an estimate of people affected. |
| [Open-Meteo historical weather](https://open-meteo.com/en/docs/historical-weather-api) | Optional minimum-temperature and rain context. |
| [Esri World Imagery](https://www.arcgis.com/home/item.html?id=10df2279f9684e4a9f6a7f08febac2a9) | Attributed basemap under data-rendered radar overlays. |

## Scientific limits

- We chose event sites where reference positives existed. Results describe this selected cohort, not national change prevalence or universal sensor superiority.
- The held-out set has only three flood sites. DSWx-S1 shares Sentinel-1 observations, so that flood reference does not provide sensor-independent validation.
- Radar passes can differ by several days. Some demonstration stories use more NISAR dates than Sentinel-1 dates; their area totals do not establish an accuracy advantage. [Story provenance](../../web/public/stories/provenance.json).
- Cause labels remain hypotheses from rules, not validated multiclass cause predictions. Terrain-dependent rules lack a terrain model. The “NISAR at 30 m” sampling comparison does not isolate wavelength from timing, geometry or processing.
- Default detection uses BH-FDR q = 0.05 and at least 2 dB relative change. This setting is not a guarantee of 95% accuracy for an individual area. Users should verify findings against independent evidence before operational decisions.

## AI-use disclosure

We used Claude Code and OpenAI Codex for implementation, debugging, tests and draft submission text. The optional runtime LLM rewrites supplied evidence into plain language; the software retains the structured rule-based class and confidence. The saved stories use deterministic text templates because the Anthropic API lacked credits during generation. We used logistic models for the benchmark's supervised fusion and matched single-sensor controls. We have not shipped the stretch learned cause classifier. The radar overlays come from data rendering; we generated no AI images for this submission.

## Reproduction and credits

The private repository contains the Python engine, Modal jobs and React/MapLibre interface. Public readers can inspect the [measured benchmark](https://www.sarstellar.earth/scorecard.json), [story provenance](https://www.sarstellar.earth/stories/provenance.json) and [methods](https://www.sarstellar.earth/#/about) without repository access. The repository's [README](../../README.md) gives setup and rebuild commands for authorized collaborators. Core methods include the Conradsen change test, Benjamini–Hochberg FDR, Fisher/Bonferroni fusion and site-level paired bootstrap. The code carries [Apache 2.0](../../LICENSE) licensing; that license does not make the repository public. Data and basemap providers retain their own terms and attribution requirements.
