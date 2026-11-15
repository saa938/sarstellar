// About / Methods page (Task B6): data, method, limits, AI-use disclosure, references, license.
// Static text only: no result numbers here (those live in the stories and the Scorecard).
import { NISAR_GAP } from "../types.ts";
import "./pages.css";

const REPO = "https://github.com/saa938/sarstellar";

interface DataSource {
  name: string;
  use: string;
  source: string;
  href: string;
}

const DATA: DataSource[] = [
  {
    name: "NISAR L2 GCOV (L-band, 24 cm)",
    use: "The main radar: HH and HV backscatter on a 10 m grid. Calibrated collections only (NISAR_L2_GCOV_PROVISIONAL_V1, NISAR_L2_GCOV_V1); BETA data is never used.",
    source: "NASA/ISRO, via the ASF DAAC and NASA Earthdata",
    href: "https://search.asf.alaska.edu/",
  },
  {
    name: "OPERA RTC-S1 (Sentinel-1, C-band, 5.6 cm)",
    use: "The comparison radar: VV and VH backscatter at 30 m (OPERA_L2_RTC-S1_V1), placed on NISAR's grid.",
    source: "NASA JPL OPERA, via the ASF DAAC",
    href: "https://www.jpl.nasa.gov/go/opera",
  },
  {
    name: "OPERA DIST-ALERT-HLS",
    use: "Optical vegetation-loss alerts: the forest-loss reference for the scorecard.",
    source: "NASA JPL OPERA, via the LP DAAC",
    href: "https://www.jpl.nasa.gov/go/opera",
  },
  {
    name: "OPERA DSWx-HLS and DSWx-S1",
    use: "Surface-water maps: the flood reference for the scorecard.",
    source: "NASA JPL OPERA, via PO.DAAC",
    href: "https://www.jpl.nasa.gov/go/opera",
  },
  {
    name: "NIFC WFIGS 2026 wildfire perimeters",
    use: "The fire reference for the scorecard, and support for the burn label.",
    source: "National Interagency Fire Center",
    href: "https://data-nifc.opendata.arcgis.com/",
  },
  {
    name: "NASA FIRMS active fires",
    use: "Fire evidence: an area is only called a burn with FIRMS or perimeter support.",
    source: "NASA LANCE FIRMS",
    href: "https://firms.modaps.eosdis.nasa.gov/",
  },
  {
    name: "USDA Cropland Data Layer",
    use: "Cultivated-land reference for the scorecard. The live app uses NLCD cropland as a contextual proxy.",
    source: "USDA NASS",
    href: "https://www.nass.usda.gov/Research_and_Science/Cropland/SARS1a.php",
  },
  {
    name: "NLCD land cover",
    use: "Land-cover groups for the change baseline and the scorecard breakdown.",
    source: "USGS and the MRLC consortium",
    href: "https://www.mrlc.gov/",
  },
  {
    name: "CDC/ATSDR Social Vulnerability Index 2022",
    use: "\"Who lives here\": census-tract vulnerability next to each change.",
    source: "CDC/ATSDR",
    href: "https://www.atsdr.cdc.gov/place-health/php/svi/index.html",
  },
  {
    name: "Open-Meteo historical weather",
    use: "Rain and minimum temperature at the box center on the final NISAR date, when available.",
    source: "Open-Meteo",
    href: "https://open-meteo.com/en/docs/historical-weather-api",
  },
  {
    name: "Esri World Imagery",
    use: "The muted satellite basemap under the overlays.",
    source: "Esri, Maxar, Earthstar Geographics, and the GIS User Community",
    href: "https://www.arcgis.com/home/item.html?id=10df2279f9684e4a9f6a7f08febac2a9",
  },
];

