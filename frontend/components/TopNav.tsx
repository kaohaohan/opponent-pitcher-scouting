import Link from "next/link";

import type { NavSection } from "@/lib/types";

const navigation: Array<{ id: NavSection; label: string; href: string }> = [
  { id: "pregame", label: "Pregame", href: "/pregame" },
  { id: "player-watch", label: "Player Watch", href: "/player-watch" },
  { id: "alerts", label: "Alerts", href: "/alerts" },
];

export function TopNav({ active }: { active: NavSection }) {
  return (
    <header className="topbar">
      <div className="topbar__inner">
        <Link className="brand" href="/pregame" aria-label="Baseball Intelligence home">
          <span className="brand__mark" aria-hidden="true">
            BI
          </span>
          <span className="brand__copy">
            <span className="brand__name">Baseball Intelligence</span>
            <span className="brand__descriptor">Game preparation console</span>
          </span>
        </Link>

        <nav className="primary-nav" aria-label="Primary navigation">
          {navigation.map((item) => (
            <Link
              className="primary-nav__link"
              data-active={active === item.id}
              href={item.href}
              key={item.id}
            >
              {item.label}
              {item.id === "alerts" ? <span className="nav-count">4</span> : null}
            </Link>
          ))}
        </nav>

        <div className="system-status" title="Mock data mode">
          <span className="system-status__dot" aria-hidden="true" />
          Mock workspace
        </div>
      </div>
    </header>
  );
}
