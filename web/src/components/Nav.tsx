interface Props {
  active?: string;
  variant?: "overlay" | "solid";
}

const LINKS = [
  { href: "#/", label: "Story", id: "story" },
  { href: "#/places", label: "Places", id: "places" },
  { href: "#/method", label: "Method", id: "method" },
];

export function Logo() {
  return (
    <a href="#/" className="logo" aria-label="SARstellar home">
      <span>
        SAR<em>stellar</em>
      </span>
    </a>
  );
}

export function Nav({ active, variant = "solid" }: Props) {
  return (
    <header className={`nav nav--${variant}`}>
      <Logo />
      <div className="nav__mid" />
      <nav className="nav__links nav__links--always" aria-label="Sections">
        {LINKS.map((l) => (
          <a key={l.id} href={l.href} className={active === l.id ? "is-on" : ""}>
            {l.label}
          </a>
        ))}
      </nav>
    </header>
  );
}
