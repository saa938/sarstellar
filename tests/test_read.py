"""Remote GCOV / RTC reads: retries, windowing, block averaging.

The offline tests build tiny synthetic GCOV HDF5 files and GeoTIFFs and serve them through a fake
fsspec session, so they cover the real h5py / rasterio code paths without a network. The one
`live` test reads a real NISAR granule from ASF (needs ~/_netrc, run with `-m live`).
"""

import io
import logging
from types import SimpleNamespace

import h5py
import numpy as np
import pytest

from sarstellar import read
from sarstellar.grid import grid_for_bbox
from sarstellar.read import (
    https_fs,
    open_remote_h5,
    read_gcov_blocks,
    read_gcov_window,
    with_retries,
)
from sarstellar.types import Grid

# --- fakes -------------------------------------------------------------------------------------


@pytest.fixture
def sleeps(monkeypatch):
    """Record backoff sleeps instead of waiting."""
    recorded: list[float] = []
    monkeypatch.setattr(read.time, "sleep", recorded.append)
    return recorded


class _FakeRemoteFile(io.RawIOBase):
    """A file whose bytes arrive through `cache.fetcher`, like an fsspec blockcache file."""

    def __init__(self, data: bytes, fs: "FakeFS"):
        self.data, self.fs, self.pos = data, fs, 0
        self.cache = SimpleNamespace(fetcher=self._fetch)

    def _fetch(self, start, stop):
        self.fs.fetch_calls += 1
        if self.fs.fetch_calls <= self.fs.fail_first:
            raise ConnectionError("502 Bad Gateway")
        return self.data[start:stop]

    def readable(self):
        return True

    def seekable(self):
        return True

    def tell(self):
        return self.pos

    def seek(self, offset, whence=0):
        base = (0, self.pos, len(self.data))[whence]
        self.pos = base + offset
        return self.pos

    def readinto(self, buf):
        chunk = self.cache.fetcher(self.pos, self.pos + len(buf))
        buf[: len(chunk)] = chunk
        self.pos += len(chunk)
        return len(chunk)


class FakeFS:
    """Serves bytes by URL. The first `fail_first` fetches raise, like a flaky ASF server."""

    def __init__(self, files: dict[str, bytes], fail_first: int = 0):
        self.files, self.fail_first = files, fail_first
        self.fetch_calls = 0
        self.open_calls: list[tuple[str, dict]] = []

    def open(self, url, mode="rb", **kwargs):
        self.open_calls.append((url, kwargs))
        return _FakeRemoteFile(self.files[url], self)


# --- synthetic GCOV ----------------------------------------------------------------------------

URL = "https://fake.asf/NISAR/GCOV/G1/G1.h5"
BBOX = (-122.9990, 47.0000, -122.9975, 47.0012)  # ~110 x 130 m near the zone 10 central meridian


def _ground_value(x, y):
    """A value that depends only on ground position, so two frames agree where they overlap."""
    return 1.0 + (x - 400000.0) / 10.0 + (5300000.0 - y) / 10.0 * 1000.0


def write_gcov(path, *, x0, y0, nx, ny, epsg=32610, dx=10.0):
    """Write a minimal GCOV (HHHH, HVHV, mask) whose first pixel centre is (x0, y0)."""
    xs = x0 + dx * np.arange(nx)
    ys = y0 - dx * np.arange(ny)
    hh = _ground_value(xs[None, :], ys[:, None]).astype("float32")
    hv = hh / 10.0
    mask = np.full((ny, nx), 1, np.uint8)
    with h5py.File(path, "w", fs_strategy="page", fs_page_size=4096) as f:
        ident = f.create_group("science/LSAR/identification")
        ident["granuleId"] = np.bytes_(b"NISAR_FAKE_GRANULE")
        ident["zeroDopplerStartTime"] = np.bytes_(b"2026-07-13T03:09:56.000000000")
        ident["trackNumber"] = np.uint32(71)
        ident["frameNumber"] = np.uint32(64)
        ident["orbitPassDirection"] = np.bytes_(b"Descending")
        ident["compositeReleaseId"] = np.bytes_(b"P05023")
        ident["productVersion"] = np.bytes_(b"1.0.11")
        ident["isMixedMode"] = np.bytes_(b"False")
        ident["isFullFrame"] = np.bytes_(b"True")
        g = f.create_group("science/LSAR/GCOV/grids/frequencyA")
        g["projection"] = np.uint32(epsg)
        g["xCoordinateSpacing"] = dx
        g["yCoordinateSpacing"] = -dx
        g["xCoordinates"] = xs
        g["yCoordinates"] = ys
        chunks = (min(32, ny), min(32, nx))
        g.create_dataset("HHHH", data=hh, chunks=chunks)
        g.create_dataset("HVHV", data=hv, chunks=chunks)
        g.create_dataset("mask", data=mask, chunks=chunks)
        g["listOfPolarizations"] = np.array([b"HH", b"HV"])
        sw = f.create_group("science/LSAR/GCOV/metadata/sourceData/swaths/frequencyA")
        sw["acquiredRangeBandwidth"] = 40e6
        sw["processedRangeBandwidth"] = 40e6


