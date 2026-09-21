"use client";

import Link from "next/link";

import type { NavSection } from "@/lib/types";
import { useAlerts } from "@/lib/queries";

const navigation: Array<{ id: NavSection; label: string; href: string }> = [
  { id: "pregame", label: "Pregame", href: "/pregame" },
  { id: "player-watch", label: "Player Watch", href: "/player-watch" },
  { id: "alerts", label: "Alerts", href: "/alerts" },
];

export function TopNav({ active }: { active: NavSection }) {
  const alertsQuery = useAlerts();

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
              {item.id === "alerts" && alertsQuery.data ? (
                <span className="nav-count">{alertsQuery.data.length}</span>
              ) : null}
            </Link>
          ))}
        </nav>

        <div className="system-status" title="FastAPI data mode">
          <span className="system-status__dot" aria-hidden="true" />
          API workspace
        </div>
      </div>
    </header>
  );
}
