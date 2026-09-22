import type { AlertData, AlertsSummaryData } from "@/lib/types";
import { DataState } from "@/components/DataState";

export type RoleFilter = "pitcher" | "batter" | "all";

const ruleLabels: Record<AlertData["rule"], string> = {
  extra_base_hit: "extra_base_hit",
  hard_contact: "hard_contact",
  high_velocity_hit: "high_velocity_hit",
  pitcher_extra_base_hit_allowed: "pitcher_extra_base_hit_allowed",
  pitcher_high_exit_velocity_allowed: "pitcher_high_exit_velocity_allowed",
};

function ruleSignal(rule: AlertData["rule"]): string {
  if (rule === "extra_base_hit" || rule === "pitcher_extra_base_hit_allowed") return "XBH";
  if (rule === "hard_contact" || rule === "pitcher_high_exit_velocity_allowed") return "EV";
  return "V+";
}

interface AlertsPanelProps {
  // Already filtered to `roleFilter` by the caller, so the summary counts
  // (Today / High priority) and the list below always agree.
  alerts: AlertData[];
  summary: AlertsSummaryData;
  roleFilter: RoleFilter;
  onRoleFilterChange: (role: RoleFilter) => void;
}

export function AlertsPanel({ alerts, summary, roleFilter, onRoleFilterChange }: AlertsPanelProps) {
  return (
    <section className="panel alerts-panel" aria-labelledby="alerts-title">
      <div className="alerts-summary">
        <div>
          <p className="section-kicker">Opponent pitcher scouting</p>
          <h2 id="alerts-title">Recent Alerts</h2>
        </div>
        <dl>
          <div><dt>Today</dt><dd>{summary.today}</dd></div>
          <div><dt>High priority</dt><dd>{summary.highPriority}</dd></div>
          <div><dt>Tracked players</dt><dd>{summary.trackedPlayers}</dd></div>
        </dl>
      </div>

      <div className="role-tabs" role="tablist" aria-label="Alert subject">
        {(["pitcher", "batter", "all"] as const).map((role) => (
          <button
            key={role}
            type="button"
            className={roleFilter === role ? "is-active" : ""}
            onClick={() => onRoleFilterChange(role)}
          >
            {role === "pitcher" ? "Pitcher" : role === "batter" ? "Batter" : "All"}
          </button>
        ))}
      </div>

      {alerts.length === 0 ? (
        <DataState>No {roleFilter === "all" ? "" : `${roleFilter} `}alerts have been recorded yet.</DataState>
      ) : (
        <div className="alert-list">
          {alerts.map((alert) => (
            <article className="alert-row" data-severity={alert.severity} key={alert.id}>
              <div className="alert-row__signal" aria-hidden="true">
                {ruleSignal(alert.rule)}
              </div>
              <div className="alert-row__body">
                <div className="alert-row__titleline">
                  <div>
                    <h3>{alert.event}</h3>
                    <span>{alert.player} · {alert.team} · {alert.subjectRole}</span>
                  </div>
                </div>
                <p>{alert.detail}</p>
                <div className="alert-row__meta">
                  <span className="rule-code">Rule: {ruleLabels[alert.rule]}</span>
                </div>
              </div>
              <div className="alert-row__moment" aria-label="Alert timing">
                <time>{alert.timestamp}</time>
                <span>{alert.gameMoment}</span>
              </div>
            </article>
          ))}
        </div>
      )}
    </section>
  );
}
