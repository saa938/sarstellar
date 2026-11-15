// One list of data credits, used by the footer and the About page.

export const REPO_URL = "https://github.com/saa938/sarstellar";

export interface Credit {
  name: string;
  role: string;
  url: string;
}

export const DATA_CREDITS: Credit[] = [
  { name: "NISAR L2 GCOV", role: "The radar itself: every dot and every image. NASA-ISRO mission, distributed by the ASF DAAC.", url: "https://asf.alaska.edu/datasets/daac/nisar/" },
  { name: "OPERA DIST-ALERT-HLS", role: "Independent optical forest-loss alerts, the reference for the Fall. NASA JPL OPERA project.", url: "https://www.jpl.nasa.gov/go/opera/" },
  { name: "OPERA DSWx", role: "Surface water maps, the reference for the Vanish. NASA JPL OPERA project.", url: "https://www.jpl.nasa.gov/go/opera/" },
  { name: "OPERA RTC-S1 (Sentinel-1)", role: "C-band backscatter for the NISAR against Sentinel-1 comparison. Contains modified Copernicus Sentinel data.", url: "https://www.jpl.nasa.gov/go/opera/" },
  { name: "NIFC wildfire perimeters", role: "Fire perimeters and dates, the reference for the Scorch. National Interagency Fire Center.", url: "https://data-nifc.opendata.arcgis.com/" },
  { name: "USDA NASS Cropland Data Layer", role: "Cultivated land, the reference for the Waltz.", url: "https://www.nass.usda.gov/Research_and_Science/Cropland/SARS1a.php" },
  { name: "NASA GIBS, VIIRS Black Marble", role: "Night lights on the globe.", url: "https://nasa-gibs.github.io/gibs-api-docs/" },
  { name: "Esri basemaps", role: "Dark Gray Canvas and World Imagery under the radar. Esri, HERE, Garmin, Maxar, Earthstar Geographics, OpenStreetMap contributors.", url: "https://www.esri.com/en-us/arcgis/products/arcgis-online/overview" },
];
