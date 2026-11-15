# SARstellar usability demonstration

Review date: November 15, 2026.

This is an agent usability review, not a human participant study or evidence of human validation. The reviewer used the visible website interface in Microsoft Edge through supported browser automation. No application source or implementation documentation was read. No new analysis job was submitted, and no account or preference settings were changed.

## Build and task

Task: locate a forest or flood finding, explain observed change versus possible cause and the dates/comparability limits, then export it. The public production page at https://www.sarstellar.earth/ was opened first. The task owner then directed the reviewer to the current local design at http://127.0.0.1:5173/, connected to the live API. The detailed findings below describe that local design, not a claim that the new panel was already deployed publicly.

The local demonstration took roughly three minutes of UI review, excluding browser setup and report writing. This is a rough agent-session estimate, not measured participant task time. It required three substantive clicks: choose a finding, expand acquisition windows, and switch to Before | After. The default example was already selected.

## Observed task path

| Step | Visible action or evidence | Outcome |
| --- | --- | --- |
| Locate a finding | Default Forest change near Morton / Mineral, WA example; rows labeled with class, sensor overlap, ID, and hectares | Chose “Forest loss / Both sensors · a6 / 42 ha” in one click. Its polygon gained a white outline. No need to draw an area or run a job. |
| Understand observed change | Selected panel begins “Change detected,” then “Radar signal changed across 42 ha” and “The radar detection does not establish a physical cause.” | Clearly understood that the finding is a radar-signal change rather than confirmed canopy removal. |
| Understand uncertainty | “Possible forest loss”; “Provisional rule-based interpretation”; independent imagery, harvest records, or field observations recommended; moisture, seasonality, and viewing geometry named as alternatives | Correct interpretation: forest loss is a hypothesis that needs independent verification. The separate measurement intervals do not provide a calibrated probability that forest loss occurred. |
| Understand time | “First flagged acquisition: Jun 26, 2026 (UTC). Observation timing; no event date is established.” Expanded Acquisition windows | Correct interpretation: June 26 is the first flagged observation, not a confirmed event date. NISAR window was May 21–Sep 30, 2026; Sentinel-1 window was May 16–Oct 1, 2026. |
| Assess comparability | Initial results warning: 11 NISAR observations and 2 Sentinel-1 observations; area totals do not establish which radar performed better; paired benchmark link. Left sidebar retains acquisition counts and windows | Correct interpretation: larger area totals cannot establish superior sensor performance in this unequal sample. No benchmark result was inferred from the map totals. |
| Inspect visual evidence | Clicked Before \| After; satellite/radar comparison loaded with “Before: NISAR May 21, 2026” and “After: NISAR Sep 30, 2026” labels | Comparison was available and dates were visible. Selected area was no longer outlined in this view, making it harder to connect a6 to the raster evidence. |
| Export the finding | Selected panel explicitly states “Exports unavailable for this result.” No download links appeared for this saved example | Blocked. No export was downloaded. The demonstration did not complete end to end. |

## Findings and priorities

1. **Export is the task blocker.** The saved example provides a useful immediate finding, but its selected result explicitly has no exports. There is no visible next step for obtaining the same result as a CSV, raster, or notebook. Provide working exports for the example, or explain a concrete recovery path beside the unavailable message. Export success remains unverified until a file is actually downloaded through the UI.
2. **One rule phrase undermines the otherwise clear uncertainty framing.** “HV fell 3 dB or more (canopy removed)” appears in supporting rule evidence and again under Measurements. “Canopy removed” reads like a cause assertion inside a panel that calls forest loss provisional. Describe the threshold as a signal consistent with possible canopy loss and keep the alternative explanations nearby.
3. **Preserve the selected finding in comparison views.** The white outline made a6 identifiable on Detected areas, then disappeared on Before \| After. A retained outline or a visible locator would make it easier to examine the same place without remembering its map position.
4. **Replace the internal-looking source label.** Measurements shows “research table (docs/research/science.md, literature values).” A visitor cannot use that workspace path as a source. Link to an accessible source or use a concise human-readable citation.

## What worked

