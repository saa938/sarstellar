import { REPO_URL } from "../lib/credits";

export function Footer() {
  return (
    <footer className="footer2">
      <div className="footer2__inner">
        <div className="footer2__name">
          SAR<em>stellar</em>
        </div>
        <p>
          NASA Space Apps Challenge 2026, "Dancing with the SARs". Radar: NISAR L2 GCOV, a NASA-ISRO mission, via the ASF DAAC. This project is independent
          and not endorsed by NASA or ISRO.
        </p>
        <div className="footer2__links">
          <a href="#/method">Method, data and credits</a>
          <a href={REPO_URL} target="_blank" rel="noreferrer">
            Source code (Apache-2.0)
          </a>
        </div>
      </div>
    </footer>
  );
}
