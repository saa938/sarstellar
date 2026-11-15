// "Analyze it yourself": the live radar change map (/map) embedded at this place, ready to draw a box.
// Live analysis covers US boxes only, so other places get a short note and a link instead.
import "./PlaceAnalyze.css";

type BBox = [number, number, number, number];

const inUS = ([w, s, e, n]: BBox) => w >= -180 && e <= -60 && s >= 17 && n <= 72;

export default function PlaceAnalyze({ id, name, bbox }: { id: string; name: string; bbox: BBox }) {
  const q = `place=${encodeURIComponent(id)}&bbox=${bbox.map((v) => v.toFixed(4)).join(",")}`;
  if (!inUS(bbox)) {
    return (
      <section className="page__body placeanalyze" aria-label="Analyze it yourself">
        <div className="eyebrow">Analyze it yourself</div>
        <p className="placeanalyze__note">
          Live NISAR and Sentinel-1 change analysis runs on US boxes for now, so {name} can't be analyzed live.{" "}
          <a href="/map/">Open the analysis map</a> to draw a box anywhere in the US.
        </p>
      </section>
    );
  }
  return (
    <section className="page__body placeanalyze" aria-label={`Analyze ${name}`}>
      <div className="placeanalyze__head">
        <div>
          <div className="eyebrow">Analyze it yourself</div>
          <h2 className="placetext__title">Draw a box, get the evidence</h2>
          <p className="placeanalyze__note">
            Compare NISAR L-band and Sentinel-1 C-band here on a 1-hectare grid. Draw a box up to 20 km a side, then click
            any change to see what changed, when, and which radar to trust.
          </p>
        </div>
        <a className="linkbtn" href={`/map/?${q}`}>
          Open full screen →
        </a>
      </div>
      <iframe className="placeanalyze__frame" src={`/map/?embed=1&${q}`} title={`Radar change analysis map for ${name}`} loading="lazy" />
    </section>
  );
}
