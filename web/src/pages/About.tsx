import { Nav } from "../components/Nav";
import { Footer } from "../components/Footer";
import { DATA_CREDITS, REPO_URL } from "../lib/credits";

export default function About() {
  return (
    <div className="page">
      <Nav active="about" />
      <header className="page__head">
        <div className="eyebrow">About</div>
        <h1 className="act__title">How SARstellar works</h1>
        <p className="act__lede" style={{ maxWidth: 780 }}>
          SARstellar turns NISAR's radar into a dance you can read. Every hectare becomes a dot placed by its two echoes, HH and HV, and every 12 days, when
          NISAR passes over again, every dot takes a step. Each kind of change on the ground moves in its own way.
        </p>
      </header>
      <div className="page__body">
        <ol className="method about__steps">
          <li>
            <strong>Read every pass.</strong> For each place, every NISAR L2 GCOV image of the same orbit track and mode is read and averaged into 100 m
            squares, one hectare each, in HH and HV (decibels).
          </li>
          <li>
            <strong>Place every hectare on the floor.</strong> Across: HH, which hears surfaces and bounces. Up: HV, which hears leaves, branches and crop
            canopies. Water, soil, crops, forest and double bounce each have their own corner.
          </li>
          <li>
            <strong>Learn the moves where the answer is known.</strong> A model learns how much HH and HV change in each move from reference sites with
            independent labels: optical forest-loss alerts, fire perimeters, water maps, crop maps.
          </li>
          <li>
            <strong>Test where it never looked.</strong> Scores come from whole states held out of training, with intervals, and a polarization report
            card that retrains with HH only and HV only. Everything is on <a href="#/proof">How we know</a>.
          </li>
        </ol>

        <section className="about__sec">
          <h2 className="proof__h">Data and credits</h2>
          <div className="credits">
            {DATA_CREDITS.map((c) => (
              <a key={c.name} className="credit" href={c.url} target="_blank" rel="noreferrer">
                <strong>{c.name}</strong>
                <span>{c.role}</span>
              </a>
            ))}
          </div>
        </section>

        <section className="about__sec">
          <h2 className="proof__h">Open source</h2>
          <p className="proof__p">
            The pipeline that reads NISAR, the model, the evaluation and this site are open source under the Apache-2.0 license, so every number here can
            be reproduced.
          </p>
          <a className="btn btn--primary" href={REPO_URL} target="_blank" rel="noreferrer">
            Source code on GitHub <span className="arrow">→</span>
          </a>
        </section>

        <section className="about__sec">
          <h2 className="proof__h">The fine print</h2>
          <ul className="limits">
            <li>Built for the NASA Space Apps Challenge 2026, "Dancing with the SARs".</li>
            <li>NISAR is a joint mission of NASA and the Indian Space Research Organisation. SARstellar is independent and is not endorsed by either agency.</li>
            <li>NISAR data shown here are provisional releases from 2025 and 2026; reprocessing can shift values.</li>
          </ul>
        </section>
      </div>
      <Footer />
    </div>
  );
}
