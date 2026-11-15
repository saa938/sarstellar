# SARstellar: submission fields (paste-ready)

Prepared 2026-11-15. Every number below is measured by our pipeline (see `web/public/proof.json`,
`docs/v2/`). No team member names, faces or voices anywhere (minors on the team).

---

## Project Name

SARstellar

## High-Level Summary

Every kind of change on Earth's surface moves in its own way through NISAR's radar. SARstellar turns
that into something anyone can watch: every hectare of a place becomes a dot on an HH-versus-HV
"dance floor", and NISAR's passes play like beats. A forest that is cut falls, rice standing in
water bounces, a wheat field waltzes, a flood makes the land vanish, an ice sheet changes its face
through the summer. We read every NISAR pass over nine places (177 granules, about 10,900 km2) and
trained a model on 2.46 million reference hectares across 242 US sites, measured on 12 states it
never saw. It answers the challenge's question with numbers: forest loss is an HV move (HV alone
finds it 6 times better than HH alone), and NISAR's forest-loss alerts were 7.8 times more often
real than Sentinel-1's. Draw a box anywhere on Earth and the site reads every NISAR pass there live.

## Demo (30 seconds)

https://www.sarstellar.earth/demo/sarstellar-demo.mp4

## Final Project

https://www.sarstellar.earth/

## Project Details

**What it does.** SARstellar is an interactive site that makes NISAR's L-band radar readable by
anyone. NISAR listens to the ground in two ways: HH, which hears surfaces and bounces, and HV, which
hears volume (leaves, branches, crop canopies). We place every hectare of a place on a plane of HH
against HV. That plane is a map of surface types: open water bottom-left, bare soil, crops, forest
top-right, double bounce (flooded forest, cities, rice paddies) far right. Press play and the dots
move pass by pass. Each kind of change makes its own move:

- The Fall: a forest is cut, HV drops several decibels in one pass.
- The Scorch: a wildfire, like the Fall over wide patches; grass fires barely register at L-band.
- The Bounce: water under plants; the pulse bounces off water and trunks, HH jumps, HV holds.
- The Vanish: open water mirrors the pulse away; both channels go dark.
- The Waltz: a crop grows (HV climbs) and is harvested (HV falls).
- The Melt: an ice sheet's surface changes through its melt season (HH only over ice).

**What we found in NISAR's data.**

- Punjab, India: wheat waltzes in HV (up about 3 dB from November to February, back down at the
  April harvest) while rice bounces in HH (up about 8 dB from July to September as stalks stand in
  water; the HH-HV gap widens from 8 to 12 dB). Same fields, two crops, two polarizations.
- Village Creek, Texas: on the NISAR pass during Tropical Storm Edouard, 3,572 forested hectares
  jumped 3 dB or more in HH while HV held still: floodwater under the canopy, invisible to optical
  satellites. Twelve days later only 266 still bounced.
- Central Iowa: HV climbed about 8 dB from bare fields in May to peak canopy in September, then fell
  4 dB in one pass at harvest. Frozen ground darkened the fields in January.
- Sylhet haor basin, Bangladesh: up to 25,200 hectares of open water came and went with the monsoon.
  One pass shows wind-roughened water lighting up, a known radar blind spot we show rather than hide.
- Rondonia, Brazil and Morton, Washington: forests falling in the dry season and in clearcuts.
- Greenland: across the ice sheet's melt zone, HH swung 4 to 5 dB at the height of summer and
  settled by October.

