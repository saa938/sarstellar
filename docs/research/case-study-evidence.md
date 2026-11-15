# Kaiser Canyon: investigate a changed radar signal

Checked November 15, 2026. This is the strongest supported investigation among the three saved
examples because its selected radar areas have a separately mapped fire perimeter as supporting
context. It is a forest/wildfire investigation, not a validated map of burned forest. The saved
output does not establish forest cover or burn severity for every selected block.

## Question and observation window

What changed inside the mapped Kaiser Canyon fire perimeter between July 13 and September 11,
2026? The saved box is west −119.248°, south 48.119°, east −118.992°, north 48.290° on the
Colville Reservation in Washington.

Both radars share the July 13 and September 11 endpoints. NISAR track 71, descending, includes
July 13, July 25, August 18, August 30 and September 11. Sentinel-1 track 115 includes only
July 13 and September 11. Thus the endpoints match but the acquisition opportunities do not.
The permanent NISAR acquisition gap also interrupts the interval. These saved results cannot
isolate wavelength from temporal sampling, geometry, calibration or processing.

## A disagreement worth inspecting

| Saved area | Area | First flagged acquisition | Area category | NISAR HV relative change | Sentinel-1 VH relative change |
| --- | ---: | --- | --- | ---: | ---: |
| a1 | 197 ha | July 25, 2026 | NISAR majority | −2.84 dB [−3.04, −2.62] | −2.13 dB [−2.39, −1.89] |
| a3 | 158 ha | July 25, 2026 | Both / mixed | −3.15 dB [−3.31, −2.97] | −3.93 dB [−4.11, −3.77] |

Intervals above are the stored within-area measurement intervals. They do not quantify the
probability that a fire caused the signal. The first flagged acquisition marks an observation,
not a verified event start.

Area a1 illustrates why a category cannot replace measurements. Sentinel-1 VH also declined,
but Sentinel-1 did not flag a majority of the connected patch's blocks. Detection combines
significance and effect size; the area label then summarizes block majorities. The saved JSON
does not retain the per-sensor block counts needed to attribute this disagreement to a single
factor. The `both` category also includes split/tied patches, so it does not prove co-located
agreement at every block. These semantics follow `core/sarstellar/areas.py`.

## Independent supporting context and its limits

The official NIFC WFIGS service identifies **Kaiser Canyon**, incident **2026-WACOA-260140**,
in Okanogan County, Washington. Its recorded discovery time is July 16, 2026 at 12:30 UTC.
The perimeter record checked here was current as of October 20, 2026 at 23:08:39 UTC.
[Official incident record](https://services3.arcgis.com/T4QMspbfLg3qTGWY/arcgis/rest/services/WFIGS_Interagency_Perimeters_YearToDate/FeatureServer/0/query?where=attr_UniqueFireIdentifier%3D%272026-WACOA-260140%27&outFields=poly_IncidentName%2Cattr_FireDiscoveryDateTime%2Cpoly_DateCurrent%2Cattr_UniqueFireIdentifier&returnGeometry=false&f=json).

The saved a1 and a3 evidence both record `Inside fire perimeter: yes`. Re-querying the official
geometry with `outSR=4326`, `geometryPrecision=6` and `maxAllowableOffset=0.0001`, then intersecting
valid Shapely geometries, found the full a1–a4 polygons within that current perimeter. This supports
fire context and the ordering of pre-fire observation, recorded discovery and first radar flag.
It does not date the disturbance within each polygon or verify a particular mechanism.

The perimeter is independent of the radar measurements but **not an unused validation source**:
the pipeline used perimeter overlap when assigning the possible-burn hypothesis. This is
corroboration, not an out-of-sample test of cause accuracy. The year-to-date perimeter is a later
mapping product and can change. No independently reviewed optical imagery, field survey or
burn-severity assessment is attached to this case.

The saved `FIRMS detections: 0` must not be presented as evidence that active fire was absent.
The reference reader can return missing context when no map key is available, and the cause
rules convert that to zero. This case relies on the mapped perimeter, not a claimed FIRMS hit.

## Why this case rather than the alternatives

Morton / Mineral has four rule-labeled forest-loss areas, but the saved selected-area evidence
does not carry an independent verified removal reference. Edouard has a strong HH rise and flat
HV consistent with a possible flooded-vegetation hypothesis, but its Sentinel-1 pair is six days
earlier than NISAR's and the saved result supplies no independent inundation observation. Neither
supports a stronger causal claim than the Kaiser perimeter context.

## One benchmark finding

**Adding a second radar did not automatically improve detection.** In the primary forest-loss
comparison, Bonferroni fusion lowered AUPRC by **0.073**, with a site-bootstrap 95% interval of
**[−0.157, −0.009]**, against the NISAR-only baseline selected on training states. None of the four
primary unsupervised fusion comparisons demonstrated a positive gain at this interval level.

The test used one pair per radar on the same eligible blocks. Comparator/method selection used
training states; evaluation used geographically held-out states, and 500 whole-site bootstrap
draws preserved site-level dependence. This controlled comparison is more informative about
performance than which radar colored more hectares in a five-versus-two-date example. It also
does not establish universal superiority: the selected event cohort and reference limitations
constrain generalization. A separate supervised cultivated-land proxy result must remain separate.
[Published benchmark](https://www.sarstellar.earth/scorecard.json).

## Interface handoff

`web/src/components/CaseStudy.tsx` exports a compact native disclosure for the Kaiser story.
Props: `storyId: string | null`, `result: Result | null`, optional
`onSelectArea: (id: string) => void`. Pass `setSelectedId` to make the a1/a3 buttons open the
existing inspector. It links `/stories/kaiser/areas.csv` for the saved-result export being
prepared by the data agent. Other stories and live results render no case-specific claims.

The component reads area and band values from the supplied saved result, keeps observed facts
separate from corroboration and unresolved explanation, and links the controlled benchmark.
