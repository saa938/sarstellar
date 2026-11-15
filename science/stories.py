"""Story text per stage. Plain language; facts only; radar statements verified against the data.

`move` is the stage's headline move; `order` its place in the world tour. Beat dates are
snapped to the nearest NISAR pass by export_stage.py.
"""

STORIES: dict[str, dict] = {
    "punjab": {
        "order": 1, "move": "waltz",
        "title": "Wheat waltzes, rice bounces",
        "teaser": "The same Punjab fields dance twice a year, with two different partners.",
        "lede": "Punjab's fields grow wheat in winter and rice in the monsoon. NISAR watched both, "
                "and the two crops move in completely different ways.",
        "body": [
            "Wheat is a volume dance. As the canopy grows, leaves scatter the radar in every "
            "direction and HV climbs about 3 dB, from late November to February. Harvest in April "
            "drops the fields back to bare soil.",
            "Rice is a bounce. Seedlings are planted into flooded paddies in July. By September the "
            "stalks stand in water, the pulse bounces off the water and up the stalks, and HH jumps "
            "about 8 dB while HV rises far less. The gap between HH and HV widens from about 8 dB "
            "to 12 dB: the double-bounce fingerprint.",
            "Medians over about 70,000 cultivated hectares in a 29 by 29 km box near Ludhiana.",
        ],
        "beats": [
            {"date": "2025-11-21", "caption": "Wheat sown into bare fields"},
            {"date": "2026-02-01", "caption": "Wheat at its fullest: HV up 3 dB"},
            {"date": "2026-04-26", "caption": "Wheat harvest: back to bare soil"},
            {"date": "2026-07-07", "caption": "Paddies flooded and planted: the fields dim"},
            {"date": "2026-09-17", "caption": "Rice stands in water: HH jumps 8 dB, the Bounce"},
            {"date": "2026-10-11", "caption": "Rice harvest begins"},
        ],
    },
    "iowa": {
        "order": 3, "move": "waltz",
        "title": "A corn belt waltz",
        "teaser": "A full year of central Iowa: frozen fields, planting, the canopy and the harvest.",
        "lede": "Central Iowa is corn and soybeans almost wall to wall. NISAR watched a full year.",
        "body": [
            "From bare fields in May to the peak of the canopy in late September, HV climbed about "
            "8 dB as leaves and stalks filled the fields with scatterers. One pass after harvest "
            "began, it had fallen 4 dB.",
            "In January, frozen ground darkened the fields: ice holds less liquid water, so the soil "
            "sends less of the radar back.",
            "Medians over about 81,000 cultivated hectares north of Ames.",
        ],
        "beats": [
            {"date": "2026-01-21", "caption": "Frozen ground: the fields go dark"},
            {"date": "2026-05-21", "caption": "Planting: bare soil"},
            {"date": "2026-07-08", "caption": "The canopy closes: HV climbs"},
            {"date": "2026-09-30", "caption": "Peak canopy: HV up 8 dB since May"},
            {"date": "2026-10-12", "caption": "Harvest: down 4 dB in one pass"},
        ],
    },
    "central_valley": {
        "order": 6, "move": "waltz",
        "title": "Irrigated all year",
        "teaser": "Orchards, tomatoes and cotton: many dances on one valley floor.",
        "lede": "On the west side of California's Central Valley, irrigation lets fields be planted "
                "and harvested on different calendars.",
        "body": [
            "Orchards hold steady near the forest zone of the floor. Row crops waltz on their own "
            "schedules, so the valley never moves all at once.",
        ],
        "beats": [],
    },
    "mekong": {
        "hidden": True,
        "order": 8, "move": "waltz",
        "title": "Rice, again and again",
        "teaser": "The Mekong Delta grows up to three rice crops a year.",
        "lede": "In the Mekong Delta, rice paddies are flooded, planted and harvested in quick "
                "succession.",
        "body": ["Neighbouring fields are at different stages, so the floor shows many small waltzes "
                 "out of step with each other."],
        "beats": [],
    },
    "morton": {
        "order": 2, "move": "fall",
        "title": "The Fall",
        "teaser": "Clearcuts in Washington's working forests, checked against optical satellites.",
        "lede": "Around Morton and Mineral, Washington, commercial forests are harvested in blocks. "
                "Each clearcut makes the same move.",
        "body": [
            "A standing forest scatters a lot of HV back to the radar, because the signal bounces "
            "around inside the canopy. When the trees are cut, that volume is gone and HV drops by "
            "several decibels in a single pass.",
            "Across 37 forest-loss reference sites, NISAR's L-band alerts were about eight times more "
            "often real than Sentinel-1's C-band alerts at the same detection rate.",
        ],
        "beats": [],
        "sources": [{"name": "OPERA DIST-ALERT-HLS (NASA JPL)",
                     "url": "https://www.jpl.nasa.gov/go/opera/products/"}],
    },
    "rondonia": {
        "order": 3, "move": "fall",
        "title": "The dry-season frontier",
        "teaser": "Rondonia, Brazil: forest cleared in the months the clouds part.",
        "lede": "Rondonia is one of the most deforested states in the Brazilian Amazon. Clearing "
                "happens in the dry season, June to October.",
        "body": [
            "Optical satellites lose the Amazon to clouds for much of the year. Radar does not. "
            "The same fall in HV that marks a Washington clearcut marks a cleared Amazon plot.",
        ],
        "beats": [],
    },
    "apui": {
        "hidden": True,
        "order": 9, "move": "fall",
        "title": "A new front",
        "teaser": "Apui, southern Amazonas, along the Trans-Amazonian highway.",
        "lede": "Apui has been one of the Amazon's fastest-clearing municipalities in recent years.",
        "body": [],
        "beats": [],
    },
    "kaiser": {
        "order": 5, "move": "scorch",
        "title": "Kaiser Canyon Fire",
        "teaser": "138,000 acres burned on the Colville Reservation in July 2026.",
        "lede": "Lightning started the Kaiser Canyon Fire on July 16, 2026. It burned about 138,000 "
                "acres of the Colville Reservation and forced evacuations in Nespelem.",
        "body": [
            "Where forest burned, HV falls like a clearcut. Where grass and shrubs burned, L-band "
            "barely notices: its 24 cm waves pass through thin vegetation. Sentinel-1's shorter "
            "waves see grass fires better, and we show that too.",
        ],
        "beats": [
            {"date": "2026-07-16", "caption": "Lightning starts the fire"},
            {"date": "2026-09-07", "caption": "Fire contained"},
        ],
        "sources": [{"name": "NIFC WFIGS fire perimeters",
                     "url": "https://data-nifc.opendata.arcgis.com/"}],
    },
    "edouard": {
        "order": 4, "move": "bounce",
        "title": "The flood under the trees",
        "teaser": "Tropical Storm Edouard flooded East Texas forests. L-band saw the water through the canopy.",
        "lede": "Edouard dropped more than 18 inches of rain on East Texas in early September 2026. "
                "Village Creek, which winds through the forests near Kountze, rose to 22 feet.",
        "body": [
            "Water under a forest canopy is invisible to optical satellites. L-band reaches the "
            "ground: its pulse bounces off the water, up the trunks and straight back to the "
            "radar. HH jumps while HV barely moves. That is the Bounce.",
            "On the September 3 pass, in the middle of the storm, 3,572 forested hectares in this "
            "box jumped 3 dB or more in HH while their HV held still. Twelve days later only 266 "
            "were still bouncing: the water had drained.",
        ],
        "beats": [
            {"date": "2026-08-22", "caption": "Before the storm"},
            {"date": "2026-09-03", "caption": "Edouard: 3,572 forest hectares bounce in HH"},
            {"date": "2026-09-15", "caption": "The water drains: the forest settles"},
        ],
    },
    "indiana": {
        "hidden": True,
        "order": 10, "move": "vanish",
        "title": "A record flood",
        "teaser": "The White River broke a 1913 record in August 2026.",
        "lede": "In mid-August 2026 the White River at Anderson, Indiana, crested above its 1913 "
                "record after more than 11 inches of rain.",
        "body": [
            "Calm floodwater reflects the radar away like a mirror, so flooded fields go dark in both "
            "channels: the Vanish. When the water drains, the dots come back.",
        ],
        "beats": [{"date": "2026-08-14", "caption": "The White River crests"}],
    },
    "okavango": {
        "hidden": True,
        "order": 11, "move": "vanish",
        "title": "The delta breathes",
        "teaser": "Rain from Angola arrives in Botswana months later, in the dry season.",
        "lede": "The Okavango's flood comes from rain that fell in Angola months before. It peaks in "
                "the middle of Botswana's dry winter.",
        "body": [
            "Floodplains fill and drain between June and October. Open water goes dark; flooded reeds "
            "and trees bounce.",
        ],
        "beats": [],
    },
    "sylhet": {
        "order": 5, "move": "vanish",
        "title": "A landscape that becomes a lake",
        "teaser": "Bangladesh's haor wetlands flood every monsoon. Watch the land vanish and return.",
        "lede": "The haors of northeastern Bangladesh are shallow basins that fill with monsoon "
                "water every year, turning farmland into an inland sea.",
        "body": [
            "Calm water reflects the radar away like a mirror, so flooded land goes dark in both "
            "channels: the Vanish. In this box, about 21,600 hectares looked like open water in "
            "June and 25,200 on September 10. By late September most had drained.",
            "On August 17 the water lit up instead. Wind ripples roughen a water surface and send "
            "the pulse back: one of radar's known blind spots, and a reason one pass is never the "
            "whole story.",
        ],
        "beats": [
            {"date": "2026-06-18", "caption": "Monsoon water: 21,600 hectares vanish"},
            {"date": "2026-08-17", "caption": "Wind roughens the water: it lights up"},
            {"date": "2026-09-10", "caption": "Peak: 25,200 hectares of open water"},
            {"date": "2026-10-16", "caption": "The water drains"},
        ],
    },
    "tonle_sap": {
        "hidden": True,
        "order": 13, "move": "bounce",
        "title": "The lake that grows five-fold",
        "teaser": "Every monsoon the Mekong pushes water back into Tonle Sap, flooding its forests.",
        "lede": "Tonle Sap is Southeast Asia's largest lake. In the monsoon the Mekong reverses into "
                "it and the lake spreads into the surrounding forest.",
        "body": [],
        "beats": [],
    },
    "greenland": {
        "order": 14, "move": "melt",
        "title": "The ice sheet's summer",
        "teaser": "At Greenland's edge, the melt zone changes its face through the summer.",
        "lede": "East of Kangerlussuaq the Greenland ice sheet meets the tundra. NISAR watched its "
                "melt zone from June to October.",
        "body": [
            "Over ice, NISAR listens with one channel, HH. Wet snow absorbs the radar. As the "
            "summer goes on, rough bare ice and refrozen crust send more of it back.",
            "Across the ice in this box, HH rose 4 to 5 dB at the height of summer, peaking on "
            "the August 19 pass, and settled back by October. The tundra to the west barely "
            "moved.",
        ],
        "beats": [
            {"date": "2026-06-20", "caption": "Early summer: wet snow on the ice"},
            {"date": "2026-08-19", "caption": "Peak of summer: the ice brightens 4 to 5 dB"},
            {"date": "2026-10-18", "caption": "Autumn: the surface settles"},
        ],
    },
    "jakobshavn": {
        "hidden": True,
        "order": 15, "move": "melt",
        "title": "The fastest glacier",
        "teaser": "Sermeq Kujalleq (Jakobshavn) pours ice into Disko Bay.",
        "lede": "Jakobshavn Glacier is one of the fastest-flowing glaciers on Earth.",
        "body": [],
        "beats": [],
    },
}
