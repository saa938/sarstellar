# Data spike results (from `data-spike` agent, 2026-11-14)
Raw scripts/output: scratchpad\data-spike (aoi_GCOV.txt, aoi_GUNW.txt, aoi_GCOV.json, sample_umm.json)

- PROVISIONAL GCOV goes back to 2025-10-29 (not 06-17). ~550-850 granules/mo Nov25-May26 (selected regions incl. US), 20k-42k/mo from June (global). VALIDATED (NISAR_L2_GCOV_V1) from 2026-10-21, 16,611 granules. Gap 07-27..08-10 confirmed.
- NO Earthdata creds on machine -> HDF5 open/timing UNVERIFIED (tree, chunks, mask values, CRS, spacing, 1 s read claim). Range GET -> 302 URS -> 401. Sidecars gated. Browse PNGs (LATLON, NATIVE_A_HHHH/HVHV) + KMLs PUBLIC via 303 to CloudFront.

| AOI | dates | main stacks | mode | GB |
|---|---|---|---|---|
| Seattle | 37 | T172F65 D 23 (Nov25-Oct26); others 10-11 (Jun-Oct) | 40+5 HH+HV | 6.2-7.4 |
| Rainier | 51 | T172F65 D 29 (Nov25-Oct26) | 40+5 HH+HV | 6.9-7.4 |
| Moses Lake | 29 | T71F64/65 D, T77F25/26 A 11 each, Jun-Oct only | 40+5 | 7.2-7.6 |
| Pine Barrens | 63 | T69F68 D 29 (Nov25-Oct26); T133F22 A 27 (Nov25-Nov2) | 40+5 | 3.0-8.0 |
| Meadowlands | 61 | same T69F68 D + T133F22 A | 40+5 | 4.1-8.0 |
| Barnegat | 56 | T69F68 D 29; T133F22 A 27 | 40+5 | 3.0-6.9 |
| Tulare | 51 | T34F20 A 27 (2025-11-24..2026-10-26); T114F70 D 24 | 40+5 | 7.1-7.5 |
| Bihar | 44 | T149F75 D 11 (not dense); mixed 20+5/40+5, DH/QP | mixed | 1.7-9.0 |

GUNW Tulare: 47 dates, all PROVISIONAL; T34F20 A 25, T114F70 D 22 (2025-11-24..2026-10-08). 40 MHz HH only ~2.4 GB.

CMR UMM-G AdditionalAttributes: TRACK_NUMBER, FRAME_NUMBER, ASCENDING_DESCENDING, FREQUENCY_A/B_RANGE_BANDWIDTH, FREQUENCY_A/B_POLARIZATION, FULL_FRAME, STACK_ID, size. asf_search: pathNumber, frameNumber, rangeBandwidth, polarization, frameCoverage. -> filter mode before reading.

OPERA Jun 1-Nov 14 2026:
- DIST-ALERT-S1: 0 granules over Seattle/Pine Barrens/Tulare (all 239k are Jan-Feb 2026 acq). NOT USABLE.
- DSWx-S1: Seattle 41 dates, Pine Barrens 13, Tulare 59.
- RTC-S1: Seattle 46, Pine Barrens 26, Tulare 30. CSLC-S1 similar. DISP-S1 0.

Traps:
1. Duplicate deliveries _001/_002 same CRID -> keep highest counter.
2. Frame footprints shift (Seattle F65 vs F64) -> group by track+direction, query by bbox.
3. Bihar mixed modes, "M" full-frame 20 MHz + "A" partial 40 MHz/QP.
4. Tulare 2025-12-12 is 5 MHz-only freq B VV+VH ("NADV") -> filter RANGE_BANDWIDTH.
5. asf_search dataset=NISAR processingLevel=GCOV silently includes BETA -> filter by shortName.
6. CRID PROVISIONAL P05023 vs VALIDATED P05036 -> possible radiometric step across 10-21 (unverified).
7. 4-6 tracks per AOI -> single track per series.

## Task 1 VERIFIED (remote read, VALIDATED Tulare granule ..._DHDH_A_20261026T130857..._P05036_N_F_J_001, 6.92 GB)
- earthaccess bearer-token fsspec session; blockcache 8 MiB, page_buf 16 MiB, rdcc 4 MiB. Login helper: scratchpad\data-spike\edl.py; dump: gcov_inspect.txt
- From home desktop: login 1.5 s; open 2.7-3.8 s; full metadata walk 6.9 s; 2000x2000 HHHH window 4.6 s (3.8 s adjacent); 21 blocks ~176 MB requested (gzip + per-block latency). Modal us-west untested.
- freqA grids (34272, 34848) float32, chunks 512x512 gzip, spacing 10 m (NOT 20) -> 10x10 px = 1 ha. freqB (5 MHz) (4284,4356) @80 m.
- `projection` dataset = EPSG uint32 (32611 here). xCoordinates/yCoordinates.
- Layers: HHHH, HVHV (DH, isFullCovariance=False), mask, inputDataExceptionMask, numberOfLooks (float32), rtcGammaToSigmaFactor, listOfPolarizations, listOfCovarianceTerms, numberOfSubSwaths, projection.
- gamma0 RTC linear power; dB = 10*log10. Noise correction + Faraday NOT applied.
- mask uint8: 1..254 valid (subswath #); 0 = partially focused/invalid sample in averaging set; 255 fill.
- inputDataExceptionMask uint16 fill 65535: bit OR of exception codes (2 = qFSP-H1 sample slip) + validity bits 256 HH, 512 HV, 1024 VH, 2048 VV.
- identification: trackNumber, frameNumber, orbitPassDirection, absoluteOrbitNumber, isFullFrame, isMixedMode ("M" flag), isJointObservation, isDithered, listOfFrequencies, compositeReleaseId, staticLayersDataAccess. Bandwidth: metadata/sourceData/swaths/frequencyA/acquiredRangeBandwidth (40e6), processedRangeBandwidth. Incidence 33.4-47.4 deg on this frame.
- Traps: RFI likelihood fields ~6.7e10 despite [0,1] range -> ignore. isJointObservation HDF5 True vs CMR False mismatch.

Top AOIs: 1 Tulare (2 tracks, 11 mo, GUNW, OPERA dense), 2 NJ Pine Barrens (T69 D + T133 A also cover Meadowlands + Barnegat), 3 Rainier (T172F65 D 29 dates, snow season, layover risk). Moses Lake alt for crops (Jun-Oct).
