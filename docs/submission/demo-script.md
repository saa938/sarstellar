# SARstellar demo script

The submission uses the [seven-slide deck](sarstellar-presentation-public.pptx), viewable at [sarstellar.earth/demo](https://www.sarstellar.earth/demo/). Speaker notes in the deck carry the narration for each slide (about 30–45 s each). The optional 30-second screen recording below follows the same story. Recheck every link before submitting.

## One-sentence pitch

NISAR and Sentinel-1 are specialists, not a team: on held-out states NISAR was 7.8× more precise for forest loss, simple fusion did not help, and SARstellar shows which radar to trust for each change.

## Seven slides

1. **Two radars, one map.** NISAR now images nearly all of Earth's land every 12 days; Sentinel-1 has done so for a decade. Which radar should you trust for which change? Image: Kaiser Canyon detections.
2. **Draw a box, get evidence you can check.** Site screenshot; pick a place → compare both radars → inspect each change, including which radar to trust for that cause (from the held-out test) → export.
3. **Kaiser Canyon Fire, Colville Reservation.** 1,764 ha classified as burn; NISAR HV −2.8 dB [−3.0, −2.6] in the largest burn patch, inside the NIFC perimeter; census tracts at the 89th–96th SVI percentile. Area totals use 5 NISAR vs 2 Sentinel-1 dates, so they are not an accuracy comparison.
4. **Statistics first, stories second.** Read → 1-ha grid → Conradsen test, FDR q = 0.05, ≥ 2 dB → areas ≥ 3 ha → rule-based cause hypothesis. The language model only rewords evidence.
5. **A fair test on states the model never saw.** 224 sites in 39 states; 164 train, 60 held out in 12 states; 2,173,521 one-hectare blocks; one image pair per radar.
6. **The radars are specialists, not a team.** Held-out precision at 50% recall: forest loss 31.1% (NISAR) vs 4.0% (Sentinel-1); burn 32.6 vs 27.8; cultivated land 41.4 vs 25.3; flood 0.7 vs 9.4. Fisher/Bonferroni fusion never reliably beat the best single radar; forest-loss ΔAUPRC −0.073 [−0.157, −0.009]. False alarms on held-out stable ground: NISAR 1.6%, Sentinel-1 3.4%, Fisher/Bonferroni fusion 4.3%.
7. **Try it: sarstellar.earth.** Limits (selected event sites, 3 held-out flood sites, causes are hypotheses, US boxes ≤ 20 km) and where to check our work (scorecard.json, story provenance, notebook exports), plus data credits.

## Optional 30-second recording

| Time | Screen | Voiceover |
|---|---|---|
| 0–5 s | Map, Kaiser Canyon example, detected areas on. | NISAR and Sentinel-1 both watch every US acre. Which should you trust? |
| 5–15 s | Click the largest burn area; show its evidence panel. | SARstellar shows what changed, when, why, who lives there, and which radar to trust. |
| 15–27 s | Benchmark tab, forest-loss comparison. | On twelve held-out states, NISAR was 7.8 times more precise for forest loss, and blind fusion didn't help. |
| 27–30 s | Back to Map; start drawing a box. | Pick the band for the hazard. Try it at sarstellar.earth. |

Keep this caption on the benchmark screen: “Two dates per radar. Held-out states. Selected US sites.”

## Sources

Numbers come from [the saved story index](../../web/public/stories/index.json), [kaiser.json](../../web/public/stories/kaiser.json) and [the scorecard generated November 15, 2026](../../web/public/scorecard.json) (`equal_recall`, `fusion`, `sites`). The flood comparison's reference (DSWx-S1) partly uses Sentinel-1 observations, so it is not sensor-independent.
