# Science brief (from `science` agent, 2026-11-14)

## NISAR ATBDs (Apache-2.0, github.com/NISAR-Science-Algorithms: _Inundation, _Disturbance, _CropArea)
- Inundation (Chapman/Siqueira): relative-calibrate dates on stable areas; classify multitemporal mean; refine w/ per-date change. Sample thresholds (linear): open water HH*HV < 5e-5; inundated veg HH > 0.5 or HH/HV > 8. Final thresholds from cal/val. [osti.gov/servlets/purl/2441094]
- Forest disturbance (Kellndorfer): HV series -> smooth -> residuals from mean -> CUSUM; peak = change date; >=500 bootstrap permutations = confidence. Req: detect 80% of areas losing >50% canopy at 1 ha.
- Crop area (Whelen/Siqueira): temporal CV = sigma/mu of HH,HV over 3+ months vs threshold (Youden J; fixed 0.5 ~74-75%). Mask water (also high CV).
- Soil moisture L3 (200 m): TSR sigma0(t2)/sigma0(t1) ~ |alpha(t2)/alpha(t1)|^2.
- Claim we can make: "flood and forest-loss labels implement NISAR ATBD rules (prelaunch, site-calibrated thresholds)".

## Rule table (delta = after-before dB on >=1 ha aggregates)
| change | HH / HV / ratio | trigger | caveat | vs C-band |
|---|---|---|---|---|
| open-water flood | down lots / to noise | post HH*HV<5e-5 & dHH<=-6 | wind/sand/tarmac/shadow; need flat low-HAND | C sees too |
| flooded vegetation | up / ~0 / up | dHH>=+3, abs(dHV)<=2; post HH>-3dB or ratio>9dB | rice, construction | L-ONLY under closed canopy (~8 dB L rise, no C change) |
| clearcut | down/up(debris) / down / up | dHV<=-3 (3-5 tropics, 2-3 boreal) | logs left delay drop | L detects earlier |
| burn | down / down | dHV<=-2, dHH<=0 | can't sep. from logging -> "fire" only w/ FIRMS hit | C co-pol often RISES |
| crop cycle | rise then abrupt HV drop | CV>=0.5 + crop mask -> "farming" | | both |
| soil wetting | up / up / flat, box-wide, reverts | +1..+4 dB, abs(dratio)<1, check IMERG | wet canopy +1 dB L | L works under crops |
| wet snow | down/down | low confidence only | -3dB C rule fails at L | C better |
| construction | up lots, persistent | dHH>=+5 | orientation | both |
| landslide | either / down | slope>15 + downslope shape | always low conf | both |
| freeze-up (FP) | down/down | suppress if ERA5 T<0C | Oct-Nov high lat | |

UNSOURCED (agent judgment, tune on real data before claiming): construction dHH>=+5, flooded-veg dHH>=+3, flood dHH<=-6, soil wetting dratio<1, 0.5 dB drift flag, layover/shadow guards, Faraday guard. ATBD thresholds are prelaunch single-site values -- say so.

## Detector: sequential omnibus test (Conradsen et al. 2016, TGRS 54:3007, doi:10.1109/TGRS.2015.2510160)
GCOV covariance diagonal (DH: HHHH,HVHV; QP adds VVVV) -> sum of independent gamma tests per channel.
s1..sk intensities, ENL n, Sj = s1+..+sj.
- Omnibus: -2lnQ = -2n[k ln k + sum ln si - k ln Sk]; summed over p channels ~ chi2 with p(k-1) dof. Small-n rho = 1 - (k/n - 1/(nk))/(6(k-1)).
- When: -2lnRj = -2n[j ln j - (j-1)ln(j-1) + (j-1)ln S(j-1) + ln sj - j ln Sj], summed over channels ~ chi2 p dof. First j with p<alpha = change; restart from j.
- Pairwise chained tests inflate FA (25 pairs @0.01 -> ~22%). Scale-invariant -> same-track RTC factor cancels. ~30 lines numpy+scipy.
- ENL: GCOV numberOfLooks layer ~4-15 at 20 m (nominal). Estimate mean^2/var on homogeneous patch, use smaller. Overstating n -> false alarms.
- Speckle: single px std = 4.34*sqrt(trigamma(n)) ~2.3 dB @n=4, 1.4 dB @n=10; two-date ratio ~3.3 dB -> quote deltas ONLY from 1-ha aggregates (25 px @20 m).
- Confidence: Benjamini-Hochberg FDR q=0.05 across box; show % significant ha + median delta w/ bootstrap CI. CUSUM-bootstrap on HV as 2nd opinion for forest loss.

## Pitfalls / guards
- tracks/incidence: split stacks by track/frame/dir/mode; test within stack; cross-stack agreement raises confidence.
- mode/bandwidth: 20/40/77 MHz post at 20/10/20 m; 5 MHz freq B at 80 m. Split on any pol/bandwidth change.
- calibration drift: per-date offset from stable pixels; flag >0.5 dB.
- noise floor: NESZ LUT in metadata; mask HV within 3 dB of it.
- wind on water: L less sensitive; HV stays dark; check JRC permanent water.
- rain: negligible attenuation at L; require persistence 2+ dates for permanent labels.
- layover/shadow: mask slope >~25, outlier rtcGammaToSigmaFactor, low numberOfLooks.
- Faraday rotation: leaks co-pol into HV ~sin^2(Omega); require abs(dHV)>=2 where HH/HV>=12 dB; QP: HVHV != VHVH flags it.

## Validation
1. Null test: stable areas + shuffled dates -> empirical FA ~ alpha (most persuasive plot for radar judge).
2. Water: P/R vs OPERA DSWx-S1, DSWx-HLS; JRC permanent water never new flood.
3. Veg loss: OPERA DIST-ALERT-HLS/DIST-S1; fires vs FIRMS + NIFC perimeters; L-only detections reported as such.
4. 3 events from Copernicus EMS/GDACS Jun-Nov 2026 w/ HLS before/after.
5. Confusion matrix at 1 ha.

Sources: S1 osti 2441094; S2 SAR Handbook ch3; S3 PMC7900998; S4 Park JSTARS 2024 + nisar-docs.asf.alaska.edu/atbd; S5 Hess 1990; S6 Refice 2020 mdpi Water 12/10/2745; S7 PALSAR HV (Santoro 2009); S8 Flores-Anderson RSE 2025; S9 Tanase TGRS 2010; S10 de Jong 2002; S11 Nagler&Rott 2000; S12 Tsai 2019; S13 Conradsen 2016; S14 Canty GEE S1 tutorial pt3; S15 nisar-docs.asf.alaska.edu/gcov
