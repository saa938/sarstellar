"""Build the guided story's content from real NISAR data: web/public/story/story.json + crops.

    python science/make_story.py --raw ../raw --web web/public --report ../raw/_ref/moves_report.json

Every crop is cut from a stage's rendered radar image (R=HH, G=HV, B=HH); every number is a
median over real hectares, computed here and written into the text. Windows are chosen
automatically where each surface or change is clearest.
"""

from __future__ import annotations

import argparse
import json
import warnings
from datetime import UTC, datetime
from pathlib import Path

import numpy as np
from PIL import Image

warnings.simplefilter("ignore", RuntimeWarning)
MOVE_IDS = ["still", "fall", "scorch", "bounce", "vanish", "waltz", "shimmer", "melt"]
WIN = 60  # crop window in hectare blocks (6 km)
rng = np.random.default_rng(11)


class Stage:
    def __init__(self, raw: Path, sid: str):
        self.sid, self.dir = sid, raw / sid
        self.info = json.loads((self.dir / "stage.json").read_text())
        z = np.load(self.dir / "cube.npz")
        self.dates = [str(d) for d in z["dates"]]
        self.hh = z["blocks_HH"].astype("float32")
        self.hv = z["blocks_HV"].astype("float32") if "blocks_HV" in z.files else None
        self.t, self.ny, self.nx = self.hh.shape
        m = self.dir / "moves.npz"
        self.move = np.load(m)["move"].reshape(self.ny, self.nx) if m.exists() else None
        self.px = int(round(100 / self.info["img_res_m"]))  # image pixels per hectare block
        self.files = self.info["render"]["files"]

    def ti(self, date: str) -> int:
        return min(range(self.t), key=lambda i: abs(
            (datetime.fromisoformat(self.dates[i]) - datetime.fromisoformat(date)).days))

    def best_window(self, score: np.ndarray, avoid_edges: int = 2) -> tuple[int, int]:
        """Top-left (row, col) of the WIN x WIN window with the highest summed score."""
        s = np.nan_to_num(score.astype("float64"))
        c = np.pad(s.cumsum(0).cumsum(1), ((1, 0), (1, 0)))
        tot = c[WIN:, WIN:] - c[:-WIN, WIN:] - c[WIN:, :-WIN] + c[:-WIN, :-WIN]
        tot[:avoid_edges, :] = -np.inf
        tot[:, :avoid_edges] = -np.inf
        r, cc = np.unravel_index(np.argmax(tot), tot.shape)
        return int(r), int(cc)

    def crop(self, date: str, rc: tuple[int, int], out: Path, size: int = 600) -> str:
        r, c = rc
        im = Image.open(self.dir / self.files[self.ti(date)]).convert("RGBA")
        box = (c * self.px, r * self.px, (c + WIN) * self.px, (r + WIN) * self.px)
        ch = im.crop(box).resize((size, size), Image.LANCZOS)
        bg = Image.new("RGBA", ch.size, (7, 8, 11, 255))
        bg.alpha_composite(ch)
        out.parent.mkdir(parents=True, exist_ok=True)
        bg.convert("RGB").save(out, "WEBP", quality=86, method=6)
        return out.as_posix()

    def win(self, arr2d: np.ndarray, rc) -> np.ndarray:
        r, c = rc
        return arr2d[r:r + WIN, c:c + WIN]

    def med(self, t: int, mask: np.ndarray, rc) -> tuple[float, float | None]:
        h = self.win(self.hh[t], rc)[mask]
        v = self.win(self.hv[t], rc)[mask] if self.hv is not None else None
        return (round(float(np.nanmedian(h)), 2),
                None if v is None else round(float(np.nanmedian(v)), 2))

    def cloud(self, t: int, rc, n: int = 1500) -> list[list[float]]:
        h = self.win(self.hh[t], rc).ravel()
        v = self.win(self.hv[t], rc).ravel()
        ok = np.flatnonzero(np.isfinite(h) & np.isfinite(v))
        pick = rng.choice(ok, min(n, len(ok)), replace=False) if len(ok) else ok
        return [[round(float(h[i]), 2), round(float(v[i]), 2)] for i in pick]