**How we know (measured, with honest limits).** We trained a gradient-boosted model on the change in
HH and HV between two NISAR passes at 2.46 million reference hectares (242 US sites with independent
labels: NASA OPERA DIST-ALERT-HLS forest loss, NIFC fire perimeters, OPERA DSWx water, USDA cropland),
training on some states and testing on 12 others. On those unseen states: the Waltz is recognized
4.6 times better than chance (AUPRC 0.44 against a 0.10 base rate) and the Fall 45 times better than
chance (AUPRC 0.11 against 0.0025, catching 54% of forest loss). When the site says a hectare
moved, it really changed 66% of the time (19% by chance). Retraining with one polarization at a time
answers "which polarization highlights which change": forest loss is carried by HV (AUPRC 0.26 with
HV alone, 0.04 with HH alone). Trained only on US sites, the model ranks forest loss in Rondonia,
Brazil 32 times better than chance against NASA's optical alerts. On 37 forest-loss sites, NISAR's
L-band alerts were 7.8 times more often real than Sentinel-1's C-band at the same detection rate.
Open-water floods were not separable from two L-band passes at our reference flood sites, and the
Scorch is weak; we report both. The site's proof page shows every interval and limit.

**Explore any place.** Draw a box up to 25 km anywhere on Earth: Modal reads every NISAR pass over
it in parallel straight from NASA's archive (a 22-pass box in Iowa takes about 80 seconds) and the
site plays its dance with the moves named.

**How it is built.** Python engine: NASA CMR search for calibrated NISAR L2 GCOV (never the
uncalibrated beta releases), same-mode series per track, windowed HTTPS reads of 2 to 9 GB HDF5
files, 1-hectare blocks, radar-only dance features, LightGBM. Modal runs one container per NISAR
granule, the training, a UMAP "constellation" of 200,000 hectares placed by the shape of their
dance, and the live API. Web: React, MapLibre, and a WebGL dance floor that moves 170,000 dots at
60 fps. Open source under Apache-2.0.

**Future NISAR applications.** Deforestation alerts through tropical wet-season clouds; floods mapped
under forest canopies; rice planting tracked across Asia for food-security forecasts; crop calendars
for every farming region; melt onset across Greenland and Antarctica every 12 days.

## Space Agency Partner and NASA Data

| Link text | URL |
|---|---|
| NISAR L2 GCOV (NASA-ISRO), ASF DAAC | https://asf.alaska.edu/datasets/daac/nisar/ |
| NASA Earthdata Search / CMR | https://search.earthdata.nasa.gov/ |
| NISAR Data User Guide (ASF) | https://nisar-docs.asf.alaska.edu/ |
| NASA JPL OPERA DIST-ALERT-HLS (forest-loss reference) | https://www.jpl.nasa.gov/go/opera/products/ |
| NASA JPL OPERA DSWx-HLS and DSWx-S1 (water reference) | https://www.jpl.nasa.gov/go/opera/products/ |
| NASA JPL OPERA RTC-S1 (Sentinel-1 comparison) | https://www.jpl.nasa.gov/go/opera/products/ |
| NASA GIBS (VIIRS Black Marble globe) | https://www.earthdata.nasa.gov/engage/open-data-services-software/earthdata-developer-portal/gibs-api |
| NASA ARSET SAR trainings (background) | https://appliedsciences.nasa.gov/what-we-do/capacity-building/arset |

## Other Data and Resources

NIFC WFIGS fire perimeters (https://data-nifc.opendata.arcgis.com/), USDA NASS Cropland Data Layer
(https://www.nass.usda.gov/Research_and_Science/Cropland/SARS1a.php), USGS NLCD
(https://www.mrlc.gov/), Esri World Imagery and Dark Gray Canvas basemaps, Modal
(https://modal.com/), Python, NumPy, SciPy, h5py, fsspec, earthaccess, pyproj, rasterio, LightGBM,
scikit-learn, umap-learn, React, MapLibre GL JS, Vite.

## Super Intelligence (SI) use

We used AI coding assistants (Claude Code and OpenAI Codex) to write and test code, to analyze data,
to draft text, and in brainstorming the project concept. The runtime site uses no AI to generate
content; move labels come from a LightGBM model trained on reference data plus documented physics
rules. No AI-generated images, video or voice: the maps, charts and dance floor are rendered from
NISAR data, and the demo's soundtrack is synthesized from NISAR measurements by our own code.
