"""Plain-English explanations of change areas.

The class, confidence and evidence always come from the rules (or the learned model). Here the LLM
only rewords them: `explain` returns a string and never modifies the area. Any failure (no API
key, network error, empty reply) falls back to `template_text`, which is deterministic and
contains the same numbers.
"""

from __future__ import annotations

import json
import logging
import os
from typing import Any

from .types import ChangeArea, Evidence

log = logging.getLogger(__name__)

MODEL = "claude-sonnet-5-5"
MAX_TOKENS = 200
SYSTEM_PROMPT = (
    "Rewrite this radar change finding in 2–3 plain sentences for a non-expert. "
    "Use only the numbers given; retain the measured area, band changes and uncertainty intervals. "
    "Do not change the classification. Distinguish detected radar change from the cause hypothesis: "
    "never present the class as an established or verified event. The change_date is the first "
    "flagged acquisition, not a confirmed event date. Confidence is a heuristic rule label, not a "
    "calibrated probability that the cause is correct. State that independent verification is needed "
    "to establish the cause. Sensor agreement or a larger detected area does not establish accuracy "
    "or that one radar performs better; missing observations are not evidence of no change."
)

_CAUSE = {
    "forest_loss": "Forest loss",
    "burn": "A burn scar",
    "flood_open_water": "Open-water flooding",
    "flooded_vegetation": "Flooded vegetation",
    "crop_cycle": "A crop cycle change (farming context)",
    "harvest": "Harvest",
    "low_veg_loss": "Low-vegetation loss",
    "soil_wetting": "Soil wetting",
    "construction": "Construction",
    "landslide": "A landslide",
    "wet_snow": "Wet snow",
    "uncertain": "A change with an uncertain cause",
}
_SEEN_BY = {
    "L": "only NISAR (L-band) met the detection criteria",
    "C": "only Sentinel-1 (C-band) met the detection criteria",
    "both": "both NISAR and Sentinel-1 met the detection criteria",
}
# Supporting evidence the template mentions, and how each reads inside a sentence.
_CONTEXT_LABELS = {
    "FIRMS detections": "FIRMS fire detections",
    "Rain": "rain",
    "Slope": "slope",
    "Minimum temperature": "minimum temperature",
    "HAND": "height above drainage (HAND)",
}
_UNIT_WORDS = {"count": "", "deg": "degrees", "C": "degrees C"}


def _num(value: Any) -> str:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return str(value)
    if isinstance(value, int):
        return str(value)
    return f"{value:+.1f}" if abs(value) >= 0.05 or value == 0 else f"{value:+.2g}"


def _band_phrase(e: Evidence, first: bool) -> str:
    """'HV changed by -3.5 dB (interval -4.1 to -2.9)'; later bands drop the verb: 'HH by -0.5 dB'."""
    band = e.label.removesuffix(" change")
    text = f"{band} {'changed by' if first else 'by'} {_num(e.value)} {e.unit}".rstrip()
    if e.ci and len(e.ci) == 2:
        text += f" (interval {_num(e.ci[0])} to {_num(e.ci[1])})"
    return text


def _context_phrase(e: Evidence) -> str:
    """A supporting fact in running prose, such as 'rain 12.0 mm' or 'FIRMS fire detections 12'."""
    value = f"{e.value:.1f}" if isinstance(e.value, float) else str(e.value)
    unit = _UNIT_WORDS.get(e.unit, e.unit)
    return f"{_CONTEXT_LABELS[e.label]} {value}{' ' + unit if unit else ''}"


def template_text(area: ChangeArea) -> str:
    """A deterministic 2-3 sentence description built only from the area's own numbers."""
    cause = _CAUSE.get(area.cls, "A change with an uncertain cause")
    when = (f"; first flagged acquisition {area.change_date} (not a confirmed event date)"
            if area.change_date else "")
    seen = _SEEN_BY.get(area.agreement, _SEEN_BY["both"])
    sentences = [f"Radar change detected across {area.area_ha:.1f} ha: {seen}{when}."]

    bands = [
        e
        for e in area.evidence
        if e.label.endswith(" change") and isinstance(e.value, (int, float))
    ]
    context = [e for e in area.evidence if e.label in _CONTEXT_LABELS]
    numbers = ", ".join(_band_phrase(b, first=i == 0) for i, b in enumerate(bands))
    if context:
        also = ", ".join(_context_phrase(e) for e in context[:2])
        numbers = f"{numbers}; also {also}" if numbers else f"Also {also}"
    if numbers:
        sentences.append(numbers + ".")

    tail = (f"Cause hypothesis: {cause.lower()}; rule confidence is {area.confidence_label.lower()} "
            "(not a calibrated cause probability); independent verification is needed")
    if any("possible freeze" in e.note for e in area.evidence):
        tail += (
            "; this may be a freeze-up artifact rather than surface change, "
            "because the minimum temperature was below freezing"
        )
    elif area.cls == "uncertain":
        tail += "; the radar signal does not establish a cause"
    sentences.append(tail + ".")
    return " ".join(sentences)


def _payload(area: ChangeArea) -> str:
    return json.dumps(
        {
            "class": area.cls,
            "agreement": area.agreement,
            "area_ha": round(area.area_ha, 2),
            "confidence": area.confidence_label,
            "change_date": area.change_date,
            "evidence": [e.to_json() for e in area.evidence],
        },
        ensure_ascii=False,
    )


def _make_client():
    import anthropic  # lazy: the SDK is only needed when a key is present

    return anthropic.Anthropic(timeout=20.0, max_retries=1)  # reads ANTHROPIC_API_KEY


def explain(area: ChangeArea, client=None) -> str:
    """Plain-language text for `area`: the LLM's rewording, or `template_text` on any problem.

    Never changes `area`. `client` is anything with `.messages.create(...)` (the Anthropic SDK
    client, or a test double). Without a client and without ANTHROPIC_API_KEY, no call is made.
    """
    fallback = template_text(area)
    try:
        if client is None:
            if not os.environ.get("ANTHROPIC_API_KEY"):
                log.info("explain: no ANTHROPIC_API_KEY, using the template text")
                return fallback
            client = _make_client()
        reply = client.messages.create(
            model=MODEL,
            max_tokens=MAX_TOKENS,
            system=SYSTEM_PROMPT,
            messages=[{"role": "user", "content": _payload(area)}],
        )
        text = "".join(
            block.text for block in reply.content if getattr(block, "type", "text") == "text"
        ).strip()
    except Exception as exc:  # noqa: BLE001 - any LLM/network/key problem falls back to the template
        # Log the exception class only: an SDK error message can echo request details.
        log.warning("explain: LLM call failed (%s), using the template text", type(exc).__name__)
        return fallback
    if not text:
        log.warning("explain: LLM reply was empty, using the template text")
        return fallback
    return text
