"""Shared contract types for every SARstellar track.

The JSON produced by `Result.to_json()` / `Job.to_json()` is the API the web app
consumes (it mirrors `web/src/types.ts`), so the key names here are frozen.
The one rename: the Python attribute `ChangeArea.cls` is the JSON key `"class"`,
because `class` is a reserved word in Python.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import date, datetime
from typing import Any


class NoUsablePasses(Exception):
    """No calibrated NISAR stack covers the requested box and dates."""


@dataclass
class Granule:
    """One NISAR GCOV granule returned by a CMR search."""

    ur: str
    url: str
    collection: str
    start: datetime
    track: int
    frame: int
    direction: str  # "A" ascending or "D" descending
    bandwidth_mhz: float
    crid: str
    counter: int
    mixed_mode: bool
    size_gb: float


@dataclass
class Stack:
    """Granules that share track, direction, bandwidth and processing CRID."""

    track: int
    direction: str
    bandwidth_mhz: float
    crid: str
    granules: list[Granule]

    @property
    def dates(self) -> list[date]:
        """Distinct acquisition dates, oldest first (several frames can share a date)."""
        return sorted({g.start.date() for g in self.granules})


@dataclass
class Grid:
    """A north-up raster grid in a projected CRS, `res` metres per pixel."""

    epsg: int
    xmin: float
    xmax: float
    ymin: float
    ymax: float
    res: float = 100.0

    @property
    def shape(self) -> tuple[int, int]:
        """(ny, nx), the order numpy arrays use."""
        return (
            round((self.ymax - self.ymin) / self.res),
            round((self.xmax - self.xmin) / self.res),
        )

    def transform(self):
        """Affine transform from (col, row) pixel indices to projected x, y."""
        from rasterio.transform import from_origin  # lazy: keeps this module cheap to import

        return from_origin(self.xmin, self.ymax, self.res, self.res)


@dataclass
class Evidence:
    """One labelled number behind a classification, with an optional interval."""

    label: str
    value: float | str
    ci: list[float] | None = None
    unit: str = ""
    note: str = ""

    def to_json(self) -> dict[str, Any]:
        return asdict(self)

    @staticmethod
    def from_json(d: dict[str, Any]) -> Evidence:
        ci = d["ci"]
        return Evidence(
            label=d["label"],
            value=d["value"],
            ci=None if ci is None else list(ci),
            unit=d["unit"],
            note=d["note"],
        )


@dataclass
class ChangeArea:
    """One detected change polygon. `cls` is serialized as the JSON key `class`."""

    id: str
    geometry: dict[str, Any]  # GeoJSON Polygon or MultiPolygon
    agreement: str  # "L", "C" or "both"
    cls: str
    area_ha: float
    confidence: float  # 0..1
    confidence_label: str  # "High", "Medium" or "Low"
    p_value: float
    change_date: str | None
    evidence: list[Evidence]
    plain_text: str
    series: dict[str, list[Any]]  # keys: dates, HH, HV, VV, VH

    def to_json(self) -> dict[str, Any]:
        # asdict keeps field order; only the `cls` key is renamed.
        return {("class" if k == "cls" else k): v for k, v in asdict(self).items()}

    @staticmethod
    def from_json(d: dict[str, Any]) -> ChangeArea:
        return ChangeArea(
            id=d["id"],
            geometry=d["geometry"],
            agreement=d["agreement"],
            cls=d["class"],
            area_ha=d["area_ha"],
            confidence=d["confidence"],
            confidence_label=d["confidence_label"],
            p_value=d["p_value"],
            change_date=d["change_date"],
            evidence=[Evidence.from_json(e) for e in d["evidence"]],
            plain_text=d["plain_text"],
            series=d["series"],
        )


def _empty_exports() -> dict[str, Any]:
    return {"geotiff": None, "csv": None, "notebook": None}


def _empty_people() -> dict[str, Any]:
    return {"svi_tracts": []}


@dataclass(kw_only=True)
class Result:
    """A finished analysis. Fields are listed in contract key order."""

    bbox: list[float]  # [west, south, east, north]
    message: str | None = None
    fixture: bool = False
    nisar: dict[str, Any]  # {track, direction, dates}
    s1: dict[str, Any] | None = None  # {track, dates} or None
    overlays: dict[str, Any]  # five PNG urls + bounds (UL, UR, LR, LL)
    areas: list[ChangeArea] = field(default_factory=list)
    people: dict[str, Any] = field(default_factory=_empty_people)
    exports: dict[str, Any] = field(default_factory=_empty_exports)

    def to_json(self) -> dict[str, Any]:
        payload = asdict(self)  # deep copy, so the payload never aliases this object
        payload["areas"] = [a.to_json() for a in self.areas]  # applies the cls -> class rename
        return payload

    @staticmethod
    def from_json(d: dict[str, Any]) -> Result:
        return Result(
            bbox=list(d["bbox"]),
            message=d["message"],
            fixture=d["fixture"],
            nisar=d["nisar"],
            s1=d["s1"],
            overlays=d["overlays"],
            areas=[ChangeArea.from_json(a) for a in d["areas"]],
            people=d["people"],
            exports=d["exports"],
        )


@dataclass
class Job:
    """An analysis job as the API reports it. `status` is queued/running/done/error."""

    job_id: str
    status: str = "queued"
    progress: float = 0.0  # 0..1
    message: str = ""
    result: Result | None = None

    def to_json(self) -> dict[str, Any]:
        return {
            "job_id": self.job_id,
            "status": self.status,
            "progress": self.progress,
            "message": self.message,
            "result": None if self.result is None else self.result.to_json(),
        }

    @staticmethod
    def from_json(d: dict[str, Any]) -> Job:
        result = d["result"]
        return Job(
            job_id=d["job_id"],
            status=d["status"],
            progress=d["progress"],
            message=d["message"],
            result=None if result is None else Result.from_json(result),
        )
