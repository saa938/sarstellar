# Recon brief (from `recon` agent, 2026-11-14)

## Competitors (60+ public 2026 repos; most created Nov 13-14)
- Dancing-Earth (monolyth365-svg): 7 fixed sites (Tonle Sap, Poyang, Shingle + Big Grass OR fires, Rondonia, Central Valley, Isaias track). Vanilla JS/MapLibre/Cesium; Python reads 512^2 GCOV windows via HTTP range requests; VIIRS, FIRMS, NIFC check, sonification, 3D, daily GH Action; "live world" = newest uncalibrated browse PNG. Live GH Pages + 30 s video. Narrow rules ("why red" fire; HH up >3 dB over HV = water under plants). Found L-band detects only 5-9% of Big Grass grass fire.
- Earth Whisper: 2 precomputed India sites; React/Vite/FastAPI; S1 metadata only; no live recalculation, no cause attribution. Live Vercel.
- dmanpark: Bihar flood plan, NISAR vs DSWx-S1 slider, 67 GB predownloaded; plans only.
- NISAR Hazard Watch (nisar-hazard-watch/nisar-hazard-watch): CLOSEST. Draw box / pick frame, backend 1-2.5 min, "changed beyond its own normal range", optical second witness, FIRMS, coherence lens, PDF report. React/Cesium, FastAPI/Postgres, Modal. Live. Created Oct 22, 6 people. Some charts labelled Demo. Explicitly "no causes".
- Others: Lynkeus (catalog + clipped layers, unfinished), Between Passes (200 random sites, radar vs SMAP rho 0.58, pre-registered), NISAR Pulse (Central Valley subsidence GUNW vs GNSS), ChangeLens, NISAR Lens, SARwatch, Blindspot.
- Our gaps vs them: calibrated GCOV every pass any box (only Hazard Watch also); general physics cause explanation (HW + EW refuse causes); OPERA/C-band cross-check anywhere; WA/NJ sites unused.
- They beat us: Dancing-Earth polish + NIFC; Hazard Watch 3-week head start.

## dmanpark data traps (docs/data.md)
1 PROVISIONAL only; never pair BETA (CRID<05023) w/ PROVISIONAL. 2 validated reprocessing supersedes. 3 gap 2026-07-27 22:03 - 08-10 00:55 UTC. 4 HDF5 need EDL; browse PNG don't. 5 swath-gap stripes move -> union of masks. 6 QP/DH + 20/40 MHz alternate; same-mode pair 24 d apart; multilook to common posting. 7 inter-pol phase not calibrated; theta=59 correction before decompositions. 8 avoid freq B. 9 40 MHz residual banding. 10 RFI leftovers on water. 11 browse colors mode-dependent. 12 GCOV is gamma0; gamma->sigma factor included. 13 posting 10/20/80 m, read from file. 14 no layover/shadow layer -> compute from GLO-30. 15 files 2-9 GB, pull only HHHH, HVHV, mask. 16 report time offset to references; separate permanent water. 17 C-band refs share errors in cities/wind/canopy. 18 24-day baselines pick up crop growth. 19 OPERA RTC needs ASF data-use agreement.

## Resources tab (via site GraphQL pageByPath; Wayback Nov 1 exists)
NASA: Earthdata Search, ASF Vertex, NISAR Data User Guide (ASF), Intro to Remote Sensing, Intro to SAR, ARSET trainings, NISAR StoryMaps, NISAR Applications White Papers, UAVSAR Postcards.
Partners: CSA RCM data, CSA SAR Python tutorial, RADARSAT-1, CONAE SAOCOM.
Sentinel-1/OPERA not named -> NISAR GCOV via ASF/Earthdata Search is the safe listed dataset.

## Events (Jun 17 - Nov 14 2026), ranked
1. Indiana floods Aug 11-16: White River at Anderson 24.93 ft (beat 1913 record), >11 in rain, >=7 dead (NPR). NISAR pairs: T47 Jul 23 -> Aug 16; T156 Aug 12 -> 24.
2. Kaiser Canyon Fire WA: lightning Jul 16; 138,293 ac; contained Sep 7; Colville Reservation, Nespelem evacuated, >1,000 displaced (KPQ, IQAir). Tribal/low-income angle. Pre-fire passes from Jun 17.
3. Spokane Complex WA ~Jul 31-Aug: ~11,000 ac; 600-700+ structures destroyed; 60k evacuated (NW News Network). Falls in data gap -> July vs post-Aug 10.
4. Hurricane Isaias Oct 9: Cat 2 near Destin FL; >=8 dead FL/AL; ~800k without power.
5. Edouard TX Sep 1-3: 18-22 in rain near Kountze; flash-flood emergencies. East Texas forest -> flooded-under-canopy (L-only) candidate.
6. NJ nor'easters Sep 26-27 and ~Oct 21: worst erosion since Sandy in spots; Brigantine beach gone to seawall. Tidal flooding drains before pass; beach/dune change maybe.
7. Oregon record fire season 2.3-2.5M ac; Big Grass 579,169 ac (but L-band detects only 5-9%).
8. Central Valley subsidence: no discrete event; storage -2M acre-ft in 2025; needs GUNW; NISAR Pulse covers.
Nothing found: NJ wildfire in window; WA flood since Jun 17 (historic WA floods were Dec 2025 -- BUT data-spike says PROVISIONAL over Seattle T172F65 D starts Nov 2025 -> CHECK Skagit/Snohomish Dec 2025 coverage); CA M4+ quake Sep-Oct.
