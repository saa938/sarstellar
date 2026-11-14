# Kaiser Canyon real-data spike (data-spike agent, 2026-11-14)
Outputs: scratchpad\data-spike\kaiser\ (stats.json, blocks.npz, before_HV.png, after_HV.png, dHV.png, dHH.png, dVH_S1_T115.png, dVH_S1_T166.png, *_overlay.png, rtc_data\)

- Perimeter: WFIGS_Interagency_Perimeters_YearToDate, 2026-WACOA-260140, 138,285 GIS acres; geometry INVALID (make_valid); containment date null.
- Box: -119.3705, 48.0531, -118.7196, 48.3605.
- Pair T71 F64 D PROVISIONAL: pre 2026-07-13 (..._025_071_D_064_4005_DHDH_A_20260713T030956_20260713T031031_P05023_N_F_J_001), post 2026-09-11 (..._030_071_D_064_4005_DHDH_A_20260911T030953_20260911T031028_P05023_N_F_J_001). Same CRID P05023, productVersion 1.0.11, 40 MHz acq=proc, HH+HV, full frame, not mixed. EPSG 32610 (zone 10 although site in zone 11!). Backup T77 F26 A same dates.
- Window 3680x5020 px @10 m; valid mask 1..254 both dates (99.98%); 10x10 linear avg -> dB; outside = >500 m outside perimeter.
- NISAR: median dHV inside -0.01 / outside +0.52; dHH +0.75 / +1.15. Inside blocks dHV<=-2: 4.65% of 56,026 (outside 0.05%); dHH 0.90%. Woody (pre HV>=-14) 6.15%; open (pre HV<-18) 2.08%. Coherent -3..-5 dB drops in forested patches. Scene-wide +0.5 dB HV / +1.1 dB HH outside -> use relative change.
- S1 RTC T115 (S1D, exact dates 07-13->09-11, 75.7% coverage): median dVH inside -1.78 / outside -0.85; 43.7% inside <=-2 (outside 14.1%).
- S1 RTC T166 (S1C, 07-11->09-09, 100%): median dVH -1.57 / -0.19; 40.6% inside <=-2 (outside 5.2%). dVV weak (4.7-6.8%).
- Per-block corr C dVH vs L dHV inside: r=0.40 (T115), 0.38 (T166).
- Interpretation: mostly shrub-steppe/grass fire; C VH catches low-veg loss; L HV reacts where trees lost. L-band = complementary, not better.
- Skagit Dec 2025: BETA only (T172 F64 D 11-10, 11-22, 12-04, 12-16, 12-28, 01-09) -> dropped.
- Engineering: ASF transient 502 mid-read -> h5py segfault -> need retry/backoff in block fetcher. Desktop read: HHHH 13-14.5 s for full box; 4 layers ~42 s/date; open 1.1-2.4 s. Different tracks use different UTM zones -> reproject.