const REFERENCES = [
  "Conradsen, K., Nielsen, A. A., & Skriver, H. (2016). Determining the points of change in time series of polarimetric SAR data. IEEE Transactions on Geoscience and Remote Sensing, 54(5), 3007–3024.",
  "Benjamini, Y., & Hochberg, Y. (1995). Controlling the false discovery rate: a practical and powerful approach to multiple testing. Journal of the Royal Statistical Society, Series B, 57(1), 289–300.",
  "Fisher, R. A. (1925). Statistical Methods for Research Workers. Oliver and Boyd.",
  "Efron, B., & Tibshirani, R. J. (1993). An Introduction to the Bootstrap. Chapman & Hall.",
  "Saito, T., & Rehmsmeier, M. (2015). The precision-recall plot is more informative than the ROC plot when evaluating binary classifiers on imbalanced datasets. PLOS ONE, 10(3), e0118432.",
  "Flanagan, B. E., Gregory, E. W., Hallisey, E. J., Heitgerd, J. L., & Lewis, B. (2011). A social vulnerability index for disaster management. Journal of Homeland Security and Emergency Management, 8(1).",
];

function utcDay(iso: string, withYear: boolean): string {
  return new Date(iso).toLocaleDateString("en-US", {
    month: "short",
    day: "numeric",
    ...(withYear ? { year: "numeric" } : {}),
    timeZone: "UTC",
  });
}

const GAP_TEXT = `${utcDay(NISAR_GAP.start, false)} to ${utcDay(NISAR_GAP.end, true)}`;

