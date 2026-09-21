import type { BriefSectionData } from "@/lib/types";
import { DataState } from "@/components/DataState";

export function PregameBrief({ sections }: { sections: BriefSectionData[] }) {
  return (
    <aside className="panel brief-panel" aria-labelledby="brief-title">
      <div className="panel-heading brief-heading">
        <div>
          <p className="section-kicker section-kicker--ai">AI interpretation</p>
          <h2 id="brief-title">Pre-game Brief</h2>
        </div>
        <span className="ai-label">AI</span>
      </div>

      <div className="brief-boundary">
        <span className="brief-boundary__icon" aria-hidden="true">◇</span>
        <p>
          Narrative interpretation of the structured facts shown at left. Statistics remain the
          source of truth.
        </p>
      </div>

      {sections.length === 0 ? (
        <DataState>Generate a brief to see the backend analysis.</DataState>
      ) : (
        <div className="brief-sections">
          {sections.map((section, index) => (
            <section className="brief-section" data-kind={section.kind} key={section.title}>
              <div className="brief-section__index">{String(index + 1).padStart(2, "0")}</div>
              <div>
                <h3>{section.title}</h3>
                <p>{section.text}</p>
              </div>
            </section>
          ))}
        </div>
      )}
    </aside>
  );
}
