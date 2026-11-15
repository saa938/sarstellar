"""Story text per stage. Plain language; facts only; radar statements verified against the data.

`move` is the stage's headline move; `order` its place in the world tour. Beat dates are
snapped to the nearest NISAR pass by export_stage.py.
"""

STORIES: dict[str, dict] = {
    "punjab": {
        "order": 1, "move": "waltz",
        "title": "Two waltzes a year",
        "teaser": "Rice in the monsoon, wheat in the winter: the same fields dance twice.",
        "lede": "Punjab feeds a large share of India. Its fields grow two crops a year, and NISAR "
                "watched both.",
        "body": [
            "Wheat is sown in November and harvested in April. Rice is planted into flooded paddies "
            "in June and July and cut in October.",
            "As a crop grows, its leaves and stalks scatter the radar in every direction, so HV "
            "climbs. At harvest the canopy disappears and HV falls back to bare soil. Flooding a "
            "paddy turns it briefly into a mirror: both channels go dark.",
        ],
        "beats": [
            {"date": "2026-02-10", "caption": "Wheat canopy: HV rises across the fields"},
            {"date": "2026-04-25", "caption": "Wheat harvest: back to bare soil"},
            {"date": "2026-07-05", "caption": "Paddies flooded for rice: the fields go dark"},
            {"date": "2026-09-10", "caption": "Rice canopy at its peak"},
        ],
    },
    "iowa": {
        "order": 4, "move": "waltz",
        "title": "Corn and soybeans",
        "teaser": "A full year of the Corn Belt, from frozen stubble to harvest.",
        "lede": "Central Iowa is corn and soybeans almost wall to wall. NISAR watched a full season.",
        "body": [
            "Planting happens in late April and May. By midsummer, corn stands taller than a person "
            "and HV rises with every pass. Harvest in September and October sends the dots back down.",
        ],
        "beats": [
            {"date": "2026-05-15", "caption": "Planting: bare fields"},
            {"date": "2026-07-25", "caption": "Canopy closes: HV climbs"},
            {"date": "2026-10-10", "caption": "Harvest"},
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
        "order": 7, "move": "bounce",
        "title": "The flood under the trees",
        "teaser": "Tropical Storm Edouard flooded East Texas forests. Only L-band saw it.",
        "lede": "Edouard dropped more than 18 inches of rain on East Texas in early September 2026. "
                "Village Creek rose to 22 feet.",
        "body": [
            "Water under a forest canopy is invisible to optical satellites and to short-wave radar. "
            "L-band reaches the ground: its pulse bounces off the water, up the trunks and straight "
            "back. HH jumps by several decibels while HV barely moves. That is the Bounce.",
        ],
        "beats": [
            {"date": "2026-09-03", "caption": "Edouard's rain arrives"},
            {"date": "2026-09-07", "caption": "Floodwater under the canopy: HH jumps"},
        ],
    },
    "indiana": {
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
        "order": 12, "move": "vanish",
        "title": "A landscape that becomes a lake",
        "teaser": "Bangladesh's haor wetlands flood for half the year.",
        "lede": "The haors of northeastern Bangladesh are shallow basins that fill with monsoon "
                "water every year.",
        "body": [],
        "beats": [],
    },
    "tonle_sap": {
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
        "teaser": "At Greenland's edge, melt darkens the ice and the freeze brings it back.",
        "lede": "At the western edge of the Greenland ice sheet, the surface melts every summer.",
        "body": [
            "Over ice, NISAR listens with one channel, HH. Liquid water in the snow absorbs the "
            "radar, so melting ice goes dark. When it refreezes, it brightens again.",
        ],
        "beats": [],
    },
    "jakobshavn": {
        "order": 15, "move": "melt",
        "title": "The fastest glacier",
        "teaser": "Sermeq Kujalleq (Jakobshavn) pours ice into Disko Bay.",
        "lede": "Jakobshavn Glacier is one of the fastest-flowing glaciers on Earth.",
        "body": [],
        "beats": [],
    },
}
