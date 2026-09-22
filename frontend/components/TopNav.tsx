"use client";

import Link from "next/link";

import { useLiveMonitoring } from "@/lib/live-monitoring-provider";
import type { NavSection } from "@/lib/types";
import { useAlerts } from "@/lib/queries";

const navigation: Array<{ id: NavSection; label: string; href: string }> = [
  { id: "pregame", label: "Pregame", href: "/pregame" },
  { id: "player-watch", label: "Player Watch", href: "/player-watch" },
  { id: "alerts", label: "Alerts", href: "/alerts" },
];

export function TopNav({ active }: { active: NavSection }) {
  const alertsQuery = useAlerts();
  const monitoring = useLiveMonitoring();
  const watchedCount = monitoring.selectedBatterIds.length + monitoring.selectedPitcherIds.length;

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

        <div className="topbar__status-group">
          {monitoring.gameId !== null ? (
            <div
              className={monitoring.isMonitoring ? "monitoring-status is-active" : "monitoring-status"}
              title={
                monitoring.lastSyncError
                  ? `Live sync error: ${monitoring.lastSyncError}`
                  : `Game ${monitoring.gameId} · ${watchedCount} watched player${watchedCount === 1 ? "" : "s"}`
              }
            >
              <span className="monitoring-status__dot" aria-hidden="true" />
              {monitoring.isMonitoring ? "Monitoring" : "Stopped"}
              <span className="monitoring-status__meta">
                Game {monitoring.gameId} · {watchedCount} watched
              </span>
              {monitoring.lastSyncError ? (
                <span className="monitoring-status__error" aria-hidden="true">
                  !
                </span>
              ) : null}
            </div>
          ) : null}

          <div className="system-status" title="FastAPI data mode">
            <span className="system-status__dot" aria-hidden="true" />
            API workspace
          </div>
        </div>
      </div>
    </header>
  );
}