def gcov_bytes(tmp_path, name="g.h5", **kw) -> bytes:
    p = tmp_path / name
    write_gcov(p, **kw)
    return p.read_bytes()


def frame_around(grid, margin_px=50, **kw):
    """Frame kwargs for a file whose lattice covers `grid` plus `margin_px` pixels on every side."""
    ny, nx = grid.shape
    return dict(
        x0=grid.xmin - margin_px * 10.0 + 5.0,
        y0=grid.ymax + margin_px * 10.0 - 5.0,
        nx=nx * 10 + 2 * margin_px,
        ny=ny * 10 + 2 * margin_px,
        **kw,
    )


# --- retries (Review Focus 4) --------------------------------------------------------------------


def test_retry_then_succeed(sleeps, caplog):
    calls = []

    def fetcher(start, stop):
        calls.append((start, stop))
        if len(calls) <= 2:
            raise ConnectionError("502 Bad Gateway")
        return b"x" * (stop - start)

    retries: list[str] = []
    with caplog.at_level(logging.WARNING, logger="sarstellar.read"):
        out = with_retries(fetcher, max_retries=6, retries=retries)(0, 4)
    assert out == b"xxxx"
    assert len(calls) == 3
    assert len(retries) == 2 and all("ConnectionError" in r for r in retries)
    assert sleeps == [1, 2]  # exponential backoff
    assert len([r for r in caplog.records if r.name == "sarstellar.read"]) == 2


def test_retry_exhausted_raises(sleeps):
    calls = []

    def fetcher(start, stop):
        calls.append(1)
        raise TimeoutError("read timed out")

    with pytest.raises(IOError, match="6 tries"):
        with_retries(fetcher, max_retries=6)(0, 4)
    assert len(calls) == 6
    assert sleeps == [1, 2, 4, 8, 16]  # no pointless sleep after the last failure


def test_open_remote_h5_retries_through_h5py(tmp_path, sleeps):
    grid = grid_for_bbox(BBOX, 32610)
    fs = FakeFS({URL: gcov_bytes(tmp_path, **frame_around(grid))}, fail_first=2)
    retries: list[str] = []
    f, h = open_remote_h5(URL, fs, retries=retries)
    try:
        assert h["science/LSAR/GCOV/grids/frequencyA/HHHH"].shape[0] > 0
    finally:
        h.close()
        f.close()
    assert len(retries) == 2 and sleeps == [1, 2]
    (_, kwargs), = fs.open_calls
    assert kwargs["cache_type"] == "blockcache" and kwargs["block_size"] == 8 * 2**20


def test_read_gcov_window_gives_up_with_oserror(tmp_path, sleeps):
    grid = grid_for_bbox(BBOX, 32610)
    fs = FakeFS({URL: gcov_bytes(tmp_path, **frame_around(grid))}, fail_first=10**6)
    with pytest.raises(OSError):  # a dead server surfaces as a clean error, not a crash
        read_gcov_window(URL, BBOX, fs)
    assert sleeps[:5] == [1, 2, 4, 8, 16]  # six tries, then it stopped


# --- read_gcov_window ----------------------------------------------------------------------------


def test_read_gcov_window_returns_aligned_window(tmp_path):
    grid = grid_for_bbox(BBOX, 32610)
    fs = FakeFS({URL: gcov_bytes(tmp_path, **frame_around(grid, margin_px=50))})
    meta, arrays, g = read_gcov_window(URL, BBOX, fs)
    assert g == grid
    ny, nx = grid.shape
    assert arrays["HH"].shape == arrays["HV"].shape == arrays["mask"].shape == (ny * 10, nx * 10)
    assert arrays["HH"].shape[0] % 10 == 0 and arrays["HH"].shape[1] % 10 == 0
    # every returned pixel sits at its expected ground position
    xc = grid.xmin + 5.0 + 10.0 * np.arange(nx * 10)
    yc = grid.ymax - 5.0 - 10.0 * np.arange(ny * 10)
    expected = _ground_value(xc[None, :], yc[:, None]).astype("float32")
    assert np.array_equal(arrays["HH"], expected)
    assert np.allclose(arrays["HV"], expected / 10.0)
    assert arrays["mask"].dtype == np.uint8 and (arrays["mask"] == 1).all()
    assert meta["crid"] == "P05023" and meta["epsg"] == 32610
    assert meta["track"] == 71 and meta["frame"] == 64 and meta["direction"] == "Descending"
    assert meta["date"] == "2026-07-13T03:09:56"
    assert meta["isMixedMode"] is False and meta["polarizations"] == ["HH", "HV"]
    assert meta["window_shape"] == [ny * 10, nx * 10] and meta["http_retries"] == []


