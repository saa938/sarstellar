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
        <header className="pg-report-header">
          <h1>Methods</h1>
          <p className="pg-sub">NISAR L-band and Sentinel-1 C-band change detection on 1-hectare blocks.</p>
        </header>

        <section className="pg-card">
          <h2>Data</h2>
          <div className="pg-data">
            {DATA.slice(0, 2).map((d) => (
              <div key={d.name}>
                <b><a href={d.href} target="_blank" rel="noreferrer">{d.name}</a></b>
                {d.use} <span>Source: {d.source}.</span>
              </div>
            ))}
          </div>
          <details>
            <summary>Reference layers and context</summary>
            <div className="pg-data">
              {DATA.slice(2).map((d) => (
                <div key={d.name}>
                  <b><a href={d.href} target="_blank" rel="noreferrer">{d.name}</a></b>
                  {d.use} <span>Source: {d.source}.</span>
                </div>
              ))}
            </div>
          </details>
        </section>

        <section className="pg-card">
          <h2>Processing</h2>
          <ol className="pg-list">
            <li><b>Acquisitions.</b> One NISAR track, direction, mode and processing version. Calibrated products only;
              BETA and mixed-mode passes excluded. Sentinel-1 uses a pair within six days of the first and last NISAR dates.</li>
            <li><b>Grid.</b> 100 m blocks (1 ha), with at least 50% valid NISAR pixels on every date.
              Sentinel-1 is averaged onto the same grid.</li>
            <li><b>Normalization.</b> Remove scene shifts using stable ground. Estimate radar noise from the data,
              with separate land-cover strata where enough stable blocks exist.</li>
            <li><b>Detection.</b> Omnibus change test; Benjamini–Hochberg FDR q = 0.05;
              absolute relative change ≥ 2 dB. Connected change areas must cover at least 3 ha.</li>
            <li><b>Interpretation.</b> Rules assign likely cause, confidence and supporting measurements.
              Unsupported causes remain uncertain. Freeze-up is treated as a potential confounder.</li>
          </ol>
        </section>

        <section className="pg-card">
          <h2>Validation</h2>
          <ul className="pg-list">
            <li><b>Primary comparison.</b> Two catalogued dates per radar, identical valid blocks, raw single-sensor
              detectors versus Fisher or Bonferroni fusion.</li>
            <li><b>Geographic hold-out.</b> Fitting and method selection use training states only.
              Results are evaluated on held-out states; uncertainty uses whole-site paired bootstrap intervals.</li>
            <li><b>Supervised comparison.</b> Logistic fusion is evaluated separately against equally trained
              single-sensor models. This benchmark does not validate cause labels.</li>
          </ul>
          <p className="pg-note"><a href="#/scorecard">Benchmark: sample counts, class results and confidence intervals</a></p>
        </section>

        <section className="pg-card">
          <h2>Limits</h2>
          <ul className="pg-list">
            <li><b>Reference dependence.</b> DSWx-S1 uses Sentinel-1 and is not an independent flood check.
              CDL identifies cultivated land, not confirmed crop change. Reference products are not field surveys.</li>
            <li><b>Sampling.</b> The NISAR-at-30 m variant changes pixel sampling; it does not isolate wavelength from
              acquisition timing, geometry, processing or other sensor differences.</li>
            <li><b>Missing dates.</b> NISAR has no data from {GAP_TEXT} (UTC). Charts show the gap.
              Offset radar acquisitions can also miss short-lived floods.</li>
            <li><b>Case sensitivity.</b> The early Kaiser Canyon spike favored Sentinel-1; the full pipeline changed
              that comparison. Published cases use the current pipeline, not the early spike totals.</li>
            <li><b>Scope.</b> US reference coverage. Live boxes are limited to 20 km per side. Static cases and
              benchmark results remain available when live analysis is paused.</li>
          </ul>
        </section>

        <section className="pg-card">
          <h2>AI use</h2>
          <p className="pg-note">Cause labels currently come from rules. Optional Claude explanations use supplied
            evidence; structured labels and confidence are unchanged. A fixed template is used when no key is set or a
            call fails. Logistic fusion is a benchmark detector; the stretch learned cause classifier has not shipped.</p>
          <details>
            <summary>Implementation disclosure</summary>
            <p>Claude Code and OpenAI Codex assisted development. Automated checks and real-data runs validate changes.
              Radar overlays are rendered from data; no AI-generated imagery is used.
              Optional text model: Anthropic claude-sonnet-5-5.</p>
          </details>
        </section>

        <section className="pg-card">
          <h2>References</h2>
          <details>
            <summary>Scientific references and mission documentation</summary>
            <ol className="pg-list pg-refs">
              {REFERENCES.map((r) => <li key={r}>{r}</li>)}
              <li><a href="https://nisar.jpl.nasa.gov/" target="_blank" rel="noreferrer">NASA-ISRO SAR mission documentation</a></li>
              <li><a href="https://www.jpl.nasa.gov/go/opera" target="_blank" rel="noreferrer">NASA OPERA mission documentation</a></li>
            </ol>
          </details>
        </section>

        <section className="pg-card">
          <h2>License</h2>
          <p className="pg-note">Apache-2.0 code: <a href={REPO} target="_blank" rel="noreferrer">github.com/saa938/sarstellar</a>.
            NASA data are openly available. Sentinel-1 products contain modified Copernicus Sentinel data (2025–2026).
            Basemap imagery © Esri and its providers. NASA Space Apps Challenge 2026; not an official NASA product.</p>
        </section>
      </div>
    </main>
  );
}
