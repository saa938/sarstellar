# Clearcut + Edouard spikes (data-spike agent, 2026-11-14)
Outputs: scratchpad\data-spike\clearcut\ (stats.json, side_by_side.png, L_HV_change_RGB.png, *_overlay.png), edouard\ (stats.json, side_by_side_HAND.png, side_by_side.png, L_HH_change_RGB.png). Shared helper: data-spike\spike_lib.py

## Clearcuts Morton/Mineral WA, box -122.45,46.55,-122.05,46.80 -> L WINS
- NISAR T172 F65 D 2026-05-21 -> 2026-09-30, P05023, v1.0.11, 40 MHz, EPSG 32610:
  ..._020_172_D_065_4005_DHDH_A_20260521T031853_20260521T031928_P05023_N_F_J_001
  ..._031_172_D_065_4005_DHDH_A_20260930T031847_20260930T031922_P05023_N_F_J_001
- S1C T137 05-27 -> 09-19 (99.9% forest coverage); T064 dropped (2.5%).
- Reference OPERA DIST-ALERT-HLS T10TES (10-11 S2B): block = ref clearcut if >=50% px lost >=50% veg, dated 05-21..10-11. 68,364 forest blocks (NLCD 41-43 >=70%), 106 ref clearcuts.
- Forest HV shift +0.11 dB -> relative dHV.
- L rel dHV<=-3: 157 flags, 56 ref hits; recall 52.8%, precision 35.7%; median rel dHV in ref -3.18.
- Of L flags: 78 also C dVH<=-2, 53 dVV<=-2; 79 L-only, 16 of them ref.
- C dVH<=-2 alone: 1,186 flags, 54 hits; recall 50.9%, precision 4.6%. Equal 157 flags: L 56 vs C 23. At -4 dB: L precision 53.9% vs C 12.5%. Median C dVH in ref -2.03.
- 36 ref missed by both (thinning/partial/DIST FA). Caveat DIST-HLS optical not ground truth; May snow unchecked.

## Edouard Neches/Village Creek near Kountze TX, box -94.45,30.10,-94.00,30.55 -> L sees flooded forest (moderate)
- NISAR T12 F73 D 08-26 -> 09-07, P05023, 40 MHz, EPSG 32615:
  ..._029_012_D_073_4005_DHDH_A_20260826T010148_20260826T010222_P05023_N_F_J_001
  ..._030_012_D_073_4005_DHDH_A_20260907T010148_20260907T010222_P05023_N_F_J_001
- Bonus T134 F17 A 08-22 -> 09-03 (during storm).
- USGS Village Creek nr Kountze: ~50 -> 28,000 cfs, stage 2 -> 22.2 ft on 09-04; 14.8 ft on 09-07; 5.6 ft 09-13.
- S1: only T136 S1D 08-20, 09-01 (pre-flood), 09-13 (after recession). S1 never saw the flood.
- Scene-wide HH +1.2..+1.5 dB (wet canopy/soil) -> relative to upland forest (HAND>=10 m).
- Floodplain forest (NLCD woody wetland, HAND<=2 m, 47,285 blocks): L rel dHH median +0.48, p90 +2.54; 5.69% >= +3 dB vs 2.63% upland. dHV median +0.22, 0.33% >= +3. C 08-20->09-13 dVV 0.17%, dVH 0.13% >= +3; 08-20->09-01 0.0-0.02%.
- 2,689 floodplain blocks rel dHH >= +3; 46 also rel dVV >= +3; DSWx-S1 (09-13) marks 5 as inundated veg.
- Visual: coherent +3..+6 dB HH ribbon along Village Creek corridor, not in HV or C. Flat coastal plain (60% blocks HAND<=2) dilutes stratum stats.
- Verdict: moderate; no inundation truth; C comparison confounded by timing.
