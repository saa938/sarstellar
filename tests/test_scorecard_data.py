"""The batch collector reuses the core engine with a pinned fair pair."""

import numpy as np
from modal_app.scorecard_data import collect_site

from sarstellar import features
from test_features import BBOX, Fakes, Synth
from test_features_pair import DAYS5


def test_collector_pins_catalog_pair_and_preserves_whole_box_flags(monkeypatch):
    synth = Synth(DAYS5)
    fakes = Fakes(monkeypatch, synth, DAYS5)
    calls = []

    def feature_fn(bbox, days, **kw):
        calls.append(kw.copy())
        kw["read_passes"] = fakes.read_passes
        return features.block_features(bbox, days, **kw)

    def labels(site, grid):
        result = np.full(grid.shape, "none", dtype="<U16")
        result[20:32, 20:32] = "forest_loss"
        result[:10] = ""  # unknown reference does not alter the box's BH calculation
        return result

    urs = [fakes.granules[i].ur for i in (0, -1)]
    site = {"id": "synthetic", "state": "WA", "kind": "forest_loss", "split": "train",
            "bbox": BBOX, "nisar_pair": urs, "s1": None,
            "meta": {"pair_dates": [str(DAYS5[0]), str(DAYS5[-1])],
                     "track": 71, "direction": "A", "crid": "P05023"}}
    table = collect_site(site, feature_fn=feature_fn, label_fn=labels)
    assert calls[0]["only_dates"] == [DAYS5[0], DAYS5[-1]]
    assert calls[0]["pair_urs"] == urs and "only_dates" not in calls[1]
    assert table.series_dates.eq(5).all()
    assert table.comparable.eq(False).all()  # missing C never enters a fusion cohort
    assert table.flag_L.sum() > 0
    assert np.isfinite(table.rel_HH30).any()
    assert len(table) == synth.L[DAYS5[0]]["HH"].size
