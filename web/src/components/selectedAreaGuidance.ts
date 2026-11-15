import type { ChangeClass, Evidence } from "../types.ts";

export interface ClassGuidance {
  hypothesis: string;
  checks: readonly [string, string];
  caveat: string;
}

/** Verification prompts, not additional model outputs or claims about the selected location. */
const GUIDANCE: Record<ChangeClass, ClassGuidance> = {
  forest_loss: {
    hypothesis: "Possible forest loss",
    checks: ["Compare independent pre/post optical imagery for canopy removal.",
      "Check dated harvest records or field observations."],
    caveat: "Moisture, seasonal vegetation, and viewing geometry can also alter backscatter.",
  },
  burn: {
    hypothesis: "Possible burn",
    checks: ["Inspect optical burn scars or independent field reports.",
      "Cross-check fire chronology and mapped perimeter dates."],
    caveat: "Backscatter change alone does not confirm burning.",
  },
  flood_open_water: {
    hypothesis: "Possible open-water flooding",
    checks: ["Compare independent optical water maps or field observations.",
      "Check river gauges and rainfall over the acquisition interval."],
    caveat: "Wind and viewing geometry can change open-water backscatter.",
  },
  flooded_vegetation: {
    hypothesis: "Possible flooded vegetation",
    checks: ["Compare independent flood maps and water-level observations.",
      "Check gauge records or field reports for inundation beneath canopy."],
    caveat: "Optical imagery can miss water beneath canopy; radar change does not measure water depth.",
  },
  crop_cycle: {
    hypothesis: "Possible crop-cycle change",
    checks: ["Compare crop calendars and optical vegetation time series.",
      "Check dated management records or field observations."],
    caveat: "A cropland label alone does not establish growth or harvest timing.",
  },
  harvest: {
    hypothesis: "Possible harvest",
    checks: ["Inspect independent optical imagery for vegetation removal.",
      "Check dated harvest or management records."],
    caveat: "Seasonal senescence can produce similar radar changes.",
  },
  low_veg_loss: {
    hypothesis: "Possible low-vegetation loss",
    checks: ["Compare vegetation cover in independent pre/post optical imagery.",
      "Check mowing, grazing, or other management records."],
    caveat: "Soil moisture and vegetation cover can both affect backscatter.",
  },
  soil_wetting: {
    hypothesis: "Possible soil wetting",
    checks: ["Compare rainfall and independent soil-moisture observations.",
      "Check vegetation state and changes in surface roughness."],
    caveat: "Rainfall proximity provides context; it does not confirm soil wetting.",
  },
  construction: {
    hypothesis: "Possible construction",
    checks: ["Compare recent optical imagery and dated land-use records.",
      "Check field photographs or permit dates."],
    caveat: "Changes in viewing geometry or surface roughness can resemble construction signals.",
  },
  landslide: {
    hypothesis: "Possible landslide",
    checks: ["Inspect independent imagery and terrain for a new scar or deposit.",
      "Check landslide inventories or field reports."],
    caveat: "Radar shadow and layover can resemble surface changes.",
  },
  wet_snow: {
    hypothesis: "Possible wet-snow change",
    checks: ["Compare snow-cover products and acquisition-time air temperature.",
      "Check local snow or weather observations."],
    caveat: "Temperature or backscatter change alone does not confirm wet snow.",
  },
  uncertain: {
    hypothesis: "Cause unresolved",
    checks: ["Inspect independent pre/post imagery and local event records.",
      "Check moisture, seasonal vegetation, snow, and viewing geometry."],
    caveat: "The available inputs do not establish a physical cause.",
  },
};

export function guidanceFor(cls: ChangeClass): ClassGuidance {
  return GUIDANCE[cls] ?? GUIDANCE.uncertain;
}

/** Qualify legacy rule wording at display time without changing saved evidence. */
export function displayRuleText(text: string): string {
  return text.replace(/\(canopy removed\)/gi, "(consistent with canopy loss)")
    .replace(/double bounce off standing water/gi, "possible double-bounce response");
}

/** Keep the actual rule explanation and a signal measurement visible without duplicating the full table. */
export function supportingEvidence(evidence: readonly Evidence[]): Evidence[] {
  const usable = evidence.filter((ev) => !/confidence|p[- ]?value/i.test(ev.label) &&
    ((typeof ev.value === "number" && Number.isFinite(ev.value)) ||
     (typeof ev.value === "string" && ev.value.trim().length > 0)));
  const rule = usable.find((ev) => /^rule\b/i.test(ev.label));
  const ruleBand = typeof rule?.value === "string" ? rule.value.match(/\b(HH|HV|VV|VH)\b/)?.[1] : undefined;
  const signal = usable.find((ev) => ruleBand && ev.label === `${ruleBand} change` && ev.unit === "dB") ??
    usable.find((ev) => ev !== rule && ev.unit === "dB");
  const selected = [rule, signal].filter((ev): ev is Evidence => ev !== undefined);
  for (const ev of usable) {
    if (selected.length === 2) break;
    if (!selected.includes(ev)) selected.push(ev);
  }
  return selected;
}