def test_read_gcov_window_second_date_reuses_grid(tmp_path):
    grid = grid_for_bbox(BBOX, 32610)
    f1 = frame_around(grid, margin_px=50)
    # the second date's frame starts 30 m further west and 20 m further north on the same lattice
    f2 = dict(f1, x0=f1["x0"] - 30.0, y0=f1["y0"] + 20.0, nx=f1["nx"] + 10, ny=f1["ny"] + 10)
    files = {URL: gcov_bytes(tmp_path, "a.h5", **f1), URL + "2": gcov_bytes(tmp_path, "b.h5", **f2)}
    fs = FakeFS(files)
    _, a1, g1 = read_gcov_window(URL, BBOX, fs)
    _, a2, g2 = read_gcov_window(URL + "2", BBOX, fs, grid=g1)
    assert g2 == g1
    assert np.array_equal(a1["HH"], a2["HH"])  # same ground pixels despite different frame origins


def test_read_gcov_window_rejects_epsg_mismatch(tmp_path):
    grid_other_zone = grid_for_bbox(BBOX, 32611)
    grid = grid_for_bbox(BBOX, 32610)
    fs = FakeFS({URL: gcov_bytes(tmp_path, **frame_around(grid))})
    with pytest.raises(ValueError, match="EPSG differs"):
        read_gcov_window(URL, BBOX, fs, grid=grid_other_zone)


@pytest.mark.parametrize(
    "shift_x_m, message",
    [
        (3.0, "lattice"),  # pixels straddle the 100 m block edges
        (50000.0, "does not overlap"),  # the frame is 50 km east of the window
    ],
)
def test_read_gcov_window_rejects_unusable_frames(tmp_path, shift_x_m, message):
    grid = grid_for_bbox(BBOX, 32610)
    kw = frame_around(grid)
    kw["x0"] += shift_x_m
    fs = FakeFS({URL: gcov_bytes(tmp_path, **kw)})
    with pytest.raises(ValueError, match=message):
        read_gcov_window(URL, BBOX, fs)


def test_read_gcov_window_pads_window_that_overhangs_the_frame(tmp_path):
    grid = grid_for_bbox(BBOX, 32610)
    ny, nx = grid.shape
    kw = frame_around(grid, margin_px=0)
    kw["x0"] += 50.0  # the frame starts 50 m (5 px) inside the window's west edge
    kw["nx"] -= 5
    fs = FakeFS({URL: gcov_bytes(tmp_path, **kw)})
    _, arrays, _ = read_gcov_window(URL, BBOX, fs)
    assert arrays["HH"].shape == (ny * 10, nx * 10)
    assert np.isnan(arrays["HH"][:, :5]).all() and np.isfinite(arrays["HH"][:, 5:]).all()
    assert (arrays["mask"][:, :5] == 255).all() and (arrays["mask"][:, 5:] == 1).all()


# --- read_gcov_blocks (ruling R1) -----------------------------------------------------------------


def _fake_window(monkeypatch, hh, hv, mask, window_grid):
    """Replace `read_gcov_window` so the block maths can be tested on hand-made arrays."""
    meta = {"crid": "P05023"}
    arrays = {"HH": hh, "HV": hv, "mask": mask}

    def fake(url, bbox, fs, grid=None):  # same signature as read_gcov_window
        return meta, arrays, window_grid

    monkeypatch.setattr(read, "read_gcov_window", fake)
    return meta


def test_read_blocks_l30_subsample(monkeypatch):
    hh = np.ones((20, 20), "float32")
    hh[::3, ::3] = 2.0  # only every third pixel, in both directions, is bright
    grid = Grid(epsg=32610, xmin=500000.0, xmax=500200.0, ymin=5200000.0, ymax=5200200.0)
    meta = _fake_window(monkeypatch, hh, hh / 2, np.ones((20, 20), np.uint8), grid)
    got_meta, out, g = read_gcov_blocks(URL, BBOX, None)
    assert got_meta is meta and g is grid
    assert set(out) == {"HH", "HV", "HH30", "HV30", "valid_frac"}
    assert all(out[k].shape == (2, 2) for k in out)
    assert np.allclose(out["HH30"], 2.0) and np.allclose(out["HV30"], 1.0)
    assert ((out["HH"] > 1.0) & (out["HH"] < 2.0)).all()  # the full average dilutes the bright ones
    assert np.allclose(out["HH"][0, 0], (16 * 2.0 + 84 * 1.0) / 100)  # linear power, not dB


