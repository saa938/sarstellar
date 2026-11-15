"""SARstellar v2 stages: the places the site tells stories about.

Boxes are [west, south, east, north]. Pass counts in comments are from CMR on 2026-11-15.
`mode` pins a polarization mode when the best stack would otherwise be wrong for the story.
"""

START = "2025-10-15"
END = "2026-11-15"

STAGES: dict[str, dict] = {
    # The Waltz: crop seasons
    "punjab": {"move": "waltz", "bbox": [75.62, 30.62, 75.92, 30.88], "name": "Punjab", "country": "India"},  # 24
    "iowa": {"move": "waltz", "bbox": [-93.75, 41.85, -93.40, 42.12], "name": "Story County, Iowa",
             "country": "United States"},  # 21
    "central_valley": {"move": "waltz", "bbox": [-120.50, 36.60, -120.15, 36.90], "name": "Central Valley, California",
                       "country": "United States"},  # 28
    "mekong": {"move": "waltz", "bbox": [105.50, 10.05, 105.85, 10.38], "name": "Mekong Delta",
               "country": "Vietnam"},  # 10
    # The Fall: forest loss
    "morton": {"move": "fall", "bbox": [-122.45, 46.55, -122.05, 46.80], "name": "Morton, Washington",
               "country": "United States"},  # 28
    "rondonia": {"move": "fall", "bbox": [-63.40, -9.70, -63.00, -9.35], "name": "Rondonia",
                 "country": "Brazil"},  # 8
    "apui": {"move": "fall", "bbox": [-60.00, -7.60, -59.60, -7.25], "name": "Apui, Amazonas",
             "country": "Brazil"},  # 7
    # The Scorch: fire
    "kaiser": {"move": "scorch", "bbox": [-119.37, 48.05, -118.72, 48.36], "name": "Kaiser Canyon Fire, Washington",
               "country": "United States"},  # 10
    # The Bounce and the Vanish: water
    "edouard": {"move": "bounce", "bbox": [-94.40, 30.15, -94.05, 30.45], "name": "Village Creek, Texas",
                "country": "United States"},  # 28
    "indiana": {"move": "vanish", "bbox": [-85.95, 39.98, -85.60, 40.20], "name": "White River, Indiana",
                "country": "United States"},  # 10, quad-pol
    "okavango": {"move": "vanish", "track": 172, "bbox": [22.60, -19.50, 23.00, -19.10], "name": "Okavango Delta",
                 "country": "Botswana"},  # 9
    "sylhet": {"move": "vanish", "bbox": [91.05, 24.40, 91.45, 24.75], "name": "Sylhet haor basin",
               "country": "Bangladesh"},  # 10
    "tonle_sap": {"move": "bounce", "track": 83, "bbox": [103.65, 13.05, 104.00, 13.32], "name": "Tonle Sap",
                  "country": "Cambodia"},  # partial frames only
    # The Melt: ice
    "greenland": {"move": "melt", "bbox": [-50.30, 67.00, -49.60, 67.25], "name": "Kangerlussuaq ice margin",
                  "country": "Greenland"},  # HH-only partial frames
    "jakobshavn": {"move": "melt", "bbox": [-50.30, 69.05, -49.60, 69.30], "name": "Jakobshavn Glacier",
                   "country": "Greenland"},  # HH-only partial frames
}
