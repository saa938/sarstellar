// Animated physics primer: a radar pulse meets five kinds of surface, and the two partners
// (HH and HV) each hear a different amount of the echo.

export type SurfaceKind = "soil" | "forest" | "flooded" | "water" | "snow";

export const SURFACES: Record<SurfaceKind, { title: string; mech: string; hh: number; hv: number; text: string }> = {
  soil: { title: "Bare soil", mech: "Surface scattering", hh: 2, hv: 1, text: "A rough surface scatters part of the pulse back. HH hears it; HV hears almost nothing." },
  forest: { title: "Forest canopy", mech: "Volume scattering", hh: 3, hv: 4, text: "Leaves and branches toss the wave around and twist it. That twisted echo is what HV hears best." },
  flooded: { title: "Flooded forest", mech: "Double bounce", hh: 5, hv: 3, text: "Water and trunks form a corner that fires the pulse straight back. HH jumps; HV barely changes." },
  water: { title: "Open water", mech: "Mirror reflection", hh: 0, hv: 0, text: "Calm water reflects the pulse away like a mirror. Almost nothing returns, so both go dark." },
  snow: { title: "Wet snow", mech: "Absorption", hh: 1, hv: 0, text: "Liquid water in melting snow soaks up the pulse. The surface goes quiet, so HH plunges." },
};

const SAT: [number, number] = [26, 24];

function Satellite() {
  return (
    <g transform={`translate(${SAT[0]},${SAT[1]}) rotate(28)`} className="sd__sat">
      <rect x="-5" y="-4" width="10" height="8" rx="1.5" />
      <rect x="-19" y="-2.5" width="12" height="5" rx="1" className="sd__panel" />
      <rect x="7" y="-2.5" width="12" height="5" rx="1" className="sd__panel" />
    </g>
  );
}

function Returns({ to, hh, hv }: { to: [number, number]; hh: number; hv: number }) {
  // two return beams back to the satellite, width by loudness
  const off = 5;
  const mk = (dx: number) => `M${to[0] + dx},${to[1] - 4} L${SAT[0] + 10 + dx},${SAT[1] + 10}`;
  return (
    <g className="sd__returns">
      {hh > 0 && <path d={mk(-off)} className="sd__ret sd__ret--hh" style={{ strokeWidth: 0.8 + hh * 1.1 }} />}
      {hv > 0 && <path d={mk(off)} className="sd__ret sd__ret--hv" style={{ strokeWidth: 0.8 + hv * 1.1 }} />}
    </g>
  );
}