def test_valid_frac(monkeypatch):
    hh = np.full((20, 20), 3.0, "float32")
    hv = np.full((20, 20), 0.3, "float32")
    mask = np.ones((20, 20), np.uint8)
    mask[:5, :10] = 255  # block (0, 0): 50 px of fill -> 0.5, exactly the 50% minimum, kept
    hh[:3, 10:] = 0.0  # block (0, 1): 30 px with a non-positive HH -> 0.7
    hv[10:16, 10:] = np.nan  # block (1, 1): 60 px with NaN HV -> 0.4, below the 50% rule
    grid = Grid(epsg=32610, xmin=500000.0, xmax=500200.0, ymin=5200000.0, ymax=5200200.0)
    _fake_window(monkeypatch, hh, hv, mask, grid)
    _, out, _ = read_gcov_blocks(URL, BBOX, None)
    assert np.allclose(out["valid_frac"], [[0.5, 0.7], [1.0, 0.4]])
    assert np.isfinite(out["HH"][0, 0]) and np.isfinite(out["HV"][0, 1])
    assert np.isnan(out["HH"][1, 1]) and np.isnan(out["HV"][1, 1])  # too few valid pixels
    assert out["HH"][1, 0] == pytest.approx(3.0) and out["HV"][1, 0] == pytest.approx(0.3)


def test_read_blocks_end_to_end_from_file(tmp_path):
    grid = grid_for_bbox(BBOX, 32610)
    fs = FakeFS({URL: gcov_bytes(tmp_path, **frame_around(grid))})
    _, out, g = read_gcov_blocks(URL, BBOX, fs)
    assert g == grid and out["HH"].shape == grid.shape
    assert np.isfinite(out["HH"]).all() and np.allclose(out["valid_frac"], 1.0)


# --- https_fs ------------------------------------------------------------------------------------


@pytest.mark.parametrize(
    "env, strategy",
    [({"EARTHDATA_USERNAME": "u", "EARTHDATA_PASSWORD": "p"}, "environment"), ({}, "netrc")],
)
def test_https_fs_picks_login_strategy(monkeypatch, env, strategy):
    import earthaccess

    for key in ("EARTHDATA_USERNAME", "EARTHDATA_PASSWORD"):
        monkeypatch.delenv(key, raising=False)
    for key, value in env.items():
        monkeypatch.setenv(key, value)
    seen = {}

    def login(strategy, persist):
        seen.update(strategy=strategy, persist=persist)
        return SimpleNamespace(authenticated=True)

    monkeypatch.setattr(earthaccess, "login", login)
    monkeypatch.setattr(earthaccess, "get_fsspec_https_session", lambda: "session")
    assert https_fs() == "session"
    assert seen == {"strategy": strategy, "persist": False}


def test_https_fs_raises_when_login_fails(monkeypatch):
    import earthaccess

    monkeypatch.setattr(earthaccess, "login", lambda **kw: SimpleNamespace(authenticated=False))
    with pytest.raises(RuntimeError, match="Earthdata"):
        https_fs()


# --- live ----------------------------------------------------------------------------------------

KAISER_PRE = (
    "NISAR_L2_PR_GCOV_025_071_D_064_4005_DHDH_A_20260713T030956_20260713T031031_P05023_N_F_J_001"
)
KAISER_URL = (
    "https://nisar.asf.earthdatacloud.nasa.gov/NISAR/NISAR_L2_GCOV_PROVISIONAL_V1/"
    f"{KAISER_PRE}/{KAISER_PRE}.h5"
)
KAISER_SMALL_BBOX = (-119.20, 48.15, -119.15, 48.19)  # ~3.7 x 4.4 km inside the Kaiser box


@pytest.mark.live
def test_live_kaiser_window():
    fs = https_fs()
    meta, arrays, grid = read_gcov_window(KAISER_URL, KAISER_SMALL_BBOX, fs)
    assert meta["crid"] == "P05023"
    assert meta["epsg"] == grid.epsg == 32610  # zone 10 file although the site is in zone 11
    hh = arrays["HH"]
    assert hh.shape == arrays["HV"].shape == arrays["mask"].shape
    assert hh.shape[0] % 10 == 0 and hh.shape[1] % 10 == 0
    assert hh.shape == (grid.shape[0] * 10, grid.shape[1] * 10)
    assert ((arrays["mask"] >= 1) & (arrays["mask"] <= 254)).mean() > 0.9
    # the same window as 1-ha blocks: plausible L-band backscatter over a burned forest
    _, blocks, g = read_gcov_blocks(KAISER_URL, KAISER_SMALL_BBOX, fs, grid=grid)
    assert g == grid and blocks["HH"].shape == grid.shape
    assert np.isfinite(blocks["HV"]).mean() > 0.9 and blocks["valid_frac"].mean() > 0.9
    hv_db = 10 * np.log10(np.nanmedian(blocks["HV"]))
    assert -30 < hv_db < -5
