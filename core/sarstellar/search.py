"""Find NISAR GCOV and OPERA RTC-S1 passes through NASA CMR and turn them into clean series.

CMR search needs no login. The hard part is not the query but the data traps the search
results hide (see docs/research/data-spike.md):

* BETA granules leak into generic NISAR searches, so we query by the two production
  collection short names only, and drop anything else that still comes back.
* Deliveries are repeated as `_001`, `_002`: keep the highest counter.
* 5 MHz-only passes and mixed-mode passes cannot join a 40 MHz (or 20 MHz) series.
* CRID P05023 (provisional) and P05036 (validated) may differ radiometrically, so a
  series never mixes them.
* Frame footprints shift from pass to pass, so a series is per track and direction,
  found by box, never per frame.
"""

from __future__ import annotations

import logging
import re
import time
from collections import defaultdict
from collections.abc import Sequence
from datetime import UTC, date, datetime, timedelta
from typing import Any

import requests

from sarstellar.types import Granule, Stack

log = logging.getLogger(__name__)

CMR_URL = "https://cmr.earthdata.nasa.gov/search/granules.umm_json"

# The only NISAR collections we ever query. NISAR_L2_GCOV_BETA_V1 is deliberately absent.
GCOV_COLLECTIONS = ("NISAR_L2_GCOV_PROVISIONAL_V1", "NISAR_L2_GCOV_V1")
RTC_COLLECTION = "OPERA_L2_RTC-S1_V1"

MIN_BANDWIDTH_MHZ = 20.0  # below this (the 5 MHz frequency B) pixels are 80 m, not 10 m

PAGE_SIZE = 2000  # CMR's maximum
CMR_ATTEMPTS = 3
CMR_TIMEOUT_S = 120

Box = Sequence[float]  # (west, south, east, north)

# NISAR granule names end in  ..._<pol code>_<mode flag>_<start>_<end>_<CRID>_N_F_J_<counter>
# where the mode flag is "A" normally and "M" for the full-frame product of a mixed-mode pass.
_GCOV_UR_TAIL = re.compile(
    r"_(?P<pol>[A-Z0-9]{4})_(?P<flag>[A-Z])_\d{8}T\d{6}_\d{8}T\d{6}"
    r"_(?P<crid>[A-Z]\d{5})_[A-Z]_[A-Z]_[A-Z]_(?P<counter>\d{3})$"
)

# OPERA_L2_RTC-S1_T137-292328-IW2_20260715T015830Z_20261010T052116Z_S1D_30_v1.0
_RTC_UR = re.compile(
    r"^OPERA_L2_RTC-S1_(?P<burst>T\d{3}-\d{6}-IW\d)_(?P<acq>\d{8})T\d{6}Z"
    r"_(?P<produced>\d{8}T\d{6}Z)_S1[A-Z]_30_v[\d.]+$"
)


# --- CMR plumbing ------------------------------------------------------------------------


def _check_box(bbox: Box) -> tuple[float, float, float, float]:
    if len(bbox) != 4:
        raise ValueError("bbox must be (west, south, east, north)")
    w, s, e, n = (float(v) for v in bbox)
    if not (w < e and s < n):
        raise ValueError(f"bbox must have west < east and south < north, got {tuple(bbox)}")
    return w, s, e, n


def _box_param(bbox: Box) -> str:
    return ",".join(str(v) for v in _check_box(bbox))


def _temporal_param(start: date, end: date) -> str:
    if start > end:
        raise ValueError(f"start {start} is after end {end}")
    return f"{start:%Y-%m-%d}T00:00:00Z,{end:%Y-%m-%d}T23:59:59Z"


def _get(params: list[tuple[str, str]], search_after: str | None) -> requests.Response:
    """One CMR request. Server errors and dropped connections are retried with backoff."""
    headers = {"CMR-Search-After": search_after} if search_after else {}
    for attempt in range(1, CMR_ATTEMPTS + 1):
        last = attempt == CMR_ATTEMPTS
        try:
            resp = requests.get(CMR_URL, params=params, headers=headers, timeout=CMR_TIMEOUT_S)
        except (requests.ConnectionError, requests.Timeout):
            if last:
                raise
        else:
            if resp.status_code < 500 or last:
                resp.raise_for_status()
                return resp
        time.sleep(2 ** (attempt - 1))
    raise AssertionError("unreachable")  # the loop always returns or raises on its last attempt