The example cards, plain class labels, hectares, and sensor-overlap rows made the initial finding easy to locate. The four-question panel provided a usable explanation without requiring technical-statistics expansion. The explicit signal/cause distinction and observation/event-date distinction supported a correct explanation of the finding. The unequal-observation warning appeared before selection, and acquisition counts remained visible after selection.

## Limits

This was one agent run on desktop Edge, centered on one saved forest example. Mobile layouts, keyboard-only operation, screen-reader experience, other examples, job creation, and successful live-job exports were not tested. Tool-assisted access to the accessibility tree can make discovery easier than ordinary visual scanning. No scientific truth claim or independently validated physical cause follows from this usability review.

## Bounded implementation and recheck

After the initial source-free review, the task owner separately authorized UI fixes. This follow-up involved reading and editing implementation files; it is not a second fresh-visitor study. Saved result records and measurements were not changed.

- Sensor labels now read “NISAR majority,” “Both / mixed,” and “Sentinel-1 majority.” The legend explains that labels summarize area block majorities, the other radar may flag some blocks, and Both / mixed covers both-majority or neither-majority patches. Hectare totals and agreement keys are unchanged.
- Legacy rule text is qualified at display time: “(canopy removed)” becomes “(consistent with canopy loss)”; “double bounce off standing water” becomes “possible double-bounce response.” The original evidence remains unchanged.
- Internal documentation source notes now link to the public Methods page as “Methods and rule criteria.”
- Both available sensor acquisition windows remain visible for a selected area because majority labels do not establish exclusive detection.

The four affected component/helper test suites passed all 26 tests. A desktop Edge recheck at http://127.0.0.1:5173/ visibly confirmed the majority legend and note, the qualified rule in a6's supporting evidence and Measurements, and navigation from the Methods link to the Methods page. At recheck time, exports for the saved example still displayed as unavailable. The selected-area comparison outline issue remains open; comparison-view files were not changed in this work.

## Export fix: observed before and after

After the task owner supplied saved-result CSVs and loader wiring, the reviewer reloaded localhost and repeated the a6 task. This was an agent verification of the changed interface, not an independent human study. No new analysis job was submitted.

Before: the selected a6 panel said “Exports unavailable for this result,” so the task stopped without a file.

After: the example overview and selected a6 panel exposed a CSV link. GeoTIFF and Notebook remained visibly disabled for this saved result. Selecting a6 still showed 42 ha, Both / mixed, Possible forest loss, a provisional rule, and June 26 as an observation date rather than a confirmed event date. Its updated narration described both radars contributing detections through “shared majorities or split blocks.”

The reviewer clicked the visible CSV link in the selected-area panel. The browser download event completed and returned `C:\Users\ashay\Downloads\areas.csv`. The downloaded file was then read from disk: 421,838 bytes and 141 data rows. Its a6 row matched the visible finding:

| Downloaded field | Observed value |
| --- | --- |
| id | a6 |
| area_ha | 42.0 |
| agreement | both |
| cause_hypothesis | forest_loss |
| first_flagged_acquisition | 2026-06-26 |
| plain_text | Describes shared majorities or split blocks, a forest-loss hypothesis, heuristic confidence, and independent verification. |

The CSV interpretation note explains the majority semantics, observation-date limit, and uncalibrated cause confidence. Raw evidence JSON retains the original saved rule/source text, and that preservation is explicitly disclosed in the export note; display-time wording changes do not alter those saved measurements. The file is a dataset-level export containing all 141 areas, rather than a single-area-only export.

**Result:** locating a6, explaining its uncertainty/date limits, and exporting a matching CSV completed end to end after the fix. This establishes successful agent execution of that bounded desktop task only. It does not establish human usability or validate the physical cause. The initial blocker above is retained as historical evidence of the before state.

## Comparison outline recheck

After the comparison-view owner supplied the selection-outline fix, the reviewer kept a6 selected and switched to Before | After. A white outline with a dark edge visibly marked the same polygon over the before raster. Moving the divider to 0% with the keyboard revealed the after raster and retained the outline in the same location. The selected a6 explanation and CSV link remained in the right panel. The dated before/after labels remained visible.

This resolves the observed “where is my selected area?” friction for this bounded a6 desktop check. The comparison fix was implemented by a separate owner; this reviewer made no comparison-view code changes. The earlier comparison finding is retained as the before state, and is no longer an open issue in the rechecked local design.
