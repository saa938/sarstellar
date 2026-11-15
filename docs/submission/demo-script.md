# SARstellar demo script

Optional 30-second screen-recording script at [sarstellar.earth](https://www.sarstellar.earth/). The completed [editable six-slide deck](sarstellar-presentation-public.pptx) meets the supplied demo-length alternative and will have a [public viewer](https://www.sarstellar.earth/demo/) after publication. A video is optional when submitting that deck. The Light-default release is live with a Charcoal option; confirm the final workflow and viewer before submission. If recording, open the examples first and align the [timed captions](demo-captions.srt) to actual narration. Show actual live-job progress; a full analysis may exceed the clip length.

| Time | Screen action | Voiceover |
|---|---|---|
| 0–4 s | Open Map with the Morton / Mineral example. | SARstellar compares NISAR GCOV and Sentinel-1 surface change. |
| 4–8 s | Toggle the NISAR-only and Sentinel-1-only layers; switch to Kaiser Canyon. | Open an example, compare detections, and select an area. |
| 8–14 s | Open Edouard and select a possible flooded-vegetation area; show its evidence sections. | Inspect what changed, when, the possible cause, and the uncertainty. |
| 14–21 s | Open Benchmark; show the held-out cohort and fusion intervals. | We held out sixty sites across twelve states. Unsupervised fusion showed no clear gain. |
| 21–25 s | Keep the forest-loss comparison and its interval visible. | Forest-loss fusion performed worse in this benchmark. |
| 25–30 s | Return to Map, draw a small valid box, then show its job status. | Draw a box, review the measurements, and export the result. |

Keep these captions visible on the relevant screens:

- Examples: “Detected areas; some examples use unequal numbers of radar dates.”
- Benchmark: “Two dates per radar. Site-bootstrap 95% intervals. Selected US sites.”
- Fusion: “Separate learned crop result uses cultivated-land labels, not confirmed crop change.”

Read the narration at a measured pace and align the supplied captions to the actual recording. If screen transitions need more time, shorten the opening rather than accelerating the scientific result.

## Six-slide outline

1. **Radar change comparison.** For researchers and land managers: locate changes, compare sensor evidence, inspect and export findings.
2. **One reproducible pipeline.** Windowed NISAR GCOV and OPERA RTC-S1 reads; one-hectare blocks; relative backscatter changes; significance plus a 2 dB effect gate; connected areas of at least 3 ha.
3. **Three real examples.** Morton / Mineral: 141 areas, 1,681 ha. Kaiser Canyon: 202 areas, 2,434 ha. Edouard: 277 areas, 5,852 ha. These are detected areas, not verified event extents or sensor-accuracy rankings.
4. **A geographic test.** 254 sites attempted; 242 processed; 224 eligible; 164 training and 60 held out across 12 states. Primary detectors use the same 2,173,521 comparable blocks and one pair per radar.
5. **Report the measured result.** No primary unsupervised fusion comparison has a positive 95% interval. Forest-loss fusion changes AUPRC by −0.073, interval [−0.157, −0.009]. Separate learned fusion improves the cultivated-land proxy by +0.048, interval [+0.018, +0.101].
6. **Limits and reproduction.** Three held-out flood sites; DSWx-S1 shares Sentinel-1 inputs; CDL identifies cultivated land; event-site sampling does not estimate national prevalence. Link the demo, repository, benchmark JSON and data credits.

Numbers come from [the saved story index](../../web/public/stories/index.json) and [the scorecard generated November 15, 2026](../../web/public/scorecard.json). Use the [project-description draft](project-description.md) for methods, source credits and AI disclosure. Record and submit only after the team checks the final links and challenge requirements.