def _cmr_items(params: list[tuple[str, str]]) -> list[dict[str, Any]]:
    """Every CMR item for `params`, following CMR-Search-After across pages."""
    items: list[dict[str, Any]] = []
    search_after: str | None = None
    while True:
        resp = _get(params, search_after)
        page = resp.json()["items"]
        items.extend(page)
        search_after = resp.headers.get("CMR-Search-After")
        if not page or not search_after or len(page) < PAGE_SIZE:
            return items


# --- NISAR GCOV ----------------------------------------------------------------------------


def gcov_query_params(bbox: Box, start: date, end: date) -> list[tuple[str, str]]:
    """CMR parameters for a GCOV search: the two production short names, nothing else."""
    return [
        *(("short_name", name) for name in GCOV_COLLECTIONS),
        ("bounding_box", _box_param(bbox)),
        ("temporal", _temporal_param(start, end)),
        ("page_size", str(PAGE_SIZE)),
    ]


def _attrs(umm: dict[str, Any]) -> dict[str, list[str]]:
    return {a["Name"]: [str(v) for v in a["Values"]] for a in umm.get("AdditionalAttributes", [])}


def _first(attrs: dict[str, list[str]], name: str) -> str | None:
    values = attrs.get(name)
    return values[0] if values else None


def _bandwidth_mhz(attrs: dict[str, list[str]]) -> float:
    """Range bandwidth of the main frequency. A 5 MHz-only pass has no frequency A at all."""
    freq_a = _first(attrs, "FREQUENCY_A_RANGE_BANDWIDTH")
    if freq_a is not None:
        return float(freq_a)
    concat = _first(attrs, "RANGE_BANDWIDTH_CONCAT")  # "40+5", "20+5", or just "5"
    if concat:
        return float(concat.split("+")[0])
    freq_b = _first(attrs, "FREQUENCY_B_RANGE_BANDWIDTH")
    if freq_b is not None:
        return float(freq_b)
    raise ValueError("record has no range bandwidth attribute")


def _identifier(
    umm: dict[str, Any], *, kind: str | None = None, name: str | None = None
) -> str | None:
    for ident in umm.get("DataGranule", {}).get("Identifiers", []):
        if (kind and ident.get("IdentifierType") == kind) or (
            name and ident.get("IdentifierName") == name
        ):
            return str(ident["Identifier"])
    return None


def _hdf5_url(umm: dict[str, Any], filename: str) -> str:
    """The granule's own HDF5 over HTTPS (not the S3 link, a browse image or QA_STATS.h5)."""
    for link in umm.get("RelatedUrls", []):
        url = link.get("URL", "")
        if (
            link.get("Type") == "GET DATA"
            and url.startswith("https://")
            and url.endswith("/" + filename)
        ):
            return url
    raise ValueError(f"no HDF5 download link for {filename}")


def _size_gb(umm: dict[str, Any], filename: str) -> float:
    files = umm.get("DataGranule", {}).get("ArchiveAndDistributionInformation", [])
    for f in files:
        if f.get("Name") == filename and f.get("SizeInBytes"):
            return f["SizeInBytes"] / 1e9
    return 0.0


def _utc(text: str) -> datetime:
    when = datetime.fromisoformat(text)
    return when if when.tzinfo else when.replace(tzinfo=UTC)


