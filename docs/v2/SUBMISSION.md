# SARstellar: submission fields (paste-ready)

Updated 2026-11-15 for the redesigned site (guided story, scientific labels). Every number is
measured by our pipeline (`web/public/story/story.json`, `web/public/proof.json`). No team member
names, faces or voices anywhere (minors on the team).

---

## Project Name

SARstellar

## High-Level Summary

Earth's surface is always changing, and NISAR, the new NASA-ISRO radar satellite, sees it through
clouds and darkness every 12 days. SARstellar shows anyone how to read what it sees. NISAR listens
to each echo in two ways: HH hears surfaces and bounces, HV hears leaves and branches. Every kind of
change leaves its own signature in those two channels, and we follow those signatures through real
NISAR data: wheat growing in Punjab (HV up 3.3 dB), rice standing in water in the same fields (HH up
6.9 dB), a flood hidden under Texas forests, Amazon forest cut down, Greenland's ice through the
summer. We read every NISAR pass over nine places (177 granules, about 10,900 km2) and tested a
model on 12 US states it never saw: it found 54% of forest loss while pointing at 1.7% of the land,
and forest loss turned out to live in HV, which finds it 6 times better than HH alone.

## Demo

(30-second video: link to be added once rendered)

## Final Project

https://www.sarstellar.earth/

## Project Details

**What it does.** SARstellar is a guided, interactive story about what NISAR's L-band radar sees on
Earth's surface, built entirely from real NISAR data. It explains, with real radar images rather
than drawings, how the satellite listens in two ways (HH: surfaces and bounces; HV: canopy), shows
where water, bare fields, crops, forests and cities sit when every hectare is placed by its two
echoes, and then walks through real changes one at a time, each with before-and-after radar images,
the measured path of the hectares that changed, and one number:

- A crop growing (Punjab, India): across 70,752 cultivated hectares, the median HV climbed 3.3 dB from
  November to February as the wheat filled in, and fell at the April harvest.
- Rice standing in water (the same fields): the median HH jumped 6.9 dB from mid-July to mid-September
  while HV rose far less; the pulse bounces off the water and up the stalks. Two crops, two channels.
- A flood hidden under trees (Village Creek, Texas): on the NISAR pass during Tropical Storm Edouard,
  3,572 forested hectares jumped 3 dB or more in HH while HV held still. Twelve days later the water
  had drained.
- A forest cut down (Rondonia, Brazil): cleared hectares lost about 8 dB of HV between June and
  October.
- An ice sheet's summer (Greenland): HH rose 4 to 5 dB across the melt zone at the height of summer
  and settled by October.

A Places section lets you play each of the nine places pass by pass, and a Method page explains the
data, the model, the tests and the limits.

**Does it work?** We trained a gradient-boosted model on the change in HH and HV between two NISAR
passes at 2.46 million reference hectares on 170 US sites with independent labels (NASA OPERA
DIST-ALERT-HLS optical forest loss, NIFC fire perimeters, OPERA DSWx water, USDA cropland), and tested
it on 72 sites in 12 states it never saw. It found 54% of forest loss while pointing at 1.7% of the
land (random picking would find about 2%). When it says a field is growing a crop it is right 63
times in 100 (10 by guessing). When it says a hectare changed, it really did 66 times in 100 (19 by
guessing). Retraining with one channel at a time shows forest loss lives in HV (6 times better than
HH alone). Trained only on US sites, it still found 54% of the forest loss NASA's optical satellites
recorded in Rondonia, Brazil. On 37 forest-loss sites, NISAR's alerts were 7.8 times more often real
than Sentinel-1's (Europe's shorter-wavelength radar) at the same detection rate. Limits, shown on
the site: open-water floods were hard to separate from two passes, grass fires barely register at
L-band, and floods under trees and ice changes have no labeled test set yet.

**How it is built.** Python: NASA CMR search for calibrated NISAR L2 GCOV (never the uncalibrated
beta releases), same-mode series per track, windowed HTTPS reads of 2 to 9 GB HDF5 files, 1-hectare
blocks, radar-only features, LightGBM. Modal ran one container per NISAR granule and the training.
Web: React and canvas charts, every image rendered from NISAR data. Open source under Apache-2.0:
https://github.com/saa938/sarstellar

**Future NISAR applications.** Deforestation alerts through tropical wet-season clouds; floods mapped
under forest canopies; rice planting tracked across Asia for food security; crop calendars for every
farming region; the melt season across Greenland and Antarctica, every 12 days.

## Space Agency Partner and NASA Data

| Link text | URL |
|---|---|
| NISAR L2 GCOV (NASA-ISRO), ASF DAAC | https://asf.alaska.edu/datasets/daac/nisar/ |
| NISAR Data User Guide (ASF) | https://nisar-docs.asf.alaska.edu/ |
| NASA Earthdata Search / CMR | https://search.earthdata.nasa.gov/ |
| NASA JPL OPERA DIST-ALERT-HLS (forest-loss reference) | https://www.jpl.nasa.gov/go/opera/products/ |
| NASA JPL OPERA DSWx-HLS and DSWx-S1 (water reference) | https://www.jpl.nasa.gov/go/opera/products/ |
| NASA JPL OPERA RTC-S1 (Sentinel-1 comparison) | https://www.jpl.nasa.gov/go/opera/products/ |
| NASA ARSET SAR trainings (background) | https://appliedsciences.nasa.gov/what-we-do/capacity-building/arset |

## Other Data and Resources

NIFC WFIGS fire perimeters (https://data-nifc.opendata.arcgis.com/), USDA NASS Cropland Data Layer
(https://www.nass.usda.gov/Research_and_Science/Cropland/SARS1a.php), USGS NLCD
(https://www.mrlc.gov/), Modal (https://modal.com/), Python, NumPy, SciPy, h5py, fsspec, earthaccess,
pyproj, rasterio, LightGBM, scikit-learn, React, Vite.

## Super Intelligence (SI) use

We used AI coding assistants (Claude Code and OpenAI Codex) to write and test code, to analyze data,
to draft text, and in brainstorming the project concept. The site generates no content with AI: labels
come from a LightGBM model trained on reference data plus documented physics rules, and every image is
rendered from NISAR data. No AI-generated images, video or voice.
