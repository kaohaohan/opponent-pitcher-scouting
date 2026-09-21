import type { AlertData, AlertsSummaryData } from "@/lib/types";

const ruleLabels: Record<AlertData["rule"], string> = {
  extra_base_hit: "extra_base_hit",
  hard_contact: "hard_contact",
  high_velocity_hit: "high_velocity_hit",
};

interface AlertsPanelProps {
  alerts: AlertData[];
  summary: AlertsSummaryData;
}

export function AlertsPanel({ alerts, summary }: AlertsPanelProps) {
  return (
    <section className="panel alerts-panel" aria-labelledby="alerts-title">
      <div className="alerts-summary">
        <div>
          <p className="section-kicker">Watch-rule stream</p>
          <h2 id="alerts-title">Recent Alerts</h2>
        </div>
        <dl>
          <div><dt>Today</dt><dd>{summary.today}</dd></div>
          <div><dt>High priority</dt><dd>{summary.highPriority}</dd></div>
          <div><dt>Tracked players</dt><dd>{summary.trackedPlayers}</dd></div>
        </dl>
      </div>

      <div className="alert-list">
        {alerts.map((alert) => (
          <article className="alert-row" data-severity={alert.severity} key={alert.id}>
            <div className="alert-row__signal" aria-hidden="true">
              {alert.rule === "extra_base_hit" ? "2B" : alert.rule === "hard_contact" ? "EV" : "V+"}
            </div>
            <div className="alert-row__body">
              <div className="alert-row__titleline">
                <div>
                  <h3>{alert.event}</h3>
                  <span>{alert.player} · {alert.team}</span>
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
    </section>
  );
}