export function ScatterDiagram({ kind }: { kind: SurfaceKind }) {
  const s = SURFACES[kind];
  let surface = null;
  let pulse = "";
  let target: [number, number] = [140, 136];
  let extra = null;
  switch (kind) {
    case "soil":
      target = [138, 134];
      pulse = `M${SAT[0] + 8},${SAT[1] + 8} L${target[0]},${target[1]}`;
      surface = (
        <path d="M0,140 l12,-5 l9,6 l10,-7 l8,5 l11,-4 l9,6 l10,-6 l9,5 l12,-5 l10,6 l9,-6 l11,5 l10,-5 l9,6 l12,-4 l9,4 l10,-5 l10,5 l11,-4 l9,5 l12,-5 l10,4 l9,-4 l12,5 l10,-3 L260,138 V180 H0Z" className="sd__soil" />
      );
      extra = (
        <g className="sd__scatter">
          {[-150, -120, -60, -30, -95].map((a, i) => {
            const r = (a * Math.PI) / 180;
            return <path key={i} d={`M${target[0]},${target[1] - 3} l${Math.cos(r) * 22},${Math.sin(r) * 22}`} />;
          })}
        </g>
      );
      break;
    case "forest":
      target = [140, 92];
      pulse = `M${SAT[0] + 8},${SAT[1] + 8} L${target[0]},${target[1]}`;
      surface = (
        <g>
          <rect x="0" y="150" width="260" height="30" className="sd__ground" />
          {[92, 140, 190].map((x, i) => (
            <g key={i}>
              <rect x={x - 2.5} y={98} width="5" height="54" className="sd__trunk" />
              <ellipse cx={x} cy={92 - (i % 2) * 4} rx="30" ry="24" className="sd__canopy" />
              <path d={`M${x},${110} l-12,-14 M${x},${104} l11,-12 M${x},${118} l14,-10`} className="sd__branch" />
            </g>
          ))}
        </g>
      );
      extra = (
        <g className="sd__scatter sd__scatter--vol">
          <path d="M140,92 l-14,8 l10,9 l-8,-20 l18,-4 l-6,16" />
          <path d="M150,84 l12,6 l-6,10 l14,-2" />
        </g>
      );
      break;
    case "flooded":
      target = [150, 112];
      pulse = `M${SAT[0] + 8},${SAT[1] + 8} L136,140 L${target[0]},${target[1]}`;
      surface = (
        <g>
          <rect x="0" y="140" width="260" height="40" className="sd__water" />
          <path d="M0,140 H260" className="sd__waterline" />
          {[100, 150, 200].map((x, i) => (
            <g key={i}>
              <rect x={x - 3} y={64} width="6" height="78" className="sd__trunk" />
              <ellipse cx={x} cy={58} rx="27" ry="17" className="sd__canopy sd__canopy--thin" />
              <rect x={x - 3} y={142} width="6" height="14" className="sd__trunk sd__trunk--reflect" />
            </g>
          ))}
        </g>
      );
      break;
    case "water":
      target = [130, 140];
      pulse = `M${SAT[0] + 8},${SAT[1] + 8} L${target[0]},${target[1]} L250,40`;
      surface = (
        <g>
          <rect x="0" y="140" width="260" height="40" className="sd__water sd__water--deep" />
          <path d="M0,140 H260" className="sd__waterline" />
          <path d="M40,152 h30 M120,160 h44 M190,150 h26" className="sd__shine" />
        </g>
      );
      extra = <text x="200" y="76" className="sd__note">away from the satellite</text>;
      break;
    case "snow":
      target = [136, 128];
      pulse = `M${SAT[0] + 8},${SAT[1] + 8} L${target[0]},${target[1]}`;
      surface = (
        <g>
          <path d="M0,124 C40,118 80,128 130,122 S210,118 260,124 V180 H0Z" className="sd__snow" />
          <path d="M0,150 H260 V180 H0Z" className="sd__ice" />
          {[30, 70, 110, 160, 200, 236].map((x, i) => (
            <circle key={i} cx={x} cy={136 + (i % 3) * 5} r="2" className="sd__melt" />
          ))}
        </g>
      );
      extra = <circle cx={target[0]} cy={target[1] + 6} r="10" className="sd__absorb" />;
      break;
  }
  return (
    <svg className={`sd sd--${kind}`} viewBox="0 0 260 180" role="img" aria-label={`${s.title}: ${s.mech}`}>
      <defs>
        <linearGradient id={`sd-fade-${kind}`} x1="0" y1="0" x2="0" y2="1">
          <stop offset="0" stopColor="#fff" stopOpacity="0.9" />
          <stop offset="1" stopColor="#fff" stopOpacity="0.2" />
        </linearGradient>
      </defs>
      {surface}
      <path d={pulse} className="sd__pulse-base" />
      <path d={pulse} className="sd__pulse" pathLength={300} />
      {extra}
      <Returns to={target} hh={s.hh} hv={s.hv} />
      <Satellite />
    </svg>
  );
}

export function Meter({ label, value, pol }: { label: string; value: number; pol: "hh" | "hv" }) {
  return (
    <div className={`meter meter--${pol}`}>
      <span className="meter__label">{label}</span>
      <span className="meter__dots" aria-label={`${label}: ${value} of 5`}>
        {[1, 2, 3, 4, 5].map((i) => (
          <i key={i} className={i <= value ? "is-on" : ""} />
        ))}
      </span>
    </div>
  );
}
