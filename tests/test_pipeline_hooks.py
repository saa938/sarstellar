"""Hooks that the job API adds to `run_box`: the block sink and the too-small-box message."""

from __future__ import annotations

import numpy as np

from sarstellar import features, pipeline
from sarstellar.grid import grid_for_bbox
from test_features import DAYS, EPSG
from test_pipeline import (
    NO_VALID,
    Scene,
    offline_refs,  # noqa: F401  (autouse fixture: no network in these tests)
    run,
)

TOO_SMALL = "This box is too small to analyse; draw at least about 2 km on a side."
TINY = (-119.20, 48.15, -119.188, 48.159)  # about 0.9 km x 1 km: under 200 blocks, all valid


def test_tiny_valid_box_says_too_small(monkeypatch):
    ny, nx = grid_for_bbox(TINY, EPSG).shape
    assert ny * nx < 200  # fewer blocks than the ENL estimate needs
    result, _ = run(monkeypatch, Scene(DAYS, TINY), bbox=TINY)
    assert result.areas == [] and result.message == TOO_SMALL
    assert TOO_SMALL == pipeline.TOO_SMALL_MESSAGE


def test_mostly_fill_box_still_says_no_valid_data(monkeypatch):
    result, _ = run(monkeypatch, Scene(DAYS, ocean_cols=71))
    assert result.message == NO_VALID


def test_blocks_sink_gets_block_set_and_masks(monkeypatch):
    calls = []
    result, _ = run(monkeypatch, blocks_sink=lambda *args: calls.append(args))
    assert len(calls) == 1
    bs, changed_l, changed_c = calls[0]
    assert isinstance(bs, features.BlockSet)
    assert changed_l.dtype == bool and changed_l.shape == bs.grid.shape
    assert changed_c.shape == bs.grid.shape
    assert changed_l.sum() >= 15  # the 20-block HV patch
    assert result.areas  # the result itself is unchanged by the sink


def test_blocks_sink_not_called_for_empty_box(monkeypatch):
    calls = []
    run(monkeypatch, Scene(DAYS, ocean_cols=71), blocks_sink=lambda *a: calls.append(a))
    assert calls == []


def test_valid_fraction_helper_ignores_other_zone():
    ok = np.ones((4, 4))
    passes = [
        ({"epsg": 32610, "date": "2026-07-13T00:00:00"}, {"valid_frac": ok}),
        ({"epsg": 32611, "date": "2026-07-13T00:00:00"}, {"valid_frac": ok * 0}),
        ({"epsg": 32610, "date": "2026-07-25T00:00:00"}, {"valid_frac": ok}),
    ]
    assert pipeline._valid_fraction(passes) == 1.0
