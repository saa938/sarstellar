"""Explanations: a deterministic template, and an LLM that may only reword it."""

import json
from types import SimpleNamespace

import pytest

from sarstellar.explain import MODEL, SYSTEM_PROMPT, explain, template_text
from sarstellar.types import ChangeArea, Evidence


def make_area(**kw) -> ChangeArea:
    base = {
        "id": "a1",
        "geometry": {"type": "Polygon", "coordinates": [[[0, 0], [1, 0], [1, 1], [0, 0]]]},
        "agreement": "L",
        "cls": "forest_loss",
        "area_ha": 12.4,
        "confidence": 0.9,
        "confidence_label": "High",
        "p_value": 0.001,
        "change_date": "2026-09-02",
        "evidence": [
            Evidence("HV change", -3.5, [-4.1, -2.9], "dB", "NISAR L-band"),
            Evidence("HH change", -0.5, None, "dB", "NISAR L-band"),
            Evidence("Rule fired", "HV fell at least 3 dB", None, "", "NISAR disturbance ATBD"),
        ],
        "plain_text": "",
        "series": {"dates": [], "HH": [], "HV": [], "VV": [], "VH": []},
    }
    base.update(kw)
    return ChangeArea(**base)


class FakeClient:
    """Records the call and returns canned text, like anthropic.Anthropic().messages."""

    def __init__(self, text="Reworded by the model."):
        self.calls = []
        self.text = text
        self.messages = self

    def create(self, **kwargs):
        self.calls.append(kwargs)
        return SimpleNamespace(content=[SimpleNamespace(type="text", text=self.text)])


class RaisingClient:
    def __init__(self, exc=None):
        self.messages = self
        self.exc = exc if exc is not None else RuntimeError("503 overloaded")

    def create(self, **kwargs):
        raise self.exc


# ---- template ------------------------------------------------------------------------------


def test_template_contains_numbers():
    text = template_text(make_area())
    assert "-3.5" in text  # the dHV value
    assert "only NISAR" in text
    assert "12.4" in text  # area in hectares
    assert "forest" in text.lower()
    assert text.count(".") >= 2  # a few plain sentences, no markdown or JSON


def test_template_agreement_wording():
    assert "both NISAR and Sentinel-1" in template_text(make_area(agreement="both"))
    c = template_text(make_area(agreement="C"))
    assert "only Sentinel-1" in c and "only NISAR" not in c


def test_template_names_every_class():
    from sarstellar.rules import CLASSES

    for cls in CLASSES:
        text = template_text(make_area(cls=cls))
        assert text.strip() and "_" not in text  # no raw class codes leaking into prose


def test_template_for_uncertain_says_so_and_flags_freeze():
    area = make_area(
        cls="uncertain",
        confidence_label="Low",
        evidence=[
            Evidence("HV change", -3.0, None, "dB", ""),
            Evidence("Minimum temperature", -4.0, None, "C", "possible freeze: both bands fell"),
        ],
    )
    text = template_text(area)
    assert "uncertain" in text.lower()
    assert "freeze" in text.lower()
    assert "low" in text.lower()


def test_template_survives_missing_numbers():
    text = template_text(make_area(evidence=[]))
    assert text.strip()


# ---- the LLM path --------------------------------------------------------------------------


def test_llm_text_is_used_and_call_is_shaped_as_specified():
    client = FakeClient("A patch of forest about 12 ha was cleared.")
    area = make_area()
    assert explain(area, client=client) == "A patch of forest about 12 ha was cleared."
    (call,) = client.calls
    assert call["model"] == MODEL == "claude-sonnet-5-5"
    assert call["max_tokens"] == 200
    assert call["system"] == SYSTEM_PROMPT
    assert "2–3 plain sentences" in SYSTEM_PROMPT
    assert "Do not change the classification" in SYSTEM_PROMPT
    (message,) = call["messages"]
    assert message["role"] == "user"
    payload = json.loads(message["content"])
    assert payload["class"] == "forest_loss"
    assert payload["evidence"][0]["value"] == -3.5


def test_llm_error_falls_back():
    area = make_area()
    assert explain(area, client=RaisingClient()) == template_text(area)


def test_llm_empty_reply_falls_back():
    area = make_area()
    assert explain(area, client=FakeClient("   ")) == template_text(area)
    odd = FakeClient()
    odd.create = lambda **kw: SimpleNamespace(content=[])
    assert explain(area, client=odd) == template_text(area)


def test_llm_cannot_change_class():
    area = make_area()
    before = (area.cls, area.confidence, area.confidence_label, list(area.evidence))
    # the model "disagrees": it talks about a burn scar. The words may differ; the data may not
    text = explain(area, client=FakeClient("This was a burn scar."))
    assert text == "This was a burn scar."
    assert (area.cls, area.confidence, area.confidence_label, list(area.evidence)) == before
    assert area.cls == "forest_loss"
    assert area.plain_text == ""  # explain returns text; the caller decides where it goes


def test_no_api_key_uses_template_without_a_network_call(monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    area = make_area()
    assert explain(area) == template_text(area)


def test_default_client_is_built_from_the_environment(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key-not-real")
    built = {}

    def fake_ctor(**kwargs):
        built.update(kwargs)
        return FakeClient("From the default client.")

    monkeypatch.setattr("sarstellar.explain._make_client", lambda: fake_ctor(api_key="x"))
    assert explain(make_area()) == "From the default client."
    assert built == {"api_key": "x"}


def test_client_construction_failure_falls_back(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key-not-real")

    def boom():
        raise RuntimeError("cannot build client")

    monkeypatch.setattr("sarstellar.explain._make_client", boom)
    area = make_area()
    assert explain(area) == template_text(area)


@pytest.mark.parametrize("exc", [TimeoutError("slow"), ConnectionError("down"), ValueError("bad")])
def test_any_exception_type_falls_back(exc):
    area = make_area()
    assert explain(area, client=RaisingClient(exc)) == template_text(area)