export default function About() {
  return (
    <main className="pg">
      <div className="pg-inner">
        <div className="pg-kicker">About and methods</div>
        <h1>About SARstellar</h1>
        <p className="pg-sub">
          Two radars, one map. SARstellar compares what NISAR's L-band radar and Sentinel-1's C-band radar each see
          change on the ground: on a box you draw, in three stories, and across the eligible US sites in the national
          scorecard. Amber means only NISAR saw a change, violet means both did, cyan means only Sentinel-1 did.
        </p>

        <section className="pg-card">
          <h2>Data we use</h2>
          <div className="pg-data">
            {DATA.map((d) => (
              <div key={d.name}>
                <b>
                  <a href={d.href} target="_blank" rel="noreferrer">
                    {d.name}
                  </a>
                </b>
                {d.use} <span>Source: {d.source}.</span>
              </div>
            ))}
          </div>
        </section>

        <section className="pg-card">
          <h2>Method</h2>
          <ol className="pg-list">
            <li>
              <b>Find comparable passes.</b> For the box and dates, use one NISAR track, direction, mode and processing
              version so every date is comparable. Skip BETA and mixed-mode passes. Compare the NISAR series with a
              Sentinel-1 pair near its first and last dates (within six days), and record the offsets.
            </li>
            <li>
              <b>Read only the box</b> from NASA's servers, with retries when a server hiccups.
            </li>
            <li>
              <b>Average into 1-hectare blocks</b> (10 × 10 NISAR pixels, at least half of them valid), with Sentinel-1
              on the same grid. Single pixels swing by about ±3 dB from radar speckle, so no number is ever quoted per
              pixel.
            </li>
            <li>
              <b>Remove the background shift.</b> Subtract the typical change of unchanged ground in the same land cover,
              which cancels scene-wide shifts from moisture or calibration.
            </li>
            <li>
              <b>Test every block.</b> The omnibus change test (Conradsen et al., 2016) gives each block a p-value per
              radar band. The Benjamini–Hochberg procedure targets a 5% false discovery rate across the box. A block
              counts as changed only if it is significant and moved by at least 2 dB.
            </li>
            <li>
              <b>Compare the radars.</b> Connected changed blocks of at least 3 ha form a change area, marked as seen by
              only NISAR, by both, or by only Sentinel-1.
            </li>
            <li>
              <b>Name the likely cause</b> with physics rules (open-water flood, flooded vegetation, forest loss, burn,
              crop cycle, soil wetting, construction and others), each with a confidence. Freeze-up is a known false
              alarm and is suppressed; anything the rules can't explain is labelled uncertain.
            </li>
            <li>
              <b>Explain in plain words.</b> A language model rewrites the rule output as two or three sentences (see AI
              use below).
            </li>
            <li>
              <b>Score it across US sites.</b> The scorecard reports actual attempted, eligible and held-out counts.
              Its primary comparison pins both radars to two dates, uses identical valid blocks, and compares raw
              NISAR and Sentinel-1 with Fisher and Bonferroni fusion. Supervised logistic fusion is compared separately
              with equally trained single-radar models. Whole sites are resampled for confidence intervals.
            </li>
          </ol>
        </section>

        <section className="pg-card">
          <h2>Limits</h2>
          <div className="pg-callout">
            <b>Neither radar always wins.</b> The early Kaiser Canyon spike favored Sentinel-1, but the full pipeline
            changed that comparison. The story shows the pipeline's current areas and agreement, rather than the early
            spike totals. A radar difference alone does not establish the cause of a change.
          </div>
          <ul className="pg-list">
            <li>
              NISAR has no data at all from {GAP_TEXT} (UTC). Charts and the timeline show this gap rather than bridging
              it.
            </li>
            <li>
              Only calibrated NISAR products are used. Uncalibrated BETA data is excluded, which rules out NISAR's
              December 2025 Washington floods.
            </li>
            <li>
              The scorecard's references are other satellite products (optical alerts, fire perimeters, water and crop
              maps), not field surveys. DSWx-S1 uses Sentinel-1 and is not an independent flood check. CDL identifies
              cultivated land, not the timing or existence of a crop change.
            </li>
            <li>
              NISAR is 10 m and Sentinel-1 is 30 m. The scorecard's "NISAR at 30 m" variant changes pixel sampling; it
              does not isolate wavelength from timing, geometry, processing or other sensor differences.
            </li>
            <li>
              The two radars rarely pass on the same day. A Sentinel-1 pass can be days away from the NISAR pass it is
              paired with, and a flood can recede in between.
            </li>
            <li>
              Cause labels come from rules and carry a confidence. Landslide and wet-snow labels are low confidence, and
              changes only Sentinel-1 saw that no rule explains are marked "cause uncertain".
            </li>
            <li>
              Claims are for the United States only. Drawn boxes are limited to 20 km a side, and live analysis may be
              paused under heavy load; stories and the scorecard keep working.
            </li>
            <li>Saved examples from early test runs are marked "Example data" until the final pipeline replaces them.</li>
          </ul>
        </section>

        <section className="pg-card">
          <h2>AI use</h2>
          <ul className="pg-list">
            <li>
              <b>Plain-language text.</b> Claude (Anthropic, model claude-sonnet-5-5) rewrites each change area's rule
              output (class, confidence, evidence numbers) as two or three sentences, when configured. The prompt
              requires it to use only supplied facts; the structured class and confidence remain unchanged. If the
              call fails or no key is set, a fixed template is used instead.
            </li>
            <li>
              <b>Cause labels and learned fusion.</b> Cause labels currently come from rules. The benchmark's logistic
              fusion is a separate change-detection comparison; it does not validate the cause labels. The stretch
              learned cause classifier has not shipped.
            </li>
            <li>
              <b>Building the app.</b> The team wrote this software with AI coding assistants (Claude Code and OpenAI
              Codex). Automated checks and real-data runs were used to validate the changes.
            </li>
            <li>
              <b>Images.</b> Map overlays are rendered directly from radar data. The app contains no AI-generated images.
            </li>
          </ul>
        </section>

        <section className="pg-card">
          <h2>References</h2>
          <ol className="pg-list pg-refs">
            {REFERENCES.map((r) => (
              <li key={r}>{r}</li>
            ))}
            <li>
              NASA-ISRO SAR (NISAR) mission, NASA Jet Propulsion Laboratory:{" "}
              <a href="https://nisar.jpl.nasa.gov/" target="_blank" rel="noreferrer">
                nisar.jpl.nasa.gov
              </a>
              .
            </li>
            <li>
              OPERA (Observational Products for End-Users from Remote Sensing Analysis), NASA Jet Propulsion Laboratory:{" "}
              <a href="https://www.jpl.nasa.gov/go/opera" target="_blank" rel="noreferrer">
                jpl.nasa.gov/go/opera
              </a>
              .
            </li>
          </ol>
        </section>

        <section className="pg-card">
          <h2>License</h2>
          <p className="pg-note">
            Code is open source under the Apache-2.0 license at{" "}
            <a href={REPO} target="_blank" rel="noreferrer">
              github.com/saa938/sarstellar
            </a>
            . NISAR, OPERA and FIRMS data are openly available from NASA. Sentinel-1 products contain modified Copernicus
            Sentinel data (2025–2026). Basemap imagery © Esri and its data providers. Built for the NASA Space Apps
            Challenge 2026 ("Dancing with the SARs"); not an official NASA product.
          </p>
        </section>
      </div>
    </main>
  );
}