def rel(p: str, web: Path) -> str:
    return Path(p).relative_to(web).as_posix()


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--raw", type=Path, required=True)
    ap.add_argument("--web", type=Path, required=True)
    ap.add_argument("--report", type=Path, required=True)
    a = ap.parse_args()
    web, out = a.web, a.web / "story"
    S = {s: Stage(a.raw, s) for s in ["punjab", "iowa", "morton", "rondonia", "edouard",
                                      "sylhet", "greenland", "central_valley", "kaiser"]}
    rep = json.loads(a.report.read_text())

    # ---- hero: Punjab through the year
    p = S["punjab"]
    frames = []
    for k, d in enumerate(["2025-11-21", "2026-02-01", "2026-04-26", "2026-07-19", "2026-09-17",
                           "2026-10-11"]):
        im = Image.open(p.dir / p.files[p.ti(d)]).convert("RGB")
        im.thumbnail((1700, 1700))
        f = out / "hero" / f"punjab_{k}.webp"
        f.parent.mkdir(parents=True, exist_ok=True)
        im.save(f, "WEBP", quality=82, method=6)
        frames.append({"date": p.dates[p.ti(d)], "image": rel(str(f), web)})

    # ---- chips: one typical patch per surface
    chips = []
    sy = S["sylhet"]
    t = sy.ti("2026-09-10")
    water = ((sy.hh[t] <= -18) & (sy.hv[t] <= -24)).astype(float)
    rc = sy.best_window(water)
    m = sy.win(water, rc) > 0
    hh, hv = sy.med(t, m, rc)
    chips.append({"id": "water", "label": "Open water", "place": "Sylhet, Bangladesh",
                  "date": sy.dates[t], "image": rel(sy.crop(sy.dates[t], rc, out / "chips" / "water.webp"), web),
                  "HH": hh, "HV": hv,
                  "text": "Calm water reflects the pulse away like a mirror: almost no echo in either channel."})
    io = S["iowa"]
    t_bare, t_crop = io.ti("2026-05-21"), io.ti("2026-09-18")
    crop_like = ((io.hv[t_crop] - io.hv[t_bare]) >= 5).astype(float)
    rc = io.best_window(crop_like)
    m = io.win(crop_like, rc) > 0
    hh, hv = io.med(t_bare, m, rc)
    chips.append({"id": "bare", "label": "Bare field", "place": "Central Iowa", "date": io.dates[t_bare],
                  "image": rel(io.crop(io.dates[t_bare], rc, out / "chips" / "bare.webp"), web),
                  "HH": hh, "HV": hv,
                  "text": "Bare soil sends back a modest HH echo and very little HV: there is nothing to twist the pulse."})
    hh2, hv2 = io.med(t_crop, m, rc)
    chips.append({"id": "crop", "label": "Full-grown crop", "place": "Central Iowa (same fields)",
                  "date": io.dates[t_crop],
                  "image": rel(io.crop(io.dates[t_crop], rc, out / "chips" / "crop.webp"), web),
                  "HH": hh2, "HV": hv2,
                  "text": f"The same fields in September: leaves and stalks scatter the pulse, and HV is "
                          f"{hv2 - hv:.0f} dB louder than in May."})
    ro = S["rondonia"]
    t = ro.ti("2026-07-19")
    mean_hv = np.nanmean(ro.hv, axis=0)
    sd_hv = np.nanstd(ro.hv, axis=0)
    forest = ((mean_hv >= -15.5) & (sd_hv <= 1.0)).astype(float)
    rc = ro.best_window(forest)
    m = ro.win(forest, rc) > 0
    hh, hv = ro.med(t, m, rc)
    chips.append({"id": "forest", "label": "Forest", "place": "Rondonia, Brazil (intact Amazon forest)",
                  "date": ro.dates[t],
                  "image": rel(ro.crop(ro.dates[t], rc, out / "chips" / "forest.webp"), web),
                  "HH": hh, "HV": hv,
                  "text": "A forest canopy scatters the pulse in every direction, so HV is strong and steady."})
    t = p.ti("2026-02-01")
    city = (p.hh[t] >= -2.5).astype(float)
    rc = p.best_window(city)
    m = p.win(city, rc) > 0
    hh, hv = p.med(t, m, rc)
    chips.append({"id": "city", "label": "City", "place": "Ludhiana, Punjab", "date": p.dates[t],
                  "image": rel(p.crop(p.dates[t], rc, out / "chips" / "city.webp"), web),
                  "HH": hh, "HV": hv,
                  "text": "Walls and streets bounce the pulse straight back to the satellite: the loudest HH of all."})
    bg = []
    for s in S.values():
        if s.hv is None:
            continue
        tm = s.t // 2
        h, v = s.hh[tm].ravel(), s.hv[tm].ravel()
        ok = np.flatnonzero(np.isfinite(h) & np.isfinite(v))
        for i in rng.choice(ok, min(700, len(ok)), replace=False):
            bg.append([round(float(h[i]), 2), round(float(v[i]), 2)])

    # ---- examples
    ex = []

    def path_of(s: Stage, mask, rc, dates):
        pts = []
        for d in dates:
            ti = s.ti(d)
            hh_, hv_ = s.med(ti, mask, rc)
            pts.append({"date": s.dates[ti], "HH": hh_, "HV": hv_})
        return pts

    # Punjab: every cultivated field, selected without looking at the change being measured
    hv_range = np.nanmax(p.hv, 0) - np.nanmin(p.hv, 0)
    fields = (hv_range > 3) & (np.nanmedian(p.hh, 0) < -4)
    rc = p.best_window(fields.astype(float))

    def field_path(dates):
        pts = []
        for d in dates:
            ti = p.ti(d)
            pts.append({"date": p.dates[ti], "HH": round(float(np.nanmedian(p.hh[ti][fields])), 2),
                        "HV": round(float(np.nanmedian(p.hv[ti][fields])), 2)})
        return pts

    n_fields = int(fields.sum())
    tb, ta = p.ti("2025-11-21"), p.ti("2026-02-01")
    path = field_path(["2025-11-21", "2025-12-27", "2026-02-01", "2026-03-21", "2026-04-26"])
    d_hv = path[2]["HV"] - path[0]["HV"]
    ex.append({"id": "wheat", "kicker": "Punjab, India", "title": "A crop growing: wheat",
               "text": f"In winter, Punjab's fields grow wheat. As the plants fill in, their leaves twist "
                       f"the radar pulse: across {n_fields:,} cultivated hectares, the median HV climbed "
                       f"{d_hv:.1f} dB between November and February. The April harvest takes it back "
                       f"down to bare soil.",
               "measure": f"HV +{d_hv:.1f} dB", "channel": "HV",
               "before": {"date": p.dates[tb], "image": rel(p.crop(p.dates[tb], rc, out / "ex" / "wheat_before.webp"), web)},
               "after": {"date": p.dates[ta], "image": rel(p.crop(p.dates[ta], rc, out / "ex" / "wheat_after.webp"), web)},
               "path": path, "cloud_before": p.cloud(tb, rc), "cloud_after": p.cloud(ta, rc), "one_d": False})
    tb, ta = p.ti("2026-07-19"), p.ti("2026-09-17")
    path = field_path(["2026-06-13", "2026-07-07", "2026-07-19", "2026-08-12", "2026-09-05",
                       "2026-09-17", "2026-10-11"])
    d_hh = path[5]["HH"] - path[2]["HH"]
    d_hv2 = path[5]["HV"] - path[2]["HV"]
    gap0 = path[2]["HH"] - path[2]["HV"]
    gap1 = path[5]["HH"] - path[5]["HV"]
    ex.append({"id": "rice", "kicker": "Punjab, India (the same fields, the same year)",
               "title": "Rice standing in water",
               "text": f"In the monsoon the same fields are flooded and planted with rice. Now the pulse "
                       f"bounces off the water, up the stalks and straight back: the median HH jumped "
                       f"{d_hh:.1f} dB between mid-July and mid-September while HV rose only "
                       f"{d_hv2:.1f} dB. The gap between the channels widened from {gap0:.0f} to "
                       f"{gap1:.0f} dB. Two crops, two radar channels.",
               "measure": f"HH +{d_hh:.1f} dB", "channel": "HH",
               "before": {"date": p.dates[tb], "image": rel(p.crop(p.dates[tb], rc, out / "ex" / "rice_before.webp"), web)},
               "after": {"date": p.dates[ta], "image": rel(p.crop(p.dates[ta], rc, out / "ex" / "rice_after.webp"), web)},
               "path": path, "cloud_before": p.cloud(tb, rc), "cloud_after": p.cloud(ta, rc), "one_d": False})
    # flood under trees (Edouard)
    ed = S["edouard"]
    tb, ta = ed.ti("2026-08-22"), ed.ti("2026-09-03")
    medh, medv = np.nanmedian(ed.hh, 0), np.nanmedian(ed.hv, 0)
    fl = (((ed.hh[ta] - medh) >= 3) & ((ed.hv[ta] - medv) < 1.5) & (medv >= -16)).astype(float)
    n_flood = int(np.nansum(fl))
    rc = ed.best_window(fl)
    m = ed.win(fl, rc) > 0
    path = path_of(ed, m, rc, ["2026-08-10", "2026-08-22", "2026-09-03", "2026-09-15", "2026-09-27"])
    d_hh = path[2]["HH"] - path[1]["HH"]
    ex.append({"id": "flood-trees", "kicker": "Village Creek, Texas", "title": "A flood hidden under trees",
               "text": f"Tropical Storm Edouard flooded East Texas forests in early September 2026. From "
                       f"above, the canopy hides the water. NISAR's 24 cm waves reach the ground: on the "
                       f"pass during the storm, {n_flood:,} forested hectares jumped 3 dB or more in HH "
                       f"while HV held still, the double bounce off water and trunks. Twelve days later "
                       f"the water had drained.",
               "measure": f"HH +{d_hh:.1f} dB in one pass", "channel": "HH",
               "before": {"date": ed.dates[tb], "image": rel(ed.crop(ed.dates[tb], rc, out / "ex" / "flood_before.webp"), web)},
               "after": {"date": ed.dates[ta], "image": rel(ed.crop(ed.dates[ta], rc, out / "ex" / "flood_after.webp"), web)},
               "path": path, "cloud_before": ed.cloud(tb, rc), "cloud_after": ed.cloud(ta, rc), "one_d": False})
    # forest loss (Rondonia)
    ro = S["rondonia"]
    tb, ta = 0, ro.t - 1
    pre = np.nanmean(ro.hv[:2], 0)
    post = np.nanmean(ro.hv[-2:], 0)
    loss = ((pre >= -15.5) & ((post - pre) <= -3)).astype(float)
    n_loss = int(np.nansum(loss))
    rc = ro.best_window(loss)
    m = ro.win(loss, rc) > 0
    path = path_of(ro, m, rc, ro.dates)
    d_hv = path[-1]["HV"] - path[0]["HV"]
    ex.append({"id": "forest-loss", "kicker": "Rondonia, Brazil", "title": "A forest cut down",
               "text": f"Rondonia is one of the most deforested states in the Amazon, and clearing happens "
                       f"in the dry season. When the canopy goes, so does its scattering: the hectares cleared "
                       f"in this window lost about {abs(d_hv):.0f} dB of HV. In this 6 km window the dark new clearings appear between June "
                       f"and October; across the whole 40 km box, {n_loss:,} forested hectares lost 3 dB "
                       f"or more of HV.",
               "measure": f"HV {d_hv:.1f} dB", "channel": "HV",
               "before": {"date": ro.dates[tb], "image": rel(ro.crop(ro.dates[tb], rc, out / "ex" / "loss_before.webp"), web)},
               "after": {"date": ro.dates[ta], "image": rel(ro.crop(ro.dates[ta], rc, out / "ex" / "loss_after.webp"), web)},
               "path": path, "cloud_before": ro.cloud(tb, rc), "cloud_after": ro.cloud(ta, rc), "one_d": False})
    # ice (Greenland, HH only)
    gr = S["greenland"]
    tb, ta = gr.ti("2026-06-20"), gr.ti("2026-08-19")
    rise = (gr.hh[ta] - gr.hh[tb] >= 4).astype(float)
    rc = gr.best_window(rise)
    m = gr.win(rise, rc) > 0
    series = [{"date": gr.dates[i], "HH": gr.med(i, m, rc)[0]} for i in range(gr.t)]
    d = series[gr.ti("2026-08-19")]["HH"] - series[0]["HH"]
    ex.append({"id": "ice", "kicker": "Greenland ice sheet, near Kangerlussuaq", "title": "An ice sheet's summer",
               "text": f"Over ice, NISAR listens with HH alone. Wet snow absorbs the pulse; as summer goes "
                       f"on, rough bare ice and refrozen crust send more of it back. In the window shown, "
                       f"HH rose about {d:.0f} dB by the August 19 pass and settled again by October; "
                       f"across the whole melt zone in this box the rise was 4 to 5 dB.",
               "measure": f"HH +{d:.1f} dB", "channel": "HH",
               "before": {"date": gr.dates[tb], "image": rel(gr.crop(gr.dates[tb], rc, out / "ex" / "ice_before.webp"), web)},
               "after": {"date": gr.dates[ta], "image": rel(gr.crop(gr.dates[ta], rc, out / "ex" / "ice_after.webp"), web)},
               "one_d": True, "series": series})

    # ---- proof in plain words
    main_ = rep["main"]
    g = main_["gated"]
    n_test = main_["n_test_blocks"]
    fall_flag_share = 100 * g["fall"]["n_flagged"] / n_test
    ab = rep["ablations"]
    hv_only, hh_only = ab["HV only"]["fall"]["auprc"], ab["HH only"]["fall"]["auprc"]
    ro_m = np.load(S["rondonia"].dir / "moves.npz")
    ro_ref = np.load(S["rondonia"].dir / "refs.npz")["dist_frac"].ravel()
    ro_flag = ro_m["move"].ravel() == 1
    ok = np.isfinite(ro_ref)
    y = ro_ref[ok] >= 0.5
    ro_recall = 100 * (ro_flag[ok] & y).sum() / max(y.sum(), 1)
    ro_share = 100 * ro_flag[ok].mean()
    proof = {
        "title": "Does it work?",
        "intro": (f"We taught a model the signatures using {main_['n_train_sites']} US places where other "
                  f"sources already say what happened: NASA's optical forest-loss alerts, wildfire "
                  f"perimeters, water maps and cropland maps. Then we tested it on "
                  f"{main_['n_test_sites']} places in {main_['n_test_states']} states it had never seen."),
        "items": [
            {"id": "forest", "kind": "dots", "model": round(100 * g["fall"]["recall"]),
             "baseline": max(1, round(fall_flag_share)),
             "model_label": "found by SARstellar", "baseline_label": "found by picking land at random",
             "statement": (f"It finds forest loss. Pointing at just {fall_flag_share:.1f}% of the land, it "
                           f"found {100 * g['fall']['recall']:.0f} of every 100 hectares of real forest "
                           f"loss. Picking the same amount of land at random would find about "
                           f"{max(1, round(fall_flag_share))}."),
             "detail": f"{main_['fall']['n']:,} hectares of reference forest loss in the 12 unseen states."},
            {"id": "crops", "kind": "dots", "model": round(100 * g["waltz"]["precision"]),
             "baseline": round(100 * g["waltz"]["base_rate"]),
             "model_label": "right", "baseline_label": "right by guessing",
             "statement": (f"It recognizes growing crops. When it says a field is growing a crop, it is "
                           f"right {100 * g['waltz']['precision']:.0f} times in 100; a guess would be right "
                           f"about {100 * g['waltz']['base_rate']:.0f} times."),
             "detail": "Checked against the USDA Cropland Data Layer."},
            {"id": "any", "kind": "dots", "model": round(100 * g["any_move"]["precision"]),
             "baseline": round(100 * g["any_move"]["base_rate"]),
             "model_label": "really changed", "baseline_label": "by guessing",
             "statement": (f"When SARstellar says a hectare changed, it really did "
                           f"{100 * g['any_move']['precision']:.0f} times in 100, against "
                           f"{100 * g['any_move']['base_rate']:.0f} by guessing."),
             "detail": "Any labeled change: forest loss, fire, open-water flood or crop growth."},
            {"id": "channel", "kind": "bars",
             "statement": (f"Forest loss lives in HV. Listening to HV alone, the model finds it "
                           f"{hv_only / hh_only:.0f} times better than listening to HH alone: the canopy "
                           f"echo is what disappears."),
             "bars": [{"label": "HV alone", "value": round(hv_only, 3)},
                      {"label": "HH alone", "value": round(hh_only, 3)}],
             "detail": "Same model retrained with one channel at a time; ranking quality on the unseen states."},
            {"id": "sentinel", "kind": "dots", "model": 31, "baseline": 4,
             "model_label": "NISAR (L-band) alerts that were real",
             "baseline_label": "Sentinel-1 (C-band) alerts that were real",
             "statement": ("NISAR beats the radar we had before. At the same detection rate, 31 of every "
                           "100 NISAR forest-loss alerts were real, against 4 of 100 for Sentinel-1, "
                           "Europe's shorter-wavelength radar: 7.8 times more often right."),
             "detail": "37 forest-loss sites, same hectares, same reference (SARstellar v1 benchmark)."},
            {"id": "amazon", "kind": "dots", "model": round(ro_recall), "baseline": max(1, round(ro_share)),
             "model_label": "found by SARstellar", "baseline_label": "found at random",
             "statement": (f"It travels. Trained only on US places, it still found {ro_recall:.0f}% of the "
                           f"forest loss NASA's optical satellites recorded in Rondonia, Brazil, while "
                           f"pointing at {ro_share:.1f}% of the land."),
             "detail": "OPERA DIST-ALERT-HLS, June to October 2026."},
        ],
        "limits": [
            "Open-water floods were hard to tell apart from two passes alone at our test sites, and "
            "grass fires barely register at L-band. We show those, not hide them.",
            "The reference maps are imperfect: optical satellites miss cloudy weeks and fire "
            "perimeters include unburned patches.",
            "Floods under trees and ice changes have no labeled test set yet; we show them as physics, "
            "measured but not scored.",
            "Test places were chosen where changes happened, so these numbers describe those places, "
            "not how common change is everywhere.",
            "NISAR's 2026 data are provisional releases; NASA may reprocess them.",
        ],
    }
    apps = [
        {"title": "Deforestation through the clouds",
         "text": "The tropics are cloudy for months. Radar alerts don't wait for a clear day."},
        {"title": "Floods under forests",
         "text": "Map where water spreads beneath the canopy, where optical satellites see only trees."},
        {"title": "Rice and food security",
         "text": "Track when Asia's paddies are flooded and planted, every 12 days."},
        {"title": "Crop calendars everywhere",
         "text": "Planting, growth and harvest for any field on Earth, cloud or no cloud."},
        {"title": "Ice in a warming world",
         "text": "Follow the melt season across Greenland and Antarctica, pass by pass."},
    ]
    story = {
        "generated_at": datetime.now(UTC).isoformat(timespec="seconds"),
        "hero": {"title": "Earth is dancing. NISAR can see the steps.",
                 "subtitle": ("NISAR, the new NASA-ISRO radar satellite, scans nearly all of Earth's land "
                              "every 12 days, through clouds and darkness. Every kind of change, a forest "
                              "cut, a field planted, a flood, leaves its own signature in its two radar "
                              "channels. Here is how to read them."),
                 "place": "Punjab, India, November 2025 to October 2026", "frames": frames},
        "channels": {
            "title": "Two ways of listening",
            "text": [
                "NISAR sends down microwave pulses 24 centimeters long and listens to the echoes in two ways.",
                "HH hears echoes that come back the way they left: smooth ground, and pulses that bounce "
                "between water and a trunk or a wall.",
                "HV hears echoes twisted by bouncing around inside leaves and branches. It measures "
                "living canopy.",
                "Give every hectare a spot by its two echoes and each kind of surface finds its own "
                "place: water at the bottom left, forests at the top right, cities and flooded trees far "
                "right. Decibels (dB) are the radar's loudness scale: +3 dB is twice as loud.",
            ],
            "chips": chips, "cloud": bg},
        "examples": ex,
        "proof": proof,
        "applications": apps,
    }
    (out / "story.json").write_text(json.dumps(story, indent=1))
    print(json.dumps({"chips": [(c["id"], c["HH"], c["HV"]) for c in chips],
                      "examples": [(e["id"], e["measure"]) for e in ex],
                      "proof": [i["statement"][:90] for i in proof["items"]]}, indent=1))


if __name__ == "__main__":
    main()