def parse_umm(umm: dict[str, Any]) -> Granule:
    """Turn one CMR UMM-G record (the `umm` part of an item) into a `Granule`.

    `mixed_mode` is True for the "M" full-frame product of a mixed-mode pass and for every
    partial-frame granule (FULL_FRAME FALSE). Neither can join a same-mode series: the M
    product has a different bandwidth or polarization set from its neighbours, and a
    partial frame covers only part of the box (in mixed-mode passes it carries the
    other-mode piece; elsewhere it is a short fragment at the start or end of a pass).

    Raises ValueError for a record that is not a usable GCOV granule.
    """
    ur = umm.get("GranuleUR", "")
    tail = _GCOV_UR_TAIL.search(ur)
    if tail is None:
        raise ValueError(f"unrecognised NISAR GCOV granule name: {ur!r}")
    attrs = _attrs(umm)
    try:
        track = int(attrs["TRACK_NUMBER"][0])
        frame = int(attrs["FRAME_NUMBER"][0])
        direction = attrs["ASCENDING_DESCENDING"][0][0].upper()
        start = _utc(umm["TemporalExtent"]["RangeDateTime"]["BeginningDateTime"])
        collection = umm["CollectionReference"]["ShortName"]
    except (KeyError, IndexError) as exc:
        raise ValueError(f"GCOV record {ur} is missing {exc}") from exc

    filename = ur + ".h5"
    counter = _identifier(umm, name="ProductCounter") or tail["counter"]
    return Granule(
        ur=ur,
        url=_hdf5_url(umm, filename),
        collection=collection,
        start=start,
        track=track,
        frame=frame,
        direction=direction,
        bandwidth_mhz=_bandwidth_mhz(attrs),
        crid=_identifier(umm, kind="CRID") or tail["crid"],
        counter=int(counter),
        mixed_mode=tail["flag"] == "M" or _first(attrs, "FULL_FRAME") == "FALSE",
        size_gb=_size_gb(umm, filename),
    )


def search_gcov(bbox: Box, start: date, end: date) -> list[Granule]:
    """Every NISAR GCOV granule over `bbox` acquired from `start` to `end` (inclusive).

    Raw result, oldest first: duplicates and unusable modes are still in it. Use
    `build_stacks` to get series. Records that cannot be parsed are logged and skipped.
    """
    items = _cmr_items(gcov_query_params(bbox, start, end))
    granules: list[Granule] = []
    for item in items:
        try:
            g = parse_umm(item["umm"])
        except ValueError as exc:
            log.warning("skipping CMR record: %s", exc)
            continue
        if g.collection in GCOV_COLLECTIONS:  # belt and braces: never let BETA through
            granules.append(g)
    return sorted(granules, key=lambda g: (g.start, g.track, g.frame, g.crid, g.counter))


def dedupe(gs: Sequence[Granule]) -> list[Granule]:
    """Keep the highest-counter delivery of each acquisition (`_002` replaces `_001`).

    An acquisition is the same track, frame, start time and mode under the same CRID. The
    same pass reprocessed under a new CRID is a different product and is kept.
    """
    best: dict[tuple, Granule] = {}
    for g in gs:
        key = (g.track, g.direction, g.frame, g.start, g.bandwidth_mhz, g.crid, g.mixed_mode)
        if key not in best or g.counter > best[key].counter:
            best[key] = g
    return sorted(best.values(), key=lambda g: (g.start, g.track, g.frame, g.crid))


def build_stacks(gs: Sequence[Granule]) -> list[Stack]:
    """Group granules into same-mode series, most dates first.

    One stack per (track, direction, bandwidth, CRID). Granules narrower than 20 MHz or
    in mixed-mode passes are dropped, and duplicate deliveries are removed first.
    """
    groups: dict[tuple[int, str, float, str], list[Granule]] = defaultdict(list)
    for g in dedupe(gs):
        if g.mixed_mode or g.bandwidth_mhz < MIN_BANDWIDTH_MHZ:
            continue
        groups[(g.track, g.direction, g.bandwidth_mhz, g.crid)].append(g)

    stacks = [
        Stack(
            track=track,
            direction=direction,
            bandwidth_mhz=bandwidth,
            crid=crid,
            granules=sorted(members, key=lambda g: (g.start, g.frame)),
        )
        for (track, direction, bandwidth, crid), members in groups.items()
    ]
    # Most dates first; on a tie the more recent series, then a fixed order so runs repeat.
    stacks.sort(
        key=lambda s: (-len(s.dates), -s.dates[-1].toordinal(), s.track, s.direction, s.crid)
    )
    return stacks


def granules_on(stack: Stack, day: date) -> list[Granule]:
    """The stack's granules acquired on `day`, lowest frame first (frames can share a date)."""
    return sorted((g for g in stack.granules if g.start.date() == day), key=lambda g: g.frame)


def _nearest(days: list[date], target: date) -> date:
    return min(days, key=lambda d: (abs((d - target).days), d))  # ties go to the earlier date


