import { DATA_CREDITS, REPO_URL } from "../lib/credits";

export function Footer() {
  return (
    <footer className="footer">
      <div className="footer__inner">
        <div className="footer__brand">
          <div className="footer__name">
            SAR<em>stellar</em>
          </div>
          <p>
            An open-source project for the NASA Space Apps Challenge 2026, "Dancing with the SARs". NISAR is a joint mission of NASA and ISRO. SARstellar is
            not affiliated with or endorsed by NASA or ISRO.
          </p>
          <a className="footer__repo" href={REPO_URL} target="_blank" rel="noreferrer">
            <svg viewBox="0 0 16 16" width="15" height="15" aria-hidden>
              <path
                fill="currentColor"
                d="M8 0C3.58 0 0 3.58 0 8a8 8 0 0 0 5.47 7.59c.4.07.55-.17.55-.38v-1.33c-2.23.48-2.7-1.07-2.7-1.07-.36-.92-.89-1.17-.89-1.17-.73-.5.06-.49.06-.49.8.06 1.23.83 1.23.83.72 1.22 1.88.87 2.34.66.07-.52.28-.87.5-1.07-1.78-.2-3.65-.89-3.65-3.95 0-.87.31-1.59.82-2.15-.08-.2-.36-1.02.08-2.12 0 0 .67-.21 2.2.82a7.6 7.6 0 0 1 4 0c1.53-1.04 2.2-.82 2.2-.82.44 1.1.16 1.92.08 2.12.51.56.82 1.28.82 2.15 0 3.07-1.87 3.75-3.65 3.95.29.25.54.73.54 1.48v2.2c0 .21.15.46.55.38A8 8 0 0 0 16 8c0-4.42-3.58-8-8-8z"
              />
            </svg>
            Source code on GitHub · Apache-2.0
          </a>
        </div>
        <div className="footer__cols">
          <div>
            <h4>Data</h4>
            <ul>
              {DATA_CREDITS.slice(0, 6).map((c) => (
                <li key={c.name}>
                  <a href={c.url} target="_blank" rel="noreferrer">
                    {c.name}
                  </a>
                </li>
              ))}
            </ul>
          </div>
          <div>
            <h4>Maps</h4>
            <ul>
              <li>
                <a href="https://nasa-gibs.github.io/gibs-api-docs/" target="_blank" rel="noreferrer">
                  Night lights: NASA GIBS, VIIRS Black Marble
                </a>
              </li>
              <li>Basemaps © Esri, HERE, Garmin, Maxar, Earthstar Geographics</li>
              <li>© OpenStreetMap contributors</li>
              <li>Rendered with MapLibre GL</li>
            </ul>
          </div>
          <div>
            <h4>Explore</h4>
            <ul>
              <li>
                <a href="#/explore">All stages</a>
              </li>
              <li>
                <a href="#/moves">Field guide to the moves</a>
              </li>
              <li>
                <a href="#/constellation">The constellation</a>
              </li>
              <li>
                <a href="#/proof">How we know</a>
              </li>
              <li>
                <a href="#/about">About and credits</a>
              </li>
            </ul>
          </div>
        </div>
      </div>
    </footer>
  );
}
