import type { ReactNode } from "react";

interface Props {
  active?: string;
  children?: ReactNode;
  variant?: "overlay" | "solid";
  className?: string;
}

const LINKS = [
  { href: "#/", label: "Story", id: "landing" },
  { href: "#/explore", label: "Stages", id: "explore" },
  { href: "#/moves", label: "Field guide", id: "moves" },
  { href: "#/proof", label: "How we know", id: "proof" },
];

export function Logo() {
  return (
    <a href="#/" className="logo" aria-label="SARstellar home">
      <svg viewBox="0 0 32 32" width="22" height="22" aria-hidden>
        <circle cx="9" cy="22" r="1.8" fill="#9dbcff" opacity=".85" />
        <circle cx="15.5" cy="15" r="2.1" fill="#f2d08a" />
        <circle cx="23" cy="9" r="2.6" fill="#f7e3b5" />
        <circle cx="23" cy="9" r="6" fill="#f2d08a" opacity=".16" />
        <path d="M4 27 Q 12 24 15.5 15 T 28 4" stroke="#f2d08a" strokeOpacity=".4" strokeWidth="1" fill="none" />
      </svg>
      <span>
        SAR<em>stellar</em>
      </span>
    </a>
  );
}

export function Nav({ active, children, variant = "solid", className = "" }: Props) {
  return (
    <header className={`nav nav--${variant} ${className}`}>
      <Logo />
      <div className="nav__mid">{children}</div>
      <nav className="nav__links" aria-label="Sections">
        {LINKS.map((l) => (
          <a key={l.id} href={l.href} className={active === l.id ? "is-on" : ""}>
            {l.label}
          </a>
        ))}
      </nav>
    </header>
  );
}
