# SARstellar demo script

Draft for a 30-second screen recording at [sarstellar.earth](https://www.sarstellar.earth/). Open the three real stories and scorecard before recording so the clip follows completed results. Show actual live-job progress; a full analysis may exceed the clip length.

| Time | Screen action | Voiceover |
|---|---|---|
| 0–4 s | Open Explore with the Morton / Mineral story. | SARstellar puts NISAR and Sentinel-1 changes on one map. |
| 4–8 s | Toggle the amber and cyan legend entries; switch to Kaiser Canyon. | These Washington examples show where their detections differ. |
| 8–13 s | Open Edouard and select a flooded-vegetation area. | At Edouard, inspect the evidence for possible flooded vegetation. |
| 13–20 s | Open Scorecard; show the held-out cohort and fusion intervals. | We benchmarked 224 eligible sites, holding out 60 across twelve states. |
| 20–25 s | Keep the forest-loss comparison and its interval visible. | Unsupervised fusion showed no clear gain; forest-loss fusion performed worse. |
| 25–30 s | Return to Explore, draw a small valid box, then show its job status. | Draw a box to run the pipeline and export the evidence. |

Keep these captions visible on the relevant screens:

- Stories: “Detection areas; some examples use unequal numbers of radar dates.”
- Scorecard: “Two dates per radar. Site-bootstrap 95% intervals. Selected US sites.”
- Fusion: “Separate learned crop result uses cultivated-land labels, not confirmed crop change.”

The narration contains 58 words, about 116 words per minute. If screen transitions need more time, shorten the opening rather than accelerating the scientific result.

## Six-slide outline

1. **Two radars, one map.** For researchers and land managers: locate changes, compare sensor evidence, inspect and export findings.
2. **One reproducible pipeline.** Windowed NISAR GCOV and OPERA RTC-S1 reads; one-hectare blocks; relative backscatter changes; significance plus a 2 dB effect gate; connected areas of at least 3 ha.
3. **Three real examples.** Morton / Mineral: 141 areas, 1,681 ha. Kaiser Canyon: 202 areas, 2,434 ha. Edouard: 277 areas, 5,852 ha. These are detected areas, not verified event extents or sensor-accuracy rankings.
4. **A geographic test.** 254 sites attempted; 242 processed; 224 eligible; 164 training and 60 held out across 12 states. Primary detectors use the same 2,173,521 comparable blocks and one pair per radar.
5. **Report the measured result.** No primary unsupervised fusion comparison has a positive 95% interval. Forest-loss fusion changes AUPRC by −0.073, interval [−0.157, −0.009]. Separate learned fusion improves the cultivated-land proxy by +0.048, interval [+0.018, +0.101].
6. **Limits and reproduction.** Three held-out flood sites; DSWx-S1 shares Sentinel-1 inputs; CDL identifies cultivated land; event-site sampling does not estimate national prevalence. Link the demo, repository, benchmark JSON and data credits.

Numbers come from [the saved story index](../../web/public/stories/index.json) and [the scorecard generated November 15, 2026](../../web/public/scorecard.json). Use the [project-description draft](project-description.md) for methods, source credits and AI disclosure. Record and submit only after the team checks the final links and challenge requirements.