def pick_pair(stack: Stack, dates: tuple[date, date] | None = None) -> tuple[Granule, Granule]:
    """Choose the (before, after) granules to compare.

    With no `dates`, the stack's earliest and latest acquisitions. With `dates`, the
    acquisitions nearest to each requested date (so a date inside a data gap snaps to
    a real pass). The two are always different acquisition dates: if both requested dates
    land on the same pass, ValueError is raised instead of returning a pair of one date.
    """
    days = stack.dates
    if len(days) < 2:
        raise ValueError(f"a pair needs at least two acquisition dates, stack has {len(days)}")
    if dates is None:
        first, last = days[0], days[-1]
    else:
        early, late = sorted(dates)
        first, last = _nearest(days, early), _nearest(days, late)
        if first == last:
            raise ValueError(
                f"requested dates {early} and {late} both resolve to the same acquisition "
                f"({first}); pick dates on either side of a different pass"
            )
    return granules_on(stack, first)[0], granules_on(stack, last)[0]


# --- OPERA RTC-S1 (Sentinel-1) -------------------------------------------------------------


def rtc_query_params(bbox: Box, around: date, max_days: int) -> list[tuple[str, str]]:
    window = timedelta(days=max_days)
    return [
        ("short_name", RTC_COLLECTION),
        ("bounding_box", _box_param(bbox)),
        ("temporal", _temporal_param(around - window, around + window)),
        ("page_size", str(PAGE_SIZE)),
    ]


def _rtc_links(umm: dict[str, Any]) -> tuple[str | None, str | None]:
    """HTTPS URLs of the burst's VV and VH GeoTIFFs."""
    vv = vh = None
    for link in umm.get("RelatedUrls", []):
        url = link.get("URL", "")
        if link.get("Type") != "GET DATA" or not url.startswith("https://"):
            continue
        if url.endswith("_VV.tif"):
            vv = url
        elif url.endswith("_VH.tif"):
            vh = url
    return vv, vh


def search_rtc_s1(bbox: Box, around: date, max_days: int = 6) -> list[dict[str, Any]]:
    """OPERA RTC-S1 scenes over `bbox` within `max_days` of `around`, nearest date first.

    One dict per Sentinel-1 track and date: {"track": int, "date": date, "urls_vv": [...],
    "urls_vh": [...]}. A pass over a box is delivered as several bursts, so each list holds
    one GeoTIFF per burst (sorted by burst, so VV and VH line up). If a burst was produced
    twice, only the newest delivery is kept.
    """
    if max_days < 0:
        raise ValueError("max_days must not be negative")
    items = _cmr_items(rtc_query_params(bbox, around, max_days))

    newest: dict[tuple[int, date, str], tuple[str, tuple[str | None, str | None]]] = {}
    for item in items:
        umm = item["umm"]
        name = _RTC_UR.match(umm.get("GranuleUR", ""))
        if name is None:
            log.warning("skipping unrecognised RTC-S1 record %r", umm.get("GranuleUR"))
            continue
        acquired = datetime.strptime(name["acq"], "%Y%m%d").date()
        if abs((acquired - around).days) > max_days:
            continue
        path = _first(_attrs(umm), "PATH_NUMBER")
        track = int(path) if path else int(name["burst"][1:4])
        key = (track, acquired, name["burst"])
        if key not in newest or name["produced"] > newest[key][0]:
            newest[key] = (name["produced"], _rtc_links(umm))

    by_pass: dict[tuple[int, date], list[tuple[str, str | None, str | None]]] = defaultdict(list)
    for (track, acquired, burst), (_produced, (vv, vh)) in newest.items():
        by_pass[(track, acquired)].append((burst, vv, vh))

    scenes = []
    for (track, acquired), bursts in by_pass.items():
        bursts.sort()
        urls_vv = [vv for _b, vv, _vh in bursts if vv]
        urls_vh = [vh for _b, _vv, vh in bursts if vh]
        if urls_vv or urls_vh:
            scenes.append(
                {"track": track, "date": acquired, "urls_vv": urls_vv, "urls_vh": urls_vh}
            )
    scenes.sort(key=lambda r: (abs((r["date"] - around).days), r["date"], r["track"]))
    return scenes
