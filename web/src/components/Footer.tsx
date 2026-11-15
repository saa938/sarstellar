export function Footer() {
  return (
    <footer className="footer">
      <div className="footer__inner">
        <div className="footer__brand">
          <div className="footer__name">
            SAR<em>stellar</em>
          </div>
          <p>
            An independent NASA Space Apps Challenge 2026 project for "Dancing with the SARs". NISAR is a joint mission of NASA and ISRO. SARstellar is
            not affiliated with or endorsed by NASA or ISRO.
          </p>
        </div>
        <div className="footer__cols">
          <div>
            <h4>Data</h4>
            <ul>
              <li>
                <a href="https://asf.alaska.edu/" target="_blank" rel="noreferrer">
                  NISAR L2 GCOV, NASA-ISRO, via the ASF DAAC
                </a>
              </li>
              <li>
                <a href="https://earthdata.nasa.gov/gibs" target="_blank" rel="noreferrer">
                  VIIRS Black Marble night lights, NASA GIBS
                </a>
              </li>
              <li>OPERA DIST-ALERT and DSWx reference layers (NASA JPL)</li>
            </ul>
          </div>
          <div>
            <h4>Maps</h4>
            <ul>
              <li>© OpenStreetMap contributors © CARTO</li>
              <li>World Imagery © Esri, Maxar, Earthstar Geographics</li>
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
                <a href="#/proof">How we know</a>
              </li>
            </ul>
          </div>
        </div>
      </div>
    </footer>
  );
}
