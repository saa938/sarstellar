"""`block_features` pinned to one stack and one pair of dates (the scorecard's fair comparison)."""

from __future__ import annotations

from datetime import timedelta

import pytest

from sarstellar import features
from sarstellar.types import NoUsablePasses
from test_features import BBOX, DAYS, Fakes, Synth
from test_search import make_granule

DAYS5 = [DAYS[0] + timedelta(days=12 * i) for i in range(5)]


def _run(monkeypatch, **kw):
    synth = Synth(DAYS5)
    other = [make_granule(d, track=99) for d in DAYS5]  # a longer-named track that must be ignored
    fakes = Fakes(monkeypatch, synth, DAYS5, extra_granules=other)
    bs = features.block_features(BBOX, (DAYS5[0], DAYS5[-1]), read_passes=fakes.read_passes, **kw)
    return bs, fakes


def test_only_dates_reads_exactly_the_pair(monkeypatch):
    bs, fakes = _run(monkeypatch, stack_key=(71, "A", "P05023"), only_dates=[DAYS5[0], DAYS5[-1]])
    assert bs.dates == [DAYS5[0], DAYS5[-1]] and bs.stack.track == 71
    read = [g.start.date() for g in fakes.read_calls[0][0]]
    assert read == [DAYS5[0], DAYS5[-1]]


def test_stack_key_picks_the_named_stack_even_if_another_ties(monkeypatch):
    bs, _ = _run(monkeypatch, stack_key=(99, "A", "P05023"))
    assert bs.stack.track == 99 and bs.dates == DAYS5


def test_unknown_stack_or_missing_date_is_no_usable_passes(monkeypatch):
    with pytest.raises(NoUsablePasses):
        _run(monkeypatch, stack_key=(5, "A", "P05023"))
    with pytest.raises(NoUsablePasses):
        _run(monkeypatch, stack_key=(71, "A", "P05023"),
             only_dates=[DAYS5[0], DAYS5[-1] + timedelta(days=1)])


def test_catalog_pair_identifiers_must_exist_in_the_selected_stack(monkeypatch):
    with pytest.raises(NoUsablePasses):
        _run(monkeypatch, pair_urs=["not-an-existing-granule"])
